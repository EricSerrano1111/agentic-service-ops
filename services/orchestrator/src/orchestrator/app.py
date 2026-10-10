"""FastAPI app: `POST /ask` and `/healthz`.

Each question is routed by one LLM call (`routing.Router`). Reporting questions go to
the reporting agent, sentiment questions to the sentiment agent and forecast questions to
the forecast agent, over A2A with the question text (ADR-046, ADR-068, ADR-072).
Multi-domain questions get a split instruction (ADR-032), and anything else a polite
decline. Errors map to clear HTTP responses; no raw exception text reaches the caller.

One deadline is set when a request arrives and travels with every hop (ADR-034, ADR-088); each
specialist hop runs under that deadline, a circuit breaker per specialist and a per-request cost
cap. When any of them stops a request, or a specialist is down, the answer is the degraded
result (FR-13, NFR-1, NFR-4): `outcome: degraded`, an escalation flag, a warning, and the
capability that is unavailable.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from a2a.client import A2AClientError, A2AClientTimeoutError
from a2a.client.errors import AgentCardResolutionError
from a2a.types import Task
from common import (
    BreakerOpen,
    CircuitBreaker,
    Deadline,
    DeadlineExceeded,
    RequestCost,
    bind_trace_id,
    max_cost_per_run_usd,
    new_trace_id,
    track_request_cost,
)
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from llm import (
    LLMBreakerOpen,
    LLMClient,
    LLMDailyQuotaExhausted,
    LLMError,
    LLMOutputInvalid,
    LLMRateLimited,
    LLMRequestError,
    LLMUnavailable,
)
from pydantic import BaseModel, Field, model_validator
from schemas import QaStatus, Verdict, VerificationRequest

from .a2a_client import AgentCardCache, AgentProtocolError, send_question
from .auth import AgentAuthError, IdTokenProvider
from .config import Settings
from .degraded import (
    FORECAST,
    NOT_VERIFIED_LINE,
    QA,
    REPORTING,
    ROUTING,
    SENTIMENT,
    DegradedResult,
    answer_for,
    qa_status_for,
    warning_for,
)
from .result import (
    TaskFailed,
    extract_answer,
    extract_cost,
    extract_forecast_answer,
    extract_sentiment_answer,
    extract_verdict,
    failure_code,
)
from .routing import (
    Router,
    RoutingLLM,
    clarification_message,
    out_of_scope_message,
    split_message,
)

log = logging.getLogger("orchestrator")

RATE_LIMIT_RETRY_AFTER_S = 60

Outcome = Literal[
    "answered", "not_available", "split_required", "declined", "needs_clarification", "degraded"
]
#: Why an answer is `needs_clarification` (ADR-075): the reporting agent's codes for a
#: technician or account name that picks out no one or several (ADR-073, ADR-086), or an
#: ambiguous question.
#: Null for every other outcome.
Reason = Literal[
    "technician_not_found",
    "technician_ambiguous",
    "account_not_found",
    "account_ambiguous",
    "intent_ambiguous",
]
_CLARIFY = (
    "technician_not_found",
    "technician_ambiguous",
    "account_not_found",
    "account_ambiguous",
)


class AskRequest(BaseModel):
    """PROVISIONAL request shape. The gateway contract is decided in Sprint 5."""

    question: str = Field(min_length=1, max_length=2000)


class AskResponse(BaseModel):
    """PROVISIONAL response shape. The gateway contract is decided in Sprint 5.

    `route` is the routing decision (with its reason, for the trace) and
    `prompt_version` the routing prompt that made it. For an answered reporting question,
    `reporting` holds the specialist's validated payload: the parsed request, the range
    queried, the as-of date and the figures; `task_id` is the A2A task. For an answered
    sentiment question, `sentiment` holds the sentiment agent's validated payload instead
    (ADR-068), and for a forecast question `forecast` holds the forecast agent's
    (ADR-072). `reason` says why an answer is `needs_clarification`, and is null for every
    other outcome (ADR-075). `trace_id` correlates the log lines of every service that
    handled the request.

    `outcome: degraded` is the degraded result (FR-13, ADR-088): `escalate` is true, `warning`
    says why, and `unavailable_capability` names a dependency that is down. `answer` then holds
    the warning, followed by the best available answer marked "not verified" when one exists.
    An answer that failed verification is never shown. `route` is empty when the request was
    stopped before routing.
    """

    answer: str
    outcome: Outcome
    reason: Reason | None = None
    route: dict[str, Any]
    prompt_version: str
    reporting: dict[str, Any] | None = None
    sentiment: dict[str, Any] | None = None
    forecast: dict[str, Any] | None = None
    task_id: str | None = None
    trace_id: str
    escalate: bool = False
    warning: str | None = None
    unavailable_capability: str | None = None
    #: Whether the verification agent checked this answer (ADR-089): `verified`; `not_checked`
    #: (no check exists yet, as for sentiment, or the request ended first); `unavailable`
    #: (QA was needed and could not run); `not_applicable` (no specialist answered).
    qa_status: QaStatus = "not_applicable"

    @model_validator(mode="after")
    def _reason_only_for_clarification(self) -> AskResponse:
        if (self.outcome == "needs_clarification") != (self.reason is not None):
            raise ValueError("reason is set exactly when the outcome is needs_clarification")
        degraded = self.outcome == "degraded"
        if degraded != self.escalate or degraded != (self.warning is not None):
            raise ValueError("a degraded result escalates and warns; nothing else does")
        if self.unavailable_capability is not None and not degraded:
            raise ValueError("only a degraded result names an unavailable capability")
        if self.qa_status == "verified" and (
            degraded or self.outcome not in ("answered", "not_available", "needs_clarification")
        ):
            raise ValueError("only a specialist's answer or decline can be verified")
        if self.qa_status == "unavailable" and not degraded:
            raise ValueError("only a degraded result can say QA was unavailable")
        return self


def _error(
    status: int,
    error: str,
    detail: str,
    trace_id: str,
    headers: dict[str, str] | None = None,
    **extra: Any,
) -> JSONResponse:
    body = {"error": error, "detail": detail, "trace_id": trace_id, **extra}
    return JSONResponse(
        body, status_code=status, headers={"X-Trace-Id": trace_id, **(headers or {})}
    )


def _llm_error(exc: LLMError, trace_id: str) -> JSONResponse:
    """Map a routing-call failure. Messages are ours; the exception text never leaks."""
    if isinstance(exc, LLMOutputInvalid):
        return _error(
            422,
            "unclear_question",
            "I couldn't interpret the question. Please rephrase it.",
            trace_id,
        )
    if isinstance(exc, LLMRateLimited):
        return _error(
            429,
            "rate_limited",
            f"The language model is rate-limited right now. Please retry in about "
            f"{RATE_LIMIT_RETRY_AFTER_S} seconds.",
            trace_id,
            headers={"Retry-After": str(RATE_LIMIT_RETRY_AFTER_S)},
        )
    if isinstance(exc, LLMDailyQuotaExhausted):
        return _error(
            503,
            "daily_quota_exhausted",
            "The language model's daily quota is used up. It resets at midnight Pacific time.",
            trace_id,
        )
    if isinstance(exc, LLMUnavailable):
        return _error(
            503,
            "model_unavailable",
            "The language model is temporarily unavailable. Please try again shortly.",
            trace_id,
        )
    if isinstance(exc, LLMRequestError):
        # Google rejected our request as malformed: a bug on our side, not an outage.
        return _error(
            500,
            "internal_error",
            "Something went wrong on our side while reading the question.",
            trace_id,
        )
    # Auth, budget, request cap, config: an operator problem, not the caller's.
    return _error(503, "model_unavailable", "The service can't answer right now.", trace_id)


# Agent failure codes (agent_reporting.executor) -> (status, error). The agent's text is
# written for the user, so it is passed through as the detail.
_AGENT_ERRORS: dict[str, tuple[int, str]] = {
    "unclear_question": (422, "unclear_question"),
    "invalid_range": (422, "invalid_range"),
    "rate_limited": (429, "rate_limited"),
    "daily_quota_exhausted": (503, "daily_quota_exhausted"),
    "model_unavailable": (503, "model_unavailable"),
    "internal_error": (500, "internal_error"),
}


class TaskOutage(Exception):
    """A task that failed because the service behind it could not do its job (QA's database or
    model was down). It counts against that service's breaker, unlike a task that failed
    because of the input."""


#: QA task failures that mean QA could not decide, as opposed to a request it rejected.
QA_OUTAGE_CODES = ("qa_unavailable", "interpretation_unavailable", "qa_timeout")
#: The most a reviewer note handed back to a specialist may be, before it is sent (ADR-089).
MAX_GUIDANCE = 300


def is_dependency_failure(exc: BaseException) -> bool:
    """Does this A2A error count against the dependency's breaker (ADR-088)?

    Timeouts, connection errors and HTTP 5xx do. A 4xx, a validation error or a protocol
    error is the caller's or the content's fault, not the dependency's, and does not.
    """
    if isinstance(exc, TaskOutage | TimeoutError | A2AClientTimeoutError | httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, AgentCardResolutionError):
        if exc.status_code is not None:
            return exc.status_code >= 500
        cause = exc.__cause__ or exc.__context__
        return True if cause is None else is_dependency_failure(cause)
    if isinstance(exc, A2AClientError):
        cause = exc.__cause__ or exc.__context__
        return cause is not None and is_dependency_failure(cause)
    return False


@dataclass
class RequestState:
    """What one request carries from hop to hop: its trace id, its one deadline (ADR-034) and
    its running cost (ADR-088)."""

    trace_id: str
    deadline: Deadline
    spend: RequestCost  # the orchestrator's own LLM calls (the routing call)
    max_cost_usd: float
    downstream_usd: float = 0.0  # what the specialists report back
    decision: Any = None  # the routing decision, once made
    prompt_version: str = ""

    @property
    def total_usd(self) -> float:
        return self.spend.total_usd + self.downstream_usd


@dataclass(frozen=True)
class Specialist:
    key: str  # "reporting"
    capability: str  # the name a warning uses
    url: str
    cap_s: float  # this hop's own cap (before the request deadline clamps it)
    breaker: CircuitBreaker
    extract: Callable[[Task], tuple[str, BaseModel]]
    field: str  # the AskResponse field the payload goes in
    clarify: bool = False  # does it return name-clarification codes (reporting)?
    verified: bool = False  # does QA check its answers (ADR-089)?


def create_app(
    settings: Settings,
    llm: RoutingLLM | None = None,
    *,
    breaker_clock: Callable[[], float] = time.monotonic,
) -> FastAPI:
    router = Router(
        llm if llm is not None else LLMClient.from_env("orchestrator"), as_of=settings.as_of
    )
    app = FastAPI(title="orchestrator", version="0.1.0")
    # None locally: no token is fetched or sent. On Cloud Run (A2A_AUTH=google_id_token) one
    # provider caches a token per specialist.
    tokens = IdTokenProvider() if settings.a2a_auth == "google_id_token" else None
    cards = AgentCardCache(settings.agent_card_ttl_s)
    max_cost = max_cost_per_run_usd()

    def breaker(name: str) -> CircuitBreaker:
        return CircuitBreaker(name, clock=breaker_clock)

    specialists = {
        "reporting": Specialist(
            "reporting",
            REPORTING,
            settings.agent_reporting_url,
            settings.a2a_timeout_s,
            breaker("reporting"),
            extract_answer,
            "reporting",
            clarify=True,
            verified=True,
        ),
        "sentiment": Specialist(
            "sentiment",
            SENTIMENT,
            settings.agent_sentiment_url,
            settings.sentiment_a2a_timeout_s,
            breaker("sentiment"),
            extract_sentiment_answer,
            "sentiment",
        ),
        "forecast": Specialist(
            "forecast",
            FORECAST,
            settings.agent_forecast_url,
            settings.forecast_a2a_timeout_s,
            breaker("forecast"),
            extract_forecast_answer,
            "forecast",
            verified=True,
        ),
    }
    qa_spec = Specialist(
        "qa",
        QA,
        settings.agent_qa_url,
        settings.qa_a2a_timeout_s,
        breaker("qa"),
        extract_verdict,
        "qa",
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "service": "orchestrator"}

    async def delegate(
        spec: Specialist,
        question: str,
        state: RequestState,
        *,
        data: dict | None = None,
        metadata: dict | None = None,
    ) -> Task:
        """One hop to a specialist, under the cost cap, the request deadline and the
        specialist's breaker. Raises `DegradedResult` for any of those three, or for a counted
        failure of the specialist; other errors (4xx, a protocol error) propagate."""
        if state.total_usd >= state.max_cost_usd:
            log.warning(
                "cost cap reached",
                extra={"cost_usd": round(state.total_usd, 6), "cap_usd": state.max_cost_usd},
            )
            raise DegradedResult("cost_cap")
        try:
            timeout_s = state.deadline.hop_timeout(spec.cap_s)
        except DeadlineExceeded:
            raise DegradedResult("deadline") from None

        async def hop() -> Task:
            return await send_question(
                spec.url,
                question,
                trace_id=state.trace_id,
                timeout_s=timeout_s,
                deadline=state.deadline,
                token_provider=tokens,
                card_cache=cards,
                **({} if data is None else {"data": data}),
                **({} if not metadata else {"metadata": metadata}),
            )

        async def guarded_hop() -> Task:
            task = await hop()
            if spec is qa_spec and failure_code(task) in QA_OUTAGE_CODES:
                raise TaskOutage(spec.key)  # QA could not decide: count it, fail closed
            return task

        try:
            task = await spec.breaker.call(guarded_hop, is_dependency_failure)
        except BreakerOpen:
            log.warning("breaker open", extra={"dependency": spec.key})
            raise DegradedResult("dependency", spec.capability) from None
        except Exception as exc:
            if not is_dependency_failure(exc):
                raise
            log.warning(
                "dependency failed",
                extra={"dependency": spec.key, "error": type(exc).__name__},
            )
            if isinstance(exc, TimeoutError | A2AClientTimeoutError | httpx.TimeoutException) and (
                timeout_s < spec.cap_s
            ):  # the request deadline, not the hop's own cap, cut this hop short
                raise DegradedResult("deadline") from None
            raise DegradedResult("dependency", spec.capability) from None
        state.downstream_usd += extract_cost(task) or 0.0
        return task

    def degraded_response(d: DegradedResult, state: RequestState, began: float) -> JSONResponse:
        log.warning(
            "ask degraded",
            extra={
                "trigger": d.trigger,
                "capability": d.capability,
                "failed_checks": list(d.failed_checks),
                "cost_usd": round(state.total_usd, 6),
                "duration_ms": round((time.perf_counter() - began) * 1000, 1),
            },
        )
        payload = AskResponse(
            answer=answer_for(d),
            outcome="degraded",
            escalate=True,
            warning=warning_for(d),
            unavailable_capability=(
                d.capability if d.trigger in ("dependency", "qa_unavailable") else None
            ),
            qa_status=qa_status_for(d),
            route={} if state.decision is None else state.decision.model_dump(mode="json"),
            prompt_version=state.prompt_version,
            trace_id=state.trace_id,
        )
        return JSONResponse(payload.model_dump(), headers={"X-Trace-Id": state.trace_id})

    @app.post("/ask", response_model=AskResponse)
    async def ask(body: AskRequest) -> Any:
        """PROVISIONAL: the request/response contract is decided with the gateway in Sprint 5."""
        trace_id = new_trace_id()
        with bind_trace_id(trace_id), track_request_cost() as spend:
            began = time.perf_counter()
            state = RequestState(trace_id, Deadline.start(), spend, max_cost)
            state.prompt_version = router.prompt.version
            log.info("ask received", extra={"question_chars": len(body.question)})
            try:
                return await handle(body, state, began)
            except DegradedResult as d:
                return degraded_response(d, state, began)

    async def handle(body: AskRequest, state: RequestState, began: float) -> Any:
        trace_id = state.trace_id
        try:
            route_timeout_s = state.deadline.hop_timeout(settings.route_timeout_s)
        except DeadlineExceeded:
            raise DegradedResult("deadline") from None
        try:
            async with asyncio.timeout(route_timeout_s):
                decision = await router.classify(body.question, trace_id=trace_id)
        except TimeoutError:
            if route_timeout_s < settings.route_timeout_s:
                raise DegradedResult("deadline") from None
            log.warning("routing timed out", extra={"timeout_s": settings.route_timeout_s})
            raise DegradedResult("dependency", ROUTING) from None
        except LLMBreakerOpen:
            log.warning("breaker open", extra={"dependency": "language_model"})
            raise DegradedResult("dependency", ROUTING) from None
        except (LLMOutputInvalid, LLMRequestError) as exc:
            # The question could not be read (the caller's to fix), or Google rejected our request
            # as malformed (our bug): neither is an outage, so neither is a degraded result.
            log.warning("routing failed", extra={"llm_error": type(exc).__name__})
            return _llm_error(exc, trace_id)
        except LLMError as exc:
            # Rate limit, quota, outage, a refused request: routing cannot run (FR-13).
            log.warning("routing failed", extra={"llm_error": type(exc).__name__})
            raise DegradedResult("dependency", ROUTING) from None

        state.decision = decision
        base = {
            "route": decision.model_dump(mode="json"),
            "prompt_version": router.prompt.version,
            "trace_id": trace_id,
        }

        def respond(answer: str, outcome: Outcome, **more: Any) -> JSONResponse:
            log.info(
                "ask answered",
                extra={
                    "outcome": outcome,
                    "route": decision.route,
                    "cost_usd": round(state.total_usd, 6),
                    "duration_ms": round((time.perf_counter() - began) * 1000, 1),
                },
            )
            payload = AskResponse(answer=answer, outcome=outcome, **base, **more)
            return JSONResponse(payload.model_dump(), headers={"X-Trace-Id": trace_id})

        if decision.route in ("reporting", "sentiment", "forecast"):
            return await ask_specialist(
                specialists[decision.route], body.question, state, base, respond
            )
        if decision.route == "multi_domain":
            return respond(split_message(decision), "split_required")
        if decision.route == "out_of_scope":
            return respond(out_of_scope_message(), "declined")
        if decision.route == "ambiguous":
            # ADR-075: no specialist call and no QA; the turn ends (ADR-031).
            return respond(
                clarification_message(decision),
                "needs_clarification",
                reason="intent_ambiguous",
            )
        # "reporting" is also the fallback for a route the table does not name.
        return await ask_specialist(specialists["reporting"], body.question, state, base, respond)

    @dataclass
    class Attempt:
        """One specialist run: an answer, or a decline (a normal answer with no figures)."""

        text: str
        task: Task | None = None
        payload: BaseModel | None = None
        failure: TaskFailed | None = None

    async def run_specialist(
        spec: Specialist, question: str, state: RequestState, base: dict, guidance: str | None
    ) -> Attempt | JSONResponse:
        """Ask a specialist once. An answer or a decline comes back as an `Attempt`; any other
        failure is the HTTP error response for it (not something QA verifies). `guidance` is
        QA's reviewer note from the last attempt, sent as message metadata."""
        trace_id = state.trace_id
        try:
            task = await delegate(
                spec,
                question,
                state,
                metadata={"qa_guidance": guidance[:MAX_GUIDANCE]} if guidance else None,
            )
            answer, payload = spec.extract(task)
            return Attempt(answer, task=task, payload=payload)
        except TaskFailed as exc:
            if exc.error_code == "deadline_exceeded":
                raise DegradedResult("deadline") from None
            if exc.error_code == "not_supported" or (spec.clarify and exc.error_code in _CLARIFY):
                # A request the agent doesn't offer, or a name that picks out no one or several:
                # a normal answer whose text says what to do, not an error.
                return Attempt(exc.reason, failure=exc)
            log.warning(
                "agent task failed",
                extra={
                    "agent": spec.key,
                    "task_id": exc.task_id,
                    "reason": exc.reason,
                    "code": exc.error_code,
                },
            )
            status, error = _AGENT_ERRORS.get(exc.error_code or "", (502, "agent_task_failed"))
            headers = {"Retry-After": str(RATE_LIMIT_RETRY_AFTER_S)} if status == 429 else None
            return _error(
                status,
                error,
                exc.reason,
                trace_id,
                headers=headers,
                task_id=exc.task_id,
                route=base["route"],
            )
        except (A2AClientError, httpx.HTTPError, AgentProtocolError, AgentAuthError) as exc:
            # Not a counted failure of the dependency (those became a degraded result in
            # `delegate`): a 4xx, a protocol error, a token that couldn't be fetched.
            log.warning("agent unavailable", extra={"agent": spec.key, "error": type(exc).__name__})
            return _error(
                502,
                "agent_unavailable",
                f"The {spec.key} agent is unavailable.",
                trace_id,
                route=base["route"],
            )

    async def verify(
        spec: Specialist, question: str, attempt: Attempt, state: RequestState
    ) -> Verdict:
        """One QA hop. QA being down, slow, over budget or unreadable is a degraded result that
        returns the answer marked "not verified": an answer is never verified by default."""
        failure = attempt.failure
        request = VerificationRequest(
            domain=spec.key,
            kind="decline" if failure else "answer",
            question=question,
            text=attempt.text[:20_000],
            answer=None if failure else attempt.payload.model_dump(mode="json"),
            error_code=failure.error_code if failure else None,
            parsed_request=failure.parsed_request if failure else None,
        )
        try:
            task = await delegate(
                qa_spec,
                "verification request",
                state,
                data=request.model_dump(mode="json", exclude_none=True),
            )
            return extract_verdict(task)
        except DegradedResult as d:
            if d.trigger == "dependency":  # QA's breaker, a timeout or a transport failure
                raise DegradedResult("qa_unavailable", QA) from None
            raise
        except TaskFailed as exc:
            if exc.error_code == "deadline_exceeded":
                raise DegradedResult("deadline") from None
            log.warning("qa task failed", extra={"code": exc.error_code})
            raise DegradedResult("qa_unavailable", QA) from None
        except (A2AClientError, httpx.HTTPError, AgentProtocolError, AgentAuthError) as exc:
            log.warning("qa unavailable", extra={"error": type(exc).__name__})
            raise DegradedResult("qa_unavailable", QA) from None

    def pass_through(attempt: Attempt, spec: Specialist, respond, qa_status: QaStatus) -> Any:
        """The response for a specialist's answer or decline, with its verification status."""
        if attempt.failure is not None:
            exc = attempt.failure
            if exc.error_code == "not_supported":
                return respond(
                    exc.reason, "not_available", task_id=exc.task_id, qa_status=qa_status
                )
            return respond(
                exc.reason,
                "needs_clarification",
                reason=exc.error_code,
                task_id=exc.task_id,
                qa_status=qa_status,
            )
        text = attempt.text
        if not spec.verified:
            text += "\n\n" + NOT_VERIFIED_LINE
        return respond(
            text,
            "answered",
            **{spec.field: attempt.payload.model_dump(mode="json")},
            task_id=attempt.task.id,
            qa_status=qa_status,
        )

    async def ask_specialist(
        spec: Specialist, question: str, state: RequestState, base: dict, respond
    ) -> Any:
        """The loop (ADR-089): specialist, then QA. A pass is returned as verified. A figures
        failure ends the request as a degraded result at once. An interpretation failure
        re-asks the specialist with QA's note, up to `max_qa_retry_attempts` times, then ends
        the same way. QA down, the deadline or the cost cap end it as a degraded result that
        shows the unverified answer marked as such; an answer that failed is never shown."""
        guidance: str | None = None
        retries = 0
        while True:
            attempt = await run_specialist(spec, question, state, base, guidance)
            if isinstance(attempt, JSONResponse):
                return attempt
            if not spec.verified:
                return pass_through(attempt, spec, respond, "not_checked")
            try:
                verdict = await verify(spec, question, attempt, state)
            except DegradedResult as d:
                if d.trigger != "qa_failed" and d.best_answer is None:
                    d.best_answer = attempt.text  # shown, marked "not verified"
                raise
            failed = tuple(c.code for c in verdict.failed)
            log.info(
                "qa verdict",
                extra={
                    "domain": spec.key,
                    "attempt": retries + 1,
                    "verdict": verdict.verdict,
                    "failed_checks": list(failed),
                    "advisory_failed": [c.code for c in verdict.advisories if not c.passed],
                    "cost_usd": round(state.total_usd, 6),
                },
            )
            if verdict.verdict == "pass":
                return pass_through(attempt, spec, respond, "verified")
            if verdict.figures_failed or retries >= settings.max_qa_retry_attempts:
                raise DegradedResult("qa_failed", failed_checks=failed)
            retries += 1
            guidance = verdict.guidance
            log.info("qa retry", extra={"domain": spec.key, "retry": retries})

    return app
