"""Offline tests for packages/llm, against a fake transport. No network, no key.

The fake raises the SDK's real exception classes (`google.genai.errors.ClientError` /
`ServerError`, google-genai 2.25.0), built from error bodies of the real shape.
Where each shape comes from:

- **Envelope** `{"error": {"code", "status", "message", "details"}}`: the body
  `google.genai.errors.APIError` parses. It reads `code`, `status` and `message` from
  under `"error"` (errors.py `_get_code` / `_get_status` / `_get_message`) and keeps the
  whole body as `.details`, which is what `str(exc)` prints.
- **Quota identifiers** `GenerateRequestsPerMinutePerProjectPerModel` and
  `GenerateRequestsPerDayPerProjectPerModel-FreeTier`, with status
  `RESOURCE_EXHAUSTED`: build_corpus.py's 429 handling, as exercised in
  tests/unit/test_build_corpus.py (`test_daily_quota_error_detection`, lines 327-329;
  `test_per_minute_429_backs_off_and_continues`, line 531).
- **Billing messages** ("Your prepayment credits are depleted", "Billing is disabled for
  this project", "billing account not in good standing") with codes 429/403/400:
  tests/unit/test_build_corpus.py `test_billing_error_stops_cleanly_without_retries`,
  lines 818-820.
- **5xx**: 500 INTERNAL and 503 UNAVAILABLE, the codes build_corpus.py retried and its
  run logs record for gemma-4-31b-it (data/generator/corpus/work/run_2026-09-24_*.log;
  the logs keep the code, not the body). "high demand" is from test_build_corpus.py:859.
- **Detail objects** `google.rpc.QuotaFailure` (violations[].quotaId) and
  `google.rpc.RetryInfo` (retryDelay "Ns"): Google's standard error-detail types
  (googleapis google/rpc/error_details.proto), which is where the quota identifiers above
  sit in the body. No real 429 body was ever logged in this repo: the corpus build's
  local daily caps always stopped it first. The live test cannot provoke one either, so
  these two detail shapes are the one part not observed here. Capture a real 429 body
  when one first occurs and replace them.
"""

from __future__ import annotations

import io
import json
import logging
import traceback

import pytest
from google.genai import errors as genai_errors
from llm import (
    LLMAuthError,
    LLMBudgetExceeded,
    LLMClient,
    LLMConfigError,
    LLMDailyQuotaExhausted,
    LLMError,
    LLMOutputInvalid,
    LLMRateLimited,
    LLMRequestCapReached,
    LLMSettings,
    LLMUnavailable,
    Secret,
    load_price_table,
)
from llm.classify import Kind, classify
from pydantic import BaseModel

KEY = "AIzaSyTEST-not-a-real-key-7f3c"
PAID_KEY = "AIzaSyPAID-not-a-real-key-91ab"
MODEL = "gemini-3.5-flash-lite"
PRICES = load_price_table()

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


# --------------------------------------------------------------------------- payloads


def _body(code: int, status: str, message: str, details: list | None = None) -> dict:
    error = {"code": code, "status": status, "message": message}
    if details is not None:
        error["details"] = details
    return {"error": error}


def _quota(quota_id: str) -> dict:
    return {
        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
        "violations": [
            {
                "quotaMetric": (
                    "generativelanguage.googleapis.com/generate_content_free_tier_requests"
                ),
                "quotaId": quota_id,
            }
        ],
    }


def _retry(seconds: str) -> dict:
    return {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": seconds}


QUOTA_MSG = "You exceeded your current quota, please check your plan and billing details."


def per_minute_429(delay: str | None = "7s") -> genai_errors.ClientError:
    details = [_quota("GenerateRequestsPerMinutePerProjectPerModel")]
    if delay is not None:
        details.append(_retry(delay))
    # The real quota message mentions "billing details"; the structured quotaId must win
    # over a naive billing text match. Hence "plan and billing" is kept in the message.
    return genai_errors.ClientError(
        429, _body(429, "RESOURCE_EXHAUSTED", "Quota exceeded.", details)
    )


def daily_429() -> genai_errors.ClientError:
    details = [_quota("GenerateRequestsPerDayPerProjectPerModel-FreeTier"), _retry("41s")]
    return genai_errors.ClientError(
        429, _body(429, "RESOURCE_EXHAUSTED", "Quota exceeded.", details)
    )


def server_error(code: int = 503) -> genai_errors.ServerError:
    status = {500: "INTERNAL", 503: "UNAVAILABLE"}[code]
    return genai_errors.ServerError(code, _body(code, status, "The model is under high demand."))


BILLING = [
    (429, "RESOURCE_EXHAUSTED", "Your prepayment credits are depleted."),
    (403, "PERMISSION_DENIED", "Billing is disabled for this project."),
    (400, "FAILED_PRECONDITION", "billing account not in good standing"),
]


# --------------------------------------------------------------------------- fakes


class Usage:
    def __init__(self, prompt: int, candidates: int, thoughts: int = 0) -> None:
        self.prompt_token_count = prompt
        self.candidates_token_count = candidates
        self.thoughts_token_count = thoughts


class Response:
    def __init__(self, text: str, prompt: int = 1_000, out: int = 200, thoughts: int = 0):
        self.text = text
        self.usage_metadata = Usage(prompt, out, thoughts)


class FakeTransport:
    """Plays a script: each item is a Response to return or an exception to raise."""

    def __init__(self, *script) -> None:
        self.script = list(script)
        self.calls = 0

    async def generate(self, *, model, prompt, response_model):
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class Sleeps:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


def settings(**overrides) -> LLMSettings:
    base = dict(
        mode="free",
        api_key=Secret(KEY),
        default_model=MODEL,
        max_requests=100,
        max_retry_wait_s=30.0,
    )
    return LLMSettings(**(base | overrides))


def client(*script, **overrides) -> tuple[LLMClient, FakeTransport, Sleeps]:
    transport, sleeps = FakeTransport(*script), Sleeps()
    return LLMClient(settings(**overrides), transport=transport, sleep=sleeps), transport, sleeps


@pytest.fixture
def log_lines():
    """JSON lines written by the `llm` logger during the test."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    from common import JsonFormatter

    handler.setFormatter(JsonFormatter("test"))
    logger = logging.getLogger("llm")
    # Alembic's fileConfig (run in-process by other unit tests) disables existing loggers.
    was_disabled, logger.disabled = logger.disabled, False
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        yield lambda: [json.loads(line) for line in stream.getvalue().splitlines()]
    finally:
        logger.removeHandler(handler)
        logger.disabled = was_disabled


class Parsed(BaseModel):
    intent: str
    confidence: float


# --------------------------------------------------------------------------- classification


def test_structured_quota_id_decides_daily_vs_per_minute():
    assert classify(per_minute_429()).kind is Kind.RATE_LIMIT
    assert classify(per_minute_429()).retry_delay_s == 7.0
    assert classify(daily_429()).kind is Kind.DAILY_QUOTA
    assert classify(daily_429()).quota_id == "GenerateRequestsPerDayPerProjectPerModel-FreeTier"


def test_text_fallback_only_without_structured_detail():
    no_detail = genai_errors.ClientError(
        429, _body(429, "RESOURCE_EXHAUSTED", "quota exceeded: requests per day")
    )
    assert classify(no_detail).kind is Kind.DAILY_QUOTA
    bare = genai_errors.ClientError(429, _body(429, "RESOURCE_EXHAUSTED", "slow down"))
    assert classify(bare).kind is Kind.RATE_LIMIT


# --------------------------------------------------------------------------- 429s


async def test_per_minute_429_waits_stated_delay_then_succeeds():
    c, transport, sleeps = client(per_minute_429("7s"), Response("hello"))
    result = await c.generate("hi", trace_id="t")
    assert result.text == "hello"
    assert sleeps.delays == [7.0]
    assert result.attempts == 2 and transport.calls == 2


async def test_per_minute_429_without_stated_delay_uses_build_corpus_fallback():
    c, _, sleeps = client(per_minute_429(delay=None), Response("ok"))
    await c.generate("hi", trace_id="t")
    assert sleeps.delays == [30.0]


async def test_waits_past_max_retry_wait_raise_rate_limited():
    c, transport, sleeps = client(
        per_minute_429("20s"), per_minute_429("20s"), Response("never"), max_retry_wait_s=30.0
    )
    with pytest.raises(LLMRateLimited, match="LLM_MAX_RETRY_WAIT_S=30s"):
        await c.generate("hi", trace_id="t")
    # The first 20 s wait fits; the second would reach 40 s, so it is not taken.
    assert sleeps.delays == [20.0]
    assert transport.calls == 2


async def test_daily_429_raises_immediately_without_retry():
    c, transport, sleeps = client(daily_429(), Response("never"))
    with pytest.raises(LLMDailyQuotaExhausted, match=MODEL) as info:
        await c.generate("hi", trace_id="t")
    assert info.value.model == MODEL
    assert transport.calls == 1 and sleeps.delays == []


# --------------------------------------------------------------------------- 5xx and auth


async def test_5xx_retries_then_succeeds():
    c, transport, sleeps = client(server_error(503), server_error(500), Response("ok"))
    assert (await c.generate("hi", trace_id="t")).attempts == 3
    assert len(sleeps.delays) == 2 and all(0 <= d <= 4 for d in sleeps.delays)


async def test_5xx_retries_are_bounded_then_unavailable():
    c, transport, _ = client(*[server_error(503)] * 5)
    with pytest.raises(LLMUnavailable, match="persisted through 2 retries"):
        await c.generate("hi", trace_id="t")
    assert transport.calls == 3


async def test_timeouts_count_as_transient():
    c, transport, _ = client(TimeoutError("read timed out"), Response("ok"))
    assert (await c.generate("hi", trace_id="t")).text == "ok"


@pytest.mark.parametrize(("code", "status", "message"), BILLING)
async def test_billing_errors_raise_auth_error_without_retry(code, status, message):
    c, transport, sleeps = client(genai_errors.ClientError(code, _body(code, status, message)))
    with pytest.raises(LLMAuthError, match="billing"):
        await c.generate("hi", trace_id="t")
    assert transport.calls == 1 and sleeps.delays == []


async def test_permission_error_raises_auth_error_without_retry():
    err = genai_errors.ClientError(
        403, _body(403, "PERMISSION_DENIED", "Method doesn't allow unregistered callers.")
    )
    c, transport, _ = client(err, Response("never"))
    with pytest.raises(LLMAuthError, match="auth error 403"):
        await c.generate("hi", trace_id="t")
    assert transport.calls == 1


async def test_every_error_is_an_llm_error():
    c, _, _ = client(daily_429())
    with pytest.raises(LLMError):
        await c.generate("hi", trace_id="t")


# --------------------------------------------------------------------------- modes and caps


PAID_ENV = {
    "LLM_MODE": "paid",
    "GOOGLE_AI_API_KEY_PAID": PAID_KEY,
    "LLM_MAX_REQUESTS": "50",
    "LLM_MAX_SPEND_USD": "1.00",
    "GEMINI_MODEL_SPECIALIST": MODEL,
}


def _env(monkeypatch, values: dict) -> None:
    for name in (
        "LLM_MODE",
        "GOOGLE_AI_API_KEY",
        "GOOGLE_AI_API_KEY_PAID",
        "LLM_MAX_REQUESTS",
        "LLM_MAX_SPEND_USD",
        "GEMINI_MODEL_SPECIALIST",
    ):
        monkeypatch.delenv(name, raising=False)
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def test_free_is_the_default_mode(monkeypatch):
    _env(monkeypatch, {"GOOGLE_AI_API_KEY": KEY, "GEMINI_MODEL_SPECIALIST": MODEL})
    s = LLMSettings.from_env("specialist")
    assert s.mode == "free" and s.key_var == "GOOGLE_AI_API_KEY"
    assert s.max_requests == 1000  # the generous free default


def test_paid_mode_starts_with_flag_key_and_caps(monkeypatch):
    _env(monkeypatch, PAID_ENV)
    s = LLMSettings.from_env("specialist")
    assert (s.mode, s.max_requests, s.max_spend_usd) == ("paid", 50, 1.0)
    assert s.api_key.reveal() == PAID_KEY


@pytest.mark.parametrize(
    "missing", ["GOOGLE_AI_API_KEY_PAID", "LLM_MAX_REQUESTS", "LLM_MAX_SPEND_USD"]
)
def test_paid_mode_refuses_to_start_without_key_or_caps(monkeypatch, missing):
    # The free key is present: paid mode must not fall back to it.
    _env(
        monkeypatch,
        {k: v for k, v in PAID_ENV.items() if k != missing} | {"GOOGLE_AI_API_KEY": KEY},
    )
    with pytest.raises(LLMConfigError, match=missing):
        LLMSettings.from_env("specialist")


def test_without_the_flag_the_paid_key_is_never_used(monkeypatch):
    _env(monkeypatch, {k: v for k, v in PAID_ENV.items() if k != "LLM_MODE"})
    # No LLM_MODE=paid: free mode, which needs the free key and ignores the paid one.
    with pytest.raises(LLMConfigError, match="GOOGLE_AI_API_KEY must be set"):
        LLMSettings.from_env("specialist")


def test_model_comes_from_config(monkeypatch):
    _env(monkeypatch, {"GOOGLE_AI_API_KEY": KEY})
    with pytest.raises(LLMConfigError, match="GEMINI_MODEL_SPECIALIST"):
        LLMSettings.from_env("specialist")


async def test_spend_cap_blocks_the_call_before_it_is_sent():
    # One call of 1M input tokens costs $0.30 at Flash-Lite list price. The next call is
    # estimated before sending at ~$0.0025 (1,000 expected output tokens), which would
    # take the total past $0.301.
    c, transport, _ = client(
        Response("a", prompt=1_000_000, out=0),
        Response("never"),
        mode="paid",
        max_spend_usd=0.301,
    )
    await c.generate("x", trace_id="t")
    assert c.totals.cost_usd == pytest.approx(0.30)
    with pytest.raises(LLMBudgetExceeded, match="LLM_MAX_SPEND_USD"):
        await c.generate("x", trace_id="t")
    assert transport.calls == 1  # the second call never reached the transport


async def test_spend_cap_is_not_applied_in_free_mode():
    c, transport, _ = client(
        Response("a", prompt=1_000_000, out=0), Response("b"), max_spend_usd=0.01
    )
    await c.generate("x", trace_id="t")
    await c.generate("x", trace_id="t")
    assert transport.calls == 2


async def test_request_cap_counts_every_request_including_retries():
    c, transport, _ = client(per_minute_429("1s"), Response("a"), Response("never"), max_requests=2)
    await c.generate("x", trace_id="t")  # two requests: the 429 and the retry
    with pytest.raises(LLMRequestCapReached, match="LLM_MAX_REQUESTS=2"):
        await c.generate("x", trace_id="t")
    assert transport.calls == 2


def test_paid_mode_refuses_an_unpriced_model():
    with pytest.raises(LLMConfigError, match="price"):
        LLMClient(
            settings(mode="paid", default_model="gemini-9-unpriced", max_spend_usd=1.0),
            transport=FakeTransport(),
        )


# --------------------------------------------------------------------------- metering


def test_price_table_entries_have_source_and_date():
    for model, price in PRICES.items():
        assert price.source == "UNCONFIRMED" or price.source.startswith("https://"), model
        assert price.as_of.year >= 2026, model


async def test_metering_matches_the_price_table():
    # 12,000 input + (800 output + 200 thinking) at $0.30 / $2.50 per million.
    c, _, _ = client(Response("a", prompt=12_000, out=800, thoughts=200))
    result = await c.generate("x", trace_id="t")
    expected = (12_000 * 0.30 + 1_000 * 2.50) / 1_000_000
    assert (result.input_tokens, result.output_tokens) == (12_000, 1_000)
    assert result.cost_usd == pytest.approx(expected)  # 0.0061
    assert c.totals.cost_usd == pytest.approx(expected)
    assert (c.totals.calls, c.totals.requests) == (1, 1)


async def test_running_totals_accumulate_across_calls():
    c, _, _ = client(Response("a", 100, 10), per_minute_429("1s"), Response("b", 200, 20))
    await c.generate("x", trace_id="t")
    await c.generate("x", trace_id="t")
    t = c.totals
    assert (t.calls, t.requests, t.input_tokens, t.output_tokens) == (2, 3, 300, 30)
    assert t.by_outcome == {"ok": 2}


async def test_unpriced_model_in_free_mode_meters_tokens_with_no_cost(log_lines):
    c, _, _ = client(Response("a", 100, 10))
    result = await c.generate("x", model="gemini-9-unpriced", trace_id="t")
    assert result.cost_usd is None and result.input_tokens == 100
    assert log_lines()[-1]["price_source"] is None


# --------------------------------------------------------------------------- structured output


async def test_structured_output_parses():
    c, _, _ = client(Response('{"intent": "reporting", "confidence": 0.93}'))
    result = await c.generate("x", response_model=Parsed, trace_id="t")
    assert result.parsed == Parsed(intent="reporting", confidence=0.93)


@pytest.mark.parametrize(
    "raw", ['{"intent": "reporting"}', "not json at all", '{"intent": 3, "confidence": "high"}']
)
async def test_invalid_output_raises_with_raw_text_and_no_retry(raw):
    c, transport, _ = client(Response(raw), Response('{"intent": "x", "confidence": 1}'))
    with pytest.raises(LLMOutputInvalid) as info:
        await c.generate("x", response_model=Parsed, trace_id="t")
    assert info.value.raw_text == raw
    assert transport.calls == 1  # no repair loop
    assert c.totals.input_tokens == 1_000  # the tokens were still spent and metered


# --------------------------------------------------------------------------- log line


async def test_one_log_line_per_call_with_trace_id_and_metering(log_lines):
    c, _, _ = client(per_minute_429("2s"), Response("a", prompt=500, out=50))
    await c.generate("x", trace_id="trace-123")
    [line] = log_lines()
    assert line["trace_id"] == "trace-123"
    assert line["msg"] == "llm call"
    expected = {
        "model": MODEL,
        "mode": "free",
        "billed": False,
        "input_tokens": 500,
        "output_tokens": 50,
        "attempts": 2,
        "outcome": "ok",
        "price_source": "https://ai.google.dev/gemini-api/docs/pricing",
    }
    assert {k: line[k] for k in expected} == expected
    assert line["latency_s"] >= 0 and line["waited_s"] == 2.0
    assert line["cost_usd"] == pytest.approx((500 * 0.30 + 50 * 2.50) / 1e6)


async def test_failed_calls_are_logged_with_their_outcome(log_lines):
    c, _, _ = client(daily_429())
    with pytest.raises(LLMDailyQuotaExhausted):
        await c.generate("x", trace_id="t-9")
    [line] = log_lines()
    assert (line["outcome"], line["trace_id"], line["attempts"]) == (
        "LLMDailyQuotaExhausted",
        "t-9",
        1,
    )


# --------------------------------------------------------------------------- key secrecy


async def test_key_appears_in_no_log_line_exception_or_repr(log_lines):
    leaky = [
        # Errors whose bodies echo the key back: the worst case, not the usual one.
        genai_errors.ClientError(
            403, _body(403, "PERMISSION_DENIED", f"API key {KEY} is not valid.")
        ),
        genai_errors.ClientError(400, _body(400, "INVALID_ARGUMENT", f"bad request key={KEY}")),
        genai_errors.ServerError(503, _body(503, "UNAVAILABLE", f"upstream {KEY}")),
    ]
    c, _, _ = client(leaky[0], leaky[1], *[leaky[2]] * 3)
    texts = [repr(c), str(c), repr(c.settings), str(c.settings.api_key), repr(c._transport)]
    for _ in range(3):
        with pytest.raises(LLMError) as info:
            await c.generate("x", trace_id="t")
        exc = info.value
        texts += [str(exc), repr(exc), "".join(traceback.format_exception(exc))]
    texts += [json.dumps(line) for line in log_lines()]
    assert len(log_lines()) == 3
    leaks = [t for t in texts if KEY in t]
    assert leaks == []


def test_real_transport_repr_hides_the_key():
    from llm.transport import GeminiTransport

    transport = GeminiTransport(settings())
    assert KEY not in repr(transport) and KEY not in str(transport)
