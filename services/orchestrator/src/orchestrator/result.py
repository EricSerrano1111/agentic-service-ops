"""Turning a finished A2A Task into the `/ask` response.

A2A data parts are protobuf `Value`s, which carry every number as a double: 344 arrives
as 344.0. Every data part is validated against its `packages/schemas` model on receipt
(architecture §11), which restores the integers and rejects anything that does not
match, so the orchestrator never passes on figures it has not checked the shape of.
"""

from __future__ import annotations

import logging

from a2a.types import Task, TaskState
from common import COST_KEY, parse_cost_usd
from google.protobuf.json_format import MessageToDict
from pydantic import ValidationError
from schemas import ForecastAnswer, ReportingAnswer, SentimentAnswer, Verdict

log = logging.getLogger("orchestrator")


class TaskFailed(RuntimeError):
    """The agent's task did not complete. `error_code` is the agent's machine-readable
    reason from the status message metadata, when it gave one."""

    def __init__(
        self,
        task_id: str,
        state: str,
        reason: str,
        error_code: str | None,
        parsed_request: dict | None = None,
    ) -> None:
        super().__init__(reason)
        self.task_id, self.state, self.reason, self.error_code = task_id, state, reason, error_code
        #: How the specialist read the question, for a decline (QA verifies it); else None.
        self.parsed_request = parsed_request


def _status(task: Task) -> tuple[str, str | None]:
    if not task.status.HasField("message"):
        return "", None
    message = task.status.message
    text = " ".join(p.text for p in message.parts if p.HasField("text")).strip()
    code = (
        MessageToDict(message.metadata).get("error_code") if message.HasField("metadata") else None
    )
    return text, (str(code) if code else None)


def _parsed_request(task: Task) -> dict | None:
    """The `parsed_request` a declining specialist put in its status metadata, if it is a
    JSON object. Untrusted: it is only ever passed on to QA, which validates it."""
    if not (task.status.HasField("message") and task.status.message.HasField("metadata")):
        return None
    try:
        value = MessageToDict(task.status.message.metadata).get("parsed_request")
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def failure_code(task: Task) -> str | None:
    """The `error_code` of a failed task, or None."""
    if task.status.state == TaskState.TASK_STATE_COMPLETED:
        return None
    return _status(task)[1]


def extract_cost(task: Task) -> float | None:
    """The service's list-price cost for this request, from A2A response metadata (ADR-088):
    an artifact's metadata for a completed task, the status message's for a failed one. A
    missing cost is None; a malformed or negative one is rejected and ignored (it could be
    used to keep a runaway request under the cap)."""
    found = None
    structs = [a.metadata for a in task.artifacts if a.HasField("metadata")]
    if task.status.HasField("message") and task.status.message.HasField("metadata"):
        structs.append(task.status.message.metadata)
    metadata = []
    for struct in structs:
        try:
            metadata.append(MessageToDict(struct))
        except Exception:  # e.g. an infinite number, which protobuf cannot serialise
            log.warning("ignored unreadable response metadata from a service")
    for md in metadata:
        if COST_KEY in md:
            cost = parse_cost_usd(md[COST_KEY])
            if cost is None:
                log.warning("ignored a malformed cost_usd from a service")
                continue
            found = (found or 0.0) + cost
    return found


def extract_answer(task: Task) -> tuple[str, ReportingAnswer]:
    """(answer text, validated answer) from a completed task; `TaskFailed` otherwise."""
    state = TaskState.Name(task.status.state)
    if task.status.state != TaskState.TASK_STATE_COMPLETED:
        text, code = _status(task)
        raise TaskFailed(
            task.id, state, text or f"task ended in {state}", code, _parsed_request(task)
        )

    texts: list[str] = []
    data: list[dict] = []
    for artifact in task.artifacts:
        for part in artifact.parts:
            if part.HasField("text"):
                texts.append(part.text)
            elif part.HasField("data"):
                data.append(MessageToDict(part.data))
    if not texts or len(data) != 1:
        raise TaskFailed(task.id, state, "completed task is missing its text or data part", None)
    try:
        # Only the reporting agent is routed to today, so its contract is known here.
        answer = ReportingAnswer.model_validate(data[0])
    except ValidationError as exc:
        raise TaskFailed(
            task.id, state, f"answer failed validation: {exc.error_count()} error(s)", None
        ) from None
    return "\n".join(texts), answer


def extract_sentiment_answer(task: Task) -> tuple[str, SentimentAnswer]:
    """(answer text, validated answer) from the sentiment agent's completed task.

    The sentiment agent's contract (ADR-068); `TaskFailed` otherwise, as for reporting.
    """
    state = TaskState.Name(task.status.state)
    if task.status.state != TaskState.TASK_STATE_COMPLETED:
        text, code = _status(task)
        raise TaskFailed(
            task.id, state, text or f"task ended in {state}", code, _parsed_request(task)
        )

    texts: list[str] = []
    data: list[dict] = []
    for artifact in task.artifacts:
        for part in artifact.parts:
            if part.HasField("text"):
                texts.append(part.text)
            elif part.HasField("data"):
                data.append(MessageToDict(part.data))
    if not texts or len(data) != 1:
        raise TaskFailed(task.id, state, "completed task is missing its text or data part", None)
    try:
        answer = SentimentAnswer.model_validate(data[0])
    except ValidationError as exc:
        raise TaskFailed(
            task.id, state, f"answer failed validation: {exc.error_count()} error(s)", None
        ) from None
    return "\n".join(texts), answer


def extract_forecast_answer(task: Task) -> tuple[str, ForecastAnswer]:
    """(answer text, validated answer) from the forecast agent's completed task (ADR-072).

    `ForecastAnswer` rejects a payload carrying numbers for an unserved week, so the
    orchestrator never passes one on, whatever the agent sent.
    """
    state = TaskState.Name(task.status.state)
    if task.status.state != TaskState.TASK_STATE_COMPLETED:
        text, code = _status(task)
        raise TaskFailed(
            task.id, state, text or f"task ended in {state}", code, _parsed_request(task)
        )

    texts: list[str] = []
    data: list[dict] = []
    for artifact in task.artifacts:
        for part in artifact.parts:
            if part.HasField("text"):
                texts.append(part.text)
            elif part.HasField("data"):
                data.append(MessageToDict(part.data))
    if not texts or len(data) != 1:
        raise TaskFailed(task.id, state, "completed task is missing its text or data part", None)
    try:
        answer = ForecastAnswer.model_validate(data[0])
    except ValidationError as exc:
        raise TaskFailed(
            task.id, state, f"answer failed validation: {exc.error_count()} error(s)", None
        ) from None
    return "\n".join(texts), answer


def extract_verdict(task: Task) -> Verdict:
    """The QA agent's verdict from its completed task (ADR-089). A task that did not complete,
    or whose payload is not a valid verdict, is `TaskFailed`: the orchestrator then treats QA
    as unavailable and never returns the answer as verified."""
    state = TaskState.Name(task.status.state)
    if task.status.state != TaskState.TASK_STATE_COMPLETED:
        text, code = _status(task)
        raise TaskFailed(task.id, state, text or f"task ended in {state}", code)
    data = [
        MessageToDict(part.data)
        for artifact in task.artifacts
        for part in artifact.parts
        if part.HasField("data")
    ]
    if len(data) != 1:
        raise TaskFailed(task.id, state, "completed task is missing its verdict", None)
    try:
        return Verdict.model_validate(data[0])
    except ValidationError:
        raise TaskFailed(task.id, state, "verdict failed validation", None) from None
