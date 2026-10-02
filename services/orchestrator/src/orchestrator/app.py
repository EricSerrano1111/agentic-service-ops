"""FastAPI app: `POST /ask` and `/healthz`.

Each question is routed by one LLM call (`routing.Router`). Reporting questions go to
the reporting agent, sentiment questions to the sentiment agent and forecast questions to
the forecast agent, over A2A with the question text (ADR-046, ADR-068, ADR-072).
Multi-domain questions get a split instruction (ADR-032), and anything else a polite
decline. Errors map to clear HTTP responses; no raw exception
text reaches the caller.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Literal

import httpx
from a2a.client import A2AClientError, A2AClientTimeoutError
from common import bind_trace_id, new_trace_id
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from llm import (
    LLMClient,
    LLMDailyQuotaExhausted,
    LLMError,
    LLMOutputInvalid,
    LLMRateLimited,
    LLMRequestError,
    LLMUnavailable,
)
from pydantic import BaseModel, Field

from .a2a_client import AgentProtocolError, send_question
from .config import Settings
from .result import (
    TaskFailed,
    extract_answer,
    extract_forecast_answer,
    extract_sentiment_answer,
)
from .routing import Router, RoutingLLM, out_of_scope_message, split_message

log = logging.getLogger("orchestrator")

RATE_LIMIT_RETRY_AFTER_S = 60

Outcome = Literal["answered", "not_available", "split_required", "declined"]


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
    (ADR-072). `trace_id` correlates the log lines of every service that handled the
    request.
    """

    answer: str
    outcome: Outcome
    route: dict[str, Any]
    prompt_version: str
    reporting: dict[str, Any] | None = None
    sentiment: dict[str, Any] | None = None
    forecast: dict[str, Any] | None = None
    task_id: str | None = None
    trace_id: str


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


def create_app(settings: Settings, llm: RoutingLLM | None = None) -> FastAPI:
    router = Router(
        llm if llm is not None else LLMClient.from_env("orchestrator"), as_of=settings.as_of
    )
    app = FastAPI(title="orchestrator", version="0.1.0")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "service": "orchestrator"}

    @app.post("/ask", response_model=AskResponse)
    async def ask(body: AskRequest) -> Any:
        """PROVISIONAL: the request/response contract is decided with the gateway in Sprint 5."""
        trace_id = new_trace_id()
        with bind_trace_id(trace_id):
            began = time.perf_counter()
            log.info("ask received", extra={"question_chars": len(body.question)})

            try:
                async with asyncio.timeout(settings.route_timeout_s):
                    decision = await router.classify(body.question, trace_id=trace_id)
            except TimeoutError:
                log.warning("routing timed out", extra={"timeout_s": settings.route_timeout_s})
                return _error(
                    504,
                    "routing_timeout",
                    f"Routing the question took longer than {settings.route_timeout_s:g}s.",
                    trace_id,
                )
            except LLMError as exc:
                log.warning("routing failed", extra={"llm_error": type(exc).__name__})
                return _llm_error(exc, trace_id)

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
                        "duration_ms": round((time.perf_counter() - began) * 1000, 1),
                    },
                )
                payload = AskResponse(answer=answer, outcome=outcome, **base, **more)
                return JSONResponse(payload.model_dump(), headers={"X-Trace-Id": trace_id})

            if decision.route == "forecast":
                return await ask_forecast(body.question, trace_id, base, respond)
            if decision.route == "sentiment":
                return await ask_sentiment(body.question, trace_id, base, respond)
            if decision.route == "multi_domain":
                return respond(split_message(decision), "split_required")
            if decision.route == "out_of_scope":
                return respond(out_of_scope_message(), "declined")

            try:
                task = await send_question(
                    settings.agent_reporting_url,
                    body.question,
                    trace_id=trace_id,
                    timeout_s=settings.a2a_timeout_s,
                )
                answer, reporting = extract_answer(task)
            except (TimeoutError, A2AClientTimeoutError, httpx.TimeoutException):
                log.warning("agent timed out", extra={"timeout_s": settings.a2a_timeout_s})
                return _error(
                    504,
                    "agent_timeout",
                    f"The reporting agent did not answer within {settings.a2a_timeout_s:g}s.",
                    trace_id,
                    route=base["route"],
                )
            except TaskFailed as exc:
                if exc.error_code == "not_supported":
                    # A metric or breakdown the agent doesn't offer yet: a normal answer,
                    # like an unbuilt domain, not an error. The agent's text says so.
                    return respond(exc.reason, "not_available", task_id=exc.task_id)
                log.warning(
                    "agent task failed",
                    extra={"task_id": exc.task_id, "reason": exc.reason, "code": exc.error_code},
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
            except (A2AClientError, httpx.HTTPError, AgentProtocolError) as exc:
                log.warning("agent unavailable", extra={"error": type(exc).__name__})
                return _error(
                    502,
                    "agent_unavailable",
                    "The reporting agent is unavailable.",
                    trace_id,
                    route=base["route"],
                )

            return respond(
                answer,
                "answered",
                reporting=reporting.model_dump(mode="json"),
                task_id=task.id,
            )

    async def ask_sentiment(question: str, trace_id: str, base: dict, respond) -> Any:
        """The sentiment route (ADR-068), with the same failure handling as reporting's."""
        timeout_s = settings.sentiment_a2a_timeout_s
        try:
            task = await send_question(
                settings.agent_sentiment_url, question, trace_id=trace_id, timeout_s=timeout_s
            )
            answer, sentiment = extract_sentiment_answer(task)
        except (TimeoutError, A2AClientTimeoutError, httpx.TimeoutException):
            log.warning("agent timed out", extra={"agent": "sentiment", "timeout_s": timeout_s})
            return _error(
                504,
                "agent_timeout",
                f"The sentiment agent did not answer within {timeout_s:g}s.",
                trace_id,
                route=base["route"],
            )
        except TaskFailed as exc:
            if exc.error_code == "not_supported":
                # A breakdown the agent doesn't offer: a normal answer whose text names
                # what it can do (ADR-068), not an error.
                return respond(exc.reason, "not_available", task_id=exc.task_id)
            log.warning(
                "agent task failed",
                extra={"task_id": exc.task_id, "reason": exc.reason, "code": exc.error_code},
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
        except (A2AClientError, httpx.HTTPError, AgentProtocolError) as exc:
            log.warning(
                "agent unavailable", extra={"agent": "sentiment", "error": type(exc).__name__}
            )
            return _error(
                502,
                "agent_unavailable",
                "The sentiment agent is unavailable.",
                trace_id,
                route=base["route"],
            )
        return respond(
            answer, "answered", sentiment=sentiment.model_dump(mode="json"), task_id=task.id
        )

    async def ask_forecast(question: str, trace_id: str, base: dict, respond) -> Any:
        """The forecast route (ADR-072), with the same failure handling as the others."""
        timeout_s = settings.forecast_a2a_timeout_s
        try:
            task = await send_question(
                settings.agent_forecast_url, question, trace_id=trace_id, timeout_s=timeout_s
            )
            answer, forecast = extract_forecast_answer(task)
        except (TimeoutError, A2AClientTimeoutError, httpx.TimeoutException):
            log.warning("agent timed out", extra={"agent": "forecast", "timeout_s": timeout_s})
            return _error(
                504,
                "agent_timeout",
                f"The forecast agent did not answer within {timeout_s:g}s.",
                trace_id,
                route=base["route"],
            )
        except TaskFailed as exc:
            if exc.error_code == "not_supported":
                # Unsupported forecasts and past periods: a normal answer whose text names
                # what is supported (ADR-072), not an error.
                return respond(exc.reason, "not_available", task_id=exc.task_id)
            log.warning(
                "agent task failed",
                extra={"task_id": exc.task_id, "reason": exc.reason, "code": exc.error_code},
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
        except (A2AClientError, httpx.HTTPError, AgentProtocolError) as exc:
            log.warning(
                "agent unavailable", extra={"agent": "forecast", "error": type(exc).__name__}
            )
            return _error(
                502,
                "agent_unavailable",
                "The forecast agent is unavailable.",
                trace_id,
                route=base["route"],
            )
        return respond(
            answer, "answered", forecast=forecast.model_dump(mode="json"), task_id=task.id
        )

    return app
