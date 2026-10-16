"""Owner-session driver (ADR-110): traffic through the deployed gateway, counted before it is sent.

Spec: scripts/SESSION_DRIVER.md. Every request reserves its slot in the ledger file, and the file
is written, before the request leaves; costs are worst-case constants by request type, never read
from a response. IPv4 only. The evidence log carries lengths, never question or answer text.

    python scripts/session_driver.py --ledger L init --max-requests 60 --max-dollars 0.25
    $env:SESSION_INVITE_LINK = '<link>'
    python scripts/session_driver.py --ledger L ask --scenario TS-20-A --question "..."
"""

from __future__ import annotations

import argparse
import contextlib
import http.client
import importlib.util
import json
import os
import ssl
import sys
import threading
import time
import urllib.parse
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = "https://ops-gateway-587647038690.us-central1.run.app"
CREDENTIAL_ENV = "SESSION_INVITE_LINK"
COOKIE_NAME = "__Host-session"
CONNECT_TIMEOUT_S = 10.0
READ_TIMEOUT_S = 150.0
CAP_TEST_MAX = 31

#: Worst-case dollars per request by type: calls x $0.00058 (plan, section 5; L-71 list price).
COSTS: dict[str, float] = {
    "answered": 0.0029,  # 5 calls
    "clarify": 0.0023,  # 4
    "failure": 0.0023,  # 4
    "declined": 0.0012,  # 2
    "probe": 0.0,
    "exchange": 0.0,
}
ASK_KINDS = ("answered", "clarify", "failure", "declined")
#: The 05 texts the plan uses (TS-05-B, TS-07-A, TS-08-B).
COLDSTART_QUESTIONS = {
    "reporting": "What was SLA compliance in the west region in July 2026?",
    "sentiment": "What does customer sentiment look like across all sites for July 2026?",
    "forecast": "How many install requests should we expect over the next 8 weeks?",
}
DECLINED_QUESTION = "How do our response times compare with other field service companies?"

EXIT_OK, EXIT_USAGE, EXIT_CAP, EXIT_EXCHANGE = 0, 2, 3, 4


# ------------------------------------------------------------------------------------ ledger


class LedgerError(RuntimeError):
    pass


class CapReached(LedgerError):
    """A request would pass a cap; nothing was sent."""


#: On Windows, `os.open(O_CREAT|O_EXCL)` raises `PermissionError`, not `FileExistsError`, while
#: another thread is deleting the lock file (S6-L1). That is the same "held" state, so it waits and
#: retries, a bounded number of times in a row; a real permission problem (a read-only folder)
#: then surfaces as the error itself instead of hanging until the timeout.
LOCK_PERMISSION_TRIES = 50
LOCK_PERMISSION_WAIT_S = 0.05


@contextlib.contextmanager
def _file_lock(path: Path, timeout: float = 30.0) -> Iterator[None]:
    lock = path.with_name(path.name + ".lock")
    deadline = time.monotonic() + timeout
    denied = 0
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            denied = 0
            if time.monotonic() > deadline:
                raise LedgerError(
                    f"ledger lock {lock} is held; if no driver is running, delete it"
                ) from None
            time.sleep(0.01)
        except PermissionError:
            denied += 1
            if denied >= LOCK_PERMISSION_TRIES:
                raise
            time.sleep(LOCK_PERMISSION_WAIT_S)
    try:
        yield
    finally:
        os.close(fd)
        with contextlib.suppress(FileNotFoundError):
            os.unlink(lock)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class Ledger:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def _load(self) -> dict:
        try:
            return json.loads(self.path.read_text("utf-8"))
        except FileNotFoundError:
            raise LedgerError(f"no ledger at {self.path}; run `init` first") from None

    def _save(self, state: dict) -> None:
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)

    def init(self, max_requests: int, max_dollars: float) -> None:
        with _file_lock(self.path):
            if self.path.exists():
                raise LedgerError(f"{self.path} exists; caps are never changed after creation")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._save(
                {
                    "max_requests": max_requests,
                    "max_dollars": max_dollars,
                    "requests": 0,
                    "dollars": 0.0,
                    "by_kind": {},
                    "events": [],
                }
            )

    def reserve(self, kind: str, scenario: str = "", note: str = "", count: int = 1) -> None:
        """Count `count` requests of `kind` and write the file; raise `CapReached` before that if
        either cap would be passed. Called before the request is sent."""
        if kind not in COSTS:
            raise LedgerError(f"unknown request type {kind!r}")
        cost = COSTS[kind] * count
        with _file_lock(self.path):
            s = self._load()
            if s["requests"] + count > s["max_requests"]:
                raise CapReached(f"request cap: {s['requests']} of {s['max_requests']} counted")
            if s["dollars"] + cost > s["max_dollars"] + 1e-9:
                raise CapReached(
                    f"spend cap: ${s['dollars']:.4f} counted, next ${cost:.4f}, "
                    f"cap ${s['max_dollars']:.2f}"
                )
            s["requests"] += count
            s["dollars"] = round(s["dollars"] + cost, 6)
            bk = s["by_kind"].setdefault(kind, {"requests": 0, "dollars": 0.0})
            bk["requests"] += count
            bk["dollars"] = round(bk["dollars"] + cost, 6)
            s["events"].append(
                {"at": _now(), "kind": kind, "count": count, "scenario": scenario, "note": note}
            )
            self._save(s)

    def status(self) -> dict:
        s = self._load()
        return {k: v for k, v in s.items() if k != "events"}


# ---------------------------------------------------------------------------------- transport


@dataclass
class Reply:
    status: int | None
    body: dict = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)  # lower-case names
    cookies: dict[str, str] = field(default_factory=dict)
    seconds: float = 0.0
    error: str = ""


Transport = Callable[[str, str, dict[str, str], bytes | None], Reply]


def _load_verify():
    """deploy/verify.py's IPv4 mechanism (`connect_socket`), imported, not copied."""
    name = "deploy_verify_session_driver"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "deploy" / "verify.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def ipv4_transport(method: str, url: str, headers: dict[str, str], body: bytes | None) -> Reply:
    connect_socket = _load_verify().connect_socket
    parts = urllib.parse.urlsplit(url)
    https = parts.scheme == "https"
    host, port = parts.hostname or "", parts.port or (443 if https else 80)
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    base = http.client.HTTPSConnection if https else http.client.HTTPConnection

    class Connection(base):  # type: ignore[misc, valid-type]
        def connect(self) -> None:
            sock = connect_socket((host, port), CONNECT_TIMEOUT_S, True)
            if https:
                sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
            sock.settimeout(READ_TIMEOUT_S)
            self.sock = sock

    began = time.perf_counter()
    conn = Connection(host, port, timeout=READ_TIMEOUT_S)
    try:
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
        try:
            parsed = json.loads(raw) if raw else {}
        except ValueError:
            parsed = {}
        cookies = {}
        for line in resp.msg.get_all("Set-Cookie") or []:
            pair = line.split(";", 1)[0]
            if "=" in pair:
                k, v = pair.split("=", 1)
                cookies[k.strip()] = v.strip()
        return Reply(
            resp.status,
            parsed if isinstance(parsed, dict) else {},
            {k.lower(): v for k, v in resp.getheaders()},
            cookies,
            time.perf_counter() - began,
        )
    except (OSError, http.client.HTTPException) as exc:
        return Reply(None, seconds=time.perf_counter() - began, error=type(exc).__name__)
    finally:
        conn.close()


# ------------------------------------------------------------------------------------ driver


def invite_token(value: str) -> str:
    """The token from a link (`<base>/#invite=<token>`) or a bare token."""
    return value.split("#invite=", 1)[1] if "#invite=" in value else value.strip()


class Evidence:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def write(self, **fields) -> None:
        line = json.dumps({"at": _now(), **fields}, separators=(",", ":"))
        with self._lock, self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


class Driver:
    def __init__(
        self,
        ledger: Ledger,
        evidence: Evidence,
        base_url: str,
        transport: Transport,
        scenario: str = "",
        sleep: Callable[[float], None] = time.sleep,
        out: Callable[[str], None] = print,
    ) -> None:
        self.ledger, self.evidence = ledger, evidence
        self.base = base_url.rstrip("/")
        self.transport, self.scenario, self.sleep, self.out = transport, scenario, sleep, out
        self.cookie: str | None = None
        self.cap_hit = False
        self.cap_verdict: str | None = None

    # -- one request: reserve, send, record
    def _send(
        self,
        subcommand: str,
        kind: str,
        method: str,
        url: str,
        headers: dict[str, str],
        payload: dict | None,
        **extra,
    ) -> Reply | None:
        try:
            self.ledger.reserve(kind, self.scenario, subcommand)
        except CapReached as exc:
            self.cap_hit = True
            self.evidence.write(
                scenario=self.scenario,
                subcommand=subcommand,
                status=None,
                outcome="ledger_refused",
                **extra,
            )
            self.out(f"[{self.scenario}] {subcommand} NOT SENT: {exc}")
            return None
        body = json.dumps(payload).encode() if payload is not None else None
        reply = self.transport(method, url, headers, body)
        ok = reply.status == 200
        outcome = reply.body.get("outcome") if ok else reply.body.get("error")
        trace = reply.headers.get("x-trace-id") or reply.body.get("trace_id")
        self.evidence.write(
            scenario=self.scenario,
            subcommand=subcommand,
            trace_id=trace,
            status=reply.status,
            latency_s=round(reply.seconds, 3),
            outcome=outcome or reply.error or None,
            qa_status=reply.body.get("qa_status") if ok else None,
            answer_chars=len(str(reply.body.get("answer", ""))) if ok else None,
            **extra,
        )
        self.out(
            f"[{self.scenario}] {subcommand} status={reply.status} outcome={outcome or reply.error}"
            f" {reply.seconds:.2f}s trace={trace}"
        )
        return reply

    def _json_headers(self, origin: str | None = None, cookie: str | None = None) -> dict[str, str]:
        h = {"Content-Type": "application/json", "Origin": origin or self.base}
        if cookie:
            h["Cookie"] = f"{COOKIE_NAME}={cookie}"
        return h

    def sign_in(self, token: str) -> bool:
        reply = self._send(
            "exchange",
            "exchange",
            "POST",
            f"{self.base}/auth/exchange",
            self._json_headers(),
            {"token": token},
        )
        if reply is None or reply.status != 200 or COOKIE_NAME not in reply.cookies:
            return False
        self.cookie = reply.cookies[COOKIE_NAME]
        return True

    def ask_one(self, question: str, kind: str, subcommand: str = "ask", **extra) -> Reply | None:
        return self._send(
            subcommand,
            kind,
            "POST",
            f"{self.base}/api/ask",
            self._json_headers(cookie=self.cookie),
            {"question": question},
            question_chars=len(question),
            **extra,
        )

    # -- subcommands
    def ask(self, questions: list[str], kind: str, repeat: int, parallel: int) -> None:
        jobs = [q for q in questions for _ in range(repeat)]
        with ThreadPoolExecutor(max_workers=max(1, parallel)) as pool:
            list(pool.map(lambda q: self.ask_one(q, kind), jobs))

    def probe(self, url: str, mode: str, method: str) -> Reply | None:
        if mode == "nosession":
            headers = self._json_headers()
        elif mode == "badtoken":
            headers = self._json_headers(cookie="not-a-real-session")
        else:  # wrongorigin: the Origin check runs before the token is looked at
            headers = self._json_headers(origin="https://example.invalid")
        payload = None
        if mode == "wrongorigin":
            url = f"{self.base}/auth/exchange" if url == f"{self.base}/api/ask" else url
            payload = {"token": "not-a-real-token"}
            method = "POST"
        elif method == "POST":
            payload = {"question": "hello"}
        return self._send("probe", "probe", method, url, headers, payload, mode=mode)

    def coldstart(self, path: str, token: str, wait_seconds: float) -> Reply | None:
        if not self.sign_in(token):
            return None
        if wait_seconds > 0:
            self.sleep(wait_seconds)  # no request while idle
        return self.ask_one(COLDSTART_QUESTIONS[path], "answered", "coldstart", path=path)

    def cap_test(self, token: str, maximum: int, question: str) -> int | None:
        """Questions in sequence on one invite; stops at the first refusal. Returns its 1-based
        index, or None when no refusal came (or the ledger stopped it first)."""
        self.cap_verdict = "inconclusive"
        if not self.sign_in(token):
            return None
        for i in range(1, maximum + 1):
            reply = self.ask_one(question, "declined", "cap-test", index=i)
            if reply is None:
                return None
            if reply.status == 429 and reply.body.get("error") in ("session_limit", "daily_limit"):
                error = reply.body.get("error")
                # Only the hourly cap at the 31st question is a PASS (TS-18-D); a daily-cap
                # refusal or a refusal at another index says nothing about the hourly limit.
                self.cap_verdict = (
                    "pass" if error == "session_limit" and i == 31 else "inconclusive"
                )
                self.evidence.write(
                    scenario=self.scenario,
                    subcommand="cap-test",
                    index=i,
                    refused=True,
                    error=error,
                    outcome=self.cap_verdict,
                )
                self.out(f"[{self.scenario}] cap-test: refused at question {i} ({error})")
                return i
        self.cap_verdict = "inconclusive"
        self.evidence.write(
            scenario=self.scenario,
            subcommand="cap-test",
            index=None,
            refused=False,
            error=None,
            outcome="inconclusive",
        )
        return None


# ------------------------------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="session_driver.py")
    p.add_argument("--ledger", required=True, help="ledger JSON path")
    p.add_argument("--evidence", help="evidence JSONL path (default: <ledger>.evidence.jsonl)")
    p.add_argument("--base-url", default=os.environ.get("GATEWAY_PUBLIC_ORIGIN", DEFAULT_BASE))
    sub = p.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init")
    init.add_argument("--max-requests", type=int, required=True)
    init.add_argument("--max-dollars", type=float, required=True)
    sub.add_parser("status")
    tally = sub.add_parser("tally")
    tally.add_argument("--count", type=int, required=True)
    tally.add_argument("--note", required=True)
    tally.add_argument("--kind", choices=ASK_KINDS, default="answered")
    tally.add_argument("--scenario", default="")

    ask = sub.add_parser("ask")
    ask.add_argument("--scenario", required=True)
    ask.add_argument("--question", action="append", required=True)
    ask.add_argument("--kind", choices=ASK_KINDS, default="answered")
    ask.add_argument("--repeat", type=int, default=1)
    ask.add_argument("--parallel", type=int, default=1)

    probe = sub.add_parser("probe")
    probe.add_argument("--scenario", required=True)
    probe.add_argument("--url")
    probe.add_argument(
        "--mode", choices=("nosession", "badtoken", "wrongorigin"), default="nosession"
    )
    probe.add_argument("--method", choices=("GET", "POST"), default="POST")

    cold = sub.add_parser("coldstart")
    cold.add_argument("--scenario", required=True)
    cold.add_argument("--path", choices=tuple(COLDSTART_QUESTIONS), required=True)
    cold.add_argument("--wait-seconds", type=float, default=0.0)

    cap = sub.add_parser("cap-test")
    cap.add_argument("--scenario", required=True)
    cap.add_argument("--max", type=int, default=CAP_TEST_MAX)
    cap.add_argument("--question", default=DECLINED_QUESTION)
    return p


def main(
    argv: list[str] | None = None,
    *,
    transport: Transport = ipv4_transport,
    sleep: Callable[[float], None] = time.sleep,
    out: Callable[[str], None] = print,
) -> int:
    args = build_parser().parse_args(argv)
    ledger = Ledger(args.ledger)
    try:
        if args.command == "init":
            ledger.init(args.max_requests, args.max_dollars)
            out(json.dumps(ledger.status()))
            return EXIT_OK
        if args.command == "status":
            out(json.dumps(ledger.status(), indent=1))
            return EXIT_OK
        if args.command == "tally":
            if args.count < 1:
                return EXIT_USAGE
            ledger.reserve(args.kind, args.scenario, f"tally: {args.note}", count=args.count)
            out(json.dumps(ledger.status()))
            return EXIT_OK
    except CapReached as exc:
        out(f"REFUSED: {exc}")
        return EXIT_CAP
    except LedgerError as exc:
        out(f"error: {exc}")
        return EXIT_USAGE

    evidence_path = args.evidence or f"{args.ledger}.evidence.jsonl"
    driver = Driver(
        ledger, Evidence(Path(evidence_path)), args.base_url, transport, args.scenario, sleep, out
    )
    try:
        if args.command == "probe":
            driver.probe(args.url or f"{driver.base}/api/ask", args.mode, args.method)
            return EXIT_CAP if driver.cap_hit else EXIT_OK
        link = os.environ.get(CREDENTIAL_ENV, "")
        if not link:
            out(f"error: set {CREDENTIAL_ENV} to the invite link (it is never printed)")
            return EXIT_USAGE
        token = invite_token(link)
        if args.command == "ask":
            if not driver.sign_in(token):
                return EXIT_CAP if driver.cap_hit else EXIT_EXCHANGE
            driver.ask(args.question, args.kind, args.repeat, args.parallel)
        elif args.command == "coldstart":
            reply = driver.coldstart(args.path, token, args.wait_seconds)
            if reply is None and not driver.cap_hit:
                return EXIT_EXCHANGE
            if reply is not None:
                out(f"client-side latency {reply.seconds:.2f}s")
        elif args.command == "cap-test":
            index = driver.cap_test(token, args.max, args.question)
            out(f"refusal index: {index}")
            out(f"cap-test verdict: {driver.cap_verdict}")
    except LedgerError as exc:
        out(f"error: {exc}")
        return EXIT_USAGE
    return EXIT_CAP if driver.cap_hit else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
