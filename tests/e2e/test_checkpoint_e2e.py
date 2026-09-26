"""R-06 checkpoint 2: an LLM-routed, LLM-parsed question answered end to end.

Calls Gemini through the running stack (free key; about four requests: three routing
calls on the orchestrator's model and one parse). Local only, never in CI. Skipped
unless both flags are set, with the stack up and the dataset loaded:

    docker compose up -d --build
    $env:RUN_E2E=1; $env:RUN_LIVE_LLM=1
    .venv\\Scripts\\python -m pytest tests/e2e/test_checkpoint_e2e.py -v -rs

Checks: "last month" routes to reporting and parses to the calendar month before the
as-of date (July 2026 with the default as-of date 2026-08-30, ADR-050); the figures equal
an independent SQL computation run as `app_qa` for the range the agent reports; the
trace id appears in all three services' logs; an out-of-scope question is declined and
a sentiment question answered as not available yet, neither reaching the agent.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
from pathlib import Path

import httpx
import psycopg
import pytest
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env", override=False)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("RUN_E2E") != "1" or os.environ.get("RUN_LIVE_LLM") != "1",
        reason="set RUN_E2E=1 and RUN_LIVE_LLM=1 with compose up (calls Gemini)",
    ),
]

ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "http://localhost:8000")
SERVICES = ("orchestrator", "agent_reporting", "mcp_incidents")
LAST_MONTH = "How many incidents were reported last month?"

EXPECTED_SQL = """
    SELECT severity, count(*)
    FROM incidents
    WHERE reported_at >= (%(start)s::date)::timestamp AT TIME ZONE 'UTC'
      AND reported_at <  ((%(end)s::date + 1))::timestamp AT TIME ZONE 'UTC'
    GROUP BY severity
"""


def ask(question: str) -> httpx.Response:
    return httpx.post(
        f"{ORCHESTRATOR_URL}/ask",
        json={"question": question},
        timeout=130,  # ADR-034: callers wait longer than the 120 s ceiling
    )


def previous_month(as_of: dt.date) -> tuple[dt.date, dt.date]:
    end = as_of.replace(day=1) - dt.timedelta(days=1)
    return end.replace(day=1), end


def independent_figures(start: str, end: str) -> dict:
    with psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["DB_ROLE_QA_USER"],
        password=os.environ["DB_ROLE_QA_PASSWORD"],
        connect_timeout=5,
    ) as conn:
        rows = conn.execute(
            EXPECTED_SQL,
            {"start": dt.date.fromisoformat(start), "end": dt.date.fromisoformat(end)},
        ).fetchall()
    by_severity = {"low": 0, "medium": 0, "high": 0} | dict(rows)
    return {
        "start": start,
        "end": end,
        "incident_count": sum(by_severity.values()),
        "by_severity": by_severity,
    }


def compose_logs(service: str) -> list[dict]:
    raw = subprocess.run(
        ["docker", "compose", "logs", "--no-log-prefix", service],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    ).stdout
    lines = []
    for line in raw.splitlines():
        try:
            lines.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return lines


@pytest.fixture(scope="module")
def last_month() -> dict:
    response = ask(LAST_MONTH)
    assert response.status_code == 200, response.text
    return response.json()


def test_last_month_routes_to_reporting(last_month):
    assert last_month["route"]["route"] == "reporting"
    assert last_month["outcome"] == "answered"
    assert last_month["prompt_version"] == "route_v1"


def test_last_month_parses_to_the_month_before_the_as_of_date(last_month):
    reporting = last_month["reporting"]
    as_of = dt.date.fromisoformat(reporting["as_of"])
    start, end = previous_month(as_of)
    assert (reporting["start"], reporting["end"]) == (start.isoformat(), end.isoformat())
    assert reporting["range_assumed"] is False  # "last month" is a stated period
    if as_of == dt.date(2026, 8, 30):  # the default as-of date (ADR-050)
        assert (reporting["start"], reporting["end"]) == ("2026-07-01", "2026-07-31")
    assert f"As of {reporting['as_of']}" in last_month["answer"]


def test_figures_match_independent_sql_for_the_reported_range(last_month):
    reporting = last_month["reporting"]
    figures = reporting["figures"]
    assert figures == independent_figures(reporting["start"], reporting["end"])
    assert figures["incident_count"] > 0


def test_trace_id_appears_in_all_three_services(last_month):
    trace_id = last_month["trace_id"]
    for service in SERVICES:
        traced = [line for line in compose_logs(service) if line.get("trace_id") == trace_id]
        assert traced, f"trace id {trace_id} not found in {service} logs"


def test_out_of_scope_question_is_declined():
    response = ask("What's the weather forecast for Chicago tomorrow?")
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["route"]["route"], body["outcome"]) == ("out_of_scope", "declined")
    assert body["task_id"] is None and body["reporting"] is None


def test_sentiment_question_is_answered_as_not_available_yet():
    response = ask("What share of customer feedback comments were negative last month?")
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["route"]["route"], body["outcome"]) == ("sentiment", "not_available")
    assert body["task_id"] is None
