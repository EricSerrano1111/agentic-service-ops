"""The answer journey (data dictionary section 6 rule 10; ADR-117 item 5).

Offline: fake specialists, a fake QA agent and a fake router, as in the QA-loop tests. The journey
is read-only telemetry, so these tests check its shape for every outcome and degraded trigger,
that its totals equal what the orchestrator logs, that nothing sensitive reaches it, and that a
service's unreadable metadata means no sub-steps and never an error.
"""

from __future__ import annotations

import json
import math

import httpx
import pytest
from a2a.types import TaskState
from llm import LLMUnavailable
from orchestrator.journey import extract_telemetry
from orchestrator.result import extract_cost
from pydantic import ValidationError
from schemas import Hop, Journey, QaSummary, Verdict, interpretation_of, qa_summary
from test_orchestrator import (
    FakeLLM,
    decision,
    failing_verdict,
    qa_failed_task,
    verdict_task,
)
from test_qa_loop import declined, interpretation_fail, routed, specialist_hop
from test_resilience import (
    CostLLM,
    ask,
    captured_logs,
    client_for,
    in_seconds,
    task,
)
from test_resilience import (
    Hop as FakeHop,
)

PARSE = {"step": "parse", "start_ms": 1.5, "duration_ms": 300.0, "status": "ok"}
TOOL = {"step": "tool", "start_ms": 302.0, "duration_ms": 40.0, "status": "ok"}
FIGURES = {"step": "figures_check", "start_ms": 0.5, "duration_ms": 20.0, "status": "ok"}
INTERP = {"step": "interpretation_check", "start_ms": 21.0, "duration_ms": 400.0, "status": "ok"}


def reporting_task(steps=(PARSE, TOOL), calls=1, cost=0.0004):
    t = task(cost=cost)
    t.artifacts[0].metadata.update({"model_calls": calls, "steps": list(steps)})
    return t


def qa_task(verdict=None, steps=(FIGURES, INTERP), calls=1, cost=0.0002, **extra):
    t = verdict_task(verdict, cost=cost)
    t.artifacts[0].metadata.update({"model_calls": calls, "steps": list(steps), **extra})
    return t


def journey_of(body) -> Journey:
    assert body["journey"] is not None
    return Journey.model_validate(body["journey"])


def pairs(journey: Journey):
    return [(h.service, h.step, h.attempt, h.status) for h in journey.hops]


def check_shape(journey: Journey) -> None:
    starts = [h.start_ms for h in journey.hops]
    assert starts == sorted(starts)  # in order
    assert all(h.start_ms >= 0 and h.duration_ms >= 0 for h in journey.hops)


def logged_totals(lines, msg):
    [line] = [x for x in lines if x["msg"] == msg]
    return line["model_calls"], line["cost_usd"]


# --------------------------------------------------------------------------- every outcome


def test_an_answer_has_route_parse_tool_and_the_qa_steps_in_order(monkeypatch):
    hop = FakeHop(lambda n: reporting_task(), qa=lambda n: qa_task())
    with captured_logs() as lines:
        body = ask(client_for(monkeypatch, CostLLM(decision("reporting")), hop)).json()
        logged = lines()
    assert body["outcome"] == "answered"
    journey = journey_of(body)
    check_shape(journey)
    assert pairs(journey) == [
        ("orchestrator", "route", 1, "ok"),
        ("reporting", "parse", 1, "ok"),
        ("reporting", "tool", 1, "ok"),
        ("qa", "figures_check", 1, "ok"),
        ("qa", "interpretation_check", 1, "ok"),
    ]
    # routing 1 + specialist 1 + QA 1; cost 0.0006 + 0.0004 + 0.0002
    assert journey.model_calls == 3
    assert journey.cost_usd == pytest.approx(0.0012)
    assert (journey.model_calls, journey.cost_usd) == pytest.approx(
        logged_totals(logged, "ask answered")
    )


def test_the_specialists_steps_start_inside_the_call_and_after_routing(monkeypatch):
    body = ask(
        client_for(
            monkeypatch,
            FakeLLM(decision("reporting")),
            FakeHop(lambda n: reporting_task(), qa=lambda n: qa_task()),
        )
    ).json()
    journey = journey_of(body)
    route, parse, tool, figures, _ = journey.hops
    assert parse.start_ms >= route.start_ms + route.duration_ms - 0.2
    # A fake call takes milliseconds, so the reported offsets are clamped inside its wall time.
    assert tool.start_ms >= parse.start_ms
    assert figures.start_ms >= tool.start_ms


@pytest.mark.parametrize("route", ["reporting", "forecast"])
def test_the_qa_summary_matches_the_verdict(monkeypatch, route):
    hop = specialist_hop(route)
    hop.qa = lambda n: qa_task()
    body = ask(routed(monkeypatch, route, hop)).json()
    qa = journey_of(body).qa
    assert qa is not None and qa.verdict == "pass"
    assert [(c.code, c.check_class, c.passed) for c in qa.checks] == [
        ("figures_match_database", "figures", True),
        ("interpretation_matches_question", "interpretation", True),
    ]
    assert qa.interpretation == "faithful" and qa.mode == "enforce"  # derived: a checked class


def test_qa_reports_its_mode_and_an_advisory_result_is_listed(monkeypatch):
    advisory = {
        "verdict": "pass",
        "checks": [
            {"code": "figures_match_database", "check_class": "figures", "passed": True},
        ],
        "advisories": [
            {
                "code": "interpretation_matches_question",
                "check_class": "interpretation",
                "passed": False,
                "detail": "advisory: differs in period",
            }
        ],
    }
    hop = FakeHop(
        qa=lambda n: qa_task(advisory, qa_interpretation="not_faithful", qa_mode="advisory")
    )
    body = ask(routed(monkeypatch, "reporting", hop)).json()
    assert body["qa_status"] == "verified"  # an advisory failure changes nothing
    qa = journey_of(body).qa
    assert qa.mode == "advisory" and qa.interpretation == "not_faithful" and qa.verdict == "pass"
    assert [c.passed for c in qa.checks] == [True, False]
    assert "differs" not in json.dumps(body["journey"])  # QA's detail text is not included


def test_a_figures_failure_shows_the_check_that_failed_and_no_interpretation(monkeypatch):
    hop = FakeHop(qa=lambda n: qa_task(failing_verdict("figures_match_database"), steps=(FIGURES,)))
    body = ask(routed(monkeypatch, "reporting", hop)).json()
    assert body["outcome"] == "degraded"
    journey = journey_of(body)
    assert journey.qa.verdict == "fail" and journey.qa.interpretation == "not_run"
    assert [c.passed for c in journey.qa.checks] == [False]
    assert pairs(journey)[-1] == ("qa", "figures_check", 1, "ok")


def test_a_decline_shows_the_specialist_step_that_ran(monkeypatch):
    t = declined("not_supported", "Not supported.")
    t.status.message.metadata.update({"model_calls": 1, "steps": [PARSE]})
    body = ask(routed(monkeypatch, "reporting", FakeHop(lambda n: t))).json()
    assert body["outcome"] == "not_available"
    journey = journey_of(body)
    assert pairs(journey)[:2] == [
        ("orchestrator", "route", 1, "ok"),
        ("reporting", "parse", 1, "ok"),
    ]
    assert journey.qa is not None


def test_a_clarification_from_a_specialist_has_its_parse_and_tool_steps(monkeypatch):
    t = declined("technician_ambiguous", "2 technicians match.")
    t.status.message.metadata.update({"steps": [PARSE, TOOL]})
    body = ask(routed(monkeypatch, "reporting", FakeHop(lambda n: t))).json()
    assert body["outcome"] == "needs_clarification"
    assert [h.step for h in journey_of(body).hops] == ["route", "parse", "tool", "figures_check"]


@pytest.mark.parametrize(
    ("route", "outcome"),
    [
        ("ambiguous", "needs_clarification"),
        ("out_of_scope", "declined"),
        ("multi_domain", "split_required"),
    ],
)
def test_a_routing_only_outcome_has_the_route_hop_and_nothing_else(monkeypatch, route, outcome):
    hop = FakeHop()
    with captured_logs() as lines:
        body = ask(routed(monkeypatch, route, hop)).json()
        logged = lines()
    assert body["outcome"] == outcome and hop.calls == []
    journey = journey_of(body)
    assert pairs(journey) == [("orchestrator", "route", 1, "ok")]
    assert journey.qa is None and journey.model_calls == 0
    assert (journey.model_calls, journey.cost_usd) == pytest.approx(
        logged_totals(logged, "ask answered")
    )


# --------------------------------------------------------------------------- degraded triggers


def degraded_journey(monkeypatch, llm, hop, **kwargs):
    with captured_logs() as lines:
        body = ask(client_for(monkeypatch, llm, hop, **kwargs)).json()
        logged = lines()
    assert body["outcome"] == "degraded"
    journey = journey_of(body)
    check_shape(journey)
    assert (journey.model_calls, journey.cost_usd) == pytest.approx(
        logged_totals(logged, "ask degraded")
    )
    return journey


def test_degraded_when_no_time_is_left_before_routing(monkeypatch):
    journey = degraded_journey(
        monkeypatch, FakeLLM(decision("reporting")), FakeHop(), deadline=in_seconds(-1)
    )
    assert pairs(journey) == [("orchestrator", "route", 1, "skipped")]


def test_degraded_when_routing_fails_shows_the_failed_route_hop(monkeypatch):
    llm = FakeLLM(decision("reporting"), error=LLMUnavailable("down"))
    journey = degraded_journey(monkeypatch, llm, FakeHop())
    assert pairs(journey) == [("orchestrator", "route", 1, "failed")]


def test_degraded_when_the_cost_cap_stops_the_specialist(monkeypatch):
    monkeypatch.setenv("MAX_COST_PER_RUN_USD", "0.0005")
    journey = degraded_journey(monkeypatch, CostLLM(decision("reporting")), FakeHop())
    assert pairs(journey) == [
        ("orchestrator", "route", 1, "ok"),
        ("reporting", "parse", 1, "skipped"),
    ]
    assert journey.model_calls == 1


def test_degraded_when_the_specialist_is_down_shows_it_failed(monkeypatch):
    hop = FakeHop(lambda n: httpx.ConnectError("SUPER-SECRET connect"))
    journey = degraded_journey(monkeypatch, FakeLLM(decision("reporting")), hop)
    assert pairs(journey)[-1] == ("reporting", "parse", 1, "failed")


def test_degraded_when_the_specialist_times_out_shows_timeout(monkeypatch):
    hop = FakeHop(lambda n: httpx.ReadTimeout("slow"))
    journey = degraded_journey(monkeypatch, FakeLLM(decision("reporting")), hop)
    assert pairs(journey)[-1] == ("reporting", "parse", 1, "timeout")


def test_degraded_when_the_breaker_is_open_shows_the_hop_skipped(monkeypatch):
    hop = FakeHop(lambda n: httpx.ConnectError("x"))
    client = client_for(monkeypatch, FakeLLM(decision("reporting")), hop)
    for _ in range(3):
        assert ask(client).json()["outcome"] == "degraded"
    body = ask(client).json()
    journey = journey_of(body)
    assert pairs(journey)[-1] == ("reporting", "parse", 1, "skipped")
    assert len(hop.calls) == 3  # the fourth never reached the specialist


def test_degraded_when_qa_is_unavailable_shows_the_qa_hop_failed_and_no_summary(monkeypatch):
    hop = FakeHop(lambda n: reporting_task(), qa=lambda n: qa_failed_task("qa_unavailable"))
    journey = degraded_journey(monkeypatch, FakeLLM(decision("reporting")), hop)
    assert pairs(journey)[-1] == ("qa", "figures_check", 1, "failed")
    assert journey.qa is None


def test_degraded_when_qa_times_out_shows_the_qa_hop_timeout(monkeypatch):
    hop = FakeHop(lambda n: reporting_task(), qa=lambda n: qa_failed_task("qa_timeout"))
    journey = degraded_journey(monkeypatch, FakeLLM(decision("reporting")), hop)
    assert pairs(journey)[-1] == ("qa", "figures_check", 1, "timeout")


# --------------------------------------------------------------------------- the revision loop


def test_every_revision_attempt_is_numbered_and_present(monkeypatch):
    verdicts = [qa_task(interpretation_fail()), qa_task(interpretation_fail()), qa_task()]
    hop = FakeHop(lambda n: reporting_task(), qa=lambda n: verdicts[n - 1])
    body = ask(routed(monkeypatch, "reporting", hop)).json()
    assert body["outcome"] == "answered" and len(hop.calls) == 3
    journey = journey_of(body)
    check_shape(journey)
    assert pairs(journey) == [
        ("orchestrator", "route", 1, "ok"),
        *[
            (service, step, attempt, "ok")
            for attempt in (1, 2, 3)
            for service, step in (
                ("reporting", "parse"),
                ("reporting", "tool"),
                ("qa", "figures_check"),
                ("qa", "interpretation_check"),
            )
        ],
    ]
    assert journey.model_calls == 6  # a parse and a QA call, three times


def test_retries_exhausted_keeps_every_attempt_in_the_degraded_journey(monkeypatch):
    hop = FakeHop(lambda n: reporting_task(), qa=lambda n: qa_task(interpretation_fail()))
    journey = degraded_journey(monkeypatch, FakeLLM(decision("reporting")), hop)
    assert sorted({h.attempt for h in journey.hops}) == [1, 2, 3]
    assert journey.qa.verdict == "fail" and journey.qa.interpretation in (
        "faithful",
        "not_faithful",
    )


# --------------------------------------------------------------------------- nothing leaks

MARKERS = {
    "question": "QMARK-7f3a-what-is-this",
    "technician": "TECHMARK-Zebulon-Q",
    "reason": "REASONMARK-router-thoughts",
    "detail": "DETAILMARK-qa-detail",
    "error": "ERRMARK-tool-error-text",
    "model": "MODELMARK-model-output",
}


def test_no_marker_reaches_the_journey(monkeypatch):
    m = MARKERS
    llm = CostLLM(decision("reporting", reason=m["reason"]))
    answer = reporting_task()
    # A specialist cannot smuggle text in: unknown keys, steps and values are ignored.
    answer.artifacts[0].metadata.update(
        {
            "note": m["model"],
            "steps": [PARSE, {**TOOL, "step": m["error"]}, {**TOOL, "status": m["error"]}],
        }
    )
    verdict = {
        "verdict": "pass",
        "checks": [
            {
                "code": "figures_match_database",
                "check_class": "figures",
                "passed": True,
                "detail": m["detail"],
            }
        ],
        "advisories": [
            {
                "code": "interpretation_matches_question",
                "check_class": "interpretation",
                "passed": False,
                "detail": f"advisory: differs in {m['detail']}",
            }
        ],
    }
    hop = FakeHop(lambda n: answer, qa=lambda n: qa_task(verdict, qa_mode="advisory"))
    client = client_for(monkeypatch, llm, hop)
    body = ask(client, m["question"] + " " + m["technician"]).json()
    assert body["outcome"] == "answered"
    text = json.dumps(body["journey"])
    for name, marker in m.items():
        assert marker not in text, name
    for forbidden in ("172", "As of", "task-1", "http://", "ctx"):  # figures, answer text, ids
        assert forbidden not in text, forbidden


def test_a_failing_tool_error_text_does_not_reach_the_degraded_journey(monkeypatch):
    hop = FakeHop(
        lambda n: task(TaskState.TASK_STATE_FAILED, code="tool_error", reason=MARKERS["error"])
    )
    response = ask(client_for(monkeypatch, FakeLLM(decision("reporting")), hop))
    assert MARKERS["error"] not in json.dumps(response.json().get("journey"))


def test_the_journey_has_only_fixed_keys(monkeypatch):
    hop = FakeHop(lambda n: reporting_task(), qa=lambda n: qa_task())
    body = ask(routed(monkeypatch, "reporting", hop)).json()
    j = body["journey"]
    assert set(j) == {"hops", "qa", "model_calls", "cost_usd"}
    assert all(
        set(h) == {"service", "step", "attempt", "start_ms", "duration_ms", "status"}
        for h in j["hops"]
    )
    assert set(j["qa"]) == {"verdict", "checks", "interpretation", "mode"}
    assert all(set(c) == {"code", "class", "passed"} for c in j["qa"]["checks"])


# --------------------------------------------------------------------------- no answer changes


def test_the_response_without_the_journey_is_the_same_as_before(monkeypatch):
    hop = FakeHop(lambda n: reporting_task(), qa=lambda n: qa_task())
    with_telemetry = ask(routed(monkeypatch, "reporting", hop)).json()
    bare = FakeHop(lambda n: task(cost=0.0004), qa=lambda n: verdict_task(cost=0.0002))
    without = ask(routed(monkeypatch, "reporting", bare)).json()
    for body in (with_telemetry, without):
        body.pop("trace_id")
    assert without["journey"]["hops"][1:3] != []  # the fallback hops exist
    with_telemetry.pop("journey")
    without.pop("journey")
    assert with_telemetry == without


# --------------------------------------------------------------------------- metadata robustness

BAD_STEPS = [
    "not a list",
    [None, 3, "x", [1]],
    [{"step": "parse"}],
    [{**PARSE, "start_ms": -1}],
    [{**PARSE, "duration_ms": -0.5}],
    [{**PARSE, "start_ms": True}],
    [{**PARSE, "duration_ms": "300"}],
    [{**PARSE, "duration_ms": 1e12}],
    [{**PARSE, "step": "figures_check"}],  # QA's step from a specialist
    [{**PARSE, "step": "route"}],
    [{**PARSE, "status": "skipped"}],
    [{**PARSE, "status": "not_called"}],
    [{**PARSE, "status": None}],
]


@pytest.mark.parametrize("steps", BAD_STEPS)
def test_unusable_steps_give_no_sub_steps_never_an_error(monkeypatch, steps):
    t = task(cost=0.0004)
    t.artifacts[0].metadata.update({"steps": steps})
    assert extract_telemetry(t, "reporting").steps == []
    hop = FakeHop(lambda n: t)
    body = ask(routed(monkeypatch, "reporting", hop)).json()
    assert body["outcome"] == "answered"
    # The call still shows, as one hop carrying its whole wall time.
    assert [h["step"] for h in body["journey"]["hops"][:2]] == ["route", "parse"]


@pytest.mark.parametrize("calls", [None, True, False, -1, 1.5, "2", [2], {"n": 2}, 10**9, 1e30])
def test_unusable_model_calls_count_as_zero(calls):
    t = task(cost=0.0004)
    t.artifacts[0].metadata.update({"model_calls": calls} if calls is not None else {})
    assert extract_telemetry(t, "reporting").calls == 0


def test_a_whole_number_of_calls_arrives_as_a_float_and_is_read():
    t = task()
    t.artifacts[0].metadata.update({"model_calls": 2.0})
    assert extract_telemetry(t, "reporting").calls == 2


def test_infinite_values_make_the_metadata_unreadable_not_an_error():
    t = task(cost=0.0004)
    t.artifacts[0].metadata.update(
        {"model_calls": math.inf, "steps": [{**PARSE, "duration_ms": math.inf}]}
    )
    telemetry = extract_telemetry(t, "reporting")
    assert telemetry.steps == [] and telemetry.calls == 0
    assert extract_cost(t) is None  # the existing ADR-088 hardening, unchanged


def test_missing_metadata_means_no_telemetry():
    t = task()
    t.artifacts[0].ClearField("metadata")
    telemetry = extract_telemetry(t, "qa")
    assert telemetry.steps == [] and telemetry.calls == 0 and telemetry.interpretation is None
    assert extract_telemetry(None, "qa").steps == []


def test_a_service_may_report_at_most_eight_steps():
    t = task()
    t.artifacts[0].metadata.update({"steps": [PARSE] * 30})
    assert len(extract_telemetry(t, "reporting").steps) == 8


def test_a_step_longer_than_its_call_is_clamped_inside_it(monkeypatch):
    t = reporting_task(steps=({**PARSE, "start_ms": 5.0, "duration_ms": 500_000.0},))
    body = ask(routed(monkeypatch, "reporting", FakeHop(lambda n: t))).json()
    journey = journey_of(body)
    call = journey.hops[1]
    assert call.duration_ms < 5_000  # the whole fake call took milliseconds, not 500 s


# --------------------------------------------------------------------------- the schema


def hop_fields(**more):
    return {
        "service": "qa",
        "step": "figures_check",
        "attempt": 1,
        "start_ms": 1.0,
        "duration_ms": 2.0,
        "status": "ok",
    } | more


@pytest.mark.parametrize(
    "bad",
    [
        {"service": "browser"},
        {"step": "think"},
        {"status": "great"},
        {"attempt": 0},
        {"start_ms": -1},
        {"duration_ms": -0.1},
        {"duration_ms": float("inf")},
        {"duration_ms": float("nan")},
        {"extra": "field"},
    ],
)
def test_a_hop_rejects_unknown_values_and_extra_fields(bad):
    Hop.model_validate(hop_fields())
    with pytest.raises(ValidationError):
        Hop.model_validate(hop_fields(**bad))


def test_every_documented_service_step_and_status_is_accepted():
    for service in ("gateway", "orchestrator", "reporting", "sentiment", "forecast", "qa"):
        Hop.model_validate(hop_fields(service=service))
    for step in ("route", "parse", "tool", "figures_check", "interpretation_check", "forward"):
        Hop.model_validate(hop_fields(step=step))
    for status in ("ok", "failed", "timeout", "skipped", "not_called"):
        Hop.model_validate(hop_fields(status=status))


def test_journey_and_qa_summary_reject_extra_fields():
    with pytest.raises(ValidationError):
        Journey.model_validate({"hops": [], "model_calls": 0, "cost_usd": 0, "note": "x"})
    with pytest.raises(ValidationError):
        QaSummary.model_validate(
            {
                "verdict": "pass",
                "checks": [],
                "interpretation": "faithful",
                "mode": "advisory",
                "x": 1,
            }
        )
    with pytest.raises(ValidationError):
        QaSummary.model_validate(
            {"verdict": "pass", "checks": [], "interpretation": "maybe", "mode": "advisory"}
        )


def test_qa_summary_lists_codes_classes_and_results_only():
    verdict = Verdict.model_validate(
        {
            "verdict": "fail",
            "checks": [
                {
                    "code": "a_check",
                    "check_class": "figures",
                    "passed": False,
                    "detail": "DETAILMARK",
                }
            ],
        }
    )
    summary = qa_summary(verdict, interpretation_of(verdict, "advisory"), "advisory")
    dumped = summary.model_dump(by_alias=True)
    assert dumped["checks"] == [{"code": "a_check", "class": "figures", "passed": False}]
    assert dumped["interpretation"] == "not_run"
    assert "DETAILMARK" not in json.dumps(dumped)
