"""Offline tests for the orchestrator: task-to-answer extraction, `/ask` error mapping,
the A2A timeout, and the CLI. The live A2A hop is covered by the e2e test."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from a2a.helpers.proto_helpers import new_data_part, new_text_part
from a2a.types import Artifact, Message, Role, Task, TaskState, TaskStatus
from fastapi.testclient import TestClient
from orchestrator import __main__ as cli
from orchestrator import app as app_mod
from orchestrator.a2a_client import send_question
from orchestrator.app import create_app
from orchestrator.config import Settings
from orchestrator.result import TaskFailed, extract_answer

FIGURES = {
    "start": "2026-06-01",
    "end": "2026-08-30",
    "incident_count": 172,
    "by_severity": {"low": 93, "medium": 54, "high": 25},
}


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _task(state=TaskState.TASK_STATE_COMPLETED, parts=None, reason=None) -> Task:
    status = TaskStatus(state=state)
    if reason:
        status.message.CopyFrom(
            Message(message_id="m", role=Role.ROLE_AGENT, parts=[new_text_part(reason)])
        )
    artifacts = [] if parts is None else [Artifact(artifact_id="a", name="r", parts=parts)]
    return Task(id="task-1", context_id="ctx", status=status, artifacts=artifacts)


def _completed() -> Task:
    return _task(parts=[new_text_part("172 incidents ..."), new_data_part(FIGURES)])


# --------------------------------------------------------------------------- extraction


def test_extract_answer_restores_integers():
    answer, figures = extract_answer(_completed())
    assert answer == "172 incidents ..."
    # Protobuf Value carries numbers as doubles; the contract restores ints.
    assert figures == FIGURES
    assert isinstance(figures["incident_count"], int)


def test_failed_task_raises_with_reason():
    with pytest.raises(TaskFailed, match="MCP call timed out") as info:
        extract_answer(_task(TaskState.TASK_STATE_FAILED, reason="MCP call timed out"))
    assert info.value.state == "TASK_STATE_FAILED"


def test_figures_that_break_the_contract_are_rejected():
    bad = dict(FIGURES, incident_count=999)  # by_severity no longer sums to it
    with pytest.raises(TaskFailed, match="validation"):
        extract_answer(_task(parts=[new_text_part("x"), new_data_part(bad)]))


def test_missing_data_part_is_rejected():
    with pytest.raises(TaskFailed, match="missing"):
        extract_answer(_task(parts=[new_text_part("x")]))


# --------------------------------------------------------------------------- /ask


def _ask(monkeypatch, behaviour) -> httpx.Response:
    async def fake(agent_url, question, *, trace_id, timeout_s):
        return behaviour(trace_id)

    monkeypatch.setattr(app_mod, "send_question", fake)
    with TestClient(create_app(Settings())) as client:
        return client.post("/ask", json={"question": "How many incidents?"})


def test_ask_success(monkeypatch):
    response = _ask(monkeypatch, lambda trace_id: _completed())
    assert response.status_code == 200
    body = response.json()
    assert body["figures"] == FIGURES
    assert body["task_id"] == "task-1"
    assert body["route"] == "reporting"
    assert len(body["trace_id"]) == 32
    assert response.headers["X-Trace-Id"] == body["trace_id"]


def test_ask_trace_id_is_what_was_sent(monkeypatch):
    sent = {}

    def behaviour(trace_id):
        sent["trace_id"] = trace_id
        return _completed()

    body = _ask(monkeypatch, behaviour).json()
    assert body["trace_id"] == sent["trace_id"]


def _raise(exc):
    def behaviour(trace_id):
        raise exc

    return behaviour


@pytest.mark.parametrize(
    ("exc", "status", "error"),
    [
        (TimeoutError(), 504, "agent_timeout"),
        (httpx.ConnectError("refused"), 502, "agent_unavailable"),
    ],
)
def test_ask_maps_transport_errors(monkeypatch, exc, status, error):
    response = _ask(monkeypatch, _raise(exc))
    assert response.status_code == status
    assert response.json()["error"] == error
    assert response.json()["trace_id"]


def test_ask_maps_failed_task(monkeypatch):
    response = _ask(monkeypatch, lambda t: _task(TaskState.TASK_STATE_FAILED, reason="boom"))
    assert response.status_code == 502
    assert response.json() | {"trace_id": None} == {
        "error": "agent_task_failed",
        "detail": "boom",
        "trace_id": None,
        "task_id": "task-1",
        "state": "TASK_STATE_FAILED",
    }


def test_ask_rejects_empty_question():
    with TestClient(create_app(Settings())) as client:
        assert client.post("/ask", json={"question": ""}).status_code == 422


# --------------------------------------------------------------------------- timeout


@pytest.mark.anyio
async def test_send_question_times_out_instead_of_hanging():
    async def never_answers(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(30)
        raise AssertionError("unreachable")

    loop = asyncio.get_running_loop()
    began = loop.time()
    with pytest.raises(TimeoutError):
        await send_question(
            "http://agent.test",
            "q",
            trace_id="t",
            timeout_s=0.3,
            transport=httpx.MockTransport(never_answers),
        )
    assert loop.time() - began < 5


# --------------------------------------------------------------------------- CLI


def test_cli_prints_answer(monkeypatch, capsys):
    body = {"answer": "172 incidents", "figures": FIGURES, "task_id": "t1", "trace_id": "tr"}
    monkeypatch.setattr(
        cli.httpx, "post", lambda url, json, timeout: httpx.Response(200, json=body)
    )
    assert cli.main(["ask", "How many?", "--url", "http://x"]) == 0
    out = capsys.readouterr().out
    assert "172 incidents" in out
    assert "trace_id=tr" in out
    assert json.dumps(FIGURES["by_severity"]["low"]) in out


def test_cli_waits_longer_than_the_ceiling():
    assert cli.CLI_TIMEOUT_S > 120  # ADR-034
