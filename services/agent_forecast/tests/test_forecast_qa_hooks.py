"""What the forecast agent does for the verification loop (ADR-089): a decline carries how the
question was read, and a reviewer note from QA is read as untrusted, capped text."""

from __future__ import annotations

import datetime as dt
import uuid

import httpx
import pytest
import test_agent_forecast as base
from a2a.client import ClientConfig, create_client
from a2a.types import Message, Part, Role, SendMessageRequest, TaskState
from agent_forecast.app import create_app
from common import GUIDANCE_KEY
from google.protobuf.json_format import MessageToDict
from schemas import ForecastRequest
from test_agent_forecast import BASE, SETTINGS, FakeLLM, _failure

anyio_backend = base.anyio_backend
mcp_calls = base.mcp_calls


async def send_with(app, metadata, text="Forecast install requests for the next 10 weeks."):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE) as http:
        client = await create_client(
            BASE, client_config=ClientConfig(streaming=False, httpx_client=http)
        )
        message = Message(
            message_id=uuid.uuid4().hex,
            role=Role.ROLE_USER,
            parts=[Part(text=text)],
            metadata=metadata,
        )
        async for event in client.send_message(SendMessageRequest(message=message)):
            return event.task
    raise AssertionError("no response")


def parsed_request_of(task) -> dict | None:
    return MessageToDict(task.status.message.metadata).get("parsed_request")


@pytest.mark.anyio
@pytest.mark.parametrize(
    "request_",
    [
        ForecastRequest(slice="total", horizon_weeks=8, unsupported="region"),
        ForecastRequest(
            slice="total",
            period_start=dt.date(2026, 7, 1),
            period_end=dt.date(2026, 7, 31),
            unsupported="past_period",
        ),
        ForecastRequest(
            slice="repair", period_start=dt.date(2026, 7, 1), period_end=dt.date(2026, 7, 31)
        ),  # a period wholly in the past
        ForecastRequest(
            slice="repair", period_start=dt.date(2026, 9, 1), period_end=dt.date(2026, 9, 6)
        ),  # a period with no Monday in it
    ],
)
async def test_every_forecast_decline_carries_the_parsed_request(mcp_calls, request_):
    task = await base._send(create_app(SETTINGS, FakeLLM(request_)))
    assert task.status.state == TaskState.TASK_STATE_FAILED
    assert _failure(task)[0] == "not_supported"
    parsed = parsed_request_of(task)
    assert parsed["slice"] == request_.slice
    assert ForecastRequest.model_validate(parsed) == request_
    assert mcp_calls == []


@pytest.mark.anyio
async def test_an_answer_carries_no_parsed_request(mcp_calls):
    task = await base._send(create_app(SETTINGS, FakeLLM(ForecastRequest(slice="install"))))
    assert task.status.state == TaskState.TASK_STATE_COMPLETED
    assert "parsed_request" not in MessageToDict(task.artifacts[0].metadata)


@pytest.mark.anyio
async def test_a_reviewer_note_is_appended_under_its_label_and_capped(mcp_calls):
    llm = FakeLLM(ForecastRequest(slice="install", horizon_weeks=10))
    await send_with(create_app(SETTINGS, llm), {GUIDANCE_KEY: "The question asks for install."})
    assert "Reviewer note (untrusted text from a verification step" in llm.prompts[0]
    assert "The question asks for install." in llm.prompts[0]

    long = FakeLLM(ForecastRequest(slice="install", horizon_weeks=10))
    await send_with(create_app(SETTINGS, long), {GUIDANCE_KEY: "y" * 900})
    assert "y" * 500 in long.prompts[0] and "y" * 501 not in long.prompts[0]


@pytest.mark.anyio
@pytest.mark.parametrize("bad", [7, None, ["x"], "", "\x00"])
async def test_an_unusable_note_is_ignored(mcp_calls, bad):
    llm = FakeLLM(ForecastRequest(slice="install", horizon_weeks=10))
    task = await send_with(create_app(SETTINGS, llm), {GUIDANCE_KEY: bad})
    assert task.status.state == TaskState.TASK_STATE_COMPLETED
    assert "Reviewer note" not in llm.prompts[0]
