"""The "Interpreted as:" line, the qa_status words and the response mapping (data dictionary §6,
"Answer display (UI)")."""

from __future__ import annotations

import httpx
import pytest
from api_gateway.interpret import answer_without_warning, interpreted_as, qa_text
from gateway_testkit import Kit, answered


@pytest.fixture
def kit(tmp_path) -> Kit:
    return Kit(tmp_path)


def reporting(**request) -> dict:
    body = answered()
    body["reporting"]["request"] |= request
    return body


def test_a_reporting_answer_shows_measure_resolved_dates_and_region():
    assert interpreted_as(answered()) == ("SLA compliance · 2026-08-01 to 2026-08-30 · Northeast")


def test_resolved_dates_come_from_the_answer_not_the_requests_null_dates():
    body = answered()
    assert body["reporting"]["request"]["start"] is None
    assert "2026-08-01 to 2026-08-30" in interpreted_as(body)


def test_an_assumed_range_says_so():
    body = answered()
    body["reporting"]["range_assumed"] = True
    assert interpreted_as(body).endswith("(assumed: the question named no dates) · Northeast")


def test_no_region_is_all_regions_and_other_fields_appear_only_when_present():
    line = interpreted_as(reporting(region=None, group_by="service_type", account_name="Acme"))
    assert line == (
        "SLA compliance · 2026-08-01 to 2026-08-30 · all regions · account: Acme · by service type"
    )
    assert "technician" not in line


def test_a_technician_is_shown_as_typed():
    assert "technician: Priya N." in interpreted_as(reporting(technician_name="Priya N."))


def test_a_decline_with_an_unsupported_region_says_region_not_recognised():
    body = {
        "answer": "I can only restrict a question to one of four regions.",
        "outcome": "not_available",
        "route": {"route": "reporting"},
        "reporting": None,
        "parsed_request": {
            "metric": "sla_compliance",
            "region": "unsupported",
            "start": "2026-08-01",
            "end": "2026-08-31",
        },
    }
    assert interpreted_as(body) == (
        "SLA compliance · 2026-08-01 to 2026-08-31 · region not recognised"
    )


def test_a_sentiment_answer():
    body = {
        "route": {"route": "sentiment"},
        "sentiment": {
            "request": {
                "region": None,
                "bucket": "month",
                "want_trend": True,
                "want_examples": False,
                "unsupported": None,
            },
            "start": "2026-05-01",
            "end": "2026-07-31",
            "range_assumed": False,
        },
    }
    assert interpreted_as(body) == (
        "customer sentiment trend · 2026-05-01 to 2026-07-31 · all regions · by month"
    )


def test_a_forecast_answer_shows_the_resolved_weeks_and_the_horizon():
    body = {
        "route": {"route": "forecast"},
        "forecast": {
            "request": {"slice": "total", "horizon_weeks": 8, "want_history": False},
            "requested_first_week": "2026-08-31",
            "requested_last_week": "2026-10-19",
            "range_assumed": False,
        },
    }
    assert interpreted_as(body) == (
        "weekly service request forecast · all service types · "
        "weeks starting 2026-08-31 to 2026-10-19 · next 8 weeks"
    )


@pytest.mark.parametrize("route", ["multi_domain", "out_of_scope", "ambiguous", None])
def test_no_line_when_no_specialist_read_the_question(route):
    assert interpreted_as({"route": {"route": route} if route else {}}) is None


def test_a_decline_without_a_valid_parsed_request_has_no_line():
    assert interpreted_as({"route": {"route": "reporting"}, "parsed_request": None}) is None


# ---------------------------------------------------------------- qa_status words


def test_verified_never_reads_as_verified_correct():
    words = qa_text("verified")
    assert words.startswith("Figures checked for the request as interpreted")
    assert "correct" not in words.lower()


def test_every_qa_status_has_the_documented_words_and_not_applicable_has_none():
    assert qa_text("failed").startswith("Not verified")
    assert qa_text("unavailable").startswith("Not verified")
    assert qa_text("not_checked").startswith("Not checked")
    assert qa_text("not_applicable") is None


# ---------------------------------------------------------------- response mapping


def test_the_view_carries_only_the_displayed_fields(kit):
    kit.sign_in()
    r = kit.ask("How is SLA?")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {
        "question",
        "answer",
        "outcome",
        "interpreted_as",
        "qa_status",
        "qa_text",
        "escalate",
        "warning",
        "trace_id",
    }
    assert body["question"] == "How is SLA?"
    assert body["interpreted_as"].startswith("SLA compliance")
    assert body["qa_text"].startswith("Figures checked")
    assert "route" not in body and "reporting" not in body and "task_id" not in body


def test_a_degraded_answer_shows_the_warning_once(kit):
    warning = (
        "Verification (QA) is temporarily unavailable, so this answer could not be "
        "checked and is not verified."
    )
    kit.upstream.body = answered(
        outcome="degraded",
        escalate=True,
        warning=warning,
        qa_status="unavailable",
        answer=warning + "\n\nNot verified: SLA compliance was 94.1%.",
    )
    kit.sign_in()
    body = kit.ask().json()
    assert body["escalate"] is True and body["warning"] == warning
    assert body["answer"] == "Not verified: SLA compliance was 94.1%."
    assert body["qa_text"].startswith("Not verified")


def test_answer_without_warning_leaves_other_text_alone():
    assert answer_without_warning("plain", None) == "plain"
    assert answer_without_warning("plain", "other") == "plain"


@pytest.mark.parametrize("status", [422, 429, 503, 500])
def test_an_orchestrator_error_is_passed_on_as_its_user_facing_detail(kit, status):
    kit.upstream.status = status
    kit.upstream.body = {
        "error": "rate_limited",
        "detail": "The language model is rate-limited right now.",
        "trace_id": "t",
    }
    kit.sign_in()
    r = kit.ask()
    assert r.status_code == status
    assert r.json() == {
        "error": "rate_limited",
        "detail": "The language model is rate-limited right now.",
    }


def test_an_unexpected_upstream_status_is_a_generic_502(kit):
    kit.upstream.status = 418
    kit.upstream.body = {"error": "x", "detail": "http://internal-host:8000 exploded"}
    kit.sign_in()
    r = kit.ask()
    assert r.status_code == 502
    assert "internal-host" not in r.text


def test_an_unreachable_orchestrator_is_a_503_with_no_cause(kit):
    kit.upstream.raise_error = httpx.ConnectError("connect to http://orchestrator:8000 failed")
    kit.sign_in()
    r = kit.ask()
    assert r.status_code == 503
    assert "orchestrator" not in r.text and "connect" not in r.text.lower()


def test_one_post_and_no_retry_per_question(kit):
    kit.upstream.status = 503
    kit.upstream.body = {"error": "model_unavailable", "detail": "Please try again shortly."}
    kit.sign_in()
    kit.ask()
    assert len(kit.upstream.requests) == 1
    assert kit.upstream.requests[0].url.path == "/ask"
