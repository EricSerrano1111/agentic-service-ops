"""FastAPI app: `POST /ask` and `/healthz`.

Each question is routed by one LLM call (`routing.Router`). Reporting questions go to
the reporting agent over A2A with the question text (ADR-046). Sentiment and forecast
get a "not available yet" answer, multi-domain questions a split instruction (ADR-032),
and anything else a polite decline. Errors map to clear HTTP responses; no raw exception
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
    LLMUnavailable,
)
from pydantic import BaseModel, Field

from .a2a_client import AgentProtocolError, send_question
from .config import Settings
from .result import TaskFailed, extract_answer
from .routing import Router, RoutingLLM, not_available_message, out_of_scope_message, split_message

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
    queried, the as-of date and the figures; `task_id` is the A2A task. `trace_id`
    correlates the log lines of every service that handled the request.
    """

    answer: str
    outcome: Outcome
    route: dict[str, Any]
    prompt_version: str
    reporting: dict[str, Any] | None = None
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
}


def create_app(settings: Settings, llm: RoutingLLM | None = None) -> FastAPI:
    router = Router(llm if llm is not None else LLMClient.from_env("orchestrator"))
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

            if decision.route in ("sentiment", "forecast"):
                return respond(not_available_message(decision), "not_available")
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

    return app
