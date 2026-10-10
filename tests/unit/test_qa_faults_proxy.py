"""The loop demonstration's fault-injecting proxy changes one count and re-renders the text
(Prompt N, section 6). Offline: only the mutation function is exercised."""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

PROXY = Path(__file__).resolve().parents[2] / "evals" / "qa_faults" / "proxy"
sys.path.insert(0, str(PROXY))

import proxy  # noqa: E402
from schemas import IncidentSummary, ReportingAnswer, ReportingRequest, SeverityCounts  # noqa: E402


def _answer() -> ReportingAnswer:
    start, end = dt.date(2026, 7, 1), dt.date(2026, 7, 31)
    return ReportingAnswer(
        request=ReportingRequest(metric="incident_count", start=start, end=end),
        start=start,
        end=end,
        range_assumed=False,
        as_of=dt.date(2026, 8, 30),
        figures=IncidentSummary(
            start=start,
            end=end,
            incident_count=54,
            by_severity=SeverityCounts(low=36, medium=12, high=6),
        ),
    )


def test_r01_adds_one_to_the_count_and_the_text_follows_the_data():
    data, text = proxy.mutate_r01(_answer().model_dump(mode="json"))
    assert data["figures"]["incident_count"] == 55
    assert data["figures"]["by_severity"] == {"low": 36, "medium": 13, "high": 6}
    assert "55 incidents" in text and "54 incidents" not in text
