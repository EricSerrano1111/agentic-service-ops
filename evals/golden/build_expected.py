"""Compute golden set v1's expected figures and hash the set (ADR-074).

    .venv\\Scripts\\python evals/golden/build_expected.py

Runs every item's oracle against Postgres as `app_eval` (and the forecast artifact from
local files), then writes:
- `golden_v1.expected.json`: the expected figures per item, the oracle code's git commit
  and SHA-256, the database's row counts, the sentiment `model_version` and the forecast
  manifest's SHA-256;
- `golden_v1.manifest.json`: SHA-256 of the questions file and of the expected file.

Calls nothing but Postgres and local files: no model, agent, orchestrator or MCP server.
Prints a summary only.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import oracles  # noqa: E402
from schema import Item  # noqa: E402

QUESTIONS = HERE / "golden_v1.jsonl"
EXPECTED = HERE / "golden_v1.expected.json"
MANIFEST = HERE / "golden_v1.manifest.json"
TABLES = (
    "accounts",
    "locations",
    "technicians",
    "service_requests",
    "archived_requests",
    "incidents",
    "service_feedback",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def load_items() -> list[Item]:
    lines = QUESTIONS.read_text(encoding="utf-8").splitlines()
    return [Item.model_validate_json(line) for line in lines if line]


def main() -> int:
    items = load_items()
    conn = oracles.connect()
    counts = {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in TABLES}
    counts["sentiment_predictions@model_version"] = conn.execute(
        "SELECT count(*) FROM sentiment_predictions WHERE model_version = %s",
        (oracles.SENTIMENT_MODEL_VERSION,),
    ).fetchone()[0]
    expected = {}
    for item in items:
        if item.oracle is not None:
            expected[item.id] = oracles.ORACLES[item.oracle](conn)
    dirty = bool(git("status", "--porcelain", "--", "evals/golden/oracles.py"))
    out = {
        "evidence": "observed",
        "set": "golden_v1",
        "as_of": oracles.AS_OF.isoformat(),
        "oracle_code": {
            "git_commit": git("rev-parse", "HEAD"),
            "oracles_py_sha256": sha256(HERE / "oracles.py"),
            "uncommitted_at_build": dirty,
        },
        "database_row_counts": counts,
        "sentiment_model_version": oracles.SENTIMENT_MODEL_VERSION,
        "forecast_manifest_sha256": sha256(oracles.FORECAST_MANIFEST),
        "items": expected,
    }
    EXPECTED.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    MANIFEST.write_text(
        json.dumps(
            {
                "set": "golden_v1",
                "questions": {"file": QUESTIONS.name, "sha256": sha256(QUESTIONS)},
                "expected": {"file": EXPECTED.name, "sha256": sha256(EXPECTED)},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"{len(items)} items, {len(expected)} with oracles; rows {counts}; "
        f"wrote {EXPECTED.name} and {MANIFEST.name}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
