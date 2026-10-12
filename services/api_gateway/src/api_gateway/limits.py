"""In-process rate limits (ADR-097). Per instance, and reset on a restart: stated limits (L-88).

`SlidingWindow` is a per-key limit over a window (exchange attempts per client IP per minute;
questions per session per hour). `DailyCap` is the global question cap, counted by
Pacific-time day because the model quota resets at midnight Pacific (ADR-029).
"""

from __future__ import annotations

import datetime as dt
import time
from collections import defaultdict, deque
from collections.abc import Callable
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo("America/Los_Angeles")
#: Keys remembered at once. Past it the oldest are dropped, so a flood of client addresses
#: cannot grow memory without bound.
MAX_KEYS = 10_000


class SlidingWindow:
    def __init__(
        self,
        limit: int,
        window_s: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit, self.window_s, self._clock = limit, window_s, clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def hit(self, key: str) -> bool:
        """Count one attempt for `key`; False when it is over the limit (and not counted)."""
        now = self._clock()
        hits = self._hits[key]
        while hits and now - hits[0] >= self.window_s:
            hits.popleft()
        if len(self._hits) > MAX_KEYS:
            self._evict(now)
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True

    def _evict(self, now: float) -> None:
        for key in [k for k, h in self._hits.items() if not h or now - h[-1] >= self.window_s]:
            del self._hits[key]
        while len(self._hits) > MAX_KEYS:
            del self._hits[next(iter(self._hits))]


class DailyCap:
    def __init__(
        self,
        limit: int,
        now: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.UTC),
    ) -> None:
        self.limit, self._now = limit, now
        self._day: dt.date | None = None
        self._count = 0

    def take(self) -> bool:
        """Count one question; False when today's cap is used up."""
        today = self._now().astimezone(PACIFIC).date()
        if today != self._day:
            self._day, self._count = today, 0
        if self._count >= self.limit:
            return False
        self._count += 1
        return True
