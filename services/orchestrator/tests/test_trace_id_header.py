"""The orchestrator takes the caller's trace id and puts it on every hop (ADR-108)."""

from __future__ import annotations

import re

import httpx
import pytest
from fastapi.testclient import TestClient
from orchestrator import app as app_mod
from orchestrator.a2a_client import send_question
from orchestrator.app import create_app
from orchestrator.config import Settings
from test_orchestrator import QUESTION, FakeLLM, Sent, decision

HEX32 = re.compile(r"[0-9a-f]{32}")


def _post(monkeypatch, headers=None):
    sent = Sent()
    seen: list[str] = []

    async def spy(agent_url, question, *, trace_id, timeout_s, **kwargs):
        seen.append(trace_id)
        return await sent(agent_url, question, trace_id=trace_id, timeout_s=timeout_s, **kwargs)

    monkeypatch.setattr(app_mod, "send_question", spy)
    with TestClient(create_app(Settings(), FakeLLM(decision("reporting")))) as client:
        response = client.post("/ask", json={"question": QUESTION}, headers=headers or {})
    return response, seen


def test_a_valid_incoming_id_is_the_requests_id_on_every_hop(monkeypatch):
    tid = "ef" * 16
    response, seen = _post(monkeypatch, {"X-Trace-Id": tid})
    assert response.status_code == 200
    assert response.headers["X-Trace-Id"] == tid and response.json()["trace_id"] == tid
    assert seen and set(seen) == {tid}  # the specialist and QA both got it


def test_a_request_with_no_id_is_given_one(monkeypatch):
    response, seen = _post(monkeypatch)
    tid = response.json()["trace_id"]
    assert HEX32.fullmatch(tid) and response.headers["X-Trace-Id"] == tid
    assert set(seen) == {tid}


def test_an_invalid_incoming_id_is_replaced(monkeypatch):
    response, seen = _post(monkeypatch, {"X-Trace-Id": "../../etc/passwd"})
    tid = response.json()["trace_id"]
    assert HEX32.fullmatch(tid) and set(seen) == {tid}


@pytest.mark.anyio
async def test_the_a2a_http_calls_carry_the_id_as_a_header():
    captured: list[httpx.Headers] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.headers)
        return httpx.Response(500)

    tid = "12" * 16
    with pytest.raises(Exception):  # noqa: B017, PT011  # the stub is not an agent
        await send_question(
            "http://agent.test",
            "q",
            trace_id=tid,
            timeout_s=2.0,
            transport=httpx.MockTransport(handler),
        )
    assert captured and all(h.get("x-trace-id") == tid for h in captured)
