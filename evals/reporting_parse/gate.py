"""The ADR-086 parse gate, computed from saved run files. Pre-registered; never loosened.

    .venv\\Scripts\\python evals/reporting_parse/gate.py BASELINE.json CANDIDATE.json

BASELINE is a `parse_v3` run on the 16 old items; CANDIDATE a `parse_v4` (or `parse_v5`) run on
all 28. The gate:

  (a) on the 16 old items, the candidate's mean number correct (over its runs) is at least the
      baseline's mean minus 1;
  (b) on the 12 new items, the candidate gets at least 10 of 12 in **every** run;
  (c) on the 2 unsupported-area items (f11, f12), the parsed `region` is "unsupported" in
      every run: never mapped to one of the four regions.

"Correct" is the runner's exact match of every field. Criterion (c) looks at the `region`
field alone, because its point is that the area is declined, not mapped. Exit status 0 when
all three hold.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

NEW_IDS = [f"f{n:02d}" for n in range(1, 13)]
UNSUPPORTED_IDS = ["f11", "f12"]
MIN_NEW_PER_RUN = 10
TOLERANCE = 1.0


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def exact_by_run(result: dict, ids: list[str] | None) -> list[int]:
    """Items correct in each run, over `ids` (None: every item in the file)."""
    return [sum(r["exact"] for r in run if ids is None or r["id"] in ids) for run in result["runs"]]


def evaluate(baseline: dict, candidate: dict) -> dict:
    old_ids = [i for i in baseline["expected"]]
    base = exact_by_run(baseline, old_ids)
    cand_old = exact_by_run(candidate, old_ids)
    cand_new = exact_by_run(candidate, NEW_IDS)
    base_mean = sum(base) / len(base)
    cand_mean = sum(cand_old) / len(cand_old)
    unsupported = []
    for run in candidate["runs"]:
        rows = [r for r in run if r["id"] in UNSUPPORTED_IDS]
        unsupported.append(
            len(rows) == len(UNSUPPORTED_IDS)
            and all(r["got"] is not None and r["got"].get("region") == "unsupported" for r in rows)
        )
    a = cand_mean >= base_mean - TOLERANCE
    b = len(cand_new) > 0 and all(n >= MIN_NEW_PER_RUN for n in cand_new)
    c = len(unsupported) > 0 and all(unsupported)
    return {
        "baseline_prompt": baseline["prompt"],
        "candidate_prompt": candidate["prompt"],
        "baseline_old_per_run": base,
        "candidate_old_per_run": cand_old,
        "candidate_new_per_run": cand_new,
        "baseline_mean": round(base_mean, 3),
        "candidate_old_mean": round(cand_mean, 3),
        "unsupported_declined_per_run": unsupported,
        "a_old_items_hold": a,
        "b_new_items_10_of_12_every_run": b,
        "c_unsupported_never_mapped": c,
        "passes": a and b and c,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: gate.py BASELINE.json CANDIDATE.json", file=sys.stderr)
        return 2
    verdict = evaluate(load(argv[1]), load(argv[2]))
    print(json.dumps(verdict, indent=2))
    return 0 if verdict["passes"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
