"""The fault catalogue's mutations (catalogue_v1.yaml names them; this file does them).

Each fault has an `applies` predicate on the base answer's attributes only, and an `apply`
that returns the case's `Prepared` request (text, data part, decline code, parsed request) or
raises `Skip` with a reason when the mutation cannot be made on that base answer (it would
change nothing, or the data has no such rows). A mutation that changes the data part
re-renders the text through the agent's own renderer so the two stay consistent; text-only
faults change the text alone.

The pre-registered rule for rating contradictions (ADR-087: n >= 20 and one-sided exact
binomial P(X >= x | n, p0 = 0.01) < 0.01) is `rating_rule_fails` below, written here from the
ADR, not taken from QA's code.

Frozen with catalogue_v1.yaml: nothing in this file changes after the first measurement run
except bug fixes to the plumbing, each listed in the results.
"""

from __future__ import annotations

import calendar
import datetime as dt
import random
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from agent_forecast.render import YEAR_END
from agent_forecast.render import render_answer as render_forecast
from agent_reporting.executor import unsupported_reason
from agent_reporting.render import TOO_FEW
from agent_reporting.render import render_answer as render_reporting
from agent_sentiment.render import render_answer as render_sentiment
from schemas import (
    DATASET_WINDOW_END,
    DATASET_WINDOW_START,
    ForecastAnswer,
    ReportingAnswer,
    ReportingRequest,
    SentimentAnswer,
    rate_string,
)
from scipy.stats import binom

MIN_GROUP = 20
REGIONS = ("northeast", "southeast", "central", "west")
SLICES = ("total", "inspection", "install", "maintenance", "repair", "upgrade")
LABELS = ("positive", "negative", "mixed", "neutral")
P0 = 0.01
ALPHA = 0.01
RATING_MIN_N = 20


class Skip(Exception):  # noqa: N818 - control flow, not an error
    """The mutation does not apply to this base answer; the message says why."""


@dataclass
class Base:
    base_id: str
    agent: str
    item_id: str
    source: str  # parse_set | owner
    category: str
    question: str
    request: dict
    kind: str  # answer | decline
    error_code: str | None
    text: str
    answer: dict | None
    parsed_request: dict | None

    @property
    def figures(self) -> dict:
        return (self.answer or {}).get("figures", {})

    @property
    def metric(self) -> str | None:
        return self.request.get("metric")


@dataclass
class Prepared:
    text: str
    answer: dict | None
    kind: str = "answer"
    error_code: str | None = None
    parsed_request: dict | None = None
    note: dict = field(default_factory=dict)
    prediction: dict | None = None


@dataclass
class Ctx:
    stack: Any
    rng: random.Random
    conn: Any = None  # the open transaction's connection, for database faults
    source: Any = None  # QA's source for this case (the transaction's, or the normal one)


@dataclass(frozen=True)
class Fault:
    id: str
    agent: str
    applies: Callable[[Base], bool]
    apply: Callable[[Base, Ctx], Awaitable[Prepared]]
    needs_db: bool = False


# --------------------------------------------------------------------------- helpers


def rating_rule_fails(n: int, x: int) -> bool:
    """ADR-087, written out: the cross-check fails when n >= 20 and P(X >= x | n, 0.01) < 0.01."""
    return n >= RATING_MIN_N and x > 0 and float(binom.sf(x - 1, n, P0)) < ALPHA


def add_months(d: dt.date, k: int) -> dt.date:
    index = d.year * 12 + (d.month - 1) + k
    year, month = divmod(index, 12)
    month += 1
    last = calendar.monthrange(year, month)[1]
    was_last = d.day == calendar.monthrange(d.year, d.month)[1]
    return dt.date(year, month, last if was_last else min(d.day, last))


def shifted_range(
    start: dt.date, end: dt.date, *, historical: bool = True
) -> tuple[dt.date, dt.date]:
    """The same range one month later (one earlier when that would pass the dataset window; a
    forecast period is in the future and always moves later)."""
    for k in (1, -1):
        s, e = add_months(start, k), add_months(end, k)
        if not historical or (s >= DATASET_WINDOW_START and e <= DATASET_WINDOW_END):
            return s, e
    raise Skip("no month-shifted range fits the dataset window")


def valid(model, data: dict):
    try:
        return model.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        raise Skip(f"the mutated data part is not schema-valid ({type(exc).__name__})") from exc


def last_digit(number: str) -> str:
    return number[:-1] + str((int(number[-1]) + 1) % 10)


def bump_in_text(text: str, token: str, replacement: str) -> str:
    pattern = re.compile(r"(?<![\d.,])" + re.escape(token) + r"(?!\d|[.,]\d)")
    if not pattern.search(text):
        raise Skip("the figure is not in the text in a form this fault changes")
    return pattern.sub(replacement, text, count=1)


def percent(rate: str) -> str:
    return f"{Decimal(rate) * 100:.2f}%"


def default_previous_month(as_of: dt.date) -> tuple[dt.date, dt.date]:
    end = as_of.replace(day=1) - dt.timedelta(days=1)
    return end.replace(day=1), end


def rep(base: Base) -> ReportingAnswer:
    return ReportingAnswer.model_validate(base.answer)


def reporting_prepared(base: Base, data: dict, **note) -> Prepared:
    answer = valid(ReportingAnswer, data)
    return Prepared(
        render_reporting(answer, MIN_GROUP), answer.model_dump(mode="json"), note=note or {}
    )


def is_answer(agent: str):
    return lambda b: b.agent == agent and b.kind == "answer"


def is_decline(agent: str):
    return lambda b: b.agent == agent and b.kind == "decline"


# --------------------------------------------------------------------------- reporting


def _is_rate(b: Base) -> bool:
    return b.metric in ("incident_rate", "sla_compliance", "first_time_fix_rate")


def _scale(metric: str) -> int:
    return 100 if metric == "incident_rate" else 1


async def r01_count_off_by_one(b: Base, ctx: Ctx) -> Prepared:
    d = rep(b).model_dump(mode="json")
    f = d["figures"]
    if b.metric == "incident_count":
        f["incident_count"] += 1
        f["by_severity"]["medium"] += 1
        if f["groups"] and not f["truncated"]:
            f["groups"][0]["count"] += 1
    elif _is_rate(b):
        f["numerator"] += 1
        f["rate"] = rate_string(f["numerator"], f["denominator"], _scale(b.metric))
    else:  # repeat drivers
        o = f["overall"]
        o["repeated"] += 1
        o["rate"] = rate_string(o["repeated"], o["jobs"])
    return reporting_prepared(b, d)


async def r02_rate_last_digit(b: Base, ctx: Ctx) -> Prepared:
    d = rep(b).model_dump(mode="json")
    f = d["figures"]
    holder = f["overall"] if b.metric == "repeat_visit_drivers" else f
    if holder["rate"] is None:
        raise Skip("the answer has no rate")
    holder["rate"] = last_digit(holder["rate"])
    return reporting_prepared(b, d)


async def r03_denominator_off_by_one(b: Base, ctx: Ctx) -> Prepared:
    d = rep(b).model_dump(mode="json")
    f = d["figures"]
    if b.metric == "repeat_visit_drivers":
        o = f["overall"]
        o["jobs"] += 1
        o["rate"] = rate_string(o["repeated"], o["jobs"])
    else:
        f["denominator"] += 1
        f["rate"] = rate_string(f["numerator"], f["denominator"], _scale(b.metric))
    return reporting_prepared(b, d)


def _grouped(b: Base) -> bool:
    return b.kind == "answer" and bool(b.figures.get("groups"))


def _with_groups(b: Base, minimum: int = 1) -> dict:
    d = rep(b).model_dump(mode="json")
    if len(d["figures"]["groups"]) < minimum:
        raise Skip(f"fewer than {minimum} groups")
    return d


async def r04_group_dropped(b: Base, ctx: Ctx) -> Prepared:
    d = _with_groups(b)
    d["figures"]["groups"].pop()
    d["figures"]["truncated"] = True  # group_count is unchanged, so the cut is flagged
    return reporting_prepared(b, d)


async def r05_order_swapped(b: Base, ctx: Ctx) -> Prepared:
    d = _with_groups(b, 2)
    g = d["figures"]["groups"]
    g[0], g[1] = g[1], g[0]
    return reporting_prepared(b, d)


async def r06_group_count_wrong(b: Base, ctx: Ctx) -> Prepared:
    d = _with_groups(b)
    d["figures"]["group_count"] = (d["figures"]["group_count"] or 0) + 1
    d["figures"]["truncated"] = True
    return reporting_prepared(b, d)


async def r07_too_few_flag_flipped(b: Base, ctx: Ctx) -> Prepared:
    d = _with_groups(b)
    for i, g in enumerate(d["figures"]["groups"]):
        candidate = rep(b).model_dump(mode="json")
        flipped = candidate["figures"]["groups"][i]
        flipped["compared"] = not g["compared"]
        if not flipped["compared"]:
            flipped["stands_out"] = False
        try:
            return reporting_prepared(b, candidate, flipped_group=g["group"])
        except Skip:
            continue
    raise Skip("no group's flag can be flipped and stay schema-valid")


def _has_filter(b: Base) -> bool:
    r = b.request
    return b.kind == "answer" and bool(
        r.get("technician_name") or r.get("account_name") or r.get("region") in REGIONS
    )


async def r08_filter_dropped(b: Base, ctx: Ctx) -> Prepared:
    unfiltered = dict(b.request, technician_name=None, account_name=None, region=None)
    reply = await ctx.stack.ask("reporting", unfiltered)
    if reply.kind != "answer":
        raise Skip("the unfiltered question was not answered")
    d = rep(b).model_dump(mode="json")
    other = reply.answer["figures"]
    labels = ("technician_id", "technician_name", "region", "account_id", "account_name")
    figures = {**other, **{k: d["figures"].get(k) for k in labels}}
    if figures == d["figures"]:
        raise Skip("the unfiltered figures equal the filtered ones")
    d["figures"] = figures
    return reporting_prepared(b, d)


async def r09_range_shifted_in_data_only(b: Base, ctx: Ctx) -> Prepared:
    a = rep(b)
    s, e = shifted_range(a.start, a.end)
    reply = await ctx.stack.ask(
        "reporting", dict(b.request, start=s.isoformat(), end=e.isoformat())
    )
    if reply.kind != "answer":
        raise Skip("the shifted range was not answered")
    d = a.model_dump(mode="json")
    d["start"], d["end"] = s.isoformat(), e.isoformat()
    d["figures"] = reply.answer["figures"]
    answer = valid(ReportingAnswer, d)
    return Prepared(b.text, answer.model_dump(mode="json"), note={"shifted_to": [str(s), str(e)]})


async def r10_text_figure_differs(b: Base, ctx: Ctx) -> Prepared:
    f = rep(b).figures
    if b.metric == "incident_count":
        text = bump_in_text(b.text, f"{f.incident_count:,}", f"{f.incident_count + 1:,}")
    elif b.metric == "repeat_visit_drivers":
        n = f.overall.repeated
        text = bump_in_text(b.text, f"{n:,}", f"{n + 1:,}")
    elif f.rate is None:
        raise Skip("the answer has no rate")
    elif b.metric == "incident_rate":
        text = bump_in_text(b.text, f.rate, last_digit(f.rate))
    else:
        text = bump_in_text(b.text, percent(f.rate), percent(last_digit(f.rate)))
    return Prepared(text, b.answer)


async def r11_decline_carries_a_figure(b: Base, ctx: Ctx) -> Prepared:
    return Prepared(
        b.text + " There were 4,821 incidents in that period.",
        None,
        "decline",
        b.error_code,
        b.parsed_request,
    )


_CANNED = {
    "unsupported_metric": dict(metric="unsupported"),
    "unsupported_breakdown": dict(metric="incident_count", group_by="unsupported"),
    "breakdown_not_offered": dict(metric="incident_rate", group_by="incident_type"),
    "unsupported_area": dict(metric="incident_count", region="unsupported"),
    "repeat_region_or_account": dict(metric="repeat_visit_drivers", region="west"),
    "region_same_dimension": dict(metric="incident_count", region="west", group_by="region"),
    "account_same_dimension": dict(
        metric="incident_count", account_name="Acme", group_by="account"
    ),
    "technician_breakdown": dict(
        metric="incident_count", technician_name="Dave", group_by="region"
    ),
    "repeat_technician": dict(metric="repeat_visit_drivers", technician_name="Dave"),
}


async def r12_decline_states_the_wrong_reason(b: Base, ctx: Ctx) -> Prepared:
    for _name, fields in _CANNED.items():
        other = unsupported_reason(ReportingRequest(**fields))
        if other and other != b.text:
            return Prepared(other, None, "decline", b.error_code, b.parsed_request)
    raise Skip("no other reason text")


def _p_changed(p: float) -> float:
    q = round(1 - p, 6)
    return q if abs(q - p) > 0.05 else min(1.0, round(p + 0.2, 6))


async def r13_p_value_changed(b: Base, ctx: Ctx) -> Prepared:
    d = _with_groups(b)
    for g in d["figures"]["groups"]:
        if g["p_value"] is not None:
            g["p_value"] = _p_changed(g["p_value"])
            return reporting_prepared(b, d)
    raise Skip("no group has a p-value")


async def r14_standout_flipped(b: Base, ctx: Ctx) -> Prepared:
    d = _with_groups(b)
    for g in d["figures"]["groups"]:
        if g["compared"]:
            g["stands_out"] = not g["stands_out"]
            return reporting_prepared(b, d)
    raise Skip("no compared group")


# --------------------------------------------------------------------------- forecast


def fc(b: Base) -> ForecastAnswer:
    return ForecastAnswer.model_validate(b.answer)


def forecast_prepared(data: dict, *, check: bool = True, **note) -> Prepared:
    if check:
        answer = valid(ForecastAnswer, data)
        return Prepared(render_forecast(answer), answer.model_dump(mode="json"), note=note)
    # a shape the shared contract itself rejects: render from the unmutated answer's fields
    return Prepared("", data, note=note)


async def f01_numbers_for_an_unserved_band(b: Base, ctx: Ctx) -> Prepared:
    d = fc(b).model_dump(mode="json")
    target = next((w for w in d["weeks"] if not w["served"]), None)
    if target is None:
        raise Skip("every shown week is served")
    for w in d["weeks"]:
        if w["band"] == target["band"]:
            w.update(served=True, point=1000.0, lo80=800.0, hi80=1200.0, lo95=700.0, hi95=1300.0)
    d["bands"][target["band"]]["served"] = True
    return forecast_prepared(d)


async def f02_shown_error_differs(b: Base, ctx: Ctx) -> Prepared:
    d = fc(b).model_dump(mode="json")
    if not d["bands"]:
        raise Skip("no band is shown")
    band = next(iter(d["bands"]))
    d["bands"][band]["shown_error"] = round(d["bands"][band]["shown_error"] + 1.0, 6)
    return forecast_prepared(d)


async def f03_interval_misses_its_point(b: Base, ctx: Ctx) -> Prepared:
    d = fc(b).model_dump(mode="json")
    served = next((w for w in d["weeks"] if w["served"]), None)
    if served is None:
        raise Skip("no served week")
    served["lo80"] = served["point"] + 1.0
    served["hi80"] = max(served["hi80"], served["lo80"] + 1.0)
    return forecast_prepared(d)


async def f04_total_is_not_the_sum(b: Base, ctx: Ctx) -> Prepared:
    a = fc(b)
    if a.period_total is None:
        raise Skip("no period total")
    # The shared contract rejects this shape, so QA can only meet it as a malformed answer;
    # the data part is built without the validator and the text rendered from it.
    lying = a.model_copy(update={"period_total": a.period_total + 1.0})
    return Prepared(
        render_forecast(lying), lying.model_dump(mode="json"), note={"schema_rejects": True}
    )


async def f05_horizon_over_26_weeks(b: Base, ctx: Ctx) -> Prepared:
    d = fc(b).model_dump(mode="json")
    if not d["beyond_horizon_weeks"]:
        raise Skip("no requested week lies beyond the horizon")
    d["beyond_horizon_weeks"] = 0
    return forecast_prepared(d)


async def f06_history_week_changed(b: Base, ctx: Ctx) -> Prepared:
    d = fc(b).model_dump(mode="json")
    if not d["history"]:
        raise Skip("no history shown")
    d["history"][-1]["count"] += 1
    return forecast_prepared(d)


async def f07_year_end_caveat_removed(b: Base, ctx: Ctx) -> Prepared:
    if YEAR_END not in b.text:
        raise Skip("the text carries no year-end caveat")
    return Prepared(b.text.replace(YEAR_END, "").replace("\n\n", "\n").strip(), b.answer)


async def f08_text_figure_differs(b: Base, ctx: Ctx) -> Prepared:
    a = fc(b)
    served = next((w for w in a.weeks if w.served), None)
    if served is None:
        raise Skip("no served week")
    n = round(served.point)
    text = bump_in_text(b.text, f"about {n:,} requests", f"about {n + 1:,} requests")
    return Prepared(text, b.answer)


# --------------------------------------------------------------------------- sentiment


def sent(b: Base) -> SentimentAnswer:
    return SentimentAnswer.model_validate(b.answer)


def sentiment_prepared(data: dict, **note) -> Prepared:
    answer = valid(SentimentAnswer, data)
    return Prepared(render_sentiment(answer), answer.model_dump(mode="json"), note=note)


async def s01_label_count_changed(b: Base, ctx: Ctx) -> Prepared:
    d = sent(b).model_dump(mode="json")
    label = next((k for k, v in d["summary"]["counts"].items() if v > 0), None)
    if label is None:
        raise Skip("nothing scored")
    d["summary"]["counts"][label] += 1
    return sentiment_prepared(d)


async def s02_share_changed(b: Base, ctx: Ctx) -> Prepared:
    d = sent(b).model_dump(mode="json")
    label = next((k for k, v in d["summary"]["shares"].items() if v is not None), None)
    if label is None:
        raise Skip("no shares")
    d["summary"]["shares"][label] = last_digit(d["summary"]["shares"][label])
    return sentiment_prepared(d)


async def s03_flagged_count_changed(b: Base, ctx: Ctx) -> Prepared:
    d = sent(b).model_dump(mode="json")
    d["summary"]["flagged_count"] += 1
    return sentiment_prepared(d)


def _window(a: SentimentAnswer):
    lo = dt.datetime.combine(a.start, dt.time.min, dt.UTC)
    hi = dt.datetime.combine(a.end + dt.timedelta(days=1), dt.time.min, dt.UTC)
    return lo, hi


_SET = (
    "FROM sentiment_predictions p"
    " JOIN service_feedback f ON f.feedback_id = p.feedback_id"
    " JOIN service_requests r ON r.request_id = f.request_id"
    " JOIN locations l ON l.location_id = r.location_id"
    " WHERE p.model_version = %(v)s AND f.feedback_text IS NOT NULL"
    " AND f.submitted_at >= %(lo)s AND f.submitted_at < %(hi)s"
)


def _params(ctx: Ctx, a: SentimentAnswer, **extra) -> dict:
    lo, hi = _window(a)
    return {"v": ctx.stack.sentiment_manifest.version, "lo": lo, "hi": hi, **extra}


def _where_region(a: SentimentAnswer, params: dict) -> str:
    if a.request.region is not None:
        params["region"] = a.request.region
        return " AND l.region = %(region)s"
    return ""


def _read(ctx: Ctx, sql: str, params: dict) -> list[tuple]:
    from world import admin_connection  # local import: world needs the database

    if ctx.conn is not None:
        return ctx.conn.execute(sql, params).fetchall()
    with admin_connection(autocommit=True) as conn:
        return conn.execute(sql, params).fetchall()


def _example(row: tuple) -> dict:
    fid, at, region, label, confidence, flagged, text = row
    return {
        "feedback_id": fid,
        "submitted_at": at.astimezone(dt.UTC).isoformat().replace("+00:00", "Z"),
        "region": region,
        "label": label,
        "confidence": f"{confidence:.4f}",
        "flagged": flagged,
        "feedback_text": text,
    }


_EXAMPLE_COLUMNS = (
    "SELECT f.feedback_id, f.submitted_at, l.region, p.predicted_label, p.confidence,"
    " p.flagged, f.feedback_text "
)


async def s04_stored_flag_inconsistent(b: Base, ctx: Ctx) -> Prepared:
    a = sent(b)
    params = _params(ctx, a, tau=ctx.stack.sentiment_manifest.tau)
    region = _where_region(a, params)
    rows = _read(
        ctx,
        "SELECT p.feedback_id "
        + _SET
        + region
        + " AND abs(p.confidence - %(tau)s) > 0.0001 ORDER BY p.feedback_id",
        params,
    )
    if not rows:
        raise Skip("no prediction clear of the rounding band")
    target = ctx.rng.choice([r[0] for r in rows])
    ctx.conn.execute(
        "UPDATE sentiment_predictions SET flagged = NOT flagged"
        " WHERE feedback_id = %s AND model_version = %s",
        (target, ctx.stack.sentiment_manifest.version),
    )
    return await _regenerated(b, ctx, flipped_feedback_id=target)


async def _regenerated(b: Base, ctx: Ctx, **note) -> Prepared:
    reply = await ctx.stack.ask("sentiment", b.request)
    if reply.kind != "answer":
        raise Skip("the specialist did not answer on the changed database")
    return Prepared(reply.text, reply.answer, note=note)


async def s05_trend_verdict_flipped(b: Base, ctx: Ctx) -> Prepared:
    d = sent(b).model_dump(mode="json")
    if d["trend"] is None or d["trend"]["verdict"] == "needs two periods":
        raise Skip("no trend comparison")
    flip = {"rose": "fell", "fell": "rose", "no clear change": "rose"}
    d["trend"]["verdict"] = flip[d["trend"]["verdict"]]
    return sentiment_prepared(d)


async def s06_trend_p_value_changed(b: Base, ctx: Ctx) -> Prepared:
    d = sent(b).model_dump(mode="json")
    t = d["trend"]
    if t is None or t["p_value"] is None:
        raise Skip("no p-value")
    t["p_value"] = _p_changed(t["p_value"])
    return sentiment_prepared(d)


async def s07_compared_bucket_mislabelled(b: Base, ctx: Ctx) -> Prepared:
    d = sent(b).model_dump(mode="json")
    t = d["trend"]
    if t is None or t["latest_bucket"] is None or not t["earlier_buckets"]:
        raise Skip("no comparison to mislabel")
    t["latest_bucket"] = t["earlier_buckets"][0]
    return sentiment_prepared(d)


def _with_examples(b: Base) -> dict:
    d = sent(b).model_dump(mode="json")
    if not d["examples"]:
        raise Skip("no quoted comments")
    return d


def _put_example(d: dict, example: dict) -> Prepared:
    d["examples"][0] = example
    d["quoted_feedback_ids"] = [e["feedback_id"] for e in d["examples"]]
    return sentiment_prepared(d, replaced_with=example["feedback_id"])


async def s08_quote_changed_by_one_word(b: Base, ctx: Ctx) -> Prepared:
    d = _with_examples(b)
    words = d["examples"][0]["feedback_text"].split(" ")
    i = max(range(len(words)), key=lambda k: len(words[k]))
    words[i] = "satisfactory" if words[i] != "satisfactory" else "adequate"
    d["examples"][0]["feedback_text"] = " ".join(words)
    return sentiment_prepared(d)


async def s09_quote_from_another_region(b: Base, ctx: Ctx) -> Prepared:
    a = sent(b)
    d = _with_examples(b)
    if a.request.region is None:
        raise Skip("no region was asked for, so no comment is from another region")
    params = _params(ctx, a, region=a.request.region)
    label = ""
    if a.request.example_label:
        params["label"] = a.request.example_label
        label = " AND p.predicted_label = %(label)s"
    rows = _read(
        ctx,
        _EXAMPLE_COLUMNS
        + _SET
        + " AND l.region <> %(region)s"
        + label
        + " ORDER BY p.confidence DESC, f.feedback_id LIMIT 1",
        params,
    )
    if not rows:
        raise Skip("no comment from another region in the set")
    return _put_example(d, _example(rows[0]))


async def s10_quote_not_in_the_top_three(b: Base, ctx: Ctx) -> Prepared:
    a = sent(b)
    d = _with_examples(b)
    params = _params(ctx, a)
    region = _where_region(a, params)
    label = ""
    if a.request.example_label:
        params["label"] = a.request.example_label
        label = " AND p.predicted_label = %(label)s"
    rows = _read(
        ctx,
        _EXAMPLE_COLUMNS
        + _SET
        + region
        + label
        + " ORDER BY p.confidence DESC, f.feedback_id OFFSET 3 LIMIT 1",
        params,
    )
    if not rows:
        raise Skip("no fourth comment in the set")
    return _put_example(d, _example(rows[0]))


async def s11_complete_on_a_partial_answer(b: Base, ctx: Ctx) -> Prepared:
    a = sent(b)
    params = _params(ctx, a)
    region = _where_region(a, params)
    rows = _read(ctx, "SELECT p.feedback_id " + _SET + region + " ORDER BY p.feedback_id", params)
    if len(rows) < 8:
        raise Skip("too few scored comments to hide some of")
    k = min(40, len(rows) // 4)
    ctx.conn.execute(
        "DELETE FROM sentiment_predictions WHERE model_version = %s AND feedback_id = ANY(%s)",
        (ctx.stack.sentiment_manifest.version, [r[0] for r in rows[:k]]),
    )
    reply = await ctx.stack.ask("sentiment", b.request)
    if reply.kind != "answer":
        raise Skip("the specialist did not answer on the changed database")
    d = SentimentAnswer.model_validate(reply.answer).model_dump(mode="json")
    if d["summary"]["complete"]:
        raise Skip("the answer is still complete")
    d["summary"]["complete"] = True
    return sentiment_prepared(d, removed=k)


async def s12_text_figure_differs(b: Base, ctx: Ctx) -> Prepared:
    a = sent(b)
    n = a.summary.n_scored
    if n == 0:
        raise Skip("nothing scored")
    text = bump_in_text(b.text, f"{n:,} comments:", f"{n + 1:,} comments:")
    return Prepared(text, b.answer)


def _rating_counts(ctx: Ctx, a: SentimentAnswer) -> tuple[int, int]:
    params = _params(ctx, a)
    region = _where_region(a, params)
    row = _read(
        ctx,
        "SELECT count(*) FILTER (WHERE f.rating IS NOT NULL"
        " AND p.predicted_label IN ('positive','negative')),"
        " count(*) FILTER (WHERE (p.predicted_label = 'positive' AND f.rating <= 2)"
        " OR (p.predicted_label = 'negative' AND f.rating >= 4)) " + _SET + region,
        params,
    )[0]
    return int(row[0]), int(row[1])


def rating_fault(rate: float) -> Callable[[Base, Ctx], Awaitable[Prepared]]:
    async def apply(b: Base, ctx: Ctx) -> Prepared:
        a = sent(b)
        n, x0 = _rating_counts(ctx, a)
        if n < 100:
            raise Skip(f"covered n = {n} is under 100")
        target = max(x0, round(rate * n))
        k = target - x0
        params = _params(ctx, a)
        region = _where_region(a, params)
        pool = _read(
            ctx,
            "SELECT p.feedback_id, p.predicted_label "
            + _SET
            + region
            + " AND ((p.predicted_label = 'negative' AND f.rating <= 2)"
            " OR (p.predicted_label = 'positive' AND f.rating >= 4)) ORDER BY p.feedback_id",
            params,
        )
        if len(pool) < k:
            raise Skip("not enough consistent predictions to flip")
        chosen = ctx.rng.sample(pool, k)
        for fid, label in chosen:
            ctx.conn.execute(
                "UPDATE sentiment_predictions SET predicted_label = %s"
                " WHERE feedback_id = %s AND model_version = %s",
                (
                    "positive" if label == "negative" else "negative",
                    fid,
                    ctx.stack.sentiment_manifest.version,
                ),
            )
        n2, x2 = _rating_counts(ctx, a)
        prepared = await _regenerated(
            b, ctx, covered_n=n2, contradictions=x2, flipped=k, contradiction_rate=round(x2 / n2, 5)
        )
        prepared.prediction = {
            "rule": "n >= 20 and P(X >= x | n, 0.01) < 0.01",
            "n": n2,
            "x": x2,
            "predicted_caught": rating_rule_fails(n2, x2),
        }
        return prepared

    return apply


# --------------------------------------------------------------------------- consistent misparse


async def _reparsed(b: Base, ctx: Ctx, request: dict, **note) -> Prepared:
    if request == b.request:
        raise Skip("the changed request equals the original")
    reply = await ctx.stack.ask(b.agent, request)
    if reply.kind != "answer":
        raise Skip("the wrong request is declined or fails, so no consistent answer exists")
    return Prepared(reply.text, reply.answer, note={"wrong_request": request, **note})


def _cycle(value, options, default=None):
    if value not in options:
        return options[0] if default is None else default
    return options[(options.index(value) + 1) % len(options)]


async def mr_month(b: Base, ctx: Ctx) -> Prepared:
    r = b.request
    if r.get("start"):
        s, e = shifted_range(dt.date.fromisoformat(r["start"]), dt.date.fromisoformat(r["end"]))
    else:
        s, e = default_previous_month(DATASET_WINDOW_END)
        s, e = shifted_range(s, e)
    return await _reparsed(b, ctx, dict(r, start=s.isoformat(), end=e.isoformat()))


async def mr_region(b: Base, ctx: Ctx) -> Prepared:
    r = b.request
    return await _reparsed(b, ctx, dict(r, region=_cycle(r.get("region"), REGIONS)))


_SWAP = {
    "sla_compliance": "first_time_fix_rate",
    "first_time_fix_rate": "sla_compliance",
    "incident_count": "incident_rate",
    "incident_rate": "incident_count",
}


async def mr_metric(b: Base, ctx: Ctx) -> Prepared:
    if b.metric not in _SWAP:
        raise Skip("no neighbouring metric")
    return await _reparsed(b, ctx, dict(b.request, metric=_SWAP[b.metric]))


async def mf_month(b: Base, ctx: Ctx) -> Prepared:
    r = b.request
    if not r.get("period_start"):
        raise Skip("no period named")
    s, e = shifted_range(
        dt.date.fromisoformat(r["period_start"]),
        dt.date.fromisoformat(r["period_end"]),
        historical=False,
    )
    return await _reparsed(b, ctx, dict(r, period_start=s.isoformat(), period_end=e.isoformat()))


async def mf_slice(b: Base, ctx: Ctx) -> Prepared:
    return await _reparsed(b, ctx, dict(b.request, slice=_cycle(b.request["slice"], SLICES)))


async def ms_month(b: Base, ctx: Ctx) -> Prepared:
    r = b.request
    if not r.get("start"):
        raise Skip("no period named")
    s, e = shifted_range(dt.date.fromisoformat(r["start"]), dt.date.fromisoformat(r["end"]))
    return await _reparsed(b, ctx, dict(r, start=s.isoformat(), end=e.isoformat()))


async def ms_region(b: Base, ctx: Ctx) -> Prepared:
    r = b.request
    return await _reparsed(b, ctx, dict(r, region=_cycle(r.get("region"), REGIONS, "west")))


async def ms_label(b: Base, ctx: Ctx) -> Prepared:
    r = b.request
    return await _reparsed(b, ctx, dict(r, example_label=_cycle(r["example_label"], LABELS)))


# --------------------------------------------------------------------------- owner faults


async def o1a_repeat_links_ignored(b: Base, ctx: Ctx) -> Prepared:
    d = rep(b).model_dump(mode="json")
    f = d["figures"]
    if f["numerator"] == f["denominator"]:
        raise Skip("no repeat visit in the range, so ignoring the links changes nothing")
    f["numerator"] = f["denominator"]
    f["rate"] = rate_string(f["numerator"], f["denominator"])
    return reporting_prepared(b, d, rate=f["rate"])


async def o1b_literal_no_linked_incident(b: Base, ctx: Ctx) -> Prepared:
    a = rep(b)
    lo = dt.datetime.combine(a.start, dt.time.min, dt.UTC)
    hi = dt.datetime.combine(a.end + dt.timedelta(days=1), dt.time.min, dt.UTC)
    params: dict[str, Any] = {"lo": lo, "hi": hi}
    where = ""
    f = a.figures
    if f.technician_id is not None:
        where += " AND ar.technician_id = %(t)s"
        params["t"] = f.technician_id
    if f.account_id is not None:
        where += " AND r.account_id = %(a)s"
        params["a"] = f.account_id
    if f.region is not None:
        where += " AND l.region = %(g)s"
        params["g"] = f.region
    rows = _read(
        ctx,
        "SELECT count(*), count(*) FILTER (WHERE NOT EXISTS"
        " (SELECT 1 FROM incidents i WHERE i.request_id = r.request_id))"
        " FROM archived_requests ar JOIN service_requests r ON r.request_id = ar.request_id"
        " JOIN locations l ON l.location_id = r.location_id"
        " WHERE ar.completed_at >= %(lo)s AND ar.completed_at < %(hi)s" + where,
        params,
    )
    total, clean = rows[0]
    if total != f.denominator:
        raise Skip("the literal query's denominator differs from the answer's")
    if clean == f.numerator:
        raise Skip("the literal definition gives the same figure")
    d = a.model_dump(mode="json")
    d["figures"]["numerator"] = int(clean)
    d["figures"]["rate"] = rate_string(int(clean), int(total))
    return reporting_prepared(b, d, rate=d["figures"]["rate"])


async def o2_holiday_weeks_flattened(b: Base, ctx: Ctx) -> Prepared:
    d = fc(b).model_dump(mode="json")
    served = [w for w in d["weeks"] if w["served"]]
    if len(served) < 3:
        raise Skip("fewer than three served weeks")
    level = sum(w["point"] for w in served[:-2]) / len(served[:-2])
    for w in served[-2:]:
        delta = level - w["point"]
        for key in ("point", "lo80", "hi80", "lo95", "hi95"):
            w[key] = round(w[key] + delta, 4)
    if d["period_total"] is not None:
        d["period_total"] = sum(w["point"] for w in d["weeks"])
    return forecast_prepared(
        d, flattened=[w["week_start"] for w in served[-2:]], level=round(level, 2)
    )


async def o3a_all_low_star_flipped(b: Base, ctx: Ctx) -> Prepared:
    return await _flip_positive(b, ctx, also_unrated_and_three_star=False)


async def o3b_flip_to_about_88_percent(b: Base, ctx: Ctx) -> Prepared:
    return await _flip_positive(b, ctx, also_unrated_and_three_star=True)


async def _flip_positive(b: Base, ctx: Ctx, also_unrated_and_three_star: bool) -> Prepared:
    a = sent(b)
    params = _params(ctx, a)
    region = _where_region(a, params)
    scored = _read(ctx, "SELECT count(*) " + _SET + region, params)[0][0]
    if scored < 100:
        raise Skip(f"only {scored} scored comments in the set")
    low = [
        r[0]
        for r in _read(
            ctx,
            "SELECT p.feedback_id "
            + _SET
            + region
            + " AND p.predicted_label <> 'positive' AND f.rating <= 2 ORDER BY p.feedback_id",
            params,
        )
    ]
    if not low:
        raise Skip("no non-positive prediction on a 1-2 star comment")
    flip = list(low)
    if also_unrated_and_three_star:
        pool = [
            r[0]
            for r in _read(
                ctx,
                "SELECT p.feedback_id " + _SET + region + " AND p.predicted_label <> 'positive'"
                " AND (f.rating = 3 OR f.rating IS NULL) ORDER BY p.feedback_id",
                params,
            )
        ]
        ctx.rng.shuffle(pool)
        positives = _read(
            ctx, "SELECT count(*) " + _SET + region + " AND p.predicted_label = 'positive'", params
        )[0][0]
        need = max(0, -(-88 * scored // 100) - positives - len(low))
        flip += pool[:need]
    ctx.conn.execute(
        "UPDATE sentiment_predictions SET predicted_label = 'positive'"
        " WHERE model_version = %s AND feedback_id = ANY(%s)",
        (ctx.stack.sentiment_manifest.version, flip),
    )
    prepared = await _regenerated(b, ctx, flipped=len(flip), low_star_flipped=len(low))
    answer = SentimentAnswer.model_validate(prepared.answer)
    share = answer.summary.shares.positive
    n, x = _rating_counts(ctx, a)
    prepared.note.update(
        positive_share=share,
        covered_n=n,
        contradictions=x,
        contradiction_rate=round(x / n, 4) if n else None,
        reached_88=bool(share and Decimal(share) >= Decimal("0.88")),
    )
    prepared.prediction = {
        "rule": "n >= 20 and P(X >= x | n, 0.01) < 0.01",
        "n": n,
        "x": x,
        "predicted_caught": rating_rule_fails(n, x),
    }
    return prepared


async def o4a_ranked_without_the_minimum(b: Base, ctx: Ctx) -> Prepared:
    a = rep(b)
    small = [g for g in (a.figures.groups or []) if g.denominator < MIN_GROUP]
    if not small:
        raise Skip("no group under 20 cases")
    text = render_reporting(a, 0)
    if text == b.text:
        raise Skip("the text is unchanged")
    return Prepared(text, b.answer, note={"groups_under_20": len(small)})


async def o4b_too_few_marking_removed(b: Base, ctx: Ctx) -> Prepared:
    marking = f" That is {TOO_FEW}."
    if marking not in b.text:
        raise Skip("the text carries no too-few marking")
    return Prepared(b.text.replace(marking, ""), b.answer)


async def o5_trailing_quarter(b: Base, ctx: Ctx) -> Prepared:
    end = DATASET_WINDOW_END
    start = end - dt.timedelta(days=89)
    return await _reparsed(
        b,
        ctx,
        dict(b.request, start=start.isoformat(), end=end.isoformat()),
        implied_window=["2026-08-17", "2026-08-30"],
    )


# --------------------------------------------------------------------------- the registry


def _all(*preds):
    return lambda b: all(p(b) for p in preds)


rep_answer = is_answer("reporting")
fc_answer = is_answer("forecast")
se_answer = is_answer("sentiment")


def _fc_has(key):
    return lambda b: bool((b.answer or {}).get(key))


REGISTRY: dict[str, Fault] = {}


def _add(fault_id: str, agent: str, applies, apply, needs_db: bool = False) -> None:
    REGISTRY[fault_id] = Fault(fault_id, agent, applies, apply, needs_db)


_add("R01", "reporting", rep_answer, r01_count_off_by_one)
_add(
    "R02",
    "reporting",
    _all(rep_answer, lambda b: b.metric != "incident_count"),
    r02_rate_last_digit,
)
_add(
    "R03",
    "reporting",
    _all(rep_answer, lambda b: b.metric != "incident_count"),
    r03_denominator_off_by_one,
)
_add("R04", "reporting", _grouped, r04_group_dropped)
_add("R05", "reporting", _grouped, r05_order_swapped)
_add("R06", "reporting", _grouped, r06_group_count_wrong)
_add(
    "R07",
    "reporting",
    _all(_grouped, lambda b: b.metric == "repeat_visit_drivers"),
    r07_too_few_flag_flipped,
)
_add(
    "R08",
    "reporting",
    _all(_has_filter, lambda b: b.metric != "repeat_visit_drivers"),
    r08_filter_dropped,
)
_add("R09", "reporting", rep_answer, r09_range_shifted_in_data_only)
_add("R10", "reporting", rep_answer, r10_text_figure_differs)
_add("R11", "reporting", is_decline("reporting"), r11_decline_carries_a_figure)
_add(
    "R12",
    "reporting",
    _all(is_decline("reporting"), lambda b: b.error_code == "not_supported"),
    r12_decline_states_the_wrong_reason,
)
_add(
    "R13",
    "reporting",
    _all(_grouped, lambda b: b.metric == "repeat_visit_drivers"),
    r13_p_value_changed,
)
_add(
    "R14",
    "reporting",
    _all(_grouped, lambda b: b.metric == "repeat_visit_drivers"),
    r14_standout_flipped,
)

_add("F01", "forecast", fc_answer, f01_numbers_for_an_unserved_band)
_add("F02", "forecast", fc_answer, f02_shown_error_differs)
_add("F03", "forecast", fc_answer, f03_interval_misses_its_point)
_add(
    "F04",
    "forecast",
    _all(fc_answer, lambda b: (b.answer or {}).get("period_total") is not None),
    f04_total_is_not_the_sum,
)
_add(
    "F05",
    "forecast",
    _all(fc_answer, lambda b: (b.answer or {}).get("beyond_horizon_weeks", 0) > 0),
    f05_horizon_over_26_weeks,
)
_add("F06", "forecast", _all(fc_answer, _fc_has("history")), f06_history_week_changed)
_add("F07", "forecast", _all(fc_answer, _fc_has("year_end_weeks")), f07_year_end_caveat_removed)
_add("F08", "forecast", fc_answer, f08_text_figure_differs)

_add("S01", "sentiment", se_answer, s01_label_count_changed)
_add("S02", "sentiment", se_answer, s02_share_changed)
_add("S03", "sentiment", se_answer, s03_flagged_count_changed)
_add("S04", "sentiment", se_answer, s04_stored_flag_inconsistent, needs_db=True)
_add(
    "S05",
    "sentiment",
    _all(se_answer, lambda b: b.request.get("want_trend")),
    s05_trend_verdict_flipped,
)
_add(
    "S06",
    "sentiment",
    _all(se_answer, lambda b: b.request.get("want_trend")),
    s06_trend_p_value_changed,
)
_add(
    "S07",
    "sentiment",
    _all(se_answer, lambda b: b.request.get("want_trend")),
    s07_compared_bucket_mislabelled,
)
_add(
    "S08",
    "sentiment",
    _all(se_answer, lambda b: b.request.get("want_examples")),
    s08_quote_changed_by_one_word,
)
_add(
    "S09",
    "sentiment",
    _all(se_answer, lambda b: b.request.get("want_examples") and b.request.get("region")),
    s09_quote_from_another_region,
)
_add(
    "S10",
    "sentiment",
    _all(se_answer, lambda b: b.request.get("want_examples")),
    s10_quote_not_in_the_top_three,
)
_add("S11", "sentiment", se_answer, s11_complete_on_a_partial_answer, needs_db=True)
_add("S12", "sentiment", se_answer, s12_text_figure_differs)

RATING_LEVELS = {"K05": 0.005, "K10": 0.01, "K20": 0.02, "K40": 0.04, "K80": 0.08}
for _id, _rate in RATING_LEVELS.items():
    _add(_id, "sentiment", se_answer, rating_fault(_rate), needs_db=True)

_add("MR1", "reporting", rep_answer, mr_month)
_add(
    "MR2",
    "reporting",
    _all(
        rep_answer,
        lambda b: b.metric != "repeat_visit_drivers" and b.request.get("group_by") != "region",
    ),
    mr_region,
)
_add("MR3", "reporting", _all(rep_answer, lambda b: b.metric in _SWAP), mr_metric)
_add("MF1", "forecast", _all(fc_answer, lambda b: b.request.get("period_start")), mf_month)
_add("MF2", "forecast", fc_answer, mf_slice)
_add("MS1", "sentiment", _all(se_answer, lambda b: b.request.get("start")), ms_month)
_add("MS2", "sentiment", se_answer, ms_region)
_add(
    "MS3",
    "sentiment",
    _all(se_answer, lambda b: b.request.get("want_examples") and b.request.get("example_label")),
    ms_label,
)

_add(
    "O1a",
    "reporting",
    _all(rep_answer, lambda b: b.metric == "first_time_fix_rate" and not b.request.get("group_by")),
    o1a_repeat_links_ignored,
)
_add(
    "O1b",
    "reporting",
    _all(rep_answer, lambda b: b.metric == "first_time_fix_rate" and not b.request.get("group_by")),
    o1b_literal_no_linked_incident,
)
_add(
    "O2",
    "forecast",
    _all(fc_answer, lambda b: b.request.get("slice") == "total"),
    o2_holiday_weeks_flattened,
)
_add("O3a", "sentiment", se_answer, o3a_all_low_star_flipped, needs_db=True)
_add("O3b", "sentiment", se_answer, o3b_flip_to_about_88_percent, needs_db=True)
_add(
    "O4a",
    "reporting",
    _all(
        _grouped, lambda b: b.metric in ("incident_rate", "sla_compliance", "first_time_fix_rate")
    ),
    o4a_ranked_without_the_minimum,
)
_add("O4b", "reporting", _all(rep_answer, lambda b: TOO_FEW in b.text), o4b_too_few_marking_removed)
_add("O5", "sentiment", se_answer, o5_trailing_quarter)
