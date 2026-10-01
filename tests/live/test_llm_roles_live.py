"""One real call per role, exactly as production makes it. Local only, never in CI.

    $env:RUN_LIVE_LLM=1; .venv\\Scripts\\python -m pytest tests/live -v -rs

Each test goes through the service's own code path: the role's model from .env, its
per-role settings (thinking level, temperature), its versioned prompt and its real
response model. The earlier live test used one generic model and prompt, so it never
exercised the orchestrator's configuration. That is how gemini-3.7-flash rejecting
thinking level "minimal" reached the checkpoint e2e (2026-09-26). Free mode is forced,
so this cannot spend money: two requests of the free daily quota.
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

pytestmark = [
    pytest.mark.live,
    pytest.mark.anyio,
    pytest.mark.skipif(os.environ.get("RUN_LIVE_LLM") != "1", reason="set RUN_LIVE_LLM=1"),
]

QUESTION = "How many incidents were reported last month?"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def free_mode(monkeypatch):
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    monkeypatch.setenv("LLM_MODE", "free")  # never paid, whatever .env says


async def test_orchestrator_routing_call():
    from llm import LLMClient
    from orchestrator.routing import Router

    client = LLMClient.from_env("orchestrator")
    decision = await Router(client).classify(QUESTION, trace_id="live-orchestrator")
    assert decision.route == "reporting"
    assert client.totals.input_tokens > 0 and client.totals.output_tokens > 0
    model = client.settings.default_model
    print(
        f"\norchestrator: {model}, thinking {client.thinking_level_for(model)!r} -> "
        f"{decision.route} ({decision.reason})"
    )


async def test_specialist_parsing_call():
    from agent_reporting.config import Settings
    from agent_reporting.parsing import Parser
    from llm import LLMClient

    client = LLMClient.from_env("specialist")
    as_of = Settings().as_of
    resolved = await Parser(client, as_of).parse(QUESTION, trace_id="live-specialist")
    # ADR-050: "last month" is the calendar month before the as-of date's month.
    end = as_of.replace(day=1) - dt.timedelta(days=1)
    assert (resolved.start, resolved.end) == (end.replace(day=1), end)
    assert resolved.assumed is False
    assert client.totals.input_tokens > 0 and client.totals.output_tokens > 0
    model = client.settings.default_model
    print(
        f"\nspecialist: {model}, thinking {client.thinking_level_for(model)!r} -> "
        f"{resolved.start} to {resolved.end}"
    )


@pytest.mark.skip(reason="no QA call exists until the Sprint 4 QA agent; add its smoke test then")
async def test_qa_call():
    """Placeholder so the gap is visible: the QA role has a model but no call yet."""


async def test_specialist_parses_a_metric_and_breakdown():
    """prompt parse_v2: metric and group_by, as production parses them (FR-06)."""
    from agent_reporting.config import Settings
    from agent_reporting.parsing import Parser
    from llm import LLMClient

    client = LLMClient.from_env("specialist")
    as_of = Settings().as_of
    resolved = await Parser(client, as_of).parse(
        "What was SLA compliance by region last month?", trace_id="live-specialist-metric"
    )
    end = as_of.replace(day=1) - dt.timedelta(days=1)
    assert resolved.request.metric == "sla_compliance"
    assert resolved.request.group_by == "region"
    assert (resolved.start, resolved.end) == (end.replace(day=1), end)
    print(f"\nspecialist metric: {resolved.request.model_dump(mode='json')}")
