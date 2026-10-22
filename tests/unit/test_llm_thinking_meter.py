"""ADR-114 P0: the client's meter counts thinking tokens.

The usage object is the pinned SDK's own type (google-genai 2.25.0,
`GenerateContentResponseUsageMetadata`), whose thinking field is `thoughts_token_count`.
The call goes through `LLMClient.generate`, the real metering path, against a fake transport.
Offline: no network, no key.
"""

from __future__ import annotations

import asyncio
import logging

from google.genai import types
from llm import LLMClient, LLMSettings, Secret, load_price_table

MODEL = "gemini-3.5-flash-lite"
PROMPT_TOKENS, ANSWER_TOKENS, THINKING_TOKENS = 1_000, 40, 600


class Response:
    text = "ok"

    def __init__(self) -> None:
        self.usage_metadata = types.GenerateContentResponseUsageMetadata(
            prompt_token_count=PROMPT_TOKENS,
            candidates_token_count=ANSWER_TOKENS,
            thoughts_token_count=THINKING_TOKENS,
        )


class Transport:
    async def generate(self, *, model, prompt, response_model, thinking_level):
        return Response()


def client() -> LLMClient:
    settings = LLMSettings(
        mode="free",
        api_key=Secret("k"),
        default_model=MODEL,
        max_requests=10,
        thinking_level="high",
    )
    return LLMClient(settings, transport=Transport())


def test_thinking_tokens_are_output_tokens_priced_at_the_output_rate(caplog):
    c = client()
    with caplog.at_level(logging.INFO, logger="llm"):
        result = asyncio.run(c.generate("q", trace_id="t"))

    thinking_in_output = ANSWER_TOKENS + THINKING_TOKENS
    # (a) counted as output tokens, on the result and on the running totals
    assert result.output_tokens == thinking_in_output
    assert c.totals.output_tokens == thinking_in_output
    # (b) the list-price cost includes them at the output rate
    price = load_price_table()[MODEL]
    expected = (PROMPT_TOKENS * price.input_per_m + thinking_in_output * price.output_per_m) / 1e6
    assert result.cost_usd == expected
    assert (
        result.cost_usd
        > (PROMPT_TOKENS * price.input_per_m + ANSWER_TOKENS * price.output_per_m) / 1e6
    )
    assert c.totals.cost_usd == expected
    # (c) the per-call log record carries them inside `output_tokens` (no field of their own)
    (record,) = [r for r in caplog.records if r.getMessage() == "llm call"]
    assert record.output_tokens == thinking_in_output
    assert record.cost_usd == round(expected, 6)
    assert not hasattr(record, "thinking_tokens")
