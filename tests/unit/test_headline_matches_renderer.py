"""The gateway's headline figure is a substring of what the reporting renderer actually prints.

The gateway formats the figure itself so it need not import the reporting agent (ADR-079's least
privilege); this holds the two together (data dictionary §6, rule 8). A change to the renderer's
wording that the gateway no longer finds drops the headline, and this test fails first.
"""

from __future__ import annotations

import datetime as dt

import pytest
from agent_reporting.render import render_answer
from api_gateway.interpret import headline
from schemas import (
    FirstTimeFixResult,
    IncidentRateResult,
    IncidentSummary,
    ReportingAnswer,
    ReportingRequest,
    SlaComplianceResult,
)
from schemas.incidents import SeverityCounts
from schemas.metrics import rate_string

START, END = dt.date(2026, 8, 1), dt.date(2026, 8, 30)


def answer(metric: str, figures, **request) -> ReportingAnswer:
    return ReportingAnswer(
        request=ReportingRequest(metric=metric, start=START, end=END, **request),
        start=START,
        end=END,
        range_assumed=False,
        as_of=END,
        figures=figures,
    )


def body_for(a: ReportingAnswer) -> dict:
    return {
        "answer": render_answer(a),
        "outcome": "answered",
        "qa_status": "verified",
        "route": {"route": "reporting"},
        "reporting": a.model_dump(mode="json"),
    }


def share(cls, n: int, d: int, **kw):
    return cls(start=START, end=END, numerator=n, denominator=d, rate=rate_string(n, d), **kw)


@pytest.mark.parametrize("region", [None, "northeast"])
@pytest.mark.parametrize(
    ("metric", "cls"),
    [("sla_compliance", SlaComplianceResult), ("first_time_fix_rate", FirstTimeFixResult)],
)
@pytest.mark.parametrize(("n", "d"), [(141, 160), (1, 1), (1234, 1500), (3, 7)])
def test_a_rendered_share_answer_keeps_its_headline(metric, cls, region, n, d):
    a = answer(metric, share(cls, n, d, region=region), region=region)
    body = body_for(a)
    result = headline(body, body["answer"])
    assert result is not None, body["answer"]
    assert result["figure"] in body["answer"]
    assert f"{n:,} of {d:,} " in result["caption"]


@pytest.mark.parametrize("region", [None, "west"])
@pytest.mark.parametrize("count", [0, 1, 5, 1204])
def test_a_rendered_count_answer_keeps_its_headline(count, region):
    high = min(count, 1)
    figures = IncidentSummary(
        start=START,
        end=END,
        incident_count=count,
        by_severity=SeverityCounts(high=high, medium=count - high, low=0),
        region=region,
    )
    body = body_for(answer("incident_count", figures, region=region))
    result = headline(body, body["answer"])
    assert result is not None, body["answer"]
    assert result["figure"] == f"{count:,}"


def test_a_rendered_incident_rate_answer_has_none():
    body = body_for(answer("incident_rate", share(IncidentRateResult, 12, 300)))
    assert headline(body, body["answer"]) is None
