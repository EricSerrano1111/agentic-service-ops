"""Turning a finished A2A Task into the `/ask` response.

A2A data parts are protobuf `Value`s, which carry every number as a double: 344 arrives
as 344.0. Validating the data part against the shared contract (`schemas`) restores the
integers and rejects anything that does not match, so the orchestrator never passes on
figures it has not checked the shape of.
"""

from __future__ import annotations

from a2a.types import Task, TaskState
from google.protobuf.json_format import MessageToDict
from pydantic import ValidationError
from schemas import IncidentSummary


class TaskFailed(RuntimeError):
    def __init__(self, task_id: str, state: str, reason: str) -> None:
        super().__init__(reason)
        self.task_id, self.state, self.reason = task_id, state, reason


def _status_text(task: Task) -> str:
    if not task.status.HasField("message"):
        return ""
    return " ".join(p.text for p in task.status.message.parts if p.HasField("text")).strip()


def extract_answer(task: Task) -> tuple[str, dict]:
    """(answer text, figures) from a completed task; raises `TaskFailed` otherwise."""
    state = TaskState.Name(task.status.state)
    if task.status.state != TaskState.TASK_STATE_COMPLETED:
        raise TaskFailed(task.id, state, _status_text(task) or f"task ended in {state}")

    texts: list[str] = []
    data: list[dict] = []
    for artifact in task.artifacts:
        for part in artifact.parts:
            if part.HasField("text"):
                texts.append(part.text)
            elif part.HasField("data"):
                data.append(MessageToDict(part.data))
    if not texts or len(data) != 1:
        raise TaskFailed(task.id, state, "completed task is missing its text or data part")
    try:
        # Route is hardcoded to the reporting agent, so its contract is known here.
        figures = IncidentSummary.model_validate(data[0]).model_dump(mode="json")
    except ValidationError as exc:
        raise TaskFailed(task.id, state, f"figures failed validation: {exc}") from None
    return "\n".join(texts), figures
