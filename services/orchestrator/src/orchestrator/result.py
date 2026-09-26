"""Turning a finished A2A Task into the `/ask` response.

A2A data parts are protobuf `Value`s, which carry every number as a double: 344 arrives
as 344.0. Every data part is validated against its `packages/schemas` model on receipt
(architecture §11), which restores the integers and rejects anything that does not
match, so the orchestrator never passes on figures it has not checked the shape of.
"""

from __future__ import annotations

from a2a.types import Task, TaskState
from google.protobuf.json_format import MessageToDict
from pydantic import ValidationError
from schemas import ReportingAnswer


class TaskFailed(RuntimeError):
    """The agent's task did not complete. `error_code` is the agent's machine-readable
    reason from the status message metadata, when it gave one."""

    def __init__(self, task_id: str, state: str, reason: str, error_code: str | None) -> None:
        super().__init__(reason)
        self.task_id, self.state, self.reason, self.error_code = task_id, state, reason, error_code


def _status(task: Task) -> tuple[str, str | None]:
    if not task.status.HasField("message"):
        return "", None
    message = task.status.message
    text = " ".join(p.text for p in message.parts if p.HasField("text")).strip()
    code = (
        MessageToDict(message.metadata).get("error_code") if message.HasField("metadata") else None
    )
    return text, (str(code) if code else None)


def extract_answer(task: Task) -> tuple[str, ReportingAnswer]:
    """(answer text, validated answer) from a completed task; `TaskFailed` otherwise."""
    state = TaskState.Name(task.status.state)
    if task.status.state != TaskState.TASK_STATE_COMPLETED:
        text, code = _status(task)
        raise TaskFailed(task.id, state, text or f"task ended in {state}", code)

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
