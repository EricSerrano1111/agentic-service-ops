"""verify.py's window-day options (S6-T1, deploy/README.md "Window-day options").

No network beyond loopback and no gcloud: the resolver, the socket class and the process
runner are faked. A real subprocess is started in one test only, and it is the Python
interpreter, not gcloud.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

DEPLOY = Path(__file__).resolve().parents[2] / "deploy"


def _load():
    spec = importlib.util.spec_from_file_location("deploy_verify_window", DEPLOY / "verify.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


verify = _load()
socket = verify.socket  # the stdlib module; patched through monkeypatch only

ENV = {
    "PROJECT_ID": "proj-x",
    "PROJECT_NUMBER": "123456789",
    "REGION": "us-central1",
    "EXPECTED_IMAGE_TAG": "abc123",
    "ORCHESTRATOR_SA": "run-orchestrator@proj-x.iam.gserviceaccount.com",
    "REPORTING_SA": "run-reporting@proj-x.iam.gserviceaccount.com",
    "PROBE_SA": "probe-noauth@proj-x.iam.gserviceaccount.com",
    "CLOUD_SQL_INSTANCE_NAME": "ops-db",
}
TOKEN = "ya29.SECRET-IDENTITY-TOKEN"


@pytest.fixture
def env(monkeypatch):
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("CALLER_SA", raising=False)
    monkeypatch.delenv("QUESTION", raising=False)


def service_json(name: str) -> dict:
    return {
        "metadata": {"name": name},
        "status": {
            "url": f"https://{name}-abc.a.run.app",
            "traffic": [{"percent": 100, "revisionName": f"{name}-00001"}],
            "latestReadyRevisionName": f"{name}-00001",
        },
        "spec": {
            "template": {
                "spec": {
                    "serviceAccountName": "x@proj-x.iam.gserviceaccount.com",
                    "containers": [{"name": "c", "image": "img:abc123", "env": []}],
                }
            }
        },
    }


class FakeGcloud:
    """Stands in for `verify.run_process`: records every call, answers from `answers`."""

    def __init__(self, events: list | None = None, fail=None):
        self.calls: list[tuple[str, ...]] = []
        self.timeouts: list[float] = []
        self.events = events if events is not None else []
        self.fail = fail or (lambda args: None)

    def __call__(self, argv, timeout):
        args = tuple(argv[1:])
        self.calls.append(args)
        self.timeouts.append(timeout)
        self.events.append(("run", " ".join(args)))
        outcome = self.fail(args)
        if outcome is not None:
            raise outcome
        if args[:3] == ("run", "services", "describe"):
            return json.dumps(service_json(args[3]))
        if args[:3] == ("run", "services", "get-iam-policy"):
            return json.dumps({"bindings": []})
        if args[:2] == ("auth", "print-identity-token"):
            return TOKEN
        if args[:2] == ("config", "get-value"):
            return "owner@example.com"
        return json.dumps({})


def expired(args):
    return subprocess.TimeoutExpired(["gcloud", *args], 1)


# ------------------------------------------------------------------ loopback server and resolver


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/slow":
                time.sleep(1.0)
            body = b'{"hello": "world"}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv.server_address[1]
    srv.shutdown()
    srv.server_close()


@pytest.fixture
def resolver(monkeypatch, server):
    """`svc.run.app` resolves to an IPv6 address (nothing listens) and then the loopback IPv4
    one, whatever family was asked for: a resolver that ignores the request must not matter."""
    real = socket.getaddrinfo
    asked: list[int] = []

    def getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        if host != "svc.run.app":
            return real(host, port, family, type, proto, flags)
        asked.append(family)
        return [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", port, 0, 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    return asked


@pytest.fixture
def families(monkeypatch):
    """Every socket family opened from here on."""
    seen: list[int] = []
    real = socket.socket

    class Spy(real):
        def __init__(self, family=-1, type=-1, proto=-1, fileno=None):
            seen.append(family)
            super().__init__(family, type, proto, fileno)

    monkeypatch.setattr(socket, "socket", Spy)
    return seen


def test_ipv4_resolves_for_ipv4_only_and_never_opens_an_ipv6_socket(server, resolver, families):
    status, body = verify.http(
        "GET", f"http://svc.run.app:{server}/", opts=verify.Options(ipv4=True)
    )
    assert (status, body) == (200, {"hello": "world"})
    assert resolver == [socket.AF_INET]
    assert socket.AF_INET6 not in families


def test_default_resolution_is_unchanged_and_may_try_ipv6_first(server, resolver, families):
    status, _ = verify.http("GET", f"http://svc.run.app:{server}/")
    assert status == 200  # the IPv6 address refused (or does not exist); IPv4 answered
    assert resolver == [socket.AF_UNSPEC]
    assert families[0] == socket.AF_INET6


def test_the_url_is_not_rewritten_to_an_address(server, resolver):
    seen: list[str] = []
    # the Host header sent is the name, not 127.0.0.1
    import http.client

    original = http.client.HTTPConnection.putheader

    def putheader(self, header, *values):
        if header.lower() == "host":
            seen.append(values[0])
        return original(self, header, *values)

    http.client.HTTPConnection.putheader = putheader
    try:
        verify.http("GET", f"http://svc.run.app:{server}/", opts=verify.Options(ipv4=True))
    finally:
        http.client.HTTPConnection.putheader = original
    assert seen and all(h.startswith("svc.run.app") for h in seen)


# ------------------------------------------------------------------------------ connect timeout


class FakeSock:
    """A socket whose connect times out for the addresses in `slow`."""

    slow: set[str] = set()
    connected: list[str] = []

    def __init__(self, family=-1, type=-1, proto=-1, fileno=None):
        self.family = family

    def settimeout(self, value):
        self.timeout = value

    def connect(self, sockaddr):
        if sockaddr[0] in self.slow:
            raise TimeoutError("timed out")
        self.connected.append(sockaddr[0])

    def close(self):
        pass


@pytest.fixture
def fake_net(monkeypatch):
    FakeSock.slow = set()
    FakeSock.connected = []
    monkeypatch.setattr(socket, "socket", FakeSock)

    def getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        both = [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2001:db8::1", port, 0, 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("203.0.113.1", port)),
        ]
        return both if family == socket.AF_UNSPEC else [i for i in both if i[0] == family]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    return FakeSock


def test_a_timed_out_address_falls_through_to_the_next(fake_net):
    fake_net.slow = {"2001:db8::1"}
    sock = verify.connect_socket(("svc.run.app", 443), 0.01)
    assert isinstance(sock, FakeSock) and fake_net.connected == ["203.0.113.1"]


def test_every_address_timing_out_is_a_connect_timeout(fake_net):
    fake_net.slow = {"2001:db8::1", "203.0.113.1"}
    with pytest.raises(verify.ConnectTimeout):
        verify.connect_socket(("svc.run.app", 443), 0.01)


def test_ipv4_mode_only_tries_ipv4_addresses(fake_net):
    fake_net.slow = {"203.0.113.1"}  # IPv6 would answer, but is not allowed
    with pytest.raises(verify.ConnectTimeout):
        verify.connect_socket(("svc.run.app", 443), 0.01, ipv4=True)
    assert fake_net.connected == []


def test_a_connect_timeout_is_a_fail_line_naming_the_check_not_an_exception(
    fake_net, monkeypatch, env, capsys
):
    fake_net.slow = {"2001:db8::1", "203.0.113.1"}
    monkeypatch.setattr(verify, "run_process", FakeGcloud())
    code = verify.main([])
    out = capsys.readouterr().out
    assert code == 1
    assert "FAIL  orchestrator refuses an unauthenticated POST /ask: connect timeout" in out
    assert "FAIL  orchestrator answers a reporting question end to end: connect timeout" in out
    assert "FAIL  reporting refuses a caller that is not the orchestrator: connect timeout" in out
    assert "Traceback" not in out


def test_the_ipv4_flag_reaches_the_connection_through_main(fake_net, monkeypatch, env, capsys):
    """`--ipv4` -> Options -> http() -> the HTTPS handler: IPv4 times out, IPv6 would answer,
    and no IPv6 connect is attempted."""
    fake_net.slow = {"203.0.113.1"}
    monkeypatch.setattr(verify, "run_process", FakeGcloud())
    assert verify.main(["--ipv4"]) == 1
    out = capsys.readouterr().out
    assert "FAIL  orchestrator refuses an unauthenticated GET /: connect timeout" in out
    assert fake_net.connected == []


def test_a_read_timeout_is_not_called_a_connect_timeout(server, resolver):
    opts = verify.Options(read_timeout=0.3)
    assert verify.http("GET", f"http://svc.run.app:{server}/slow", opts=opts) == (None, {})


def test_the_default_timeouts():
    assert verify.CONNECT_TIMEOUT == 10 and verify.READ_TIMEOUT == 150
    assert verify.GCLOUD_TIMEOUT == 300
    opts = verify.Options()
    assert (opts.connect_timeout, opts.read_timeout, opts.gcloud_timeout) == (10, 150, 300)
    assert opts.ipv4 is False


# ------------------------------------------------------------------------------ gcloud timeout


def test_a_gcloud_timeout_is_a_fail_line_and_the_run_continues(monkeypatch, env, capsys):
    fake = FakeGcloud(
        fail=lambda a: (
            expired(a) if a[:4] == ("run", "services", "describe", "ops-orchestrator") else None
        )
    )
    monkeypatch.setattr(verify, "run_process", fake)
    monkeypatch.setattr(verify, "http", lambda *a, **k: (403, {}))
    code = verify.main(["--gcloud-timeout", "7"])
    out = capsys.readouterr().out
    assert code == 1
    assert (
        "FAIL  ops-orchestrator: serving revision is the one just deployed: gcloud timed out "
        "after 7 s: run services describe ops-orchestrator --region=us-central1" in out
    )
    # a check that does not need the failed call still ran and passed
    assert "PASS  cloud sql: authorizedNetworks is empty" in out
    assert "PASS  ops-qa: serving revision is the one just deployed" in out
    # and the failed call was not repeated by the checks that depend on it
    assert (
        fake.calls.count(
            (
                "run",
                "services",
                "describe",
                "ops-orchestrator",
                "--region=us-central1",
                "--format=json",
            )
        )
        == 1
    )


def test_gcloud_timeout_option_reaches_every_call(monkeypatch, env):
    fake = FakeGcloud()
    monkeypatch.setattr(verify, "run_process", fake)
    monkeypatch.setattr(verify, "http", lambda *a, **k: (403, {}))
    verify.main(["--gcloud-timeout", "42.5"])
    assert fake.calls and set(fake.timeouts) == {42.5}


def test_default_gcloud_timeout_is_300(monkeypatch, env):
    fake = FakeGcloud()
    monkeypatch.setattr(verify, "run_process", fake)
    monkeypatch.setattr(verify, "http", lambda *a, **k: (403, {}))
    verify.main([])
    assert set(fake.timeouts) == {300}


def test_a_gcloud_failure_exit_is_a_fail_line_with_its_first_error_line(monkeypatch, env, capsys):
    def fail(args):
        if args[:2] == ("sql", "instances"):
            return subprocess.CalledProcessError(1, ["gcloud"], stderr="ERROR: denied\nmore\n")

    monkeypatch.setattr(verify, "run_process", FakeGcloud(fail=fail))
    monkeypatch.setattr(verify, "http", lambda *a, **k: (403, {}))
    assert verify.main([]) == 1
    assert "FAIL  cloud sql: authorizedNetworks is empty: gcloud failed: ERROR: denied" in (
        capsys.readouterr().out
    )


def test_a_failed_token_mint_stays_its_own_fail_line(monkeypatch, env, capsys):
    """ADR-085: a failed mint is a FAIL line (not the generic one)."""

    def fail(args):
        if args[:2] == ("auth", "print-identity-token") and not any(
            a.startswith("--impersonate-service-account=probe") for a in args
        ):
            return subprocess.CalledProcessError(1, ["gcloud"], stderr="ERROR: no token\n")

    monkeypatch.setattr(verify, "run_process", FakeGcloud(fail=fail))
    monkeypatch.setattr(verify, "http", lambda *a, **k: (403, {}))
    verify.main([])
    assert (
        "FAIL  orchestrator answers a reporting question end to end: could not mint an "
        "identity token for the caller: ERROR: no token" in capsys.readouterr().out
    )


def test_run_process_kills_the_whole_tree_on_timeout(tmp_path):
    """On Windows gcloud.cmd starts a child that holds the pipes. A child that outlives its
    parent must not make the timeout wait for it."""
    marker = tmp_path / "grandchild.pid"
    script = (
        "import subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"open({str(marker)!r}, 'w').write(str(child.pid))\n"
        "time.sleep(60)\n"
    )
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        verify.run_process([sys.executable, "-c", script], timeout=2)
    assert time.monotonic() - started < 25
    pid = int(marker.read_text())
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and _alive(pid):
        time.sleep(0.2)
    assert not _alive(pid)


def _alive(pid: int) -> bool:
    if os.name == "nt":
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True
        ).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def test_run_process_returns_stripped_stdout_and_raises_on_a_nonzero_exit():
    assert verify.run_process([sys.executable, "-c", "print(' hi ')"], timeout=30) == "hi"
    with pytest.raises(subprocess.CalledProcessError) as caught:
        verify.run_process(
            [sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"], timeout=30
        )
    assert caught.value.returncode == 3 and caught.value.stderr == "boom"


# ------------------------------------------------------------------------------------ output


class RecordingStdout:
    """Records when a line is written and when it is flushed, in one event list."""

    def __init__(self, events: list):
        self.events = events
        self.pending: list[str] = []

    def write(self, text):
        if text.strip():
            self.pending.append(text.rstrip("\n"))
        return len(text)

    def flush(self):
        for line in self.pending:
            self.events.append(("flushed", line))
        self.pending.clear()

    def isatty(self):
        return False


def test_each_line_is_flushed_before_the_next_gcloud_call(monkeypatch, env):
    events: list = []
    monkeypatch.setattr(verify, "run_process", FakeGcloud(events))
    monkeypatch.setattr(verify, "http", lambda *a, **k: (403, {}))
    monkeypatch.setattr(sys, "stdout", RecordingStdout(events))
    verify.main([])

    def at(kind, needle):
        return next(i for i, (k, v) in enumerate(events) if k == kind and needle in v)

    first_describe = at("run", "run services describe ops-orchestrator")
    check_line = at("flushed", "ops-orchestrator: serving revision is the one just deployed")
    next_describe = at("run", "run services describe ops-reporting")
    assert first_describe < check_line < next_describe
    # and no line is ever written and left unflushed at the end
    assert not sys.stdout.pending


def test_every_gcloud_call_is_named_before_it_runs_and_its_output_is_never_printed(
    monkeypatch, env, capsys
):
    fake = FakeGcloud()
    monkeypatch.setattr(verify, "run_process", fake)
    monkeypatch.setattr(verify, "http", lambda *a, **k: (403, {}))
    verify.main([])
    out = capsys.readouterr().out
    assert TOKEN not in out and "owner@example.com" not in out
    infos = [line for line in out.splitlines() if line.startswith("INFO  gcloud ")]
    assert len(infos) == len(fake.calls)
    assert "INFO  gcloud run services describe ops-orchestrator --region=us-central1 " in out
    assert "(timeout 300 s)" in infos[0]


def test_the_closing_info_lines_and_exit_code_are_as_before(monkeypatch, env, capsys):
    monkeypatch.setattr(verify, "run_process", FakeGcloud())
    monkeypatch.setattr(verify, "http", lambda *a, **k: (403, {}))
    code = verify.main([])
    lines = capsys.readouterr().out.splitlines()
    assert lines[-2].startswith("INFO  /healthz without a token answers HTTP 403")
    assert lines[-1].startswith("INFO  not tested: that the project Owner's own token")
    assert code == 1  # the fake services have no invoker bindings


def test_missing_configuration_is_one_fail_line(monkeypatch, capsys):
    for name in ENV:
        monkeypatch.delenv(name, raising=False)
    assert verify.main([]) == 1
    assert capsys.readouterr().out.startswith("FAIL  configuration: unset PROJECT_ID")


def test_the_check_order_is_unchanged(monkeypatch, env, capsys):
    monkeypatch.setattr(verify, "run_process", FakeGcloud())
    monkeypatch.setattr(verify, "http", lambda *a, **k: (403, {}))
    verify.main([])
    names = [
        line.split("  ", 1)[1].split(":")[0]
        for line in capsys.readouterr().out.splitlines()
        if line.startswith(("PASS", "FAIL"))
    ]
    assert names[:11] == [
        "ops-orchestrator",
        "ops-reporting",
        "orchestrator refuses an unauthenticated POST /ask",
        "orchestrator refuses an unauthenticated GET /",
        "reporting refuses an unauthenticated GET /",
        "reporting refuses a caller that is not the orchestrator",
        "reporting",
        "ops-orchestrator",
        "ops-reporting",
        "orchestrator answers a reporting question end to end",
        "cloud sql",
    ]
    assert len(names) == 11 + 4 * len(verify.SIX)


def test_the_gcloud_call_pattern_is_the_one_before_s6_t1(monkeypatch, env):
    """19 calls on a clean run, as before: each call is minutes on the owner's PC."""
    from collections import Counter

    fake = FakeGcloud()
    monkeypatch.setattr(verify, "run_process", fake)
    monkeypatch.setattr(verify, "http", lambda *a, **k: (403, {}))
    verify.main([])
    describes = Counter(a[3] for a in fake.calls if a[:3] == ("run", "services", "describe"))
    policies = Counter(a[3] for a in fake.calls if a[:3] == ("run", "services", "get-iam-policy"))
    assert describes == {
        "ops-orchestrator": 2,
        "ops-reporting": 2,
        "ops-qa": 1,
        "ops-sentiment": 1,
        "ops-forecast": 1,
        "ops-gateway": 1,
    }
    assert policies == {
        "ops-reporting": 2,
        "ops-orchestrator": 1,
        "ops-qa": 1,
        "ops-sentiment": 1,
        "ops-forecast": 1,
        "ops-gateway": 1,
    }
    assert sum(a[:2] == ("auth", "print-identity-token") for a in fake.calls) == 2
    assert sum(a[:2] == ("config", "get-value") for a in fake.calls) == 1
    assert sum(a[:2] == ("sql", "instances") for a in fake.calls) == 1
    assert len(fake.calls) == 19


# ------------------------------------------------------------------------------- arguments


def test_arguments():
    ns = verify.parse_args([])
    assert ns.ipv4 is False and ns.gcloud_timeout == 300
    ns = verify.parse_args(["--ipv4", "--gcloud-timeout", "30"])
    assert ns.ipv4 is True and ns.gcloud_timeout == 30
    with pytest.raises(SystemExit):
        verify.parse_args(["--gcloud-timeout", "0"])
    with pytest.raises(SystemExit):
        verify.parse_args(["--connect-timeout", "5"])  # no such flag (spec)


# ------------------------------------------------------------------------- cloudbuild is unchanged

#: The verify step as it was before S6-T1: deploy/cloudbuild.yaml, unchanged since 05a0c34.
VERIFY_STEP_BEFORE = {
    "id": "verify",
    "name": "gcr.io/google.com/cloudsdktool/cloud-sdk:slim",
    "entrypoint": "bash",
    "env": [
        "PROJECT_ID=${PROJECT_ID}",
        "PROJECT_NUMBER=${PROJECT_NUMBER}",
        "REGION=${_REGION}",
        "EXPECTED_IMAGE_TAG=${COMMIT_SHA}",
        "ORCHESTRATOR_SA=${_ORCHESTRATOR_SA}",
        "REPORTING_SA=${_REPORTING_SA}",
        "PROBE_SA=${_PROBE_SA}",
        "CALLER_SA=${_BUILD_SA}",
        "CLOUD_SQL_INSTANCE_NAME=${_INSTANCE_NAME}",
    ],
    "args": [
        "-c",
        "set -euo pipefail\n"
        'if [ "${_RUN_VERIFY}" = "true" ]; then\n'
        "  python3 deploy/verify.py\n"
        "else\n"
        '  echo "verify skipped (_RUN_VERIFY=${_RUN_VERIFY}); run deploy/verify.py after the '
        'invoker bindings"\n'
        "fi\n",
    ],
    "waitFor": ["deploy-gateway"],
}


def test_the_pipelines_verify_step_is_unchanged():
    doc = yaml.safe_load((DEPLOY / "cloudbuild.yaml").read_text("utf-8"))
    step = next(s for s in doc["steps"] if s["id"] == "verify")
    assert step == VERIFY_STEP_BEFORE
    assert "--ipv4" not in " ".join(step["args"])
    assert "--gcloud-timeout" not in " ".join(step["args"])
