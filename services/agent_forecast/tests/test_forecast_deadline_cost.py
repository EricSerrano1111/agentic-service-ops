"""The forecast agent under the request deadline and its cost report (ADR-088)."""

from __future__ import annotations

import time
import uuid

import httpx
import pytest
import test_agent_forecast as base
from a2a.client import ClientConfig, create_client
from a2a.types import Message, Part, Role, SendMessageRequest, TaskState
from agent_forecast.app import create_app
from common import DEADLINE_KEY, add_cost
from google.protobuf.json_format import MessageToDict
from schemas import ForecastRequest
from test_agent_forecast import BASE, SETTINGS, FakeLLM

# Fixtures of the sibling module, re-bound here so pytest finds them.
anyio_backend = base.anyio_backend
mcp_calls = base.mcp_calls

REQUEST = ForecastRequest(slice="install", horizon_weeks=10)


class CostLLM(FakeLLM):
    async def generate(self, prompt, **kwargs):
        add_cost(0.0004)
        return await super().generate(prompt, **kwargs)


async def send(app, metadata=None, text="Forecast install requests for the next 10 weeks."):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE) as http:
        client = await create_client(
            BASE, client_config=ClientConfig(streaming=False, httpx_client=http)
        )
        message = Message(
            message_id=uuid.uuid4().hex,
            role=Role.ROLE_USER,
            parts=[Part(text=text)],
            metadata={"trace_id": "t-1"} | (metadata or {}),
        )
        async for event in client.send_message(SendMessageRequest(message=message)):
            return event.task
    raise AssertionError("no response")


def in_ms(seconds: float) -> float:
    return (time.time() + seconds) * 1000


@pytest.mark.anyio
async def test_an_expired_deadline_fails_the_task_before_any_model_call(mcp_calls):
    llm = FakeLLM(REQUEST)
    task = await send(create_app(SETTINGS, llm), {DEADLINE_KEY: in_ms(-30)})
    assert task.status.state == TaskState.TASK_STATE_FAILED
    assert MessageToDict(task.status.message.metadata)["error_code"] == "deadline_exceeded"
    assert llm.prompts == [] and mcp_calls == []


@pytest.mark.anyio
@pytest.mark.parametrize("bad", ["soon", True, -5, 0, [1], in_ms(86_400 * 365)])
async def test_a_malformed_deadline_is_never_trusted(mcp_calls, bad):
    task = await send(create_app(SETTINGS, FakeLLM(REQUEST)), {DEADLINE_KEY: bad})
    assert task.status.state == TaskState.TASK_STATE_COMPLETED


@pytest.mark.anyio
async def test_a_completed_task_reports_its_list_price_cost(mcp_calls):
    task = await send(create_app(SETTINGS, CostLLM(REQUEST)))
    assert task.status.state == TaskState.TASK_STATE_COMPLETED
    assert MessageToDict(task.artifacts[0].metadata)["cost_usd"] == pytest.approx(0.0004)
