"""ADR-114 P1: the go criteria G1 to G5 for one thinking level, from saved run files.

    .venv\\Scripts\\python evals/fr03_v3/p1_score.py --validate     # against the ADR-101 runs

Counts and item IDs only; no question text is read into the output. A run file is a
`run_seed.py` result (rows hold `id`, `expected`, `predicted`); the per-call latency and cost
come from the P1 runner's calls files. The scoring functions of `evals/routing/fr03_gate.py`
(`load`, `non_ambiguous_correct`, ADR-076's 43.00) are used, not copied.

Criteria, for one level (k=3, 115 items: 20 ambiguous, 95 not):
  G1  at least 11 of the 15 discriminating ambiguous items return `ambiguous` in >= 2 of 3 runs
      (the 15 are the ambiguous items of `fr03_fresh_v2` (8) and `routing_heldout_v1` (7))
  G2  that count is at least 3 more than `route_v6` at `minimal` on the same 15
  G3  at most 11 of the 285 non-ambiguous item-runs are routed `ambiguous`
  G4  the mean non-ambiguous correct count on the v2 sets is at least 42.00 of 44
  G5  median latency <= 5 s, p95 <= 10 s, mean list-price cost <= $0.003 per call
A failed call has no route, so it is scored as wrong (ADR-076). The 5 ambiguous items of the v2
sets are reported, not counted.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gate = _load("fr03_gate_for_p1", ROOT / "evals" / "routing" / "fr03_gate.py")
fr03_ledger = _load("fr03_v3_ledger_for_p1", HERE / "ledger.py")

V2_SETS = ("seed_v2.jsonl", "routing_v2.jsonl")
DISCRIMINATING_SETS = ("fr03_fresh_v2.jsonl", "routing_heldout_v1.jsonl")
SET_SIZES = {
    "seed_v2.jsonl": 31,
    "routing_v2.jsonl": 18,
    "fr03_fresh_v2.jsonl": 16,
    "routing_heldout_v1.jsonl": 50,
}
RUNS = 3

G1_MIN, G2_MIN_GAIN, G3_MAX, G4_MIN = 11, 3, 11, gate.ROUTE_V3_DEV_MEAN - 1
G5_MEDIAN_S, G5_P95_S, G5_COST_USD = 5.0, 10.0, 0.003
DISCRIMINATING_AMBIGUOUS, NON_AMBIGUOUS_ITEM_RUNS = 15, 285


def by_set(files: list[dict]) -> dict[str, list[dict]]:
    """Run files grouped by set, each group ordered by `run_at` (run i is the i-th file)."""
    grouped: dict[str, list[dict]] = {}
    for f in files:
        grouped.setdefault(f["seed_set"], []).append(f)
    return {k: sorted(v, key=lambda f: f["run_at"]) for k, v in grouped.items()}


def runs_complete(grouped: dict[str, list[dict]], sets: tuple[str, ...]) -> list[str]:
    notes = []
    for name in sets:
        runs = grouped.get(name, [])
        if len(runs) != RUNS or any(
            r["answered"] != SET_SIZES[name] or r.get("stopped_early") for r in runs
        ):
            notes.append(f"{name}: not {RUNS} complete runs of {SET_SIZES[name]}")
    return notes


def ambiguous_hits(grouped: dict[str, list[dict]], sets: tuple[str, ...]) -> dict[str, int]:
    """For each ambiguous item, the runs (of 3) in which it was routed `ambiguous`."""
    hits: dict[str, int] = {}
    for name in sets:
        for run in grouped.get(name, []):
            for r in run["rows"]:
                if r["expected"] == "ambiguous":
                    hits[r["id"]] = hits.get(r["id"], 0) + (r["predicted"] == "ambiguous")
    return hits


def recognised(grouped: dict[str, list[dict]], sets: tuple[str, ...]) -> dict:
    hits = ambiguous_hits(grouped, sets)
    return {
        "count": sum(1 for n in hits.values() if n >= 2),
        "of": len(hits),
        "recognised_ids": sorted(i for i, n in hits.items() if n >= 2),
        "missed_3_of_3_ids": sorted(i for i, n in hits.items() if n == 0),
        "per_item_hits": dict(sorted(hits.items())),
    }


def flagged(grouped: dict[str, list[dict]]) -> dict:
    """Non-ambiguous item-runs routed `ambiguous`, over all four sets."""
    per_item: dict[str, int] = {}
    total = 0
    for runs in grouped.values():
        for run in runs:
            for r in run["rows"]:
                if r["expected"] != "ambiguous" and r["predicted"] == "ambiguous":
                    total += 1
                    per_item[r["id"]] = per_item.get(r["id"], 0) + 1
    return {
        "item_runs": total,
        "flagged_in_2plus_runs_ids": sorted(i for i, n in per_item.items() if n >= 2),
        "per_item": dict(sorted(per_item.items())),
    }


def v2_counts(grouped: dict[str, list[dict]]) -> list[int]:
    """Per run i, the non-ambiguous correct count summed over the v2 sets."""
    n = min(len(grouped.get(s, [])) for s in V2_SETS)
    return [
        sum(gate.non_ambiguous_correct(grouped[s][i]["rows"]) for s in V2_SETS) for i in range(n)
    ]


def latency_cost(calls: list[dict]) -> dict:
    lat = [c["latency_s"] for c in calls]
    return {
        "calls": len(calls),
        "median_s": round(statistics.median(lat), 3) if lat else None,
        "p95_s": fr03_ledger.percentile_95(lat),
        "mean_cost_per_call_usd": round(sum(c["cost_usd"] for c in calls) / len(calls), 8)
        if calls
        else None,
        "mean_thinking_tokens": round(sum(c["thinking_tokens"] for c in calls) / len(calls), 1)
        if calls
        else None,
    }


def baseline_g1(baseline_files: list[dict]) -> dict:
    """`route_v6` at `minimal` on the 15 discriminating items: `routing_heldout_v1` from the P1
    baseline runs and `fr03_fresh_v2` from the existing C1 runs (ADR-101)."""
    return recognised(by_set(baseline_files), DISCRIMINATING_SETS)


def score_level(level_files: list[dict], calls: list[dict], baseline: dict) -> dict:
    grouped = by_set(level_files)
    notes = runs_complete(grouped, tuple(SET_SIZES))
    g1 = recognised(grouped, DISCRIMINATING_SETS)
    v2_ambiguous = recognised(grouped, V2_SETS)
    fl = flagged(grouped)
    counts = v2_counts(grouped)
    mean = sum(counts) / len(counts) if counts else 0.0
    g5 = latency_cost(calls)
    criteria = {
        "G1": {"count": g1["count"], "of": g1["of"], "need": G1_MIN, "pass": g1["count"] >= G1_MIN},
        "G2": {
            "gain": g1["count"] - baseline["count"],
            "baseline_count": baseline["count"],
            "need": G2_MIN_GAIN,
            "pass": g1["count"] - baseline["count"] >= G2_MIN_GAIN,
        },
        "G3": {
            "item_runs": fl["item_runs"],
            "of": NON_AMBIGUOUS_ITEM_RUNS,
            "max": G3_MAX,
            "pass": fl["item_runs"] <= G3_MAX,
        },
        "G4": {
            "counts": counts,
            "mean": round(mean, 2),
            "need": G4_MIN,
            "pass": bool(counts) and mean >= G4_MIN,
        },
        "G5": {
            **g5,
            "pass": bool(calls)
            and g5["median_s"] <= G5_MEDIAN_S
            and g5["p95_s"] <= G5_P95_S
            and g5["mean_cost_per_call_usd"] <= G5_COST_USD,
        },
    }
    failed = [k for k, v in criteria.items() if not v["pass"]]
    return {
        "complete": not notes,
        "notes": notes,
        "criteria": criteria,
        "pass": not notes and not failed,
        "failed": failed,
        "discriminating_missed_3_of_3_ids": g1["missed_3_of_3_ids"],
        "flagged_in_2plus_runs_ids": fl["flagged_in_2plus_runs_ids"],
        "v2_ambiguous_reported_not_counted": {
            k: v for k, v in v2_ambiguous.items() if k != "per_item_hits"
        },
        "g1_per_item_hits": g1["per_item_hits"],
    }


def load_files(paths: list[str | Path]) -> list[dict]:
    return [gate.load(Path(p) if Path(p).is_absolute() else ROOT / p) for p in paths]


def table(label: str, s: dict) -> str:
    c = s["criteria"]
    g5 = c["G5"]
    return (
        f"{label}: G1 {c['G1']['count']}/{c['G1']['of']} (need {G1_MIN}) | "
        f"G2 +{c['G2']['gain']} (need {G2_MIN_GAIN}) | "
        f"G3 {c['G3']['item_runs']}/{NON_AMBIGUOUS_ITEM_RUNS} (max {G3_MAX}) | "
        f"G4 {c['G4']['mean']:.2f} {c['G4']['counts']} (need {G4_MIN:.2f}) | "
        f"G5 {g5['median_s']}s/{g5['p95_s']}s/${g5['mean_cost_per_call_usd']} | "
        f"{'PASS' if s['pass'] else 'FAIL ' + ','.join(s['failed'])}"
    )


def c1_paths() -> list[Path]:
    """The three existing `route_v6` `minimal` runs on `fr03_fresh_v2` (ADR-101's C1)."""
    results = ROOT / "evals" / "results"
    return [
        p
        for hour in ("2134", "2135", "2136")
        for p in sorted(results.glob(f"routing_fr03_fresh_v2_*route_v6_20261012T{hour}*.json"))
    ]


def a1_paths() -> list[Path]:
    """The three existing `route_v6` `minimal` runs on `seed_v2` and `routing_v2` (ADR-101's A1)."""
    results = ROOT / "evals" / "results"
    return [
        p
        for stem in ("seed_v2", "routing_v2")
        for p in sorted(results.glob(f"routing_{stem}_*route_v6_20261012T21[12]*.json"))
    ]


def validate() -> dict:
    """The ADR-101 figures, reproduced from the committed `route_v6` `minimal` runs."""
    c1, a1 = c1_paths(), a1_paths()
    fresh = by_set(load_files(c1))["fr03_fresh_v2.jsonl"]
    dev = by_set(load_files(a1))
    return {
        "c1_files": len(c1),
        "a1_files": len(a1),
        "fresh_recognised": recognised({"fr03_fresh_v2.jsonl": fresh}, ("fr03_fresh_v2.jsonl",)),
        "fresh_flagged_item_runs": flagged({"fr03_fresh_v2.jsonl": fresh})["item_runs"],
        "fresh_non_ambiguous_correct": [gate.non_ambiguous_correct(r["rows"]) for r in fresh],
        "dev_non_ambiguous_correct": v2_counts(dev),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--validate", action="store_true")
    args = ap.parse_args(argv)
    if args.validate:
        v = validate()
        v["fresh_recognised"].pop("per_item_hits")
        print(json.dumps(v, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
