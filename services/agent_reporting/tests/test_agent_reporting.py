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
from llm import LLMDailyQuotaExhausted, LLMOutputInvalid, LLMRateLimited, LLMResult, LLMUnavailable
from schemas import IncidentSummary, ReportingAnswer, ReportingRequest, SeverityCounts

BASE = "http://agent.test"
AS_OF = dt.date(2026, 8, 30)
SETTINGS = Settings(public_url=f"{BASE}/")
JULY = (dt.date(2026, 7, 1), dt.date(2026, 7, 31))


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


@pytest.fixture
def mcp_calls(monkeypatch):
    """Replace the MCP call; record its arguments; answer with fixed figures."""
    calls: list[dict] = []

    async def fake(url, start, end, *, trace_id, timeout_s):
        calls.append({"start": start, "end": end, "trace_id": trace_id})
        return summary(start, end)

    monkeypatch.setattr(executor_mod, "get_incidents_by_date_range", fake)
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
    stated = resolve(ReportingRequest(start=dt.date(2025, 1, 1), end=dt.date(2025, 3, 31)), AS_OF)
    assert (stated.start, stated.end, stated.assumed) == (
        dt.date(2025, 1, 1),
        dt.date(2025, 3, 31),
        False,
    )
    empty = resolve(ReportingRequest(), AS_OF)
    assert ((empty.start, empty.end), empty.assumed) == (JULY, True)


def test_parsed_request_needs_both_dates_or_neither():
    with pytest.raises(ValueError):
        ReportingRequest(start=dt.date(2025, 1, 1))


def _answer(assumed: bool) -> ReportingAnswer:
    request = ReportingRequest() if assumed else ReportingRequest(start=JULY[0], end=JULY[1])
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
    llm = FakeLLM(ReportingRequest(start=JULY[0], end=JULY[1]))
    task = await _send(create_app(SETTINGS, llm), trace_id="trace-abc")

    assert task.status.state == TaskState.TASK_STATE_COMPLETED
    assert mcp_calls == [{"start": JULY[0], "end": JULY[1], "trace_id": "trace-abc"}]
    [artifact] = task.artifacts
    text, data = artifact.parts
    answer = ReportingAnswer.model_validate(MessageToDict(data.data))
    assert answer.request == ReportingRequest(start=JULY[0], end=JULY[1])
    assert (answer.start, answer.end, answer.range_assumed, answer.as_of) == (
        *JULY,
        False,
        AS_OF,
    )
    assert text.text == render_answer(answer)
    assert "As of 2026-08-30" in text.text


@pytest.mark.anyio
async def test_question_and_as_of_date_reach_the_parsing_prompt(mcp_calls):
    llm = FakeLLM(ReportingRequest(start=JULY[0], end=JULY[1]))
    settings = Settings(public_url=f"{BASE}/", as_of=dt.date(2025, 3, 15))
    await _send(create_app(settings, llm), text="incidents in the past 30 days")
    [prompt] = llm.prompts
    assert "incidents in the past 30 days" in prompt
    assert "2025-03-15" in prompt and "{{" not in prompt


@pytest.mark.anyio
async def test_no_date_defaults_to_last_full_month_and_says_so(mcp_calls):
    task = await _send(create_app(SETTINGS, FakeLLM(ReportingRequest())), text="Any incidents?")
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

    monkeypatch.setattr(executor_mod, "get_incidents_by_date_range", rejects)
    llm = FakeLLM(ReportingRequest(start=dt.date(2027, 1, 1), end=dt.date(2027, 1, 31)))
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

    monkeypatch.setattr(executor_mod, "get_incidents_by_date_range", fails)
    task = await _send(create_app(SETTINGS, FakeLLM(ReportingRequest(start=JULY[0], end=JULY[1]))))
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
        await _send(create_app(SETTINGS, FakeLLM(ReportingRequest())), trace_id="t-log")
    finally:
        logger.removeHandler(handler)
        logger.disabled = was_disabled
    [line] = [json.loads(x) for x in stream.getvalue().splitlines() if "question parsed" in x]
    assert line["prompt_version"] == "parse_v1" and len(line["prompt_sha"]) == 12
    assert line["trace_id"] == "t-log" and line["range_assumed"] is True
