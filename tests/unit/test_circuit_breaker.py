"""The circuit breaker (ADR-077, ADR-088): opens after 3, fails fast, one trial, per dependency."""

from __future__ import annotations

import asyncio

import pytest
from common import COOLDOWN_S, FAILURE_THRESHOLD, BreakerOpen, CircuitBreaker


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class Boom(Exception):
    """A counted failure."""


class BadRequest(Exception):
    """Not counted: the caller's fault."""


def counts(exc: BaseException) -> bool:
    return isinstance(exc, Boom)


def make(name="dep"):
    clock = Clock()
    return CircuitBreaker(name, clock=clock), clock


async def fail():
    raise Boom


async def bad():
    raise BadRequest


async def ok():
    return "fine"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_the_pre_registered_values():
    assert (FAILURE_THRESHOLD, COOLDOWN_S) == (3, 30.0)
    assert CircuitBreaker("x").failure_threshold == 3 and CircuitBreaker("x").cooldown_s == 30.0


@pytest.mark.anyio
async def test_it_opens_after_three_consecutive_counted_failures_not_two():
    breaker, _ = make()
    for _ in range(2):
        with pytest.raises(Boom):
            await breaker.call(fail, counts)
    assert breaker.state == "closed" and breaker.consecutive_failures == 2
    with pytest.raises(Boom):
        await breaker.call(fail, counts)
    assert breaker.state == "open"


@pytest.mark.anyio
async def test_while_open_it_fails_fast_without_calling_the_dependency():
    breaker, clock = make("forecast")
    for _ in range(3):
        with pytest.raises(Boom):
            await breaker.call(fail, counts)
    calls = []

    async def probe():
        calls.append(1)
        return "x"

    clock.advance(10)
    with pytest.raises(BreakerOpen) as caught:
        await breaker.call(probe, counts)
    assert calls == [] and caught.value.name == "forecast"
    assert caught.value.retry_in_s == pytest.approx(20.0)


@pytest.mark.anyio
async def test_after_the_cooldown_exactly_one_trial_call_is_allowed():
    breaker, clock = make()
    for _ in range(3):
        with pytest.raises(Boom):
            await breaker.call(fail, counts)
    clock.advance(29.9)
    with pytest.raises(BreakerOpen):
        await breaker.call(ok, counts)
    clock.advance(0.2)
    assert breaker.state == "half_open"
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_trial():
        started.set()
        await release.wait()
        return "trial"

    trial = asyncio.create_task(breaker.call(slow_trial, counts))
    await started.wait()
    with pytest.raises(BreakerOpen):  # a second call while the trial is out
        await breaker.call(ok, counts)
    release.set()
    assert await trial == "trial"
    assert breaker.state == "closed"


@pytest.mark.anyio
async def test_a_successful_trial_closes_it_and_resets_the_count():
    breaker, clock = make()
    for _ in range(3):
        with pytest.raises(Boom):
            await breaker.call(fail, counts)
    clock.advance(31)
    assert await breaker.call(ok, counts) == "fine"
    assert breaker.state == "closed" and breaker.consecutive_failures == 0
    with pytest.raises(Boom):  # needs three more to open again, not one
        await breaker.call(fail, counts)
    assert breaker.state == "closed"


@pytest.mark.anyio
async def test_a_failed_trial_reopens_it_for_another_cooldown():
    breaker, clock = make()
    for _ in range(3):
        with pytest.raises(Boom):
            await breaker.call(fail, counts)
    clock.advance(31)
    with pytest.raises(Boom):
        await breaker.call(fail, counts)
    assert breaker.state == "open"
    clock.advance(29)
    with pytest.raises(BreakerOpen):
        await breaker.call(ok, counts)
    clock.advance(2)
    assert await breaker.call(ok, counts) == "fine" and breaker.state == "closed"


@pytest.mark.anyio
async def test_errors_that_are_not_counted_never_open_it():
    breaker, _ = make()
    for _ in range(10):
        with pytest.raises(BadRequest):
            await breaker.call(bad, counts)
    assert breaker.state == "closed"


@pytest.mark.anyio
async def test_a_non_counted_answer_resets_the_consecutive_count():
    breaker, _ = make()
    for _ in range(2):
        with pytest.raises(Boom):
            await breaker.call(fail, counts)
    with pytest.raises(BadRequest):  # the dependency answered
        await breaker.call(bad, counts)
    assert breaker.consecutive_failures == 0
    for _ in range(2):
        with pytest.raises(Boom):
            await breaker.call(fail, counts)
    assert breaker.state == "closed"  # two, not three, in a row


@pytest.mark.anyio
async def test_a_success_between_failures_resets_the_count():
    breaker, _ = make()
    for _ in range(2):
        with pytest.raises(Boom):
            await breaker.call(fail, counts)
    await breaker.call(ok, counts)
    for _ in range(2):
        with pytest.raises(Boom):
            await breaker.call(fail, counts)
    assert breaker.state == "closed"


@pytest.mark.anyio
async def test_one_dependencys_breaker_does_not_affect_another():
    forecast, clock = make("forecast")
    reporting = CircuitBreaker("reporting", clock=clock)
    for _ in range(3):
        with pytest.raises(Boom):
            await forecast.call(fail, counts)
    assert forecast.state == "open"
    assert await reporting.call(ok, counts) == "fine" and reporting.state == "closed"


@pytest.mark.anyio
async def test_a_cancelled_trial_frees_the_slot_without_deciding():
    breaker, clock = make()
    for _ in range(3):
        with pytest.raises(Boom):
            await breaker.call(fail, counts)
    clock.advance(31)
    started = asyncio.Event()

    async def hangs():
        started.set()
        await asyncio.sleep(3600)

    trial = asyncio.create_task(breaker.call(hangs, counts))
    await started.wait()
    trial.cancel()
    with pytest.raises(asyncio.CancelledError):
        await trial
    assert breaker.state == "half_open"
    assert await breaker.call(ok, counts) == "fine" and breaker.state == "closed"


def test_bad_settings_are_rejected():
    with pytest.raises(ValueError):
        CircuitBreaker("x", failure_threshold=0)
    with pytest.raises(ValueError):
        CircuitBreaker("x", cooldown_s=-1)
