"""Region and account filters, and `find_account` (ADR-086): reach, declines, malformed
input, and what the logs hold. Offline: a recording backend stands in for the database."""

from __future__ import annotations

import contextlib
import io
import json
import logging

import pytest
from common import JsonFormatter
from mcp import Client
from mcp_incidents.config import Settings
from mcp_incidents.queries import InvalidArgument, check_scope, match_accounts
from mcp_incidents.server import (
    FIND_ACCOUNT,
    FIRST_TIME_FIX,
    INCIDENT_RATE,
    SLA_COMPLIANCE,
    TOOL_NAME,
    Backend,
    create_server,
)
from schemas import (
    AccountMatches,
    FirstTimeFixResult,
    GroupRate,
    IncidentRateResult,
    IncidentSummary,
    SeverityCounts,
    SlaComplianceResult,
)

SETTINGS = Settings(db_host="unused", db_port=5432, db_name="unused", db_user="unused")
RANGE = {"start": "2024-01-01", "end": "2024-01-31"}
ACCOUNTS = [
    (1, "Bluewater Energy Inc."),
    (2, "Bluewater Hospitality Partners"),
    (3, "Bluewater Manufacturing LLC"),
    (4, "Cedar Ridge Retail Inc."),
    (5, "Brightpath Labs LLC"),
]
METRIC_MODELS = {
    INCIDENT_RATE: IncidentRateResult,
    SLA_COMPLIANCE: SlaComplianceResult,
    FIRST_TIME_FIX: FirstTimeFixResult,
}


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _scope_fields(region, account_id):
    fields = {}
    if region is not None:
        fields["region"] = region
    if account_id is not None:
        fields |= {"account_id": account_id, "account_name": "Bluewater Energy Inc."}
    return fields


class Recorder:
    """A backend whose four metric callables record every argument they get."""

    def __init__(self):
        self.calls: list[tuple] = []

    def count(self, start, end, group_by, technician_id, region, account_id):
        self.calls.append(("count", group_by, technician_id, region, account_id))
        return IncidentSummary(
            start=start,
            end=end,
            incident_count=0,
            by_severity=SeverityCounts(low=0, medium=0, high=0),
            **_scope_fields(region, account_id),
        )

    def metric(self, model):
        def query(start, end, group_by, technician_id, region, account_id):
            self.calls.append((model.__name__, group_by, technician_id, region, account_id))
            groups = None
            if group_by is not None:
                groups = [GroupRate(group="x", numerator=1, denominator=2, rate="0.5000")]
            return model(
                start=start,
                end=end,
                group_by=group_by,
                numerator=1,
                denominator=2,
                rate="0.5000",
                groups=groups,
                group_count=None if groups is None else 1,
                **_scope_fields(region, account_id),
            )

        return query

    def backend(self) -> Backend:
        def unused(*args, **kwargs):
            raise AssertionError("not called")

        return Backend(
            incidents=self.count,
            incident_rate=self.metric(IncidentRateResult),
            sla_compliance=self.metric(SlaComplianceResult),
            first_time_fix_rate=self.metric(FirstTimeFixResult),
            find_technician=unused,
            find_account=lambda name: match_accounts(name, ACCOUNTS),
            repeat_drivers=unused,
        )


async def call(tool: str, arguments: dict, recorder: Recorder | None = None):
    recorder = recorder or Recorder()
    async with Client(create_server(SETTINGS, recorder.backend())) as client:
        return await client.call_tool(tool, arguments)


ALL_TOOLS = [TOOL_NAME, INCIDENT_RATE, SLA_COMPLIANCE, FIRST_TIME_FIX]


# --------------------------------------------------------------------------- reach


@pytest.mark.anyio
@pytest.mark.parametrize("tool", ALL_TOOLS)
async def test_the_filters_reach_every_tool_and_the_result_states_them(tool):
    recorder = Recorder()
    result = await call(tool, RANGE | {"region": "west", "account_id": 3}, recorder)
    assert not result.is_error, result.content
    assert recorder.calls[-1][2:] == (None, "west", 3)
    content = result.structured_content
    assert content["region"] == "west" and content["account_id"] == 3
    assert content["account_name"] == "Bluewater Energy Inc."


@pytest.mark.anyio
@pytest.mark.parametrize("tool", ALL_TOOLS)
async def test_unfiltered_calls_carry_no_filter(tool):
    recorder = Recorder()
    result = await call(tool, RANGE, recorder)
    assert recorder.calls[-1][2:] == (None, None, None)
    assert result.structured_content["region"] is None
    assert result.structured_content["account_id"] is None


# --------------------------------------------------------------------------- combinations


@pytest.mark.anyio
@pytest.mark.parametrize("tool", ALL_TOOLS)
@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"region": "west", "group_by": "region"}, "region filter cannot be combined"),
        ({"account_id": 3, "group_by": "account"}, "account filter cannot be combined"),
    ],
)
async def test_a_filter_with_a_breakdown_by_the_same_dimension_is_declined(
    tool, arguments, message
):
    recorder = Recorder()
    result = await call(tool, RANGE | arguments, recorder)
    assert result.is_error and message in result.content[0].text
    assert recorder.calls == []  # declined before any query


@pytest.mark.anyio
@pytest.mark.parametrize("tool", ALL_TOOLS)
@pytest.mark.parametrize(
    "arguments",
    [
        {"region": "west", "group_by": "account"},
        {"region": "west", "group_by": "service_type"},
        {"account_id": 3, "group_by": "region"},
        {"account_id": 3, "group_by": "service_type"},
        {"region": "west", "account_id": 3},
        {"region": "west", "technician_id": 7},
        {"account_id": 3, "technician_id": 7},
        {"region": "west", "account_id": 3, "technician_id": 7},
    ],
)
async def test_other_combinations_are_allowed(tool, arguments):
    recorder = Recorder()
    result = await call(tool, RANGE | arguments, recorder)
    assert not result.is_error, result.content
    assert len(recorder.calls) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("tool", ALL_TOOLS)
async def test_a_technician_filter_with_a_breakdown_stays_declined(tool):
    result = await call(tool, RANGE | {"technician_id": 7, "group_by": "region"})
    assert result.is_error and "technician filter" in result.content[0].text


def test_check_scope_is_the_one_rule():
    check_scope(None)
    check_scope("account", region="west")
    check_scope("region", account_id=3)
    for args in (
        ("region", None, "west", None),
        ("account", None, None, 3),
        ("service_type", 7, None, None),
    ):
        with pytest.raises(InvalidArgument) as caught:
            check_scope(*args)
        assert caught.value.kind == "conflicting_arguments"


# --------------------------------------------------------------------------- malformed input


@pytest.mark.anyio
@pytest.mark.parametrize("tool", ALL_TOOLS)
@pytest.mark.parametrize(
    "bad",
    [
        {"region": "midwest"},
        {"region": "West"},
        {"region": "west; DROP TABLE incidents"},
        {"region": ""},
        {"region": 3},
        {"account_id": 0},
        {"account_id": -4},
        {"account_id": "3 OR 1=1"},
        {"account_id": 1.5},
    ],
)
async def test_invalid_region_and_account_values_are_rejected_before_any_query(tool, bad):
    recorder = Recorder()
    result = await call(tool, RANGE | bad, recorder)
    assert result.is_error
    assert recorder.calls == []


# --------------------------------------------------------------------------- find_account


@pytest.mark.parametrize(
    ("name", "found"),
    [
        ("Zed", []),
        ("Blue", []),  # a partial word finds nothing
        ("cedar ridge retail inc.", ["Cedar Ridge Retail Inc."]),
        ("  RIDGE ", ["Cedar Ridge Retail Inc."]),
        ("Brightpath Labs", ["Brightpath Labs LLC"]),
        ("llc", ["Bluewater Manufacturing LLC", "Brightpath Labs LLC"]),
        (
            "Bluewater",
            [
                "Bluewater Energy Inc.",
                "Bluewater Hospitality Partners",
                "Bluewater Manufacturing LLC",
            ],
        ),
    ],
)
def test_match_accounts_zero_one_or_many(name, found):
    matches = match_accounts(name, ACCOUNTS)
    assert [m.account_name for m in matches.matches] == found
    assert matches.total_matches == len(found)


def test_match_accounts_caps_the_list_at_five_and_counts_them_all():
    many = [(i, f"Acme Group {chr(65 + i)} Inc.") for i in range(8)]
    matches = match_accounts("Acme", many)
    assert len(matches.matches) == 5 and matches.total_matches == 8
    assert [m.account_name for m in matches.matches] == sorted(
        m.account_name for m in matches.matches
    )


@pytest.mark.anyio
@pytest.mark.parametrize("name", ["Bluewater", "Cedar Ridge Retail Inc.", "Zed"])
async def test_find_account_tool_returns_the_matches(name):
    result = await call(FIND_ACCOUNT, {"name": name})
    assert not result.is_error
    matches = AccountMatches.model_validate(result.structured_content)
    assert matches.name == name and matches.total_matches == len(matches.matches)


PATTERNS = ["%", "Blue%", "Blue_ater", "*", "Blue*", "B?uewater", "[B]luewater", "a\\b", "^Blue$"]


@pytest.mark.anyio
@pytest.mark.parametrize("name", PATTERNS + ["Blue'; DROP TABLE accounts;--", "x" + chr(0)])
async def test_find_account_rejects_wildcards_patterns_and_sql(name):
    result = await call(FIND_ACCOUNT, {"name": name})
    assert result.is_error and "wildcards" in result.content[0].text


@pytest.mark.anyio
@pytest.mark.parametrize("name", ["a" * 101, "", "   ", "1234", "Bluewater 2"])
async def test_find_account_rejects_an_oversized_empty_or_numeric_name(name):
    result = await call(FIND_ACCOUNT, {"name": name})
    assert result.is_error


# --------------------------------------------------------------------------- exposure


@contextlib.contextmanager
def captured_logs(*service_loggers: str):
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


@pytest.mark.anyio
async def test_a_typed_account_name_is_never_logged():
    marker_hit = "Bluewater"  # a real first word: three matches, whose names are in the answer
    marker_miss = "Zzyzxmarker"  # no match
    marker_bad = "MARKER-d41d8c%"  # rejected characters
    with captured_logs("mcp_incidents") as lines:
        async with Client(create_server(SETTINGS, Recorder().backend())) as client:
            hit = await client.call_tool(FIND_ACCOUNT, {"name": marker_hit})
            miss = await client.call_tool(FIND_ACCOUNT, {"name": marker_miss})
            bad = await client.call_tool(FIND_ACCOUNT, {"name": marker_bad})
        logged = lines()
    assert not hit.is_error and not miss.is_error and bad.is_error
    text = json.dumps(logged)
    for forbidden in (marker_hit, marker_miss, marker_bad, "Bluewater Energy"):
        assert forbidden not in text, forbidden
    calls = [x for x in logged if x["msg"] == "tool call" and x.get("tool") == FIND_ACCOUNT]
    assert sorted(c["matches"] for c in calls) == [0, 3]
    rejected = [x for x in logged if x["msg"] == "tool rejected input"]
    assert [(r["tool"], r["argument"], r["error_type"]) for r in rejected] == [
        (FIND_ACCOUNT, "name", "invalid_characters")
    ]


@pytest.mark.anyio
async def test_a_filtered_call_logs_the_account_id_and_region_not_the_account_name():
    with captured_logs("mcp_incidents") as lines:
        await call(SLA_COMPLIANCE, RANGE | {"region": "west", "account_id": 3})
        logged = lines()
    [entry] = [x for x in logged if x["msg"] == "tool call" and x["tool"] == SLA_COMPLIANCE]
    assert entry["region"] == "west" and entry["account_id"] == 3
    assert "Bluewater" not in json.dumps(logged)
