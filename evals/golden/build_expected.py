"""Compute golden set v1's expected figures and hash the set (ADR-074).

    .venv\\Scripts\\python evals/golden/build_expected.py [--set golden_v2]

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

#: Why each later version exists. ADR-074: a new version keeps the earlier one and says
#: why it changed; it records that the set was not run or used to tune anything.
DERIVATIONS = {
    "golden_v2": {
        "derived_from": "golden_v1",
        "reason": (
            "ADR-075. G35 ('How's the Southeast doing?') is ambiguous under ADR-075's "
            "definition and now expects needs_clarification with reason intent_ambiguous, "
            "where v1 accepted a reporting or sentiment answer. G01 and G16 are scored on "
            "AskResponse.reason (technician_not_found, technician_ambiguous): v1 named "
            "error codes the API never returned. Every other item is unchanged."
        ),
        "disclosure": (
            "The golden set has not been run against the system, and neither v1 nor v2 was "
            "used to tune any prompt. It stays blind until the Sprint 5 evaluation."
        ),
    }
}
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


def load_items(questions: Path) -> list[Item]:
    lines = questions.read_text(encoding="utf-8").splitlines()
    return [Item.model_validate_json(line) for line in lines if line]


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--set", default="golden_v1", help="set stem (golden_v1, golden_v2)")
    name = ap.parse_args(argv).set
    questions = HERE / f"{name}.jsonl"
    expected_path = HERE / f"{name}.expected.json"
    manifest_path = HERE / f"{name}.manifest.json"
    items = load_items(questions)
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
    conn.close()
    dirty = bool(git("status", "--porcelain", "--", "evals/golden/oracles.py"))
    out = {
        "evidence": "observed",
        "set": name,
        **DERIVATIONS.get(name, {}),
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
    expected_path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "set": name,
                **DERIVATIONS.get(name, {}),
                "questions": {"file": questions.name, "sha256": sha256(questions)},
                "expected": {"file": expected_path.name, "sha256": sha256(expected_path)},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"{len(items)} items, {len(expected)} with oracles; rows {counts}; "
        f"wrote {expected_path.name} and {manifest_path.name}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
