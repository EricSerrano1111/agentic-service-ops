"""The QA agent's A2A executor: read one `VerificationRequest`, run the checks, return a
`Verdict` (ADR-087, ADR-089).

Every task ends in a terminal state inside one `SendMessage` call (ADR-047). A completed task
carries the verdict, whether it passes or fails: a failed check is an answer, not an error. A
failed task means QA could not decide, and the orchestrator treats it as QA being unavailable
(it never returns the answer as verified). The failure codes are `bad_request` (the input did
not parse), `deadline_exceeded`, `qa_timeout`, `interpretation_unavailable` (the language-model
call failed or was refused) and `qa_unavailable` (the database).

The message is attacker-shaped input on a new service edge: metadata that protobuf cannot
serialise is ignored, the payload is size-capped and validated before anything runs, and no
exception text or input value is returned or logged.
"""

from __future__ import annotations

import asyncio
import json
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
)
from google.protobuf.json_format import MessageToDict
from llm import LLMError
from pydantic import ValidationError
from schemas import Verdict, VerificationRequest

from .config import Settings
from .verify import Verifier

log = logging.getLogger("agent_qa")

TIME_LIMIT = "The time limit for this request was reached."
ARTIFACT_NAME = "qa_verdict"
DATA_SCHEMA = "Verdict"
#: The largest request payload read (a 25-group answer is a few tens of KB).
MAX_PAYLOAD_BYTES = 200_000


def message_metadata(context: RequestContext) -> dict:
    """The message metadata as a dict, or {} when there is none or it cannot be read."""
    if context.message is None or not context.message.HasField("metadata"):
        return {}
    try:
        return MessageToDict(context.message.metadata)
    except Exception:
        log.warning("message metadata not readable; ignored")
        return {}


def deadline_of(context: RequestContext) -> Deadline:
    """The orchestrator's request deadline, never trusted: a missing or malformed one is
    replaced by this agent's own 120 s default, a far-future one is clamped (ADR-088)."""
    deadline = Deadline.from_metadata(message_metadata(context))
    if deadline.origin in ("malformed", "clamped"):
        log.warning("received deadline not trusted", extra={"origin": deadline.origin})
    return deadline


def cost_metadata(extra: dict | None = None) -> dict:
    return (extra or {}) | {COST_KEY: round(current_cost_usd(), 6)}


def trace_id_of(context: RequestContext) -> str | None:
    trace_id = message_metadata(context).get(TRACE_ID_KEY)
    if trace_id:
        return str(trace_id)
    trace_id = context.metadata.get(TRACE_ID_KEY)
    return str(trace_id) if trace_id else None


def read_request(context: RequestContext) -> VerificationRequest | None:
    """The one data part as a validated request, or None for anything else."""
    if context.message is None:
        return None
    parts = [p for p in context.message.parts if p.HasField("data")]
    if len(parts) != 1:
        return None
    try:
        data = MessageToDict(parts[0].data)
        if len(json.dumps(data)) > MAX_PAYLOAD_BYTES:
            return None
        return VerificationRequest.model_validate(data)
    except (ValidationError, ValueError, TypeError):
        return None
    except Exception:
        return None


def summary_text(verdict: Verdict) -> str:
    if verdict.verdict == "pass":
        return f"Verified: {len(verdict.checks)} checks passed."
    return "Failed checks: " + ", ".join(c.code for c in verdict.failed) + "."


class QAExecutor(AgentExecutor):
    def __init__(self, settings: Settings, verifier: Verifier) -> None:
        self.settings = settings
        self.verifier = verifier

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
            request = read_request(context)
            if request is None:
                await self._fail(updater, task.id, "bad_request", "The request was not understood.")
                return
            log.info(
                "task received",
                extra={"task_id": task.id, "domain": request.domain, "kind": request.kind},
            )
            try:
                async with asyncio.timeout(clamp_to_deadline(self.settings.verify_timeout_s)):
                    verdict = await self.verifier.verify(request, trace_id=trace_id)
            except DeadlineExceeded:
                await self._fail(updater, task.id, "deadline_exceeded", TIME_LIMIT)
                return
            except TimeoutError:
                await self._fail(updater, task.id, "qa_timeout", "Verification timed out.")
                return
            except LLMError as exc:
                log.warning("interpretation call failed", extra={"llm_error": type(exc).__name__})
                await self._fail(
                    updater,
                    task.id,
                    "interpretation_unavailable",
                    "The interpretation check could not run.",
                )
                return
            except Exception:
                log.exception("verification failed", extra={"task_id": task.id})
                await self._fail(updater, task.id, "qa_unavailable", "Verification is unavailable.")
                return

            await updater.add_artifact(
                [
                    new_text_part(summary_text(verdict), media_type="text/plain"),
                    new_data_part(verdict.model_dump(mode="json"), media_type="application/json"),
                ],
                name=ARTIFACT_NAME,
                metadata=cost_metadata({"schema": DATA_SCHEMA}),
            )
            await updater.complete()
            log.info(
                "task completed",
                extra={
                    "task_id": task.id,
                    "verdict": verdict.verdict,
                    "failed_checks": [c.code for c in verdict.failed],
                },
            )

    async def _fail(self, updater: TaskUpdater, task_id: str, code: str, reason: str) -> None:
        log.warning("task failed", extra={"task_id": task_id, "code": code})
        await updater.failed(
            updater.new_agent_message(
                [new_text_part(reason)], metadata=cost_metadata({"error_code": code})
            )
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("cancellation is not supported")
