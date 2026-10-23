"""The answer journey: how one `/ask` request was handled (data dictionary section 6, rule 10;
ADR-117 item 5).

Every orchestrator response carries an optional `journey`. It is read-only telemetry about a
request that has already happened: it changes no answer, figure, route or `qa_status`, and it
never carries a figure, question text, a name typed by the user, model output text, an error
message or an internal address. Every model here forbids extra fields and takes only the fixed
vocabularies below, so a leak would have to be a new field or value, which validation rejects.

The orchestrator measures `route` and the wall time of each A2A call. A specialist or QA reports
its own timed steps (`parse`, `tool`, `figures_check`, `interpretation_check`) and its
`model_calls` in A2A response metadata beside `cost_usd` (ADR-088). When a service reports no
steps, the orchestrator shows the call as one hop under the service's first step. The gateway
adds a `forward` hop.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .verification import CODE_PATTERN, MAX_CHECKS, Verdict

JourneyService = Literal["gateway", "orchestrator", "reporting", "sentiment", "forecast", "qa"]
JourneyStep = Literal["route", "parse", "tool", "figures_check", "interpretation_check", "forward"]
HopStatus = Literal["ok", "failed", "timeout", "skipped", "not_called"]
Interpretation = Literal["faithful", "not_faithful", "not_run", "unavailable"]
QaMode = Literal["advisory", "enforce"]

MAX_HOPS = 40
#: A guard on a reported time: ten minutes is far past the 120 s request ceiling.
MAX_MS = 600_000.0

#: The steps each service may report about itself (the orchestrator and gateway are not reported).
REPORTED_STEPS: dict[str, tuple[str, ...]] = {
    "reporting": ("parse", "tool"),
    "sentiment": ("parse", "tool"),
    "forecast": ("parse", "tool"),
    "qa": ("figures_check", "interpretation_check"),
}
#: The status a reported step may carry (a service cannot report that it was not called).
REPORTED_STATUSES = ("ok", "failed", "timeout")


class Hop(BaseModel):
    """One step of the request, in order. `start_ms` is relative to the orchestrator receiving
    the request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    service: JourneyService
    step: JourneyStep
    attempt: int = Field(ge=1, le=10)
    start_ms: float = Field(ge=0, le=MAX_MS, allow_inf_nan=False)
    duration_ms: float = Field(ge=0, le=MAX_MS, allow_inf_nan=False)
    status: HopStatus


class QaCheck(BaseModel):
    """One QA check: its fixed code, class and result. QA's detail text is not included."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    code: str = Field(pattern=CODE_PATTERN)
    check_class: Literal["figures", "interpretation"] = Field(alias="class")
    passed: bool


class QaSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    verdict: Literal["pass", "fail"]
    checks: list[QaCheck] = Field(max_length=MAX_CHECKS)
    interpretation: Interpretation
    mode: QaMode


class Journey(BaseModel):
    """`model_calls` and `cost_usd` (a list-price estimate, L-71) are sums over every service for
    this request; they equal the totals the orchestrator logs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    hops: list[Hop] = Field(max_length=MAX_HOPS)
    qa: QaSummary | None = None
    model_calls: int = Field(ge=0, le=1000)
    cost_usd: float = Field(ge=0, le=1000, allow_inf_nan=False)


def interpretation_of(verdict: Verdict, mode: QaMode) -> Interpretation:
    """What happened to QA's interpretation check, from its verdict and mode. In advisory mode the
    result is in `advisories`; in enforce mode it is a check. With neither, it did not run (a
    figures failure ends QA before the model call)."""
    for check in [*verdict.advisories, *verdict.checks]:
        if check.check_class == "interpretation":
            if check.passed:
                return "faithful"
            return "unavailable" if "could not run" in check.detail else "not_faithful"
    return "not_run"


def qa_summary(verdict: Verdict, interpretation: Interpretation, mode: QaMode) -> QaSummary:
    """The journey's view of a verdict: codes, classes and results only. The interpretation check
    is listed in `checks` too when it ran in advisory mode, so the list shows what ran."""
    checks = [
        QaCheck(code=c.code, check_class=c.check_class, passed=c.passed) for c in verdict.checks
    ]
    if interpretation != "not_run":
        for a in verdict.advisories:
            checks.append(QaCheck(code=a.code, check_class=a.check_class, passed=a.passed))
    return QaSummary(
        verdict=verdict.verdict, checks=checks, interpretation=interpretation, mode=mode
    )
