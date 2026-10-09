"""A small async circuit breaker, one per outbound dependency (ADR-077, ADR-088).

It opens after `failure_threshold` (3) consecutive counted failures and stays open for
`cooldown_s` (30 s). After the cool-down it lets exactly one trial call through (half-open):
success closes it, failure re-opens it for another cool-down. While open, `call` raises
`BreakerOpen` at once, so the caller can fail fast to the degraded result and name the
capability that is down (NFR-4).

Which failures count is the caller's decision, passed as `counts`: timeouts, connection
errors, 5xx and the language-model unavailability errors do; 4xx, validation errors and
declines do not, because they are the caller's or the content's fault, not the dependency's.
A call that ends in a non-counted error means the dependency answered, so it resets the
consecutive count and closes a half-open breaker.

State is per process: two Cloud Run instances keep two breakers (L-70). There is no lock:
the state changes happen between awaits on one event loop.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Literal

#: ADR-088's values.
FAILURE_THRESHOLD = 3
COOLDOWN_S = 30.0

State = Literal["closed", "open", "half_open"]


class BreakerOpen(Exception):
    """The breaker is open: the dependency is being given time to recover."""

    def __init__(self, name: str, retry_in_s: float) -> None:
        super().__init__(f"{name} circuit is open")
        self.name = name
        self.retry_in_s = max(0.0, retry_in_s)


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = FAILURE_THRESHOLD,
        cooldown_s: float = COOLDOWN_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1 or cooldown_s < 0:
            raise ValueError("failure_threshold must be at least 1 and cooldown_s not negative")
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_s = cooldown_s
        self._clock = clock
        self._state: State = "closed"
        self._failures = 0
        self._opened_at = 0.0
        self._trial_in_flight = False

    def __repr__(self) -> str:
        return f"CircuitBreaker({self.name!r}, state={self.state!r})"

    @property
    def state(self) -> State:
        """The state now: an open breaker whose cool-down has passed reads as half-open."""
        if self._state == "open" and self._clock() - self._opened_at >= self.cooldown_s:
            return "half_open"
        return self._state

    @property
    def consecutive_failures(self) -> int:
        return self._failures

    # ------------------------------------------------------------------ the state machine

    def before_call(self) -> None:
        """Let a call through, or raise `BreakerOpen`. Letting through after the cool-down
        takes the one trial slot."""
        now = self._clock()
        if self._state == "closed":
            return
        if self._state == "open":
            if now - self._opened_at < self.cooldown_s:
                raise BreakerOpen(self.name, self.cooldown_s - (now - self._opened_at))
            self._state = "half_open"
            self._trial_in_flight = False
        if self._trial_in_flight:  # half-open, and the trial has not finished
            raise BreakerOpen(self.name, 0.0)
        self._trial_in_flight = True

    def record_success(self) -> None:
        self._failures = 0
        self._trial_in_flight = False
        self._state = "closed"

    def record_failure(self) -> None:
        self._trial_in_flight = False
        if self._state == "half_open":
            self._open()
            return
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._open()

    def _open(self) -> None:
        self._state = "open"
        self._opened_at = self._clock()

    def _release_trial(self) -> None:
        """A trial that never finished (cancelled) frees the slot without deciding."""
        self._trial_in_flight = False

    # ------------------------------------------------------------------ guarding a call

    async def call[T](
        self,
        fn: Callable[[], Awaitable[T]],
        counts: Callable[[BaseException], bool],
    ) -> T:
        """Run `fn` under the breaker. `counts(exc)` says whether an exception is a failure of
        the dependency; any other outcome counts as the dependency answering."""
        self.before_call()
        try:
            result = await fn()
        except asyncio.CancelledError:
            self._release_trial()
            raise
        except BaseException as exc:
            if counts(exc):
                self.record_failure()
            else:
                self.record_success()
            raise
        self.record_success()
        return result
