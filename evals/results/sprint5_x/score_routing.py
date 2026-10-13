"""Score the held-out routing runs as pre-registered (evals/sprint5_gates.md B3).

    .venv\\Scripts\\python evals/results/sprint5_x/score_routing.py

Reads evals/results/routing_heldout_v1/2026-10-13/run{1,2,3}.json (harness output) and writes
score.json beside them. The default router is route_v3, which has no `ambiguous` route, so the
7 ambiguous items are scored wrong (FR-03 forbids force-routing); the figure without them is
reported alongside and labelled. Nothing here changes a label or a rule.

Taxonomy, one class per wrong item-run, first match wins:
  error or timeout       no usable route in the response
  ambiguous not flagged  expected ambiguous, any other route returned
  false ambiguous        returned ambiguous for a non-ambiguous item
  multi-domain missed    expected multi_domain, anything else returned
  out-of-scope accepted  expected out_of_scope, anything else returned
  in-scope declined      expected a single domain, out_of_scope returned
  wrong area             expected a single domain, another domain or multi_domain returned
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

DIR = Path(__file__).resolve().parents[1] / "routing_heldout_v1" / "2026-10-13"
CLASSES = (
    "wrong area",
    "ambiguous not flagged",
    "false ambiguous",
    "multi-domain missed",
    "out-of-scope accepted",
    "in-scope declined",
    "error or timeout",
)
DOMAINS = {"reporting", "sentiment", "forecast"}
DEADLINE_S = 120


def predicted_route(row: dict) -> str | None:
    body = row.get("response") or {}
    if row.get("http_status") != 200 or not isinstance(body, dict):
        return None
    route = body.get("route") or {}
    return route.get("route")


def classify(expected: str, got: str | None) -> str | None:
    """None when correct."""
    if got is None:
        return "error or timeout"
    if got == expected:
        return None
    if expected == "ambiguous":
        return "ambiguous not flagged"
    if got == "ambiguous":
        return "false ambiguous"
    if expected == "multi_domain":
        return "multi-domain missed"
    if expected == "out_of_scope":
        return "out-of-scope accepted"
    if expected in DOMAINS and got == "out_of_scope":
        return "in-scope declined"
    return "wrong area"


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return float("nan")
    k = (len(ordered) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def main() -> int:
    runs = []
    for p in (1, 2, 3):
        path = DIR / f"run{p}.json"
        if path.exists():
            runs.append(json.loads(path.read_text("utf-8")))
    out: dict = {"runs": [], "complete_runs": sum(r.get("complete", False) for r in runs)}
    per_item: dict[str, list[bool]] = defaultdict(list)
    wrong_rows: list[dict] = []
    cat_hits: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    taxonomy: Counter = Counter()
    for run in runs:
        rows = run["rows"]
        correct = no_amb_correct = no_amb_n = 0
        secs = [r["seconds"] for r in rows]
        for r in rows:
            got = predicted_route(r)
            cls = classify(r["expected"], got)
            ok = cls is None
            correct += ok
            amb = r["expected"] == "ambiguous"
            if not amb:
                no_amb_n += 1
                no_amb_correct += ok
            per_item[r["id"]].append(ok)
            cat_hits[r["category"]][0] += ok
            cat_hits[r["category"]][1] += 1
            if not ok:
                taxonomy[cls] += 1
                body = r.get("response") or {}
                wrong_rows.append(
                    {
                        "pass": run["pass"],
                        "id": r["id"],
                        "category": r["category"],
                        "expected": r["expected"],
                        "got": got,
                        "class": cls,
                        "outcome": body.get("outcome"),
                        "route_reason": (body.get("route") or {}).get("reason"),
                        "question": r["question"],
                        "error": r.get("error", ""),
                    }
                )
        outcomes = Counter((r.get("response") or {}).get("outcome") for r in rows)
        out["runs"].append(
            {
                "pass": run["pass"],
                "n": len(rows),
                "complete": run.get("complete", False),
                "correct": correct,
                "correct_without_ambiguous": no_amb_correct,
                "n_without_ambiguous": no_amb_n,
                "median_s": round(statistics.median(secs), 2) if secs else None,
                "p95_s": round(percentile(secs, 0.95), 2) if secs else None,
                "over_deadline": sorted(
                    r["id"]
                    for r in rows
                    if r["seconds"] > DEADLINE_S or r.get("http_status") != 200
                ),
                "outcomes": dict(outcomes),
            }
        )
    counts = [r["correct"] for r in out["runs"]]
    out["range"] = [min(counts), max(counts)] if counts else None
    out["flipping_items"] = sorted(i for i, v in per_item.items() if len(set(v)) > 1)
    out["per_category"] = {c: f"{h}/{n}" for c, (h, n) in sorted(cat_hits.items())}
    out["taxonomy"] = {c: taxonomy.get(c, 0) for c in CLASSES}
    out["wrong_item_runs"] = wrong_rows
    (DIR / "score.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    for run in out["runs"]:
        print(
            f"pass {run['pass']}: {run['correct']}/{run['n']} correct; "
            f"{run['correct_without_ambiguous']}/{run['n_without_ambiguous']} without ambiguous; "
            f"median {run['median_s']} s, p95 {run['p95_s']} s; not-200-or-over-120s: "
            f"{run['over_deadline']}"
        )
    print("range:", out["range"], "| flips:", out["flipping_items"])
    print("per category:", out["per_category"])
    print("taxonomy:", out["taxonomy"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
