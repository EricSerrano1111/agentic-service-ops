"""Offline tests for the incidents MCP server: input validation and the tool contract.

The tool is exercised through a real MCP client connected in-process, with the database
query swapped for a fake. The live query is covered by
tests/integration/test_mcp_incidents_figures.py.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import logging
import sys
from pathlib import Path

import pytest
from common import JsonFormatter
from mcp import Client
from mcp_incidents.config import DEFAULT_WINDOW_END, DEFAULT_WINDOW_START, Settings
from mcp_incidents.queries import InvalidRange, parse_date_range
from mcp_incidents.server import TOOL_NAME, create_app, create_server
from schemas import IncidentSummary, SeverityCounts
from starlette.testclient import TestClient

WINDOW = (DEFAULT_WINDOW_START, DEFAULT_WINDOW_END)
pytestmark = pytest.mark.anyio

SETTINGS = Settings(db_host="unused", db_port=5432, db_name="unused", db_user="unused")


def _fake_summary(start: dt.date, end: dt.date) -> IncidentSummary:
    return IncidentSummary(
        start=start,
        end=end,
        incident_count=6,
        by_severity=SeverityCounts(low=3, medium=2, high=1),
    )


@pytest.fixture
def anyio_backend():
    return "asyncio"


# --------------------------------------------------------------------------- validation


def test_valid_range_parses():
    assert parse_date_range("2024-01-01", "2024-03-31", *WINDOW) == (
        dt.date(2024, 1, 1),
        dt.date(2024, 3, 31),
    )


def test_single_day_range_is_allowed():
    assert parse_date_range("2024-01-01", "2024-01-01", *WINDOW)[0] == dt.date(2024, 1, 1)


def test_window_edges_are_inclusive():
    parse_date_range(DEFAULT_WINDOW_START.isoformat(), DEFAULT_WINDOW_END.isoformat(), *WINDOW)


@pytest.mark.parametrize(
    ("start", "end", "message"),
    [
        ("2024-03-31", "2024-01-01", "is after end"),
        ("2024-13-01", "2024-12-31", "must be an ISO date"),
        ("yesterday", "2024-12-31", "must be an ISO date"),
        ("20240101", "2024-12-31", "must be an ISO date"),  # basic format: rejected
        ("2024-01-01T00:00", "2024-12-31", "must be an ISO date"),
        ("", "2024-12-31", "must be an ISO date"),
        ("2023-09-03", "2024-01-01", "outside the dataset window"),
        ("2026-01-01", "2026-08-31", "outside the dataset window"),
    ],
)
def test_invalid_ranges_are_rejected(start, end, message):
    with pytest.raises(InvalidRange, match=message):
        parse_date_range(start, end, *WINDOW)


def test_window_defaults_match_generator_parameters():
    """The window is config (app_reporting cannot read generation_parameters), so hold
    it to the generator's own definition: 156 weeks from the first Monday."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "data" / "generator"))
    import parameters as prm

    window = prm.PARAMS.window
    start = window.start_monday.value
    end_exclusive = start + dt.timedelta(weeks=window.n_weeks.value)
    assert start == DEFAULT_WINDOW_START
    assert end_exclusive - dt.timedelta(days=1) == DEFAULT_WINDOW_END


# --------------------------------------------------------------------------- MCP contract


async def test_exactly_one_narrow_tool_is_exposed():
    async with Client(create_server(SETTINGS, _fake_summary)) as client:
        tools = (await client.list_tools()).tools
    assert [t.name for t in tools] == [TOOL_NAME]
    tool = tools[0]
    assert set(tool.input_schema["properties"]) == {"start", "end"}
    # Aggregates only: no row ids, no free-text columns.
    assert set(tool.output_schema["properties"]) == {
        "start",
        "end",
        "incident_count",
        "by_severity",
    }


async def test_tool_returns_structured_summary():
    async with Client(create_server(SETTINGS, _fake_summary)) as client:
        result = await client.call_tool(TOOL_NAME, {"start": "2024-01-01", "end": "2024-01-31"})
    assert not result.is_error
    summary = IncidentSummary.model_validate(result.structured_content)
    assert summary.start == dt.date(2024, 1, 1)
    assert summary.incident_count == 6


async def test_tool_rejects_bad_input_with_clear_error():
    async with Client(create_server(SETTINGS, _fake_summary)) as client:
        result = await client.call_tool(TOOL_NAME, {"start": "2024-02-01", "end": "2024-01-01"})
    assert result.is_error
    assert "is after end" in result.content[0].text


async def test_query_failure_does_not_leak_detail():
    def broken(start, end):
        raise RuntimeError('relation "incidents" secret detail')

    async with Client(create_server(SETTINGS, broken)) as client:
        result = await client.call_tool(TOOL_NAME, {"start": "2024-01-01", "end": "2024-01-31"})
    assert result.is_error
    assert "secret" not in result.content[0].text
    assert "incident query failed" in result.content[0].text


async def test_trace_id_from_meta_reaches_the_log():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter("mcp_incidents"))
    logger = logging.getLogger("mcp_incidents")
    # Alembic's env.py (run in-process by other unit tests) calls fileConfig, which
    # disables every logger that already exists.
    was_disabled, logger.disabled = logger.disabled, False
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        async with Client(create_server(SETTINGS, _fake_summary)) as client:
            await client.call_tool(
                TOOL_NAME, {"start": "2024-01-01", "end": "2024-01-31"}, meta={"trace_id": "t-123"}
            )
    finally:
        logger.removeHandler(handler)
        logger.disabled = was_disabled
    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert any(line["msg"] == "tool call" and line["trace_id"] == "t-123" for line in lines)


def test_healthz():
    with TestClient(create_app(SETTINGS, _fake_summary)) as client:
        response = client.get("/healthz", headers={"host": "localhost:8101"})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
