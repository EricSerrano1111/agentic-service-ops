"""Settings from environment variables.

This container holds exactly one set of database credentials: `app_reporting`'s, read
from the same `DB_ROLE_REPORTING_*` variables the roles migration created the role from.
No admin credentials and no other role's.
"""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass

from schemas import DATASET_WINDOW_END, DATASET_WINDOW_START

# The dataset window lives in the shared contract (schemas.reporting): the reporting
# agent's as-of date defaults to its end (ADR-050). `app_reporting` cannot read
# `generation_parameters`, so the window is configuration, not a query.
DEFAULT_WINDOW_START = DATASET_WINDOW_START
DEFAULT_WINDOW_END = DATASET_WINDOW_END


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
    window_start: dt.date = DEFAULT_WINDOW_START
    window_end: dt.date = DEFAULT_WINDOW_END
    #: Server-side cap on any one query, well inside the MCP call timeout (ADR-034).
    statement_timeout_ms: int = 10_000
    connect_timeout_s: int = 5
    host: str = "0.0.0.0"
    port: int = 8101
    #: Host headers accepted on /mcp (DNS-rebinding protection stays on).
    allowed_hosts: tuple[str, ...] = ("localhost:*", "127.0.0.1:*", "mcp_incidents:*")

    def __repr__(self) -> str:  # never print the password
        return f"Settings(db_user={self.db_user!r}, db_host={self.db_host!r}, port={self.port})"

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ.get
        return cls(
            db_host=_required("POSTGRES_HOST"),
            db_port=int(env("POSTGRES_PORT", "5432")),
            db_name=_required("POSTGRES_DB"),
            db_user=_required("DB_ROLE_REPORTING_USER"),
            db_password=_required("DB_ROLE_REPORTING_PASSWORD"),
            window_start=dt.date.fromisoformat(
                env("DATASET_WINDOW_START", DEFAULT_WINDOW_START.isoformat())
            ),
            window_end=dt.date.fromisoformat(
                env("DATASET_WINDOW_END", DEFAULT_WINDOW_END.isoformat())
            ),
            statement_timeout_ms=int(env("MCP_DB_STATEMENT_TIMEOUT_MS", "10000")),
            port=int(env("MCP_INCIDENTS_PORT", "8101")),
            allowed_hosts=tuple(
                h.strip()
                for h in env("MCP_ALLOWED_HOSTS", "localhost:*,127.0.0.1:*,mcp_incidents:*").split(
                    ","
                )
                if h.strip()
            ),
        )
