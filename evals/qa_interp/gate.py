"""The interpretation gate (ADR-089), computed from saved run files. Pre-registered; never loosened.

    .venv\\Scripts\\python evals/qa_interp/gate.py RUN.json [RUN2.json ...]

Each run file holds `runs`: for each run (k = 1..3), the judged pairs. For every run:

  (a) **false rejects**: at most 2 of the 42 correct pairs (28 reporting + 14 forecast) judged
      `faithful: false`;
  (b) **catches**: at least 34 of the 42 wrong pairs (28 + 14) judged `faithful: false`.

The gate passes only if (a) and (b) hold in **every** run and every run is complete (all 84
pairs judged). A call that failed (an API error) counts against the pair: a correct pair
whose call failed is a false reject, a wrong pair whose call failed is not caught. Given
several files (a resumed run), cells are merged by (run, pair id) with the later file winning.
Exit status 0 when the gate passes, 1 when it does not, 2 when runs are incomplete.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MAX_FALSE_REJECTS = 2
MIN_CAUGHT = 34
CORRECT_PAIRS = 42
WRONG_PAIRS = 42
PAIRS_PER_RUN = CORRECT_PAIRS + WRONG_PAIRS


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def merge(files: list[dict]) -> dict[int, dict[str, dict]]:
    """run number -> pair id -> judged cell, later files overriding earlier ones."""
    cells: dict[int, dict[str, dict]] = {}
    for result in files:
        for number, run in enumerate(result["runs"], 1):
            for cell in run:
                cells.setdefault(number, {})[cell["id"]] = cell
    return cells


def rejected(cell: dict) -> bool:
    """Judged `faithful: false`. A failed call is not a judgement: it counts as a rejection of
    a correct pair (a false reject) and as a miss on a wrong pair (see `caught`)."""
    return cell["faithful"] is False


def score_run(cells: dict[str, dict]) -> dict:
    out = {"complete": len(cells) == PAIRS_PER_RUN}
    for domain in ("reporting", "forecast", "total"):
        subset = [c for c in cells.values() if domain == "total" or c["domain"] == domain]
        correct = [c for c in subset if c["label"] == "matches"]
        wrong = [c for c in subset if c["label"] == "mismatch"]
        out[domain] = {
            "correct_pairs": len(correct),
            "false_rejects": sum(1 for c in correct if rejected(c) or c["faithful"] is None),
            "wrong_pairs": len(wrong),
            "caught": sum(1 for c in wrong if rejected(c)),
            "errors": sum(1 for c in subset if c["faithful"] is None),
        }
    total = out["total"]
    out["a_false_rejects_ok"] = total["false_rejects"] <= MAX_FALSE_REJECTS
    out["b_catches_ok"] = total["caught"] >= MIN_CAUGHT
    return out


def evaluate(files: list[dict]) -> dict:
    merged = merge(files)
    runs = [score_run(merged[n]) for n in sorted(merged)]
    complete = bool(runs) and all(r["complete"] for r in runs)
    passes = (
        complete
        and all(r["a_false_rejects_ok"] and r["b_catches_ok"] for r in runs)
        and len(runs) >= 3
    )
    return {
        "prompt": files[-1].get("prompt"),
        "runs": runs,
        "complete": complete and len(runs) >= 3,
        "a_every_run_at_most_2_false_rejects": bool(runs)
        and all(r["a_false_rejects_ok"] for r in runs),
        "b_every_run_at_least_34_of_42_caught": bool(runs) and all(r["b_catches_ok"] for r in runs),
        "passes": passes,
    }


def table(verdict: dict) -> str:
    lines = [
        f"prompt {verdict['prompt']}",
        "run | domain    | false rejects (of correct) | caught (of wrong) | errors",
    ]
    for number, run in enumerate(verdict["runs"], 1):
        for domain in ("reporting", "forecast", "total"):
            r = run[domain]
            lines.append(
                f"{number:>3} | {domain:<9} | {r['false_rejects']:>2} of {r['correct_pairs']:<2}"
                f"{'':<17} | {r['caught']:>2} of {r['wrong_pairs']:<2}{'':<10} | {r['errors']}"
            )
    lines.append(
        f"(a) every run <= {MAX_FALSE_REJECTS} false rejects of {CORRECT_PAIRS}: "
        f"{'PASS' if verdict['a_every_run_at_most_2_false_rejects'] else 'FAIL'}"
    )
    lines.append(
        f"(b) every run >= {MIN_CAUGHT} of {WRONG_PAIRS} caught: "
        f"{'PASS' if verdict['b_every_run_at_least_34_of_42_caught'] else 'FAIL'}"
    )
    lines.append(f"gate: {'PASS' if verdict['passes'] else 'FAIL'}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: gate.py RUN.json [RUN2.json ...]", file=sys.stderr)
        return 2
    verdict = evaluate([load(p) for p in argv[1:]])
    print(table(verdict))
    if not verdict["complete"]:
        print("incomplete: not every run has judged all 84 pairs", file=sys.stderr)
        return 2
    return 0 if verdict["passes"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
