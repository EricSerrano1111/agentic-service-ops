"""scripts/session_driver.py: ledger, IPv4 forcing, subcommands, evidence (S6-W1).

HTTP is mocked everywhere; nothing here opens a network connection. The IPv4 test fakes the
resolver and the socket class.
"""

from __future__ import annotations

import importlib.util
import json
import socket as socket_module
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "session_driver_under_test", ROOT / "scripts" / "session_driver.py"
)
sd = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = sd
_spec.loader.exec_module(sd)

LINK = "https://gw.example/#invite=SECRET-TOKEN-VALUE"
ANSWER = "The SLA compliance was 0.8813 across 160 requests. SECRET-ANSWER-TEXT"


class FakeGateway:
    """Records every request; answers like the gateway for the paths the driver uses."""

    def __init__(self, refuse_after: int | None = None, crash_on: int | None = None) -> None:
        self.calls: list[tuple[str, str, dict, dict | None]] = []
        self.refuse_after = refuse_after
        self.crash_on = crash_on
        self.asks = 0
        self.lock = threading.Lock()

    def __call__(self, method, url, headers, body):
        payload = json.loads(body) if body else None
        with self.lock:
            self.calls.append((method, url, headers, payload))
            if url.endswith("/auth/exchange"):
                if payload and payload.get("token") == "SECRET-TOKEN-VALUE":
                    return sd.Reply(
                        200,
                        {"signed_in": True},
                        {"x-trace-id": "t" * 32},
                        {sd.COOKIE_NAME: "cookie-value"},
                        0.01,
                    )
                return sd.Reply(
                    401, {"error": "invalid_invite"}, {"x-trace-id": "e" * 32}, {}, 0.01
                )
            if url.endswith("/api/ask"):
                self.asks += 1
                if self.crash_on is not None and self.asks == self.crash_on:
                    raise RuntimeError("process died mid-request")
                if self.refuse_after is not None and self.asks > self.refuse_after:
                    return sd.Reply(
                        429,
                        {"error": "session_limit", "detail": "Too many questions this hour"},
                        {"x-trace-id": "r" * 32},
                        {},
                        0.01,
                    )
                if "cookie" not in {k.lower() for k in headers}:
                    return sd.Reply(401, {"error": "sign_in_required"}, {}, {}, 0.01)
                return sd.Reply(
                    200,
                    {
                        "outcome": "answered",
                        "answer": ANSWER,
                        "qa_status": "verified",
                        "trace_id": "b" * 32,
                    },
                    {"x-trace-id": "b" * 32},
                    {},
                    0.5,
                )
        return sd.Reply(403, {}, {}, {}, 0.01)

    @property
    def ask_calls(self):
        return [c for c in self.calls if c[1].endswith("/api/ask")]


@pytest.fixture
def paths(tmp_path):
    return str(tmp_path / "ledger.json"), tmp_path / "ledger.json.evidence.jsonl"


@pytest.fixture(autouse=True)
def _credential(monkeypatch):
    monkeypatch.setenv(sd.CREDENTIAL_ENV, LINK)


def run(ledger, argv, gateway, **kw):
    out: list[str] = []
    code = sd.main(
        ["--ledger", ledger, "--base-url", "https://gw.example", *argv],
        transport=gateway,
        out=out.append,
        **kw,
    )
    return code, out


def init(ledger, requests=60, dollars=0.25):
    code, _ = run(
        ledger,
        ["init", "--max-requests", str(requests), "--max-dollars", str(dollars)],
        FakeGateway(),
    )
    assert code == 0


def state(ledger):
    return json.loads(Path(ledger).read_text("utf-8"))


# ------------------------------------------------------------------------------------ ledger


def test_request_cap_refuses_and_reserves_before_sending(paths):
    ledger, _ = paths
    init(ledger, requests=3)  # one slot goes to the exchange
    gw = FakeGateway()
    code, out = run(ledger, ["ask", "--scenario", "S", "--question", "q", "--repeat", "5"], gw)
    assert code == sd.EXIT_CAP
    assert len(gw.ask_calls) == 2  # exchange + 2 asks = 3 requests, the rest never sent
    assert state(ledger)["requests"] == 3
    assert any("NOT SENT" in line for line in out)


def test_dollar_cap_refuses(paths):
    ledger, _ = paths
    init(ledger, requests=50, dollars=0.006)  # two answered at $0.0029, not three
    gw = FakeGateway()
    code, _ = run(ledger, ["ask", "--scenario", "S", "--question", "q", "--repeat", "5"], gw)
    assert code == sd.EXIT_CAP
    assert len(gw.ask_calls) == 2
    assert state(ledger)["dollars"] == pytest.approx(0.0058)


def test_crash_after_reservation_leaves_the_count_raised(paths):
    ledger, evidence = paths
    init(ledger)
    gw = FakeGateway(crash_on=1)
    with pytest.raises(RuntimeError):
        run(ledger, ["ask", "--scenario", "S", "--question", "q"], gw)
    s = state(ledger)
    assert s["requests"] == 2  # exchange + the ask that died
    assert s["dollars"] == pytest.approx(0.0029)
    assert not Path(str(ledger) + ".lock").exists()


def test_parallel_never_passes_the_cap(paths):
    ledger, _ = paths
    init(ledger, requests=6)  # exchange + 5
    gw = FakeGateway()
    code, _ = run(
        ledger,
        [
            "ask",
            "--scenario",
            "S",
            "--question",
            "a",
            "--question",
            "b",
            "--repeat",
            "10",
            "--parallel",
            "8",
        ],
        gw,
    )
    assert code == sd.EXIT_CAP
    assert len(gw.ask_calls) == 5
    assert state(ledger)["requests"] == 6


def test_init_never_overwrites_and_status_prints_totals(paths):
    ledger, _ = paths
    init(ledger, requests=7, dollars=0.1)
    code, out = run(ledger, ["init", "--max-requests", "99", "--max-dollars", "9"], FakeGateway())
    assert code == sd.EXIT_USAGE and state(ledger)["max_requests"] == 7
    code, out = run(ledger, ["status"], FakeGateway())
    shown = json.loads("\n".join(out))
    assert code == 0 and shown["max_requests"] == 7 and shown["requests"] == 0
    assert "events" not in shown


def test_tally_adds_browser_questions_and_respects_the_cap(paths):
    ledger, _ = paths
    init(ledger, requests=10)
    code, _ = run(
        ledger, ["tally", "--count", "4", "--note", "browser: cold starts"], FakeGateway()
    )
    assert code == 0
    s = state(ledger)
    assert s["requests"] == 4 and s["dollars"] == pytest.approx(4 * 0.0029)
    code, out = run(ledger, ["tally", "--count", "7", "--note", "too many"], FakeGateway())
    assert code == sd.EXIT_CAP and state(ledger)["requests"] == 4


# --------------------------------------------------------------------------------- subcommands


def test_cap_test_stops_at_the_first_refusal_and_records_index_31(paths):
    ledger, evidence = paths
    init(ledger)
    gw = FakeGateway(refuse_after=30)
    code, out = run(ledger, ["cap-test", "--scenario", "TS-18-D"], gw)
    assert code == 0
    assert len(gw.ask_calls) == 31
    lines = [json.loads(x) for x in evidence.read_text("utf-8").splitlines()]
    refusal = [x for x in lines if x.get("refused")]
    assert len(refusal) == 1 and refusal[0]["index"] == 31
    assert refusal[0]["outcome"] == "session_limit"
    assert "refusal index: 31" in out[-1]


def test_cap_test_stops_when_the_ledger_does(paths):
    ledger, _ = paths
    init(ledger, requests=5)
    gw = FakeGateway()
    code, out = run(ledger, ["cap-test", "--scenario", "TS-18-D"], gw)
    assert code == sd.EXIT_CAP and len(gw.ask_calls) == 4
    assert out[-1] == "refusal index: None"


def test_probe_is_a_request_at_zero_dollars_and_needs_no_credential(paths, monkeypatch):
    ledger, evidence = paths
    monkeypatch.delenv(sd.CREDENTIAL_ENV)
    init(ledger)
    gw = FakeGateway()
    code, _ = run(ledger, ["probe", "--scenario", "TS-14-A", "--mode", "nosession"], gw)
    assert code == 0
    s = state(ledger)
    assert s["requests"] == 1 and s["dollars"] == 0.0
    assert "cookie" not in {k.lower() for k in gw.calls[0][2]}
    line = json.loads(evidence.read_text("utf-8").splitlines()[0])
    assert line["status"] == 401 and line["outcome"] == "sign_in_required"


def test_coldstart_waits_without_a_request_then_times_the_question(paths):
    ledger, evidence = paths
    init(ledger)
    gw = FakeGateway()
    waited = []
    code, out = run(
        ledger,
        ["coldstart", "--scenario", "TS-16-D", "--path", "sentiment", "--wait-seconds", "900"],
        gw,
        sleep=lambda s: waited.append((s, len(gw.calls))),
    )
    assert code == 0 and waited == [(900.0, 1)]  # only the exchange had been sent
    assert any("client-side latency 0.50s" in line for line in out)
    assert gw.ask_calls[0][3]["question"].startswith("What does customer sentiment")


def test_missing_credential_is_a_usage_error_and_sends_nothing(paths, monkeypatch):
    ledger, _ = paths
    monkeypatch.delenv(sd.CREDENTIAL_ENV)
    init(ledger)
    gw = FakeGateway()
    code, _ = run(ledger, ["ask", "--scenario", "S", "--question", "q"], gw)
    assert code == sd.EXIT_USAGE and gw.calls == [] and state(ledger)["requests"] == 0


# ---------------------------------------------------------------------------- evidence and secrets


def test_evidence_lines_carry_lengths_never_text_or_credentials(paths):
    ledger, evidence = paths
    init(ledger)
    gw = FakeGateway()
    question = "What is the secret question text?"
    code, out = run(ledger, ["ask", "--scenario", "TS-20-A", "--question", question], gw)
    assert code == 0
    raw = evidence.read_text("utf-8")
    for forbidden in (
        "SECRET-ANSWER-TEXT",
        "SLA compliance was",
        "secret question text",
        "SECRET-TOKEN-VALUE",
        "cookie-value",
    ):
        assert forbidden not in raw
        assert all(forbidden not in line for line in out)
    ask_line = [json.loads(x) for x in raw.splitlines()][-1]
    assert ask_line["scenario"] == "TS-20-A" and ask_line["subcommand"] == "ask"
    assert ask_line["trace_id"] == "b" * 32 and ask_line["status"] == 200
    assert ask_line["outcome"] == "answered" and ask_line["answer_chars"] == len(ANSWER)
    assert ask_line["question_chars"] == len(question) and "latency_s" in ask_line
    assert "SECRET-TOKEN-VALUE" not in json.dumps(state(ledger))


def test_the_session_cookie_and_origin_are_sent_on_asks(paths):
    ledger, _ = paths
    init(ledger)
    gw = FakeGateway()
    run(ledger, ["ask", "--scenario", "S", "--question", "q"], gw)
    exchange, ask = gw.calls[0], gw.calls[1]
    assert exchange[3] == {"token": "SECRET-TOKEN-VALUE"}
    assert ask[2]["Cookie"] == f"{sd.COOKIE_NAME}=cookie-value"
    assert ask[2]["Origin"] == "https://gw.example"
    assert ask[2]["Content-Type"] == "application/json"


# ---------------------------------------------------------------------------------------- IPv4


def test_ipv4_only_resolution_never_tries_an_ipv6_address(monkeypatch):
    verify = sd._load_verify()
    attempted: list[tuple] = []
    requested_families: list[int] = []

    def getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        requested_families.append(family)
        v6 = (
            socket_module.AF_INET6,
            socket_module.SOCK_STREAM,
            6,
            "",
            ("2600:1900::1", port, 0, 0),
        )
        v4 = (socket_module.AF_INET, socket_module.SOCK_STREAM, 6, "", ("203.0.113.9", port))
        return [v6, v4]  # IPv6 first, as the owner's PC resolves it

    class FakeSocket:
        def __init__(self, af, kind, proto):
            self.af = af

        def settimeout(self, _):
            pass

        def connect(self, sockaddr):
            attempted.append((self.af, sockaddr))

        def close(self):
            pass

    monkeypatch.setattr(verify.socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(verify.socket, "socket", FakeSocket)
    sock = verify.connect_socket(("gw.example", 443), 1.0, True)
    assert requested_families == [socket_module.AF_INET]
    assert attempted == [(socket_module.AF_INET, ("203.0.113.9", 443))]
    assert isinstance(sock, FakeSocket)


def test_the_real_transport_forces_ipv4_through_the_imported_mechanism(monkeypatch):
    verify = sd._load_verify()
    seen = {}

    def fake_connect(address, timeout, ipv4=False):
        seen["call"] = (address, timeout, ipv4)
        raise OSError("stop here: no network in tests")

    monkeypatch.setattr(verify, "connect_socket", fake_connect)
    reply = sd.ipv4_transport("GET", "https://gw.example/health", {}, None)
    assert seen["call"] == (("gw.example", 443), sd.CONNECT_TIMEOUT_S, True)
    assert reply.status is None and reply.error == "OSError"
