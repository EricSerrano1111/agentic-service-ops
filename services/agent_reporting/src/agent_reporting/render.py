"""Template-rendered answers, one template per metric. No model writes prose around the
figures (ADR-046). Every answer states the as-of date and the range (ADR-050); every
rate is shown with the counts behind it (ADR-033); grouped answers rank the worst
`TEXT_GROUPS` groups that have enough cases, with the full list in the data part.
"""

from __future__ import annotations

from decimal import Decimal

from schemas import (
    GroupRate,
    IncidentRateResult,
    IncidentSummary,
    ReportingAnswer,
    SlaComplianceResult,
)

TEXT_GROUPS = 5
#: Groups with fewer cases than this are left out of the ranked text (not the data).
#: Configurable per deployment: REPORTING_MIN_GROUP_DENOMINATOR.
DEFAULT_MIN_GROUP_DENOMINATOR = 20

_DIMENSION = {
    "account": "account",
    "region": "region",
    "service_type": "service type",
    "technician": "technician",
}


def _plural(n: int, word: str) -> str:
    return f"{n:,} {word}" + ("" if n == 1 else "s")


def _span(start, end) -> str:
    return f"from {start.isoformat()} to {end.isoformat()} (inclusive, UTC)"


def _percent(rate: str) -> str:
    """A 4-place fraction as a 2-place percentage, exactly: "0.8881" -> "88.81%"."""
    return f"{Decimal(rate) * 100:.2f}%"


def render_incident_summary(summary: IncidentSummary) -> str:
    s = summary.by_severity
    return (
        f"{_plural(summary.incident_count, 'incident')} reported "
        f"{_span(summary.start, summary.end)}: "
        f"{s.high:,} high, {s.medium:,} medium, {s.low:,} low severity."
    )


# --------------------------------------------------------------------------- per metric


def _incident_rate_overall(r: IncidentRateResult) -> str:
    if r.rate is None:
        return (
            f"No requests were completed {_span(r.start, r.end)}, so there is no incident "
            f"rate ({_plural(r.numerator, 'incident')} reported)."
        )
    return (
        f"{r.rate} incidents per 100 completed requests {_span(r.start, r.end)}: "
        f"{_plural(r.numerator, 'incident')} over "
        f"{_plural(r.denominator, 'completed request')}."
    )


def _incident_rate_group(g: GroupRate) -> str:
    counts = f"{g.numerator:,} of {_plural(g.denominator, 'completed job')}"
    if g.rate is None:
        return f"{g.group}: no completed jobs ({_plural(g.numerator, 'incident')})"
    return f"{g.group} {g.rate} per 100 ({counts.replace(' of ', ' incidents / ', 1)})"


def _share_overall(r, what: str, over: str, success: str, none: str) -> str:
    if r.rate is None:
        return f"{none} {_span(r.start, r.end)}, so there is no {what} figure."
    return (
        f"{what[0].upper()}{what[1:]} was {_percent(r.rate)} {_span(r.start, r.end)}: "
        f"{r.numerator:,} of {r.denominator:,} {over} {success}."
    )


def _share_group(g: GroupRate) -> str:
    if g.rate is None:
        return f"{g.group}: no qualifying requests"
    return f"{g.group} {_percent(g.rate)} ({g.numerator:,} of {g.denominator:,})"


def _overall(figures) -> str:
    if isinstance(figures, IncidentRateResult):
        return _incident_rate_overall(figures)
    if isinstance(figures, SlaComplianceResult):
        return _share_overall(
            figures,
            "SLA compliance",
            "dispatched requests",
            "were completed within their SLA window",
            "No dispatched requests were completed",
        )
    return _share_overall(
        figures,
        "first-time fix rate",
        "completed requests",
        "needed no return visit",
        "No requests were completed",
    )


def _groups(figures, min_denominator: int) -> str:
    """Rank the worst groups with enough cases; say how many were left out.

    A presentation rule, not a metric definition: a group with fewer than
    `min_denominator` cases (completed jobs, dispatched requests) can top the ranking
    on one incident. It is left out of the text only; the data part keeps every group
    the tool returned, with its counts.
    """
    dimension = _DIMENSION[figures.group_by]
    eligible = [g for g in figures.groups if g.denominator >= min_denominator]
    left_out = len(figures.groups) - len(eligible)
    fmt = _incident_rate_group if isinstance(figures, IncidentRateResult) else _share_group
    if eligible:
        listed = "; ".join(fmt(g) for g in eligible[:TEXT_GROUPS])
        text = f" By {dimension}, worst first: {listed}."
    else:
        text = f" By {dimension}: no {dimension} has at least {min_denominator} cases to rank."
    if left_out:
        noun = dimension if left_out == 1 else f"{dimension}s"
        text += (
            f" {left_out} {noun} left out of the ranking for fewer than {min_denominator} "
            "cases; all are in the data."
        )
    if figures.truncated:
        text += (
            f" {figures.group_count} {dimension}s in total; the worst "
            f"{len(figures.groups)} are in the data."
        )
    if isinstance(figures, IncidentRateResult) and figures.group_by == "technician":
        text += (
            " Technician incident counts cover attributable incidents only (ADR-033), so "
            "they don't sum to the total."
        )
    return text


def render_answer(
    answer: ReportingAnswer, min_denominator: int = DEFAULT_MIN_GROUP_DENOMINATOR
) -> str:
    """The as-of date is always stated; an assumed range says so (ADR-050)."""
    lead = f"As of {answer.as_of.isoformat()}: "
    if answer.range_assumed:
        lead += (
            "the question named no dates, so this covers the last full calendar month, "
            f"{answer.start.isoformat()} to {answer.end.isoformat()}. "
        )
    figures = answer.figures
    if isinstance(figures, IncidentSummary):
        return lead + render_incident_summary(figures)
    body = _overall(figures)
    if figures.group_by is not None:
        body += _groups(figures, min_denominator)
    return lead + body
