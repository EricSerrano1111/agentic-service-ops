"""Gateway settings, all from environment variables (ADR-097).

The gateway holds no database credential and no model key. Its secrets are the session signing
key and, on Cloud Run, access to the invite secret.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .session import MIN_KEY_CHARS

AUTH_MODES = ("none", "google_id_token")


class GatewayConfigError(RuntimeError):
    """A setting is missing or invalid; the gateway refuses to start."""


def _int(env, name: str, default: int, minimum: int = 1) -> int:
    raw = (env(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise GatewayConfigError(f"{name} must be an integer") from None
    if value < minimum:
        raise GatewayConfigError(f"{name} must be at least {minimum}")
    return value


@dataclass(frozen=True)
class Settings:
    session_key: str
    public_origin: str
    orchestrator_url: str = "http://orchestrator:8000"
    auth: str = "none"
    invites_file: Path | None = None
    invites_secret: str | None = None
    static_dir: Path | None = None
    #: Just over the orchestrator's 120 s request deadline (ADR-034), so its own degraded
    #: response is what the user sees rather than a gateway timeout.
    upstream_timeout_s: float = 125.0
    exchange_per_minute: int = 10
    asks_per_session_hour: int = 30  # per invite; ADR-107 (was 15, ADR-097)
    daily_question_cap: int = 50
    trusted_proxy_hops: int = 1
    port: int = 8080

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ.get
        key = (env("GATEWAY_SESSION_KEY") or "").strip()
        if len(key) < MIN_KEY_CHARS:
            raise GatewayConfigError(
                f"GATEWAY_SESSION_KEY must be set to at least {MIN_KEY_CHARS} characters"
            )
        auth = (env("GATEWAY_AUTH") or "none").strip().lower()
        if auth not in AUTH_MODES:
            raise GatewayConfigError(f"GATEWAY_AUTH must be one of {', '.join(AUTH_MODES)}")
        file = (env("GATEWAY_INVITES_FILE") or "").strip()
        secret = (env("GATEWAY_INVITES_SECRET") or "").strip()
        if not file and not secret:
            raise GatewayConfigError(
                "set GATEWAY_INVITES_FILE (local) or GATEWAY_INVITES_SECRET (Secret Manager)"
            )
        origin = (env("GATEWAY_PUBLIC_ORIGIN") or "http://127.0.0.1:8080").strip().rstrip("/")
        static = (env("GATEWAY_STATIC_DIR") or "").strip()
        return cls(
            session_key=key,
            public_origin=origin,
            orchestrator_url=(env("GATEWAY_ORCHESTRATOR_URL") or cls.orchestrator_url).rstrip("/"),
            auth=auth,
            invites_file=Path(file) if file else None,
            invites_secret=secret or None,
            static_dir=Path(static) if static else None,
            upstream_timeout_s=float(env("GATEWAY_UPSTREAM_TIMEOUT_S") or cls.upstream_timeout_s),
            exchange_per_minute=_int(env, "GATEWAY_EXCHANGE_PER_MINUTE", 10),
            asks_per_session_hour=_int(env, "GATEWAY_ASKS_PER_SESSION_HOUR", 30),
            daily_question_cap=_int(env, "GATEWAY_DAILY_QUESTION_CAP", 50),
            trusted_proxy_hops=_int(env, "GATEWAY_TRUSTED_PROXY_HOPS", 1),
            port=_int(env, "GATEWAY_PORT", 8080),
        )
