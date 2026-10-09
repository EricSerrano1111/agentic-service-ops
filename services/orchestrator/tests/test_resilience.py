"""The request deadline, the circuit breakers, the cost cap and the degraded result at the
orchestrator (ADR-088; FR-13, NFR-1, NFR-4). Offline: fake specialists and a fake router."""

from __future__ import annotations

import contextlib
import io
import json
import logging
import math
import time

import httpx
import pytest
from a2a.client import A2AClientError, A2AClientTimeoutError
from a2a.client.errors import AgentCardResolutionError
from a2a.helpers.proto_helpers import new_data_part, new_text_part
from a2a.types import Artifact, Message, Role, Task, TaskState, TaskStatus
from common import Deadline, JsonFormatter, add_cost
from fastapi.testclient import TestClient
from llm import LLMBreakerOpen, LLMUnavailable
from orchestrator import app as app_mod
from orchestrator.app import AskResponse, create_app, is_dependency_failure
from orchestrator.config import Settings
from orchestrator.degraded import DegradedResult, answer_for, warning_for
from orchestrator.result import extract_cost
from test_orchestrator import ANSWER, QUESTION, FakeLLM, decision

SECRET = (
    "SUPER-SECRET-bearer-abc123 postgresql://user:hunter2@db/x Traceback (most recent call last)"
)


class Clock:
    def __init__(self) -> None:
        self.t = 5000.0

    def __call__(self) -> float:
        return self.t


def task(state=TaskState.TASK_STATE_COMPLETED, cost=None, code=None, reason=None) -> Task:
    metadata = {} if cost is None else {"cost_usd": cost}
    artifacts = []
    status = TaskStatus(state=state)
    if state == TaskState.TASK_STATE_COMPLETED:
        artifacts = [
            Artifact(
                artifact_id="a",
                name="r",
                parts=[new_text_part("As of 2026-08-30: 172 incidents ..."), new_data_part(ANSWER)],
                metadata=metadata or None,
            )
        ]
    else:
        status.message.CopyFrom(
            Message(
                message_id="m",
                role=Role.ROLE_AGENT,
                parts=[new_text_part(reason or "failed")],
                metadata=({"error_code": code} if code else {}) | metadata or None,
            )
        )
    return Task(id="task-1", context_id="ctx", status=status, artifacts=artifacts)


class Hop:
    """Replaces send_question; records each call and answers from `behaviour(call_number)`."""

    def __init__(self, behaviour=None):
        self.calls: list[dict] = []
        self.behaviour = behaviour or (lambda n: task())

    async def __call__(self, agent_url, question, *, trace_id, timeout_s, **kwargs):
        self.calls.append({"url": agent_url, "timeout_s": timeout_s, **kwargs})
        result = self.behaviour(len(self.calls))
        if isinstance(result, BaseException):
            raise result
        return result


class CostLLM(FakeLLM):
    """A router that adds its list-price cost to the request's running total, as LLMClient does."""

    def __init__(self, decision_, cost=0.0006):
        super().__init__(decision_)
        self.cost = cost

    async def generate(self, prompt, **kwargs):
        add_cost(self.cost)
        return await super().generate(prompt, **kwargs)


def client_for(monkeypatch, llm, hop, *, clock=None, deadline=None, settings=None):
    monkeypatch.setattr(app_mod, "send_question", hop)
    if deadline is not None:
        monkeypatch.setattr(
            Deadline, "start", classmethod(lambda cls, now=None, budget_s=120.0: deadline)
        )
    app = create_app(settings or Settings(), llm, breaker_clock=clock or time.monotonic)
    return TestClient(app)


def ask(client, question=QUESTION):
    return client.post("/ask", json={"question": question})


def in_seconds(n: float) -> Deadline:
    return Deadline(int((time.time() + n) * 1000))


@contextlib.contextmanager
def captured_logs():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter("test"))
    root = logging.getLogger()
    orchestrator = logging.getLogger("orchestrator")
    was_disabled = orchestrator.disabled
    orchestrator.disabled = False
    level = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    try:
        yield lambda: [json.loads(line) for line in stream.getvalue().splitlines()]
    finally:
        root.removeHandler(handler)
        root.setLevel(level)
        orchestrator.disabled = was_disabled


# --------------------------------------------------------------------------- the deadline


def test_the_request_deadline_is_120_seconds_and_travels_to_the_agent(monkeypatch):
    hop = Hop()
    before = time.time()
    body = ask(client_for(monkeypatch, FakeLLM(decision("reporting")), hop)).json()
    assert body["outcome"] == "answered"
    [call] = hop.calls
    assert isinstance(call["deadline"], Deadline)
    assert call["deadline"].remaining_s(before) == pytest.approx(120.0, abs=3.0)
    assert call["timeout_s"] == 60.0  # plenty of time: the hop's own cap rules


def test_a_hop_is_clamped_to_the_time_left_minus_the_five_second_reserve(monkeypatch):
    hop = Hop()
    ask(client_for(monkeypatch, FakeLLM(decision("reporting")), hop, deadline=in_seconds(25)))
    [call] = hop.calls
    assert call["timeout_s"] == pytest.approx(20.0, abs=0.5)  # 25 s left, 5 s reserved


def test_no_time_left_before_routing_is_the_degraded_result_with_no_model_call(monkeypatch):
    llm = FakeLLM(decision("reporting"))
    hop = Hop()
    response = ask(client_for(monkeypatch, llm, hop, deadline=in_seconds(4)))
    body = response.json()
    assert response.status_code == 200 and body["outcome"] == "degraded"
    assert body["escalate"] is True and body["unavailable_capability"] is None
    assert "Time limit reached" in body["warning"] and body["route"] == {}
    assert llm.prompts == [] and hop.calls == []


def test_a_hop_cut_short_by_the_deadline_is_the_time_limit_not_a_dependency_failure(monkeypatch):
    hop = Hop(lambda n: TimeoutError())
    body = ask(
        client_for(monkeypatch, FakeLLM(decision("reporting")), hop, deadline=in_seconds(30))
    ).json()
    assert body["outcome"] == "degraded" and "Time limit reached" in body["warning"]
    assert body["unavailable_capability"] is None  # the agent was not blamed


def test_an_agent_that_reports_its_deadline_gone_is_the_time_limit(monkeypatch):
    hop = Hop(lambda n: task(TaskState.TASK_STATE_FAILED, code="deadline_exceeded", reason="x"))
    body = ask(client_for(monkeypatch, FakeLLM(decision("sentiment")), hop)).json()
    assert body["outcome"] == "degraded" and "Time limit reached" in body["warning"]


# --------------------------------------------------------------------------- the breaker


def test_three_failures_open_the_breaker_and_the_fourth_request_fails_fast(monkeypatch):
    hop = Hop(lambda n: httpx.ConnectError("refused"))
    client = client_for(monkeypatch, FakeLLM(decision("forecast")), hop)
    for _ in range(3):
        body = ask(client).json()
        assert body["outcome"] == "degraded" and body["unavailable_capability"] == "forecast"
    assert len(hop.calls) == 3
    again = ask(client).json()
    assert again["outcome"] == "degraded" and again["unavailable_capability"] == "forecast"
    assert "forecast service is temporarily unavailable" in again["warning"]
    assert len(hop.calls) == 3  # failed fast: the dependency was not called


def test_one_domains_open_breaker_leaves_the_others_answering(monkeypatch):
    def behaviour(n):
        return httpx.ConnectError("down")

    hop = Hop(behaviour)
    monkeypatch.setattr(app_mod, "send_question", hop)
    clock = Clock()
    app = create_app(Settings(), FakeLLM(decision("forecast")), breaker_clock=clock)
    client = TestClient(app)
    for _ in range(3):
        ask(client)
    assert ask(client).json()["outcome"] == "degraded"
    # Reporting uses its own breaker, still closed; this specialist answers.
    ok = Hop()
    monkeypatch.setattr(app_mod, "send_question", ok)
    app2 = create_app(Settings(), FakeLLM(decision("reporting")), breaker_clock=clock)
    assert ask(TestClient(app2)).json()["outcome"] == "answered"


def test_one_trial_call_after_the_cooldown_closes_or_reopens_the_breaker(monkeypatch):
    clock = Clock()
    results = {"fail": True}

    def behaviour(n):
        return httpx.ConnectError("down") if results["fail"] else task()

    hop = Hop(behaviour)
    client = client_for(monkeypatch, FakeLLM(decision("reporting")), hop, clock=clock)
    for _ in range(3):
        ask(client)
    assert len(hop.calls) == 3
    clock.t += 29
    ask(client)
    assert len(hop.calls) == 3  # still open
    clock.t += 2  # past 30 s: one trial
    ask(client)
    assert len(hop.calls) == 4  # the trial failed: open for another 30 s
    ask(client)
    assert len(hop.calls) == 4
    clock.t += 31
    results["fail"] = False
    assert ask(client).json()["outcome"] == "answered"  # the trial succeeded: closed
    assert ask(client).json()["outcome"] == "answered" and len(hop.calls) == 6


def test_declines_and_4xx_never_open_the_breaker(monkeypatch):
    request = httpx.Request("POST", "http://agent.test/")
    four_xx = httpx.HTTPStatusError(
        "no", request=request, response=httpx.Response(403, request=request)
    )
    hop = Hop(lambda n: four_xx)
    client = client_for(monkeypatch, FakeLLM(decision("reporting")), hop)
    for _ in range(6):
        assert ask(client).status_code == 502
    assert len(hop.calls) == 6  # every call went through; nothing opened

    declines = Hop(lambda n: task(TaskState.TASK_STATE_FAILED, code="unclear_question", reason="?"))
    client = client_for(monkeypatch, FakeLLM(decision("reporting")), declines)
    for _ in range(6):
        assert ask(client).status_code == 422
    assert len(declines.calls) == 6


def test_the_language_model_breaker_open_is_degraded_naming_the_language_model(monkeypatch):
    hop = Hop()
    llm = FakeLLM(decision("reporting"), error=LLMBreakerOpen("the Gemini circuit breaker is open"))
    body = ask(client_for(monkeypatch, llm, hop)).json()
    assert body["outcome"] == "degraded" and body["unavailable_capability"] == "language model"
    assert "language model service is temporarily unavailable" in body["warning"]
    assert hop.calls == []


def test_an_ordinary_language_model_failure_keeps_its_own_status(monkeypatch):
    llm = FakeLLM(decision("reporting"), error=LLMUnavailable("503 from google"))
    response = ask(client_for(monkeypatch, llm, Hop()))
    assert response.status_code == 503 and response.json()["error"] == "model_unavailable"


@pytest.mark.parametrize(
    ("exc", "counts"),
    [
        (TimeoutError(), True),
        (A2AClientTimeoutError("t"), True),
        (httpx.ReadTimeout("t"), True),
        (httpx.ConnectError("c"), True),
        (httpx.RemoteProtocolError("r"), True),
        (AgentCardResolutionError("card", status_code=503), True),
        (AgentCardResolutionError("card", status_code=403), False),
        (AgentCardResolutionError("card", status_code=404), False),
        (A2AClientError("plain"), False),
        (ValueError("validation"), False),
        (KeyError("k"), False),
    ],
)
def test_which_errors_count_against_a_specialists_breaker(exc, counts):
    assert is_dependency_failure(exc) is counts


def test_a_wrapped_network_error_counts_and_a_wrapped_4xx_does_not():
    request = httpx.Request("GET", "http://agent.test/")
    wrapped = A2AClientError("Network communication error: refused")
    wrapped.__cause__ = httpx.ConnectError("refused")
    assert is_dependency_failure(wrapped)
    four = A2AClientError("HTTP error")
    four.__cause__ = httpx.HTTPStatusError(
        "x", request=request, response=httpx.Response(401, request=request)
    )
    assert not is_dependency_failure(four)
    five = A2AClientError("HTTP error")
    five.__cause__ = httpx.HTTPStatusError(
        "x", request=request, response=httpx.Response(502, request=request)
    )
    assert is_dependency_failure(five)


# --------------------------------------------------------------------------- the cost cap


def test_the_requests_cost_is_the_routing_call_plus_what_the_agent_reports(monkeypatch):
    hop = Hop(lambda n: task(cost=0.0004))
    with captured_logs() as lines:
        body = ask(client_for(monkeypatch, CostLLM(decision("reporting")), hop)).json()
        logged = lines()
    assert body["outcome"] == "answered"
    [done] = [x for x in logged if x["msg"] == "ask answered"]
    assert done["cost_usd"] == pytest.approx(0.0010)  # 0.0006 routing + 0.0004 agent


def test_the_cap_stops_a_request_before_the_next_hop(monkeypatch):
    monkeypatch.setenv("MAX_COST_PER_RUN_USD", "0.0005")
    hop = Hop()
    body = ask(client_for(monkeypatch, CostLLM(decision("reporting")), hop)).json()
    assert body["outcome"] == "degraded" and "Cost limit reached" in body["warning"]
    assert body["escalate"] is True and body["unavailable_capability"] is None
    assert hop.calls == []  # routing alone (0.0006) had reached the cap


def test_a_request_under_the_default_cap_is_not_stopped(monkeypatch):
    monkeypatch.delenv("MAX_COST_PER_RUN_USD", raising=False)
    hop = Hop(lambda n: task(cost=0.003))
    assert (
        ask(client_for(monkeypatch, CostLLM(decision("reporting")), hop)).json()["outcome"]
        == "answered"
    )


def test_the_default_cap_is_two_cents_and_a_blank_value_means_the_default(monkeypatch):
    monkeypatch.setenv("MAX_COST_PER_RUN_USD", "")
    hop = Hop()
    assert (
        ask(client_for(monkeypatch, CostLLM(decision("reporting"), cost=0.019), hop)).json()[
            "outcome"
        ]
        == "answered"
    )
    monkeypatch.setenv("MAX_COST_PER_RUN_USD", "")
    hop2 = Hop()
    stopped = ask(client_for(monkeypatch, CostLLM(decision("reporting"), cost=0.021), hop2)).json()
    assert stopped["outcome"] == "degraded" and hop2.calls == []


@pytest.mark.parametrize("bad", [-1.0, -0.0001, "0.01", True, [0.1], math.inf, -math.inf, math.nan])
def test_a_malformed_or_negative_cost_from_an_agent_is_rejected(monkeypatch, bad):
    """A negative number must not keep a runaway request under the cap."""
    assert extract_cost(task(cost=bad)) is None
    hop = Hop(lambda n: task(cost=bad))
    with captured_logs() as lines:
        client = client_for(monkeypatch, CostLLM(decision("reporting")), hop)
        assert ask(client).json()["outcome"] == "answered"
        [done] = [x for x in lines() if x["msg"] == "ask answered"]
    assert done["cost_usd"] == pytest.approx(0.0006)  # only the routing call counted


def test_extract_cost_reads_artifacts_and_failed_status_messages():
    assert extract_cost(task(cost=0.0004)) == pytest.approx(0.0004)
    failed = task(TaskState.TASK_STATE_FAILED, cost=0.0002, code="not_supported", reason="no")
    assert extract_cost(failed) == pytest.approx(0.0002)
    assert extract_cost(task()) is None


# --------------------------------------------------------------------------- the degraded shape


def test_qa_unavailable_is_degraded_marked_not_verified_with_the_escalation_flag():
    d = DegradedResult("qa_unavailable", "verification (QA)", best_answer="172 incidents in July.")
    text = answer_for(d)
    assert text.startswith(warning_for(d)) and "Not verified: 172 incidents in July." in text
    assert "could not be checked and is not verified" in warning_for(d)


def test_a_degraded_result_without_an_answer_has_only_the_warning():
    d = DegradedResult("deadline")
    assert answer_for(d) == warning_for(d) and "Not verified" not in answer_for(d)


def test_an_answer_that_failed_qa_is_never_shown_as_an_answer():
    d = DegradedResult(
        "qa_failed",
        failed_checks=("figures_mismatch", "bad code!!", "x" * 80, "range_mismatch"),
        best_answer="54 incidents were reported.",
    )
    text = answer_for(d)
    assert "54 incidents" not in text and "Not verified" not in text
    assert "figures_mismatch" in text and "range_mismatch" in text
    assert "bad code" not in text and "xxxx" not in text  # only machine-style codes are echoed


def test_the_response_model_ties_the_degraded_fields_together():
    base = {"route": {}, "prompt_version": "route_v3", "trace_id": "t"}
    ok = AskResponse(
        answer="w",
        outcome="degraded",
        escalate=True,
        warning="w",
        unavailable_capability="forecast",
        **base,
    )
    assert ok.escalate and ok.unavailable_capability == "forecast"
    for bad in (
        {"outcome": "degraded", "escalate": False, "warning": "w"},
        {"outcome": "degraded", "escalate": True, "warning": None},
        {"outcome": "answered", "escalate": True, "warning": "w"},
        {"outcome": "answered", "unavailable_capability": "forecast"},
    ):
        with pytest.raises(ValueError):
            AskResponse(answer="a", **bad, **base)


# --------------------------------------------------------------------------- exposure (L-60)


@pytest.mark.parametrize("trigger", ["dependency", "deadline", "cost"])
def test_no_traceback_token_or_raw_error_text_reaches_the_degraded_response(monkeypatch, trigger):
    if trigger == "dependency":
        hop = Hop(lambda n: httpx.ConnectError(SECRET))
        client = client_for(monkeypatch, FakeLLM(decision("reporting")), hop)
    elif trigger == "deadline":
        hop = Hop(lambda n: TimeoutError(SECRET))
        client = client_for(
            monkeypatch, FakeLLM(decision("reporting")), hop, deadline=in_seconds(30)
        )
    else:
        monkeypatch.setenv("MAX_COST_PER_RUN_USD", "0.0001")
        client = client_for(monkeypatch, CostLLM(decision("reporting")), Hop())
    with captured_logs() as lines:
        response = ask(client)
        logged = json.dumps(lines())
    text = response.text
    assert json.loads(text)["outcome"] == "degraded"
    for forbidden in ("SUPER-SECRET", "bearer", "hunter2", "postgresql://", "Traceback"):
        assert forbidden not in text, forbidden
        assert forbidden not in logged, forbidden  # the log names the error type, not its text
    assert "ConnectError" not in text


def test_the_x_trace_id_header_is_set_on_a_degraded_response(monkeypatch):
    hop = Hop(lambda n: httpx.ConnectError("x"))
    response = ask(client_for(monkeypatch, FakeLLM(decision("reporting")), hop))
    assert response.headers["X-Trace-Id"] == response.json()["trace_id"]


# --------------------------------------------------------------------------- the wire


@pytest.mark.anyio
async def test_the_deadline_goes_to_the_agent_in_the_a2a_message_metadata():
    """Absolute epoch milliseconds, next to the trace id, on the real message the agent gets."""
    from orchestrator.a2a_client import send_question
    from test_orchestrator import AGENT_URL, recording_agent

    inner, _ = recording_agent()
    bodies: list[bytes] = []

    class Tap(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            if request.method == "POST":
                bodies.append(request.content)
            return await inner.handle_async_request(request)

    deadline = in_seconds(90)
    await send_question(
        AGENT_URL,
        "q",
        trace_id="trace-xyz",
        timeout_s=10,
        transport=Tap(),
        deadline=deadline,
    )
    [body] = bodies
    metadata = json.loads(body)["params"]["message"]["metadata"]
    assert metadata["trace_id"] == "trace-xyz"
    assert metadata["deadline_ms"] == deadline.at_ms
    assert abs(metadata["deadline_ms"] / 1000 - (time.time() + 90)) < 5
