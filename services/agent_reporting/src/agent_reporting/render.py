"""Template-rendered answers, one template per metric. No model writes prose around the
figures (ADR-046). Every answer states the as-of date and the range (ADR-050); every
rate is shown with the counts behind it (ADR-033); grouped answers rank the worst
`TEXT_GROUPS` groups that have enough cases, with the full list in the data part.

ADR-073: incident counts by breakdown list the highest counts; a single technician's
figure says how many cases it rests on, and flags fewer than the group minimum as too
few to compare reliably; repeat-visit drivers open with the repeat count and rate and
the fact that every repeat is recorded through a repeat-visit-required incident, then
say which groups stand out (or that none does), worst first.
"""

from __future__ import annotations

from decimal import Decimal

from schemas import (
    MIN_GROUP_JOBS,
    UNATTRIBUTED,
    GroupRate,
    IncidentRateResult,
    IncidentSummary,
    RepeatDriversResult,
    RepeatGroup,
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
    "incident_type": "incident type",
    "severity": "severity",
}
ASSOCIATION_CAVEAT = (
    "Jobs with several incidents are more likely to need a repeat visit; this shows "
    "association, not cause."
)
COHERENCE = (
    "Every repeat visit is recorded through a repeat-visit-required incident on the original job."
)
TOO_FEW = "too few to compare reliably"


def _label(group: str, group_by: str | None) -> str:
    """Vocabulary values read as words ("wrong_dispatch_info" -> "wrong dispatch info")."""
    return group.replace("_", " ") if group_by in ("incident_type", "severity") else group


def _plural(n: int, word: str) -> str:
    return f"{n:,} {word}" + ("" if n == 1 else "s")


def _span(start, end) -> str:
    return f"from {start.isoformat()} to {end.isoformat()} (inclusive, UTC)"


def _percent(rate: str) -> str:
    """A 4-place fraction as a 2-place percentage, exactly: "0.8881" -> "88.81%"."""
    return f"{Decimal(rate) * 100:.2f}%"


def render_incident_summary(summary: IncidentSummary) -> str:
    s = summary.by_severity
    whose = ""
    if summary.technician_name is not None:
        # No denominator: the count attributed to the technician is the whole answer.
        whose = f" attributed to {summary.technician_name}"
    text = (
        f"{_plural(summary.incident_count, 'incident')}{whose} reported "
        f"{_span(summary.start, summary.end)}: "
        f"{s.high:,} high, {s.medium:,} medium, {s.low:,} low severity."
    )
    if summary.groups is not None:
        text += _count_groups(summary)
    return text


def _count_groups(summary: IncidentSummary) -> str:
    dimension = _DIMENSION[summary.group_by]
    shown = summary.groups[:TEXT_GROUPS]
    listed = "; ".join(f"{_label(g.group, summary.group_by)} {g.count:,}" for g in shown)
    text = f" By {dimension}, highest first: {listed}."
    rest = summary.group_count - len(shown)
    if rest > 0:
        text += f" {rest} more {dimension} groups are in the data."
    if summary.truncated:
        text += (
            f" {summary.group_count} groups in total; the top {len(summary.groups)} are in "
            "the data, so their counts don't sum to the total."
        )
    if summary.group_by == "technician" and any(g.group == UNATTRIBUTED for g in summary.groups):
        text += " Incidents attributed to no technician are counted as unattributed."
    return text


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


# --------------------------------------------------------------------------- one technician


def _for_technician(figures, min_denominator: int) -> str:
    """A metric filtered to one technician: the figure and the cases it rests on."""
    name, span, n = figures.technician_name, _span(figures.start, figures.end), figures.denominator
    if isinstance(figures, IncidentRateResult):
        noun = "completed request"
        if figures.rate is None:
            return f"{name} completed no requests {span}, so there is no incident rate."
        text = (
            f"For {name}, {figures.rate} incidents per 100 completed requests {span}: "
            f"{_plural(figures.numerator, 'attributed incident')}, based on {_plural(n, noun)}."
        )
    elif isinstance(figures, SlaComplianceResult):
        noun = "dispatched request"
        if figures.rate is None:
            return f"{name} completed no dispatched requests {span}, so there is no SLA figure."
        text = (
            f"For {name}, SLA compliance was {_percent(figures.rate)} {span}, based on "
            f"{_plural(n, noun)}: {figures.numerator:,} completed within their SLA window."
        )
    else:
        noun = "completed request"
        if figures.rate is None:
            return f"{name} completed no requests {span}, so there is no first-time fix rate."
        text = (
            f"For {name}, the first-time fix rate was {_percent(figures.rate)} {span}, based "
            f"on {_plural(n, noun)}: {figures.numerator:,} needed no return visit."
        )
    if n < min_denominator:
        text += f" That is {TOO_FEW}."
    return text


# --------------------------------------------------------------------------- repeat drivers


def _repeat_group(g: RepeatGroup, group_by: str) -> str:
    return (
        f"{_label(g.group, group_by)} {_percent(g.this.rate)} "
        f"({g.this.repeated:,} of {_plural(g.this.jobs, 'job')})"
    )


def render_repeat_drivers(r: RepeatDriversResult, min_denominator: int) -> str:
    span = _span(r.start, r.end)
    if r.overall.jobs == 0:
        return f"No jobs were completed {span}, so there are no repeat visits to compare."
    text = (
        f"{r.overall.repeated:,} of {_plural(r.overall.jobs, 'job')} completed {span} "
        f"needed a repeat visit ({_percent(r.overall.rate)}). {COHERENCE}"
    )
    dimension = _DIMENSION[r.group_by]
    if r.group_by == "incident_type":
        dimension = "other incident type"
    standouts = [g for g in r.groups if g.stands_out]
    if standouts:
        named = "; ".join(
            f"{_repeat_group(g, r.group_by)}, against {_percent(g.rest.rate)} for the rest"
            for g in standouts
        )
        text += f" Higher than the rest, beyond what chance explains: {named}."
    else:
        text += (
            f" No {dimension} stands out: no difference is larger than chance would explain "
            f"(Fisher's exact test, Bonferroni-corrected, groups with at least "
            f"{MIN_GROUP_JOBS} jobs)."
        )
    eligible = [g for g in r.groups if g.this.jobs >= min_denominator]
    if eligible:
        listed = "; ".join(_repeat_group(g, r.group_by) for g in eligible[:TEXT_GROUPS])
        text += f" By {dimension}, worst first: {listed}."
    left_out = len(r.groups) - len(eligible)
    if left_out:
        text += (
            f" {left_out} with fewer than {min_denominator} jobs left out of the list; all "
            "are in the data."
        )
    if r.truncated:
        text += f" {r.group_count} groups in total; the worst {len(r.groups)} are in the data."
    if r.group_by == "incident_type":
        a, n = r.any_other_incident, r.no_other_incident
        text += (
            f" Jobs with any other incident: {_rate_or_none(a)}; jobs with none: "
            f"{_rate_or_none(n)}. {ASSOCIATION_CAVEAT}"
        )
    return text


def _rate_or_none(j) -> str:
    if j.rate is None:
        return "no jobs"
    return f"{_percent(j.rate)} ({j.repeated:,} of {_plural(j.jobs, 'job')})"


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
    if isinstance(figures, RepeatDriversResult):
        return lead + render_repeat_drivers(figures, min_denominator)
    if figures.technician_id is not None:
        return lead + _for_technician(figures, min_denominator)
    body = _overall(figures)
    if figures.group_by is not None:
        body += _groups(figures, min_denominator)
    return lead + body
