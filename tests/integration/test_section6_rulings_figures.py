"""The owner's 2026-10-09 rulings on data dictionary §6 (L-72) against the loaded database: the
tie example keeps Summit Distribution Co. in the 25 shown, "Summit Distribution Co" finds the
account, and QA (written from §6 alone) agrees with the tools on both."""

from __future__ import annotations

import datetime as dt
import os

import pytest
from agent_qa import reporting as qa_reporting
from agent_qa.config import Settings
from agent_qa.db import PostgresSource
from mcp_incidents import metrics as tool_metrics
from mcp_incidents import queries as tool_queries
from schemas import DATASET_WINDOW_END, ReportingAnswer, ReportingRequest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool

pytestmark = [pytest.mark.integration]

AUGUST = (dt.date(2026, 8, 1), dt.date(2026, 8, 30))


def _engine(user_var: str, password_var: str):
    url = URL.create(
        "postgresql+psycopg",
        username=os.environ[user_var],
        password=os.environ[password_var],
        host=os.environ["POSTGRES_HOST"],
        port=int(os.environ["POSTGRES_PORT"]),
        database=os.environ["POSTGRES_DB"],
    )
    return create_engine(url, poolclass=NullPool)


@pytest.fixture(scope="module")
def tools(live_database, loaded_database):
    engine = _engine("DB_ROLE_REPORTING_USER", "DB_ROLE_REPORTING_PASSWORD")
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def qa(live_database, loaded_database):
    engine = _engine("DB_ROLE_QA_USER", "DB_ROLE_QA_PASSWORD")
    yield engine
    engine.dispose()


def test_summit_distribution_co_is_in_the_25_when_39_accounts_tie(tools):
    figures = tool_metrics.first_time_fix_rate(tools, *AUGUST, group_by="account")
    tied = [g for g in figures.groups if g.rate == "1.0000"]
    assert figures.group_count == 43 and len(figures.groups) == 25 and figures.truncated
    # four accounts rank worse than 1.0000; the other 21 places go to the tied accounts, by the
    # number of jobs they rest on, then by name (39 accounts tie in all)
    assert len(tied) == 21
    names = [g.group for g in tied]
    assert names[:2] == ["Pinecrest Manufacturing Group", "Summit Distribution Co."]
    sizes = [g.denominator for g in tied]
    assert sizes == sorted(sizes, reverse=True)


def test_the_account_name_without_its_final_period_finds_the_account(tools):
    with tools.connect() as conn:
        accounts = [
            (r[0], r[1])
            for r in conn.execute(text("SELECT account_id, account_name FROM accounts"))
        ]
    for query in ("Summit Distribution Co", "Summit Distribution Co."):
        found = tool_queries.match_accounts(query, accounts)
        assert [m.account_name for m in found.matches] == ["Summit Distribution Co."]
        assert found.total_matches == 1


def test_qa_agrees_with_the_tools_on_the_tie_example(tools, qa):
    figures = tool_metrics.first_time_fix_rate(tools, *AUGUST, group_by="account")
    settings = Settings(
        db_host=os.environ["POSTGRES_HOST"],
        db_port=int(os.environ["POSTGRES_PORT"]),
        db_name=os.environ["POSTGRES_DB"],
        db_user="unused",
    )
    checker = qa_reporting.Checker(PostgresSource(qa), settings)
    request = ReportingRequest(
        metric="first_time_fix_rate", group_by="account", start=AUGUST[0], end=AUGUST[1]
    )
    answer = ReportingAnswer(
        request=request,
        start=AUGUST[0],
        end=AUGUST[1],
        range_assumed=False,
        as_of=DATASET_WINDOW_END,
        figures=figures,
    )
    checks = checker.check_answer(answer, "")
    assert "figures_match_database" not in {c.code for c in checks if not c.passed}
    # the old order (ties by name only) is no longer accepted
    by_name = sorted(figures.groups, key=lambda g: (g.group_id is None, g.group))
    wrong = figures.model_copy(update={"groups": by_name[:25]})
    wrong_answer = answer.model_copy(update={"figures": wrong})
    assert "figures_match_database" in {
        c.code for c in checker.check_answer(wrong_answer, "") if not c.passed
    }
