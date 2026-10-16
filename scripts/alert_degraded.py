"""The `outcome=degraded` alert as code (ADR-112): a log-based metric, an alert policy, a test.

*Added 2026-10-16 (S6-A1, Part A). Nothing here has been run against GCP: Part B does that with
the owner present.*

    python scripts/alert_degraded.py plan              # the default: prints every command and body
    python scripts/alert_degraded.py apply --channel ID
    python scripts/alert_degraded.py test

`plan` makes no call at all (no process, no network). `apply` creates the metric and the policy, or
updates them, then reads both back and prints a diff against the files. `test` writes one
synthetic entry with `gcloud logging write` (it can set the monitored resource, ADR-112) and polls
the metric and the policy for an open incident every 30 s for up to 15 minutes.

Configuration comes from the environment `deploy/verify.py` reads: PROJECT_ID and REGION. The
service name is verify.py's `ORCHESTRATOR`. The notification channel is passed by ID at apply time
and written only to a temporary file; neither an address nor an ID is in the repo.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MONITORING = REPO / "ops" / "monitoring"
METRIC_FILE = MONITORING / "degraded_metric.json"
POLICY_FILE = MONITORING / "degraded_policy.json"

METRIC = "orchestrator_degraded_answers"
METRIC_TYPE = f"logging.googleapis.com/user/{METRIC}"
TEST_LOG = "degraded-alert-test"
TRACE_PREFIX = "alerttest-"
POLL_EVERY_S = 30.0
POLL_FOR_S = 15 * 60.0
HTTP_TIMEOUT_S = 30.0
#: `gcloud` is `gcloud.cmd` on Windows and the JSON payload travels on its command line, so a
#: character `cmd.exe` treats as an operator would corrupt it (ADR-112).
CMD_METACHARACTERS = set("&|<>^%")
MONITORING_API = "https://monitoring.googleapis.com/v3"


def _load_verify():
    spec = importlib.util.spec_from_file_location("deploy_verify", REPO / "deploy" / "verify.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


verify = _load_verify()
SERVICE = verify.ORCHESTRATOR
emit = verify.emit


# --------------------------------------------------------------------------- the filter


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


_TERM = re.compile(r'^\s*([\w.]+)\s*=\s*"((?:[^"\\]|\\.)*)"\s*$')


def filter_conditions(log_filter: str) -> list[tuple[str, str]]:
    """The `field="value"` terms of a filter written as terms joined by AND. Anything else (OR, a
    comparison, a function) raises, so the metric file cannot grow past what the tests can check."""
    terms = []
    for part in re.split(r"\s+AND\s+", log_filter.strip()):
        match = _TERM.match(part)
        if not match:
            raise ValueError(f'not a field="value" term: {part!r}')
        terms.append((match.group(1), match.group(2).replace('\\"', '"')))
    return terms


def _lookup(entry: dict, dotted: str):
    node = entry
    for key in dotted.split("."):
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def entry_matches(entry: dict, conditions: list[tuple[str, str]]) -> bool:
    """Whether a log entry (`resource`, `jsonPayload`) satisfies every term."""
    return all(_lookup(entry, field) == value for field, value in conditions)


def metric_conditions() -> list[tuple[str, str]]:
    return filter_conditions(load(METRIC_FILE)["filter"])


# --------------------------------------------------------------------------- the synthetic entry


def synthetic_entry(project: str, region: str, trace_id: str | None = None) -> dict:
    """The log entry the test writes: the real degraded line's shape, flat, plus the marker."""
    trace_id = trace_id or f"{TRACE_PREFIX}{uuid.uuid4().hex[:16]}"
    return {
        "resource": {
            "type": "cloud_run_revision",
            "labels": {
                "project_id": project,
                "service_name": SERVICE,
                "revision_name": f"{SERVICE}-alerttest",
                "location": region,
                "configuration_name": SERVICE,
            },
        },
        "jsonPayload": {
            "msg": "ask degraded",
            "service": "orchestrator",
            "trigger": "dependency",
            "capability": "routing",
            "trace_id": trace_id,
            "synthetic_alert_test": True,
        },
    }


def write_argv(entry: dict, project: str) -> list[str]:
    payload = json.dumps(entry["jsonPayload"], separators=(",", ":"))
    bad = CMD_METACHARACTERS & set(payload)
    if bad:
        raise ValueError(f"payload holds cmd.exe metacharacters {sorted(bad)}")
    labels = ",".join(f"{k}={v}" for k, v in entry["resource"]["labels"].items())
    return [
        "logging",
        "write",
        TEST_LOG,
        payload,
        "--payload-type=json",
        "--severity=WARNING",
        f"--monitored-resource-type={entry['resource']['type']}",
        f"--monitored-resource-labels={labels}",
        f"--project={project}",
    ]


# --------------------------------------------------------------------------- the policy


def channel_name(project: str, channel_id: str) -> str:
    """`ID` or a full `projects/P/notificationChannels/ID`; either gives the full name."""
    if channel_id.startswith("projects/"):
        return channel_id
    return f"projects/{project}/notificationChannels/{channel_id}"


def policy_body(channel: str) -> dict:
    body = load(POLICY_FILE)
    body["notificationChannels"] = [channel]
    return body


def subset_diff(expected, actual, path: str = "") -> list[str]:
    """Differences where `actual` lacks or changes something `expected` states. Extra fields in
    `actual` (the server adds names, ids and defaults) are not differences."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path or '.'}: expected an object, got {actual!r}"]
        out: list[str] = []
        for key, value in expected.items():
            where = f"{path}.{key}" if path else key
            if key not in actual:
                # The API leaves proto3 defaults out of its JSON (a threshold of 0, `false`).
                if value is not False and not (isinstance(value, int | float) and value == 0):
                    out.append(f"{where}: missing")
            else:
                out += subset_diff(value, actual[key], where)
        return out
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            return [f"{path}: expected {expected!r}, got {actual!r}"]
        out = []
        for i, (e, a) in enumerate(zip(expected, actual, strict=True)):
            out += subset_diff(e, a, f"{path}[{i}]")
        return out
    # The API returns numbers as numbers and durations as strings; compare as written.
    return [] if expected == actual else [f"{path}: expected {expected!r}, got {actual!r}"]


# --------------------------------------------------------------------------- running gcloud


class Config:
    def __init__(self, env: dict | None = None) -> None:
        env = os.environ if env is None else env
        self.project = env.get("PROJECT_ID", "")
        self.region = env.get("REGION", "")

    def missing(self) -> list[str]:
        return [n for n, v in (("PROJECT_ID", self.project), ("REGION", self.region)) if not v]


class Gcloud:
    """`gcloud` calls, each named on a line first and bounded by a timeout that kills the process
    tree (verify.run_process). Output is returned and never printed: some of it carries tokens."""

    def __init__(self, timeout: float, run: Callable = verify.run_process) -> None:
        self.timeout = timeout
        self._run = run

    def __call__(self, *args: str, label: str | None = None) -> str:
        shown = label if label is not None else " ".join(args)
        emit(f"INFO  gcloud {shown} (timeout {self.timeout:g} s)")
        argv = [shutil.which("gcloud") or "gcloud", *args]
        try:
            return self._run(argv, self.timeout)
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"gcloud timed out after {self.timeout:g} s") from None
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"gcloud failed ({exc.returncode}): {(exc.stderr or '').strip()}"
            ) from None

    def json(self, *args: str, label: str | None = None):
        return json.loads(self(*args, "--format=json", label=label) or "null")


def access_token(gc: Gcloud) -> str:
    # The token is returned to the caller and is never printed or put in a message.
    argv = [shutil.which("gcloud") or "gcloud", "auth", "print-access-token"]
    emit(f"INFO  gcloud auth print-access-token (timeout {gc.timeout:g} s; output not shown)")
    try:
        return gc._run(argv, gc.timeout).strip()
    except (subprocess.SubprocessError, OSError):
        raise RuntimeError("could not get an access token from gcloud") from None


class ApiHttpError(RuntimeError):
    def __init__(self, path: str, code: int) -> None:
        super().__init__(f"GET {path} gave HTTP {code}")
        self.code = code


#: The alerts endpoint answering 403 or 404 means this account or API surface cannot list
#: incidents; that stage is then unverified (check the console), not failed.
UNVERIFIABLE_CODES = (403, 404)
READBACK_TRIES = 6
READBACK_EVERY_S = 5.0


def readback_argv(entry: dict, project: str) -> list[str]:
    """Read the synthetic entry back by its trace id (bounded: one entry, ten minutes)."""
    trace_id = entry["jsonPayload"]["trace_id"]
    return [
        "logging",
        "read",
        f'resource.type=cloud_run_revision AND jsonPayload.trace_id="{trace_id}"',
        f"--project={project}",
        "--freshness=10m",
        "--limit=1",
    ]


def readback(
    gc: Gcloud, entry: dict, project: str, sleep: Callable[[float], None] = time.sleep
) -> list[str] | None:
    """Differences between what was written and what is stored, or None if it never appears."""
    argv = readback_argv(entry, project)
    for attempt in range(READBACK_TRIES):
        found = gc.json(*argv, label="logging read <trace_id filter> (synthetic entry)")
        if found:
            stored = found[0]
            diff = subset_diff(entry["jsonPayload"], stored.get("jsonPayload", {}), "jsonPayload")
            labels = stored.get("resource", {}).get("labels", {})
            diff += subset_diff(entry["resource"]["labels"], labels, "resource.labels")
            if stored.get("resource", {}).get("type") != entry["resource"]["type"]:
                diff.append("resource.type: differs")
            return diff
        if attempt + 1 < READBACK_TRIES:
            sleep(READBACK_EVERY_S)
    return None


def api_get(token: str, path: str, params: dict[str, str]) -> dict:
    url = f"{MONITORING_API}/{path}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ApiHttpError(path, exc.code) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"GET {path} failed: {type(exc).__name__}") from None


# --------------------------------------------------------------------------- plan


def plan_lines(cfg: Config, channel_id: str | None = None) -> list[str]:
    project = cfg.project or "<PROJECT_ID>"
    region = cfg.region or "<REGION>"
    channel = channel_name(project, channel_id or "<CHANNEL_ID>")
    metric_file = "ops/monitoring/degraded_metric.json"
    entry = synthetic_entry(project, region, f"{TRACE_PREFIX}0123456789abcdef")
    out = [
        f"project {project}, region {region}, service {SERVICE}",
        "",
        "== apply --channel <CHANNEL_ID> ==",
        f"gcloud beta monitoring channels describe {channel} --project={project} --format=json"
        "   (read; must be type=email and enabled; the address is not printed)",
        f"gcloud logging metrics list --project={project} --filter=name={METRIC} "
        "--format=json   (read)",
        f"gcloud logging metrics create {METRIC} --config-from-file={metric_file} "
        f"--project={project}   (or `update` when it exists)",
        f"gcloud alpha monitoring policies list --project={project} "
        f'--filter=displayName="{load(POLICY_FILE)["displayName"]}" --format=json   (read)',
        "gcloud alpha monitoring policies create --policy-from-file=<temp copy of "
        f"degraded_policy.json with notificationChannels set> --project={project}"
        "   (or `update <NAME>` when it exists)",
        "then read both back (metrics list, policies list) and print a diff against the files",
        "",
        "-- metric file (ops/monitoring/degraded_metric.json) --",
        json.dumps(load(METRIC_FILE), indent=2),
        "",
        "-- policy body as sent (channel filled at apply time) --",
        json.dumps(policy_body(channel), indent=2),
        "",
        "== test ==",
        "gcloud " + " ".join(_shown(a) for a in write_argv(entry, project)),
        "gcloud " + " ".join(_shown(a) for a in readback_argv(entry, project)) + " --format=json",
        f"  (read back by trace_id, up to {READBACK_TRIES} tries {READBACK_EVERY_S:g} s apart; "
        "stop if not found or any field differs)",
        "then every 30 s for up to 15 min:",
        "  gcloud auth print-access-token   (token never printed)",
        f"  GET {MONITORING_API}/projects/{project}/timeSeries"
        f'?filter=metric.type="{METRIC_TYPE}"'
        "&interval.startTime=<test start>&interval.endTime=<now>"
        "   -> stage 1: the metric counts 1 or more",
        f"  GET {MONITORING_API}/projects/{project}/alerts"
        '?filter=policy.name="<policy name>"   -> stage 2: an incident for the policy is OPEN',
        "then print the entry's timestamp and trace id, and which stage (if any) did not fire.",
        "(a 403 or 404 from the alerts endpoint is reported as: incident stage unverified,",
        " check the console; it is not a failure)",
        "",
        "-- the synthetic entry (the trace id suffix is random at run time) --",
        json.dumps(entry, indent=2),
    ]
    return out


def _shown(arg: str) -> str:
    return f"'{arg}'" if any(c in arg for c in ' {}"') else arg


# --------------------------------------------------------------------------- apply


def apply(cfg: Config, gc: Gcloud, channel_id: str) -> int:
    project = cfg.project
    channel = channel_name(project, channel_id)
    info = gc.json("beta", "monitoring", "channels", "describe", channel, f"--project={project}")
    if info.get("type") != "email" or str(info.get("enabled", "true")).lower() == "false":
        emit(f"FAIL  channel is type={info.get('type')!r}, not an enabled email channel")
        return 1
    emit("PASS  channel is an enabled email channel")

    metrics = gc.json(
        "logging", "metrics", "list", f"--project={project}", f"--filter=name={METRIC}"
    )
    verb = "update" if metrics else "create"
    gc(
        "logging",
        "metrics",
        verb,
        METRIC,
        f"--config-from-file={METRIC_FILE}",
        f"--project={project}",
    )

    display = load(POLICY_FILE)["displayName"]
    list_args = (
        "alpha", "monitoring", "policies", "list", f"--project={project}",
        f'--filter=displayName="{display}"',
    )  # fmt: skip
    existing = gc.json(*list_args)
    if len(existing) > 1:
        emit(f"FAIL  {len(existing)} policies are named {display!r}; remove the extras first")
        return 1
    with tempfile.TemporaryDirectory(prefix="alert-policy-") as folder:
        path = Path(folder) / "policy.json"
        path.write_text(json.dumps(policy_body(channel)), encoding="utf-8")
        if existing:
            gc("alpha", "monitoring", "policies", "update", existing[0]["name"],
               f"--policy-from-file={path}", f"--project={project}")  # fmt: skip
        else:
            gc("alpha", "monitoring", "policies", "create",
               f"--policy-from-file={path}", f"--project={project}")  # fmt: skip

    bad = 0
    got = gc.json("logging", "metrics", "list", f"--project={project}", f"--filter=name={METRIC}")
    metric_diff = subset_diff(load(METRIC_FILE), got[0] if got else {})
    got_policy = gc.json(*list_args)
    policy_diff = subset_diff(policy_body(channel), got_policy[0] if got_policy else {})
    for name, diff in (("metric", metric_diff), ("policy", policy_diff)):
        if diff:
            bad += 1
            emit(f"FAIL  {name} read back differs from its file:")
            for line in diff:
                emit(f"        {line}")
        else:
            emit(f"PASS  {name} read back matches its file")
    return 1 if bad else 0


# --------------------------------------------------------------------------- test


def metric_count(series: dict) -> int:
    return sum(
        int(point["value"].get("int64Value", 0))
        for ts in series.get("timeSeries", [])
        for point in ts.get("points", [])
    )


def incident_open(alerts: dict) -> bool:
    return any(a.get("state") == "OPEN" for a in alerts.get("alerts", []))


def rfc3339(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def run_test(
    cfg: Config,
    gc: Gcloud,
    *,
    get: Callable[[str, str, dict], dict] = api_get,
    now: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
    poll_every: float = POLL_EVERY_S,
    poll_for: float = POLL_FOR_S,
) -> int:
    project = cfg.project
    entry = synthetic_entry(project, cfg.region)
    trace_id = entry["jsonPayload"]["trace_id"]
    started = now()
    gc(*write_argv(entry, project), label=f"logging write {TEST_LOG} <payload> (synthetic entry)")
    emit(f"INFO  wrote the synthetic entry at {rfc3339(started)}, trace_id {trace_id}")
    emit("INFO  record both in docs/deploy-window-log.md")

    diff = readback(gc, entry, project, sleep)
    if diff is None:
        emit("FAIL  the synthetic entry was not found on read-back; not waiting for the alert")
        return 1
    if diff:
        emit("FAIL  the stored entry differs from what was written; not waiting for the alert:")
        for line in diff:
            emit(f"        {line}")
        return 1
    emit("PASS  the synthetic entry reads back with every field as written")

    display = load(POLICY_FILE)["displayName"]
    policies = gc.json(
        "alpha", "monitoring", "policies", "list", f"--project={project}",
        f'--filter=displayName="{display}"',
    )  # fmt: skip
    if len(policies) != 1:
        emit(f"FAIL  expected one policy named {display!r}, found {len(policies)}")
        return 1
    policy_name = policies[0]["name"]

    metric_seen = incident_seen = incident_unverified = False
    deadline = started + poll_for
    while True:
        token = access_token(gc)
        series = get(
            token,
            f"projects/{project}/timeSeries",
            {
                "filter": f'metric.type="{METRIC_TYPE}"',
                "interval.startTime": rfc3339(started - 60),
                "interval.endTime": rfc3339(now() + 60),
            },
        )
        count = metric_count(series)
        metric_seen = metric_seen or count >= 1
        is_open = False
        if not incident_unverified:
            try:
                alerts = get(
                    token, f"projects/{project}/alerts", {"filter": f'policy.name="{policy_name}"'}
                )
            except ApiHttpError as exc:
                if exc.code not in UNVERIFIABLE_CODES:
                    raise
                incident_unverified = True
                emit(
                    f"WARN  incident stage: unverified (alerts endpoint gave HTTP {exc.code}); "
                    "check the console"
                )
            else:
                is_open = incident_open(alerts)
                incident_seen = incident_seen or is_open
        emit(f"INFO  metric count {count}, incident open: {is_open}")
        if metric_seen and incident_seen:
            emit("PASS  the metric counted the entry and the policy opened an incident")
            emit("INFO  check the owner's inbox for the notification; this does not prove it")
            return 0
        if metric_seen and incident_unverified:
            emit("PASS  the metric counted the entry")
            emit("UNVERIFIED  incident stage: open the console, Alerting, Incidents, and look")
            emit("INFO  check the owner's inbox for the notification; this does not prove it")
            return 0
        if now() >= deadline:
            break
        sleep(poll_every)
    stage = "the metric never counted the entry" if not metric_seen else "no incident opened"
    emit(f"FAIL  after {poll_for / 60:g} min: {stage}")
    emit(f"INFO  entry timestamp {rfc3339(started)}, trace_id {trace_id}")
    return 1


# --------------------------------------------------------------------------- main


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--gcloud-timeout", type=float, default=verify.GCLOUD_TIMEOUT)
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("plan", help="print every command and body; make no call (the default)")
    apply_parser = sub.add_parser("apply", help="create or update the metric and the policy")
    apply_parser.add_argument("--channel", required=True, help="notification channel ID")
    sub.add_parser("test", help="write one synthetic entry and wait for the metric and incident")
    args = parser.parse_args(argv)
    args.command = args.command or "plan"
    return args


def main(argv: list[str] | None = None, *, env: dict | None = None) -> int:
    args = parse_args(argv)
    cfg = Config(env)
    if args.command == "plan":
        for line in plan_lines(cfg):
            emit(line)
        if cfg.missing():
            emit(f"\nNOTE  unset: {', '.join(cfg.missing())} (placeholders shown)")
        return 0
    if cfg.missing():
        emit(f"FAIL  configuration: unset {', '.join(cfg.missing())}")
        return 1
    gc = Gcloud(args.gcloud_timeout)
    try:
        if args.command == "apply":
            return apply(cfg, gc, args.channel)
        return run_test(cfg, gc)
    except RuntimeError as exc:
        emit(f"FAIL  {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
