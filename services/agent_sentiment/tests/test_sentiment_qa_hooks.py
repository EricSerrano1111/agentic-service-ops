"""What the sentiment agent does for the verification loop (ADR-089, ADR-090): a decline carries
how the question was read, and a reviewer note from QA is read as untrusted, capped text."""

from __future__ import annotations

import uuid

import httpx
import pytest
import test_agent_sentiment as base
from a2a.client import ClientConfig, create_client
from a2a.types import Message, Part, Role, SendMessageRequest, TaskState
from agent_sentiment.app import create_app
from common import GUIDANCE_KEY
from google.protobuf.json_format import MessageToDict
from schemas import SentimentRequest
from test_agent_sentiment import BASE, SETTINGS, FakeLLM, _failure

anyio_backend = base.anyio_backend
mcp_calls = base.mcp_calls

REQUEST = SentimentRequest(region="west", want_trend=True)


async def send_with(app, metadata, text="Is sentiment trending down in the West?"):
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


@pytest.mark.anyio
@pytest.mark.parametrize("dimension", ["account", "technician", "service_type", "other"])
async def test_a_decline_carries_the_parsed_request_and_makes_no_mcp_call(mcp_calls, dimension):
    request = SentimentRequest(unsupported=dimension)
    task = await base._send(create_app(SETTINGS, FakeLLM(request)))
    assert task.status.state == TaskState.TASK_STATE_FAILED and _failure(task)[0] == "not_supported"
    parsed = MessageToDict(task.status.message.metadata)["parsed_request"]
    assert SentimentRequest.model_validate(parsed) == request
    assert mcp_calls == []


@pytest.mark.anyio
async def test_an_answer_carries_no_parsed_request(mcp_calls):
    task = await base._send(create_app(SETTINGS, FakeLLM(REQUEST)))
    assert task.status.state == TaskState.TASK_STATE_COMPLETED
    assert "parsed_request" not in MessageToDict(task.artifacts[0].metadata)


@pytest.mark.anyio
async def test_a_reviewer_note_is_appended_under_its_label_and_capped(mcp_calls):
    llm = FakeLLM(REQUEST)
    await send_with(create_app(SETTINGS, llm), {GUIDANCE_KEY: "The question is about the West."})
    assert "Reviewer note (untrusted text from a verification step" in llm.prompts[0]
    assert "The question is about the West." in llm.prompts[0]
    long = FakeLLM(REQUEST)
    await send_with(create_app(SETTINGS, long), {GUIDANCE_KEY: "y" * 900})
    assert "y" * 500 in long.prompts[0] and "y" * 501 not in long.prompts[0]


@pytest.mark.anyio
@pytest.mark.parametrize("bad", [7, None, ["x"], "", "\x00"])
async def test_an_unusable_note_is_ignored(mcp_calls, bad):
    llm = FakeLLM(REQUEST)
    task = await send_with(create_app(SETTINGS, llm), {GUIDANCE_KEY: bad})
    assert task.status.state == TaskState.TASK_STATE_COMPLETED
    assert "Reviewer note" not in llm.prompts[0]
