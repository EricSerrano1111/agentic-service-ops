"""The LLM client every agent uses (ADR-048).

    client = LLMClient.from_env("specialist")
    result = await client.generate(prompt, response_model=MyRequest, trace_id=trace_id)

One provider (Gemini), free key by default, per-minute and daily 429s told apart,
every call metered at list price. See `client.py` for the policy.
"""

from __future__ import annotations

from .client import LLMClient, LLMResult, UsageTotals
from .config import LLMSettings, Price, Secret, load_price_table
from .errors import (
    LLMAuthError,
    LLMBudgetExceeded,
    LLMConfigError,
    LLMDailyQuotaExhausted,
    LLMError,
    LLMOutputInvalid,
    LLMRateLimited,
    LLMRequestCapReached,
    LLMRequestError,
    LLMUnavailable,
)

__all__ = [
    "LLMAuthError",
    "LLMBudgetExceeded",
    "LLMClient",
    "LLMConfigError",
    "LLMDailyQuotaExhausted",
    "LLMError",
    "LLMOutputInvalid",
    "LLMRateLimited",
    "LLMRequestCapReached",
    "LLMRequestError",
    "LLMResult",
    "LLMSettings",
    "LLMUnavailable",
    "Price",
    "Secret",
    "UsageTotals",
    "load_price_table",
]
