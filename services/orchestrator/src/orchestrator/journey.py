"""Building the answer journey for one request (data dictionary section 6, rule 10).

The recorder lives in `RequestState` and only watches: it times the routing call and each A2A
call, folds in the steps a service reports about itself, and at the end returns a `schemas.Journey`.
It never alters an answer, a route or a status, and a journey that cannot be built is dropped (None)
rather than allowed to fail the request. Nothing from a service reaches the journey except fixed
vocabulary and numbers: a reported step is accepted only with a known step name for that service, a
known status and finite non-negative times; anything else is ignored.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any

from a2a.types import Task, TaskState
from common import CALLS_KEY, MAX_STEPS, STEPS_KEY
from google.protobuf.json_format import MessageToDict
from pydantic import ValidationError
from schemas import (
    MAX_HOPS,
    MAX_MS,
    REPORTED_STATUSES,
    REPORTED_STEPS,
    Hop,
    Journey,
    QaSummary,
    Verdict,
    interpretation_of,
    qa_summary,
)

from .result import failure_code

log = logging.getLogger("orchestrator")

#: A task that ended with one of these codes is a normal answer (a decline or a clarification),
#: not a failed hop.
DECLINE_CODES = (
    "not_supported",
    "technician_not_found",
    "technician_ambiguous",
    "account_not_found",
    "account_ambiguous",
)
TIMEOUT_CODES = ("deadline_exceeded", "qa_timeout")
MAX_REPORTED_CALLS = 1000
_INTERPRETATIONS = ("faithful", "not_faithful", "not_run", "unavailable")
_MODES = ("advisory", "enforce")


def _number(raw: Any, cap: float) -> float | None:
    """A reported number: a non-boolean int or float, finite, between 0 and `cap`."""
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        return None
    value = float(raw)
    return value if math.isfinite(value) and 0 <= value <= cap else None


@dataclass
class Telemetry:
    """What a service reported about itself in response metadata: steps, model calls and, for QA,
    how its interpretation check went. All of it read defensively; unreadable means empty."""

    steps: list[tuple[str, float, float, str]] = field(default_factory=list)
    calls: int = 0
    interpretation: str | None = None
    mode: str | None = None


def _metadata(task: Task) -> list[dict]:
    structs = [a.metadata for a in task.artifacts if a.HasField("metadata")]
    if task.status.HasField("message") and task.status.message.HasField("metadata"):
        structs.append(task.status.message.metadata)
    found = []
    for struct in structs:
        try:
            found.append(MessageToDict(struct))
        except Exception:  # e.g. an infinite number, which protobuf cannot serialise
            log.warning("ignored unreadable response metadata from a service")
    return found


def extract_telemetry(task: Task | None, service: str) -> Telemetry:
    """The steps, model-call count and QA interpretation a service reported for this request."""
    out = Telemetry()
    if task is None:
        return out
    allowed = REPORTED_STEPS.get(service, ())
    for md in _metadata(task):
        calls = _number(md.get(CALLS_KEY), MAX_REPORTED_CALLS)
        if calls is not None and calls == int(calls):
            out.calls += int(calls)
        raw_steps = md.get(STEPS_KEY)
        if isinstance(raw_steps, list):
            for raw in raw_steps:
                if len(out.steps) >= MAX_STEPS or not isinstance(raw, dict):
                    continue
                start = _number(raw.get("start_ms"), MAX_MS)
                duration = _number(raw.get("duration_ms"), MAX_MS)
                if (
                    raw.get("step") in allowed
                    and raw.get("status") in REPORTED_STATUSES
                    and start is not None
                    and duration is not None
                ):
                    out.steps.append((raw["step"], start, duration, raw["status"]))
        if md.get("qa_interpretation") in _INTERPRETATIONS:
            out.interpretation = md["qa_interpretation"]
        if md.get("qa_mode") in _MODES:
            out.mode = md["qa_mode"]
    return out


def task_status(task: Task) -> str:
    """The hop status of a task that came back: `ok`, or `failed`/`timeout` for one that did not
    complete (a decline or a clarification is an answer, so `ok`)."""
    if task.status.state == TaskState.TASK_STATE_COMPLETED:
        return "ok"
    code = failure_code(task)
    if code in DECLINE_CODES:
        return "ok"
    return "timeout" if code in TIMEOUT_CODES else "failed"


def qa_summary_of(verdict: Verdict, telemetry: Telemetry) -> QaSummary | None:
    """The QA summary for a verdict. QA reports its mode and interpretation state; when it did
    not (an older QA), they are derived from the verdict's shape."""
    mode = telemetry.mode
    if mode is None:
        mode = (
            "enforce"
            if any(c.check_class == "interpretation" for c in verdict.checks)
            else ("advisory")
        )
    interpretation = telemetry.interpretation or interpretation_of(verdict, mode)  # type: ignore[arg-type]
    try:
        return qa_summary(verdict, interpretation, mode)  # type: ignore[arg-type]
    except ValidationError:
        return None


class _Step:
    """`with recorder.step(service, step):` times one orchestrator-side step."""

    def __init__(self, rec: Recorder, service: str, step: str) -> None:
        self.rec, self.service, self.step = rec, service, step

    def __enter__(self) -> None:
        self.start = self.rec.now_ms()
        self.began = time.perf_counter()

    async def __aenter__(self) -> None:
        self.__enter__()

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self.__exit__(exc_type, exc, tb)

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            status = "ok"
        elif issubclass(exc_type, TimeoutError | asyncio.CancelledError):
            status = "timeout"
        else:
            status = "failed"
        self.rec.add(
            self.service,
            self.step,
            self.rec.attempt,
            self.start,
            (time.perf_counter() - self.began) * 1000,
            status,
        )


class Recorder:
    """The hops of one request, in the order they started."""

    def __init__(self, began: float | None = None) -> None:
        self.began = time.perf_counter() if began is None else began
        self.hops: list[tuple[str, str, int, float, float, str]] = []
        self.qa: QaSummary | None = None
        self.attempt = 1  # the revision-loop attempt in progress (ADR-089)

    def now_ms(self) -> float:
        return (time.perf_counter() - self.began) * 1000

    def step(self, service: str, step: str) -> _Step:
        return _Step(self, service, step)

    def add(
        self,
        service: str,
        step: str,
        attempt: int,
        start_ms: float,
        duration_ms: float,
        status: str,
    ) -> None:
        self.hops.append(
            (service, step, attempt, max(start_ms, 0.0), max(duration_ms, 0.0), status)
        )

    def call(
        self,
        service: str,
        start_ms: float,
        duration_ms: float,
        status: str,
        telemetry: Telemetry | None,
    ) -> None:
        """One A2A call, as its reported steps placed inside the call's wall time. A service that
        reported no steps shows as one hop under its first step, carrying the whole wall time and
        the call's status."""
        attempt = self.attempt
        if telemetry is None or not telemetry.steps:
            first = REPORTED_STEPS[service][0]
            self.add(service, first, attempt, start_ms, duration_ms, status)
            return
        for name, offset, length, step_status in telemetry.steps:
            offset = min(offset, duration_ms)
            self.add(
                service,
                name,
                attempt,
                start_ms + offset,
                min(length, duration_ms - offset),
                step_status,
            )

    def build(self, model_calls: int, cost_usd: float) -> Journey | None:
        """The finished journey, or None if it cannot be built (it must never fail a request)."""
        try:
            hops = [
                Hop(
                    service=s,
                    step=st,
                    attempt=min(a, 10),
                    start_ms=round(start, 1),
                    duration_ms=round(dur, 1),
                    status=status,
                )
                for s, st, a, start, dur, status in sorted(self.hops, key=lambda h: h[3])
            ][:MAX_HOPS]
            return Journey(
                hops=hops, qa=self.qa, model_calls=model_calls, cost_usd=round(cost_usd, 6)
            )
        except ValidationError:
            log.warning("journey could not be built; the response carries none")
            return None
