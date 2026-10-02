"""The forecast holdout ledger (ADR-069): append-only, one line per model, scored once.

`evals/results/forecast/test_ledger.jsonl`. Same rules as the sentiment test ledger
(ADR-064): a second holdout scoring for a model is refused before the holdout is scored,
and the git-dirty check ignores the ledger file itself, so an earlier line appended in
the same session doesn't mark a clean commit dirty.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "evals" / "results" / "forecast" / "test_ledger.jsonl"


class LedgerRefusal(RuntimeError):
    """This model has already been scored on the holdout."""


def check_not_scored(model: str, ledger: Path | None = None) -> None:
    ledger = ledger or LEDGER
    if ledger.exists():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            if line.strip() and json.loads(line)["model"] == model:
                raise LedgerRefusal(
                    f"{model} was already scored on the holdout. The holdout is scored "
                    "once per model (ADR-069)."
                )


def append(entry: dict, ledger: Path | None = None) -> None:
    ledger = ledger or LEDGER
    check_not_scored(entry["model"], ledger)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")


def git_state(root: Path | None = None, ledger: Path | None = None) -> tuple[str, bool]:
    """(HEAD, dirty). Dirty means a tracked change other than to the ledger itself."""
    root = root or ROOT
    rel = (ledger or LEDGER).resolve().relative_to(root.resolve()).as_posix()
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()
    diff = ["git", "diff", "--quiet", "HEAD", "--", ".", f":(exclude){rel}"]
    return head, subprocess.run(diff, cwd=root).returncode != 0
