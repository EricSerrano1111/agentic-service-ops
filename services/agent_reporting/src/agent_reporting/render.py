"""Template-rendered answers. No model writes prose around the figures (ADR-046)."""

from __future__ import annotations

from schemas import IncidentSummary


def _plural(n: int, word: str) -> str:
    return f"{n:,} {word}" + ("" if n == 1 else "s")


def render_incident_summary(summary: IncidentSummary) -> str:
    s = summary.by_severity
    return (
        f"{_plural(summary.incident_count, 'incident')} reported from "
        f"{summary.start.isoformat()} to {summary.end.isoformat()} (inclusive, UTC): "
        f"{s.high:,} high, {s.medium:,} medium, {s.low:,} low severity."
    )
