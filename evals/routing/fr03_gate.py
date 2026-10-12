"""The Sprint 5 FR-03 gate (Prompt W, `evals/sprint5_gates.md` B1), from saved run files.

    .venv\\Scripts\\python evals/routing/fr03_gate.py --fresh-v6 F1 F2 F3 --fresh-v3 F1 F2 F3 \\
        --dev-v6 SEED1 ROUT1 SEED2 ROUT2 SEED3 ROUT3

Files are `run_seed.py` results (rows hold `expected` and `predicted`). Criteria (ADR-076's,
scaled to `fr03_fresh_v2`: 8 ambiguous and 8 non-ambiguous items):

  (a)  at most 1 non-ambiguous item-run routed `ambiguous`, across route_v6's 3 fresh runs;
  (b1) on the development sets seed_v2 + routing_v2 (44 non-ambiguous items), route_v6's mean
       non-ambiguous correct count over its 3 runs is at least 43.00 - 1 = 42.00 (route_v3's
       recorded 3-run mean, ADR-076);
  (b2) on the fresh set's 8 non-ambiguous items, route_v6's 3-run mean is at least route_v3's
       3-run mean minus 1;
  (c)  at least 6 of the 8 ambiguous items return `ambiguous` in at least 2 of 3 runs.

A pass needs all four, with every run complete (a part-run gate counts as failed).
`--dev-v6` takes the A1 files; they are grouped by set (`seed_set` field) and ordered by
`run_at`, so run i of the development check is the i-th file of each set.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROUTE_V3_DEV_MEAN = 43.00  # ADR-076: 43, 43, 43
FRESH_AMBIGUOUS = 8
FRESH_NON_AMBIGUOUS = 8
DEV_SETS = {"seed_v2.jsonl": 31, "routing_v2.jsonl": 18}
RUNS = 3
C_NEEDED = math.ceil(2 / 3 * FRESH_AMBIGUOUS)  # 6


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def non_ambiguous_correct(rows: list[dict]) -> int:
    return sum(1 for r in rows if r["expected"] != "ambiguous" and r["predicted"] == r["expected"])


def evaluate(fresh_v6: list[dict], fresh_v3: list[dict], dev_v6: list[dict]) -> dict:
    notes: list[str] = []

    def runs_ok(files: list[dict], size: int, label: str) -> None:
        bad = len(files) != RUNS or any(
            f["answered"] != size or f.get("stopped_early") for f in files
        )
        if bad:
            notes.append(f"{label}: not {RUNS} complete runs of {size}")

    fresh_size = FRESH_AMBIGUOUS + FRESH_NON_AMBIGUOUS
    runs_ok(fresh_v6, fresh_size, "fresh route_v6")
    runs_ok(fresh_v3, fresh_size, "fresh route_v3")
    by_set: dict[str, list[dict]] = {name: [] for name in DEV_SETS}
    for f in dev_v6:
        by_set.setdefault(f["seed_set"], []).append(f)
    for name, size in DEV_SETS.items():
        by_set[name] = sorted(by_set[name], key=lambda f: f["run_at"])
        runs_ok(by_set[name], size, f"development {name}")
    complete = not notes

    false_amb = sum(
        1
        for f in fresh_v6
        for r in f["rows"]
        if r["expected"] != "ambiguous" and r["predicted"] == "ambiguous"
    )
    n_dev = min(len(by_set[n]) for n in DEV_SETS)
    dev_counts = [
        sum(non_ambiguous_correct(by_set[name][i]["rows"]) for name in DEV_SETS)
        for i in range(n_dev)
    ]
    dev_mean = sum(dev_counts) / len(dev_counts) if dev_counts else 0.0
    v6_counts = [non_ambiguous_correct(f["rows"]) for f in fresh_v6]
    v3_counts = [non_ambiguous_correct(f["rows"]) for f in fresh_v3]
    v6_mean = sum(v6_counts) / len(v6_counts) if v6_counts else 0.0
    v3_mean = sum(v3_counts) / len(v3_counts) if v3_counts else 0.0
    hits: dict[str, int] = {}
    for f in fresh_v6:
        for r in f["rows"]:
            if r["expected"] == "ambiguous":
                hits[r["id"]] = hits.get(r["id"], 0) + (r["predicted"] == "ambiguous")
    recognised = sorted(i for i, n in hits.items() if n >= 2)
    misses = sorted(i for i, n in hits.items() if n < 2)

    verdict = {
        "complete": complete,
        "notes": notes,
        "a": {"non_ambiguous_routed_ambiguous": false_amb, "limit": 1, "pass": false_amb <= 1},
        "b1": {
            "counts": dev_counts,
            "mean": round(dev_mean, 2),
            "floor": ROUTE_V3_DEV_MEAN - 1,
            "pass": bool(dev_counts) and dev_mean >= ROUTE_V3_DEV_MEAN - 1,
        },
        "b2": {
            "v6": v6_counts,
            "v3": v3_counts,
            "v6_mean": round(v6_mean, 2),
            "v3_mean": round(v3_mean, 2),
            "floor": round(v3_mean - 1, 2),
            "pass": bool(v6_counts) and bool(v3_counts) and v6_mean >= v3_mean - 1,
        },
        "c": {
            "recognised": len(recognised),
            "needed": C_NEEDED,
            "misses": misses,
            "pass": len(recognised) >= C_NEEDED,
        },
    }
    verdict["passes"] = complete and all(verdict[k]["pass"] for k in ("a", "b1", "b2", "c"))
    return verdict


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--fresh-v6", nargs="+", required=True)
    ap.add_argument("--fresh-v3", nargs="+", required=True)
    ap.add_argument("--dev-v6", nargs="+", required=True)
    args = ap.parse_args(argv)
    verdict = evaluate(
        [load(p) for p in args.fresh_v6],
        [load(p) for p in args.fresh_v3],
        [load(p) for p in args.dev_v6],
    )
    print(json.dumps(verdict, indent=2))
    print("FR-03 gate:", "PASS" if verdict["passes"] else "FAIL")
    return 0 if verdict["passes"] else 1


if __name__ == "__main__":
    sys.exit(main())
