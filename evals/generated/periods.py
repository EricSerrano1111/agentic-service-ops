"""Deterministic period resolution for `interp_fresh_v1` eligibility (plan.md).

Past periods follow ADR-050 against the as-of date; future periods follow ADR-072. Only
phrases those ADRs define are recognised. Everything else returns None and the item is
ineligible: the module never guesses (a bare month name in a past question is L-38).
Notably unrecognised, although brief_v1.md defines some of them: "this quarter",
"year to date", "the past N weeks", and "next quarter".
"""

from __future__ import annotations

import calendar
import datetime as dt
import re
from dataclasses import dataclass

MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name} | {
    name.lower(): i for i, name in enumerate(calendar.month_abbr) if name
}
MAX_HORIZON_WEEKS = 26

_PREFIX = re.compile(r"^(?:(?:in|for|during|over|from|within|across)\s+)?(?:the\s+)?")


@dataclass(frozen=True)
class Resolved:
    start: dt.date
    end: dt.date
    horizon_weeks: int | None = None  # set only by "the next N weeks"


def _month_bounds(year: int, month: int) -> tuple[dt.date, dt.date]:
    return dt.date(year, month, 1), dt.date(year, month, calendar.monthrange(year, month)[1])


def _quarter_bounds(year: int, q: int) -> tuple[dt.date, dt.date]:
    first = 3 * (q - 1) + 1
    return dt.date(year, first, 1), _month_bounds(year, first + 2)[1]


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    idx = year * 12 + (month - 1) + delta
    return idx // 12, idx % 12 + 1


def normalise(text: str) -> str:
    t = re.sub(r"[?.!,;]+", " ", text.lower())
    t = re.sub(r"\s+", " ", t).strip()
    return _PREFIX.sub("", t, count=1).strip()


def resolve_period(text: str | None, as_of: dt.date, area: str) -> Resolved | None:
    """The period `text` denotes on `as_of`, for a question in `area`; None if unrecognised.

    Relative past phrases ("last month") resolve for reporting and sentiment only: in a
    forecast question they are a past period the forecast agent declines.
    """
    if not text or area not in ("reporting", "sentiment", "forecast"):
        return None
    t = normalise(text)
    past = area in ("reporting", "sentiment")

    if past:
        if t == "last month":
            y, m = _shift_month(as_of.year, as_of.month, -1)
            return Resolved(*_month_bounds(y, m))
        if t == "this month":
            return Resolved(dt.date(as_of.year, as_of.month, 1), as_of)
        if t == "last quarter":
            cur_q = (as_of.month - 1) // 3 + 1
            y, q = (as_of.year, cur_q - 1) if cur_q > 1 else (as_of.year - 1, 4)
            return Resolved(*_quarter_bounds(y, q))
        m = re.fullmatch(r"past (\d{1,3}) days", t)
        if m and int(m.group(1)) >= 1:
            n = int(m.group(1))
            return Resolved(as_of - dt.timedelta(days=n - 1), as_of)

    # An explicit month or quarter with a year is taken as stated, in either direction.
    m = re.fullmatch(r"([a-z]+) (\d{4})", t)
    if m and m.group(1) in MONTHS:
        return Resolved(*_month_bounds(int(m.group(2)), MONTHS[m.group(1)]))
    m = re.fullmatch(r"(?:q([1-4]) (\d{4})|(\d{4}) q([1-4]))", t)
    if m:
        q = int(m.group(1) or m.group(4))
        y = int(m.group(2) or m.group(3))
        return Resolved(*_quarter_bounds(y, q))

    if not past:
        if t == "next month":
            y, mo = _shift_month(as_of.year, as_of.month, 1)
            return Resolved(*_month_bounds(y, mo))
        m = re.fullmatch(r"next (\d{1,2}) weeks?", t)
        if m and int(m.group(1)) >= 1:
            n = int(m.group(1))
            return Resolved(
                as_of + dt.timedelta(days=1), as_of + dt.timedelta(days=7 * n), horizon_weeks=n
            )
        # A bare month or quarter means its next occurrence after the as-of date (ADR-072).
        # The current month or quarter is the L-38 ambiguity: not guessed.
        if t in MONTHS:
            mo = MONTHS[t]
            if mo == as_of.month:
                return None
            return Resolved(*_month_bounds(as_of.year + (1 if mo < as_of.month else 0), mo))
        m = re.fullmatch(r"q([1-4])", t)
        if m:
            q = int(m.group(1))
            cur_q = (as_of.month - 1) // 3 + 1
            if q == cur_q:
                return None
            return Resolved(*_quarter_bounds(as_of.year + (1 if q < cur_q else 0), q))
    return None


def _date(value: object) -> dt.date | None:
    return dt.date.fromisoformat(value) if isinstance(value, str) else None


def check_item_period(intent: dict, as_of: dt.date) -> tuple[bool, str]:
    """(eligible, reason) for the date check of an item's `intent`, as parsed JSON."""
    area = intent["area"]
    start, end = _date(intent.get("period_start")), _date(intent.get("period_end"))
    horizon = intent.get("horizon_weeks")
    if area != "forecast" and horizon is not None:
        return False, "horizon_weeks on a past-period item"
    if intent.get("period_stated"):
        res = resolve_period(intent.get("period_text"), as_of, area)
        if res is None:
            return False, "period_text not recognised"
        if (res.start, res.end) != (start, end):
            return False, "stated dates differ from the deterministic resolution"
        if res.horizon_weeks is not None and horizon != res.horizon_weeks:
            return False, "horizon_weeks differs from the stated weeks"
        weeks_ahead = -(-(res.end - as_of).days // 7)
        if (
            area == "forecast"
            and horizon is not None
            and res.horizon_weeks is None
            and horizon != weeks_ahead
        ):
            return False, "horizon_weeks differs from the period's weeks ahead"
    else:
        if any(v is not None for v in (intent.get("period_text"), start, end)):
            return False, "period fields set although no period is stated"
        if horizon is not None and not 1 <= horizon <= MAX_HORIZON_WEEKS:
            return False, "horizon_weeks outside 1..26"
    return True, "ok"
