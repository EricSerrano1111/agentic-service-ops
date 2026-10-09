"""Phase 4b end-to-end checks (ADR-089): verified answers through the whole stack, then QA stopped.

Calls Gemini through the running stack on the free key. The budget is 20 calls: each reporting
or forecast question is one routing call, one parse call and one QA interpretation call (3),
the sentiment question is a routing and a parse call (2), and the question asked with QA
stopped is routing and parse (2): 13 expected, 20 allowed. Local only, never in CI. Run with
the stack up and the dataset loaded:

    $env:RUN_E2E=1; $env:RUN_LIVE_LLM=1
    .venv\\Scripts\\python -m pytest tests/e2e/test_qa_e2e.py -v -rs -s

Checks, in order: a reporting question, a region-filtered reporting question and a forecast
question each come back `qa_status: verified` with QA's own log saying every check passed for
that trace; the sentiment question comes back `not_checked` with the visible "not verified"
line; then with `agent_qa` stopped one question gets the degraded result with `qa_status:
unavailable` and the unverified answer marked as such, never verified.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from test_checkpoint_e2e import ask, compose_logs

REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("RUN_E2E") != "1" or os.environ.get("RUN_LIVE_LLM") != "1",
        reason="set RUN_E2E=1 and RUN_LIVE_LLM=1 with compose up (calls Gemini)",
    ),
]

REPORTING = "How many incidents were reported last month?"
REGION = "How many incidents were reported in the west last month?"
FORECAST = "Forecast total requests for the next 8 weeks."
SENTIMENT = "Is customer sentiment trending down in the West?"
BUDGET = 20
SERVICES = ("orchestrator", "agent_reporting", "agent_sentiment", "agent_forecast", "agent_qa")


def compose(*args: str) -> None:
    subprocess.run(
        ["docker", "compose", *args], cwd=REPO_ROOT, check=True, capture_output=True, timeout=180
    )


def llm_calls() -> int:
    return sum(1 for s in SERVICES for line in compose_logs(s) if line.get("msg") == "llm call")


def line_for(service: str, trace_id: str, msg: str) -> dict | None:
    for line in compose_logs(service):
        if line.get("trace_id") == trace_id and line.get("msg") == msg:
            return line
    return None


def verified(question: str, field: str) -> dict:
    response = ask(question)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "answered" and body["escalate"] is False, body["answer"]
    assert body["qa_status"] == "verified" and body[field] is not None
    assert "Not verified" not in body["answer"]
    qa = line_for("agent_qa", body["trace_id"], "task completed")
    assert qa is not None and qa["verdict"] == "pass" and qa["failed_checks"] == []
    seen = line_for("orchestrator", body["trace_id"], "qa verdict")
    assert seen is not None and seen["verdict"] == "pass" and seen["attempt"] == 1
    return body


def test_verified_answers_then_qa_stopped_gives_the_degraded_result():
    started_with = llm_calls()

    body = verified(REPORTING, "reporting")
    print(f"\nreporting: verified, {body['reporting']['figures']['incident_count']} incidents")

    body = verified(REGION, "reporting")
    assert body["reporting"]["figures"]["region"] == "west"
    print(f"region: verified, west {body['reporting']['figures']['incident_count']} incidents")

    body = verified(FORECAST, "forecast")
    print(f"forecast: verified, {len(body['forecast']['weeks'])} weeks")

    response = ask(SENTIMENT)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "answered" and body["qa_status"] == "not_checked"
    assert body["answer"].rstrip().endswith("not yet checked by the verification agent.")
    assert line_for("agent_qa", body["trace_id"], "task received") is None  # QA was not asked
    print("sentiment: not_checked, with the not-verified line")

    compose("stop", "agent_qa")
    try:
        response = ask(REPORTING)
        assert response.status_code == 200, response.text
        degraded = response.json()
        assert degraded["outcome"] == "degraded" and degraded["escalate"] is True
        assert degraded["qa_status"] == "unavailable"
        assert degraded["unavailable_capability"] == "verification (QA)"
        assert "Not verified:" in degraded["answer"] and "is not verified" in degraded["warning"]
        for secret in ("Traceback", "ConnectError", "Errno", "agent_qa:8004"):
            assert secret not in response.text, secret
        print("QA stopped: degraded, qa_status unavailable, answer marked not verified")
    finally:
        compose("start", "agent_qa")

    used = llm_calls() - started_with
    print(f"live model calls used in this check: {used}")
    assert used <= BUDGET
