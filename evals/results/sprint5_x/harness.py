"""Prompt X harness: blind evaluation runs against the deployed orchestrator's /ask.

    .venv\\Scripts\\python evals/results/sprint5_x/harness.py routing [--passes 3]
    .venv\\Scripts\\python evals/results/sprint5_x/harness.py golden

Calls the deployed orchestrator directly (never the gateway), authenticated with the caller's
own gcloud identity, one request at a time, **no retries**. A request that errors or times out
is recorded as such and scored by the pre-registered taxonomy.

Ledger (evals/results/sprint5_x_ledger.json): requests are counted directly; per-request cost is
the orchestrator's `ask answered` / degraded log line (`cost_usd`), looked up by trace_id with
`gcloud logging read` (read-only), one request behind. A lookup that finds nothing after 30 s
is recorded as unknown and charged at the highest cost seen so far for the cap check.
Stop rules: 186 requests, $1.50, 5 errors in a row (outage). Resumable: completed
(run, item) pairs in the results files are never re-run. Never raises a cap.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
RESULTS = ROOT / "evals" / "results"
LEDGER = RESULTS / "sprint5_x_ledger.json"
ROUTING_SET = ROOT / "evals" / "generated" / "sets" / "routing_heldout_v1.jsonl"
GOLDEN_SET = ROOT / "evals" / "golden" / "golden_v2.jsonl"
DATE = "2026-10-13"
PROJECT = "a2a-agentic-service-ops-gcp"
ORCHESTRATOR_URL = "https://ops-orchestrator-vszrpegifq-uc.a.run.app"
CAP_REQUESTS = 186
CAP_MODEL_CALLS = 1000  # not countable per request; bounded by 186 x 5 = 930 (reported as such)
CAP_USD = 1.50
CONSECUTIVE_ERRORS = 5
HTTP_TIMEOUT_S = 150
LOG_WAIT_S = 30
REQUIRED_KEYS = ("route", "qa_status", "escalate", "outcome", "parsed_request", "trace_id")
TOKEN_TTL_S = 40 * 60


class Stop(RuntimeError):
    """A stop rule fired; what has been recorded stays, and the run is reported as partial."""


def now() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def gcloud(*args: str, check: bool = True) -> str:
    done = subprocess.run(
        ["gcloud", *args],
        capture_output=True,
        text=True,
        shell=sys.platform == "win32",
        check=check,
    )
    return done.stdout.strip()


# ------------------------------------------------------------------------------------ ledger


class Ledger:
    """Process-safe enough for one runner at a time; written after every request."""

    def __init__(self, path: Path = LEDGER) -> None:
        self.path = path
        if not path.exists():
            self._save(
                {
                    "cap_requests": CAP_REQUESTS,
                    "cap_model_calls": CAP_MODEL_CALLS,
                    "model_calls_note": "not returned per request; bounded by requests x 5",
                    "cap_usd": CAP_USD,
                    "requests": 0,
                    "cost_usd_known": 0.0,
                    "unknown_cost_requests": 0,
                    "max_request_cost_usd": 0.0,
                    "by_path": {},
                    "events": [],
                }
            )
        self.lock = threading.Lock()

    def state(self) -> dict:
        return json.loads(self.path.read_text("utf-8"))

    def _save(self, state: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)

    def charged(self, s: dict) -> float:
        """Known cost plus each unknown request at the highest cost seen."""
        return s["cost_usd_known"] + s["unknown_cost_requests"] * s["max_request_cost_usd"]

    def check(self, pending_unresolved: int) -> None:
        s = self.state()
        if s["requests"] + 1 > s["cap_requests"]:
            raise Stop(f"request cap: {s['requests']} of {s['cap_requests']} sent")
        worst = s["max_request_cost_usd"]
        # the previous request's lookup is still pending: charge it, and the next one, at worst
        projected = self.charged(s) + (pending_unresolved + 1) * worst
        if projected > s["cap_usd"]:
            raise Stop(f"spend cap: ${projected:.4f} projected against ${s['cap_usd']:.2f}")

    def sent(self, path: str, label: str) -> None:
        with self.lock:
            s = self.state()
            s["requests"] += 1
            bp = s["by_path"].setdefault(path, {"requests": 0, "cost_usd_known": 0.0})
            bp["requests"] += 1
            s["events"].append({"at": now(), "event": "sent", "path": path, "label": label})
            self._save(s)

    def cost(self, path: str, label: str, trace_id: str | None, cost: float | None) -> None:
        with self.lock:
            s = self.state()
            bp = s["by_path"].setdefault(path, {"requests": 0, "cost_usd_known": 0.0})
            if cost is None:
                s["unknown_cost_requests"] += 1
            else:
                s["cost_usd_known"] = round(s["cost_usd_known"] + cost, 8)
                bp["cost_usd_known"] = round(bp["cost_usd_known"] + cost, 8)
                s["max_request_cost_usd"] = max(s["max_request_cost_usd"], cost)
            s["events"].append(
                {
                    "at": now(),
                    "event": "cost",
                    "path": path,
                    "label": label,
                    "trace_id": trace_id,
                    "cost_usd": cost,
                }
            )
            self._save(s)


# -------------------------------------------------------------------------------- transport


class Caller:
    def __init__(self) -> None:
        self._token = ""
        self._minted = 0.0
        self.account = gcloud("config", "get-value", "account")

    def token(self) -> str:
        if not self._token or time.time() - self._minted > TOKEN_TTL_S:
            self._token = gcloud("auth", "print-identity-token", f"--audiences={ORCHESTRATOR_URL}")
            self._minted = time.time()
        return self._token

    def ask(self, question: str) -> tuple[int | None, dict, float, str]:
        """(HTTP status or None, body, seconds, error text). One attempt."""
        data = json.dumps({"question": question}).encode()
        request = urllib.request.Request(ORCHESTRATOR_URL + "/ask", data=data, method="POST")
        request.add_header("Content-Type", "application/json")
        request.add_header("Authorization", f"Bearer {self.token()}")
        began = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response:  # noqa: S310
                body = json.loads(response.read() or b"{}")
                return response.status, body, time.perf_counter() - began, ""
        except urllib.error.HTTPError as exc:
            try:
                body = json.loads(exc.read() or b"{}")
            except ValueError:
                body = {}
            return exc.code, body, time.perf_counter() - began, f"HTTP {exc.code}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return None, {}, time.perf_counter() - began, type(exc).__name__


def logged_cost(trace_id: str) -> float | None:
    """`cost_usd` from the orchestrator's log line for this trace; None if it never arrives."""
    flt = (
        "resource.type=cloud_run_revision AND resource.labels.service_name=ops-orchestrator "
        f'AND jsonPayload.trace_id="{trace_id}" AND jsonPayload.cost_usd:*'
    )
    deadline = time.time() + LOG_WAIT_S
    while True:
        out = gcloud(
            "logging",
            "read",
            flt,
            f"--project={PROJECT}",
            "--freshness=1d",
            "--limit=5",
            "--format=json(jsonPayload.cost_usd)",
            check=False,
        )
        try:
            rows = json.loads(out or "[]")
        except ValueError:
            rows = []
        costs = [r["jsonPayload"]["cost_usd"] for r in rows if "jsonPayload" in r]
        if costs:
            return float(max(costs))
        if time.time() >= deadline:
            return None
        time.sleep(3)


# ------------------------------------------------------------------------------------ runner


class Session:
    def __init__(self, path_name: str) -> None:
        self.ledger = Ledger()
        self.caller = Caller()
        self.path_name = path_name
        self.lookups: list[threading.Thread] = []
        self.errors_in_a_row = 0
        self.checked_fields = False

    def _lookup(self, label: str, trace_id: str | None) -> None:
        cost = logged_cost(trace_id) if trace_id else None
        self.ledger.cost(self.path_name, label, trace_id, cost)

    def _unresolved(self) -> int:
        self.lookups = [t for t in self.lookups if t.is_alive()]
        return len(self.lookups)

    def call(self, label: str, question: str) -> dict:
        """One request with ledger accounting. Returns the result row."""
        # one request behind: every lookup but the most recent must be finished
        for t in self.lookups[:-1]:
            t.join()
        self.ledger.check(self._unresolved())
        self.ledger.sent(self.path_name, label)
        status, body, seconds, err = self.caller.ask(question)
        trace_id = body.get("trace_id") if isinstance(body, dict) else None
        usable = status == 200 and isinstance(body, dict) and "outcome" in body
        degraded_unrouted = usable and body.get("outcome") == "degraded" and not body.get("route")
        errored = (not usable) or degraded_unrouted
        if usable and not self.checked_fields:
            missing = [k for k in REQUIRED_KEYS if k not in body]
            if missing:
                raise Stop(f"response lacks {missing}: stop per section 0")
            self.checked_fields = True
        thread = threading.Thread(target=self._lookup, args=(label, trace_id), daemon=True)
        thread.start()
        self.lookups.append(thread)
        self.errors_in_a_row = self.errors_in_a_row + 1 if errored else 0
        row = {
            "label": label,
            "question": question,
            "at": now(),
            "http_status": status,
            "seconds": round(seconds, 2),
            "error": err or ("degraded before routing" if degraded_unrouted else ""),
            "response": body,
        }
        return row


# ---------------------------------------------------------------------------------- commands


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text("utf-8").splitlines() if x.strip()]


def save_run(path: Path, meta: dict, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({**meta, "rows": rows}, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def run_routing(passes: int) -> None:
    items = load_jsonl(ROUTING_SET)
    assert len(items) == 50, len(items)
    out_dir = RESULTS / "routing_heldout_v1" / DATE
    session = Session("X1")
    stopped = ""
    try:
        for p in range(1, passes + 1):
            path = out_dir / f"run{p}.json"
            existing = json.loads(path.read_text("utf-8")) if path.exists() else {"rows": []}
            rows = existing["rows"]
            done = {r["id"] for r in rows}
            meta = {
                "set": "routing_heldout_v1",
                "pass": p,
                "date": DATE,
                "orchestrator": ORCHESTRATOR_URL,
                "caller": session.caller.account,
            }
            for it in items:
                if it["uid"] in done:
                    continue
                row = session.call(f"X1/p{p}/{it['uid']}", it["item"]["question"])
                row.update(
                    {
                        "id": it["uid"],
                        "category": it["item"]["category"],
                        "expected": it["system_route"],
                        "expected_candidates": it["item"].get("candidate_areas") or [],
                    }
                )
                rows.append(row)
                save_run(path, meta | {"complete": len(rows) == len(items)}, rows)
                if session.errors_in_a_row >= CONSECUTIVE_ERRORS:
                    raise Stop(f"{CONSECUTIVE_ERRORS} errors in a row: outage")
    except Stop as stop:
        stopped = str(stop)
    for t in session.lookups:
        t.join()
    print("STOPPED:" if stopped else "X1 complete.", stopped)
    print(json.dumps({k: v for k, v in session.ledger.state().items() if k != "events"}, indent=1))


def run_golden() -> None:
    items = load_jsonl(GOLDEN_SET)
    assert len(items) == 36, len(items)
    path = RESULTS / "golden_v2" / DATE / "run1.json"
    existing = json.loads(path.read_text("utf-8")) if path.exists() else {"rows": []}
    rows = existing["rows"]
    done = {r["id"] for r in rows}
    session = Session("X2")
    meta = {"set": "golden_v2", "date": DATE, "orchestrator": ORCHESTRATOR_URL}
    meta["caller"] = session.caller.account
    stopped = ""
    try:
        for it in items:
            if it["id"] in done:
                continue
            row = session.call(f"X2/{it['id']}", it["question"])
            row["id"] = it["id"]
            rows.append(row)
            save_run(path, meta | {"complete": len(rows) == len(items)}, rows)
            if session.errors_in_a_row >= CONSECUTIVE_ERRORS:
                raise Stop(f"{CONSECUTIVE_ERRORS} errors in a row: outage")
    except Stop as stop:
        stopped = str(stop)
    for t in session.lookups:
        t.join()
    print("STOPPED:" if stopped else "X2 complete.", stopped)
    print(json.dumps({k: v for k, v in session.ledger.state().items() if k != "events"}, indent=1))


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("routing")
    r.add_argument("--passes", type=int, default=3)
    sub.add_parser("golden")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    if args.cmd == "routing":
        run_routing(args.passes)
    else:
        run_golden()
    return 0


if __name__ == "__main__":
    sys.exit(main())
