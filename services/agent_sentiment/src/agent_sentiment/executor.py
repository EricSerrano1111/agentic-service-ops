"""The sentiment agent's A2A executor: parse the question, query `mcp_feedback`, answer.

Mirrors `agent_reporting.executor`. Every task ends in a terminal state, completed or
failed, inside one `SendMessage` call (ADR-047). A failed task's status message carries
user-facing text plus an `error_code` in its metadata. An unsupported breakdown fails
with `not_supported` and a templated decline, before any MCP call (ADR-068).

The only LLM call is the parse, and it sees the question only. Comments returned by
`get_feedback_examples` go into the data part and the answer template, never to a model.
"""

from __future__ import annotations

import asyncio
import logging

from a2a.helpers.proto_helpers import new_data_part, new_task_from_user_message, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from common import (
    COST_KEY,
    TRACE_ID_KEY,
    Deadline,
    DeadlineExceeded,
    bind_deadline,
    bind_trace_id,
    clamp_to_deadline,
    current_cost_usd,
    track_request_cost,
    with_reviewer_note,
)
from google.protobuf.json_format import MessageToDict
from llm import (
    LLMDailyQuotaExhausted,
    LLMError,
    LLMOutputInvalid,
    LLMRateLimited,
    LLMRequestError,
)
from schemas import FeedbackExamples, SentimentAnswer, SentimentSummary

from .config import Settings
from .mcp_client import McpToolError, call_tool
from .parsing import Parser, ParsingLLM, Resolved
from .render import decline_message, render_answer
from .trend import negative_trend

log = logging.getLogger("agent_sentiment")

#: What a task failed for when the request's one deadline ran out (ADR-088).
TIME_LIMIT = "The time limit for this request was reached."
ARTIFACT_NAME = "sentiment_answer"
DATA_SCHEMA = "SentimentAnswer"
SUMMARY_TOOL = "get_sentiment_summary"
EXAMPLES_TOOL = "get_feedback_examples"
# The MCP server's own message when its query (not the caller's input) failed.
_TOOL_QUERY_FAILED = "feedback query failed"


def message_metadata(context: RequestContext) -> dict:
    """The message metadata as a dict, or {} when there is none or it cannot be read. Metadata
    is attacker-shaped input on a new service edge: a number protobuf cannot serialise (an
    infinity) must not crash the task, so it is treated as no metadata at all."""
    if context.message is None or not context.message.HasField("metadata"):
        return {}
    try:
        return MessageToDict(context.message.metadata)
    except Exception:
        log.warning("message metadata not readable; ignored")
        return {}


def deadline_of(context: RequestContext) -> Deadline:
    """The orchestrator's request deadline from the message metadata, never trusted: a missing
    or malformed one is replaced by this agent's own 120 s default, a far-future one is clamped
    (ADR-088)."""
    deadline = Deadline.from_metadata(message_metadata(context))
    if deadline.origin in ("malformed", "clamped"):
        log.warning("received deadline not trusted", extra={"origin": deadline.origin})
    return deadline


def cost_metadata(extra: dict | None = None) -> dict:
    """Response metadata carrying this service's list-price cost for the request (ADR-088)."""
    return (extra or {}) | {COST_KEY: round(current_cost_usd(), 6)}


def trace_id_of(context: RequestContext) -> str | None:
    """The orchestrator's trace id: message metadata first, then request metadata."""
    trace_id = message_metadata(context).get(TRACE_ID_KEY)
    if trace_id:
        return str(trace_id)
    trace_id = context.metadata.get(TRACE_ID_KEY)
    return str(trace_id) if trace_id else None


def _llm_failure(exc: LLMError) -> tuple[str, str]:
    """(error_code, user-facing text) for a parsing-call failure."""
    if isinstance(exc, LLMOutputInvalid):
        return (
            "unclear_question",
            "I couldn't read the question. Please rephrase it, for example: "
            "'How did customers in the West feel in July 2026?'",
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


def summary_arguments(resolved: Resolved) -> dict:
    args = {
        "start": resolved.start.isoformat(),
        "end": resolved.end.isoformat(),
        "bucket": resolved.bucket,
    }
    if resolved.request.region is not None:
        args["region"] = resolved.request.region
    return args


def examples_arguments(resolved: Resolved, limit: int) -> dict:
    args = {"start": resolved.start.isoformat(), "end": resolved.end.isoformat(), "limit": limit}
    if resolved.request.region is not None:
        args["region"] = resolved.request.region
    if resolved.request.example_label is not None:
        args["label"] = resolved.request.example_label
    return args


class SentimentExecutor(AgentExecutor):
    def __init__(self, settings: Settings, llm: ParsingLLM) -> None:
        self.settings = settings
        self.parser = Parser(llm, settings.as_of)

    async def _query(self, resolved: Resolved, trace_id: str | None):
        """Summary always; examples only when asked. Both inside one deadline."""
        async with asyncio.timeout(clamp_to_deadline(self.settings.mcp_timeout_s)):
            summary = await call_tool(
                self.settings.mcp_feedback_url,
                SUMMARY_TOOL,
                summary_arguments(resolved),
                SentimentSummary,
                trace_id=trace_id,
                timeout_s=self.settings.mcp_timeout_s,
            )
            examples = None
            if resolved.request.want_examples:
                examples = await call_tool(
                    self.settings.mcp_feedback_url,
                    EXAMPLES_TOOL,
                    examples_arguments(resolved, self.settings.examples_limit),
                    FeedbackExamples,
                    trace_id=trace_id,
                    timeout_s=self.settings.mcp_timeout_s,
                )
        return summary, examples

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        trace_id = trace_id_of(context)
        with (
            bind_trace_id(trace_id),
            bind_deadline(deadline_of(context)),
            track_request_cost(),
        ):
            task = context.current_task
            if task is None:
                task = new_task_from_user_message(context.message)
                await event_queue.enqueue_event(task)
            updater = TaskUpdater(event_queue, task.id, task.context_id)
            question = context.get_user_input()
            log.info("task received", extra={"task_id": task.id, "question_chars": len(question)})

            try:
                async with asyncio.timeout(clamp_to_deadline(self.settings.parse_timeout_s)):
                    # After QA's interpretation check failed, the question comes back with
                    # a reviewer note (untrusted, capped, never logged; ADR-089).
                    resolved = await self.parser.parse(
                        with_reviewer_note(question, message_metadata(context)),
                        trace_id=trace_id,
                    )
            except DeadlineExceeded:
                await self._fail(updater, task.id, "deadline_exceeded", TIME_LIMIT)
                return
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
            if request.unsupported is not None:
                await self._fail(
                    updater,
                    task.id,
                    "not_supported",
                    decline_message(request.unsupported),
                    parsed_request=request.model_dump(mode="json"),
                )
                return

            try:
                summary, examples = await self._query(resolved, trace_id)
            except DeadlineExceeded:
                await self._fail(updater, task.id, "deadline_exceeded", TIME_LIMIT)
                return
            except TimeoutError:
                await self._fail(
                    updater,
                    task.id,
                    "tool_timeout",
                    f"The feedback query timed out after {self.settings.mcp_timeout_s:g}s.",
                )
                return
            except McpToolError as exc:
                if _TOOL_QUERY_FAILED in str(exc):
                    await self._fail(updater, task.id, "tool_error", "The feedback query failed.")
                else:  # the tool rejected the input: its message is written for users
                    await self._fail(
                        updater,
                        task.id,
                        "invalid_range",
                        f"That question can't be answered: {exc}. "
                        f"Dates are resolved as of {self.settings.as_of.isoformat()}.",
                    )
                return
            except Exception:
                log.exception("MCP call failed", extra={"task_id": task.id})
                await self._fail(
                    updater, task.id, "tool_unavailable", "The feedback service is unavailable."
                )
                return

            quoted = list(examples.examples[: self.settings.examples_limit]) if examples else []
            answer = SentimentAnswer(
                request=request,
                start=resolved.start,
                end=resolved.end,
                range_assumed=resolved.assumed,
                as_of=self.settings.as_of,
                summary=summary,
                trend=negative_trend(summary) if request.want_trend else None,
                examples=quoted,
                quoted_feedback_ids=[e.feedback_id for e in quoted],
            )
            await updater.add_artifact(
                [
                    new_text_part(render_answer(answer), media_type="text/plain"),
                    new_data_part(answer.model_dump(mode="json"), media_type="application/json"),
                ],
                name=ARTIFACT_NAME,
                metadata=cost_metadata({"schema": DATA_SCHEMA}),
            )
            await updater.complete()
            log.info(
                "task completed",
                extra={
                    "task_id": task.id,
                    "n_comments": summary.n_comments,
                    "n_scored": summary.n_scored,
                    "complete": summary.complete,
                    "trend": answer.trend.verdict if answer.trend else None,
                    "quoted": len(quoted),
                },
            )

    async def _fail(
        self,
        updater: TaskUpdater,
        task_id: str,
        code: str,
        reason: str,
        parsed_request: dict | None = None,
    ) -> None:
        log.warning("task failed", extra={"task_id": task_id, "code": code, "reason": reason})
        # A decline also carries how the question was read, for QA (ADR-090); not logged.
        await updater.failed(
            updater.new_agent_message(
                [new_text_part(reason)],
                metadata=cost_metadata(
                    {"error_code": code}
                    | ({} if parsed_request is None else {"parsed_request": parsed_request})
                ),
            )
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        # Tasks finish inside the blocking call that created them; nothing to cancel.
        raise NotImplementedError("cancellation is not supported")
