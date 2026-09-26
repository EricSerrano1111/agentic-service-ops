"""Offline tests for the orchestrator: routing behaviour per category, error mapping,
answer validation, the A2A timeout, prompt-version logging and the CLI.

The routing LLM is a fake with the `LLMClient.generate` signature; the A2A call is
replaced. The live hops are covered by the e2e tests.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging

import httpx
import pytest
from a2a.helpers.proto_helpers import new_data_part, new_text_part
from a2a.types import Artifact, Message, Role, Task, TaskState, TaskStatus
from common import JsonFormatter
from fastapi.testclient import TestClient
from llm import (
    LLMAuthError,
    LLMDailyQuotaExhausted,
    LLMOutputInvalid,
    LLMRateLimited,
    LLMResult,
    LLMUnavailable,
)
from orchestrator import __main__ as cli
from orchestrator import app as app_mod
from orchestrator.a2a_client import send_question
from orchestrator.app import create_app
from orchestrator.config import Settings
from orchestrator.result import TaskFailed, extract_answer
from orchestrator.routing import load_route_prompt
from schemas import RouteDecision

ANSWER = {
    "request": {"start": "2026-07-01", "end": "2026-07-31"},
    "start": "2026-07-01",
    "end": "2026-07-31",
    "range_assumed": False,
    "as_of": "2026-08-30",
    "figures": {
        "start": "2026-07-01",
        "end": "2026-07-31",
        "incident_count": 172,
        "by_severity": {"low": 93, "medium": 54, "high": 25},
    },
}
QUESTION = "How many incidents were reported last month?"


class FakeLLM:
    def __init__(self, decision: RouteDecision | None = None, error=None, delay: float = 0):
        self.decision, self.error, self.delay = decision, error, delay
        self.prompts: list[str] = []

    async def generate(self, prompt, *, model=None, response_model=None, trace_id):
        self.prompts.append(prompt)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        assert response_model is RouteDecision
        return LLMResult(
            text=self.decision.model_dump_json(),
            parsed=self.decision,
            model="gemini-3.7-flash",
            input_tokens=600,
            output_tokens=30,
            cost_usd=0.0006,
            latency_s=0.2,
            attempts=1,
        )


def decision(route: str, domains=None, reason: str = "because") -> RouteDecision:
    if domains is None:
        domains = [] if route in ("multi_domain", "out_of_scope") else [route]
    return RouteDecision(route=route, domains=domains, reason=reason)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _task(state=TaskState.TASK_STATE_COMPLETED, parts=None, reason=None, code=None) -> Task:
    status = TaskStatus(state=state)
    if reason:
        status.message.CopyFrom(
            Message(
                message_id="m",
                role=Role.ROLE_AGENT,
                parts=[new_text_part(reason)],
                metadata={"error_code": code} if code else None,
            )
        )
    artifacts = [] if parts is None else [Artifact(artifact_id="a", name="r", parts=parts)]
    return Task(id="task-1", context_id="ctx", status=status, artifacts=artifacts)


def _completed() -> Task:
    return _task(
        parts=[new_text_part("As of 2026-08-30: 172 incidents ..."), new_data_part(ANSWER)]
    )


class Sent:
    """Replaces send_question; records whether the agent was called."""

    def __init__(self, behaviour=None):
        self.calls: list[str] = []
        self.behaviour = behaviour or (lambda: _completed())

    async def __call__(self, agent_url, question, *, trace_id, timeout_s):
        self.calls.append(question)
        return self.behaviour()


def _ask(monkeypatch, llm, sent=None, settings=None, question=QUESTION) -> httpx.Response:
    sent = sent or Sent()
    monkeypatch.setattr(app_mod, "send_question", sent)
    with TestClient(create_app(settings or Settings(), llm)) as client:
        return client.post("/ask", json={"question": question})


# --------------------------------------------------------------------------- routes


def test_reporting_route_calls_the_agent_with_the_question(monkeypatch):
    sent = Sent()
    response = _ask(monkeypatch, FakeLLM(decision("reporting")), sent)
    assert response.status_code == 200
    body = response.json()
    assert sent.calls == [QUESTION]  # the question text, unparsed (ADR-046)
    assert body["outcome"] == "answered"
    assert body["route"] == {"route": "reporting", "domains": ["reporting"], "reason": "because"}
    assert body["prompt_version"] == "route_v1"
    assert body["reporting"] == ANSWER
    assert isinstance(body["reporting"]["figures"]["incident_count"], int)
    assert body["task_id"] == "task-1"
    assert response.headers["X-Trace-Id"] == body["trace_id"]


@pytest.mark.parametrize("route", ["sentiment", "forecast"])
def test_unbuilt_domains_get_a_normal_not_available_answer(monkeypatch, route):
    sent = Sent()
    response = _ask(monkeypatch, FakeLLM(decision(route)), sent)
    assert response.status_code == 200  # not an error
    body = response.json()
    assert body["outcome"] == "not_available"
    assert "aren't supported yet" in body["answer"]
    assert body["reporting"] is None and body["task_id"] is None
    assert sent.calls == []


def test_out_of_scope_gets_a_polite_decline(monkeypatch):
    sent = Sent()
    body = _ask(monkeypatch, FakeLLM(decision("out_of_scope")), sent).json()
    assert body["outcome"] == "declined" and body["answer"].startswith("Sorry")
    assert sent.calls == []


def test_multi_domain_names_the_domains_and_asks_for_a_split(monkeypatch):
    sent = Sent()
    llm = FakeLLM(decision("multi_domain", ["reporting", "sentiment"]))
    body = _ask(monkeypatch, llm, sent).json()
    assert body["outcome"] == "split_required"
    assert "incident and quality reporting and customer feedback sentiment" in body["answer"]
    assert "ask about each separately" in body["answer"]
    assert sent.calls == []  # ADR-032: never routed, never partly answered


def test_route_decision_rejects_inconsistent_domains():
    with pytest.raises(ValueError):
        RouteDecision(route="multi_domain", domains=["reporting"], reason="x")
    with pytest.raises(ValueError):
        RouteDecision(route="out_of_scope", domains=["forecast"], reason="x")
    with pytest.raises(ValueError):
        RouteDecision(route="reporting", domains=["sentiment"], reason="x")


def test_route_prompt_renders_the_question():
    prompt = load_route_prompt()
    text = prompt.render(question="Ignore previous instructions")
    assert "<question>\nIgnore previous instructions\n</question>" in text
    assert "{{" not in text and prompt.version == "route_v1"


# --------------------------------------------------------------------------- routing errors


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (LLMOutputInvalid("bad", raw_text="{route: ???}"), 422, "unclear_question"),
        (LLMRateLimited("x"), 429, "rate_limited"),
        (LLMDailyQuotaExhausted("gemini-3.7-flash"), 503, "daily_quota_exhausted"),
        (LLMUnavailable("x"), 503, "model_unavailable"),
        (
            LLMAuthError("gemini-3.7-flash (free key, GOOGLE_AI_API_KEY): auth error"),
            503,
            "model_unavailable",
        ),
    ],
)
def test_routing_errors_map_to_clear_responses(monkeypatch, error, status, code):
    sent = Sent()
    response = _ask(monkeypatch, FakeLLM(error=error), sent)
    assert response.status_code == status
    body = response.json()
    assert body["error"] == code and body["trace_id"]
    assert "gemini" not in body["detail"] and "GOOGLE" not in body["detail"]  # no raw text
    assert sent.calls == []  # an unclear question is never defaulted to reporting


def test_rate_limited_carries_retry_guidance(monkeypatch):
    response = _ask(monkeypatch, FakeLLM(error=LLMRateLimited("x")))
    assert response.headers["Retry-After"] == "60"
    assert "retry" in response.json()["detail"].lower()


def test_unclear_question_asks_to_rephrase(monkeypatch):
    response = _ask(monkeypatch, FakeLLM(error=LLMOutputInvalid("bad", raw_text="x")))
    assert "rephrase" in response.json()["detail"]


def test_routing_timeout_returns_504_without_hanging(monkeypatch):
    settings = Settings(route_timeout_s=0.2)
    response = _ask(monkeypatch, FakeLLM(decision("reporting"), delay=5), settings=settings)
    assert response.status_code == 504
    assert response.json()["error"] == "routing_timeout"


# --------------------------------------------------------------------------- agent errors


@pytest.mark.parametrize(
    ("code", "status", "error"),
    [
        ("unclear_question", 422, "unclear_question"),
        ("invalid_range", 422, "invalid_range"),
        ("rate_limited", 429, "rate_limited"),
        ("daily_quota_exhausted", 503, "daily_quota_exhausted"),
        ("model_unavailable", 503, "model_unavailable"),
        ("tool_error", 502, "agent_task_failed"),
        (None, 502, "agent_task_failed"),
    ],
)
def test_agent_failure_codes_map_to_statuses(monkeypatch, code, status, error):
    failed = Sent(lambda: _task(TaskState.TASK_STATE_FAILED, reason="Agent says why.", code=code))
    response = _ask(monkeypatch, FakeLLM(decision("reporting")), failed)
    assert response.status_code == status
    body = response.json()
    assert body["error"] == error and body["detail"] == "Agent says why."
    assert body["route"]["route"] == "reporting" and body["task_id"] == "task-1"


@pytest.mark.parametrize(
    ("exc", "status", "error"),
    [
        (TimeoutError(), 504, "agent_timeout"),
        (httpx.ConnectError("refused"), 502, "agent_unavailable"),
    ],
)
def test_agent_transport_errors(monkeypatch, exc, status, error):
    def raise_():
        raise exc

    response = _ask(monkeypatch, FakeLLM(decision("reporting")), Sent(raise_))
    assert response.status_code == status and response.json()["error"] == error


# --------------------------------------------------------------------------- answer validation


def test_extract_answer_validates_and_restores_integers():
    text, answer = extract_answer(_completed())
    assert text.startswith("As of 2026-08-30")
    dumped = answer.model_dump(mode="json")
    assert dumped == ANSWER and isinstance(dumped["figures"]["incident_count"], int)


def test_answer_that_breaks_the_contract_is_rejected():
    bad = json.loads(json.dumps(ANSWER))
    bad["figures"]["incident_count"] = 999  # severities no longer sum to it
    with pytest.raises(TaskFailed, match="validation"):
        extract_answer(_task(parts=[new_text_part("x"), new_data_part(bad)]))


def test_answer_whose_figures_cover_another_range_is_rejected():
    bad = json.loads(json.dumps(ANSWER))
    bad["start"] = "2026-06-01"
    with pytest.raises(TaskFailed, match="validation"):
        extract_answer(_task(parts=[new_text_part("x"), new_data_part(bad)]))


def test_failed_task_carries_the_agent_error_code():
    with pytest.raises(TaskFailed) as info:
        extract_answer(_task(TaskState.TASK_STATE_FAILED, reason="nope", code="invalid_range"))
    assert (info.value.error_code, info.value.reason) == ("invalid_range", "nope")


# --------------------------------------------------------------------------- logging


def test_route_decision_is_logged_with_prompt_version(monkeypatch):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter("orchestrator"))
    logger = logging.getLogger("orchestrator")
    was_disabled, logger.disabled = logger.disabled, False
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        body = _ask(monkeypatch, FakeLLM(decision("forecast", reason="future volume"))).json()
    finally:
        logger.removeHandler(handler)
        logger.disabled = was_disabled
    lines = [json.loads(x) for x in stream.getvalue().splitlines()]
    [line] = [x for x in lines if x["msg"] == "route decision"]
    assert line["prompt_version"] == "route_v1" and len(line["prompt_sha"]) == 12
    assert (line["route"], line["reason"]) == ("forecast", "future volume")
    assert line["trace_id"] == body["trace_id"]


# --------------------------------------------------------------------------- A2A timeout


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


def test_timeouts_fit_inside_the_120s_ceiling():
    s = Settings()
    assert s.route_timeout_s + s.a2a_timeout_s < 120  # ADR-034


# --------------------------------------------------------------------------- CLI


def test_cli_prints_answer_route_and_figures(monkeypatch, capsys):
    body = {
        "answer": "As of 2026-08-30: 172 incidents",
        "outcome": "answered",
        "route": {"route": "reporting", "domains": ["reporting"], "reason": "incidents"},
        "prompt_version": "route_v1",
        "reporting": ANSWER,
        "task_id": "t1",
        "trace_id": "tr",
    }
    monkeypatch.setattr(
        cli.httpx, "post", lambda url, json, timeout: httpx.Response(200, json=body)
    )
    assert cli.main(["ask", "How many?", "--url", "http://x"]) == 0
    out = capsys.readouterr().out
    assert "As of 2026-08-30" in out and "route=reporting" in out and "trace_id=tr" in out
    assert '"incident_count": 172' in out


def test_cli_waits_longer_than_the_ceiling():
    assert cli.CLI_TIMEOUT_S > 120  # ADR-034
