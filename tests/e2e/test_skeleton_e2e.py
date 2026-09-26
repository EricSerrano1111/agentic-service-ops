"""End to end through docker-compose: orchestrator → A2A → reporting agent → MCP → Postgres.

Local only: skipped unless `RUN_E2E=1`, with the stack up and the dataset loaded:

    docker compose up -d --build
    set RUN_E2E=1   (PowerShell: $env:RUN_E2E=1)
    .venv\\Scripts\\python -m pytest tests/e2e -q -rs

Checks that every hop is real: the answer comes back as a completed A2A task, its
figures equal an independent SQL computation run as `app_qa`, the orchestrator's trace
id appears in all three services' logs, and the running agent containers hold no
database variables.
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
    pytest.mark.skipif(os.environ.get("RUN_E2E") != "1", reason="set RUN_E2E=1 with compose up"),
]

ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "http://localhost:8000")
SERVICES = ("orchestrator", "agent_reporting", "mcp_incidents")

EXPECTED_SQL = """
    SELECT severity, count(*)
    FROM incidents
    WHERE reported_at >= (%(start)s::date)::timestamp AT TIME ZONE 'UTC'
      AND reported_at <  ((%(end)s::date + 1))::timestamp AT TIME ZONE 'UTC'
    GROUP BY severity
"""


def _compose(*args: str) -> str:
    result = subprocess.run(
        ["docker", "compose", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


@pytest.fixture(scope="module")
def answer() -> dict:
    response = httpx.post(
        f"{ORCHESTRATOR_URL}/ask",
        json={"question": "How many incidents were reported last quarter, by severity?"},
        timeout=130,  # ADR-034: callers wait longer than the 120 s ceiling
    )
    assert response.status_code == 200, response.text
    return response.json()


def _independent_figures(start: str, end: str) -> dict:
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


def test_answer_is_a_completed_task_with_correct_figures(answer):
    figures = answer["figures"]
    assert figures == _independent_figures(figures["start"], figures["end"])
    assert figures["incident_count"] > 0
    assert f"{figures['incident_count']:,} incident" in answer["answer"]
    assert answer["task_id"]
    assert answer["route"] == "reporting"


def test_trace_id_appears_in_all_three_services(answer):
    trace_id = answer["trace_id"]
    for service in SERVICES:
        lines = []
        for raw in _compose("logs", "--no-log-prefix", service).splitlines():
            try:
                lines.append(json.loads(raw))
            except json.JSONDecodeError:
                continue  # e.g. a Python warning printed before logging is configured
        traced = [line for line in lines if line.get("trace_id") == trace_id]
        assert traced, f"trace id {trace_id} not found in {service} logs"


@pytest.mark.parametrize("service", ["agent_reporting", "orchestrator"])
def test_running_agent_containers_hold_no_database_variables(service):
    container = _compose("ps", "-q", service).strip()
    assert container, f"{service} is not running"
    env = json.loads(
        subprocess.run(
            ["docker", "inspect", "--format", "{{json .Config.Env}}", container],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    leaked = [kv.split("=", 1)[0] for kv in env if kv.startswith(("POSTGRES_", "DB_ROLE_"))]
    assert leaked == []
