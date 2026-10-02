"""The forecast agent's A2A executor: parse the question, query `mcp_volume`, answer.

Mirrors `agent_sentiment.executor`. Every task ends in a terminal state inside one
`SendMessage` call (ADR-047). An unsupported question, a past period, or a period with no
forecast week fails with `not_supported` and a templated decline, before any MCP call
(ADR-072). Numbers come only from `mcp_volume`, which withholds unserved ones (ADR-071).
"""

from __future__ import annotations

import asyncio
import logging

from a2a.helpers.proto_helpers import new_data_part, new_task_from_user_message, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from common import TRACE_ID_KEY, bind_trace_id
from google.protobuf.json_format import MessageToDict
from llm import (
    LLMDailyQuotaExhausted,
    LLMError,
    LLMOutputInvalid,
    LLMRateLimited,
    LLMRequestError,
)
from schemas import ForecastAnswer, VolumeForecast, VolumeHistory

from .config import Settings
from .mcp_client import McpToolError, call_tool
from .parsing import Parser, ParsingLLM, Resolved
from .render import decline_message, no_week_message, render_answer

log = logging.getLogger("agent_forecast")

ARTIFACT_NAME = "forecast_answer"
DATA_SCHEMA = "ForecastAnswer"
FORECAST_TOOL = "get_volume_forecast"
HISTORY_TOOL = "get_order_volume_history"
_TOOL_QUERY_FAILED = "volume query failed"


def trace_id_of(context: RequestContext) -> str | None:
    """The orchestrator's trace id: message metadata first, then request metadata."""
    if context.message is not None and context.message.HasField("metadata"):
        trace_id = MessageToDict(context.message.metadata).get(TRACE_ID_KEY)
        if trace_id:
            return str(trace_id)
    trace_id = context.metadata.get(TRACE_ID_KEY)
    return str(trace_id) if trace_id else None


def _llm_failure(exc: LLMError) -> tuple[str, str]:
    if isinstance(exc, LLMOutputInvalid):
        return (
            "unclear_question",
            "I couldn't read the question. Please rephrase it, for example: "
            "'Forecast request volume for the next 8 weeks.'",
        )
    if isinstance(exc, LLMRateLimited):
        return "rate_limited", "The language model is rate-limited right now. Please retry shortly."
    if isinstance(exc, LLMDailyQuotaExhausted):
        return (
            "daily_quota_exhausted",
            "The language model's daily quota is used up. It resets at midnight Pacific time.",
        )
    if isinstance(exc, LLMRequestError):
        return "internal_error", "Something went wrong on our side while reading the question."
    return "model_unavailable", "The language model is temporarily unavailable. Please try again."


def build_answer(
    resolved: Resolved,
    forecast: VolumeForecast,
    history: VolumeHistory | None,
    as_of,
) -> ForecastAnswer:
    """Keep the requested weeks, and only figures the tool returned. Pure."""
    wanted = set(resolved.horizons)
    weeks = [w for w in forecast.weeks if w.horizon in wanted]
    bands = {b: v for b, v in forecast.bands.items() if b in {w.band for w in weeks}}
    total = None
    if len(weeks) > 1 and all(w.served for w in weeks):
        total = sum(w.point for w in weeks)
    shown = {w.week_start for w in weeks}
    return ForecastAnswer(
        request=resolved.request,
        as_of=as_of,
        trained_through=forecast.trained_through,
        model_version=forecast.model_version,
        range_assumed=resolved.assumed,
        requested_first_week=resolved.requested[0],
        requested_last_week=resolved.requested[-1],
        beyond_horizon_weeks=resolved.beyond,
        weeks=weeks,
        bands=bands,
        period_total=total,
        year_end_weeks=[d for d in forecast.year_end_weeks if d in shown],
        history=list(history.weeks) if history else [],
    )


class ForecastExecutor(AgentExecutor):
    def __init__(self, settings: Settings, llm: ParsingLLM) -> None:
        self.settings = settings
        self.parser = Parser(llm, settings.as_of)

    async def _query(self, resolved: Resolved, trace_id: str | None):
        request = resolved.request
        horizon = max(resolved.horizons, default=1)
        async with asyncio.timeout(self.settings.mcp_timeout_s):
            forecast = await call_tool(
                self.settings.mcp_volume_url,
                FORECAST_TOOL,
                {"slice": request.slice, "horizon_weeks": horizon},
                VolumeForecast,
                trace_id=trace_id,
                timeout_s=self.settings.mcp_timeout_s,
            )
            history = None
            if request.want_history:
                history = await call_tool(
                    self.settings.mcp_volume_url,
                    HISTORY_TOOL,
                    {"slice": request.slice, "weeks": self.settings.history_weeks},
                    VolumeHistory,
                    trace_id=trace_id,
                    timeout_s=self.settings.mcp_timeout_s,
                )
        return forecast, history

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        trace_id = trace_id_of(context)
        with bind_trace_id(trace_id):
            task = context.current_task
            if task is None:
                task = new_task_from_user_message(context.message)
                await event_queue.enqueue_event(task)
            updater = TaskUpdater(event_queue, task.id, task.context_id)
            question = context.get_user_input()
            log.info("task received", extra={"task_id": task.id, "question_chars": len(question)})

            try:
                async with asyncio.timeout(self.settings.parse_timeout_s):
                    resolved = await self.parser.parse(question, trace_id=trace_id)
            except TimeoutError:
                await self._fail(
                    updater,
                    task.id,
                    "model_unavailable",
                    f"Reading the question took longer than {self.settings.parse_timeout_s:g}s.",
                )
                return
            except LLMError as exc:
                code, text = _llm_failure(exc)
                log.warning("parse failed", extra={"llm_error": type(exc).__name__})
                await self._fail(updater, task.id, code, text)
                return

            request = resolved.request
            as_of = self.settings.as_of
            if request.unsupported is not None:
                await self._fail(
                    updater, task.id, "not_supported", decline_message(request.unsupported, as_of)
                )
                return
            if resolved.past:
                await self._fail(
                    updater, task.id, "not_supported", decline_message("past_period", as_of)
                )
                return
            if not resolved.requested:
                await self._fail(updater, task.id, "not_supported", no_week_message(as_of))
                return

            try:
                forecast, history = await self._query(resolved, trace_id)
            except TimeoutError:
                await self._fail(
                    updater,
                    task.id,
                    "tool_timeout",
                    f"The volume query timed out after {self.settings.mcp_timeout_s:g}s.",
                )
                return
            except McpToolError as exc:
                if _TOOL_QUERY_FAILED in str(exc):
                    await self._fail(updater, task.id, "tool_error", "The volume query failed.")
                else:
                    await self._fail(
                        updater,
                        task.id,
                        "invalid_range",
                        f"That question can't be answered: {exc}.",
                    )
                return
            except Exception:
                log.exception("MCP call failed", extra={"task_id": task.id})
                await self._fail(
                    updater, task.id, "tool_unavailable", "The volume service is unavailable."
                )
                return

            answer = build_answer(resolved, forecast, history, as_of)
            await updater.add_artifact(
                [
                    new_text_part(render_answer(answer), media_type="text/plain"),
                    new_data_part(answer.model_dump(mode="json"), media_type="application/json"),
                ],
                name=ARTIFACT_NAME,
                metadata={"schema": DATA_SCHEMA},
            )
            await updater.complete()
            log.info(
                "task completed",
                extra={
                    "task_id": task.id,
                    "slice": request.slice,
                    "weeks": len(answer.weeks),
                    "served_weeks": sum(w.served for w in answer.weeks),
                    "beyond": answer.beyond_horizon_weeks,
                },
            )

    async def _fail(self, updater: TaskUpdater, task_id: str, code: str, reason: str) -> None:
        log.warning("task failed", extra={"task_id": task_id, "code": code, "reason": reason})
        await updater.failed(
            updater.new_agent_message([new_text_part(reason)], metadata={"error_code": code})
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("cancellation is not supported")
