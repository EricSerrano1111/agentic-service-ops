"""The orchestrator's verification loop (ADR-089): specialist, then QA, branch by branch.

Offline: fake specialists, a fake QA agent and a fake router. Each test is one branch of the
loop in the order the spec lists them: pass, decline, figures failure, interpretation failure
and re-ask, retries exhausted, QA unavailable, QA's breaker, the deadline and the cost cap
across the loop, sentiment (no check exists yet), and what the logs hold.
"""

from __future__ import annotations

import time

import httpx
import pytest
from a2a.helpers.proto_helpers import new_data_part, new_text_part
from a2a.types import Message, Role, Task, TaskState, TaskStatus
from common import Deadline, DeadlineExceeded
from orchestrator import app as app_mod
from orchestrator.app import AskResponse, create_app
from orchestrator.config import Settings
from test_orchestrator import (
    ANSWER,
    PASS_VERDICT,
    QA_URL,
    QUESTION,
    FakeLLM,
    _forecast_completed,
    decision,
    failing_verdict,
    qa_failed_task,
    verdict_task,
)
from test_resilience import CostLLM, Hop, ask, captured_logs, client_for, in_seconds, task

PARSED = {
    "metric": "unsupported",
    "group_by": None,
    "technician_name": None,
    "region": None,
    "account_name": None,
    "start": "2026-07-01",
    "end": "2026-07-31",
}
NOTE = "The question asks for incident counts by severity, not a rate."


def declined(code: str, reason: str, parsed: dict | None = PARSED) -> Task:
    status = TaskStatus(state=TaskState.TASK_STATE_FAILED)
    metadata = {"error_code": code} | ({} if parsed is None else {"parsed_request": parsed})
    status.message.CopyFrom(
        Message(
            message_id="m",
            role=Role.ROLE_AGENT,
            parts=[new_text_part(reason)],
            metadata=metadata,
        )
    )
    return Task(id="task-1", context_id="ctx", status=status)


def interpretation_fail(guidance: str | None = NOTE) -> dict:
    return failing_verdict("interpretation_matches_question", "interpretation", guidance)


def routed(monkeypatch, route, hop, **kwargs):
    domains = ["reporting", "sentiment"] if route == "multi_domain" else None
    return client_for(monkeypatch, FakeLLM(decision(route, domains)), hop, **kwargs)


def specialist_hop(route, **kwargs):
    """A Hop whose specialist answers with the payload that route's contract expects."""
    answer = _forecast_completed if route == "forecast" else task
    return Hop(lambda n: answer(), **kwargs)


# --------------------------------------------------------------------------- pass


@pytest.mark.parametrize("route", ["reporting", "forecast"])
def test_a_pass_is_returned_as_verified_with_the_specialists_payload(monkeypatch, route):
    hop = specialist_hop(route)
    body = ask(routed(monkeypatch, route, hop)).json()
    assert body["outcome"] == "answered" and body["qa_status"] == "verified"
    assert body["escalate"] is False and body["warning"] is None
    assert len(hop.calls) == 1 and len(hop.qa_calls) == 1
    assert "Not verified" not in body["answer"]


def test_qa_is_sent_the_question_and_the_answer_exactly_as_the_specialist_returned_it(
    monkeypatch,
):
    hop = Hop()
    ask(routed(monkeypatch, "reporting", hop))
    [call] = hop.qa_calls
    sent = call["data"]
    assert sent["domain"] == "reporting" and sent["kind"] == "answer"
    assert sent["question"] == QUESTION and sent["answer"] == ANSWER
    assert sent["text"].startswith("As of 2026-08-30")
    assert "error_code" not in sent and "parsed_request" not in sent
    assert call["deadline"] is not None  # the request's one deadline reaches QA too
    assert call["timeout_s"] == Settings().qa_a2a_timeout_s == 50.0


def test_the_first_specialist_ask_carries_no_reviewer_note(monkeypatch):
    hop = Hop()
    ask(routed(monkeypatch, "reporting", hop))
    assert "metadata" not in hop.calls[0]


# --------------------------------------------------------------------------- declines


def test_a_verified_decline_is_a_normal_not_available_answer(monkeypatch):
    hop = Hop(lambda n: declined("not_supported", "That metric isn't supported yet."))
    body = ask(routed(monkeypatch, "reporting", hop)).json()
    assert body["outcome"] == "not_available" and body["qa_status"] == "verified"
    [call] = hop.qa_calls
    assert call["data"]["kind"] == "decline" and call["data"]["error_code"] == "not_supported"
    assert call["data"]["parsed_request"] == PARSED and "answer" not in call["data"]


def test_a_verified_clarification_keeps_its_reason(monkeypatch):
    hop = Hop(lambda n: declined("technician_ambiguous", "2 technicians match Priya: A and B."))
    body = ask(routed(monkeypatch, "reporting", hop)).json()
    assert body["outcome"] == "needs_clarification" and body["reason"] == "technician_ambiguous"
    assert body["qa_status"] == "verified"


def test_a_decline_that_fails_a_figures_check_is_never_shown(monkeypatch):
    hop = Hop(
        lambda n: declined("technician_not_found", "No technician matches Dave."),
        qa=lambda n: verdict_task(failing_verdict("decline_matches_reason")),
    )
    body = ask(routed(monkeypatch, "reporting", hop)).json()
    assert body["outcome"] == "degraded" and "decline_matches_reason" in body["warning"]
    assert "Dave" not in body["answer"]


def test_other_failures_are_errors_not_verified(monkeypatch):
    hop = Hop(lambda n: task(TaskState.TASK_STATE_FAILED, code="unclear_question", reason="?"))
    response = ask(routed(monkeypatch, "reporting", hop))
    assert response.status_code == 422 and hop.qa_calls == []


# --------------------------------------------------------------------------- figures failure


def test_a_figures_failure_is_degraded_at_once_with_no_second_ask(monkeypatch):
    hop = Hop(qa=lambda n: verdict_task(failing_verdict("figures_match_database")))
    body = ask(routed(monkeypatch, "reporting", hop)).json()
    assert body["outcome"] == "degraded" and body["escalate"] is True
    assert body["qa_status"] == "not_checked" and body["unavailable_capability"] is None
    assert "failed verification (checks: figures_match_database)" in body["warning"]
    assert "172" not in body["answer"]  # the failed answer is not shown
    assert len(hop.calls) == 1 and len(hop.qa_calls) == 1


def test_a_figures_failure_beats_a_simultaneous_interpretation_failure(monkeypatch):
    mixed = {
        "verdict": "fail",
        "checks": [
            {
                "code": "range_matches_request",
                "check_class": "figures",
                "passed": False,
                "detail": "",
            },
            {
                "code": "interpretation_matches_question",
                "check_class": "interpretation",
                "passed": False,
                "detail": "",
            },
        ],
        "guidance": None,
    }
    hop = specialist_hop("forecast", qa=lambda n: verdict_task(mixed))
    body = ask(routed(monkeypatch, "forecast", hop)).json()
    assert body["outcome"] == "degraded" and len(hop.calls) == 1


# --------------------------------------------------------------------------- interpretation


def test_an_interpretation_failure_re_asks_with_the_reviewer_note_then_passes(monkeypatch):
    verdicts = [verdict_task(interpretation_fail()), verdict_task()]
    hop = Hop(qa=lambda n: verdicts[n - 1])
    body = ask(routed(monkeypatch, "reporting", hop)).json()
    assert body["outcome"] == "answered" and body["qa_status"] == "verified"
    assert len(hop.calls) == 2 and len(hop.qa_calls) == 2
    assert "metadata" not in hop.calls[0]
    assert hop.calls[1]["metadata"] == {"qa_guidance": NOTE}


def test_the_reviewer_note_is_capped_before_it_is_sent(monkeypatch):
    # Settings and schema cap it at 300 characters; the orchestrator caps again on its own.
    verdicts = [verdict_task(interpretation_fail("x" * 300)), verdict_task()]
    hop = Hop(qa=lambda n: verdicts[n - 1])
    ask(routed(monkeypatch, "reporting", hop))
    assert len(hop.calls[1]["metadata"]["qa_guidance"]) <= 300


def test_two_re_asks_then_degraded_with_the_failed_answer_hidden(monkeypatch):
    hop = Hop(qa=lambda n: verdict_task(interpretation_fail()))
    body = ask(routed(monkeypatch, "reporting", hop)).json()
    assert body["outcome"] == "degraded" and body["qa_status"] == "not_checked"
    assert "interpretation_matches_question" in body["warning"]
    assert len(hop.calls) == 3 and len(hop.qa_calls) == 3  # one ask and two re-asks
    assert "172" not in body["answer"] and "Not verified" not in body["answer"]


def test_the_retry_count_comes_from_settings(monkeypatch):
    hop = Hop(qa=lambda n: verdict_task(interpretation_fail()))
    client = routed(monkeypatch, "reporting", hop, settings=Settings(max_qa_retry_attempts=0))
    assert ask(client).json()["outcome"] == "degraded"
    assert len(hop.calls) == 1


def test_a_re_ask_that_comes_back_a_decline_is_verified_like_any_other(monkeypatch):
    results = [task(), declined("not_supported", "That metric isn't supported yet.")]
    hop = Hop(
        lambda n: results[n - 1],
        qa=lambda n: verdict_task(interpretation_fail() if n == 1 else None),
    )
    body = ask(routed(monkeypatch, "reporting", hop)).json()
    assert body["outcome"] == "not_available" and body["qa_status"] == "verified"


# --------------------------------------------------------------------------- QA unavailable


@pytest.mark.parametrize(
    "failure",
    [
        httpx.ConnectError("refused"),
        TimeoutError(),
        qa_failed_task("qa_unavailable"),
        qa_failed_task("interpretation_unavailable"),
        qa_failed_task("qa_timeout"),
        qa_failed_task("bad_request"),
        verdict_task({"nonsense": True}),
    ],
)
def test_qa_that_cannot_decide_is_degraded_marked_not_verified(monkeypatch, failure):
    hop = Hop(qa=lambda n: failure)
    body = ask(routed(monkeypatch, "reporting", hop)).json()
    assert body["outcome"] == "degraded" and body["escalate"] is True
    assert body["qa_status"] == "unavailable"
    assert body["unavailable_capability"] == "verification (QA)"
    assert "is not verified" in body["warning"]
    assert "Not verified: As of 2026-08-30: 172 incidents" in body["answer"]  # shown, marked


def test_a_qa_that_is_down_is_never_reported_as_verified(monkeypatch):
    for route in ("reporting", "forecast"):
        hop = specialist_hop(route, qa=lambda n: httpx.ConnectError("refused"))
        body = ask(routed(monkeypatch, route, hop)).json()
        assert body["qa_status"] != "verified"


def test_qa_failures_open_its_own_breaker_and_specialists_keep_answering(monkeypatch):
    clock = type("C", (), {"t": 9000.0, "__call__": lambda self: self.t})()
    hop = Hop(qa=lambda n: httpx.ConnectError("refused"))
    client = routed(monkeypatch, "reporting", hop, clock=clock)
    for _ in range(3):
        assert ask(client).json()["qa_status"] == "unavailable"
    assert len(hop.qa_calls) == 3
    again = ask(client).json()
    assert again["outcome"] == "degraded" and again["qa_status"] == "unavailable"
    assert len(hop.qa_calls) == 3  # failed fast: QA was not called
    assert len(hop.calls) == 4  # the reporting specialist still answered each time
    clock.t += 31  # past the cool-down: one trial, which succeeds
    hop.qa = lambda n: verdict_task()
    assert ask(client).json()["qa_status"] == "verified"


def test_a_task_qa_rejected_does_not_count_against_its_breaker(monkeypatch):
    hop = Hop(qa=lambda n: qa_failed_task("bad_request"))
    client = routed(monkeypatch, "reporting", hop)
    for _ in range(6):
        assert ask(client).json()["qa_status"] == "unavailable"
    assert len(hop.qa_calls) == 6  # nothing opened


def test_qa_reporting_its_deadline_gone_is_the_time_limit(monkeypatch):
    hop = Hop(qa=lambda n: qa_failed_task("deadline_exceeded"))
    body = ask(routed(monkeypatch, "reporting", hop)).json()
    assert body["outcome"] == "degraded" and "Time limit reached" in body["warning"]


# --------------------------------------------------------------------------- deadline and cost


def test_the_qa_hop_is_clamped_to_the_time_left_minus_the_reserve(monkeypatch):
    hop = Hop()
    ask(routed(monkeypatch, "reporting", hop, deadline=in_seconds(25)))
    [call] = hop.qa_calls
    assert call["timeout_s"] == pytest.approx(20.0, abs=0.5)


class RunsOutAfter(Deadline):
    """A deadline with time for `hops` hops and none after: the next `hop_timeout` raises."""

    hops_left = 0

    def hop_timeout(self, cap_s, now=None, reserve_s=5.0):
        if type(self).hops_left <= 0:
            raise DeadlineExceeded("no time left")
        type(self).hops_left -= 1
        return min(30.0, cap_s)


def test_a_deadline_that_runs_out_before_qa_shows_the_unverified_answer(monkeypatch):
    RunsOutAfter.hops_left = 2  # routing and the specialist; none left for QA
    hop = Hop()
    deadline = RunsOutAfter(int((time.time() + 60) * 1000))
    body = ask(routed(monkeypatch, "reporting", hop, deadline=deadline)).json()
    assert body["outcome"] == "degraded" and "Time limit reached" in body["warning"]
    assert hop.qa_calls == [] and len(hop.calls) == 1
    assert body["qa_status"] == "not_checked"
    assert "Not verified: As of 2026-08-30" in body["answer"]  # the specialist's, marked


def test_a_deadline_that_runs_out_between_asks_hides_the_failed_answer(monkeypatch):
    RunsOutAfter.hops_left = 3  # routing, specialist, QA (fails interpretation); none for a re-ask
    hop = Hop(qa=lambda n: verdict_task(interpretation_fail()))
    deadline = RunsOutAfter(int((time.time() + 60) * 1000))
    body = ask(routed(monkeypatch, "reporting", hop, deadline=deadline)).json()
    assert body["outcome"] == "degraded" and "Time limit reached" in body["warning"]
    assert len(hop.calls) == 1 and len(hop.qa_calls) == 1
    assert "172" not in body["answer"] and "Not verified" not in body["answer"]


def test_the_cap_stops_the_loop_before_the_qa_hop_and_shows_the_unverified_answer(monkeypatch):
    monkeypatch.setenv("MAX_COST_PER_RUN_USD", "0.01")
    hop = Hop(lambda n: task(cost=0.0095), qa=lambda n: verdict_task())
    body = ask(client_for(monkeypatch, CostLLM(decision("reporting")), hop)).json()
    assert body["outcome"] == "degraded" and "Cost limit reached" in body["warning"]
    assert hop.qa_calls == []
    assert body["qa_status"] == "not_checked"
    assert "Not verified: As of 2026-08-30" in body["answer"]


def test_the_cap_counts_qas_cost_and_stops_a_re_ask(monkeypatch):
    monkeypatch.setenv("MAX_COST_PER_RUN_USD", "0.01")
    hop = Hop(
        lambda n: task(cost=0.004),
        qa=lambda n: verdict_task(interpretation_fail(), cost=0.0065),
    )
    body = ask(client_for(monkeypatch, CostLLM(decision("reporting"), cost=0.0), hop)).json()
    assert body["outcome"] == "degraded" and "Cost limit reached" in body["warning"]
    assert len(hop.calls) == 1 and len(hop.qa_calls) == 1  # the re-ask was never made
    assert "172" not in body["answer"]  # the failed answer stays hidden


# --------------------------------------------------------------------------- not verified yet


def test_sentiment_is_not_checked_and_says_so(monkeypatch):
    from test_orchestrator import SENTIMENT_ANSWER, _task

    sentiment = _task(
        parts=[new_text_part("Customer feedback sentiment ..."), new_data_part(SENTIMENT_ANSWER)]
    )
    hop = Hop(lambda n: sentiment)
    body = ask(routed(monkeypatch, "sentiment", hop)).json()
    assert body["outcome"] == "answered" and body["qa_status"] == "not_checked"
    assert body["answer"].rstrip().endswith("not yet checked by the verification agent.")
    assert "Not verified:" in body["answer"]
    assert hop.qa_calls == []


@pytest.mark.parametrize("route", ["out_of_scope", "multi_domain", "ambiguous"])
def test_a_routing_answer_has_nothing_to_verify(monkeypatch, route):
    hop = Hop()
    body = ask(routed(monkeypatch, route, hop)).json()
    assert body["qa_status"] == "not_applicable" and hop.qa_calls == [] and hop.calls == []


def test_the_response_model_ties_qa_status_to_the_outcome():
    base = {"route": {}, "prompt_version": "route_v3", "trace_id": "t", "answer": "a"}
    AskResponse(outcome="answered", qa_status="verified", **base)
    with pytest.raises(ValueError):
        AskResponse(outcome="declined", qa_status="verified", **base)
    with pytest.raises(ValueError):
        AskResponse(outcome="answered", qa_status="unavailable", **base)
    AskResponse(outcome="degraded", escalate=True, warning="w", qa_status="unavailable", **base)
    with pytest.raises(ValueError):
        AskResponse(outcome="degraded", escalate=True, warning="w", qa_status="verified", **base)


# --------------------------------------------------------------------------- logs


def test_loop_decisions_are_logged_without_the_note_or_the_question(monkeypatch):
    secret_question = "How many incidents CANARYQUESTION happened last month?"
    verdicts = [verdict_task(interpretation_fail("CANARYNOTE says reread")), verdict_task()]
    hop = Hop(qa=lambda n: verdicts[n - 1])
    with captured_logs() as lines:
        ask(routed(monkeypatch, "reporting", hop), secret_question)
        logged = lines()
    text = " ".join(str(x) for x in logged)
    assert "CANARYQUESTION" not in text and "CANARYNOTE" not in text
    verdict_lines = [x for x in logged if x["msg"] == "qa verdict"]
    assert [v["verdict"] for v in verdict_lines] == ["fail", "pass"]
    assert verdict_lines[0]["failed_checks"] == ["interpretation_matches_question"]
    assert [v["attempt"] for v in verdict_lines] == [1, 2]
    assert [x["retry"] for x in logged if x["msg"] == "qa retry"] == [1]


def test_the_pass_verdict_constant_is_a_valid_verdict():
    from schemas import Verdict

    assert Verdict.model_validate(PASS_VERDICT).verdict == "pass"
    assert Settings().agent_qa_url == QA_URL


def test_settings_read_the_qa_url_and_retry_count_from_the_environment(monkeypatch):
    monkeypatch.setenv("AGENT_QA_URL", "http://qa.example:9")
    monkeypatch.setenv("MAX_QA_RETRY_ATTEMPTS", "1")
    s = Settings.from_env()
    assert s.agent_qa_url == "http://qa.example:9" and s.max_qa_retry_attempts == 1
    monkeypatch.setenv("MAX_QA_RETRY_ATTEMPTS", "")
    assert Settings.from_env().max_qa_retry_attempts == 2
    for bad in ("x", "-1", "6"):
        monkeypatch.setenv("MAX_QA_RETRY_ATTEMPTS", bad)
        with pytest.raises(ValueError, match="MAX_QA_RETRY_ATTEMPTS"):
            Settings.from_env()


def test_create_app_builds_without_a_network():
    assert create_app(Settings(), FakeLLM(decision("reporting"))) is not None
    assert app_mod.QA_OUTAGE_CODES == (
        "qa_unavailable",
        "interpretation_unavailable",
        "qa_timeout",
    )


def test_an_advisory_interpretation_failure_is_logged_and_neither_fails_nor_retries(monkeypatch):
    advisory = PASS_VERDICT | {
        "advisories": [
            {
                "code": "interpretation_matches_question",
                "check_class": "interpretation",
                "passed": False,
                "detail": "advisory: differs in dates",
            }
        ]
    }
    hop = Hop(qa=lambda n: verdict_task(advisory))
    with captured_logs() as lines:
        body = ask(routed(monkeypatch, "reporting", hop)).json()
        logged = lines()
    assert body["outcome"] == "answered" and body["qa_status"] == "verified"
    assert len(hop.calls) == 1 and len(hop.qa_calls) == 1  # no re-ask
    [seen] = [x for x in logged if x["msg"] == "qa verdict"]
    assert seen["verdict"] == "pass" and seen["advisory_failed"] == [
        "interpretation_matches_question"
    ]
    assert not [x for x in logged if x["msg"] == "qa retry"]
