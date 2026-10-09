"""Phase 4a end-to-end checks (ADR-088): a normal question with its cost in the logs, then the
reporting agent stopped (degraded, naming reporting), then the breaker open (fails fast).

Calls Gemini through the running stack on the free key: about 6 calls in total (the budget):
2 for the normal question (route, parse), and 1 routing call for each of the four asks with the
agent stopped. Local only, never in CI. Run with the stack up and the dataset loaded:

    $env:RUN_E2E=1; $env:RUN_LIVE_LLM=1
    .venv\\Scripts\\python -m pytest tests/e2e/test_resilience_e2e.py -v -rs -s
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import httpx
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

QUESTION = "How many incidents were reported last month?"


def compose(*args: str) -> None:
    subprocess.run(
        ["docker", "compose", *args], cwd=REPO_ROOT, check=True, capture_output=True, timeout=120
    )


def llm_calls() -> int:
    return sum(
        1
        for service in ("orchestrator", "agent_reporting")
        for line in compose_logs(service)
        if line.get("msg") == "llm call"
    )


def line_for(trace_id: str, msg: str) -> dict | None:
    for line in compose_logs("orchestrator"):
        if line.get("trace_id") == trace_id and line.get("msg") == msg:
            return line
    return None


def test_cost_is_logged_then_a_stopped_agent_degrades_then_the_breaker_fails_fast():
    started_with = llm_calls()

    # 1. A normal question still answers, now with a cost total in the logs.
    normal = ask(QUESTION)
    assert normal.status_code == 200, normal.text
    body = normal.json()
    assert body["outcome"] == "answered" and body["escalate"] is False
    done = line_for(body["trace_id"], "ask answered")
    assert done is not None and done["cost_usd"] > 0  # routing + the agent's parse call
    print(f"\nnormal question: cost_usd={done['cost_usd']} (list-price, free mode)")

    compose("stop", "agent_reporting")
    try:
        # 2. With the reporting agent stopped: the degraded result naming reporting. Three
        #    counted failures open the breaker; each costs one routing call.
        for attempt in range(1, 4):
            response = ask(QUESTION)
            assert response.status_code == 200, response.text
            degraded = response.json()
            assert degraded["outcome"] == "degraded" and degraded["escalate"] is True
            assert degraded["unavailable_capability"] == "reporting"
            assert "reporting service is temporarily unavailable" in degraded["warning"]
            assert degraded["route"]["route"] == "reporting"  # it was routed before it failed
            for secret in ("Traceback", "ConnectError", "Errno", "agent_reporting:8001"):
                assert secret not in response.text, secret
            print(f"stopped agent, ask {attempt}: degraded, naming reporting")

        # 3. The breaker is open: the next ask fails fast, without calling the agent.
        began = time.perf_counter()
        fast = ask(QUESTION)
        elapsed = time.perf_counter() - began
        fast_body = fast.json()
        assert fast_body["outcome"] == "degraded"
        assert fast_body["unavailable_capability"] == "reporting"
        opened = line_for(fast_body["trace_id"], "breaker open")
        assert opened is not None and opened["dependency"] == "reporting"
        assert line_for(fast_body["trace_id"], "dependency failed") is None  # no call was made
        print(f"breaker open, ask 4: degraded in {elapsed:.1f}s (routing only), no agent call")
    finally:
        compose("start", "agent_reporting")

    used = llm_calls() - started_with
    print(f"live model calls used in this check: {used}")
    assert used <= 6

    # The other domains are unaffected: the sentiment route has its own breaker (no model
    # call here; a /healthz check that the orchestrator itself is still healthy).
    assert (
        httpx.get(
            f"{os.environ.get('ORCHESTRATOR_URL', 'http://localhost:8000')}/healthz"
        ).status_code
        == 200
    )
