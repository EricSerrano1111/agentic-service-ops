"""The reporting agent's A2A executor: parse the question, query, answer.

Every task ends in a terminal state, completed or failed, inside one `SendMessage` call.
No `input-required`, no streaming, no push (ADR-047). A failed task's status message
carries user-facing text plus an `error_code` in its metadata, which the orchestrator
maps to an HTTP status. A range is never guessed: an unparseable question fails.
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
from schemas import (
    FirstTimeFixResult,
    IncidentRateResult,
    IncidentSummary,
    ReportingAnswer,
    ReportingRequest,
    SlaComplianceResult,
)

from .config import Settings
from .mcp_client import McpToolError, call_tool
from .parsing import Parser, ParsingLLM
from .render import render_answer

log = logging.getLogger("agent_reporting")

ARTIFACT_NAME = "reporting_answer"

#: The agent, not the model, picks the tool: one fixed tool per metric (ADR-046).
TOOLS: dict[str, tuple[str, type]] = {
    "incident_count": ("get_incidents_by_date_range", IncidentSummary),
    "incident_rate": ("get_incident_rate", IncidentRateResult),
    "sla_compliance": ("get_sla_compliance", SlaComplianceResult),
    "first_time_fix_rate": ("get_first_time_fix_rate", FirstTimeFixResult),
}
SUPPORTED = (
    "incident counts, incident rate, SLA compliance and first-time fix rate, over a date "
    "range; the rates can be broken down by account, region, service type or technician"
)


def unsupported_reason(request: ReportingRequest) -> str | None:
    """Why this request can't be answered yet, or None. Never guesses a nearby metric."""
    if request.metric == "unsupported":
        return f"That metric isn't supported yet. I can report {SUPPORTED}."
    if request.group_by == "unsupported":
        return f"That breakdown isn't supported yet. I can report {SUPPORTED}."
    if request.metric == "incident_count" and request.group_by is not None:
        return (
            "Incident counts can't be broken down yet; the incident rate can. "
            f"I can report {SUPPORTED}."
        )
    return None


DATA_SCHEMA = "ReportingAnswer"
# The MCP server's own message when its query (not the caller's input) failed.
_TOOL_QUERY_FAILED = "incident query failed"


def trace_id_of(context: RequestContext) -> str | None:
    """The orchestrator's trace id: message metadata first, then request metadata."""
    if context.message is not None and context.message.HasField("metadata"):
        trace_id = MessageToDict(context.message.metadata).get(TRACE_ID_KEY)
        if trace_id:
            return str(trace_id)
    trace_id = context.metadata.get(TRACE_ID_KEY)
    return str(trace_id) if trace_id else None


def _llm_failure(exc: LLMError) -> tuple[str, str]:
    """(error_code, user-facing text) for a parsing-call failure."""
    if isinstance(exc, LLMOutputInvalid):
        return (
            "unclear_question",
            "I couldn't read a date range from the question. Please rephrase it, "
            "for example: 'How many incidents were reported in July 2026?'",
        )
    if isinstance(exc, LLMRateLimited):
        return "rate_limited", "The language model is rate-limited right now. Please retry shortly."
    if isinstance(exc, LLMDailyQuotaExhausted):
        return (
            "daily_quota_exhausted",
            "The language model's daily quota is used up. It resets at midnight Pacific time.",
        )
    if isinstance(exc, LLMRequestError):
        # Google rejected the request as malformed: our bug, not an outage.
        return "internal_error", "Something went wrong on our side while reading the question."
    return "model_unavailable", "The language model is temporarily unavailable. Please try again."


class ReportingExecutor(AgentExecutor):
    def __init__(self, settings: Settings, llm: ParsingLLM) -> None:
        self.settings = settings
        self.parser = Parser(llm, settings.as_of)

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
            reason = unsupported_reason(request)
            if reason is not None:
                await self._fail(updater, task.id, "not_supported", reason)
                return

            tool, result_model = TOOLS[request.metric]
            arguments = {"start": resolved.start.isoformat(), "end": resolved.end.isoformat()}
            if request.group_by is not None:
                arguments["group_by"] = request.group_by
            try:
                figures = await call_tool(
                    self.settings.mcp_incidents_url,
                    tool,
                    arguments,
                    result_model,
                    trace_id=trace_id,
                    timeout_s=self.settings.mcp_timeout_s,
                )
            except TimeoutError:
                await self._fail(
                    updater,
                    task.id,
                    "tool_timeout",
                    f"The incidents query timed out after {self.settings.mcp_timeout_s:g}s.",
                )
                return
            except McpToolError as exc:
                if _TOOL_QUERY_FAILED in str(exc):
                    await self._fail(updater, task.id, "tool_error", "The incidents query failed.")
                else:  # the tool rejected the range: its message is written for users
                    await self._fail(
                        updater,
                        task.id,
                        "invalid_range",
                        f"That date range can't be answered: {exc}. "
                        f"Dates are resolved as of {self.settings.as_of.isoformat()}.",
                    )
                return
            except Exception:
                log.exception("MCP call failed", extra={"task_id": task.id})
                await self._fail(
                    updater, task.id, "tool_unavailable", "The incidents service is unavailable."
                )
                return

            answer = ReportingAnswer(
                request=resolved.request,
                start=resolved.start,
                end=resolved.end,
                range_assumed=resolved.assumed,
                as_of=self.settings.as_of,
                figures=figures,
            )
            await updater.add_artifact(
                [
                    new_text_part(
                        render_answer(answer, self.settings.min_group_denominator),
                        media_type="text/plain",
                    ),
                    new_data_part(answer.model_dump(mode="json"), media_type="application/json"),
                ],
                name=ARTIFACT_NAME,
                metadata={"schema": DATA_SCHEMA},
            )
            await updater.complete()
            log.info(
                "task completed",
                extra={"task_id": task.id, "metric": request.metric, "tool": tool},
            )

    async def _fail(self, updater: TaskUpdater, task_id: str, code: str, reason: str) -> None:
        log.warning("task failed", extra={"task_id": task_id, "code": code, "reason": reason})
        await updater.failed(
            updater.new_agent_message([new_text_part(reason)], metadata={"error_code": code})
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        # Tasks finish inside the blocking call that created them; nothing to cancel.
        raise NotImplementedError("cancellation is not supported")
