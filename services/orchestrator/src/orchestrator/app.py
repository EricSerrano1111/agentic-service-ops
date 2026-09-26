"""FastAPI app: `POST /ask` and `/healthz`.

Walking skeleton: no classification yet. Every question goes to the reporting agent.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from a2a.client import A2AClientError, A2AClientTimeoutError
from common import bind_trace_id, new_trace_id
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .a2a_client import AgentProtocolError, send_question
from .config import Settings
from .result import TaskFailed, extract_answer

log = logging.getLogger("orchestrator")

ROUTE = "reporting"  # hardcoded until intent classification (Sprint 2, next item)


class AskRequest(BaseModel):
    """PROVISIONAL request shape. The gateway contract is decided in Sprint 5."""

    question: str = Field(min_length=1, max_length=2000)


class AskResponse(BaseModel):
    """PROVISIONAL response shape. The gateway contract is decided in Sprint 5.

    `figures` is the specialist's structured data, validated against its contract;
    `task_id` is the A2A task that produced it; `trace_id` correlates the log lines of
    every service that handled the request.
    """

    answer: str
    figures: dict[str, Any]
    route: str
    task_id: str
    trace_id: str


def _error(status: int, error: str, detail: str, trace_id: str, **extra: Any) -> JSONResponse:
    body = {"error": error, "detail": detail, "trace_id": trace_id, **extra}
    return JSONResponse(body, status_code=status, headers={"X-Trace-Id": trace_id})


def create_app(settings: Settings) -> FastAPI:
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
            log.info("ask received", extra={"route": ROUTE, "question_chars": len(body.question)})
            try:
                task = await send_question(
                    settings.agent_reporting_url,
                    body.question,
                    trace_id=trace_id,
                    timeout_s=settings.a2a_timeout_s,
                )
                answer, figures = extract_answer(task)
            except (TimeoutError, A2AClientTimeoutError, httpx.TimeoutException):
                log.warning("agent timed out", extra={"timeout_s": settings.a2a_timeout_s})
                return _error(
                    504,
                    "agent_timeout",
                    f"reporting agent did not answer within {settings.a2a_timeout_s:g}s",
                    trace_id,
                )
            except TaskFailed as exc:
                log.warning(
                    "agent task failed", extra={"task_id": exc.task_id, "reason": exc.reason}
                )
                return _error(
                    502,
                    "agent_task_failed",
                    exc.reason,
                    trace_id,
                    task_id=exc.task_id,
                    state=exc.state,
                )
            except (A2AClientError, httpx.HTTPError, AgentProtocolError) as exc:
                log.warning("agent unavailable", extra={"error": repr(exc)})
                return _error(502, "agent_unavailable", "reporting agent unavailable", trace_id)

            log.info(
                "ask answered",
                extra={
                    "task_id": task.id,
                    "duration_ms": round((time.perf_counter() - began) * 1000, 1),
                },
            )
            response = AskResponse(
                answer=answer, figures=figures, route=ROUTE, task_id=task.id, trace_id=trace_id
            )
            return JSONResponse(response.model_dump(), headers={"X-Trace-Id": trace_id})

    return app
