"""Offline tests for the reporting agent: Agent Card, rendering, and the A2A task flow.

The A2A flow runs through the real SDK client and server, in-process over an ASGI
transport, with the MCP call replaced by a fake. The live MCP hop is covered by the e2e
test.
"""

from __future__ import annotations

import datetime as dt
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
from agent_reporting.render import render_incident_summary
from fastapi.testclient import TestClient
from google.protobuf.json_format import MessageToDict
from schemas import IncidentSummary, SeverityCounts

BASE = "http://agent.test"
SETTINGS = Settings(public_url=f"{BASE}/")
SUMMARY = IncidentSummary(
    start=dt.date(2026, 6, 1),
    end=dt.date(2026, 8, 30),
    incident_count=172,
    by_severity=SeverityCounts(low=93, medium=54, high=25),
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


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
    with TestClient(create_app(SETTINGS)) as client:
        body = client.get(AGENT_CARD_WELL_KNOWN_PATH).json()
        assert client.get("/healthz").json()["status"] == "ok"
    assert body["capabilities"] == {"streaming": False, "pushNotifications": False}
    assert [s["id"] for s in body["skills"]] == [SKILL_ID]


# --------------------------------------------------------------------------- rendering


def test_render_incident_summary():
    assert render_incident_summary(SUMMARY) == (
        "172 incidents reported from 2026-06-01 to 2026-08-30 (inclusive, UTC): "
        "25 high, 54 medium, 93 low severity."
    )


def test_render_singular_and_thousands():
    one = SUMMARY.model_copy(
        update={"incident_count": 1, "by_severity": SeverityCounts(low=1, medium=0, high=0)}
    )
    assert render_incident_summary(one).startswith("1 incident reported")
    many = SUMMARY.model_copy(
        update={"incident_count": 1500, "by_severity": SeverityCounts(low=1500, medium=0, high=0)}
    )
    assert render_incident_summary(many).startswith("1,500 incidents")


# --------------------------------------------------------------------------- A2A task flow


async def _send(app, text: str = "How many incidents?", trace_id: str = "t-1"):
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


@pytest.mark.anyio
async def test_completed_task_has_text_and_data_parts(monkeypatch):
    seen = {}

    async def fake(url, start, end, *, trace_id, timeout_s):
        seen.update(start=start, end=end, trace_id=trace_id)
        return SUMMARY

    monkeypatch.setattr(executor_mod, "get_incidents_by_date_range", fake)
    task = await _send(create_app(SETTINGS), trace_id="trace-abc")

    assert task.status.state == TaskState.TASK_STATE_COMPLETED
    [artifact] = task.artifacts
    text, data = artifact.parts
    assert text.text == render_incident_summary(SUMMARY)
    assert IncidentSummary.model_validate(MessageToDict(data.data)) == SUMMARY
    # The trace id crossed the A2A hop in the message metadata.
    assert seen["trace_id"] == "trace-abc"
    # TODO(ADR-046) behaviour: the configured range, whatever the question says.
    assert (seen["start"], seen["end"]) == (
        SETTINGS.skeleton_range_start,
        SETTINGS.skeleton_range_end,
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (TimeoutError(), "timed out"),
        (McpToolError("start (x) is after end (y)"), "incidents tool error: start (x)"),
        (ConnectionError("refused"), "incidents MCP server unavailable"),
    ],
)
async def test_mcp_failures_end_in_failed_task(monkeypatch, error, reason):
    async def fake(*args, **kwargs):
        raise error

    monkeypatch.setattr(executor_mod, "get_incidents_by_date_range", fake)
    task = await _send(create_app(SETTINGS))

    assert task.status.state == TaskState.TASK_STATE_FAILED
    assert reason in task.status.message.parts[0].text
    assert not task.artifacts
