"""Write `manifest.json` for the frozen evaluation sets (ADR-094). Run after the freeze commit.

    .venv\Scripts\python evals/generated/write_manifest.py

Records, per file, the SHA-256, the git blob hash and the line count, and the freeze commit's
hash and time (HEAD when this runs: the commit that holds the final files). The hash test
(`tests/unit/test_eval_set_manifest.py`) recomputes the three per-file values from the files
alone; it never looks the commit up, so it passes in a shallow clone.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

SETS = (
    "evals/generated/sets/routing_heldout_v1.jsonl",
    "evals/generated/sets/fr03_fresh_v2.jsonl",
    "evals/generated/sets/interp_fresh_v1.jsonl",
    "evals/generated/sets/interp_pairs_v1.jsonl",
    "evals/generated/sets/parse_filters_v1.jsonl",
    "evals/generated/sets/reserve.jsonl",
)
SUPPORTING = (
    "evals/generated/sets/skim_applied.json",
    "evals/generated/pairs_provenance.json",
    "evals/generated/pairs_plan.md",
)


def describe(path: Path) -> dict:
    data = path.read_bytes()
    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "git_blob": hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest(),
        "lines": data.count(b"\n"),
    }


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def main() -> int:
    head = git("rev-parse", "HEAD")
    manifest = {
        "adr": "ADR-094",
        "note": "Final sets are append-never: a later change is a new version under a new ADR.",
        "freeze_commit": head,
        "freeze_time": git("show", "-s", "--format=%cI", head),
        "sets": {p: describe(ROOT / p) for p in SETS},
        "supporting": {p: describe(ROOT / p) for p in SUPPORTING},
    }
    (HERE / "manifest.json").write_bytes(
        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )
    print(json.dumps({"freeze_commit": head, "files": len(SETS) + len(SUPPORTING)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
