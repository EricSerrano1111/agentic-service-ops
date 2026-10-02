"""`python -m mcp_feedback.backfill` — score every comment for the current model version.

The same scoring code as the tools (`ensure_scored`), over the whole dataset window, in
chunks of the per-request cap until nothing is left unscored. Runs as `app_sentiment`
(`docker compose run --rm mcp_feedback python -m mcp_feedback.backfill`). Idempotent: a
rerun inserts nothing. A new model version needs its own backfill (ADR-067).
"""

from __future__ import annotations

import logging
import os
import sys
import time

from common import configure_logging

from .config import Settings
from .scoring import Scope, ensure_scored
from .wiring import build_backend

log = logging.getLogger("mcp_feedback")


def main() -> int:
    configure_logging("mcp_feedback", os.environ.get("LOG_LEVEL", "INFO"))
    settings = Settings.from_env()
    backend = build_backend(settings)
    scope = Scope(settings.window_start, settings.window_end)
    began = time.perf_counter()
    inserted = 0
    while True:
        coverage = ensure_scored(
            backend.store, backend.classifier, backend.model_version, scope, settings.score_cap
        )
        inserted += coverage.n_new
        log.info(
            "backfill progress",
            extra={
                "n_scored": coverage.n_scored,
                "n_comments": coverage.n_comments,
                "inserted_total": inserted,
                "elapsed_s": round(time.perf_counter() - began, 1),
            },
        )
        if coverage.complete or coverage.n_new == 0:
            break
    log.info(
        "backfill done",
        extra={
            "model_version": backend.model_version,
            "inserted": inserted,
            "n_scored": coverage.n_scored,
            "n_comments": coverage.n_comments,
            "complete": coverage.complete,
            "total_s": round(time.perf_counter() - began, 1),
        },
    )
    return 0 if coverage.complete else 1


if __name__ == "__main__":
    sys.exit(main())
