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
    assert interpreted_as(answered()) == (
        "Area: incident reporting · Measure: SLA compliance · "
        "Period: 2026-08-01 to 2026-08-30 · Region: Northeast"
    )


def test_resolved_dates_come_from_the_answer_not_the_requests_null_dates():
    body = answered()
    assert body["reporting"]["request"]["start"] is None
    assert "Period: 2026-08-01 to 2026-08-30" in interpreted_as(body)


def test_an_assumed_range_says_so():
    body = answered()
    body["reporting"]["range_assumed"] = True
    assert interpreted_as(body).endswith(
        "(assumed: the question named no dates) · Region: Northeast"
    )


def test_no_region_is_all_regions_and_other_fields_appear_only_when_present():
    line = interpreted_as(reporting(region=None, group_by="service_type", account_name="Acme"))
    assert line == (
        "Area: incident reporting · Measure: SLA compliance · Period: 2026-08-01 to 2026-08-30"
        " · Region: all regions · Account: Acme · Breakdown: service type"
    )
    assert "Technician" not in line


def test_a_technician_is_shown_as_typed():
    assert "Technician: Priya N." in interpreted_as(reporting(technician_name="Priya N."))


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
        "Area: incident reporting · Measure: SLA compliance · "
        "Period: 2026-08-01 to 2026-08-31 · Region: not recognised"
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
        "Area: customer sentiment · Measure: sentiment trend · "
        "Period: 2026-05-01 to 2026-07-31 · Region: all regions · Breakdown: month"
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
        "Area: volume forecast · Measure: weekly service request volume · "
        "Slice: all service types · Period: weeks starting 2026-08-31 to 2026-10-19 · "
        "Horizon: next 8 weeks"
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


@pytest.mark.parametrize(
    ("outcome", "reason"),
    [
        ("needs_clarification", "technician_ambiguous"),
        ("needs_clarification", "intent_ambiguous"),
        ("not_available", None),  # a specialist's decline (`not_supported`)
    ],
)
def test_no_verification_line_when_the_response_carries_no_figures(kit, outcome, reason):
    kit.upstream.body = answered(outcome=outcome, reason=reason, qa_status="verified")
    kit.sign_in()
    body = kit.ask().json()
    assert body["qa_status"] == "verified" and body["qa_text"] is None
    assert body["interpreted_as"] == (
        "Area: incident reporting · Measure: SLA compliance · "
        "Period: 2026-08-01 to 2026-08-30 · Region: Northeast"
    )  # the "Interpreted as:" line is unchanged


def test_an_answered_response_with_figures_still_shows_the_verified_words(kit):
    kit.sign_in()
    assert kit.ask().json()["qa_text"] == (
        "Figures checked for the request as interpreted. "
        "Check that the “Interpreted as” line matches your question."
    )


def test_the_other_statuses_are_unchanged_by_the_outcome_condition():
    for status, start in (("failed", "Not verified"), ("unavailable", "Not verified")):
        assert qa_text(status, "degraded").startswith(start)
    assert qa_text("not_checked", "degraded").startswith("Not checked")
    assert qa_text("not_checked", "answered").startswith("Not checked")
    assert qa_text("not_applicable", "declined") is None


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
    assert body["interpreted_as"].startswith("Area: incident reporting · Measure: SLA compliance")
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


UPSTREAM_DETAIL = "http://mcp-incidents:8101 SELECT secret FROM incidents failed: trace 0xBEEF"
DATA_MSG = "The data service is unavailable right now. Please try again later."
MAPPED = [
    ("agent_task_failed", 502, DATA_MSG),
    ("agent_unavailable", 502, DATA_MSG),
    ("predictions_incomplete", 502, DATA_MSG),
    ("unclear_question", 422, "I couldn't interpret the question. Please rephrase it."),
    (
        "invalid_range",
        422,
        "The date range in the question can't be answered. Please check the dates and try again.",
    ),
    (
        "rate_limited",
        429,
        "The language model is rate-limited right now. Please try again in about a minute.",
    ),
    (
        "daily_quota_exhausted",
        503,
        "The language model's daily quota is used up. It resets at midnight Pacific time.",
    ),
    (
        "model_unavailable",
        503,
        "The language model is temporarily unavailable. Please try again shortly.",
    ),
    ("internal_error", 500, "Something went wrong on our side. Please try again."),
]


@pytest.mark.parametrize(("code", "status", "message"), MAPPED, ids=[m[0] for m in MAPPED])
def test_each_known_upstream_error_code_maps_to_one_fixed_message(kit, code, status, message):
    kit.upstream.status = status
    kit.upstream.body = {"error": code, "detail": UPSTREAM_DETAIL, "trace_id": "t"}
    kit.sign_in()
    r = kit.ask()
    assert r.status_code == status
    assert r.json() == {"error": code, "detail": message}


def test_an_unknown_upstream_code_gets_the_one_generic_message(kit):
    kit.upstream.status = 502
    kit.upstream.body = {"error": "made_up_code", "detail": UPSTREAM_DETAIL, "trace_id": "t"}
    kit.sign_in()
    r = kit.ask()
    assert r.status_code == 502
    assert r.json() == {
        "error": "upstream_error",
        "detail": "The service could not answer. Please try again.",
    }


def test_a_known_code_on_an_unexpected_status_is_the_generic_message(kit):
    kit.upstream.status = 418
    kit.upstream.body = {"error": "rate_limited", "detail": UPSTREAM_DETAIL}
    kit.sign_in()
    r = kit.ask()
    assert r.status_code == 502 and r.json()["error"] == "upstream_error"


@pytest.mark.parametrize(
    "code", [m[0] for m in MAPPED] + ["made_up_code", "x" * 80], ids=lambda c: c[:24]
)
def test_no_upstream_detail_string_reaches_the_response(kit, code):
    kit.upstream.status = 502
    kit.upstream.body = {"error": code, "detail": UPSTREAM_DETAIL, "trace_id": "t"}
    kit.sign_in()
    r = kit.ask()
    for fragment in ("mcp-incidents", "SELECT", "0xBEEF", "8101", UPSTREAM_DETAIL, "x" * 41):
        assert fragment not in r.text
    assert set(r.json()) == {"error", "detail"}


def test_the_upstream_detail_is_fingerprinted_in_the_log_and_not_returned(kit):
    import logging

    class Records(logging.Handler):
        def __init__(self) -> None:
            super().__init__(logging.DEBUG)
            self.records: list[logging.LogRecord] = []

        def emit(self, record: logging.LogRecord) -> None:
            self.records.append(record)

    handler, logger = Records(), logging.getLogger("gateway")
    logger.addHandler(handler)
    previous, was_disabled = logger.level, logger.disabled
    logger.setLevel(logging.INFO)
    logger.disabled = False  # a dictConfig in another test can leave it disabled
    try:
        kit.upstream.status = 502
        kit.upstream.body = {
            "error": "agent_task_failed",
            "detail": "The incidents query failed.",
            "trace_id": "trace-123",
        }
        kit.sign_in()
        r = kit.ask()
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous)
        logger.disabled = was_disabled
    assert "incidents query" not in r.text
    record = next(x for x in handler.records if x.getMessage() == "ask refused upstream")
    # The sentence can name what the user typed, so only its length and hash are logged (ADR-108).
    assert not hasattr(record, "upstream_detail")
    assert record.upstream_detail_chars == len("The incidents query failed.")
    assert len(record.upstream_detail_sha) == 12
    assert record.upstream_trace_id == "trace-123"


def test_a_timeout_waiting_for_the_orchestrator_is_a_fixed_504(kit):
    kit.upstream.raise_error = httpx.ReadTimeout("timed out talking to http://orchestrator:8000")
    kit.sign_in()
    r = kit.ask()
    assert r.status_code == 504
    assert r.json() == {
        "error": "deadline_exceeded",
        "detail": (
            "The question took too long to answer. Please try again, or ask for a shorter period."
        ),
    }
    assert "orchestrator" not in r.text


def test_an_unexpected_upstream_status_is_a_generic_502(kit):  # 418: not one it passes on
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
