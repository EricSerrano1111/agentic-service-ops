"""Post-deploy checks for the reporting slice. Prints PASS or FAIL per check; exits 1 on any FAIL.

    python deploy/verify.py            # needs gcloud, signed in as the caller to test with

Configuration (environment): PROJECT_ID, PROJECT_NUMBER, REGION, EXPECTED_IMAGE_TAG (the
commit SHA just deployed), ORCHESTRATOR_SA, REPORTING_SA, PROBE_SA (a service account with no
project role and no invoker binding), CLOUD_SQL_INSTANCE_NAME. Optional: QUESTION.

The checks themselves are pure functions of gcloud's JSON, so they are unit-tested without a
project (tests/unit/test_deploy_config.py).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

ORCHESTRATOR = "ops-orchestrator"
REPORTING = "ops-reporting"
PUBLIC_PRINCIPALS = {"allUsers", "allAuthenticatedUsers"}
INVOKER_ROLE = "roles/run.invoker"
DEFAULT_QUESTION = "How many incidents were reported last month?"


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str = ""

    def line(self) -> str:
        return f"{'PASS' if self.ok else 'FAIL'}  {self.name}" + (
            f": {self.detail}" if self.detail else ""
        )


# ------------------------------------------------------------------------------- pure checks


def serving_revision(service: dict, expected_tag: str) -> Check:
    """The revision holding 100% of traffic is the latest ready one, built from this commit."""
    name = (
        f"{service.get('metadata', {}).get('name', '?')}: serving revision is the one just deployed"
    )
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


def unauthenticated_refused(statuses: dict[tuple[str, str, str], int | None]) -> list[Check]:
    """One check per probe: without a token the answer must be 401 or 403. Anything else (404,
    200, a 5xx, no answer) fails, since only an IAM refusal shows the boundary holds."""
    return [
        refused(
            f"{service} refuses an unauthenticated {method} {path}",
            statuses.get((service, method, path)),
        )
        for service, method, path in INGRESS_PROBES
    ]


def invokers(policy: dict, expected_member: str) -> Check:
    """Exactly one principal holds run.invoker, the expected one, and nothing is public."""
    name = "reporting: invoker is exactly the orchestrator's service account"
    bindings = policy.get("bindings", [])
    public = sorted({m for b in bindings for m in b.get("members", []) if m in PUBLIC_PRINCIPALS})
    if public:
        return Check(name, False, f"public principals bound: {public}")
    members = sorted({m for b in bindings if b.get("role") == INVOKER_ROLE for m in b["members"]})
    if members != [expected_member]:
        return Check(name, False, f"run.invoker members: {members}")
    return Check(name, True, expected_member)


def not_default_compute(service: dict, project_number: str, expected_sa: str) -> Check:
    name = f"{service.get('metadata', {}).get('name', '?')}: runs as its dedicated service account"
    sa = service["spec"]["template"]["spec"].get("serviceAccountName", "")
    if not sa or sa == f"{project_number}-compute@developer.gserviceaccount.com":
        return Check(name, False, f"runs as {sa or 'the default compute service account'}")
    if sa != expected_sa:
        return Check(name, False, f"runs as {sa}, expected {expected_sa}")
    return Check(name, True, sa)


def no_authorized_networks(instance: dict) -> Check:
    name = "cloud sql: authorizedNetworks is empty"
    nets = instance.get("settings", {}).get("ipConfiguration", {}).get("authorizedNetworks") or []
    return Check(name, not nets, f"{len(nets)} authorized network(s)" if nets else "")


def answered(status: int, body: dict) -> Check:
    name = "orchestrator answers a reporting question end to end"
    ok = status == 200 and body.get("outcome") == "answered" and body.get("reporting") is not None
    return Check(
        name, ok, f"HTTP {status}, outcome={body.get('outcome')}, error={body.get('error')}"
    )


# ------------------------------------------------------------------------------- plumbing


def gcloud(*args: str) -> str:
    return subprocess.run(
        ["gcloud", *args], check=True, capture_output=True, text=True, shell=sys.platform == "win32"
    ).stdout.strip()


METADATA_IDENTITY_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity"
)


def metadata_identity_token(audience: str) -> str | None:
    """An identity token for `audience` from the metadata server, or None when there is none.

    Inside Cloud Build the caller is the build service account, and `gcloud auth
    print-identity-token --audiences` cannot mint a token for credentials that come from the
    metadata server; the metadata server can. On a developer machine the host does not resolve,
    and the caller falls back to gcloud.
    """
    request = urllib.request.Request(
        f"{METADATA_IDENTITY_URL}?audience={urllib.parse.quote(audience, safe='')}&format=full",
        headers={"Metadata-Flavor": "Google"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310
            return response.read().decode().strip() or None
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def gcloud_json(*args: str) -> dict:
    return json.loads(gcloud(*args, "--format=json"))


def http(
    method: str, url: str, token: str | None = None, body: dict | None = None
) -> tuple[int | None, dict]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=150) as response:  # noqa: S310
            raw = response.read()
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read() or b"{}")
        except ValueError:
            return exc.code, {}
    except (urllib.error.URLError, TimeoutError):
        return None, {}


def main() -> int:
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
        print(f"FAIL  configuration: unset {', '.join(missing)}")
        return 1
    region = env["REGION"]
    tag = env["EXPECTED_IMAGE_TAG"]
    describe = lambda s: gcloud_json("run", "services", "describe", s, f"--region={region}")  # noqa: E731
    orchestrator, reporting = describe(ORCHESTRATOR), describe(REPORTING)
    orch_url, rep_url = orchestrator["status"]["url"], reporting["status"]["url"]

    def identity_token(*extra: str) -> str:
        return gcloud("auth", "print-identity-token", *extra)

    caller = gcloud("config", "get-value", "account")
    caller_args = [f"--audiences={orch_url}"] if caller.endswith("gserviceaccount.com") else []

    results = [
        serving_revision(orchestrator, tag),
        serving_revision(reporting, tag),
    ]
    urls = {"orchestrator": orch_url, "reporting": rep_url}
    probe_body = {"question": DEFAULT_QUESTION}  # refused by IAM before it reaches the app
    results += unauthenticated_refused(
        {
            (service, method, path): http(
                method, urls[service] + path, body=probe_body if method == "POST" else None
            )[0]
            for service, method, path in INGRESS_PROBES
        }
    )
    healthz = http("GET", f"{orch_url}/healthz")[0]
    probe_token = identity_token(
        f"--impersonate-service-account={env['PROBE_SA']}", f"--audiences={rep_url}"
    )
    results.append(
        refused(
            "reporting refuses a caller that is not the orchestrator",
            http("GET", f"{rep_url}/.well-known/agent-card.json", probe_token)[0],
        )
    )
    results += [
        invokers(
            gcloud_json("run", "services", "get-iam-policy", REPORTING, f"--region={region}"),
            f"serviceAccount:{env['ORCHESTRATOR_SA']}",
        ),
        not_default_compute(orchestrator, env["PROJECT_NUMBER"], env["ORCHESTRATOR_SA"]),
        not_default_compute(reporting, env["PROJECT_NUMBER"], env["REPORTING_SA"]),
    ]
    try:
        caller_token = metadata_identity_token(orch_url) or identity_token(*caller_args)
    except subprocess.CalledProcessError as exc:
        reason = (exc.stderr or "").strip().splitlines()[:1] or ["gcloud failed"]
        results.append(
            Check(
                "orchestrator answers a reporting question end to end",
                False,
                f"could not mint an identity token for the caller: {reason[0]}",
            )
        )
    else:
        status, body = http(
            "POST",
            f"{orch_url}/ask",
            caller_token,
            {"question": env.get("QUESTION", DEFAULT_QUESTION)},
        )
        results.append(answered(status or 0, body))
    results.append(
        no_authorized_networks(
            gcloud_json("sql", "instances", "describe", env["CLOUD_SQL_INSTANCE_NAME"])
        )
    )

    for r in results:
        print(r.line())
    print(
        f"INFO  /healthz without a token answers HTTP {healthz}: Cloud Run's front end reserves "
        "that path and answers before IAM, so it is not used as the unauthenticated probe."
    )
    print(
        "INFO  not tested: that the project Owner's own token is refused by reporting. Owner "
        "invokes any service through the basic role, so that check would fail by design; the "
        "negative test uses the no-role probe service account above."
    )
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
