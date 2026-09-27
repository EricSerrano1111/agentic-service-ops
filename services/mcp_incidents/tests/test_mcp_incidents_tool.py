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
from mcp_incidents.server import (
    FIRST_TIME_FIX,
    INCIDENT_RATE,
    SLA_COMPLIANCE,
    TOOL_NAME,
    Backend,
    create_app,
    create_server,
)
from schemas import (
    FirstTimeFixResult,
    GroupRate,
    IncidentRateResult,
    IncidentSummary,
    SeverityCounts,
    SlaComplianceResult,
)
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


def _fake_metric(model):
    """A metric query stand-in: records its arguments, returns fixed figures."""
    calls = []

    def query(start: dt.date, end: dt.date, group_by=None):
        calls.append((start, end, group_by))
        groups = None
        if group_by is not None:
            groups = [GroupRate(group="northeast", numerator=1, denominator=3, rate="0.3333")]
        return model(
            start=start,
            end=end,
            group_by=group_by,
            numerator=1,
            denominator=3,
            rate="0.3333",
            groups=groups,
            group_count=None if groups is None else 1,
        )

    query.calls = calls
    return query


def backend(incidents=_fake_summary) -> Backend:
    return Backend(
        incidents=incidents,
        incident_rate=_fake_metric(IncidentRateResult),
        sla_compliance=_fake_metric(SlaComplianceResult),
        first_time_fix_rate=_fake_metric(FirstTimeFixResult),
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


async def test_only_the_four_narrow_tools_are_exposed():
    """ADR-023: purpose-built tools, no generic query tool."""
    async with Client(create_server(SETTINGS, backend())) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == {TOOL_NAME, INCIDENT_RATE, SLA_COMPLIANCE, FIRST_TIME_FIX}
    assert set(tools[TOOL_NAME].input_schema["properties"]) == {"start", "end"}
    for name in (INCIDENT_RATE, SLA_COMPLIANCE, FIRST_TIME_FIX):
        schema = tools[name].input_schema["properties"]
        assert set(schema) == {"start", "end", "group_by"}
        # Every dimension app_reporting has grants for; no free-form breakdown.
        enum = next(o["enum"] for o in schema["group_by"]["anyOf"] if "enum" in o)
        assert enum == ["account", "region", "service_type", "technician"]
    # Aggregates only: no row ids, no free-text columns.
    assert set(tools[TOOL_NAME].output_schema["properties"]) == {
        "metric",
        "start",
        "end",
        "incident_count",
        "by_severity",
    }


@pytest.mark.parametrize(
    ("tool", "field"),
    [
        (INCIDENT_RATE, "incident_rate"),
        (SLA_COMPLIANCE, "sla_compliance"),
        (FIRST_TIME_FIX, "first_time_fix_rate"),
    ],
)
async def test_metric_tools_pass_the_range_and_breakdown_through(tool, field):
    b = backend()
    async with Client(create_server(SETTINGS, b)) as client:
        plain = await client.call_tool(tool, {"start": "2024-01-01", "end": "2024-01-31"})
        grouped = await client.call_tool(
            tool, {"start": "2024-01-01", "end": "2024-01-31", "group_by": "region"}
        )
    assert not plain.is_error and not grouped.is_error
    assert plain.structured_content["rate"] == "0.3333"  # a string, not a float
    assert grouped.structured_content["groups"][0]["group"] == "northeast"
    jan = (dt.date(2024, 1, 1), dt.date(2024, 1, 31))
    assert getattr(b, field).calls == [(*jan, None), (*jan, "region")]


async def test_metric_tool_rejects_an_unknown_breakdown():
    async with Client(create_server(SETTINGS, backend())) as client:
        result = await client.call_tool(
            INCIDENT_RATE, {"start": "2024-01-01", "end": "2024-01-31", "group_by": "city"}
        )
    assert result.is_error


async def test_metric_tool_validates_the_range_like_the_count_tool():
    async with Client(create_server(SETTINGS, backend())) as client:
        result = await client.call_tool(
            SLA_COMPLIANCE, {"start": "2024-02-01", "end": "2024-01-01"}
        )
    assert result.is_error and "is after end" in result.content[0].text


async def test_tool_returns_structured_summary():
    async with Client(create_server(SETTINGS, backend())) as client:
        result = await client.call_tool(TOOL_NAME, {"start": "2024-01-01", "end": "2024-01-31"})
    assert not result.is_error
    summary = IncidentSummary.model_validate(result.structured_content)
    assert summary.start == dt.date(2024, 1, 1)
    assert summary.incident_count == 6


async def test_tool_rejects_bad_input_with_clear_error():
    async with Client(create_server(SETTINGS, backend())) as client:
        result = await client.call_tool(TOOL_NAME, {"start": "2024-02-01", "end": "2024-01-01"})
    assert result.is_error
    assert "is after end" in result.content[0].text


async def test_query_failure_does_not_leak_detail():
    def broken(start, end):
        raise RuntimeError('relation "incidents" secret detail')

    async with Client(create_server(SETTINGS, backend(broken))) as client:
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
        async with Client(create_server(SETTINGS, backend())) as client:
            await client.call_tool(
                TOOL_NAME, {"start": "2024-01-01", "end": "2024-01-31"}, meta={"trace_id": "t-123"}
            )
    finally:
        logger.removeHandler(handler)
        logger.disabled = was_disabled
    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert any(line["msg"] == "tool call" and line["trace_id"] == "t-123" for line in lines)


def test_healthz():
    with TestClient(create_app(SETTINGS, backend())) as client:
        response = client.get("/healthz", headers={"host": "localhost:8101"})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


# --------------------------------------------------------------------------- worst-first ranking


def _counts(pairs: dict[str, tuple[int, int]]):
    from mcp_incidents.metrics import _Counts

    numerators = {k: _Counts(k, k, n) for k, (n, _) in pairs.items()}
    denominators = {k: _Counts(k, k, d) for k, (_, d) in pairs.items()}
    return numerators, denominators


def test_higher_is_worse_ranks_highest_rate_first():
    """Incident rate: the worst group has the most incidents per 100."""
    from mcp_incidents.metrics import _rank

    nums, dens = _counts({"a": (1, 10), "b": (5, 10), "c": (3, 10)})
    groups, total = _rank(nums, dens, "region", 100, higher_is_worse=True)
    assert [g.group for g in groups] == ["b", "c", "a"] and total == 3


def test_lower_is_worse_ranks_lowest_rate_first():
    """SLA compliance and first-time fix: the worst group has the lowest share."""
    from mcp_incidents.metrics import _rank

    nums, dens = _counts({"a": (9, 10), "b": (5, 10), "c": (7, 10)})
    groups, _ = _rank(nums, dens, "region", 1, higher_is_worse=False)
    assert [g.group for g in groups] == ["b", "c", "a"]


def test_null_rates_go_last_and_ties_break_by_name():
    from mcp_incidents.metrics import _rank

    nums, dens = _counts({"z": (1, 2), "a": (1, 2), "empty": (0, 0)})
    groups, _ = _rank(nums, dens, "region", 1, higher_is_worse=False)
    assert [g.group for g in groups] == ["a", "z", "empty"]
    assert groups[-1].rate is None


@pytest.mark.parametrize("higher_is_worse", [True, False])
def test_truncation_keeps_the_worst_groups(higher_is_worse):
    from mcp_incidents.metrics import _Counts, _rank
    from schemas import MAX_GROUPS

    # 40 technicians (integer ids) with rates 1/100 .. 40/100.
    nums = {i: _Counts(i, f"tech {i}", i) for i in range(1, 41)}
    dens = {i: _Counts(i, f"tech {i}", 100) for i in range(1, 41)}
    groups, total = _rank(nums, dens, "technician", 1, higher_is_worse=higher_is_worse)
    assert total == 40 and len(groups) == MAX_GROUPS
    worst = range(40, 15, -1) if higher_is_worse else range(1, 26)
    assert {g.group_id for g in groups} == set(worst)
    assert groups[0].group_id == (40 if higher_is_worse else 1)
