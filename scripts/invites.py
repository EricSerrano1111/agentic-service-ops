"""Invite administration for the gateway (ADR-097).

    .venv/Scripts/python scripts/invites.py create --label "grader" --days 14
    .venv/Scripts/python scripts/invites.py list
    .venv/Scripts/python scripts/invites.py revoke --id <id>

The store file is `--file`, else `$GATEWAY_INVITES_FILE`, else `.local/gateway/invites.json`
(gitignored). `create` prints the link once: the token is not stored, only its SHA-256, and it
cannot be shown again. `list` never shows a hash. On Cloud Run the same document is a Secret
Manager secret: add the file's content as a new version (Prompt U); a revoke there takes effect
within the gateway's 60-second cache.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api_gateway" / "src"))

from api_gateway.invites import FileInviteStore, new_invite  # noqa: E402

DEFAULT_FILE = ROOT / ".local" / "gateway" / "invites.json"
DEFAULT_BASE = "http://127.0.0.1:8080"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="invites.py")
    parser.add_argument("--file", help="invite store file")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create", help="make an invite and print its link once")
    create.add_argument("--label", required=True)
    create.add_argument("--days", type=float, required=True)
    create.add_argument("--base-url", default=os.environ.get("GATEWAY_PUBLIC_ORIGIN", DEFAULT_BASE))
    sub.add_parser("list", help="show invite ids, labels and expiry (never hashes)")
    revoke = sub.add_parser("revoke", help="delete an invite")
    revoke.add_argument("--id", required=True)
    args = parser.parse_args(argv)

    path = args.file or os.environ.get("GATEWAY_INVITES_FILE") or DEFAULT_FILE
    store = FileInviteStore(path)
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
