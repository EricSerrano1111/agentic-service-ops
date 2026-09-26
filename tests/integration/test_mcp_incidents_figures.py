"""The incidents MCP tool's figures equal an independent SQL computation.

The tool runs in-process through a real MCP client and queries the live database as
`app_reporting`, with that role's own credentials. The expected figures come from
hand-written SQL run as `app_qa`: a different role, a different code path, and no
SQLAlchemy, the shape of the check the Sprint 4 QA agent will make (architecture §3).

Needs a migrated *and loaded* database. CI loads it with `load.py` before this runs.
"""

from __future__ import annotations

import datetime as dt
import os
from collections.abc import Callable

import psycopg
import pytest
from db_models.access_matrix import ROLE_QA
from mcp import Client
from mcp_incidents.config import DEFAULT_WINDOW_END, DEFAULT_WINDOW_START, Settings
from mcp_incidents.server import TOOL_NAME, create_server
from schemas import IncidentSummary

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

ConnectAs = Callable[[str], psycopg.Connection]

RANGES = [
    (DEFAULT_WINDOW_START, DEFAULT_WINDOW_END),  # the whole window
    (dt.date(2026, 6, 1), dt.date(2026, 8, 30)),  # the skeleton's configured range
    (dt.date(2024, 2, 29), dt.date(2024, 2, 29)),  # one day
    (dt.date(2025, 1, 1), dt.date(2025, 12, 31)),
]

# Independent of the tool: literal SQL, UTC day boundaries, inclusive end day.
EXPECTED_SQL = """
    SELECT severity, count(*)
    FROM incidents
    WHERE reported_at >= (%(start)s::date)::timestamp AT TIME ZONE 'UTC'
      AND reported_at <  ((%(end)s::date + 1))::timestamp AT TIME ZONE 'UTC'
    GROUP BY severity
"""


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
def reporting_settings(live_database: None) -> Settings:
    return Settings(
        db_host=os.environ["POSTGRES_HOST"],
        db_port=int(os.environ["POSTGRES_PORT"]),
        db_name=os.environ["POSTGRES_DB"],
        db_user=os.environ["DB_ROLE_REPORTING_USER"],
        db_password=os.environ["DB_ROLE_REPORTING_PASSWORD"],
    )


@pytest.mark.parametrize(("start", "end"), RANGES, ids=lambda d: d.isoformat())
async def test_tool_figures_match_independent_sql(
    loaded_database, connect_as: ConnectAs, reporting_settings: Settings, start, end
):
    async with Client(create_server(reporting_settings)) as client:
        result = await client.call_tool(
            TOOL_NAME, {"start": start.isoformat(), "end": end.isoformat()}
        )
    assert not result.is_error, result.content
    got = IncidentSummary.model_validate(result.structured_content)

    rows = connect_as(ROLE_QA).execute(EXPECTED_SQL, {"start": start, "end": end}).fetchall()
    expected = {"low": 0, "medium": 0, "high": 0} | dict(rows)

    assert got.by_severity.model_dump() == expected
    assert got.incident_count == sum(expected.values())
    assert (got.start, got.end) == (start, end)


async def test_whole_window_covers_every_incident(loaded_database, connect_as, reporting_settings):
    """No incident falls outside the window the tool accepts."""
    async with Client(create_server(reporting_settings)) as client:
        result = await client.call_tool(
            TOOL_NAME,
            {"start": DEFAULT_WINDOW_START.isoformat(), "end": DEFAULT_WINDOW_END.isoformat()},
        )
    (total,) = connect_as(ROLE_QA).execute("SELECT count(*) FROM incidents").fetchone()
    assert result.structured_content["incident_count"] == total > 0
