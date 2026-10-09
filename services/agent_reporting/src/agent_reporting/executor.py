"""The reporting agent's A2A executor: parse the question, query, answer.

Every task ends in a terminal state, completed or failed, inside one `SendMessage` call.
No `input-required`, no streaming, no push (ADR-047). A failed task's status message
carries user-facing text plus an `error_code` in its metadata, which the orchestrator
maps to an HTTP status. A range is never guessed: an unparseable question fails.

A technician named in the question is resolved with `find_technician` before the metric
call (ADR-073), and an account the same way with `find_account` (ADR-086). No match, or more
than one, ends the task with no figures (codes `technician_not_found`,
`technician_ambiguous`, `account_not_found`, `account_ambiguous`); nothing is kept for a
follow-up, so the user asks again with the full name (ADR-031). A technician is resolved
before an account. A region is one of four values, passed straight to the tools; any other
area is declined, never mapped.
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
    AccountMatches,
    FirstTimeFixResult,
    IncidentRateResult,
    IncidentSummary,
    RepeatDriversResult,
    ReportingAnswer,
    ReportingRequest,
    SlaComplianceResult,
    TechnicianMatches,
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
    "repeat_visit_drivers": ("get_repeat_visit_drivers", RepeatDriversResult),
}
FIND_TECHNICIAN = "find_technician"
FIND_ACCOUNT = "find_account"
REGIONS = "northeast, southeast, central or west"
SUPPORTED = (
    "incident counts, incident rate, SLA compliance and first-time fix rate over a date "
    "range, by account, region, service type or technician, or for one named technician "
    "(incident counts also by incident type or severity), optionally for one region "
    "(northeast, southeast, central or west) or one account; and which incident types, "
    "service types, regions, accounts or technicians have more repeat visits"
)
#: Breakdowns each metric offers (ADR-073).
_BREAKDOWNS = {
    "incident_count": {
        "account",
        "region",
        "service_type",
        "technician",
        "incident_type",
        "severity",
    },
    "incident_rate": {"account", "region", "service_type", "technician"},
    "sla_compliance": {"account", "region", "service_type", "technician"},
    "first_time_fix_rate": {"account", "region", "service_type", "technician"},
    "repeat_visit_drivers": {"incident_type", "service_type", "region", "account", "technician"},
}


def unsupported_reason(request: ReportingRequest) -> str | None:
    """Why this request can't be answered yet, or None. Never guesses a nearby metric."""
    if request.metric == "unsupported":
        return f"That metric isn't supported yet. I can report {SUPPORTED}."
    if request.group_by == "unsupported":
        return f"That breakdown isn't supported yet. I can report {SUPPORTED}."
    if request.group_by is not None and request.group_by not in _BREAKDOWNS[request.metric]:
        return (
            f"That metric can't be broken down by {request.group_by.replace('_', ' ')}. "
            f"I can report {SUPPORTED}."
        )
    if request.region == "unsupported":
        return (
            f"I can only restrict a question to one of four regions: {REGIONS}. Other areas, "
            "such as a state or a city, aren't mapped to a region. "
            f"I can report {SUPPORTED}."
        )
    if request.metric == "repeat_visit_drivers" and (
        request.region is not None or request.account_name is not None
    ):
        return (
            "Repeat-visit drivers can't be filtered to one region or account yet; ask for them "
            f"by region or by account instead. I can report {SUPPORTED}."
        )
    if request.region is not None and request.group_by == "region":
        return (
            "A single region's figures can't also be broken down by region. Ask for the "
            f"region alone, or for the breakdown alone. I can report {SUPPORTED}."
        )
    if request.account_name is not None and request.group_by == "account":
        return (
            "A single account's figures can't also be broken down by account. Ask for the "
            f"account alone, or for the breakdown alone. I can report {SUPPORTED}."
        )
    if request.technician_name is not None:
        if request.metric == "repeat_visit_drivers":
            return (
                "Repeat-visit drivers can't be filtered to one technician; ask for them by "
                f"technician instead. I can report {SUPPORTED}."
            )
        if request.group_by is not None:
            return (
                "A single technician's figures can't also be broken down. Ask for the "
                f"technician alone, or for the breakdown alone. I can report {SUPPORTED}."
            )
    return None


def _match_list(matches: TechnicianMatches) -> str:
    names = [m.full_name for m in matches.matches]
    more = matches.total_matches - len(names)
    if more > 0:
        return ", ".join(names) + f" and {more} more"
    return ", ".join(names[:-1]) + f" and {names[-1]}"


def technician_reply(matches: TechnicianMatches) -> tuple[str, str] | None:
    """(error_code, text) when the name doesn't pick out one technician, else None."""
    if matches.total_matches == 0:
        return "technician_not_found", f"No technician matches {matches.name}."
    if matches.total_matches > 1:
        return (
            "technician_ambiguous",
            f"{matches.total_matches} technicians match {matches.name}: "
            f"{_match_list(matches)}. Please ask again with the full name.",
        )
    return None


def _account_list(matches: AccountMatches) -> str:
    names = [m.account_name for m in matches.matches]
    more = matches.total_matches - len(names)
    if more > 0:
        return ", ".join(names) + f" and {more} more"
    return ", ".join(names[:-1]) + f" and {names[-1]}"


def account_reply(matches: AccountMatches) -> tuple[str, str] | None:
    """(error_code, text) when the name doesn't pick out one account, else None (ADR-086)."""
    if matches.total_matches == 0:
        return "account_not_found", f"No account matches {matches.name}."
    if matches.total_matches > 1:
        return (
            "account_ambiguous",
            f"{matches.total_matches} accounts match {matches.name}: "
            f"{_account_list(matches)}. Please ask again with the full name.",
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
            if request.metric == "repeat_visit_drivers":
                arguments["by"] = request.group_by or "incident_type"
            elif request.group_by is not None:
                arguments["group_by"] = request.group_by

            if request.technician_name is not None:
                matches = await self._call(
                    updater,
                    task.id,
                    trace_id,
                    FIND_TECHNICIAN,
                    {"name": request.technician_name},
                    TechnicianMatches,
                )
                if matches is None:
                    return
                reply = technician_reply(matches)
                if reply is not None:
                    # The log gets the count and the ids, never the typed name or a display
                    # name; the answer text, which holds them, is unchanged.
                    await self._fail(
                        updater,
                        task.id,
                        *reply,
                        log_reason=False,
                        log_extra={
                            "total_matches": matches.total_matches,
                            "technician_ids": [m.technician_id for m in matches.matches],
                        },
                    )
                    return
                arguments["technician_id"] = matches.matches[0].technician_id

            if request.account_name is not None:
                found = await self._call(
                    updater,
                    task.id,
                    trace_id,
                    FIND_ACCOUNT,
                    {"name": request.account_name},
                    AccountMatches,
                )
                if found is None:
                    return
                reply = account_reply(found)
                if reply is not None:
                    # As for technicians: the log gets the count and the ids, never the name.
                    await self._fail(
                        updater,
                        task.id,
                        *reply,
                        log_reason=False,
                        log_extra={
                            "total_matches": found.total_matches,
                            "account_ids": [m.account_id for m in found.matches],
                        },
                    )
                    return
                arguments["account_id"] = found.matches[0].account_id
            if request.region is not None:
                arguments["region"] = request.region

            figures = await self._call(updater, task.id, trace_id, tool, arguments, result_model)
            if figures is None:
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

    async def _call(self, updater, task_id, trace_id, tool, arguments, result_model):
        """One MCP call; on failure, fail the task and return None."""
        try:
            return await call_tool(
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
                task_id,
                "tool_timeout",
                f"The incidents query timed out after {self.settings.mcp_timeout_s:g}s.",
            )
        except McpToolError as exc:
            if _TOOL_QUERY_FAILED in str(exc):
                await self._fail(updater, task_id, "tool_error", "The incidents query failed.")
            elif tool == FIND_ACCOUNT:
                # The name has characters no account name has (the tool rejects patterns).
                await self._fail(
                    updater,
                    task_id,
                    "account_not_found",
                    f"No account matches {arguments['name']}.",
                    log_reason=False,
                    log_extra={"total_matches": 0, "account_ids": [], "name_rejected": True},
                )
            elif tool == FIND_TECHNICIAN:
                # The name has characters no display name has (the tool rejects patterns).
                name = arguments["name"]
                await self._fail(
                    updater,
                    task_id,
                    "technician_not_found",
                    f"No technician matches {name}.",
                    log_reason=False,
                    log_extra={"total_matches": 0, "technician_ids": [], "name_rejected": True},
                )
            else:  # the tool rejected the range: its message is written for users
                await self._fail(
                    updater,
                    task_id,
                    "invalid_range",
                    f"That date range can't be answered: {exc}. "
                    f"Dates are resolved as of {self.settings.as_of.isoformat()}.",
                )
        except Exception:
            log.exception("MCP call failed", extra={"task_id": task_id, "tool": tool})
            await self._fail(
                updater, task_id, "tool_unavailable", "The incidents service is unavailable."
            )
        return None

    async def _fail(
        self,
        updater: TaskUpdater,
        task_id: str,
        code: str,
        reason: str,
        *,
        log_reason: bool = True,
        log_extra: dict | None = None,
    ) -> None:
        """End the task failed. `reason` is the user-facing text; it is logged only when it
        holds nothing from the question (`log_reason`), with `log_extra` standing in."""
        fields = {"task_id": task_id, "code": code} | (log_extra or {})
        if log_reason:
            fields["reason"] = reason
        log.warning("task failed", extra=fields)
        await updater.failed(
            updater.new_agent_message([new_text_part(reason)], metadata={"error_code": code})
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        # Tasks finish inside the blocking call that created them; nothing to cancel.
        raise NotImplementedError("cancellation is not supported")
