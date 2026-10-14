"""What the user typed never reaches a log line, at INFO or DEBUG (ADR-108, L-60; TS-15-D).

The question names a technician. Every model reply, every exception and every tool failure in
the path repeats that name, as real ones do. The request goes orchestrator -> A2A -> reporting
agent over the real SDK client and server (in-process), with the logging configuration the
services use (`configure_logging`), and no log line may contain any part of the name.
"""

from __future__ import annotations

import io
import json
import logging
import sys

import httpx
import pytest
from agent_reporting import executor as executor_mod
from agent_reporting.app import create_app as create_agent
from agent_reporting.config import Settings as AgentSettings
from common import JsonFormatter, configure_logging
from fastapi.testclient import TestClient
from llm import LLMResult
from orchestrator import app as app_mod
from orchestrator.a2a_client import send_question
from orchestrator.app import create_app as create_orchestrator
from orchestrator.config import Settings as OrchestratorSettings
from schemas import ReportingRequest, RouteDecision

NAME = "Quillfeather Zanthia"
PIECES = ("Quillfeather", "Zanthia", "quillfeather", "zanthia")
QUESTION = f"How is {NAME} doing on SLA compliance last month?"
AGENT_URL = "http://agent.test"


class FakeLLM:
    """The model: its reply repeats what the user typed, as a real one does."""

    def __init__(self, parsed, model_name="gemini-3.5-flash-lite"):
        self.parsed, self.model_name = parsed, model_name

    async def generate(self, prompt, *, model=None, response_model=None, trace_id):
        return LLMResult(
            text=self.parsed.model_dump_json(),
            parsed=self.parsed,
            model=self.model_name,
            input_tokens=100,
            output_tokens=10,
            cost_usd=0.0001,
            latency_s=0.01,
            attempts=1,
        )


@pytest.fixture
def logs():
    """Production logging (`configure_logging`), at DEBUG, into a string."""
    root = logging.getLogger()
    saved = (list(root.handlers), root.level)
    names = ("a2a", "mcp", "httpx", "httpx2", "httpcore", "a2a.client.card_resolver")
    levels = {n: logging.getLogger(n).level for n in names}
    configure_logging("test", "DEBUG")
    stream = io.StringIO()
    root.handlers[0].setStream(stream)
    root.handlers[0].setFormatter(JsonFormatter("test"))
    for n in ("orchestrator", "agent_reporting", "access", "llm", "gateway"):
        logging.getLogger(n).disabled = False
    try:
        yield lambda: [json.loads(x) for x in stream.getvalue().splitlines()]
    finally:
        for h in list(root.handlers):
            root.removeHandler(h)
        for h in saved[0]:
            root.addHandler(h)
        root.setLevel(saved[1])
        for n, level in levels.items():
            logging.getLogger(n).setLevel(level)


def _run(monkeypatch, *, tool_error: Exception):
    agent = create_agent(
        AgentSettings(public_url=f"{AGENT_URL}/"),
        FakeLLM(ReportingRequest(metric="sla_compliance", technician_name=NAME)),
    )
    transport = httpx.ASGITransport(app=agent)

    async def fake_send(agent_url, question, **kw):
        return await send_question(AGENT_URL, question, transport=transport, **kw)

    async def failing_tool(*args, **kwargs):
        raise tool_error

    monkeypatch.setattr(app_mod, "send_question", fake_send)
    monkeypatch.setattr(executor_mod, "call_tool", failing_tool)
    router = FakeLLM(
        RouteDecision(
            route="reporting", domains=["reporting"], reason=f"The user asks about {NAME}'s SLA."
        )
    )
    with TestClient(create_orchestrator(OrchestratorSettings(), router)) as client:
        return client.post("/ask", json={"question": QUESTION})


def _forbid(lines):
    text = json.dumps(lines)
    for piece in PIECES:
        assert piece not in text, piece


def test_a_typed_technician_name_is_in_no_log_line_from_any_service(monkeypatch, logs):
    response = _run(monkeypatch, tool_error=RuntimeError(f"socket closed while looking up {NAME}"))
    lines = logs()
    assert response.status_code in (200, 502, 503)  # the answer path is not what is asserted
    # Not vacuous: the whole path ran and logged, failure and traceback included.
    messages = {x["msg"] for x in lines}
    assert {"route decision", "question parsed", "MCP call failed", "task failed"} <= messages
    _forbid(lines)
    # The two services both logged, under the one trace id.
    services = {x["logger"] for x in lines if x.get("trace_id") == response.headers["X-Trace-Id"]}
    assert {"orchestrator", "agent_reporting"} <= services


def test_an_exception_is_logged_as_classes_and_frames_not_its_message(monkeypatch, logs):
    try:
        try:
            raise ValueError(f"bad value {NAME}")
        except ValueError as inner:
            raise RuntimeError("wrapper") from inner
    except RuntimeError:
        logging.getLogger("agent_reporting").exception("MCP call failed", extra={"tool": "t"})
    [line] = [x for x in logs() if x["msg"] == "MCP call failed"]
    assert "RuntimeError" in line["exc"] and "ValueError" in line["exc"]
    assert "test_log_redaction.py" in line["exc"]  # the frames are still there
    _forbid([line])


def test_the_routers_reason_is_a_length_and_a_hash(monkeypatch, logs):
    _run(monkeypatch, tool_error=RuntimeError("x"))
    [decision] = [x for x in logs() if x["msg"] == "route decision"]
    assert "reason" not in decision and decision["reason_chars"] > 0
    assert len(decision["reason_sha"]) == 12


def test_a_sdk_debug_line_cannot_carry_the_question(monkeypatch, logs):
    """`configure_logging` holds the A2A and MCP SDK loggers at INFO whatever LOG_LEVEL says."""
    _run(monkeypatch, tool_error=RuntimeError("x"))
    assert logging.getLogger("a2a").level >= logging.INFO
    assert logging.getLogger("mcp").level >= logging.INFO
    assert sys.modules  # keep the fixture's configuration in scope
