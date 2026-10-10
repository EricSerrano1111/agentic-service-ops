"""Phase 4c end-to-end checks (ADR-090): sentiment answers through the whole stack and QA.

Calls Gemini through the running stack on the free key. The budget is 12 calls: each of the four
questions is one routing call, one parse call and one advisory QA interpretation call (3 x 4).
Local only, never in CI. Run with the stack up, the dataset loaded and the stored predictions in
place:

    $env:RUN_E2E=1; $env:RUN_LIVE_LLM=1
    .venv\Scripts\python -m pytest tests/e2e/test_qa_sentiment_e2e.py -v -rs -s

Checks: a trend question (FR-07's own example), a question asking for example comments, and an
account breakdown (a decline) each come back `qa_status: verified`, QA's log showing a pass with
no failed check and, for the two answers, the rating cross-check line (n, x, p0, result); the
decline carries no figures. One reporting question is the regression check.
"""

from __future__ import annotations

import os
import re

import pytest
from test_checkpoint_e2e import ask, compose_logs

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("RUN_E2E") != "1" or os.environ.get("RUN_LIVE_LLM") != "1",
        reason="set RUN_E2E=1 and RUN_LIVE_LLM=1 with compose up (calls Gemini)",
    ),
]

TREND = "Is sentiment trending down in the West?"
EXAMPLES = "Show me a few negative customer comments from last month."
BY_ACCOUNT = "Which account has the most negative sentiment?"
REPORTING = "How many incidents were reported last month?"
BUDGET = 12
SERVICES = ("orchestrator", "agent_reporting", "agent_sentiment", "agent_forecast", "agent_qa")


def llm_calls() -> int:
    return sum(1 for s in SERVICES for line in compose_logs(s) if line.get("msg") == "llm call")


def line_for(service: str, trace_id: str, msg: str) -> dict | None:
    for line in compose_logs(service):
        if line.get("trace_id") == trace_id and line.get("msg") == msg:
            return line
    return None


def qa_pass(trace_id: str) -> dict:
    qa = line_for("agent_qa", trace_id, "task completed")
    assert qa is not None and qa["verdict"] == "pass" and qa["failed_checks"] == [], qa
    seen = line_for("orchestrator", trace_id, "qa verdict")
    assert seen is not None and seen["verdict"] == "pass" and seen["attempt"] == 1
    return qa


def test_sentiment_answers_are_verified_and_an_account_breakdown_declines_verified():
    started_with = llm_calls()

    response = ask(TREND)
    assert response.status_code == 200, response.text
    trend = response.json()
    assert trend["outcome"] == "answered" and trend["qa_status"] == "verified", trend["answer"]
    assert trend["route"]["route"] == "sentiment" and trend["escalate"] is False
    assert "Not verified" not in trend["answer"] and trend["sentiment"]["trend"] is not None
    qa = qa_pass(trend["trace_id"])
    assert re.fullmatch(r"n=\d+, x=\d+, p0=0\.01: (pass|insufficient_coverage)", qa["rating_check"])
    print(f"\ntrend: verified, {trend['sentiment']['trend']['verdict']}, {qa['rating_check']}")

    response = ask(EXAMPLES)
    assert response.status_code == 200, response.text
    quotes = response.json()
    assert quotes["outcome"] == "answered" and quotes["qa_status"] == "verified", quotes["answer"]
    assert quotes["sentiment"]["examples"], "the question asked for comments"
    qa = qa_pass(quotes["trace_id"])
    print(
        f"examples: verified, {len(quotes['sentiment']['examples'])} quoted, {qa['rating_check']}"
    )

    response = ask(BY_ACCOUNT)
    assert response.status_code == 200, response.text
    decline = response.json()
    assert decline["outcome"] == "not_available" and decline["qa_status"] == "verified"
    assert decline["sentiment"] is None and not re.search(r"\d", decline["answer"])
    qa_pass(decline["trace_id"])
    print("account breakdown: declined, verified, no figures")

    response = ask(REPORTING)
    assert response.status_code == 200, response.text
    reporting = response.json()
    assert reporting["outcome"] == "answered" and reporting["qa_status"] == "verified"
    qa_pass(reporting["trace_id"])
    print("reporting regression: verified")

    used = llm_calls() - started_with
    print(f"live model calls used in this check: {used}")
    assert used <= BUDGET
