"""Per-request cost accounting (ADR-088).

Every LLM call's list-price cost is added to the request's running total. A service wraps the
handling of one request in `track_request_cost()`; `LLMClient` calls `add_cost` after each call,
which adds to the total of the request the call belongs to (a context variable, so concurrent
requests keep separate totals). The service then returns its total to the orchestrator in A2A
response metadata under `COST_KEY`, and the orchestrator sums the services' totals with its own
and enforces `MAX_COST_PER_RUN_USD` before each further hop.

Costs are list-price estimates, also in free mode (L-71). A cost received from another service
is validated: a negative, non-finite or non-numeric value is rejected, because a negative
number could be used to keep a runaway request under the cap.

The same tracker also times the request's internal steps and counts its model calls, so a service
can report them beside its cost (the answer journey, data dictionary section 6 rule 10). Timings and
counts are read-only telemetry: they change no answer.
"""

from __future__ import annotations

import asyncio
import contextvars
import math
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

#: The metadata key a service reports its request cost under.
COST_KEY = "cost_usd"
#: The metadata keys a service reports its model-call count and its timed steps under.
CALLS_KEY = "model_calls"
STEPS_KEY = "steps"
#: The most steps one service reports for one request (a guard on the response size).
MAX_STEPS = 8
#: ADR-088: the default per-request cap, a guard against runaway loops rather than a budget.
DEFAULT_MAX_COST_PER_RUN_USD = 0.02
MAX_COST_VAR = "MAX_COST_PER_RUN_USD"


class RequestCost:
    """The running list-price total for one request in this process."""

    def __init__(self) -> None:
        self.total_usd = 0.0
        self.calls = 0
        self.started = time.perf_counter()
        #: Timed steps: {step, start_ms, duration_ms, status}, start relative to `started`.
        self.steps: list[dict[str, Any]] = []

    def add(self, usd: float | None) -> None:
        self.calls += 1
        if usd is not None:
            self.total_usd += usd


_current: contextvars.ContextVar[RequestCost | None] = contextvars.ContextVar(
    "request_cost", default=None
)


@contextmanager
def track_request_cost() -> Iterator[RequestCost]:
    """Collect the cost of every LLM call made while handling one request."""
    cost = RequestCost()
    token = _current.set(cost)
    try:
        yield cost
    finally:
        _current.reset(token)


def add_cost(usd: float | None) -> None:
    """Add one LLM call's cost to the current request's total, if a request is being tracked."""
    current = _current.get()
    if current is not None:
        current.add(usd)


def current_cost_usd() -> float:
    """The list-price total so far for the request being handled (0 outside a request)."""
    current = _current.get()
    return 0.0 if current is None else current.total_usd


class timed_step:  # noqa: N801 - used as `with timed_step(...)` / `async with timed_step(...)`
    """Time one internal step of the request being handled (a no-op outside a request). The step
    is recorded `ok`, `timeout` (a timeout cancelled it) or `failed`; the exception propagates."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __enter__(self) -> None:
        self._current = _current.get()
        self._began = time.perf_counter()

    def __exit__(self, exc_type, exc, tb) -> None:
        current = self._current
        if current is None or len(current.steps) >= MAX_STEPS:
            return
        if exc_type is None:
            status = "ok"
        elif issubclass(exc_type, TimeoutError | asyncio.CancelledError):
            status = "timeout"
        else:
            status = "failed"
        now = time.perf_counter()
        current.steps.append(
            {
                "step": self.name,
                "start_ms": round((self._began - current.started) * 1000, 1),
                "duration_ms": round((now - self._began) * 1000, 1),
                "status": status,
            }
        )

    async def __aenter__(self) -> None:
        self.__enter__()

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self.__exit__(exc_type, exc, tb)


def current_calls() -> int:
    """How many model calls the request being handled has made so far (0 outside a request)."""
    current = _current.get()
    return 0 if current is None else current.calls


def telemetry_metadata() -> dict[str, Any]:
    """`model_calls` and the timed `steps` of the request being handled, for response metadata
    beside `cost_usd`."""
    current = _current.get()
    return {CALLS_KEY: current_calls(), STEPS_KEY: [] if current is None else list(current.steps)}


def parse_cost_usd(raw: Any) -> float | None:
    """A cost received from another service, or None if it is not a usable amount.
    Protobuf metadata carries numbers as floats; a whole number is accepted too."""
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        return None
    value = float(raw)
    if not math.isfinite(value) or value < 0:
        return None
    return value


def max_cost_per_run_usd(env: dict[str, str] | None = None) -> float:
    """`MAX_COST_PER_RUN_USD` (default 0.02). A blank value (as in `.env.example`) means the
    default; a non-numeric, negative or zero value is a configuration error."""
    source = os.environ if env is None else env
    raw = (source.get(MAX_COST_VAR) or "").strip()
    if not raw:
        return DEFAULT_MAX_COST_PER_RUN_USD
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"{MAX_COST_VAR} must be a number of US dollars, got {raw!r}") from None
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{MAX_COST_VAR} must be greater than zero, got {raw!r}")
    return value
