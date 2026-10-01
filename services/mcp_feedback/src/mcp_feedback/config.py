"""Settings from environment variables.

This container holds exactly one set of database credentials: `app_sentiment`'s, read
from the same `DB_ROLE_SENTIMENT_*` variables the roles migration created the role from.
No admin credentials and no other role's.
"""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass
from pathlib import Path

from schemas import DATASET_WINDOW_END, DATASET_WINDOW_START

DEFAULT_WINDOW_START = DATASET_WINDOW_START
DEFAULT_WINDOW_END = DATASET_WINDOW_END

#: On-demand scoring cap per request (ADR-067): the 30 s warm-inference budget (ADR-065)
#: times about 10.7 comments per second measured on 1 CPU in the latency proxy (the
#: largest region-quarter, 225 comments, in 20.7 s; L-28, L-29) = 321, rounded down.
#: Comments above the cap are left for a later request or the backfill, and the answer
#: reports its coverage.
DEFAULT_SCORE_CAP = 300
#: Inference batch size, as in training (ADR-065).
DEFAULT_BATCH_SIZE = 16


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
    #: Folder holding the artifact's files (`bert_v1/`), mounted read-only.
    models_dir: Path = Path("/models/sentiment/bert_v1")
    #: The committed manifest; its SHA-256 is the stored predictions' `model_version`.
    manifest_path: Path = Path("/app/artifacts/bert_v1.manifest.json")
    score_cap: int = DEFAULT_SCORE_CAP
    batch_size: int = DEFAULT_BATCH_SIZE
    window_start: dt.date = DEFAULT_WINDOW_START
    window_end: dt.date = DEFAULT_WINDOW_END
    #: Server-side cap on any one query, well inside the MCP call timeout (ADR-034).
    statement_timeout_ms: int = 10_000
    connect_timeout_s: int = 5
    host: str = "0.0.0.0"
    port: int = 8102
    #: Host headers accepted on /mcp (DNS-rebinding protection stays on).
    allowed_hosts: tuple[str, ...] = ("localhost:*", "127.0.0.1:*", "mcp_feedback:*")

    def __repr__(self) -> str:  # never print the password
        return f"Settings(db_user={self.db_user!r}, db_host={self.db_host!r}, port={self.port})"

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ.get
        return cls(
            db_host=_required("POSTGRES_HOST"),
            db_port=int(env("POSTGRES_PORT", "5432")),
            db_name=_required("POSTGRES_DB"),
            db_user=_required("DB_ROLE_SENTIMENT_USER"),
            db_password=_required("DB_ROLE_SENTIMENT_PASSWORD"),
            models_dir=Path(env("MODELS_DIR", "/models/sentiment/bert_v1")),
            manifest_path=Path(env("MANIFEST_PATH", "/app/artifacts/bert_v1.manifest.json")),
            score_cap=int(env("SENTIMENT_SCORE_CAP", str(DEFAULT_SCORE_CAP))),
            window_start=dt.date.fromisoformat(
                env("DATASET_WINDOW_START", DEFAULT_WINDOW_START.isoformat())
            ),
            window_end=dt.date.fromisoformat(
                env("DATASET_WINDOW_END", DEFAULT_WINDOW_END.isoformat())
            ),
            statement_timeout_ms=int(env("MCP_DB_STATEMENT_TIMEOUT_MS", "10000")),
            port=int(env("MCP_FEEDBACK_PORT", "8102")),
            allowed_hosts=tuple(
                h.strip()
                for h in env("MCP_ALLOWED_HOSTS", "localhost:*,127.0.0.1:*,mcp_feedback:*").split(
                    ","
                )
                if h.strip()
            ),
        )
