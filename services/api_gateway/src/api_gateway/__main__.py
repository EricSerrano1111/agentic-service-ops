"""`python -m api_gateway serve` runs the gateway."""

from __future__ import annotations

import os
import sys
import time

import uvicorn
from common import configure_logging

from .app import create_app
from .config import Settings
from .invites import FileInviteStore, SecretManagerInviteStore, secret_manager_fetch
from .upstream import IdTokenProvider, Orchestrator


def build_app():
    settings = Settings.from_env()
    if settings.invites_secret:
        store = SecretManagerInviteStore(secret_manager_fetch(settings.invites_secret))
    else:
        store = FileInviteStore(settings.invites_file)
    tokens = None
    if settings.auth == "google_id_token":
        tokens = IdTokenProvider(settings.orchestrator_url)
    orchestrator = Orchestrator(
        settings.orchestrator_url, settings.upstream_timeout_s, tokens=tokens
    )
    return create_app(settings, store, orchestrator, clock=time.time), settings


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if args != ["serve"]:
        print("usage: python -m api_gateway serve", file=sys.stderr)
        return 2
    configure_logging("gateway", os.environ.get("LOG_LEVEL", "INFO"))
    app, settings = build_app()
    uvicorn.run(
        app,
        host="0.0.0.0",  # noqa: S104  # inside the container; compose binds the port to loopback
        port=settings.port,
        log_config=None,
        access_log=False,  # replaced by the trace-id access line (ADR-108)
        # Cloud Run's front end is the only peer; the forwarded-for rule is applied in code.
        proxy_headers=False,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
