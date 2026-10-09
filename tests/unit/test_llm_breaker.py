"""The Gemini circuit breaker and per-request cost in `packages/llm` (ADR-088)."""

from __future__ import annotations

import pytest
from common import CircuitBreaker, track_request_cost
from llm import (
    LLMAuthError,
    LLMBreakerOpen,
    LLMClient,
    LLMDailyQuotaExhausted,
    LLMOutputInvalid,
    LLMRateLimited,
    LLMRequestError,
    LLMUnavailable,
)
from llm.client import counts_against_gemini
from pydantic import BaseModel
from test_llm_client import (
    BILLING,
    FakeTransport,
    Response,
    Sleeps,
    daily_429,
    per_minute_429,
    server_error,
    settings,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


class Clock:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


class Reply(BaseModel):
    answer: int


def build(*script, clock=None, **overrides):
    transport, sleeps = FakeTransport(*script), Sleeps()
    breaker = CircuitBreaker("gemini", clock=clock or Clock())
    client = LLMClient(settings(**overrides), transport=transport, sleep=sleeps, breaker=breaker)
    return client, transport, breaker


async def call(client, **kwargs):
    return await client.generate("q", trace_id="t", **kwargs)


def unavailable_script(n_calls: int):
    """Each call that ends in LLMUnavailable uses the initial request plus two retries."""
    return [server_error()] * (3 * n_calls)


async def test_three_unavailable_calls_open_the_breaker_and_the_fourth_fails_fast():
    client, transport, breaker = build(*unavailable_script(3))
    for _ in range(3):
        with pytest.raises(LLMUnavailable):
            await call(client)
    assert breaker.state == "open"
    sent = transport.calls
    with pytest.raises(LLMBreakerOpen):
        await call(client)
    assert transport.calls == sent  # fail fast: nothing was sent to Google


async def test_the_breaker_open_error_is_an_llm_unavailable():
    """So code that already handles LLMUnavailable keeps working; the orchestrator checks the
    more specific type first."""
    assert issubclass(LLMBreakerOpen, LLMUnavailable)


async def test_one_trial_after_the_cooldown_decides():
    clock = Clock()
    client, transport, breaker = build(
        *unavailable_script(3), Response('{"answer": 1}'), clock=clock
    )
    for _ in range(3):
        with pytest.raises(LLMUnavailable):
            await call(client)
    clock.t += 29
    with pytest.raises(LLMBreakerOpen):
        await call(client)
    clock.t += 2
    result = await call(client, response_model=Reply)  # the one trial call
    assert result.parsed == Reply(answer=1) and breaker.state == "closed"


async def test_a_failed_trial_reopens_it():
    clock = Clock()
    client, _, breaker = build(*unavailable_script(4), clock=clock)
    for _ in range(3):
        with pytest.raises(LLMUnavailable):
            await call(client)
    clock.t += 31
    with pytest.raises(LLMUnavailable):
        await call(client)
    assert breaker.state == "open"
    with pytest.raises(LLMBreakerOpen):
        await call(client)


@pytest.mark.parametrize(
    ("script", "error"),
    [
        ([per_minute_429("40s")], LLMRateLimited),  # wait over the 30 s limit: counted
        ([daily_429()], LLMDailyQuotaExhausted),
    ],
)
async def test_rate_limiting_and_the_daily_quota_count(script, error):
    client, _, breaker = build(*(script * 3))
    for _ in range(3):
        with pytest.raises(error):
            await call(client)
    assert breaker.state == "open"


async def test_invalid_output_never_opens_it():
    client, _, breaker = build(*[Response("not json")] * 6)
    for _ in range(6):
        with pytest.raises(LLMOutputInvalid):
            await call(client, response_model=Reply)
    assert breaker.state == "closed"


async def test_a_rejected_request_never_opens_it():
    from google.genai import errors as genai_errors

    bad = genai_errors.ClientError(
        400, {"error": {"code": 400, "message": "bad argument", "status": "INVALID_ARGUMENT"}}
    )
    client, _, breaker = build(*[bad] * 6)
    for _ in range(6):
        with pytest.raises(LLMRequestError):
            await call(client)
    assert breaker.state == "closed"


async def test_key_and_billing_problems_never_open_it():
    from google.genai import errors as genai_errors

    code, status, message = BILLING[1]
    err = genai_errors.ClientError(
        code, {"error": {"code": code, "message": message, "status": status}}
    )
    client, _, breaker = build(*[err] * 6)
    for _ in range(6):
        with pytest.raises(LLMAuthError):
            await call(client)
    assert breaker.state == "closed"


def test_which_llm_errors_count():
    assert counts_against_gemini(LLMUnavailable("x"))
    assert counts_against_gemini(LLMRateLimited("x"))
    assert counts_against_gemini(LLMDailyQuotaExhausted("m", "q"))
    assert not counts_against_gemini(LLMBreakerOpen("x"))  # never counts itself
    assert not counts_against_gemini(LLMOutputInvalid("x", raw_text=""))
    assert not counts_against_gemini(LLMRequestError("x"))
    assert not counts_against_gemini(ValueError("x"))


async def test_each_client_has_its_own_breaker_unless_one_is_shared():
    a, _, _ = build()
    b = LLMClient(settings(), transport=FakeTransport(), sleep=Sleeps())
    assert a.breaker is not b.breaker


# --------------------------------------------------------------------------- per-request cost


async def test_each_calls_cost_joins_the_running_total_of_its_request():
    client, _, _ = build(Response("a"), Response("b"))
    with track_request_cost() as cost:
        first = await call(client)
        second = await call(client)
    assert first.cost_usd and second.cost_usd
    assert cost.total_usd == pytest.approx(first.cost_usd + second.cost_usd)
    assert cost.calls == 2


async def test_a_call_outside_a_tracked_request_adds_to_no_total():
    client, _, _ = build(Response("a"))
    with track_request_cost() as cost:
        pass
    await call(client)  # no request is being tracked
    assert cost.total_usd == 0.0
