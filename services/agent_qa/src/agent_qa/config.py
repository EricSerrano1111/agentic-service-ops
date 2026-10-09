"""Settings from environment variables.

This container holds exactly one set of database credentials: `app_qa`'s, read from the same
`DB_ROLE_QA_*` variables the roles migration created the role from (data dictionary §7). No
admin credentials and no other role's. The `volume_v2` manifest is baked into the image.

Timeout budget inside the orchestrator's QA hop: the deterministic checks are a handful of
queries (each capped by `statement_timeout_ms`), then at most one language-model call of up to
`interp_timeout_s`.
"""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass
from pathlib import Path

from common import database_host
from schemas import DATASET_WINDOW_END, DATASET_WINDOW_START

DEFAULT_MANIFEST = Path("/app/artifacts/volume_v2.manifest.json")


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
    manifest_path: Path = DEFAULT_MANIFEST
    window_start: dt.date = DATASET_WINDOW_START
    window_end: dt.date = DATASET_WINDOW_END
    #: Relative dates resolve against this, never the wall clock (ADR-050); the same variable
    #: the specialists read, so QA and the specialists agree on "today".
    as_of: dt.date = DATASET_WINDOW_END
    #: The reporting agent's presentation minimum for a ranked group (the text check needs it).
    min_group_denominator: int = 20
    #: Server-side cap on any one query.
    statement_timeout_ms: int = 10_000
    connect_timeout_s: int = 5
    #: The interpretation call, retries and 429 waits included.
    interp_timeout_s: float = 30.0
    public_url: str = "http://agent_qa:8004/"
    host: str = "0.0.0.0"
    port: int = 8004

    @property
    def verify_timeout_s(self) -> float:
        """The whole verification: the queries (each capped by the statement timeout), then the
        interpretation call."""
        return self.interp_timeout_s + 15.0

    def __repr__(self) -> str:  # never print the password
        return f"Settings(db_user={self.db_user!r}, db_host={self.db_host!r}, port={self.port})"

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ.get
        d = cls.__dataclass_fields__
        return cls(
            db_host=database_host(),
            db_port=int(env("POSTGRES_PORT", "5432")),
            db_name=_required("POSTGRES_DB"),
            db_user=_required("DB_ROLE_QA_USER"),
            db_password=_required("DB_ROLE_QA_PASSWORD"),
            manifest_path=Path(env("QA_MANIFEST_PATH") or DEFAULT_MANIFEST),
            as_of=dt.date.fromisoformat(
                env("REPORTING_AS_OF_DATE") or DATASET_WINDOW_END.isoformat()
            ),
            min_group_denominator=int(
                env("REPORTING_MIN_GROUP_DENOMINATOR") or d["min_group_denominator"].default
            ),
            statement_timeout_ms=int(env("QA_DB_STATEMENT_TIMEOUT_MS", "10000")),
            interp_timeout_s=float(env("QA_INTERP_TIMEOUT_S", "30")),
            public_url=env("AGENT_QA_PUBLIC_URL", "http://agent_qa:8004/"),
            port=int(env("AGENT_QA_PORT", "8004")),
        )
