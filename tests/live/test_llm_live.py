"""One tiny real call to Gemini on the free tier. Local only, never in CI.

    $env:RUN_LIVE_LLM=1; .venv\\Scripts\\python -m pytest tests/live -q -rs

Uses GOOGLE_AI_API_KEY and GEMINI_MODEL_SPECIALIST from .env, and forces LLM_MODE=free,
so it can never spend money. Costs one request of the free daily quota.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import pytest
from dotenv import load_dotenv
from pydantic import BaseModel

pytestmark = [
    pytest.mark.live,
    pytest.mark.anyio,
    pytest.mark.skipif(os.environ.get("RUN_LIVE_LLM") != "1", reason="set RUN_LIVE_LLM=1"),
]


@pytest.fixture
def anyio_backend():
    return "asyncio"


class Route(BaseModel):
    domain: Literal["reporting", "sentiment", "forecast"]


async def test_free_tier_call_returns_parsed_result_and_tokens(monkeypatch):
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    monkeypatch.setenv("LLM_MODE", "free")  # never paid, whatever .env says
    from llm import LLMClient

    client = LLMClient.from_env("specialist")
    result = await client.generate(
        "Which domain does this question belong to: reporting, sentiment or forecast? "
        'Question: "How many incidents were reported last month?" '
        'Answer as JSON: {"domain": "..."}',
        response_model=Route,
        trace_id="live-test",
    )
    assert isinstance(result.parsed, Route)
    assert result.parsed.domain == "reporting"
    assert result.input_tokens > 0 and result.output_tokens > 0
    assert result.cost_usd is not None and result.cost_usd > 0  # list-price equivalent
    assert client.totals.calls == 1
    print(
        f"\n{result.model}: {result.input_tokens} in / {result.output_tokens} out, "
        f"${result.cost_usd:.6f} list-price equivalent (free tier, not billed), "
        f"{result.latency_s}s, {result.attempts} attempt(s)"
    )
