"""The answer text, checked by position (data dictionary §6, "Answer text"; L-82).

Each number an answer's text states is a *slot*: it stands for one named field of the data part,
in an order fixed by the template. QA builds the list of numbers the text must state from the
verified figures, formats each by the rounding rule of its quantity, reads the numbers the text
actually states, and compares the two lists position by position. A number the data part has no
slot for, a missing slot and a slot whose number differs are different failures. There is no
set membership and no tolerance: a figure that is one more than its field, or its field's
ceiling where the rule rounds to nearest, is wrong.

Written from §6 alone. It imports no specialist, server or renderer code.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from schemas import (
    ForecastAnswer,
    IncidentRateResult,
    IncidentSummary,
    RepeatDriversResult,
    ReportingAnswer,
)

from . import textcheck

#: The small-sample minimum is this rule's value (§6 "Answer text" rule 4), never a setting.
MIN_CASES = 20
RANKED = 5  # groups named in a text
PER = 100  # "incidents per 100" is printed by the template
INTERVAL = 80  # "80% range" is printed by the template
HORIZON_CAP = 26
TOO_FEW = "too few to compare reliably"
BAND_NUMBERS = {"1-4": ("1", "4"), "5-13": ("5", "13"), "14-26": ("14", "26")}
LABELS = ("positive", "neutral", "negative", "mixed")


def count(n: int) -> str:
    return str(int(n))


def percent2(rate: str) -> str:
    """A stored 4-place fraction as a 2-place percentage: exact, no rounding occurs."""
    return f"{Decimal(rate) * 100:.2f}"


def percent1(share: str) -> str:
    """A stored 4-place share as a 1-place percentage, half up."""
    return str((Decimal(share) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def fraction4(numerator: int, denominator: int) -> str:
    return str(
        (Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.0001"), ROUND_HALF_UP)
    )


def whole(x: float) -> str:
    """Nearest whole number, a tie to the even number."""
    return str(round(x))


def one_decimal(x: float) -> str:
    return f"{x:.1f}"


def four_decimals(x: float) -> str:
    return f"{x:.4f}"


# --------------------------------------------------------------------------- the comparison


def compare(text: str, expected: list[str], names: list[str]) -> list[str]:
    """Problems, as fixed codes with the first slot that differs; none when the numbers the text
    states are exactly `expected`, in order."""
    got = textcheck.numbers_in(text, names)
    if got == expected:
        return []
    if len(got) > len(expected):
        kind = "text_states_a_number_with_no_slot"
    elif len(got) < len(expected):
        kind = "text_misses_a_slot_number"
    else:
        kind = "text_number_differs_from_its_slot"
    at = next(
        (i for i, (a, b) in enumerate(zip(got, expected, strict=False)) if a != b),
        min(len(got), len(expected)),
    )
    want = expected[at] if at < len(expected) else "-"
    have = got[at] if at < len(got) else "-"
    return [f"{kind}@{at}:expected_{want}_got_{have}"]


# --------------------------------------------------------------------------- reporting


def reporting(answer: ReportingAnswer) -> tuple[list[str], list[str], list[str]]:
    """(slots, names to strip, small-sample marking problems)."""
    f = answer.figures
    names = [getattr(f, "technician_name", None) or "", getattr(f, "account_name", None) or ""]
    out: list[str] = []
    marking: list[str] = []

    if isinstance(f, IncidentSummary):
        s = f.by_severity
        out += [count(f.incident_count), count(s.high), count(s.medium), count(s.low)]
        if f.groups is not None:
            names += [g.group for g in f.groups]
            shown = f.groups[:RANKED]
            out += [count(g.count) for g in shown]
            if f.group_count - len(shown) > 0:
                out.append(count(f.group_count - len(shown)))
            if f.truncated:
                out += [count(f.group_count), count(len(f.groups))]
        return out, names, marking

    if isinstance(f, RepeatDriversResult):
        names += [g.group for g in f.groups]
        if f.overall.jobs == 0:
            return out, names, marking
        out += [count(f.overall.repeated), count(f.overall.jobs), percent2(f.overall.rate)]
        standouts = [g for g in f.groups if g.stands_out]
        if standouts:
            for g in standouts:
                out += [
                    percent2(g.this.rate),
                    count(g.this.repeated),
                    count(g.this.jobs),
                    percent2(g.rest.rate),
                ]
        else:
            out.append(count(MIN_CASES))
        eligible = [g for g in f.groups if g.this.jobs >= MIN_CASES]
        for g in eligible[:RANKED]:
            out += [percent2(g.this.rate), count(g.this.repeated), count(g.this.jobs)]
        if len(f.groups) - len(eligible) > 0:
            out += [count(len(f.groups) - len(eligible)), count(MIN_CASES)]
        if f.truncated:
            out += [count(f.group_count), count(len(f.groups))]
        if f.group_by == "incident_type":
            for side in (f.any_other_incident, f.no_other_incident):
                if side is not None and side.rate is not None:
                    out += [percent2(side.rate), count(side.repeated), count(side.jobs)]
            for side in (f.any_other_incident, f.no_other_incident):
                if side is not None and side.rate is not None:
                    out.append(percent2(side.rate))
        return out, names, marking

    incident = isinstance(f, IncidentRateResult)
    filtered = bool(f.technician_name or f.account_name or f.region is not None)
    if filtered:
        if f.rate is not None:
            if incident:
                out += [f.rate, count(PER), count(f.numerator), count(f.denominator)]
            else:
                out += [percent2(f.rate), count(f.denominator), count(f.numerator)]
            marking = ["expect"] if f.denominator < MIN_CASES else []
    elif f.rate is None:
        if incident:
            out.append(count(f.numerator))
    elif incident:
        out += [f.rate, count(PER), count(f.numerator), count(f.denominator)]
    else:
        out += [percent2(f.rate), count(f.numerator), count(f.denominator)]

    if f.groups is not None:
        names += [g.group for g in f.groups]
        eligible = [g for g in f.groups if g.denominator >= MIN_CASES]
        for g in eligible[:RANKED]:
            if incident:
                out += [g.rate, count(PER), count(g.numerator), count(g.denominator)]
            else:
                out += [percent2(g.rate), count(g.numerator), count(g.denominator)]
        if not eligible:
            out.append(count(MIN_CASES))
        left_out = len(f.groups) - len(eligible)
        if left_out:
            out += [count(left_out), count(MIN_CASES)]
        if f.truncated:
            out += [count(f.group_count), count(len(f.groups))]
    return out, names, marking


def small_sample_problems(expect: list[str], text: str) -> list[str]:
    """§6 "Answer text" rule 4(a): the marking is present exactly when the rule calls for it.
    `expect` is the list `reporting` returned: ["expect"] when a filtered rate rests on fewer
    than 20 cases."""
    wanted = bool(expect)
    present = TOO_FEW in text
    if wanted and not present:
        return ["small_sample_marking_missing"]
    if present and not wanted:
        return ["small_sample_marking_not_called_for"]
    return []


# --------------------------------------------------------------------------- forecast


def forecast(a: ForecastAnswer) -> list[str]:
    out = [count(len(a.weeks) + a.beyond_horizon_weeks)]
    if not a.weeks:
        out.append(count(HORIZON_CAP))
    served = [w for w in a.weeks if w.served]
    for w in served:
        out += [whole(w.point), count(INTERVAL), whole(w.lo80), whole(w.hi80)]
    if a.period_total is not None:
        out += [count(len(a.weeks)), whole(a.period_total)]
    for band in ("1-4", "5-13", "14-26"):
        verdict = a.bands.get(band)
        if verdict is not None:
            out += [*BAND_NUMBERS[band], one_decimal(verdict.shown_error)]
    if a.beyond_horizon_weeks and a.weeks:
        out += [count(a.beyond_horizon_weeks), count(HORIZON_CAP)]
    out += [count(h.count) for h in a.history]
    return out


# --------------------------------------------------------------------------- sentiment


def sentiment(want: Any, trend: dict[str, Any] | None, quotes: list[tuple[str, int]]) -> list[str]:
    """`want` is QA's own recomputation (n_scored, n_comments, complete, counts, flagged,
    shares()); `trend` the expected trend fields or None; `quotes` (confidence, feedback_id)."""
    out: list[str] = []
    if not want.complete:
        out += [count(want.n_scored), count(want.n_comments)]
    if want.n_scored:
        out.append(count(want.n_scored))
        shares = want.shares()
        for label in LABELS:
            out += [count(want.counts[label]), percent1(shares[label])]
        out += [
            count(want.flagged),
            percent1(fraction4(want.flagged, want.n_scored)),
        ]
    if trend is not None and trend.get("latest_n") is not None:
        out += [
            count(trend["latest_negative"]),
            count(trend["latest_n"]),
            percent1(fraction4(trend["latest_negative"], trend["latest_n"])),
            count(trend["earlier_negative"]),
            count(trend["earlier_n"]),
            percent1(fraction4(trend["earlier_negative"], trend["earlier_n"])),
            four_decimals(trend["p_value"]),
        ]
        if trend["small_sample"]:
            out.append(count(MIN_CASES))
    for confidence, feedback_id in quotes:
        out += [confidence, count(feedback_id)]
    return out
