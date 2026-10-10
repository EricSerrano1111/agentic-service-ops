"""Forecast checks (ADR-087, ADR-071, ADR-072): history against QA's own SQL, the forecast's
arithmetic, the `volume_v2` manifest's serving table, the year-end caveat, declines, and the
answer text.

QA does not reproduce the model: it cannot say a point forecast is the right number. It checks
what can be checked without trusting the forecast agent: that every week asked for is the week
the question's period or horizon names, that a band the manifest marks unserved carries no
number and its `shown_error` is the manifest's, that each interval contains its point, that a
period total is the sum of its weeks, that the history is what the database holds, and that the
text states only those numbers. It reads the manifest itself and imports nothing from the
forecast agent, the volume server or the forecast runtime.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from schemas import CheckResult, ForecastAnswer, ForecastRequest

from . import slots
from .config import Settings
from .db import Source
from .reporting import bad, result

HORIZON_CAP = 26
BANDS = (("1-4", 1, 4), ("5-13", 5, 13), ("14-26", 14, 26))
SLICES = ("total", "inspection", "install", "maintenance", "repair", "upgrade")
MAX_HISTORY_WEEKS = 52
#: The caveat the answer text carries when a Christmas or New Year week is shown (ADR-070).
YEAR_END_PHRASE = "holiday adjustment"
#: What a forecast decline's text says for each reason (matched case-insensitively).
DECLINE_PATTERNS = {
    "sla": r"\bsla\b.*can't be forecast",
    "incidents": r"incidents can't be forecast",
    "sentiment": r"sentiment can't be forecast",
    "region": r"can't be broken down by region",
    "account": r"can't be broken down by account",
    "technician": r"can't be broken down by technician",
    "other": r"isn't something i can forecast",
    "past_period": r"already happened",
    "no_week": r"no forecast week starts",
}


def band_name(horizon: int) -> str | None:
    """The band a horizon falls in, or None outside 1 to 26."""
    for name, lo, hi in BANDS:
        if lo <= horizon <= hi:
            return name
    return None


@dataclass(frozen=True)
class Manifest:
    version: str  # SHA-256 of the manifest file's bytes
    last_training_week: dt.date  # Monday of the last week the model was trained on
    serving: dict[str, dict[str, dict[str, Any]]]

    @property
    def trained_through(self) -> dt.date:
        return self.last_training_week + dt.timedelta(days=6)

    def week(self, horizon: int) -> dt.date:
        return self.last_training_week + dt.timedelta(weeks=horizon)

    @classmethod
    def load(cls, path: Path) -> Manifest:
        raw = Path(path).read_bytes()
        doc = json.loads(raw)
        return cls(
            version=hashlib.sha256(raw).hexdigest(),
            last_training_week=dt.date.fromisoformat(doc["trained_on"][1]),
            serving=doc["serving"]["slices"],
        )


def first_forecast_week(as_of: dt.date) -> dt.date:
    """The Monday after the as-of date: horizon 1 (ADR-072)."""
    return as_of + dt.timedelta(days=7 - as_of.weekday())


def _next_month(as_of: dt.date) -> tuple[dt.date, dt.date]:
    start = (as_of.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
    return start, (start + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)


def _mondays(start: dt.date, end: dt.date) -> list[dt.date]:
    day = start + dt.timedelta(days=(7 - start.weekday()) % 7)
    out = []
    while day <= end:
        out.append(day)
        day += dt.timedelta(weeks=1)
    return out


def resolve(req: ForecastRequest, as_of: dt.date) -> tuple[bool, bool, list[dt.date]]:
    """(range assumed, past, requested weeks) by ADR-072's rules: forecasts cover weeks after
    the as-of date; N weeks means the next N; a period is the Mondays inside it that are in the
    future; no period at all is next month."""
    first = first_forecast_week(as_of)
    if req.horizon_weeks is not None:
        return False, False, [first + dt.timedelta(weeks=i) for i in range(req.horizon_weeks)]
    assumed = req.period_start is None
    start, end = _next_month(as_of) if assumed else (req.period_start, req.period_end)
    weeks = [m for m in _mondays(start, end) if m >= first]
    return assumed, (not weeks and end < first), weeks


def is_year_end(monday: dt.date) -> bool:
    """An ISO week (Monday start) containing December 25 or January 1 (ADR-070)."""
    days = [monday + dt.timedelta(days=i) for i in range(7)]
    return any((d.month, d.day) in ((12, 25), (1, 1)) for d in days)


def decline_reasons(req: ForecastRequest, as_of: dt.date) -> set[str]:
    """Every reason the request cannot be forecast, as reason classes; empty if it can."""
    if req.unsupported is not None and req.unsupported != "past_period":
        return {req.unsupported}
    _, past, weeks = resolve(req, as_of)
    if req.unsupported == "past_period" or past:
        return {"past_period"}
    if not weeks:
        return {"no_week"}
    return set()


class Checker:
    def __init__(self, src: Source, settings: Settings, manifest: Manifest) -> None:
        self.src = src
        self.settings = settings
        self.manifest = manifest

    # ------------------------------------------------------------------ answers

    def check_answer(self, answer: ForecastAnswer, text: str) -> list[CheckResult]:
        checks = [
            self._request(answer),
            self._arithmetic(answer),
            self._serving(answer),
            self._year_end(answer, text),
            self._history(answer),
        ]
        if all(c.passed for c in checks):
            checks.append(self._text(answer, text))
        return checks

    def _request(self, a: ForecastAnswer) -> CheckResult:
        """The weeks shown are the weeks the request names, by QA's own resolution."""
        problems = []
        as_of = self.settings.as_of
        if a.as_of != as_of:
            problems.append("as_of_differs")
        if decline_reasons(a.request, as_of):
            problems.append("answered_a_request_that_should_be_declined")
            return result("weeks_match_request", problems)
        assumed, _, requested = resolve(a.request, as_of)
        if a.range_assumed != assumed:
            problems.append("range_assumed_flag")
        inside = [w for w in requested if w <= self.manifest.week(HORIZON_CAP)]
        if (a.requested_first_week, a.requested_last_week) != (requested[0], requested[-1]):
            problems.append("requested_weeks_differ")
        if a.beyond_horizon_weeks != len(requested) - len(inside):
            problems.append("beyond_horizon_count")
        if [w.week_start for w in a.weeks] != inside:
            problems.append("weeks_shown_differ")
        if a.trained_through != self.manifest.trained_through:
            problems.append("trained_through_differs")
        if a.model_version != self.manifest.version:
            problems.append("model_version_differs")
        return result("weeks_match_request", problems)

    def _arithmetic(self, a: ForecastAnswer) -> CheckResult:
        problems = []
        for w in a.weeks:
            if not 1 <= w.horizon <= HORIZON_CAP:
                problems.append("horizon_beyond_cap")
                continue
            if w.week_start != self.manifest.week(w.horizon):
                problems.append("week_start_does_not_match_horizon")
            if w.band != band_name(w.horizon):
                problems.append("band_differs_from_horizon")
            if w.served:
                numbers = (w.point, w.lo80, w.hi80, w.lo95, w.hi95)
                if any(n is None or not math.isfinite(n) for n in numbers):
                    problems.append("served_week_missing_a_number")
                elif not (w.lo95 <= w.lo80 <= w.point <= w.hi80 <= w.hi95):
                    problems.append("interval_does_not_contain_point")
        served = [w for w in a.weeks if w.served]
        if len(a.weeks) > 1 and len(served) == len(a.weeks):
            if a.period_total is None:
                problems.append("period_total_missing")
            elif not math.isclose(
                a.period_total, sum(w.point for w in served), rel_tol=1e-9, abs_tol=1e-6
            ):
                problems.append("period_total_is_not_the_sum")
        elif a.period_total is not None:
            problems.append("period_total_with_unshown_weeks")
        return result("forecast_arithmetic", problems)

    def _serving(self, a: ForecastAnswer) -> CheckResult:
        """Served/unserved and the shown error come from the manifest (ADR-071), not from the
        answer; a week in an unserved band carries no number."""
        problems = []
        table = self.manifest.serving.get(a.request.slice)
        if table is None:
            return bad("serving_matches_manifest", "slice not in the manifest")
        for w in a.weeks:
            entry = table.get(band_name(w.horizon))
            if entry is None:
                problems.append("band_not_in_manifest")
                continue
            if w.served != bool(entry["served"]):
                problems.append("served_flag_differs_from_manifest")
            if not entry["served"] and any(
                n is not None for n in (w.point, w.lo80, w.hi80, w.lo95, w.hi95)
            ):
                problems.append("unserved_week_carries_a_number")
        if {w.band for w in a.weeks} != set(a.bands):
            problems.append("bands_differ_from_weeks")
        for band, verdict in a.bands.items():
            entry = table.get(band)
            if entry is None:
                problems.append("band_not_in_manifest")
                continue
            if verdict.served != bool(entry["served"]):
                problems.append("band_served_differs_from_manifest")
            if not math.isclose(
                verdict.shown_error, float(entry["shown_error"]), rel_tol=1e-9, abs_tol=1e-9
            ):
                problems.append("shown_error_differs_from_manifest")
        if a.period_total is not None and any(
            not table.get(band_name(w.horizon), {}).get("served") for w in a.weeks
        ):
            problems.append("period_total_with_unserved_band")
        return result("serving_matches_manifest", problems)

    def _year_end(self, a: ForecastAnswer, text: str) -> CheckResult:
        problems = []
        marked = sorted(w.week_start for w in a.weeks if is_year_end(w.week_start))
        if sorted(a.year_end_weeks) != marked:
            problems.append("year_end_weeks_differ")
        if bool(marked) != (YEAR_END_PHRASE in text.lower()):
            problems.append("year_end_caveat_in_text" if marked else "year_end_caveat_unneeded")
        return result("year_end_caveat", problems)

    def _history(self, a: ForecastAnswer) -> CheckResult:
        """The history is what the database holds: actual weekly request counts (all
        statuses, §6), Monday UTC weeks, none later than the last training week."""
        problems = []
        if not a.request.want_history:
            if a.history:
                problems.append("history_not_asked_for")
            return result("history_matches_database", problems)
        if not a.history or len(a.history) > MAX_HISTORY_WEEKS:
            return bad("history_matches_database", "history missing or too long")
        weeks = [h.week_start for h in a.history]
        if weeks != sorted(set(weeks)) or any(w.weekday() != 0 for w in weeks):
            problems.append("history_weeks_not_ordered_mondays")
        if weeks[-1] > self.manifest.last_training_week:
            problems.append("history_beyond_training")
        if problems:
            return result("history_matches_database", problems)
        actual = self.src.weekly_counts(a.request.slice, weeks[0], weeks[-1])
        if any(actual.get(h.week_start, 0) != h.count for h in a.history):
            problems.append("history_counts_differ")
        return result("history_matches_database", problems)

    def _text(self, a: ForecastAnswer, text: str) -> CheckResult:
        """The text's numbers, by position (§6 "Answer text"): each is one slot of the data
        part, rounded by its rule: whole requests to nearest, ties to even; errors to one place."""
        problems = slots.compare(text, slots.forecast(a), [])
        dates = set(re.findall(r"\b\d{4}-\d{2}-\d{2}\b", text))
        shown = {w.week_start for w in a.weeks} | {h.week_start for h in a.history}
        known = shown | {
            a.as_of,
            a.trained_through,
            a.requested_first_week,
            a.requested_last_week + dt.timedelta(days=6),
        }
        if not dates <= {d.isoformat() for d in known}:
            problems.append("text_states_another_date")
        return result("text_matches_data", problems)

    # ------------------------------------------------------------------ declines

    def check_decline(self, req: ForecastRequest, text: str) -> list[CheckResult]:
        problems = []
        reasons = decline_reasons(req, self.settings.as_of)
        lowered = text.lower()
        stated = {r for r, pattern in DECLINE_PATTERNS.items() if re.search(pattern, lowered)}
        if not reasons:
            problems.append("declined_a_request_that_can_be_forecast")
        elif not (stated & reasons):
            problems.append("reason_in_text_does_not_apply")
        digits = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", " ", text)
        digits = digits.replace(str(HORIZON_CAP), " ")
        return [
            result("decline_matches_reason", problems),
            result(
                "decline_no_figures", ["text_carries_a_number"] if re.search(r"\d", digits) else []
            ),
        ]
