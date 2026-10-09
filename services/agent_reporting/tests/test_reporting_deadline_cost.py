"""The reporting agent under the request deadline and its cost report (ADR-088)."""

from __future__ import annotations

import asyncio
import time
import uuid

import httpx
import pytest
import test_agent_reporting as base
from a2a.client import ClientConfig, create_client
from a2a.types import Message, Part, Role, SendMessageRequest, TaskState
from agent_reporting import executor as executor_mod
from agent_reporting.app import create_app
from common import DEADLINE_KEY, add_cost
from google.protobuf.json_format import MessageToDict
from test_agent_reporting import BASE, JULY, SETTINGS, FakeLLM, req

# Fixtures of the sibling module, re-bound here so pytest finds them.
anyio_backend = base.anyio_backend
mcp_calls = base.mcp_calls

_JULY = {"start": JULY[0], "end": JULY[1]}


class CostLLM(FakeLLM):
    """Adds its list-price cost to the request's running total, as `LLMClient` does."""

    async def generate(self, prompt, **kwargs):
        add_cost(0.0004)
        return await super().generate(prompt, **kwargs)


async def send(app, metadata=None, text="How many incidents were reported last month?"):
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


def failure(task):
    message = task.status.message
    return MessageToDict(message.metadata).get("error_code"), message.parts[0].text


def in_ms(seconds: float) -> float:
    return (time.time() + seconds) * 1000


# --------------------------------------------------------------------------- the deadline


@pytest.mark.anyio
async def test_an_expired_deadline_fails_the_task_before_any_model_call(mcp_calls):
    llm = FakeLLM(req("incident_count", **_JULY))
    task = await send(create_app(SETTINGS, llm), {DEADLINE_KEY: in_ms(-30)})
    assert task.status.state == TaskState.TASK_STATE_FAILED
    assert failure(task)[0] == "deadline_exceeded"
    assert llm.prompts == [] and mcp_calls == []


@pytest.mark.anyio
async def test_only_the_reserve_left_is_also_expired(mcp_calls):
    llm = FakeLLM(req("incident_count", **_JULY))
    task = await send(create_app(SETTINGS, llm), {DEADLINE_KEY: in_ms(4.5)})
    assert failure(task)[0] == "deadline_exceeded" and llm.prompts == []


@pytest.mark.anyio
async def test_a_live_deadline_lets_the_task_complete(mcp_calls):
    llm = FakeLLM(req("incident_count", **_JULY))
    task = await send(create_app(SETTINGS, llm), {DEADLINE_KEY: in_ms(60)})
    assert task.status.state == TaskState.TASK_STATE_COMPLETED


@pytest.mark.anyio
async def test_the_mcp_call_is_clamped_to_the_deadline(monkeypatch):
    seen = {}

    async def spy(url, tool, arguments, result_model, *, trace_id, timeout_s):
        from common import clamp_to_deadline

        seen["clamped"] = clamp_to_deadline(timeout_s)
        raise executor_mod.McpToolError("incident query failed")

    monkeypatch.setattr(executor_mod, "call_tool", spy)
    llm = FakeLLM(req("incident_count", **_JULY))
    await send(create_app(SETTINGS, llm), {DEADLINE_KEY: in_ms(12)})
    assert seen["clamped"] == pytest.approx(7.0, abs=1.0)  # 12 s left, 5 s reserved (cap is 15)


@pytest.mark.anyio
async def test_a_deadline_that_runs_out_before_the_query_fails_the_task(monkeypatch):
    async def out_of_time(url, tool, arguments, result_model, *, trace_id, timeout_s):
        from common import DeadlineExceeded

        raise DeadlineExceeded("none left")

    monkeypatch.setattr(executor_mod, "call_tool", out_of_time)
    llm = FakeLLM(req("incident_count", **_JULY))
    task = await send(create_app(SETTINGS, llm), {DEADLINE_KEY: in_ms(60)})
    assert failure(task)[0] == "deadline_exceeded"


@pytest.mark.anyio
@pytest.mark.parametrize("bad", ["soon", True, -5, 0, [1], {"a": 1}, in_ms(86_400 * 365)])
async def test_a_malformed_deadline_is_never_trusted(mcp_calls, bad):
    """Replaced by the agent's own 120 s (or clamped to it); the task still completes."""
    llm = FakeLLM(req("incident_count", **_JULY))
    task = await send(create_app(SETTINGS, llm), {DEADLINE_KEY: bad})
    assert task.status.state == TaskState.TASK_STATE_COMPLETED


@pytest.mark.anyio
async def test_a_missing_deadline_gets_the_agents_default(mcp_calls):
    llm = FakeLLM(req("incident_count", **_JULY))
    task = await send(create_app(SETTINGS, llm))
    assert task.status.state == TaskState.TASK_STATE_COMPLETED


@pytest.mark.anyio
async def test_a_slow_parse_is_cut_at_the_deadline_not_the_agents_cap(mcp_calls):
    class Slow(FakeLLM):
        async def generate(self, prompt, **kwargs):
            await asyncio.sleep(3600)

    # 5.3 s left, 0.3 s usable: the 30 s parse cap would otherwise wait far longer.
    task = await asyncio.wait_for(
        send(create_app(SETTINGS, Slow(req("incident_count"))), {DEADLINE_KEY: in_ms(5.3)}),
        timeout=10,
    )
    assert failure(task)[0] == "model_unavailable"  # the existing parse-timeout code


# --------------------------------------------------------------------------- the cost report


@pytest.mark.anyio
async def test_a_completed_task_reports_its_list_price_cost(mcp_calls):
    llm = CostLLM(req("incident_count", **_JULY))
    task = await send(create_app(SETTINGS, llm))
    [artifact] = task.artifacts
    assert MessageToDict(artifact.metadata)["cost_usd"] == pytest.approx(0.0004)
    assert MessageToDict(artifact.metadata)["schema"] == "ReportingAnswer"


@pytest.mark.anyio
async def test_a_failed_task_reports_its_cost_too(mcp_calls):
    llm = CostLLM(req("sla_compliance", technician_name="Dave"))
    task = await send(create_app(SETTINGS, llm))
    metadata = MessageToDict(task.status.message.metadata)
    assert metadata["error_code"] == "technician_not_found"
    assert metadata["cost_usd"] == pytest.approx(0.0004)


@pytest.mark.anyio
async def test_concurrent_requests_report_their_own_costs(mcp_calls):
    class Priced(FakeLLM):
        def __init__(self, parsed, cost):
            super().__init__(parsed)
            self.cost = cost

        async def generate(self, prompt, **kwargs):
            await asyncio.sleep(0.01)
            add_cost(self.cost)
            return await super().generate(prompt, **kwargs)

    one, two = await asyncio.gather(
        send(create_app(SETTINGS, Priced(req("incident_count", **_JULY), 0.001))),
        send(create_app(SETTINGS, Priced(req("incident_count", **_JULY), 0.007))),
    )
    costs = sorted(MessageToDict(t.artifacts[0].metadata)["cost_usd"] for t in (one, two))
    assert costs == [pytest.approx(0.001), pytest.approx(0.007)]


def test_metadata_protobuf_cannot_serialise_is_ignored_not_a_crash():
    """An infinite number in message metadata: the SDK rejects it on the way in over HTTP, but
    the executor's own readers must not crash on it either (they are called with the message)."""
    from types import SimpleNamespace

    from agent_reporting.executor import deadline_of, message_metadata, trace_id_of

    message = Message(
        message_id="m",
        role=Role.ROLE_USER,
        parts=[Part(text="q")],
        metadata={"trace_id": "t-9", DEADLINE_KEY: float("inf")},
    )
    context = SimpleNamespace(message=message, metadata={"trace_id": "from-request"})
    assert message_metadata(context) == {}
    assert deadline_of(context).origin == "missing"  # the agent's own default
    assert trace_id_of(context) == "from-request"  # falls back to the request metadata
