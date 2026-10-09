"""QA's own SQL agrees with the incidents tools on the loaded database (ADR-087).

QA writes its metric queries from data dictionary §6 and imports none of the tools' code; the
tools were written from the same definitions. This suite is the test that the two readings are
the same wherever the data exercises them: every metric, every breakdown, every filter
combination the tools accept, and the repeat-driver significance tests, over three ranges (a
month, the regional-outage fortnight and the full window). A disagreement here is either a bug
in one of the two or a gap in §6, and either is worth knowing before QA gates anything.

It also shows the checks have teeth: perturbing one figure of a real answer makes the matching
check fail. Needs a migrated and loaded database (CI loads one before this runs).
"""

from __future__ import annotations

import datetime as dt
import os

import pytest
from agent_qa import reporting as qa_reporting
from agent_qa.config import Settings
from agent_qa.db import PostgresSource
from agent_reporting.render import render_answer
from mcp_incidents import metrics as tool_metrics
from mcp_incidents import queries as tool_queries
from mcp_incidents import repeats as tool_repeats
from schemas import DATASET_WINDOW_END, DATASET_WINDOW_START, ReportingAnswer, ReportingRequest
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool

pytestmark = [pytest.mark.integration]

JULY = (dt.date(2026, 7, 1), dt.date(2026, 7, 31))
ANOMALY = (dt.date(2025, 2, 17), dt.date(2025, 3, 2))
FULL = (DATASET_WINDOW_START, DATASET_WINDOW_END)
RANGES = [JULY, ANOMALY, FULL]
RATE_BREAKDOWNS = ["account", "region", "service_type", "technician"]
COUNT_BREAKDOWNS = [*RATE_BREAKDOWNS, "incident_type", "severity"]
REPEAT_BREAKDOWNS = ["incident_type", "service_type", "region", "account", "technician"]
RATE_TOOLS = {
    "incident_rate": tool_metrics.incident_rate,
    "sla_compliance": tool_metrics.sla_compliance,
    "first_time_fix_rate": tool_metrics.first_time_fix_rate,
}


def _engine(user: str, password: str):
    url = URL.create(
        "postgresql+psycopg",
        username=user,
        password=password,
        host=os.environ["POSTGRES_HOST"],
        port=int(os.environ["POSTGRES_PORT"]),
        database=os.environ["POSTGRES_DB"],
    )
    return create_engine(url, poolclass=NullPool)


@pytest.fixture(scope="module")
def tools(live_database, loaded_database):
    engine = _engine(os.environ["DB_ROLE_REPORTING_USER"], os.environ["DB_ROLE_REPORTING_PASSWORD"])
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def checker(live_database, loaded_database):
    engine = _engine(os.environ["DB_ROLE_QA_USER"], os.environ["DB_ROLE_QA_PASSWORD"])
    settings = Settings(
        db_host=os.environ["POSTGRES_HOST"],
        db_port=int(os.environ["POSTGRES_PORT"]),
        db_name=os.environ["POSTGRES_DB"],
        db_user="unused",
    )
    yield qa_reporting.Checker(PostgresSource(engine), settings)
    engine.dispose()


@pytest.fixture(scope="module")
def people(tools):
    technician = tool_queries.find_technician(tools, "Ben Okafor").matches[0]
    account = tool_queries.match_accounts(
        "Cedar Ridge Retail", [(r[0], r[1]) for r in _accounts(tools)]
    ).matches[0]
    return technician, account


def _accounts(engine):
    with engine.connect() as conn:
        from sqlalchemy import text

        return conn.execute(text("SELECT account_id, account_name FROM accounts")).all()


def answer_for(figures, request: ReportingRequest, span) -> ReportingAnswer:
    return ReportingAnswer(
        request=request,
        start=span[0],
        end=span[1],
        range_assumed=False,
        as_of=DATASET_WINDOW_END,
        figures=figures,
    )


def request_for(metric, span, **fields) -> ReportingRequest:
    return ReportingRequest(metric=metric, start=span[0], end=span[1], **fields)


def failed(checks):
    return {c.code for c in checks if not c.passed}


def assert_agrees(checker, answer: ReportingAnswer):
    checks = checker.check_answer(answer, render_answer(answer))
    assert failed(checks) == set(), [(c.code, c.detail) for c in checks if not c.passed]


# --------------------------------------------------------------------------- incident counts


@pytest.mark.parametrize("span", RANGES)
@pytest.mark.parametrize("group_by", [None, *COUNT_BREAKDOWNS])
def test_incident_counts_agree(tools, checker, span, group_by):
    figures = tool_queries.count_by_severity(tools, *span, group_by=group_by)
    assert_agrees(checker, answer_for(figures, request_for("incident_count", span, group_by=group_by), span))


@pytest.mark.parametrize("span", RANGES)
def test_filtered_incident_counts_agree(tools, checker, people, span):
    technician, account = people
    cases = [
        ({"region": "west"}, {"region": "west"}),
        ({"region": "west"}, {"region": "west", "group_by": "account"}),
        ({"account_id": account.account_id}, {"account_name": account.account_name}),
        (
            {"account_id": account.account_id, "region": "northeast"},
            {"account_name": account.account_name, "region": "northeast", "group_by": "incident_type"},
        ),
        ({"technician_id": technician.technician_id}, {"technician_name": technician.full_name}),
        (
            {"technician_id": technician.technician_id, "region": "central"},
            {"technician_name": technician.full_name, "region": "central"},
        ),
    ]
    for tool_args, request_fields in cases:
        group_by = request_fields.get("group_by")
        figures = tool_queries.count_by_severity(tools, *span, group_by=group_by, **tool_args)
        assert_agrees(
            checker, answer_for(figures, request_for("incident_count", span, **request_fields), span)
        )


# --------------------------------------------------------------------------- rate metrics


@pytest.mark.parametrize("span", RANGES)
@pytest.mark.parametrize("metric", list(RATE_TOOLS))
@pytest.mark.parametrize("group_by", [None, *RATE_BREAKDOWNS])
def test_rate_metrics_agree(tools, checker, metric, span, group_by):
    figures = RATE_TOOLS[metric](tools, *span, group_by=group_by)
    assert_agrees(checker, answer_for(figures, request_for(metric, span, group_by=group_by), span))


@pytest.mark.parametrize("span", RANGES)
@pytest.mark.parametrize("metric", list(RATE_TOOLS))
def test_filtered_rate_metrics_agree(tools, checker, people, metric, span):
    technician, account = people
    cases = [
        ({"region": "southeast"}, {"region": "southeast"}),
        ({"region": "west"}, {"region": "west", "group_by": "account"}),
        ({"account_id": account.account_id}, {"account_name": account.account_name}),
        (
            {"account_id": account.account_id, "region": "west"},
            {"account_name": account.account_name, "region": "west"},
        ),
        ({"technician_id": technician.technician_id}, {"technician_name": technician.full_name}),
        (
            {"technician_id": technician.technician_id, "account_id": account.account_id},
            {"technician_name": technician.full_name, "account_name": account.account_name},
        ),
    ]
    for tool_args, request_fields in cases:
        figures = RATE_TOOLS[metric](tools, *span, group_by=request_fields.get("group_by"), **tool_args)
        assert_agrees(checker, answer_for(figures, request_for(metric, span, **request_fields), span))


# --------------------------------------------------------------------------- repeat drivers


@pytest.mark.parametrize("span", RANGES)
@pytest.mark.parametrize("by", REPEAT_BREAKDOWNS)
def test_repeat_drivers_agree(tools, checker, span, by):
    figures = tool_repeats.repeat_drivers(tools, *span, by)
    request = request_for("repeat_visit_drivers", span, group_by=by)
    assert_agrees(checker, answer_for(figures, request, span))


# --------------------------------------------------------------------------- teeth


def test_a_perturbed_total_is_caught(tools, checker):
    figures = tool_metrics.sla_compliance(tools, *JULY)
    wrong = figures.model_copy(update={"numerator": figures.numerator - 1})
    answer = answer_for(wrong, request_for("sla_compliance", JULY), JULY)
    checks = checker.check_answer(answer, render_answer(answer))
    assert "figures_match_database" in failed(checks)


def test_a_perturbed_group_is_caught(tools, checker):
    figures = tool_metrics.first_time_fix_rate(tools, *FULL, group_by="region")
    first = figures.groups[0]
    groups = [first.model_copy(update={"denominator": first.denominator + 1}), *figures.groups[1:]]
    wrong = figures.model_copy(update={"groups": groups})
    answer = answer_for(wrong, request_for("first_time_fix_rate", FULL, group_by="region"), FULL)
    assert "figures_match_database" in failed(checker.check_answer(answer, ""))


def test_a_swapped_group_order_is_caught(tools, checker):
    figures = tool_metrics.incident_rate(tools, *FULL, group_by="account")
    groups = list(figures.groups)
    groups[0], groups[-1] = groups[-1], groups[0]
    wrong = figures.model_copy(update={"groups": groups})
    answer = answer_for(wrong, request_for("incident_rate", FULL, group_by="account"), FULL)
    assert "figures_match_database" in failed(checker.check_answer(answer, ""))


def test_a_wrong_range_is_caught(tools, checker):
    figures = tool_queries.count_by_severity(tools, *JULY)
    answer = ReportingAnswer(
        request=request_for("incident_count", JULY),
        start=JULY[0],
        end=JULY[1],
        range_assumed=False,
        as_of=DATASET_WINDOW_END,
        figures=figures,
    )
    stale = answer.model_copy(update={"as_of": dt.date(2026, 8, 1)})
    assert "range_matches_request" in failed(checker.check_answer(stale, ""))


def test_a_stale_number_in_the_text_is_caught(tools, checker):
    figures = tool_queries.count_by_severity(tools, *JULY)
    answer = answer_for(figures, request_for("incident_count", JULY), JULY)
    text = render_answer(answer).replace(f"{figures.incident_count:,} incident", "7,777 incident")
    assert "text_matches_data" in failed(checker.check_answer(answer, text))


def test_a_misattributed_technician_is_caught(tools, checker, people):
    technician, _ = people
    figures = tool_queries.count_by_severity(tools, *JULY, technician_id=technician.technician_id)
    other = tool_queries.find_technician(tools, "Priya").matches[0]
    request = request_for("incident_count", JULY, technician_name=other.full_name)
    answer = answer_for(figures, request, JULY)
    assert "filters_match_request" in failed(checker.check_answer(answer, ""))


def test_qa_disagrees_with_a_changed_repeat_rule(tools, checker):
    figures = tool_repeats.repeat_drivers(tools, *FULL, "region")
    flipped = [g.model_copy(update={"stands_out": not g.stands_out}) for g in figures.groups[:1]]
    wrong = figures.model_copy(update={"groups": [*flipped, *figures.groups[1:]]})
    answer = answer_for(wrong, request_for("repeat_visit_drivers", FULL, group_by="region"), FULL)
    assert "figures_match_database" in failed(checker.check_answer(answer, ""))
