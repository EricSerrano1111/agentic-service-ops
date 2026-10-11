"""Build the interpretation pairs for `interp_fresh_v1` from the labelled `intent` (ADR-094).

    .venv\\Scripts\\python evals/generated/build_pairs.py

The specification is `pairs_plan.md`, committed before this file existed. Nothing here calls a
model or the system; the only database access is a read of the account and technician names as
`app_eval` (for `name_swap`). It prints counts, hashes and reasons, never item text (ADR-030).

Writes:
- `sets/interp_pairs_v1.jsonl`: one correct and one wrong pair per eligible item;
- `pairs_provenance.json`: the name pool's hash, counts per reason and per mutation type, and the
  interpretation set's membership change (IDs only).

Order of work: skim drops (`skim_applied.json`) are already decided; this script decides which
`interp_fresh_v1` items have no documented mapping or no applicable mutation, removes them, and
refills each slot from the reserve by plan.md's rule (same category and area, eligible, rank
order). Whole items only; no question or label is edited.
"""

from __future__ import annotations

import calendar
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SETS = HERE / "sets"
sys.path.insert(0, str(HERE))
for extra in (ROOT / "services" / "agent_qa" / "src",):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import periods  # noqa: E402  (evals/generated/periods.py)
from agent_qa.reporting import decline_reason, last_full_month  # noqa: E402
from schemas import (  # noqa: E402
    DATASET_WINDOW_START,
    ForecastRequest,
    ReportingRequest,
    SentimentRequest,
)

SEED = 20261013
AS_OF = dt.date(2026, 8, 30)
MAX_HORIZON = 26

#: The categories `interp_fresh_v1` draws from (plan.md).
INTERP_CATEGORIES = frozenset(
    {
        "clear_reporting",
        "clear_sentiment",
        "clear_forecast",
        "underspecified",
        "filtered",
        "technician",
    }
)
#: The fixed type order of the round-robin (pairs_plan.md, "Selection").
TYPES = (
    "period_shift",
    "region_change",
    "measure_swap",
    "work_type_change",
    "breakdown_change",
    "filter_drop",
    "horizon_change",
    "name_swap",
)
REGIONS = ("northeast", "southeast", "central", "west")
METRICS = (
    "incident_count",
    "incident_rate",
    "sla_compliance",
    "first_time_fix_rate",
    "repeat_visit_drivers",
)
GROUP_BYS = ("account", "region", "service_type", "technician", "incident_type", "severity")
SLICES = ("total", "inspection", "install", "maintenance", "repair", "upgrade")
SENT_MODES = ((False, False), (True, False), (False, True))  # (want_trend, want_examples)

# --------------------------------------------------------------------------- citations
CITE = {
    "reporting.metric": "intent.measure; ADR-073; data-dictionary §6 repeat-visit drivers",
    "reporting.group_by": "intent.breakdown; ADR-073; §6 incident counts by breakdown; ADR-046",
    "reporting.technician_name": "intent.technician_name; ADR-073 (as written)",
    "reporting.account_name": "intent.account_name; ADR-086 (as written)",
    "reporting.region": "intent.region; ADR-086 (four regions or 'unsupported')",
    "reporting.dates": "intent.period_start/end; ADR-050 (null when none stated)",
    "sentiment.dates": "intent.period_start/end; ADR-068, ADR-050",
    "sentiment.region": "intent.region; ADR-068 (four regions)",
    "sentiment.bucket": "intent.breakdown; §6 sentiment rule 3 (month by default)",
    "sentiment.want_trend": "intent.measure; ADR-068",
    "sentiment.want_examples": "intent.measure, examples_requested; ADR-068",
    "sentiment.example_label": "intent.sentiment_label; §6 sentiment rule 7",
    "sentiment.unsupported": "intent.breakdown; §6 sentiment rule 8",
    "forecast.slice": "intent.work_type; ADR-069 slices; ForecastRequest default total",
    "forecast.horizon_weeks": "intent.period_text/horizon_weeks; ADR-072; ForecastRequest",
    "forecast.period": "intent.period_start/end; ADR-072 (a period maps to ISO weeks)",
    "forecast.unsupported": "intent.region/account/technician/breakdown; ADR-072 declines",
    "forecast.want_history": "no label; ForecastRequest default false (disclosed)",
}
MUTATION_CITE = {
    "period_shift": "pairs_plan.md (b); ADR-050 / ADR-072 period rules",
    "region_change": "pairs_plan.md (b); ADR-086 regions",
    "measure_swap": "pairs_plan.md (b); ADR-073, ADR-068",
    "work_type_change": "pairs_plan.md (b); ADR-069 slices",
    "breakdown_change": "pairs_plan.md (b); ADR-073, §6 sentiment rule 3",
    "filter_drop": "pairs_plan.md (b); ADR-073, ADR-086",
    "horizon_change": "pairs_plan.md (b); ADR-072 horizon cap 26",
    "name_swap": "pairs_plan.md (b); ADR-073, ADR-086",
}


def rank(key: str) -> str:
    return hashlib.sha256(f"{SEED}|{key}".encode()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line]


# --------------------------------------------------------------------------- the mapping


class Ineligible(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _first_monday_after(day: dt.date) -> dt.date:
    return day + dt.timedelta(days=(7 - day.weekday()) % 7 or 7)


def map_intent(intent: dict) -> tuple[str, dict, dict]:
    """(domain, request fields, citations used). Raises Ineligible with the reason."""
    area = intent["area"]
    if intent.get("work_type") is not None and area in ("reporting", "sentiment"):
        raise Ineligible("work_type_filter_no_field")
    if area != "sentiment" and (
        intent.get("sentiment_label") is not None or intent.get("examples_requested")
    ):
        raise Ineligible("examples_on_non_sentiment")
    start, end = intent.get("period_start"), intent.get("period_end")
    stated = bool(intent.get("period_stated"))

    if area == "reporting":
        metric = {"followup_drivers": "repeat_visit_drivers"}.get(
            intent["measure"], intent["measure"]
        )
        bd = intent.get("breakdown")
        group_by = {
            "work_type": "service_type",
            "month": "unsupported",
            "quarter": "unsupported",
        }.get(bd, bd)
        fields = {
            "metric": metric,
            "group_by": group_by,
            "technician_name": intent.get("technician_name"),
            "region": intent.get("region"),
            "account_name": intent.get("account_name"),
            "start": start if stated else None,
            "end": end if stated else None,
        }
        used = {
            k: CITE[f"reporting.{c}"]
            for k, c in (
                ("metric", "metric"),
                ("group_by", "group_by"),
                ("technician_name", "technician_name"),
                ("account_name", "account_name"),
                ("region", "region"),
                ("start", "dates"),
                ("end", "dates"),
            )
        }
        return "reporting", fields, used

    if area == "sentiment":
        if intent.get("region") == "unsupported":
            raise Ineligible("sentiment_region_unsupported")
        bd = intent.get("breakdown")
        if bd == "region":
            raise Ineligible("sentiment_breakdown_region")
        if intent.get("account_name") is not None or intent.get("technician_name") is not None:
            raise Ineligible("sentiment_name_filter")
        measure = intent["measure"]
        want_trend = measure == "sentiment_trend"
        want_examples = measure == "example_comments" or bool(intent.get("examples_requested"))
        label = intent.get("sentiment_label")
        if label is not None and not want_examples:
            raise Ineligible("label_without_examples")
        unsupported = {
            "account": "account",
            "technician": "technician",
            "work_type": "service_type",
            "incident_type": "other",
            "severity": "other",
        }.get(bd)
        fields = {
            "start": start if stated else None,
            "end": end if stated else None,
            "region": intent.get("region"),
            "bucket": bd if bd in ("month", "quarter") else "month",
            "want_trend": want_trend,
            "want_examples": want_examples,
            "example_label": label if want_examples else None,
            "unsupported": unsupported,
        }
        used = {
            k: CITE[f"sentiment.{c}"]
            for k, c in (
                ("start", "dates"),
                ("end", "dates"),
                ("region", "region"),
                ("bucket", "bucket"),
                ("want_trend", "want_trend"),
                ("want_examples", "want_examples"),
                ("example_label", "example_label"),
                ("unsupported", "unsupported"),
            )
        }
        return "sentiment", fields, used

    if area == "forecast":
        bd = intent.get("breakdown")
        reasons = set()
        if intent.get("region") is not None:
            reasons.add("region")
        if intent.get("account_name") is not None:
            reasons.add("account")
        if intent.get("technician_name") is not None:
            reasons.add("technician")
        slice_ = intent.get("work_type") or "total"
        if bd in ("region", "account", "technician"):
            reasons.add(bd)
        elif bd == "work_type":
            if intent.get("work_type") is None:
                raise Ineligible("forecast_breakdown_undocumented")
        elif bd is not None:
            raise Ineligible("forecast_breakdown_undocumented")
        if len(reasons) > 1:
            raise Ineligible("forecast_multiple_unsupported")
        horizon, p_start, p_end = None, None, None
        if stated:
            res = periods.resolve_period(intent.get("period_text"), AS_OF, "forecast")
            if res is not None and res.horizon_weeks is not None:
                horizon = res.horizon_weeks
            else:
                p_start, p_end = start, end
        else:
            horizon = intent.get("horizon_weeks")
        if p_start is not None and dt.date.fromisoformat(p_start) <= AS_OF:
            raise Ineligible("forecast_past_period")
        fields = {
            "slice": slice_,
            "horizon_weeks": horizon,
            "period_start": p_start,
            "period_end": p_end,
            "want_history": False,
            "unsupported": next(iter(reasons)) if reasons else None,
        }
        used = {
            "slice": CITE["forecast.slice"],
            "horizon_weeks": CITE["forecast.horizon_weeks"],
            "period_start": CITE["forecast.period"],
            "period_end": CITE["forecast.period"],
            "want_history": CITE["forecast.want_history"],
            "unsupported": CITE["forecast.unsupported"],
        }
        return "forecast", fields, used
    raise Ineligible("unknown_area")


# --------------------------------------------------------------------------- answers


def _schema(domain: str):
    return {
        "reporting": ReportingRequest,
        "sentiment": SentimentRequest,
        "forecast": ForecastRequest,
    }[domain]


def build_request(domain: str, fields: dict):
    try:
        return _schema(domain)(**fields)
    except ValueError:
        return None


def declined(domain: str, req) -> str | None:
    if domain == "reporting":
        return decline_reason(req)
    return req.unsupported


def _d(value: str | None) -> dt.date | None:
    return dt.date.fromisoformat(value) if isinstance(value, str) else value


def answer_key(domain: str, req) -> tuple:
    """The request normalised through the specialist's documented defaults (pairs_plan.md)."""
    reason = declined(domain, req)
    if reason:
        return ("decline", reason)
    if domain == "reporting":
        if req.start is None:
            start, end = last_full_month(AS_OF)
        else:
            start, end = req.start, req.end
        group = req.group_by
        if group is None and req.metric == "repeat_visit_drivers":
            group = "incident_type"
        return (
            req.metric,
            group,
            req.technician_name,
            req.region,
            req.account_name,
            start.isoformat(),
            end.isoformat(),
        )
    if domain == "sentiment":
        bucket: str | None = req.bucket
        if req.start is None:
            if req.want_trend:
                month = AS_OF.year * 12 + AS_OF.month - 1 - 5
                start = dt.date(month // 12, month % 12 + 1, 1)
                end = AS_OF
                bucket = None  # monthly whatever was asked (ADR-068)
            else:
                start, end = last_full_month(AS_OF)
        else:
            start, end = req.start, req.end
        return (
            req.region,
            start.isoformat(),
            end.isoformat(),
            bucket,
            req.want_trend,
            req.want_examples,
            req.example_label if req.want_examples else None,
        )
    first = _first_monday_after(AS_OF)
    cap = first + dt.timedelta(weeks=MAX_HORIZON - 1)
    if req.horizon_weeks is not None:
        weeks = [first + dt.timedelta(weeks=k) for k in range(min(req.horizon_weeks, MAX_HORIZON))]
        covers: tuple = tuple(w.isoformat() for w in weeks)
    elif req.period_start is not None:
        mondays = []
        day = req.period_start + dt.timedelta(days=(7 - req.period_start.weekday()) % 7)
        while day <= req.period_end:
            if day <= cap:
                mondays.append(day.isoformat())
            day += dt.timedelta(weeks=1)
        covers = tuple(mondays) or ("beyond_cap", req.period_start.isoformat())
    else:
        covers = ("default",)
    return (req.slice, covers, req.want_history)


# --------------------------------------------------------------------------- mutations


def _shift_period(start: dt.date, end: dt.date) -> tuple[dt.date, dt.date]:
    """Back by the period's own length (pairs_plan.md): whole month, whole quarter, else days."""

    def month_end(y: int, m: int) -> dt.date:
        return dt.date(y, m, calendar.monthrange(y, m)[1])

    if start.day == 1 and end == month_end(end.year, end.month):
        months = (end.year * 12 + end.month) - (start.year * 12 + start.month) + 1
        if months in (1, 3) and (months == 1 or (start.month - 1) % 3 == 0):
            idx = start.year * 12 + start.month - 1 - months
            y, m = divmod(idx, 12)
            ns = dt.date(y, m + 1, 1)
            ei = idx + months - 1
            ey, em = divmod(ei, 12)
            return ns, month_end(ey, em + 1)
    length = (end - start).days + 1
    delta = dt.timedelta(days=length)
    return start - delta, end - delta


def candidates(domain: str, base: dict, names: dict) -> dict[str, list[dict]]:
    """Every change each mutation type could make, as field changes (before validation)."""
    out: dict[str, list[dict]] = {t: [] for t in TYPES}
    if domain in ("reporting", "sentiment"):
        if base.get("start"):
            ns, ne = _shift_period(_d(base["start"]), _d(base["end"]))
            if ns >= DATASET_WINDOW_START:
                out["period_shift"].append({"start": ns.isoformat(), "end": ne.isoformat()})
        out["region_change"] = [{"region": r} for r in REGIONS if r != base.get("region")]
        out["filter_drop"] = [
            {f: None}
            for f in (
                ("region", "account_name", "technician_name")
                if domain == "reporting"
                else ("region",)
            )
            if base.get(f) is not None
        ]
    if domain == "reporting":
        out["measure_swap"] = [{"metric": m} for m in METRICS if m != base["metric"]]
        out["breakdown_change"] = [{"group_by": g} for g in GROUP_BYS if g != base.get("group_by")]
        for field, pool in (
            ("account_name", names["accounts"]),
            ("technician_name", names["technicians"]),
        ):
            current = base.get(field)
            if current:
                out["name_swap"] += [
                    {field: n} for n in pool if n.casefold() != str(current).casefold()
                ]
    elif domain == "sentiment":
        current = (base["want_trend"], base["want_examples"])
        out["measure_swap"] = [
            {"want_trend": t, "want_examples": e, "example_label": None}
            for t, e in SENT_MODES
            if (t, e) != current
        ]
        out["breakdown_change"] = [{"bucket": "quarter" if base["bucket"] == "month" else "month"}]
    else:
        if base.get("period_start"):
            ns, ne = _shift_period(_d(base["period_start"]), _d(base["period_end"]))
            if ns > AS_OF:
                out["period_shift"].append(
                    {"period_start": ns.isoformat(), "period_end": ne.isoformat()}
                )
        out["work_type_change"] = [{"slice": s} for s in SLICES if s != base["slice"]]
        h = base.get("horizon_weeks")
        if h is not None:
            out["horizon_change"] = [
                {"horizon_weeks": n} for n in range(1, MAX_HORIZON + 1) if abs(n - h) >= 4
            ]
    return out


def applicable(domain: str, base: dict, names: dict) -> dict[str, list[dict]]:
    """Per type, the changes that satisfy the three conditions of pairs_plan.md (b)."""
    base_req = build_request(domain, base)
    if base_req is None:
        return {t: [] for t in TYPES}
    base_key = answer_key(domain, base_req)
    out: dict[str, list[dict]] = {}
    for mtype, changes in candidates(domain, base, names).items():
        ok = []
        for change in changes:
            fields = {**base, **change}
            req = build_request(domain, fields)
            if req is None or declined(domain, req):
                continue
            if answer_key(domain, req) == base_key:
                continue
            ok.append(change)
        out[mtype] = ok
    return out


# --------------------------------------------------------------------------- evaluation


def evaluate(row: dict, names: dict) -> dict:
    """The mapping and mutation check for one pool row."""
    intent = row["item"]["intent"]
    if not row.get("interp_eligible"):
        return {"eligible": False, "reason": "earlier_ineligible"}
    try:
        domain, fields, used = map_intent(intent)
    except Ineligible as exc:
        return {"eligible": False, "reason": exc.reason}
    if build_request(domain, fields) is None:
        return {"eligible": False, "reason": "request_invalid"}
    app = applicable(domain, fields, names)
    if not any(app.values()):
        return {"eligible": False, "reason": "no_applicable_mutation"}
    return {"eligible": True, "domain": domain, "fields": fields, "used": used, "applicable": app}


def draw(uid: str, mtype: str, changes: list[dict]) -> dict:
    return min(
        changes,
        key=lambda c: hashlib.sha256(
            f"{SEED}|{uid}|{mtype}|{json.dumps(c, sort_keys=True)}".encode()
        ).hexdigest(),
    )


def round_robin(items: list[dict]) -> dict[str, tuple[str, dict]]:
    """uid -> (type, change). Pairs_plan.md, "Amendment": the most constrained items choose
    first, each takes the applicable type with the fewest pairs so far, ties by a cyclic
    pointer over the fixed type order."""
    pointer = 0
    counts: Counter = Counter()
    chosen: dict[str, tuple[str, dict]] = {}

    def order_key(row: dict) -> tuple:
        n = sum(1 for t in TYPES if row["_eval"]["applicable"][t])
        return (n, rank(f"item:{row['uid']}"))

    for row in sorted(items, key=order_key):
        app = row["_eval"]["applicable"]
        options = [t for t in TYPES if app[t]]
        fewest = min(counts[t] for t in options)
        tied = {t for t in options if counts[t] == fewest}
        for step in range(len(TYPES)):
            mtype = TYPES[(pointer + step) % len(TYPES)]
            if mtype in tied:
                break
        chosen[row["uid"]] = (mtype, draw(row["uid"], mtype, app[mtype]))
        counts[mtype] += 1
        pointer = (TYPES.index(mtype) + 1) % len(TYPES)
    return chosen


# --------------------------------------------------------------------------- database


def real_names() -> dict:
    import psycopg

    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    e = os.environ
    with psycopg.connect(
        host=e["POSTGRES_HOST"],
        port=e["POSTGRES_PORT"],
        dbname=e["POSTGRES_DB"],
        user=e["DB_ROLE_EVAL_USER"],
        password=e["DB_ROLE_EVAL_PASSWORD"],
    ) as conn:
        accounts = sorted(r[0] for r in conn.execute("SELECT account_name FROM accounts"))
        techs = sorted(r[0] for r in conn.execute("SELECT full_name FROM technicians"))
    return {"accounts": accounts, "technicians": techs}


def make_pair(row, ev, question, role, fields, mutation, cites) -> dict:
    req = _schema(ev["domain"])(**fields)
    return {
        "id": f"{ev['domain'][0]}-{row['uid']}-{'ok' if role == 'correct' else 'bad'}",
        "source_id": row["uid"],
        "domain": ev["domain"],
        "question": question,
        "request": json.loads(req.model_dump_json()),
        "role": role,
        "label": "matches" if role == "correct" else "mismatch",
        "mutation": mutation,
        "citations": cites,
    }


# --------------------------------------------------------------------------- main

_INVENTED = re.compile(
    r"invent|fictional|made[- ]up|not in the (list|data)|isn'?t in the|not a (real|known)|"
    r"non-?existent|doesn'?t exist|does not exist|unknown (account|technician|name)|no such",
    re.I,
)


def main() -> int:
    names = real_names()
    names_hash = sha256_text(json.dumps(names, sort_keys=True))
    skim = json.loads((SETS / "skim_applied.json").read_text("utf-8"))
    pool = read_jsonl(HERE / "filtered" / "pool.jsonl")
    draft = read_jsonl(SETS / "interp_fresh_v1.draft.jsonl")
    reserve = sorted(read_jsonl(SETS / "reserve.jsonl"), key=lambda r: r["rank"])
    taken = set(skim["reserve_used"]) | set(skim["reserve_removed_n"])
    in_other_sets = taken

    # Pool-level report counts (not selection).
    date_reasons = Counter()
    pool_new = Counter()
    for r in pool:
        if r["category"] not in INTERP_CATEGORIES:
            continue
        dc = [x for x in r["ineligible_reasons"] if x.startswith("date_check")]
        if dc:
            date_reasons[dc[0]] += 1
        elif r["interp_eligible"]:
            ev = evaluate(r, names)
            if not ev["eligible"]:
                pool_new[ev["reason"]] += 1

    # The interpretation set: evaluate, drop what has no mapping or no mutation, refill.
    kept, removed = [], []
    for r in draft:
        ev = evaluate(r, names)
        if ev["eligible"]:
            kept.append({**r, "_eval": ev})
        else:
            removed.append((r, ev["reason"]))
    refill = []
    used_ids = {k["uid"] for k in kept} | in_other_sets
    unfilled = []
    for gone, _reason in removed:
        pick = None
        for cand in reserve:
            if cand["uid"] in used_ids or not cand["interp_eligible"]:
                continue
            if cand["category"] != gone["category"] or cand["area"] != gone["area"]:
                continue
            ev = evaluate(cand, names)
            if ev["eligible"]:
                pick = {**cand, "_eval": ev}
                break
        if pick is None:
            unfilled.append(gone["uid"])
            continue
        used_ids.add(pick["uid"])
        kept.append(pick)
        refill.append({"replaces": gone["uid"], "uid": pick["uid"]})

    chosen = round_robin(kept)
    order = sorted(kept, key=lambda r: rank(f"item:{r['uid']}"))
    lines = []
    type_counts: Counter = Counter()
    domain_counts: Counter = Counter()
    for r in order:
        ev = r["_eval"]
        mtype, change = chosen[r["uid"]]
        type_counts[mtype] += 1
        domain_counts[ev["domain"]] += 1
        base_fields = ev["fields"]
        wrong_fields = {**base_fields, **change}
        question = r["item"]["question"]

        lines.append(make_pair(r, ev, question, "correct", base_fields, None, ev["used"]))
        lines.append(
            make_pair(
                r,
                ev,
                question,
                "wrong",
                wrong_fields,
                {"operator": mtype, "change": change},
                {
                    **{k: v for k, v in ev["used"].items() if k not in change},
                    "mutation": MUTATION_CITE[mtype],
                },
            )
        )
    text = "".join(json.dumps(p, sort_keys=True, ensure_ascii=False) + "\n" for p in lines)
    (SETS / "interp_pairs_v1.jsonl").write_bytes(text.encode("utf-8"))

    # Report-only: not-found name collisions (no removal).
    real_acc = {n.casefold() for n in names["accounts"]}
    real_tech = {n.casefold() for n in names["technicians"]}
    invented = collide = 0
    for r in pool:
        it = r["item"]
        intent = it.get("intent") or {}
        if not _INVENTED.search(it.get("rationale", "")):
            continue
        invented += 1
        acc, tec = intent.get("account_name"), intent.get("technician_name")
        if (acc and acc.casefold() in real_acc) or (tec and tec.casefold() in real_tech):
            collide += 1

    plan_commit = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", "evals/generated/pairs_plan.md"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout.strip()
    provenance = {
        "seed": SEED,
        "as_of": AS_OF.isoformat(),
        "plan_commit": plan_commit,
        "names": {
            "source": "accounts.account_name, technicians.full_name as app_eval",
            "sha256_of_sorted_lists": names_hash,
            "accounts": len(names["accounts"]),
            "technicians": len(names["technicians"]),
        },
        "pairs": {
            "items": len(order),
            "correct": sum(p["role"] == "correct" for p in lines),
            "wrong": sum(p["role"] == "wrong" for p in lines),
            "by_domain": dict(sorted(domain_counts.items())),
            "wrong_by_mutation": {t: type_counts.get(t, 0) for t in TYPES},
        },
        "interp_set": {
            "draft_size": len(draft),
            "removed": [{"uid": g["uid"], "reason": why} for g, why in removed],
            "refill": refill,
            "unfilled_slots": unfilled,
            "final_ids": [r["uid"] for r in kept],
            "final_size": len(kept),
        },
        "report_only": {
            "date_check_exclusions_in_pool": sum(date_reasons.values()),
            "date_check_by_reason": dict(date_reasons),
            "pool_newly_ineligible_by_reason": dict(pool_new),
            "invented_name_rationales": invented,
            "invented_name_collisions": collide,
        },
    }
    (HERE / "pairs_provenance.json").write_bytes(
        (json.dumps(provenance, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )
    print(json.dumps({k: v for k, v in provenance.items() if k != "interp_set"}, indent=2))
    print(
        "interp_set:",
        {
            k: (v if not isinstance(v, list) else len(v))
            for k, v in provenance["interp_set"].items()
        },
    )
    print("removed reasons:", dict(Counter(why for _g, why in removed)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
