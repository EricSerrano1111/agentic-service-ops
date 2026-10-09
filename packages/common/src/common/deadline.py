"""One request deadline, passed on every hop (ADR-034, ADR-088).

The orchestrator sets it when a request arrives: now plus 120 s. It travels as an absolute
epoch-milliseconds number in the A2A message metadata, under `DEADLINE_KEY`, next to the trace
id. Each hop then uses the smaller of the time left minus a 5 s reserve and its own existing
cap (`Deadline.hop_timeout`), so the reserve is always left to build the degraded response.

A deadline that arrives in metadata is never trusted (it is a new service edge): a missing or
malformed value is replaced by the receiver's own default of now plus 120 s, a value already in
the past is kept (the request is expired and the hop fails at once), and a value more than the
budget ahead is clamped to now plus the budget.
"""

from __future__ import annotations

import contextvars
import math
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

#: The metadata key the deadline travels under, in A2A message metadata.
DEADLINE_KEY = "deadline_ms"
#: ADR-034: no request runs longer than this.
REQUEST_BUDGET_S = 120.0
#: ADR-088: left over for building the degraded response.
RESERVE_S = 5.0


class DeadlineExceeded(Exception):
    """No time is left for another hop (the remaining time minus the reserve is not positive)."""


@dataclass(frozen=True)
class Deadline:
    """An absolute deadline in epoch milliseconds."""

    at_ms: int
    #: How it came about: "set" (this process started it), "metadata", or why a received
    #: value was not used ("missing", "malformed", "clamped"). For logs; not compared.
    origin: str = field(default="set", compare=False)

    # ------------------------------------------------------------------ making one

    @classmethod
    def start(cls, now: float | None = None, budget_s: float = REQUEST_BUDGET_S) -> Deadline:
        """The deadline for a request that arrives now."""
        now = time.time() if now is None else now
        return cls(int(round((now + budget_s) * 1000)))

    @classmethod
    def from_metadata(
        cls,
        metadata: Mapping[str, Any] | None,
        now: float | None = None,
        budget_s: float = REQUEST_BUDGET_S,
    ) -> Deadline:
        """The deadline carried in `metadata`, never trusted (see the module docstring)."""
        now = time.time() if now is None else now
        raw = None if metadata is None else metadata.get(DEADLINE_KEY)
        if raw is None:
            return _replace(cls.start(now, budget_s), "missing")
        value = _as_ms(raw)
        if value is None:
            return _replace(cls.start(now, budget_s), "malformed")
        ceiling = int(round((now + budget_s) * 1000))
        if value > ceiling:
            return cls(ceiling, "clamped")
        return cls(value, "metadata")

    # ------------------------------------------------------------------ using one

    def remaining_s(self, now: float | None = None) -> float:
        now = time.time() if now is None else now
        return self.at_ms / 1000.0 - now

    def expired(self, now: float | None = None, reserve_s: float = RESERVE_S) -> bool:
        """True when no hop can start: the time left does not exceed the reserve."""
        return self.remaining_s(now) - reserve_s <= 0

    def hop_timeout(
        self, cap_s: float, now: float | None = None, reserve_s: float = RESERVE_S
    ) -> float:
        """min(remaining - reserve, cap) for one hop; `DeadlineExceeded` if that is not positive."""
        usable = self.remaining_s(now) - reserve_s
        if usable <= 0:
            raise DeadlineExceeded(f"{usable:.1f}s usable of the request deadline")
        return min(usable, cap_s)

    def as_metadata(self) -> dict[str, int]:
        return {DEADLINE_KEY: self.at_ms}


def _replace(deadline: Deadline, origin: str) -> Deadline:
    return Deadline(deadline.at_ms, origin)


def _as_ms(raw: Any) -> int | None:
    """An epoch-milliseconds number, or None for anything else. Protobuf `Struct` metadata
    carries numbers as floats, so a whole-valued float is accepted. Booleans, strings, NaN,
    infinity, and zero or negative values are not numbers we will trust."""
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        return None
    if isinstance(raw, float) and not math.isfinite(raw):
        return None
    if raw <= 0:
        return None
    return int(raw)


_current: contextvars.ContextVar[Deadline | None] = contextvars.ContextVar(
    "request_deadline", default=None
)


@contextmanager
def bind_deadline(deadline: Deadline | None) -> Iterator[None]:
    """Make `deadline` the one every hop in this block is clamped to (see `clamp_to_deadline`)."""
    token = _current.set(deadline)
    try:
        yield
    finally:
        _current.reset(token)


def current_deadline() -> Deadline | None:
    return _current.get()


def clamp_to_deadline(cap_s: float) -> float:
    """A hop's timeout under the request deadline bound by `bind_deadline`: min(time left minus
    the reserve, `cap_s`). With no deadline bound, `cap_s` itself. Raises `DeadlineExceeded`
    when no time is left."""
    deadline = _current.get()
    return cap_s if deadline is None else deadline.hop_timeout(cap_s)
