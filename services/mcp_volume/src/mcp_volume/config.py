"""Settings from environment variables.

This container holds exactly one set of database credentials: `app_forecast`'s, read from
the same `DB_ROLE_FORECAST_*` variables the roles migration created the role from. No admin
credentials and no other role's.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from common import database_host


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} must be set")
    return value


@dataclass(frozen=True)
class Settings:
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str = ""
    #: Folder holding the artifact's slice files, mounted read-only.
    models_dir: Path = Path("/models/forecast/volume_v2")
    #: The committed manifest; its SHA-256 is the `model_version` every answer reports.
    manifest_path: Path = Path("/app/artifacts/volume_v2.manifest.json")
    #: Server-side cap on any one query, well inside the MCP call timeout (ADR-034).
    statement_timeout_ms: int = 10_000
    connect_timeout_s: int = 5
    host: str = "0.0.0.0"
    port: int = 8103
    #: Host headers accepted on /mcp (DNS-rebinding protection stays on).
    allowed_hosts: tuple[str, ...] = ("localhost:*", "127.0.0.1:*", "mcp_volume:*")

    def __repr__(self) -> str:  # never print the password
        return f"Settings(db_user={self.db_user!r}, db_host={self.db_host!r}, port={self.port})"

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ.get
        return cls(
            db_host=database_host(),
            db_port=int(env("POSTGRES_PORT", "5432")),
            db_name=_required("POSTGRES_DB"),
            db_user=_required("DB_ROLE_FORECAST_USER"),
            db_password=_required("DB_ROLE_FORECAST_PASSWORD"),
            models_dir=Path(env("MODELS_DIR", "/models/forecast/volume_v2")),
            manifest_path=Path(env("MANIFEST_PATH", "/app/artifacts/volume_v2.manifest.json")),
            statement_timeout_ms=int(env("MCP_DB_STATEMENT_TIMEOUT_MS", "10000")),
            port=int(env("MCP_VOLUME_PORT", "8103")),
            allowed_hosts=tuple(
                h.strip()
                for h in env("MCP_ALLOWED_HOSTS", "localhost:*,127.0.0.1:*,mcp_volume:*").split(",")
                if h.strip()
            ),
        )
