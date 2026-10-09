"""Build the interpretation gate's pairs, programmatically, from the committed parse sets.

    .venv\\Scripts\\python evals/qa_interp/build_sets.py            # rewrites pairs_v1.jsonl
    .venv\\Scripts\\python evals/qa_interp/build_sets.py --check    # fails if the file is stale

No hand-picking (ADR-089, pre-registered before any live call). Each source item gives two
pairs of (question, parsed request):

- the **correct pair**: the item's labelled *expected* request;
- the **wrong pair**: the same request with exactly one thing changed to a wrong value,
  the operator and the new value chosen by `random.Random(SEED)` over a fixed, sorted
  candidate list, so rebuilding always gives the same file.

Reporting (28 items of `reporting_parse/parse_v4.jsonl`): the operator is one of metric,
dates (both ends shifted by one month), group_by, region, account_name, technician_name. A
mutation never turns an answerable request into one the agent would decline, or the reverse,
except where it must: a request the labels mark as declined (an unsupported metric, an
unsupported area) is mutated into one that looks answerable, which counts as wrong.

Forecast (14 items of `forecast_parse/parse_v1.jsonl`): the operator is slice, horizon or
period; a labelled decline is mutated by dropping its `unsupported` flag.

Output order interleaves each item's correct and wrong pair, so a run stopped part way (a daily
quota) has seen both kinds.
"""

from __future__ import annotations

import argparse
import calendar
import datetime as dt
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
REPORTING_SET = ROOT / "evals" / "reporting_parse" / "parse_v4.jsonl"
FORECAST_SET = ROOT / "evals" / "forecast_parse" / "parse_v1.jsonl"
OUT = HERE / "pairs_v1.jsonl"

#: Fixed before any live call; never changed.
SEED = 20261009
AS_OF = dt.date(2026, 8, 30)

METRICS = (
    "incident_count",
    "incident_rate",
    "sla_compliance",
    "first_time_fix_rate",
    "repeat_visit_drivers",
)
REGIONS = ("northeast", "southeast", "central", "west")
#: Names used only as wrong values; none is the right answer for the item it replaces.
ACCOUNT_POOL = (
    "Bluewater Energy Inc.",
    "Cedar Ridge Retail",
    "Meridian Foods",
    "Northgate Logistics",
    "Summit Distribution",
)
TECHNICIAN_POOL = ("Ben Okafor", "Dave", "Marcus", "Priya", "Sarah")
FORECAST_SLICES = ("total", "inspection", "install", "maintenance", "repair", "upgrade")
HORIZONS = (4, 8, 12, 26)
REPORTING_OPERATORS = ("metric", "dates", "group_by", "region", "account_name", "technician_name")
FORECAST_OPERATORS = ("slice", "horizon", "period")

if str(ROOT / "services" / "agent_qa" / "src") not in sys.path:  # run as a script, no install
    sys.path.insert(0, str(ROOT / "services" / "agent_qa" / "src"))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line]


def add_months(day: dt.date, months: int) -> dt.date:
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    return day.replace(
        year=year, month=month + 1, day=min(day.day, calendar.monthrange(year, month + 1)[1])
    )


def answerable(request) -> bool:
    from agent_qa.reporting import decline_reasons

    return not decline_reasons(request)


def reporting_request(fields: dict):
    from schemas import ReportingRequest

    return ReportingRequest(**fields)


def reporting_candidates(base: dict, operator: str) -> list[dict]:
    """Every value the operator may change the request to, each as the field changes it
    makes. Sorted, so the seeded choice is reproducible."""
    out: list[dict] = []
    if operator == "metric":
        out = [{"metric": m} for m in METRICS if m != base["metric"]]
    elif operator == "dates":
        if base.get("start"):
            start, end = dt.date.fromisoformat(base["start"]), dt.date.fromisoformat(base["end"])
            for shift in (-1, 1):
                out.append(
                    {
                        "start": add_months(start, shift).isoformat(),
                        "end": add_months(end, shift).isoformat(),
                    }
                )
    elif operator == "group_by":
        out = [
            {"group_by": g}
            for g in (
                None,
                "account",
                "region",
                "service_type",
                "technician",
                "incident_type",
                "severity",
            )
            if g != base.get("group_by")
        ]
    elif operator == "region":
        out = [{"region": r} for r in (None, *REGIONS) if r != base.get("region")]
    elif operator == "account_name":
        out = [{"account_name": a} for a in (None, *ACCOUNT_POOL) if a != base.get("account_name")]
    elif operator == "technician_name":
        out = [
            {"technician_name": t}
            for t in (None, *TECHNICIAN_POOL)
            if t != base.get("technician_name")
        ]
    return out


def mutate_reporting(item: dict, rng: random.Random) -> tuple[dict, dict]:
    """(wrong request, mutation record) for one reporting item."""
    base = {**item["expected"]}
    forced = None
    if base.get("metric") == "unsupported":
        forced = "metric"
    elif base.get("region") == "unsupported":
        forced = "region"
    operators = [forced] if forced else list(REPORTING_OPERATORS)
    options: list[tuple[str, dict]] = []
    for operator in operators:
        for change in reporting_candidates(base, operator):
            trial = {**base, **change}
            try:
                request = reporting_request(trial)
            except ValueError:
                continue
            # A wrong pair is always one the agent would answer: an answerable request stays
            # answerable, and a labelled decline is mutated into something that looks answerable.
            if answerable(request):
                options.append((operator, change))
    if not options:
        raise RuntimeError(f"no mutation for {item['id']}")
    # One operator first (uniform over those that have a valid change), then one change.
    by_operator = {}
    for operator, change in options:
        by_operator.setdefault(operator, []).append(change)
    operator = rng.choice(sorted(by_operator))
    change = rng.choice(by_operator[operator])
    return {**base, **change}, {"operator": operator, "change": change}


def forecast_request(fields: dict):
    from schemas import ForecastRequest

    return ForecastRequest(**fields)


def mutate_forecast(item: dict, rng: random.Random) -> tuple[dict, dict]:
    base = {**item["expected"]}
    if base.get("unsupported"):
        change = {"unsupported": None}
        return {**base, **change}, {"operator": "unsupported", "change": change}
    options: list[tuple[str, dict]] = []
    for s in FORECAST_SLICES:
        if s != base["slice"]:
            options.append(("slice", {"slice": s}))
    for h in HORIZONS:
        if h != base.get("horizon_weeks"):
            options.append(
                ("horizon", {"horizon_weeks": h, "period_start": None, "period_end": None})
            )
    if base.get("period_start"):
        start = dt.date.fromisoformat(base["period_start"])
        end = dt.date.fromisoformat(base["period_end"])
        for shift in (-2, 2):
            options.append(
                (
                    "period",
                    {
                        "period_start": add_months(start, shift).isoformat(),
                        "period_end": add_months(end, shift).isoformat(),
                    },
                )
            )
    else:  # a horizon (or nothing) becomes a period: the next calendar quarter
        options.append(
            (
                "period",
                {
                    "horizon_weeks": None,
                    "period_start": "2026-10-01",
                    "period_end": "2026-12-31",
                },
            )
        )
    by_operator = {}
    for operator, change in options:
        try:
            forecast_request({**base, **change})
        except ValueError:
            continue
        by_operator.setdefault(operator, []).append(change)
    operator = rng.choice(sorted(by_operator))
    change = rng.choice(by_operator[operator])
    return {**base, **change}, {"operator": operator, "change": change}


def build() -> list[dict]:
    rng = random.Random(SEED)
    pairs: list[dict] = []
    for domain, path, mutate in (
        ("reporting", REPORTING_SET, mutate_reporting),
        ("forecast", FORECAST_SET, mutate_forecast),
    ):
        for item in read_jsonl(path):
            wrong, mutation = mutate(item, rng)
            common = {"source_id": item["id"], "domain": domain, "question": item["question"]}
            pairs.append(
                {
                    "id": f"{domain[0]}-{item['id']}-ok",
                    **common,
                    "request": item["expected"],
                    "label": "matches",
                    "mutation": None,
                }
            )
            pairs.append(
                {
                    "id": f"{domain[0]}-{item['id']}-bad",
                    **common,
                    "request": wrong,
                    "label": "mismatch",
                    "mutation": mutation,
                }
            )
    return pairs


def render(pairs: list[dict]) -> str:
    return "".join(json.dumps(p, sort_keys=True) + "\n" for p in pairs)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="fail if pairs_v1.jsonl is stale")
    args = ap.parse_args(argv)
    text = render(build())
    if args.check:
        if not OUT.exists() or OUT.read_text("utf-8").replace("\r\n", "\n") != text:
            print("pairs_v1.jsonl is stale: rebuild it", file=sys.stderr)
            return 1
        print("pairs_v1.jsonl is current")
        return 0
    OUT.write_text(text, encoding="utf-8", newline="\n")
    pairs = [json.loads(line) for line in text.splitlines()]
    kinds = {}
    for p in pairs:
        kinds[(p["domain"], p["label"])] = kinds.get((p["domain"], p["label"]), 0) + 1
    print(
        f"wrote {len(pairs)} pairs (seed {SEED}):",
        {f"{d}/{label}": n for (d, label), n in sorted(kinds.items())},
    )
    ops = {}
    for p in pairs:
        if p["mutation"]:
            key = (p["domain"], p["mutation"]["operator"])
            ops[key] = ops.get(key, 0) + 1
    print("mutations:", {f"{d}/{o}": n for (d, o), n in sorted(ops.items())})
    return 0


if __name__ == "__main__":
    sys.exit(main())
