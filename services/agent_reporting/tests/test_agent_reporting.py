"""Offline tests for the reporting agent: Agent Card, rendering, question parsing
(ADR-046, ADR-050) and the A2A task flow.

The A2A flow runs through the real SDK client and server, in-process over an ASGI
transport. The LLM is a fake with the `LLMClient.generate` signature, and the MCP call is
replaced. The live hops are covered by the e2e tests.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import logging
import uuid

import httpx
import pytest
from a2a.client import ClientConfig, create_client
from a2a.types import Message, Part, Role, SendMessageRequest, TaskState
from a2a.utils.constants import AGENT_CARD_WELL_KNOWN_PATH
from agent_reporting import executor as executor_mod
from agent_reporting.app import create_app
from agent_reporting.card import SKILL_ID, build_agent_card
from agent_reporting.config import Settings
from agent_reporting.mcp_client import McpToolError
from agent_reporting.parsing import previous_month, resolve
from agent_reporting.render import render_answer, render_incident_summary
from common import JsonFormatter
from fastapi.testclient import TestClient
from google.protobuf.json_format import MessageToDict
from llm import (
    LLMDailyQuotaExhausted,
    LLMOutputInvalid,
    LLMRateLimited,
    LLMRequestError,
    LLMResult,
    LLMUnavailable,
)
from schemas import (
    FirstTimeFixResult,
    GroupCount,
    GroupRate,
    IncidentRateResult,
    IncidentSummary,
    JobsRepeated,
    RepeatDriversResult,
    RepeatGroup,
    ReportingAnswer,
    ReportingRequest,
    SeverityCounts,
    SlaComplianceResult,
    TechnicianMatch,
    TechnicianMatches,
    rate_string,
)

BASE = "http://agent.test"
AS_OF = dt.date(2026, 8, 30)
SETTINGS = Settings(public_url=f"{BASE}/")
JULY = (dt.date(2026, 7, 1), dt.date(2026, 7, 31))
_JULY = {"start": JULY[0], "end": JULY[1]}


def req(metric: str = "incident_count", **fields) -> ReportingRequest:
    """A parsed request; the existing tests are all incident-count questions."""
    return ReportingRequest(metric=metric, **fields)


def summary(start: dt.date, end: dt.date) -> IncidentSummary:
    return IncidentSummary(
        start=start,
        end=end,
        incident_count=172,
        by_severity=SeverityCounts(low=93, medium=54, high=25),
    )


class FakeLLM:
    """`LLMClient.generate` stand-in: returns `parsed`, or raises `error`."""

    def __init__(self, parsed: ReportingRequest | None = None, error: Exception | None = None):
        self.parsed, self.error = parsed, error
        self.prompts: list[str] = []

    async def generate(self, prompt, *, model=None, response_model=None, trace_id):
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        assert response_model is ReportingRequest
        return LLMResult(
            text=self.parsed.model_dump_json(),
            parsed=self.parsed,
            model="gemini-3.5-flash-lite",
            input_tokens=300,
            output_tokens=20,
            cost_usd=0.0001,
            latency_s=0.1,
            attempts=1,
        )


@pytest.fixture
def anyio_backend():
    return "asyncio"


TECHNICIANS = [(7, "Priya Kim"), (8, "Priya Castillo"), (9, "Ben Okafor")]


def fake_matches(name: str) -> TechnicianMatches:
    found = [
        TechnicianMatch(technician_id=i, full_name=n)
        for i, n in TECHNICIANS
        if all(w in n.lower().split() for w in name.lower().split())
    ]
    return TechnicianMatches(name=name, matches=found, total_matches=len(found))


def _jr(jobs: int, repeated: int) -> JobsRepeated:
    return JobsRepeated(jobs=jobs, repeated=repeated, rate=rate_string(repeated, jobs))


def fake_repeats(
    start, end, by, standout: bool = False, other_higher: bool = False
) -> RepeatDriversResult:
    groups = [
        RepeatGroup(
            group="repair" if by != "incident_type" else "wrong_dispatch_info",
            this=_jr(500, 14),
            rest=_jr(1100, 8),
            compared=True,
            p_value=0.005,
            p_adjusted=0.025 if standout else 0.5,
            stands_out=standout,
        ),
        RepeatGroup(
            group="tiny",
            this=_jr(10, 3),
            rest=_jr(1590, 19),
            compared=False,
            stands_out=False,
        ),
        RepeatGroup(
            group="install",
            this=_jr(1090, 5),
            rest=_jr(510, 17),
            compared=True,
            p_value=0.01,
            p_adjusted=0.02,
            stands_out=False,
        ),
    ]
    extra = {}
    if by == "incident_type":
        extra = {
            "any_other_incident": _jr(129, 4),
            "no_other_incident": _jr(1471, 18),
            "other_incident_compared": True,
            "other_incident_p_value": 0.01 if other_higher else 0.2,
            "other_incident_higher": other_higher,
        }
    return RepeatDriversResult(
        start=start,
        end=end,
        group_by=by,
        overall=_jr(1600, 22),
        groups=groups,
        group_count=3,
        groups_compared=2,
        **extra,
    )


def fake_result(tool: str, result_model, start, end, group_by, technician_id=None):
    technician = {}
    if technician_id is not None:
        name = dict(TECHNICIANS)[technician_id]
        technician = {"technician_id": technician_id, "technician_name": name}
    if result_model is RepeatDriversResult:
        return fake_repeats(start, end, group_by)
    if result_model is IncidentSummary:
        if group_by is None:
            return summary(start, end).model_copy(update=technician)
        groups = [GroupCount(group="unattributed", count=100), GroupCount(group="x", count=72)]
        return IncidentSummary(
            start=start,
            end=end,
            incident_count=172,
            by_severity=SeverityCounts(low=93, medium=54, high=25),
            group_by=group_by,
            groups=groups,
            group_count=2,
        )
    groups = None
    if group_by is not None:
        # 7 groups of 40 cases, in the tool's worst-first order for a lower-is-worse
        # share: g1 has the lowest rate. (The template never re-sorts.)
        groups = [
            GroupRate(group=f"g{i}", numerator=i, denominator=40, rate=rate_string(i, 40))
            for i in range(1, 8)
        ]
    return result_model(
        start=start,
        end=end,
        group_by=group_by,
        numerator=45,
        denominator=50,
        rate=rate_string(45, 50),
        groups=groups,
        group_count=None if groups is None else 7,
        **technician,
    )


@pytest.fixture
def mcp_calls(monkeypatch):
    """Replace the MCP call; record its arguments; answer with fixed figures."""
    calls: list[dict] = []

    async def fake(url, tool, arguments, result_model, *, trace_id, timeout_s):
        if tool == "find_technician":
            calls.append({"tool": tool, "name": arguments["name"]})
            return fake_matches(arguments["name"])
        start = dt.date.fromisoformat(arguments["start"])
        end = dt.date.fromisoformat(arguments["end"])
        group_by = arguments.get("group_by", arguments.get("by"))
        call = {
            "tool": tool,
            "start": start,
            "end": end,
            "group_by": group_by,
            "trace_id": trace_id,
        }
        if "technician_id" in arguments:
            call["technician_id"] = arguments["technician_id"]
        calls.append(call)
        return fake_result(tool, result_model, start, end, group_by, arguments.get("technician_id"))

    monkeypatch.setattr(executor_mod, "call_tool", fake)
    return calls


# --------------------------------------------------------------------------- Agent Card


def test_card_advertises_one_skill():
    card = build_agent_card(SETTINGS.public_url)
    assert [s.id for s in card.skills] == [SKILL_ID]
    assert "date range" in card.skills[0].name


def test_card_advertises_only_the_minimal_subset():
    card = build_agent_card(SETTINGS.public_url)
    assert card.capabilities.streaming is False
    assert card.capabilities.push_notifications is False
    assert not card.capabilities.extended_agent_card
    [interface] = card.supported_interfaces
    assert interface.protocol_binding == "JSONRPC"
    assert interface.protocol_version == "1.0"
    assert interface.url == SETTINGS.public_url


def test_card_served_at_well_known_path():
    assert AGENT_CARD_WELL_KNOWN_PATH == "/.well-known/agent-card.json"
    with TestClient(create_app(SETTINGS, FakeLLM())) as client:
        body = client.get(AGENT_CARD_WELL_KNOWN_PATH).json()
        assert client.get("/healthz").json()["status"] == "ok"
    assert body["capabilities"] == {"streaming": False, "pushNotifications": False}
    assert [s["id"] for s in body["skills"]] == [SKILL_ID]


# --------------------------------------------------------------------------- dates and rendering


def test_as_of_defaults_to_the_dataset_end():
    assert Settings().as_of == AS_OF


@pytest.mark.parametrize(
    ("as_of", "expected"),
    [
        (dt.date(2026, 8, 30), JULY),
        (dt.date(2026, 8, 31), JULY),  # the calendar month before the as-of month
        (dt.date(2026, 1, 15), (dt.date(2025, 12, 1), dt.date(2025, 12, 31))),
        (dt.date(2024, 3, 1), (dt.date(2024, 2, 1), dt.date(2024, 2, 29))),
    ],
)
def test_default_range_is_the_previous_calendar_month(as_of, expected):
    assert previous_month(as_of) == expected


def test_resolve_keeps_a_parsed_range_and_defaults_an_empty_one():
    stated = resolve(req(start=dt.date(2025, 1, 1), end=dt.date(2025, 3, 31)), AS_OF)
    assert (stated.start, stated.end, stated.assumed) == (
        dt.date(2025, 1, 1),
        dt.date(2025, 3, 31),
        False,
    )
    empty = resolve(req(), AS_OF)
    assert ((empty.start, empty.end), empty.assumed) == (JULY, True)


def test_parsed_request_needs_both_dates_or_neither():
    with pytest.raises(ValueError):
        req(start=dt.date(2025, 1, 1))


def _answer(assumed: bool) -> ReportingAnswer:
    request = req() if assumed else req(start=JULY[0], end=JULY[1])
    return ReportingAnswer(
        request=request,
        start=JULY[0],
        end=JULY[1],
        range_assumed=assumed,
        as_of=AS_OF,
        figures=summary(*JULY),
    )


def test_render_states_the_as_of_date():
    text = render_answer(_answer(assumed=False))
    assert text.startswith("As of 2026-08-30: 172 incidents reported from 2026-07-01")
    assert "named no dates" not in text


def test_render_states_an_assumed_range():
    text = render_answer(_answer(assumed=True))
    assert text.startswith("As of 2026-08-30: the question named no dates")
    assert "2026-07-01 to 2026-07-31" in text


def test_render_singular_and_thousands():
    one = summary(*JULY).model_copy(
        update={"incident_count": 1, "by_severity": SeverityCounts(low=1, medium=0, high=0)}
    )
    assert render_incident_summary(one).startswith("1 incident reported")
    many = summary(*JULY).model_copy(
        update={"incident_count": 1500, "by_severity": SeverityCounts(low=1500, medium=0, high=0)}
    )
    assert render_incident_summary(many).startswith("1,500 incidents")


# --------------------------------------------------------------------------- A2A task flow


async def _send(app, text: str = "How many incidents were reported last month?", trace_id="t-1"):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE) as http:
        client = await create_client(
            BASE, client_config=ClientConfig(streaming=False, httpx_client=http)
        )
        message = Message(
            message_id=uuid.uuid4().hex,
            role=Role.ROLE_USER,
            parts=[Part(text=text)],
            metadata={"trace_id": trace_id},
        )
        async for event in client.send_message(SendMessageRequest(message=message)):
            return event.task
    raise AssertionError("no response")


def _failure(task) -> tuple[str, str]:
    message = task.status.message
    return MessageToDict(message.metadata).get("error_code"), message.parts[0].text


@pytest.mark.anyio
async def test_parsed_range_becomes_the_tool_arguments(mcp_calls):
    llm = FakeLLM(req(start=JULY[0], end=JULY[1]))
    task = await _send(create_app(SETTINGS, llm), trace_id="trace-abc")

    assert task.status.state == TaskState.TASK_STATE_COMPLETED
    assert mcp_calls == [
        {
            "tool": "get_incidents_by_date_range",
            "start": JULY[0],
            "end": JULY[1],
            "group_by": None,
            "trace_id": "trace-abc",
        }
    ]
    [artifact] = task.artifacts
    text, data = artifact.parts
    answer = ReportingAnswer.model_validate(MessageToDict(data.data))
    assert answer.request == req(start=JULY[0], end=JULY[1])
    assert (answer.start, answer.end, answer.range_assumed, answer.as_of) == (
        *JULY,
        False,
        AS_OF,
    )
    assert text.text == render_answer(answer)
    assert "As of 2026-08-30" in text.text


@pytest.mark.anyio
async def test_question_and_as_of_date_reach_the_parsing_prompt(mcp_calls):
    llm = FakeLLM(req(start=JULY[0], end=JULY[1]))
    settings = Settings(public_url=f"{BASE}/", as_of=dt.date(2025, 3, 15))
    await _send(create_app(settings, llm), text="incidents in the past 30 days")
    [prompt] = llm.prompts
    assert "incidents in the past 30 days" in prompt
    assert "2025-03-15" in prompt and "{{" not in prompt


@pytest.mark.anyio
async def test_no_date_defaults_to_last_full_month_and_says_so(mcp_calls):
    task = await _send(create_app(SETTINGS, FakeLLM(req())), text="Any incidents?")
    assert task.status.state == TaskState.TASK_STATE_COMPLETED
    assert (mcp_calls[0]["start"], mcp_calls[0]["end"]) == JULY
    text, data = task.artifacts[0].parts
    assert ReportingAnswer.model_validate(MessageToDict(data.data)).range_assumed is True
    assert "named no dates" in text.text and "2026-07-01 to 2026-07-31" in text.text


@pytest.mark.anyio
async def test_out_of_window_range_fails_with_a_clear_message(monkeypatch):
    async def rejects(*args, **kwargs):
        # The MCP tool's own validation message (mcp_incidents.queries.parse_date_range).
        raise McpToolError(
            "range 2027-01-01 to 2027-01-31 is outside the dataset window "
            "2023-09-04 to 2026-08-30 (inclusive)"
        )

    monkeypatch.setattr(executor_mod, "call_tool", rejects)
    llm = FakeLLM(req(start=dt.date(2027, 1, 1), end=dt.date(2027, 1, 31)))
    task = await _send(create_app(SETTINGS, llm))
    assert task.status.state == TaskState.TASK_STATE_FAILED
    code, text = _failure(task)
    assert code == "invalid_range"
    assert "outside the dataset window" in text and "as of 2026-08-30" in text
    assert not task.artifacts


@pytest.mark.anyio
async def test_invalid_parse_output_fails_and_never_guesses_a_range(mcp_calls):
    llm = FakeLLM(error=LLMOutputInvalid("bad", raw_text='{"start": "soon"}'))
    task = await _send(create_app(SETTINGS, llm))
    assert task.status.state == TaskState.TASK_STATE_FAILED
    code, text = _failure(task)
    assert code == "unclear_question" and "rephrase" in text
    assert mcp_calls == []  # no query was made with a guessed range


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error", "code"),
    [
        (LLMRateLimited("x"), "rate_limited"),
        (LLMDailyQuotaExhausted("gemini-3.5-flash-lite"), "daily_quota_exhausted"),
        (LLMUnavailable("x"), "model_unavailable"),
        (LLMRequestError("gemini-3.5-flash-lite: error 400: bad argument"), "internal_error"),
    ],
)
async def test_llm_failures_end_in_coded_failed_task(mcp_calls, error, code):
    task = await _send(create_app(SETTINGS, FakeLLM(error=error)))
    assert task.status.state == TaskState.TASK_STATE_FAILED
    assert _failure(task)[0] == code
    assert "gemini" not in _failure(task)[1]  # user text, not the exception's
    assert mcp_calls == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error", "code"),
    [
        (TimeoutError(), "tool_timeout"),
        (McpToolError("incident query failed"), "tool_error"),
        (ConnectionError("refused"), "tool_unavailable"),
    ],
)
async def test_mcp_failures_end_in_coded_failed_task(monkeypatch, error, code):
    async def fails(*args, **kwargs):
        raise error

    monkeypatch.setattr(executor_mod, "call_tool", fails)
    task = await _send(create_app(SETTINGS, FakeLLM(req(start=JULY[0], end=JULY[1]))))
    assert task.status.state == TaskState.TASK_STATE_FAILED
    assert _failure(task)[0] == code
    assert not task.artifacts


@pytest.mark.anyio
async def test_prompt_version_is_logged_with_the_parse(mcp_calls):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter("agent_reporting"))
    logger = logging.getLogger("agent_reporting")
    was_disabled, logger.disabled = logger.disabled, False
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        await _send(create_app(SETTINGS, FakeLLM(req())), trace_id="t-log")
    finally:
        logger.removeHandler(handler)
        logger.disabled = was_disabled
    [line] = [json.loads(x) for x in stream.getvalue().splitlines() if "question parsed" in x]
    assert line["prompt_version"] == "parse_v3" and len(line["prompt_sha"]) == 12
    assert line["trace_id"] == "t-log" and line["range_assumed"] is True


# --------------------------------------------------------------------------- metrics (FR-06)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("metric", "tool"),
    [
        ("incident_count", "get_incidents_by_date_range"),
        ("incident_rate", "get_incident_rate"),
        ("sla_compliance", "get_sla_compliance"),
        ("first_time_fix_rate", "get_first_time_fix_rate"),
    ],
)
async def test_each_metric_calls_its_own_tool(mcp_calls, metric, tool):
    """The agent picks the tool from the parsed metric; the model never names one."""
    task = await _send(create_app(SETTINGS, FakeLLM(req(metric, start=JULY[0], end=JULY[1]))))
    assert task.status.state == TaskState.TASK_STATE_COMPLETED
    assert [c["tool"] for c in mcp_calls] == [tool]
    answer = ReportingAnswer.model_validate(MessageToDict(task.artifacts[0].parts[1].data))
    assert answer.figures.metric == metric == answer.request.metric


@pytest.mark.anyio
@pytest.mark.parametrize("group_by", ["account", "region", "service_type", "technician"])
async def test_each_breakdown_reaches_the_tool(mcp_calls, group_by):
    llm = FakeLLM(req("sla_compliance", group_by=group_by, start=JULY[0], end=JULY[1]))
    task = await _send(create_app(SETTINGS, llm))
    assert task.status.state == TaskState.TASK_STATE_COMPLETED
    assert mcp_calls[0]["group_by"] == group_by
    answer = ReportingAnswer.model_validate(MessageToDict(task.artifacts[0].parts[1].data))
    assert answer.figures.group_by == group_by and len(answer.figures.groups) == 7


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("request_", "phrase"),
    [
        (req("unsupported", start=JULY[0], end=JULY[1]), "metric isn't supported yet"),
        (
            req("incident_rate", group_by="unsupported", start=JULY[0], end=JULY[1]),
            "breakdown isn't supported yet",
        ),
        (
            req("incident_rate", group_by="severity", start=JULY[0], end=JULY[1]),
            "can't be broken down by severity",
        ),
        (
            req("sla_compliance", group_by="incident_type", start=JULY[0], end=JULY[1]),
            "can't be broken down by incident type",
        ),
        (
            req("repeat_visit_drivers", group_by="severity", start=JULY[0], end=JULY[1]),
            "can't be broken down by severity",
        ),
        (
            req("sla_compliance", group_by="region", technician_name="Priya", **_JULY),
            "can't also be broken down",
        ),
        (
            req("repeat_visit_drivers", technician_name="Priya Kim", **_JULY),
            "can't be filtered to one technician",
        ),
    ],
)
async def test_unsupported_requests_fail_clearly_and_never_query(mcp_calls, request_, phrase):
    """e.g. "which incident types drive repeat visits?" (Sprint 3): no guessed metric."""
    task = await _send(create_app(SETTINGS, FakeLLM(request_)))
    assert task.status.state == TaskState.TASK_STATE_FAILED
    code, text = _failure(task)
    assert code == "not_supported" and phrase in text
    assert "SLA compliance" in text  # says what is supported
    assert mcp_calls == []


# --------------------------------------------------------------------------- ADR-073


@pytest.mark.anyio
@pytest.mark.parametrize(
    "group_by", ["account", "region", "service_type", "technician", "incident_type", "severity"]
)
async def test_incident_count_breakdowns_reach_the_tool_and_the_text(mcp_calls, group_by):
    llm = FakeLLM(req("incident_count", group_by=group_by, **_JULY))
    task = await _send(create_app(SETTINGS, llm))
    assert task.status.state == TaskState.TASK_STATE_COMPLETED
    assert mcp_calls[0]["group_by"] == group_by
    text = task.artifacts[0].parts[0].text
    assert "highest first: unattributed 100; x 72." in text


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("metric", "tool"),
    [
        ("incident_count", "get_incidents_by_date_range"),
        ("incident_rate", "get_incident_rate"),
        ("sla_compliance", "get_sla_compliance"),
        ("first_time_fix_rate", "get_first_time_fix_rate"),
    ],
)
async def test_one_matching_technician_filters_every_tool(mcp_calls, metric, tool):
    llm = FakeLLM(req(metric, technician_name="ben", **_JULY))
    task = await _send(create_app(SETTINGS, llm))
    assert task.status.state == TaskState.TASK_STATE_COMPLETED
    assert mcp_calls[0] == {"tool": "find_technician", "name": "ben"}
    assert mcp_calls[1]["tool"] == tool and mcp_calls[1]["technician_id"] == 9
    answer = ReportingAnswer.model_validate(MessageToDict(task.artifacts[0].parts[1].data))
    assert answer.figures.technician_name == "Ben Okafor"
    assert "Ben Okafor" in task.artifacts[0].parts[0].text


@pytest.mark.anyio
async def test_no_matching_technician_answers_with_no_figures(mcp_calls):
    task = await _send(create_app(SETTINGS, FakeLLM(req("sla_compliance", technician_name="Dave"))))
    assert task.status.state == TaskState.TASK_STATE_FAILED
    assert _failure(task) == ("technician_not_found", "No technician matches Dave.")
    assert [c["tool"] for c in mcp_calls] == ["find_technician"]
    assert not task.artifacts


@pytest.mark.anyio
async def test_several_matching_technicians_are_listed_with_no_figures(mcp_calls):
    task = await _send(
        create_app(SETTINGS, FakeLLM(req("sla_compliance", technician_name="Priya")))
    )
    assert task.status.state == TaskState.TASK_STATE_FAILED
    code, text = _failure(task)
    assert code == "technician_ambiguous"
    assert text == (
        "2 technicians match Priya: Priya Kim and Priya Castillo. "
        "Please ask again with the full name."
    )
    assert [c["tool"] for c in mcp_calls] == ["find_technician"]
    assert not task.artifacts


@pytest.mark.anyio
async def test_a_rejected_name_reads_as_no_match(monkeypatch):
    async def rejects(url, tool, arguments, result_model, **kwargs):
        raise McpToolError("name must be ... wildcards and patterns are not accepted")

    monkeypatch.setattr(executor_mod, "call_tool", rejects)
    task = await _send(create_app(SETTINGS, FakeLLM(req("sla_compliance", technician_name="P%"))))
    assert _failure(task) == ("technician_not_found", "No technician matches P%.")


def test_more_than_five_matches_say_how_many_more():
    from agent_reporting.executor import technician_reply

    matches = TechnicianMatches(
        name="Sam",
        matches=[
            TechnicianMatch(technician_id=i, full_name=f"Sam {c}") for i, c in enumerate("ABCDE")
        ],
        total_matches=7,
    )
    code, text = technician_reply(matches)
    assert code == "technician_ambiguous"
    assert "7 technicians match Sam: Sam A, Sam B, Sam C, Sam D, Sam E and 2 more." in text


def _technician_figures(model, numerator, denominator):
    return model(
        start=JULY[0],
        end=JULY[1],
        numerator=numerator,
        denominator=denominator,
        rate=rate_string(numerator, denominator, 100 if model is IncidentRateResult else 1),
        technician_id=7,
        technician_name="Priya Kim",
    )


@pytest.mark.parametrize(
    ("model", "noun"),
    [
        (IncidentRateResult, "based on 52 completed requests"),
        (SlaComplianceResult, "based on 52 dispatched requests"),
        (FirstTimeFixResult, "based on 52 completed requests"),
    ],
)
def test_single_technician_answer_states_its_denominator(model, noun):
    figures = _technician_figures(model, 2 if model is IncidentRateResult else 49, 52)
    answer = _metric_answer(figures, req(figures.metric, technician_name="Priya Kim", **_JULY))
    text = render_answer(answer)
    assert "For Priya Kim" in text and noun in text
    assert "too few to compare reliably" not in text


@pytest.mark.parametrize("model", [IncidentRateResult, SlaComplianceResult, FirstTimeFixResult])
def test_single_technician_under_20_cases_is_flagged(model):
    figures = _technician_figures(model, 1, 19)
    answer = _metric_answer(figures, req(figures.metric, technician_name="Priya Kim", **_JULY))
    assert render_answer(answer).endswith("That is too few to compare reliably.")


def test_single_technician_incident_count_states_only_the_count():
    figures = summary(*JULY).model_copy(update={"technician_id": 7, "technician_name": "Priya Kim"})
    answer = _metric_answer(figures, req("incident_count", technician_name="Priya Kim", **_JULY))
    text = render_answer(answer)
    assert "172 incidents attributed to Priya Kim reported from 2026-07-01" in text
    assert "based on" not in text


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("group_by", "by"),
    [(None, "incident_type"), ("incident_type", "incident_type"), ("region", "region")],
)
async def test_repeat_drivers_call_their_tool_with_by(mcp_calls, group_by, by):
    llm = FakeLLM(req("repeat_visit_drivers", group_by=group_by, **_JULY))
    task = await _send(create_app(SETTINGS, llm))
    assert task.status.state == TaskState.TASK_STATE_COMPLETED
    assert mcp_calls[0]["tool"] == "get_repeat_visit_drivers" and mcp_calls[0]["group_by"] == by
    answer = ReportingAnswer.model_validate(MessageToDict(task.artifacts[0].parts[1].data))
    assert answer.figures.group_by == by


def _repeat_text(by: str, standout: bool = False, other_higher: bool = False) -> str:
    figures = fake_repeats(*JULY, by, standout=standout, other_higher=other_higher)
    group_by = None if by == "incident_type" else by
    return render_answer(
        _metric_answer(figures, req("repeat_visit_drivers", group_by=group_by, **_JULY))
    )


def test_repeat_template_opens_with_count_rate_and_coherence():
    text = _repeat_text("service_type")
    assert text.startswith(
        "As of 2026-08-30: 22 of 1,600 jobs completed from 2026-07-01 to 2026-07-31 "
        "(inclusive, UTC) needed a repeat visit (1.38%). Every repeat visit is recorded "
        "through a repeat-visit-required incident on the original job."
    )


def test_repeat_template_says_no_group_stands_out_and_lists_worst_first():
    text = _repeat_text("service_type")
    assert "No service type stands out" in text
    assert "worst first: repair 2.80% (14 of 500 jobs); install 0.46% (5 of 1,090 jobs)." in text
    assert "1 with fewer than 20 jobs left out of the list" in text
    assert "association" not in text


def test_repeat_template_names_a_group_that_stands_out():
    text = _repeat_text("service_type", standout=True)
    assert (
        "Higher than the rest, beyond what chance explains: repair 2.80% (14 of 500 jobs), "
        "against 0.73% for the rest." in text
    )
    assert "stands out" not in text


def test_repeat_template_by_incident_type_states_association_only_when_significant():
    text = _repeat_text("incident_type", other_higher=True)
    assert "No other incident type stands out" in text
    assert "wrong dispatch info 2.80%" in text
    assert text.endswith(
        "Jobs with any other incident: 3.10% (4 of 129 jobs); jobs with none: 1.22% "
        "(18 of 1,471 jobs). In this period, jobs with another incident needed a repeat "
        "visit more often (3.10% vs 1.22%); this shows association, not cause."
    )


def test_repeat_template_by_incident_type_says_no_clear_difference_otherwise():
    text = _repeat_text("incident_type", other_higher=False)
    assert text.endswith(
        "In this period, jobs with another incident and jobs without didn't differ clearly "
        "(3.10% vs 1.22%)."
    )
    assert "association" not in text


def test_incident_types_show_display_labels_for_every_type():
    """Display labels, not enum values, and one for every `IncidentType` value."""
    from agent_reporting.render import INCIDENT_TYPE_LABELS
    from db_models import IncidentType

    assert set(INCIDENT_TYPE_LABELS) == {t.value for t in IncidentType}
    assert all("_" not in label for label in INCIDENT_TYPE_LABELS.values())
    assert INCIDENT_TYPE_LABELS["missed_sla"] == "missed SLA"
    figures = IncidentSummary(
        start=JULY[0],
        end=JULY[1],
        incident_count=5,
        by_severity=SeverityCounts(low=5, medium=0, high=0),
        group_by="incident_type",
        groups=[
            GroupCount(group="missed_sla", count=3),
            GroupCount(group="wrong_dispatch_info", count=2),
        ],
        group_count=2,
    )
    text = render_answer(
        _metric_answer(figures, req("incident_count", group_by="incident_type", **_JULY))
    )
    assert "highest first: missed SLA 3; wrong dispatch info 2." in text


def test_repeat_template_with_no_completed_jobs():
    figures = RepeatDriversResult(
        start=JULY[0],
        end=JULY[1],
        group_by="region",
        overall=_jr(0, 0),
        groups=[],
        group_count=0,
        groups_compared=0,
    )
    text = render_answer(
        _metric_answer(figures, req("repeat_visit_drivers", group_by="region", **_JULY))
    )
    assert "No jobs were completed" in text


def _metric_answer(figures, request_=None) -> ReportingAnswer:
    request_ = request_ or req(
        figures.metric, group_by=figures.group_by, start=figures.start, end=figures.end
    )
    return ReportingAnswer(
        request=request_,
        start=figures.start,
        end=figures.end,
        range_assumed=False,
        as_of=AS_OF,
        figures=figures,
    )


def test_sla_template_states_as_of_range_percent_and_counts():
    figures = fake_result("", SlaComplianceResult, *JULY, None)
    text = render_answer(_metric_answer(figures))
    assert text == (
        "As of 2026-08-30: SLA compliance was 90.00% from 2026-07-01 to 2026-07-31 "
        "(inclusive, UTC): 45 of 50 dispatched requests were completed within their SLA "
        "window."
    )


def test_incident_rate_template_shows_per_100_and_counts():
    figures = fake_result("", IncidentRateResult, *JULY, None)
    text = render_answer(_metric_answer(figures))
    assert "0.9000 incidents per 100 completed requests" in text
    assert "45 incidents over 50 completed requests" in text


def test_first_time_fix_template():
    figures = fake_result("", FirstTimeFixResult, *JULY, None)
    assert "First-time fix rate was 90.00%" in render_answer(_metric_answer(figures))


def test_grouped_template_ranks_the_worst_five_and_points_to_the_data():
    figures = fake_result("", SlaComplianceResult, *JULY, "region")
    text = render_answer(_metric_answer(figures))
    assert "By region, worst first: g1 2.50% (1 of 40); g2 5.00% (2 of 40)" in text
    assert "g5 12.50% (5 of 40)." in text and "g6" not in text  # five only
    assert "left out" not in text and "in total" not in text  # nothing excluded or cut


def _groups_figures(denominators: list[int], **extra) -> SlaComplianceResult:
    groups = [
        GroupRate(group=f"r{i}", numerator=1, denominator=d, rate=rate_string(1, d))
        for i, d in enumerate(denominators)
    ]
    return SlaComplianceResult(
        start=JULY[0],
        end=JULY[1],
        group_by="region",
        numerator=len(groups),
        denominator=sum(denominators),
        rate=rate_string(len(groups), sum(denominators)),
        groups=groups,
        group_count=extra.pop("group_count", len(groups)),
        **extra,
    )


def test_groups_below_the_minimum_are_left_out_of_the_text_only():
    """r0 (3 cases) would rank first on one miss; it is left out of the ranking."""
    figures = _groups_figures([3, 40, 50, 19])
    answer = _metric_answer(figures)
    text = render_answer(answer)
    assert "By region, worst first: r1 2.50% (1 of 40); r2 2.00% (1 of 50)." in text
    assert "r0" not in text and "r3" not in text
    assert "2 regions left out of the ranking for fewer than 20 cases; all are in the data." in text
    # The data part still carries every group, with its counts.
    assert [g.group for g in answer.figures.groups] == ["r0", "r1", "r2", "r3"]
    assert answer.figures.groups[0].denominator == 3


def test_the_minimum_is_configurable():
    figures = _groups_figures([3, 40])
    assert "r0" not in render_answer(_metric_answer(figures))
    loose = render_answer(_metric_answer(figures), min_denominator=3)
    assert "By region, worst first: r0 33.33% (1 of 3); r1 2.50% (1 of 40)." in loose
    assert "left out" not in loose


def test_minimum_defaults_to_20_from_config(monkeypatch):
    assert Settings().min_group_denominator == 20
    monkeypatch.setenv("REPORTING_MIN_GROUP_DENOMINATOR", "5")
    assert Settings.from_env().min_group_denominator == 5


def test_when_no_group_has_enough_cases_nothing_is_ranked():
    text = render_answer(_metric_answer(_groups_figures([3, 5])))
    assert "By region: no region has at least 20 cases to rank." in text
    assert "2 regions left out of the ranking for fewer than 20 cases" in text


def test_truncated_group_list_says_the_worst_are_kept():
    groups = [
        GroupRate(group=f"t{i}", group_id=i, numerator=1, denominator=30, rate="0.0333")
        for i in range(25)
    ]
    figures = FirstTimeFixResult(
        start=JULY[0],
        end=JULY[1],
        group_by="technician",
        numerator=25,
        denominator=750,
        rate="0.0333",
        groups=groups,
        group_count=32,
        truncated=True,
    )
    text = render_answer(_metric_answer(figures))
    assert "32 technicians in total; the worst 25 are in the data." in text


def test_technician_incident_rate_says_attributable_only():
    figures = fake_result("", IncidentRateResult, *JULY, "technician")
    text = render_answer(_metric_answer(figures))
    assert "attributable incidents only (ADR-033)" in text
    assert "completed jobs" in text  # every technician rate shows its job count


def test_null_rate_is_stated_not_shown_as_zero():
    figures = IncidentRateResult(start=JULY[0], end=JULY[1], numerator=2, denominator=0)
    text = render_answer(_metric_answer(figures))
    assert "No requests were completed" in text and "no incident rate" in text
    assert "2 incidents reported" in text


def test_answer_rejects_figures_for_another_metric_or_breakdown():
    figures = fake_result("", SlaComplianceResult, *JULY, "region")
    with pytest.raises(ValueError, match="metric"):
        _metric_answer(figures, req("incident_rate", group_by="region", start=JULY[0], end=JULY[1]))
    with pytest.raises(ValueError, match="breakdown"):
        _metric_answer(figures, req("sla_compliance", start=JULY[0], end=JULY[1]))


def test_prompt_json_template_keys_follow_the_schema_property_order():
    """Gemini's structured output writes keys in the schema's property order. If the
    prompt's template orders them differently, the model can write a later key first and
    then has no way back to the ones it skipped: parse_v3 lost every date this way while
    `technician_name` sat after `end` in the model (L-51)."""
    import re

    from agent_reporting.parsing import load_parse_prompt

    template = next(
        line for line in load_parse_prompt().text.splitlines() if line.startswith('{"metric"')
    )
    keys = re.findall(r'"(\w+)":', template)
    assert keys == list(ReportingRequest.model_json_schema()["properties"])


#: Questions that look like template syntax. The question is data: it renders without
#: error and reaches the model client unchanged (security-model.md, section 3).
TEMPLATE_SYNTAX_QUESTIONS = [
    "what is {{x}}?",
    "show {0} incidents",
    "odd }}{{ braces",
    "{{as_of}} and {{question}} and {1} and {name}",
]


@pytest.mark.anyio
@pytest.mark.parametrize("question", TEMPLATE_SYNTAX_QUESTIONS)
async def test_parse_sends_template_syntax_in_a_question_unchanged(question):
    from agent_reporting.parsing import Parser

    llm = FakeLLM(req(start=JULY[0], end=JULY[1]))
    await Parser(llm, AS_OF).parse(question, trace_id="t-syntax")
    [prompt] = llm.prompts
    assert f"<question>\n{question}\n</question>" in prompt
    assert prompt.count(question) == 1


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


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("name", "code", "total", "ids", "answer"),
    [
        ("Dave", "technician_not_found", 0, [], "No technician matches Dave."),
        (
            "Priya",
            "technician_ambiguous",
            2,
            [7, 8],
            "2 technicians match Priya: Priya Kim and Priya Castillo. "
            "Please ask again with the full name.",
        ),
    ],
)
async def test_technician_lookup_failures_log_counts_and_ids_not_names(
    mcp_calls, name, code, total, ids, answer
):
    question = "how is MARKER-Q7 doing on SLA?"
    with captured_logs("agent_reporting") as lines:
        task = await _send(
            create_app(SETTINGS, FakeLLM(req("sla_compliance", technician_name=name))),
            text=question,
            trace_id="t-names",
        )
        logged = lines()
    assert _failure(task) == (code, answer)  # the answer text is unchanged
    [failed] = [x for x in logged if x["msg"] == "task failed"]
    assert (failed["code"], failed["total_matches"], failed["technician_ids"]) == (code, total, ids)
    assert "reason" not in failed and failed["trace_id"] == "t-names"
    text = json.dumps(logged)
    for forbidden in (name, "Priya Kim", "Priya Castillo", "Kim", "Castillo", "MARKER-Q7"):
        assert forbidden not in text, forbidden


@pytest.mark.anyio
async def test_a_name_the_lookup_rejects_is_logged_without_the_name(monkeypatch):
    async def rejects(*args, **kwargs):
        raise McpToolError(
            "name must be 1 to 100 characters ... wildcards and patterns are not accepted"
        )

    monkeypatch.setattr(executor_mod, "call_tool", rejects)
    with captured_logs("agent_reporting") as lines:
        task = await _send(
            create_app(SETTINGS, FakeLLM(req("sla_compliance", technician_name="ZedMARKER%")))
        )
        logged = lines()
    assert _failure(task) == ("technician_not_found", "No technician matches ZedMARKER%.")
    [failed] = [x for x in logged if x["msg"] == "task failed"]
    assert failed["total_matches"] == 0 and failed["name_rejected"] is True
    assert "ZedMARKER" not in json.dumps(logged)
