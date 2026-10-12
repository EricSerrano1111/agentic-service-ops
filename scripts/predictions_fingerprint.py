"""Row count and content hash of the stored sentiment predictions (Prompt U, section 6).

    .venv/Scripts/python scripts/predictions_fingerprint.py            # local database
    $env:POSTGRES_PORT=5433; .venv/Scripts/python scripts/predictions_fingerprint.py  # via proxy

Reads as `app_eval` (DB_ROLE_EVAL_USER / DB_ROLE_EVAL_PASSWORD, POSTGRES_HOST, POSTGRES_PORT,
POSTGRES_DB), read-only, and prints a count and a SHA-256 for the current model version only
(the SHA-256 of the committed manifest). Rows are ordered by `feedback_id`; each is the text
`feedback_id|predicted_label|confidence|flagged` with confidence at four places. Timestamps
(`scored_at`) and anything serial are left out, so a backfill run on another day matches.
Prints no row. Equal output on two databases means the same predictions for the same comments.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "ml" / "sentiment" / "artifacts" / "bert_v1.manifest.json"


def fingerprint(rows) -> tuple[int, str]:
    digest, n = hashlib.sha256(), 0
    for feedback_id, label, confidence, flagged in rows:
        digest.update(f"{feedback_id}|{label}|{confidence:.4f}|{int(bool(flagged))}\n".encode())
        n += 1
    return n, digest.hexdigest()


def main() -> int:
    version = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    url = URL.create(
        "postgresql+psycopg",
        username=os.environ["DB_ROLE_EVAL_USER"],
        password=os.environ["DB_ROLE_EVAL_PASSWORD"],
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        database=os.environ.get("POSTGRES_DB", "service_ops"),
    )
    with create_engine(url).connect() as conn:
        rows = conn.execute(
            text(
                "SELECT feedback_id, predicted_label, confidence, flagged "
                "FROM sentiment_predictions WHERE model_version = :v ORDER BY feedback_id"
            ),
            {"v": version},
        ).all()
    n, sha = fingerprint(rows)
    print(json.dumps({"model_version": version, "rows": n, "sha256": sha}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
