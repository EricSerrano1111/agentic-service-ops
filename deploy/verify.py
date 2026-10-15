"""Post-deploy checks for the deployed system. Prints PASS or FAIL per check; exits 1 on any FAIL.

*Updated 2026-10-14 (Z2a, ADR-108): all six services are checked (ADR-099), not only the
orchestrator and reporting: the invoker policy of each, its dedicated service account, 100% of
traffic on the latest ready revision built from this commit (the tag is read at the service
template, not from a revision digest), and paid mode on exactly the five model-calling
containers (ADR-104). The end-to-end question stays one question.*

*Updated 2026-10-15 (S6-T1): window-day options for the owner's PC (`deploy/README.md`, "Window-day
options"). `--ipv4` opens every HTTP connection over IPv4 only. A connect timeout (10 s) applies to
every HTTP call and a timeout (300 s, `--gcloud-timeout`) to every `gcloud` call; either is a FAIL
line, not a hang or a traceback. Each check prints its line as it finishes. The checks, their order
and their pass conditions are unchanged.*

    python deploy/verify.py            # needs gcloud, signed in as the caller to test with
    python deploy/verify.py --ipv4 --gcloud-timeout 600     # the owner's PC (RUNBOOK_V.md)

Configuration (environment): PROJECT_ID, PROJECT_NUMBER, REGION, EXPECTED_IMAGE_TAG (the
commit SHA just deployed), ORCHESTRATOR_SA, REPORTING_SA, PROBE_SA (a service account with no
project role and no invoker binding), CLOUD_SQL_INSTANCE_NAME. Optional: QUESTION, and
CALLER_SA (the account check 6 impersonates for its token; unset on the owner's machine,
where the owner's own identity is used).

The checks themselves are pure functions of gcloud's JSON, so they are unit-tested without a
project (tests/unit/test_deploy_config.py, tests/unit/test_verify_window_day.py).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.client import HTTPConnection, HTTPSConnection

ORCHESTRATOR = "ops-orchestrator"
REPORTING = "ops-reporting"
PUBLIC_PRINCIPALS = {"allUsers", "allAuthenticatedUsers"}

#: Seconds. The connect timeout is per resolved address and covers the TCP connect and the TLS
#: handshake only; the read timeout stays long because the end-to-end question makes two model
#: calls. The `gcloud` timeout is per call.
CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 150.0
GCLOUD_TIMEOUT = 300.0

#: The six services (ADR-099): short name -> (dedicated account, who may invoke it). An invoker
#: is a short service-account name, or `allUsers` for the gateway, the only public service. The
#: orchestrator is also invoked by the build account (the pipeline's end-to-end check).
SIX = {
    "qa": ("run-qa", {"run-orchestrator"}),
    "sentiment": ("run-sentiment", {"run-orchestrator"}),
    "forecast": ("run-forecast", {"run-orchestrator"}),
    "reporting": ("run-reporting", {"run-orchestrator"}),
    "orchestrator": ("run-orchestrator", {"run-gateway", "build-deploy"}),
    "gateway": ("run-gateway", {"allUsers"}),
}
#: The containers that call the model, per service; every other container is not in paid mode.
MODEL_CALLING = {
    "qa": "agent-qa",
    "sentiment": "agent-sentiment",
    "forecast": "agent-forecast",
    "reporting": "agent-reporting",
    "orchestrator": "orchestrator",
}
INVOKER_ROLE = "roles/run.invoker"
DEFAULT_QUESTION = "How many incidents were reported last month?"

#: Check names. A step that cannot run (a timeout) prints its FAIL line under the same name the
#: pure check would have used, so these are built in one place.
SERVING_NAME = "{}: serving revision is the one just deployed"
INVOKERS_EXACT_NAME = "{}: invokers are exactly the expected set"
DEDICATED_NAME = "{}: runs as its dedicated service account"
PAID_NAME = "{}: paid mode on the model-calling container only"
INVOKERS_NAME = "reporting: invoker is exactly the orchestrator's service account"
NOT_ORCH_NAME = "reporting refuses a caller that is not the orchestrator"
ANSWER_NAME = "orchestrator answers a reporting question end to end"
SQL_NAME = "cloud sql: authorizedNetworks is empty"


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str = ""

    def line(self) -> str:
        return f"{'PASS' if self.ok else 'FAIL'}  {self.name}" + (
            f": {self.detail}" if self.detail else ""
        )


@dataclass(frozen=True)
class Options:
    ipv4: bool = False
    gcloud_timeout: float = GCLOUD_TIMEOUT
    connect_timeout: float = CONNECT_TIMEOUT
    read_timeout: float = READ_TIMEOUT


class ConnectTimeout(TimeoutError):
    """No address answered the connect (or the TLS handshake) in time."""


class GcloudTimeout(Exception):
    def __init__(self, call: str, seconds: float):
        super().__init__(f"{call} (after {seconds:g} s)")
        self.call = call
        self.seconds = seconds


# ------------------------------------------------------------------------------- pure checks


def serving_revision(service: dict, expected_tag: str) -> Check:
    """The revision holding 100% of traffic is the latest ready one, built from this commit."""
    name = SERVING_NAME.format(service.get("metadata", {}).get("name", "?"))
    status = service.get("status", {})
    traffic = status.get("traffic", [])
    ready = status.get("latestReadyRevisionName")
    full = [t for t in traffic if t.get("percent") == 100]
    if len(traffic) != 1 or len(full) != 1:
        return Check(name, False, f"traffic is split or empty: {traffic}")
    if not ready or full[0].get("revisionName") != ready:
        return Check(
            name, False, f"100% goes to {full[0].get('revisionName')}, latest ready is {ready}"
        )
    images = [c.get("image", "") for c in service["spec"]["template"]["spec"]["containers"]]
    stale = [i for i in images if not i.endswith(f":{expected_tag}")]
    if not expected_tag or stale:
        return Check(name, False, f"images not tagged {expected_tag!r}: {stale}")
    return Check(name, True, ready)


def refused(name: str, status: int | None) -> Check:
    return Check(name, status in (401, 403), f"HTTP {status}")


#: Unauthenticated requests that must be refused by IAM. Not `/healthz`: Cloud Run's front end
#: reserves that path and answers 404 before IAM sees the request, so it cannot show anything.
INGRESS_PROBES = (
    ("orchestrator", "POST", "/ask"),
    ("orchestrator", "GET", "/"),
    ("reporting", "GET", "/"),
)


def probe_name(service: str, method: str, path: str) -> str:
    return f"{service} refuses an unauthenticated {method} {path}"


def unauthenticated_refused(statuses: dict[tuple[str, str, str], int | None]) -> list[Check]:
    """One check per probe: without a token the answer must be 401 or 403. Anything else (404,
    200, a 5xx, no answer) fails, since only an IAM refusal shows the boundary holds."""
    return [
        refused(probe_name(service, method, path), statuses.get((service, method, path)))
        for service, method, path in INGRESS_PROBES
    ]


def invokers(policy: dict, expected_member: str) -> Check:
    """Exactly one principal holds run.invoker, the expected one, and nothing is public."""
    name = INVOKERS_NAME
    bindings = policy.get("bindings", [])
    public = sorted({m for b in bindings for m in b.get("members", []) if m in PUBLIC_PRINCIPALS})
    if public:
        return Check(name, False, f"public principals bound: {public}")
    members = sorted({m for b in bindings if b.get("role") == INVOKER_ROLE for m in b["members"]})
    if members != [expected_member]:
        return Check(name, False, f"run.invoker members: {members}")
    return Check(name, True, expected_member)


def invokers_exactly(service: str, policy: dict, allowed: set[str]) -> Check:
    """The members holding `run.invoker` are exactly `allowed` (full member strings, or
    `allUsers`); nothing else is bound, and no public principal unless `allUsers` is allowed."""
    name = INVOKERS_EXACT_NAME.format(service)
    bindings = policy.get("bindings", [])
    members = sorted({m for b in bindings if b.get("role") == INVOKER_ROLE for m in b["members"]})
    if members != sorted(allowed):
        return Check(name, False, f"run.invoker members: {members}, expected {sorted(allowed)}")
    others = sorted(
        {m for b in bindings for m in b.get("members", []) if m in PUBLIC_PRINCIPALS} - allowed
    )
    if others:
        return Check(name, False, f"public principals bound: {others}")
    return Check(name, True, ", ".join(members))


def paid_mode(service: dict, model_container: str | None) -> Check:
    """`LLM_MODE=paid` on the service's one model-calling container, and on no other container
    (an MCP sidecar, the gateway) of it (ADR-104). `model_container` None: no container is."""
    label = service.get("metadata", {}).get("name", "?")
    name = PAID_NAME.format(label)
    wrong = []
    for container in service["spec"]["template"]["spec"]["containers"]:
        env = {e.get("name"): e.get("value") for e in container.get("env", [])}
        is_paid = env.get("LLM_MODE") == "paid"
        should = container.get("name") == model_container
        if is_paid != should:
            wrong.append(f"{container.get('name')}: LLM_MODE={env.get('LLM_MODE')!r}")
    return Check(name, not wrong, "; ".join(wrong))


def not_default_compute(service: dict, project_number: str, expected_sa: str) -> Check:
    name = DEDICATED_NAME.format(service.get("metadata", {}).get("name", "?"))
    sa = service["spec"]["template"]["spec"].get("serviceAccountName", "")
    if not sa or sa == f"{project_number}-compute@developer.gserviceaccount.com":
        return Check(name, False, f"runs as {sa or 'the default compute service account'}")
    if sa != expected_sa:
        return Check(name, False, f"runs as {sa}, expected {expected_sa}")
    return Check(name, True, sa)


def no_authorized_networks(instance: dict) -> Check:
    name = SQL_NAME
    nets = instance.get("settings", {}).get("ipConfiguration", {}).get("authorizedNetworks") or []
    return Check(name, not nets, f"{len(nets)} authorized network(s)" if nets else "")


def answered(status: int, body: dict) -> Check:
    name = ANSWER_NAME
    ok = status == 200 and body.get("outcome") == "answered" and body.get("reporting") is not None
    return Check(
        name, ok, f"HTTP {status}, outcome={body.get('outcome')}, error={body.get('error')}"
    )


# ------------------------------------------------------------------------------- plumbing


def emit(line: str) -> None:
    """Every line goes out as it is written: a slow call must never hold earlier lines back."""
    print(line, flush=True)


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill the process and everything it started. On Windows `gcloud.cmd` runs under cmd.exe,
    which starts python.exe: killing only cmd.exe leaves the child holding the pipes."""
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, timeout=30
            )
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    with contextlib.suppress(OSError):
        proc.kill()


def run_process(argv: list[str], timeout: float) -> str:
    """Run `argv`, return its stripped stdout. Raises `CalledProcessError` on a non-zero exit and
    `subprocess.TimeoutExpired` after `timeout` seconds, having killed the whole process tree."""
    kwargs = {} if os.name == "nt" else {"start_new_session": True}
    proc = subprocess.Popen(
        argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **kwargs
    )
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.communicate(timeout=5)
        raise
    if proc.returncode:
        raise subprocess.CalledProcessError(proc.returncode, argv, output=out, stderr=err)
    return out.strip()


def gcloud(*args: str, timeout: float = GCLOUD_TIMEOUT) -> str:
    """One `gcloud` call: named on a line first, bounded by `timeout`. Its output is returned and
    never printed (it carries identity tokens and the account)."""
    emit(f"INFO  gcloud {' '.join(args)} (timeout {timeout:g} s)")
    # `shutil.which` finds gcloud.cmd on Windows, so no shell is needed (ADR-108).
    argv = [shutil.which("gcloud") or "gcloud", *args]
    try:
        return run_process(argv, timeout)
    except subprocess.TimeoutExpired:
        raise GcloudTimeout(" ".join(args), timeout) from None


def caller_token_args(env: dict, orch_url: str, account: str) -> list[str]:
    """`gcloud auth print-identity-token` arguments for the caller of check 6.

    In the pipeline, `CALLER_SA` (the build account) is set and the token is minted by
    impersonating it: inside Cloud Build neither the metadata server nor the build account's own
    credentials can issue an identity token. On the owner's machine `CALLER_SA` is unset and the
    owner's own gcloud identity is used (a service-account login needs an explicit audience).
    """
    if env.get("CALLER_SA"):
        return [f"--impersonate-service-account={env['CALLER_SA']}", f"--audiences={orch_url}"]
    return [f"--audiences={orch_url}"] if account.endswith("gserviceaccount.com") else []


def mint_failure(exc: subprocess.CalledProcessError) -> Check:
    """The FAIL line for check 6 when the caller's token cannot be minted."""
    reason = (exc.stderr or "").strip().splitlines()[:1] or ["gcloud failed"]
    return Check(
        ANSWER_NAME,
        False,
        f"could not mint an identity token for the caller: {reason[0]}",
    )


def gcloud_json(*args: str, timeout: float = GCLOUD_TIMEOUT) -> dict:
    return json.loads(gcloud(*args, "--format=json", timeout=timeout))


def connect_socket(
    address: tuple[str, int], connect_timeout: float, ipv4: bool = False
) -> socket.socket:
    """Open a TCP connection, trying each resolved address in turn for `connect_timeout` seconds.

    `ipv4` resolves for IPv4 only. The URL is never rewritten to an address, so TLS server name,
    certificate check and Host header are untouched. Raises `ConnectTimeout` when no address
    connected and at least one timed out, otherwise the last connection error.
    """
    host, port = address
    family = socket.AF_INET if ipv4 else socket.AF_UNSPEC
    infos = socket.getaddrinfo(host, port, family, socket.SOCK_STREAM)
    if ipv4:
        infos = [i for i in infos if i[0] == socket.AF_INET]
    if not infos:
        raise OSError(f"no {'IPv4 ' if ipv4 else ''}address for {host}")
    timed_out = False
    last: OSError | None = None
    for af, kind, proto, _, sockaddr in infos:
        sock = None
        try:
            sock = socket.socket(af, kind, proto)
            sock.settimeout(connect_timeout)
            sock.connect(sockaddr)
            return sock
        except TimeoutError as exc:
            timed_out = True
            last = exc
        except OSError as exc:
            last = exc
        if sock is not None:
            sock.close()
    if timed_out:
        raise ConnectTimeout(f"{host}:{port} did not accept a connection in {connect_timeout:g} s")
    assert last is not None
    raise last


def _connection_class(base: type, opts: Options) -> type:
    """`base` (HTTPConnection or HTTPSConnection) with the socket step replaced. The socket keeps
    the connect timeout through the TLS handshake, then takes the read timeout."""

    class Connection(base):  # type: ignore[misc, valid-type]
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._create_connection = lambda address, timeout=None, source_address=None: (
                connect_socket(address, opts.connect_timeout, opts.ipv4)
            )

        def connect(self):
            try:
                super().connect()
            except ConnectTimeout:
                raise
            except TimeoutError as exc:  # the TLS handshake
                raise ConnectTimeout(str(exc)) from exc
            self.sock.settimeout(self.timeout)

    return Connection


class _HTTP(urllib.request.HTTPHandler):
    def __init__(self, opts: Options):
        super().__init__()
        self._connection = _connection_class(HTTPConnection, opts)

    def http_open(self, req):
        return self.do_open(self._connection, req)


class _HTTPS(urllib.request.HTTPSHandler):
    def __init__(self, opts: Options):
        super().__init__()
        self._connection = _connection_class(HTTPSConnection, opts)

    def https_open(self, req):
        return self.do_open(self._connection, req, context=self._context)


def http(
    method: str,
    url: str,
    token: str | None = None,
    body: dict | None = None,
    opts: Options | None = None,
) -> tuple[int | None, dict]:
    """(status, body); status None when nothing answered. Raises `ConnectTimeout` when no address
    accepted the connection in time (the caller turns it into a FAIL line naming its check)."""
    opts = opts or Options()
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    opener = urllib.request.build_opener(_HTTP(opts), _HTTPS(opts))
    try:
        with opener.open(request, timeout=opts.read_timeout) as response:  # noqa: S310
            raw = response.read()
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read() or b"{}")
        except ValueError:
            return exc.code, {}
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, ConnectTimeout):
            raise exc.reason from None
        return None, {}
    except TimeoutError:  # a read timeout: it answered the connect, then went quiet
        return None, {}


class Gcloud:
    """The `gcloud` calls of one run. A call that failed is not repeated: a dependent check
    fails at once with the same reason instead of waiting out another timeout."""

    def __init__(self, timeout: float):
        self.timeout = timeout
        self._failed: dict[tuple[str, ...], Exception] = {}

    def _call(self, args: tuple[str, ...], fn):
        if args in self._failed:
            raise self._failed[args]
        try:
            return fn()
        except (GcloudTimeout, subprocess.CalledProcessError, FileNotFoundError) as exc:
            self._failed[args] = exc
            raise

    def text(self, *args: str) -> str:
        return self._call(args, lambda: gcloud(*args, timeout=self.timeout))

    def json(self, *args: str) -> dict:
        return self._call(args, lambda: gcloud_json(*args, timeout=self.timeout))


def failure_check(name: str, exc: Exception) -> Check:
    """The FAIL line for a check that could not run because a call failed."""
    if isinstance(exc, ConnectTimeout):
        return Check(name, False, "connect timeout")
    if isinstance(exc, GcloudTimeout):
        return Check(name, False, f"gcloud timed out after {exc.seconds:g} s: {exc.call}")
    if isinstance(exc, subprocess.CalledProcessError):
        reason = (exc.stderr or "").strip().splitlines()[:1] or [f"exit {exc.returncode}"]
        return Check(name, False, f"gcloud failed: {reason[0]}")
    return Check(name, False, "gcloud was not found on PATH")


FAILURES = (ConnectTimeout, GcloudTimeout, subprocess.CalledProcessError, FileNotFoundError)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="verify.py", description="Post-deploy checks for the deployed system."
    )
    parser.add_argument(
        "--ipv4",
        action="store_true",
        help="open every HTTP connection over IPv4 only (IPv6 to *.run.app can black-hole)",
    )
    parser.add_argument(
        "--gcloud-timeout",
        type=float,
        default=GCLOUD_TIMEOUT,
        metavar="SECONDS",
        help=f"timeout for each gcloud call (default {GCLOUD_TIMEOUT:g})",
    )
    args = parser.parse_args(argv)
    if args.gcloud_timeout <= 0:
        parser.error("--gcloud-timeout must be greater than 0")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    opts = Options(ipv4=args.ipv4, gcloud_timeout=args.gcloud_timeout)
    env = os.environ
    need = [
        "PROJECT_ID",
        "PROJECT_NUMBER",
        "REGION",
        "EXPECTED_IMAGE_TAG",
        "ORCHESTRATOR_SA",
        "REPORTING_SA",
        "PROBE_SA",
        "CLOUD_SQL_INSTANCE_NAME",
    ]
    missing = [n for n in need if not env.get(n)]
    if missing:
        emit(f"FAIL  configuration: unset {', '.join(missing)}")
        return 1
    region = env["REGION"]
    tag = env["EXPECTED_IMAGE_TAG"]
    domain = f"{env['PROJECT_ID']}.iam.gserviceaccount.com"
    gc = Gcloud(opts.gcloud_timeout)
    results: list[Check] = []

    def describe(service: str) -> dict:
        return gc.json("run", "services", "describe", service, f"--region={region}")

    def policy(service: str) -> dict:
        return gc.json("run", "services", "get-iam-policy", service, f"--region={region}")

    def url(service: str) -> str:
        return describe(service)["status"]["url"]

    def identity_token(*extra: str) -> str:
        return gc.text("auth", "print-identity-token", *extra)

    def request(*a, **kw) -> tuple[int | None, dict]:
        return http(*a, opts=opts, **kw)

    def step(name: str, fn) -> None:
        """Run one check and print its line now. A failed call is this check's FAIL line."""
        try:
            check = fn()
        except FAILURES as exc:
            check = failure_check(name, exc)
        results.append(check)
        emit(check.line())

    step(SERVING_NAME.format(ORCHESTRATOR), lambda: serving_revision(describe(ORCHESTRATOR), tag))
    step(SERVING_NAME.format(REPORTING), lambda: serving_revision(describe(REPORTING), tag))

    probe_body = {"question": DEFAULT_QUESTION}  # refused by IAM before it reaches the app
    service_url = {"orchestrator": lambda: url(ORCHESTRATOR), "reporting": lambda: url(REPORTING)}
    for service, method, path in INGRESS_PROBES:
        step(
            probe_name(service, method, path),
            lambda service=service, method=method, path=path: refused(
                probe_name(service, method, path),
                request(
                    method,
                    service_url[service]() + path,
                    body=probe_body if method == "POST" else None,
                )[0],
            ),
        )
    try:
        healthz = request("GET", f"{url(ORCHESTRATOR)}/healthz")[0]
    except FAILURES:
        healthz = None  # reported by the checks above; this is an INFO line only

    def probe_refused() -> Check:
        probe_token = identity_token(
            f"--impersonate-service-account={env['PROBE_SA']}", f"--audiences={url(REPORTING)}"
        )
        return refused(
            NOT_ORCH_NAME,
            request("GET", f"{url(REPORTING)}/.well-known/agent-card.json", probe_token)[0],
        )

    step(NOT_ORCH_NAME, probe_refused)
    step(
        INVOKERS_NAME,
        lambda: invokers(policy(REPORTING), f"serviceAccount:{env['ORCHESTRATOR_SA']}"),
    )
    step(
        DEDICATED_NAME.format(ORCHESTRATOR),
        lambda: not_default_compute(
            describe(ORCHESTRATOR), env["PROJECT_NUMBER"], env["ORCHESTRATOR_SA"]
        ),
    )
    step(
        DEDICATED_NAME.format(REPORTING),
        lambda: not_default_compute(
            describe(REPORTING), env["PROJECT_NUMBER"], env["REPORTING_SA"]
        ),
    )

    def end_to_end() -> Check:
        orch_url = url(ORCHESTRATOR)
        caller = gc.text("config", "get-value", "account")
        try:
            caller_token = identity_token(*caller_token_args(env, orch_url, caller))
        except subprocess.CalledProcessError as exc:
            return mint_failure(exc)
        status, body = request(
            "POST",
            f"{orch_url}/ask",
            caller_token,
            {"question": env.get("QUESTION", DEFAULT_QUESTION)},
        )
        return answered(status or 0, body)

    step(ANSWER_NAME, end_to_end)
    step(
        SQL_NAME,
        lambda: no_authorized_networks(
            gc.json("sql", "instances", "describe", env["CLOUD_SQL_INSTANCE_NAME"])
        ),
    )

    # All six services (ADR-099, ADR-104): the invoker policy, the dedicated account, the serving
    # revision and the mode. Orchestrator and reporting are repeated here by name, so the list
    # is complete in one place.
    for name, (account, allowed) in SIX.items():
        service = f"ops-{name}"
        full = {a if a == "allUsers" else f"serviceAccount:{a}@{domain}" for a in allowed}
        step(SERVING_NAME.format(service), lambda s=service: serving_revision(describe(s), tag))
        step(
            INVOKERS_EXACT_NAME.format(service),
            lambda s=service, f=full: invokers_exactly(s, policy(s), f),
        )
        step(
            DEDICATED_NAME.format(service),
            lambda s=service, a=account: not_default_compute(
                describe(s), env["PROJECT_NUMBER"], f"{a}@{domain}"
            ),
        )
        step(
            PAID_NAME.format(service),
            lambda s=service, n=name: paid_mode(describe(s), MODEL_CALLING.get(n)),
        )

    emit(
        f"INFO  /healthz without a token answers HTTP {healthz}: Cloud Run's front end reserves "
        "that path and answers before IAM, so it is not used as the unauthenticated probe."
    )
    emit(
        "INFO  not tested: that the project Owner's own token is refused by reporting. Owner "
        "invokes any service through the basic role, so that check would fail by design; the "
        "negative test uses the no-role probe service account above."
    )
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
