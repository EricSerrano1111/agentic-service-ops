"""The reporting agent's A2A executor: one blocking task per message, no LLM yet.

Every task ends in a terminal state, completed or failed, inside one `SendMessage` call.
No `input-required`, no streaming, no push (ADR-047).
"""

from __future__ import annotations

import logging

from a2a.helpers.proto_helpers import new_data_part, new_task_from_user_message, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from common import TRACE_ID_KEY, bind_trace_id
from google.protobuf.json_format import MessageToDict

from .config import Settings
from .mcp_client import McpToolError, get_incidents_by_date_range
from .render import render_incident_summary

log = logging.getLogger("agent_reporting")

ARTIFACT_NAME = "incident_summary"
DATA_SCHEMA = "IncidentSummary"


def trace_id_of(context: RequestContext) -> str | None:
    """The orchestrator's trace id: message metadata first, then request metadata."""
    if context.message is not None and context.message.HasField("metadata"):
        trace_id = MessageToDict(context.message.metadata).get(TRACE_ID_KEY)
        if trace_id:
            return str(trace_id)
    trace_id = context.metadata.get(TRACE_ID_KEY)
    return str(trace_id) if trace_id else None


class ReportingExecutor(AgentExecutor):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        with bind_trace_id(trace_id_of(context)):
            task = context.current_task
            if task is None:
                task = new_task_from_user_message(context.message)
                await event_queue.enqueue_event(task)
            updater = TaskUpdater(event_queue, task.id, task.context_id)
            question = context.get_user_input()
            log.info("task received", extra={"task_id": task.id, "question_chars": len(question)})

            # TODO(ADR-046): replace with question parsing. The question is not read yet.
            start, end = self.settings.skeleton_range_start, self.settings.skeleton_range_end

            try:
                summary = await get_incidents_by_date_range(
                    self.settings.mcp_incidents_url,
                    start,
                    end,
                    trace_id=trace_id_of(context),
                    timeout_s=self.settings.mcp_timeout_s,
                )
            except TimeoutError:
                await self._fail(
                    updater,
                    task.id,
                    f"incidents MCP call timed out after {self.settings.mcp_timeout_s:g}s",
                )
                return
            except McpToolError as exc:
                await self._fail(updater, task.id, f"incidents tool error: {exc}")
                return
            except Exception:
                log.exception("MCP call failed", extra={"task_id": task.id})
                await self._fail(updater, task.id, "incidents MCP server unavailable")
                return

            await updater.add_artifact(
                [
                    new_text_part(render_incident_summary(summary), media_type="text/plain"),
                    new_data_part(summary.model_dump(mode="json"), media_type="application/json"),
                ],
                name=ARTIFACT_NAME,
                metadata={"schema": DATA_SCHEMA},
            )
            await updater.complete()
            log.info(
                "task completed",
                extra={"task_id": task.id, "incident_count": summary.incident_count},
            )

    async def _fail(self, updater: TaskUpdater, task_id: str, reason: str) -> None:
        log.warning("task failed", extra={"task_id": task_id, "reason": reason})
        await updater.failed(updater.new_agent_message([new_text_part(reason)]))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        # Tasks finish inside the blocking call that created them; nothing to cancel.
        raise NotImplementedError("cancellation is not supported")
