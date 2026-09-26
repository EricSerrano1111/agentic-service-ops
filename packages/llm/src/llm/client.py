"""`LLMClient`: the one way any agent calls a model.

Policy (ADR-048):
- Free key by default; paid only with `LLM_MODE=paid`, its own key and caps.
- Per-minute 429: wait the delay the error states, then retry, within
  `LLM_MAX_RETRY_WAIT_S` of total waiting; past that, `LLMRateLimited`.
- Daily 429: `LLMDailyQuotaExhausted` at once. Billing or permission: `LLMAuthError` at
  once. 5xx and timeouts: a small bounded backoff, then `LLMUnavailable`.
- Every call is metered at list price and logged as one JSON line with the trace id.
- Structured output is validated with Pydantic; invalid output raises
  `LLMOutputInvalid` with the raw text. There is no repair loop.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, TypeVar

from common import bind_trace_id
from pydantic import BaseModel, ValidationError

from .classify import Kind, classify
from .config import LLMSettings, Price, Role, load_price_table
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
from .transport import GeminiTransport, Transport

log = logging.getLogger("llm")

T = TypeVar("T", bound=BaseModel)

#: A per-minute 429 that states no delay waits this long (build_corpus.py
#: PER_MINUTE_429_MIN_WAIT_S: the quota window is a minute).
FALLBACK_RATE_LIMIT_WAIT_S = 30.0
#: Transient 5xx/timeout retries: few and short, since ADR-034 caps a request at 120 s.
#: Backoff is build_corpus.py's full jitter, uniform(0, min(cap, base * 2**attempt)).
MAX_TRANSIENT_RETRIES = 2
BACKOFF_BASE_S = 1.0
BACKOFF_CAP_S = 4.0
#: Output tokens assumed when estimating a call's cost before sending it (paid spend cap).
EXPECTED_OUTPUT_TOKENS = 1_000


@dataclass(frozen=True)
class LLMResult[R: BaseModel]:
    text: str
    parsed: R | None
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float | None  # list-price equivalent; None only for an unpriced model
    latency_s: float
    attempts: int


@dataclass
class UsageTotals:
    """Per-process running totals, for the Sprint 4 eval pricing."""

    calls: int = 0
    requests: int = 0  # HTTP requests sent, retries included
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    by_outcome: dict[str, int] = field(default_factory=dict)


def _usage(response: Any) -> tuple[int, int]:
    """(input, output) tokens; thinking tokens count as output. From build_corpus.py."""
    u = getattr(response, "usage_metadata", None)
    inp = getattr(u, "prompt_token_count", None) or 0
    out = (getattr(u, "candidates_token_count", None) or 0) + (
        getattr(u, "thoughts_token_count", None) or 0
    )
    return int(inp), int(out)


class LLMClient:
    def __init__(
        self,
        settings: LLMSettings,
        *,
        transport: Transport | None = None,
        prices: dict[str, Price] | None = None,
        sleep=asyncio.sleep,
    ) -> None:
        self.settings = settings
        self.prices = prices if prices is not None else load_price_table()
        self._transport = transport if transport is not None else GeminiTransport(settings)
        self._sleep = sleep
        self._secrets = tuple(s for s in (settings.api_key.reveal(),) if s)
        self.totals = UsageTotals()
        if settings.mode == "paid" and settings.default_model not in self.prices:
            raise LLMConfigError(
                f"paid mode needs a price for {settings.default_model} to enforce the spend "
                "cap; add it to llm/prices.toml"
            )

    @classmethod
    def from_env(cls, role: Role, **kwargs: Any) -> LLMClient:
        return cls(LLMSettings.from_env(role), **kwargs)

    def __repr__(self) -> str:
        s = self.settings
        return f"LLMClient(mode={s.mode!r}, model={s.default_model!r}, calls={self.totals.calls})"

    # ------------------------------------------------------------------ helpers

    def _scrub(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, "***")
        return text

    def _cost(self, model: str, input_tokens: int, output_tokens: int) -> float | None:
        price = self.prices.get(model)
        return None if price is None else price.cost_usd(input_tokens, output_tokens)

    def _check_caps(self, model: str, prompt: str) -> None:
        s = self.settings
        if self.totals.requests >= s.max_requests:
            raise LLMRequestCapReached(
                f"request cap reached: {self.totals.requests} of LLM_MAX_REQUESTS={s.max_requests}"
            )
        if s.mode == "paid":
            if model not in self.prices:
                raise LLMConfigError(f"paid mode needs a price for {model} to enforce the cap")
            # ~4 characters per token, plus the expected output (build_corpus.py estimate).
            estimate = self.prices[model].cost_usd(len(prompt) // 4, EXPECTED_OUTPUT_TOKENS)
            if s.max_spend_usd is not None and self.totals.cost_usd + estimate > s.max_spend_usd:
                raise LLMBudgetExceeded(
                    f"spend cap: ${self.totals.cost_usd:.4f} spent + ~${estimate:.4f} for this "
                    f"call would exceed LLM_MAX_SPEND_USD=${s.max_spend_usd:.2f}"
                )

    # ------------------------------------------------------------------ the call

    async def generate(
        self,
        prompt: str,
        *,
        model: str | None = None,
        response_model: type[T] | None = None,
        trace_id: str | None,
    ) -> LLMResult[T]:
        model = model or self.settings.default_model
        began = time.perf_counter()
        attempts = 0
        waited = 0.0
        transient = 0
        inp = out = 0
        cost: float | None = None
        # Overwritten on every exit path except cancellation (a BaseException).
        outcome = "cancelled"
        self.totals.calls += 1
        try:
            while True:
                self._check_caps(model, prompt)
                attempts += 1
                self.totals.requests += 1
                try:
                    response = await self._transport.generate(
                        model=model, prompt=prompt, response_model=response_model
                    )
                except Exception as exc:
                    c = classify(exc)
                    detail = self._scrub(c.message)[:300]
                    if c.kind is Kind.RATE_LIMIT:
                        delay = c.retry_delay_s
                        if delay is None:
                            delay = FALLBACK_RATE_LIMIT_WAIT_S
                        if waited + delay > self.settings.max_retry_wait_s:
                            raise LLMRateLimited(
                                f"{model}: per-minute quota 429 would need {waited + delay:g}s "
                                f"of waiting, over LLM_MAX_RETRY_WAIT_S="
                                f"{self.settings.max_retry_wait_s:g}s"
                            ) from None
                        await self._sleep(delay)
                        waited += delay
                        continue
                    if c.kind is Kind.TRANSIENT:
                        if transient >= MAX_TRANSIENT_RETRIES:
                            raise LLMUnavailable(
                                f"{model}: {c.code or type(exc).__name__} persisted through "
                                f"{MAX_TRANSIENT_RETRIES} retries: {detail}"
                            ) from None
                        delay = random.uniform(0, min(BACKOFF_CAP_S, BACKOFF_BASE_S * 2**transient))
                        transient += 1
                        await self._sleep(delay)
                        waited += delay
                        continue
                    if c.kind is Kind.DAILY_QUOTA:
                        raise LLMDailyQuotaExhausted(model, c.quota_id) from None
                    if c.kind in (Kind.BILLING, Kind.AUTH):
                        raise LLMAuthError(
                            f"{model} ({self.settings.mode} key, {self.settings.key_var}): "
                            f"{c.kind.value} error {c.code}: {detail}"
                        ) from None
                    raise LLMRequestError(f"{model}: error {c.code}: {detail}") from None

                inp, out = _usage(response)
                cost = self._cost(model, inp, out)
                self.totals.input_tokens += inp
                self.totals.output_tokens += out
                self.totals.cost_usd += cost or 0.0
                text = getattr(response, "text", None) or ""
                parsed = None
                if response_model is not None:
                    try:
                        parsed = response_model.model_validate_json(text)
                    except ValidationError as exc:
                        raise LLMOutputInvalid(
                            f"{model}: output did not validate as {response_model.__name__}: "
                            f"{exc.error_count()} error(s)",
                            raw_text=text,
                        ) from None
                outcome = "ok"
                return LLMResult(
                    text=text,
                    parsed=parsed,
                    model=model,
                    input_tokens=inp,
                    output_tokens=out,
                    cost_usd=cost,
                    latency_s=round(time.perf_counter() - began, 3),
                    attempts=attempts,
                )
        except LLMError as exc:
            outcome = type(exc).__name__
            raise
        except Exception as exc:  # never expected; still metered, never leaks a key
            outcome = type(exc).__name__
            raise LLMError(f"{model}: unexpected {type(exc).__name__}") from None
        finally:
            self.totals.by_outcome[outcome] = self.totals.by_outcome.get(outcome, 0) + 1
            price = self.prices.get(model)
            with bind_trace_id(trace_id):
                log.info(
                    "llm call",
                    extra={
                        "model": model,
                        "mode": self.settings.mode,
                        "billed": self.settings.mode == "paid",
                        "input_tokens": inp,
                        "output_tokens": out,
                        "cost_usd": None if cost is None else round(cost, 6),
                        "price_source": price.source if price else None,
                        "latency_s": round(time.perf_counter() - began, 3),
                        "attempts": attempts,
                        "waited_s": round(waited, 3),
                        "outcome": outcome,
                    },
                )
