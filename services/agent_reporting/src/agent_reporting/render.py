"""Template-rendered answers. No model writes prose around the figures (ADR-046)."""

from __future__ import annotations

from schemas import IncidentSummary, ReportingAnswer


def _plural(n: int, word: str) -> str:
    return f"{n:,} {word}" + ("" if n == 1 else "s")


def render_incident_summary(summary: IncidentSummary) -> str:
    s = summary.by_severity
    return (
        f"{_plural(summary.incident_count, 'incident')} reported from "
        f"{summary.start.isoformat()} to {summary.end.isoformat()} (inclusive, UTC): "
        f"{s.high:,} high, {s.medium:,} medium, {s.low:,} low severity."
    )


def render_answer(answer: ReportingAnswer) -> str:
    """The as-of date is always stated; an assumed range says so (ADR-050)."""
    lead = f"As of {answer.as_of.isoformat()}: "
    if answer.range_assumed:
        lead += (
            "the question named no dates, so this covers the last full calendar month, "
            f"{answer.start.isoformat()} to {answer.end.isoformat()}. "
        )
    return lead + render_incident_summary(answer.figures)
