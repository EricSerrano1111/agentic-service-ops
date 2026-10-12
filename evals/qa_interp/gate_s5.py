"""The Sprint 5 interpretation gate (Prompt W, `evals/sprint5_gates.md` B2), from saved run files.

    .venv\\Scripts\\python evals/qa_interp/gate_s5.py RUN1.json [RUN2.json RUN3.json]

One file per run (each written by `run.py --k 1`); the files are the runs in the order given.
Pre-registered thresholds, in **every** run (ADR-089's rates, strict rounding):

  (a) false rejects: at most 1 of the 23 correct pairs judged `faithful: false`
      (2/42 = 4.76%; 4.76% of 23 = 1.09, rounded down to 1);
  (b) catches: at least 19 of the 23 wrong pairs judged `faithful: false`
      (34/42 = 80.95%; 80.95% of 23 = 18.62, rounded up to 19).

A call that failed counts against the pair (a correct pair is a false reject, a wrong pair is
not caught). A complete run that misses (a) or (b) ends the gate: later runs are not made.
The gate passes only with three complete runs that each meet both. Per-domain counts are
reported (reporting 10, forecast 7, sentiment 6 per role) and are not thresholds.
Exit status: 0 pass, 1 fail, 2 not yet decided (incomplete, fewer than 3 runs).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

CORRECT_PAIRS = 23
WRONG_PAIRS = 23
PAIRS_PER_RUN = CORRECT_PAIRS + WRONG_PAIRS
MAX_FALSE_REJECTS = 1
MIN_CAUGHT = 19
RUNS_REQUIRED = 3
DOMAINS = ("reporting", "forecast", "sentiment")


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def score_run(cells: list[dict]) -> dict:
    ids = {c["id"] for c in cells}
    out: dict = {"complete": len(cells) == PAIRS_PER_RUN and len(ids) == PAIRS_PER_RUN}
    for domain in (*DOMAINS, "total"):
        subset = [c for c in cells if domain == "total" or c["domain"] == domain]
        correct = [c for c in subset if c["label"] == "matches"]
        wrong = [c for c in subset if c["label"] == "mismatch"]
        out[domain] = {
            "correct_pairs": len(correct),
            # a failed call (faithful None) on a correct pair is a false reject
            "false_rejects": sum(1 for c in correct if c["faithful"] is not True),
            "wrong_pairs": len(wrong),
            "caught": sum(1 for c in wrong if c["faithful"] is False),
            "errors": sum(1 for c in subset if c["faithful"] is None),
        }
    total = out["total"]
    out["a_ok"] = total["false_rejects"] <= MAX_FALSE_REJECTS
    out["b_ok"] = total["caught"] >= MIN_CAUGHT
    return out


def evaluate(files: list[dict]) -> dict:
    runs = [score_run(run) for result in files for run in result["runs"]]
    scored = [r for r in runs if r["complete"]]
    failed = any(not (r["a_ok"] and r["b_ok"]) for r in scored)
    passes = len(runs) >= RUNS_REQUIRED and all(
        r["complete"] and r["a_ok"] and r["b_ok"] for r in runs[:RUNS_REQUIRED]
    )
    return {
        "prompt": files[-1].get("prompt") if files else None,
        "runs": runs,
        "failed": failed,
        "passes": passes,
    }


def table(verdict: dict) -> str:
    lines = [
        f"prompt {verdict['prompt']}",
        "run | domain    | false rejects (of correct) | caught (of wrong) | errors",
    ]
    for number, run in enumerate(verdict["runs"], 1):
        for domain in (*DOMAINS, "total"):
            r = run[domain]
            tag = "" if run["complete"] else " (incomplete)"
            rejects = f"{r['false_rejects']:>2} of {r['correct_pairs']:<2}"
            caught = f"{r['caught']:>2} of {r['wrong_pairs']:<2}"
            lines.append(
                f"{number:>3}{tag} | {domain:<9} | {rejects:<26} | {caught:<17} | {r['errors']}"
            )
        lines.append(
            f"    run {number}: (a) <= {MAX_FALSE_REJECTS}: "
            f"{'PASS' if run['a_ok'] else 'FAIL'}; (b) >= {MIN_CAUGHT}: "
            f"{'PASS' if run['b_ok'] else 'FAIL'}"
        )
    state = "PASS" if verdict["passes"] else "FAIL" if verdict["failed"] else "OPEN"
    lines.append(f"gate: {state}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: gate_s5.py RUN1.json [RUN2.json RUN3.json]", file=sys.stderr)
        return 2
    verdict = evaluate([load(p) for p in argv[1:]])
    print(table(verdict))
    if verdict["failed"]:
        return 1
    return 0 if verdict["passes"] else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
