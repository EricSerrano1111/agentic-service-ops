"""Invite administration for the gateway (ADR-097).

    .venv/Scripts/python scripts/invites.py create --label "grader" --days 14
    .venv/Scripts/python scripts/invites.py list
    .venv/Scripts/python scripts/invites.py revoke --id <id>

The store file is `--file`, else `$GATEWAY_INVITES_FILE`, else `.local/gateway/invites.json`
(gitignored). `create` prints the link once: the token is not stored, only its SHA-256, and it
cannot be shown again. `list` never shows a hash.

On Cloud Run the same document is a Secret Manager secret. `--secret projects/<number>/secrets/
gateway-invites` (or `$GATEWAY_INVITES_SECRET` when no `--file` is given) makes every command read
the secret's `latest` version and `create` / `revoke` add a new version. It runs with the
owner's own `gcloud` credentials (`gcloud auth print-access-token`), never the gateway's; a
revoke takes effect within the gateway's 60-second cache. `--secret` and `--file` together are
refused.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import subprocess
import sys
import urllib.request
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api_gateway" / "src"))

from api_gateway.invites import (  # noqa: E402
    FileInviteStore,
    Invite,
    dump_document,
    new_invite,
    parse_document,
)

DEFAULT_FILE = ROOT / ".local" / "gateway" / "invites.json"
DEFAULT_BASE = "http://127.0.0.1:8080"


API = "https://secretmanager.googleapis.com/v1"


def _gcloud_token() -> str:
    return subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        check=True,
        capture_output=True,
        text=True,
        shell=sys.platform == "win32",
    ).stdout.strip()


def _call(url: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method="POST" if body else "GET")
    request.add_header("Authorization", f"Bearer {_gcloud_token()}")
    request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return json.loads(response.read() or b"{}")


def read_secret(secret: str) -> str:
    payload = _call(f"{API}/{secret}/versions/latest:access")["payload"]["data"]
    return base64.b64decode(payload).decode("utf-8")


def add_secret_version(secret: str, text: str) -> None:
    data = base64.b64encode(text.encode("utf-8")).decode("ascii")
    _call(f"{API}/{secret}:addVersion", {"payload": {"data": data}})


class SecretInviteStore:
    """The invite document held in a Secret Manager secret: read `latest`, save as a new
    version. `read` and `write` are injected so the offline suite needs no network."""

    def __init__(
        self,
        secret: str,
        read: Callable[[str], str] = read_secret,
        write: Callable[[str, str], None] = add_secret_version,
    ) -> None:
        self.secret, self._read, self._write = secret, read, write

    def invites(self) -> list[Invite]:
        return parse_document(self._read(self.secret))

    def save(self, invites: list[Invite]) -> None:
        self._write(self.secret, dump_document(invites))


def main(
    argv: list[str] | None = None,
    store_io: tuple[Callable[[str], str], Callable[[str, str], None]] | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="invites.py")
    parser.add_argument("--file", help="invite store file")
    parser.add_argument("--secret", help="Secret Manager secret, projects/<number>/secrets/<name>")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create", help="make an invite and print its link once")
    create.add_argument("--label", required=True)
    create.add_argument("--days", type=float, required=True)
    create.add_argument("--base-url", default=os.environ.get("GATEWAY_PUBLIC_ORIGIN", DEFAULT_BASE))
    sub.add_parser("list", help="show invite ids, labels and expiry (never hashes)")
    revoke = sub.add_parser("revoke", help="delete an invite")
    revoke.add_argument("--id", required=True)
    args = parser.parse_args(argv)

    if args.secret and args.file:
        print("error: --secret and --file are exclusive", file=sys.stderr)
        return 2
    secret = args.secret or (None if args.file else os.environ.get("GATEWAY_INVITES_SECRET"))
    store: FileInviteStore | SecretInviteStore
    if secret:
        store = SecretInviteStore(secret, *(store_io or ()))
    else:
        store = FileInviteStore(args.file or os.environ.get("GATEWAY_INVITES_FILE") or DEFAULT_FILE)
    invites = store.invites()

    if args.command == "create":
        if args.days <= 0:
            print("error: --days must be positive", file=sys.stderr)
            return 2
        invite, token = new_invite(args.label, args.days, dt.datetime.now(dt.UTC))
        store.save([*invites, invite])
        print(f"invite {invite.id} ({invite.label}) expires {invite.expires_at.isoformat()}")
        print("link (shown once):")
        print(f"{args.base_url.rstrip('/')}/#invite={token}")
        return 0
    if args.command == "list":
        now = dt.datetime.now(dt.UTC)
        for i in invites:
            state = "expired" if i.expired(now) else "active"
            print(f"{i.id}  {state:8}  expires {i.expires_at.isoformat()}  {i.label}")
        print(f"{len(invites)} invite(s)")
        return 0
    kept = [i for i in invites if i.id != args.id]
    if len(kept) == len(invites):
        print(f"error: no invite with id {args.id}", file=sys.stderr)
        return 1
    store.save(kept)
    print(f"revoked {args.id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
