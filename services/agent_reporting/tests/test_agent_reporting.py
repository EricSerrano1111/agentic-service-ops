"""Offline tests for the reporting agent: Agent Card, rendering, question parsing
(ADR-046, ADR-050) and the A2A task flow.

The A2A flow runs through the real SDK client and server, in-process over an ASGI
transport. The LLM is a fake with the `LLMClient.generate` signature, and the MCP call is
replaced. The live hops are covered by the e2e tests.
"""

from __future__ import annotations

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
    GroupRate,
    IncidentRateResult,
    IncidentSummary,
    ReportingAnswer,
    ReportingRequest,
    SeverityCounts,
    SlaComplianceResult,
    rate_string,
)

BASE = "http://agent.test"
AS_OF = dt.date(2026, 8, 30)
SETTINGS = Settings(public_url=f"{BASE}/")
JULY = (dt.date(2026, 7, 1), dt.date(2026, 7, 31))


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


def fake_result(tool: str, result_model, start, end, group_by):
    if result_model is IncidentSummary:
        return summary(start, end)
    groups = None
    if group_by is not None:
        groups = [
            GroupRate(group=f"g{i}", numerator=i, denominator=10, rate=rate_string(i, 10))
            for i in range(9, 2, -1)  # 7 groups, highest rate first
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
    )


@pytest.fixture
def mcp_calls(monkeypatch):
    """Replace the MCP call; record its arguments; answer with fixed figures."""
    calls: list[dict] = []

    async def fake(url, tool, arguments, result_model, *, trace_id, timeout_s):
        start = dt.date.fromisoformat(arguments["start"])
        end = dt.date.fromisoformat(arguments["end"])
        group_by = arguments.get("group_by")
        calls.append(
            {"tool": tool, "start": start, "end": end, "group_by": group_by, "trace_id": trace_id}
        )
        return fake_result(tool, result_model, start, end, group_by)

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
    assert line["prompt_version"] == "parse_v2" and len(line["prompt_sha"]) == 12
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
            req("incident_count", group_by="region", start=JULY[0], end=JULY[1]),
            "Incident counts can't be broken down yet",
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


def test_grouped_template_lists_the_top_five_and_points_to_the_data():
    figures = fake_result("", SlaComplianceResult, *JULY, "region")
    text = render_answer(_metric_answer(figures))
    assert "By region, highest first: g9 90.00% (9 of 10); g8 80.00% (8 of 10)" in text
    assert "g5 50.00% (5 of 10)." in text and "g4" not in text  # top 5 only
    assert "7 regions in total; all are in the data." in text


def test_truncated_group_list_says_so():
    groups = [
        GroupRate(group=f"t{i}", group_id=i, numerator=1, denominator=10, rate="0.1000")
        for i in range(25)
    ]
    figures = FirstTimeFixResult(
        start=JULY[0],
        end=JULY[1],
        group_by="technician",
        numerator=25,
        denominator=250,
        rate="0.1000",
        groups=groups,
        group_count=32,
        truncated=True,
    )
    text = render_answer(_metric_answer(figures))
    assert "32 technicians in total; the top 25 are in the data." in text


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
