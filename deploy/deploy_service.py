"""Create or update one Cloud Run service from a rendered v2 JSON definition.

gcloud's `services replace` reads only the Knative v1 format, which cannot mount Cloud SQL
into a single container (see README, "Cloud SQL mount"). The v2 Admin API can, so this calls
it directly, authenticated with the caller's gcloud credentials:

    python deploy/deploy_service.py rendered/reporting.json

The definition's own `name` (projects/P/locations/R/services/S) says which service it is.
Waits for the long-running operation and exits non-zero if it fails. Not run in this repo's
tests: it needs a project.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

API = "https://run.googleapis.com/v2"
POLL_S = 5
TIMEOUT_S = 900


def access_token() -> str:
    return subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        check=True,
        capture_output=True,
        text=True,
        shell=sys.platform == "win32",
    ).stdout.strip()


def call(method: str, url: str, token: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def create_body(service: dict) -> dict:
    """The body for a create call. The v2 API rejects a `name` in it ("service.name must be
    empty on CreateServiceRequest"); the name is given as `serviceId` in the URL instead."""
    return {k: v for k, v in service.items() if k != "name"}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: deploy_service.py RENDERED.json", file=sys.stderr)
        return 2
    with open(argv[1], encoding="utf-8") as f:
        service = json.load(f)
    name = service["name"]  # projects/P/locations/R/services/S
    parent, _, service_id = name.rpartition("/services/")
    token = access_token()

    status, _ = call("GET", f"{API}/{name}", token)
    if status == 404:
        status, operation = call(
            "POST", f"{API}/{parent}/services?serviceId={service_id}", token, create_body(service)
        )
        action = "create"
    elif status == 200:
        # No updateMask: the whole definition replaces the service's template.
        status, operation = call("PATCH", f"{API}/{name}", token, service)
        action = "update"
    else:
        print(f"cannot read {name}: HTTP {status}", file=sys.stderr)
        return 1
    if status != 200:
        print(
            f"{action} {service_id} failed: HTTP {status}: {operation.get('error')}",
            file=sys.stderr,
        )
        return 1

    deadline = time.monotonic() + TIMEOUT_S
    while not operation.get("done"):
        if time.monotonic() > deadline:
            print(
                f"{action} {service_id}: timed out waiting for {operation['name']}", file=sys.stderr
            )
            return 1
        time.sleep(POLL_S)
        _, operation = call("GET", f"{API}/{operation['name']}", token)
    if "error" in operation:
        print(f"{action} {service_id} failed: {operation['error']}", file=sys.stderr)
        return 1
    print(f"{action} {service_id}: done")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
