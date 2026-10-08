"""Offline tests for the incidents MCP server: input validation and the tool contract.

The tool is exercised through a real MCP client connected in-process, with the database
query swapped for a fake. The live query is covered by
tests/integration/test_mcp_incidents_figures.py.
"""

from __future__ import annotations

import contextlib
import dataclasses
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
    FIND_TECHNICIAN,
    FIRST_TIME_FIX,
    INCIDENT_RATE,
    REPEAT_DRIVERS,
    SLA_COMPLIANCE,
    TOOL_NAME,
    Backend,
    create_app,
    create_server,
)
from schemas import (
    FirstTimeFixResult,
    GroupCount,
    GroupRate,
    IncidentRateResult,
    IncidentSummary,
    JobsRepeated,
    RepeatDriversResult,
    SeverityCounts,
    SlaComplianceResult,
    TechnicianMatches,
)
from starlette.testclient import TestClient

WINDOW = (DEFAULT_WINDOW_START, DEFAULT_WINDOW_END)
pytestmark = pytest.mark.anyio

SETTINGS = Settings(db_host="unused", db_port=5432, db_name="unused", db_user="unused")


def _technician(technician_id):
    if technician_id is None:
        return {}
    return {"technician_id": technician_id, "technician_name": "Priya Kim"}


def _fake_count():
    """The count query stand-in: records its arguments, returns fixed figures."""
    calls = []

    def query(start: dt.date, end: dt.date, group_by=None, technician_id=None):
        calls.append((start, end, group_by, technician_id))
        groups = None
        if group_by is not None:
            groups = [GroupCount(group="unattributed", count=4), GroupCount(group="x", count=2)]
        return IncidentSummary(
            start=start,
            end=end,
            incident_count=6,
            by_severity=SeverityCounts(low=3, medium=2, high=1),
            group_by=group_by,
            groups=groups,
            group_count=None if groups is None else 2,
            **_technician(technician_id),
        )

    query.calls = calls
    return query


def _fake_summary(start: dt.date, end: dt.date, group_by=None, technician_id=None):
    return _fake_count()(start, end, group_by, technician_id)


def _fake_metric(model):
    """A metric query stand-in: records its arguments, returns fixed figures."""
    calls = []

    def query(start: dt.date, end: dt.date, group_by=None, technician_id=None):
        calls.append((start, end, group_by, technician_id))
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
            **_technician(technician_id),
        )

    query.calls = calls
    return query


def _fake_find(name: str) -> TechnicianMatches:
    from mcp_incidents.queries import match_technicians

    return match_technicians(name, [(1, "Priya Kim"), (2, "Priya Castillo"), (3, "Ben Okafor")])


def _fake_repeats(start: dt.date, end: dt.date, by):
    jr = JobsRepeated(jobs=100, repeated=2, rate="0.0200")
    other = {}
    if by == "incident_type":
        other = {
            "any_other_incident": jr,
            "no_other_incident": jr,
            "other_incident_compared": True,
            "other_incident_p_value": 1.0,
            "other_incident_higher": False,
        }
    return RepeatDriversResult(
        start=start,
        end=end,
        group_by=by,
        overall=jr,
        groups=[],
        group_count=0,
        groups_compared=0,
        **other,
    )


def backend(incidents=_fake_summary, count=None) -> Backend:
    return Backend(
        incidents=count or incidents,
        incident_rate=_fake_metric(IncidentRateResult),
        sla_compliance=_fake_metric(SlaComplianceResult),
        first_time_fix_rate=_fake_metric(FirstTimeFixResult),
        find_technician=_fake_find,
        repeat_drivers=_fake_repeats,
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


def _enum(prop: dict) -> list[str]:
    if "anyOf" in prop:
        return next(o["enum"] for o in prop["anyOf"] if "enum" in o)
    return prop["enum"]


async def test_only_the_narrow_tools_are_exposed():
    """ADR-023: purpose-built tools, no generic query tool."""
    async with Client(create_server(SETTINGS, backend())) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == {
        TOOL_NAME,
        INCIDENT_RATE,
        SLA_COMPLIANCE,
        FIRST_TIME_FIX,
        FIND_TECHNICIAN,
        REPEAT_DRIVERS,
    }
    count = tools[TOOL_NAME].input_schema["properties"]
    assert set(count) == {"start", "end", "group_by", "technician_id"}
    assert _enum(count["group_by"]) == [
        "account",
        "region",
        "service_type",
        "technician",
        "incident_type",
        "severity",
    ]
    for name in (INCIDENT_RATE, SLA_COMPLIANCE, FIRST_TIME_FIX):
        schema = tools[name].input_schema["properties"]
        assert set(schema) == {"start", "end", "group_by", "technician_id"}
        # Every dimension app_reporting has grants for; no free-form breakdown.
        assert _enum(schema["group_by"]) == ["account", "region", "service_type", "technician"]
    assert set(tools[FIND_TECHNICIAN].input_schema["properties"]) == {"name"}
    repeats = tools[REPEAT_DRIVERS].input_schema["properties"]
    assert set(repeats) == {"start", "end", "by"}
    assert _enum(repeats["by"]) == [
        "incident_type",
        "service_type",
        "region",
        "account",
        "technician",
    ]
    # Aggregates only: no row ids, no free-text columns.
    assert set(tools[TOOL_NAME].output_schema["properties"]) == {
        "metric",
        "start",
        "end",
        "incident_count",
        "by_severity",
        "group_by",
        "groups",
        "group_count",
        "truncated",
        "technician_id",
        "technician_name",
    }
    assert set(tools[FIND_TECHNICIAN].output_schema["properties"]) == {
        "name",
        "matches",
        "total_matches",
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
    assert getattr(b, field).calls == [(*jan, None, None), (*jan, "region", None)]


@pytest.mark.parametrize(
    ("tool", "field"),
    [
        (TOOL_NAME, "incidents"),
        (INCIDENT_RATE, "incident_rate"),
        (SLA_COMPLIANCE, "sla_compliance"),
        (FIRST_TIME_FIX, "first_time_fix_rate"),
    ],
)
async def test_every_tool_passes_the_technician_filter_through(tool, field):
    b = backend(count=_fake_count())
    async with Client(create_server(SETTINGS, b)) as client:
        result = await client.call_tool(
            tool, {"start": "2024-01-01", "end": "2024-01-31", "technician_id": 7}
        )
    assert not result.is_error
    assert result.structured_content["technician_id"] == 7
    assert result.structured_content["technician_name"] == "Priya Kim"
    assert getattr(b, field).calls == [(dt.date(2024, 1, 1), dt.date(2024, 1, 31), None, 7)]


@pytest.mark.parametrize("tool", [TOOL_NAME, INCIDENT_RATE, SLA_COMPLIANCE, FIRST_TIME_FIX])
async def test_a_technician_filter_with_a_breakdown_is_rejected(tool):
    b = backend(count=_fake_count())
    args = {"start": "2024-01-01", "end": "2024-01-31", "technician_id": 7, "group_by": "region"}
    async with Client(create_server(SETTINGS, b)) as client:
        result = await client.call_tool(tool, args)
    assert result.is_error and "cannot be combined" in result.content[0].text


@pytest.mark.parametrize("bad", [0, -1, "seven"])
async def test_technician_id_must_be_a_positive_integer(bad):
    async with Client(create_server(SETTINGS, backend())) as client:
        result = await client.call_tool(
            INCIDENT_RATE, {"start": "2024-01-01", "end": "2024-01-31", "technician_id": bad}
        )
    assert result.is_error


async def test_an_unknown_technician_id_is_a_caller_error_returned_verbatim():
    from mcp_incidents.queries import InvalidArgument

    def unknown(start, end, group_by=None, technician_id=None):
        raise InvalidArgument(
            f"no technician has id {technician_id}", argument="technician_id", kind="unknown_id"
        )

    async with Client(create_server(SETTINGS, backend(unknown))) as client:
        result = await client.call_tool(
            TOOL_NAME, {"start": "2024-01-01", "end": "2024-01-31", "technician_id": 999}
        )
    assert result.is_error and "no technician has id 999" in result.content[0].text


@pytest.mark.parametrize(
    "group_by", ["account", "region", "service_type", "technician", "incident_type", "severity"]
)
async def test_count_tool_passes_every_breakdown_through(group_by):
    b = backend(count=_fake_count())
    async with Client(create_server(SETTINGS, b)) as client:
        result = await client.call_tool(
            TOOL_NAME, {"start": "2024-01-01", "end": "2024-01-31", "group_by": group_by}
        )
    assert not result.is_error
    summary = IncidentSummary.model_validate(result.structured_content)
    assert summary.group_by == group_by and summary.groups[0].group == "unattributed"
    assert b.incidents.calls == [(dt.date(2024, 1, 1), dt.date(2024, 1, 31), group_by, None)]


async def test_count_tool_rejects_an_unknown_breakdown():
    async with Client(create_server(SETTINGS, backend())) as client:
        result = await client.call_tool(
            TOOL_NAME, {"start": "2024-01-01", "end": "2024-01-31", "group_by": "root_cause"}
        )
    assert result.is_error


# --------------------------------------------------------------------------- find_technician


@pytest.mark.parametrize(
    ("name", "found"),
    [
        ("Zed", []),
        ("ben okafor", ["Ben Okafor"]),
        ("  OKAFOR ", ["Ben Okafor"]),
        ("Priya", ["Priya Castillo", "Priya Kim"]),
    ],
)
async def test_find_technician_returns_zero_one_or_many(name, found):
    async with Client(create_server(SETTINGS, backend())) as client:
        result = await client.call_tool(FIND_TECHNICIAN, {"name": name})
    assert not result.is_error
    matches = TechnicianMatches.model_validate(result.structured_content)
    assert [m.full_name for m in matches.matches] == found
    assert matches.total_matches == len(found)


@pytest.mark.parametrize("name", ["%", "Pri%", "Pri_a", "*", "Priya*", "P?iya", "[P]riya", "a\\b"])
async def test_find_technician_rejects_wildcards_and_patterns(name):
    async with Client(create_server(SETTINGS, backend())) as client:
        result = await client.call_tool(FIND_TECHNICIAN, {"name": name})
    assert result.is_error and "wildcards" in result.content[0].text


async def test_find_technician_rejects_an_overlong_name():
    async with Client(create_server(SETTINGS, backend())) as client:
        result = await client.call_tool(FIND_TECHNICIAN, {"name": "a" * 101})
    assert result.is_error


# --------------------------------------------------------------------------- repeat drivers


@pytest.mark.parametrize("by", ["incident_type", "service_type", "region", "account", "technician"])
async def test_repeat_drivers_tool_passes_by_through(by):
    async with Client(create_server(SETTINGS, backend())) as client:
        result = await client.call_tool(
            REPEAT_DRIVERS, {"start": "2024-01-01", "end": "2024-03-31", "by": by}
        )
    assert not result.is_error
    assert RepeatDriversResult.model_validate(result.structured_content).group_by == by


async def test_repeat_drivers_defaults_to_incident_type_and_validates_the_range():
    async with Client(create_server(SETTINGS, backend())) as client:
        plain = await client.call_tool(REPEAT_DRIVERS, {"start": "2024-01-01", "end": "2024-03-31"})
        bad = await client.call_tool(REPEAT_DRIVERS, {"start": "2024-03-01", "end": "2024-01-01"})
        unknown = await client.call_tool(
            REPEAT_DRIVERS, {"start": "2024-01-01", "end": "2024-03-31", "by": "severity"}
        )
    assert plain.structured_content["group_by"] == "incident_type"
    assert bad.is_error and "is after end" in bad.content[0].text
    assert unknown.is_error


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
    def broken(start, end, group_by=None, technician_id=None):
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


@contextlib.contextmanager
def captured_logs(*service_loggers: str):
    """Every log line written inside the block, from any logger (SDK loggers included), as
    parsed JSON. Re-enables the service loggers an earlier Alembic `fileConfig` may have
    disabled."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter("test"))
    root = logging.getLogger()
    loggers = [logging.getLogger(n) for n in service_loggers]
    was_disabled = [lg.disabled for lg in loggers]
    for lg in loggers:
        lg.disabled = False
    level = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    try:
        yield lambda: [json.loads(line) for line in stream.getvalue().splitlines()]
    finally:
        root.removeHandler(handler)
        root.setLevel(level)
        for lg, flag in zip(loggers, was_disabled, strict=True):
            lg.disabled = flag


async def test_rejected_arguments_are_logged_by_name_and_kind_never_by_value():
    marker = "MARKER-d41d8c"
    with captured_logs("mcp_incidents") as lines:
        async with Client(create_server(SETTINGS, backend())) as client:
            bad_date = await client.call_tool(TOOL_NAME, {"start": marker, "end": "2024-01-31"})
            bad_name = await client.call_tool(FIND_TECHNICIAN, {"name": f"{marker}%"})
            both = await client.call_tool(
                TOOL_NAME,
                {
                    "start": "2024-01-01",
                    "end": "2024-01-31",
                    "technician_id": 7,
                    "group_by": "region",
                },
            )
        logged = lines()
    # The message names the rule, not the value: the MCP SDK logs it verbatim at INFO.
    assert bad_date.is_error and "ISO date" in bad_date.content[0].text
    assert bad_name.is_error and both.is_error
    rejected = [line for line in logged if line["msg"] == "tool rejected input"]
    assert {(r["tool"], r["argument"], r["error_type"]) for r in rejected} == {
        (TOOL_NAME, "start", "not_iso_date"),
        (FIND_TECHNICIAN, "name", "invalid_characters"),
        (TOOL_NAME, "technician_id,group_by", "conflicting_arguments"),
    }
    assert all("error" not in r for r in rejected)
    assert marker not in json.dumps(logged)


# --------------------------------------------------------------------------- readiness


def _down():
    raise OSError("connection refused: postgres://user:secret_pw@host")


def test_readyz_ready_when_the_database_answers():
    with TestClient(create_app(SETTINGS, backend())) as client:
        r = client.get("/readyz", headers={"host": "localhost:8101"})
    assert r.status_code == 200 and r.json()["service"] == "mcp_incidents"


def test_readyz_not_ready_when_the_database_is_unreachable_and_leaks_nothing():
    with TestClient(create_app(SETTINGS, dataclasses.replace(backend(), ready=_down))) as client:
        r = client.get("/readyz", headers={"host": "localhost:8101"})
    assert r.status_code == 503
    assert "secret_pw" not in r.text and "postgres" not in r.text


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_readyz_rejects_unexpected_methods(method):
    with TestClient(create_app(SETTINGS, backend())) as client:
        assert (
            getattr(client, method)("/readyz", headers={"host": "localhost:8101"}).status_code
            == 405
        )
