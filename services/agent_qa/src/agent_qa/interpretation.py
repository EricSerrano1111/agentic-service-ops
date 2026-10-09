"""The interpretation check (ADR-087, ADR-089): does the specialist's reading of the question
match the question? The one language-model call in QA.

Containment (the question is untrusted text): the call has no tools and its output is
schema-constrained to a boolean, a list drawn from a closed set of field names and one short
note, so at worst an injected question can flip this check's verdict. It cannot make QA run a
query, skip a deterministic check or change a figure, and the deterministic checks run whatever
this returns. The note is cleaned and capped before it leaves QA (the orchestrator treats it as
untrusted again).

The same `reading_*` functions build the model's input in production and in the gate
(`evals/qa_interp/`), so what the gate measures is what ships.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
from typing import Any, Literal, Protocol

from llm import LLMResult
from llm.prompts import Prompt, load_prompt
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from schemas import MAX_GUIDANCE_CHARS, ForecastRequest, ReportingRequest

log = logging.getLogger("agent_qa")

PROMPT_NAME = "qa_interp_v1"
CHECK_CODE = "interpretation_matches_question"

DiffField = Literal[
    "metric",
    "breakdown",
    "dates",
    "technician",
    "region",
    "account",
    "slice",
    "horizon",
    "history",
    "unsupported",
]


class Judgement(BaseModel):
    """The model's whole output. Key order is the prompt template's (L-51)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    faithful: StrictBool
    differs_in: list[DiffField] = Field(default_factory=list, max_length=10)
    note: str = Field(default="", max_length=MAX_GUIDANCE_CHARS)


class InterpretationLLM(Protocol):
    async def generate(self, prompt: str, *, model=None, response_model=None, trace_id): ...


def load_interp_prompt(name: str = PROMPT_NAME) -> Prompt:
    return load_prompt("agent_qa", name, __file__)


def reading_reporting(
    request: ReportingRequest,
    start: dt.date | None,
    end: dt.date | None,
    assumed: bool,
    as_of: dt.date,
) -> str:
    """The reporting reading the model judges: the parsed request and the dates it ended up
    with. `start`/`end` are None for a decline that never resolved a range."""
    if start is None:
        date_range: Any = None
    elif assumed:
        date_range = {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "source": "none named in the question; the last full calendar month before as_of",
        }
    else:
        date_range = {"start": start.isoformat(), "end": end.isoformat(), "source": "named"}
    reading = {
        "metric": request.metric,
        "breakdown": request.group_by,
        "technician_name": request.technician_name,
        "region": request.region,
        "account_name": request.account_name,
        "date_range": date_range,
        "as_of": as_of.isoformat(),
    }
    return json.dumps(reading, indent=1)


def reading_forecast(request: ForecastRequest, as_of: dt.date) -> str:
    period: Any = None
    if request.period_start is not None:
        period = {"start": request.period_start.isoformat(), "end": request.period_end.isoformat()}
    reading = {
        "slice": request.slice,
        "horizon_weeks": request.horizon_weeks,
        "period": period,
        "none_named": request.horizon_weeks is None and request.period_start is None,
        "show_recent_history": request.want_history,
        "unsupported": request.unsupported,
        "as_of": as_of.isoformat(),
    }
    return json.dumps(reading, indent=1)


_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")


def clean_note(note: str) -> str:
    """A reviewer note safe to hand on: one line, no control characters, capped."""
    return " ".join(_CONTROL.sub(" ", note).split())[:MAX_GUIDANCE_CHARS]


GENERIC_GUIDANCE = "Re-read the question: the previous reading did not match what it asks for."


class Interpreter:
    def __init__(self, llm: InterpretationLLM, prompt: Prompt | None = None) -> None:
        self.llm = llm
        self.prompt = prompt or load_interp_prompt()

    def render(self, domain: str, question: str, reading: str) -> str:
        return self.prompt.render(domain=domain, question=question, reading=reading)

    async def judge(
        self, domain: str, question: str, reading: str, *, trace_id: str | None
    ) -> Judgement:
        result: LLMResult = await self.llm.generate(
            self.render(domain, question, reading),
            response_model=Judgement,
            trace_id=trace_id,
        )
        judgement: Judgement = result.parsed
        log.info(
            "interpretation judged",
            extra={
                "domain": domain,
                "faithful": judgement.faithful,
                "differs_in": list(judgement.differs_in),
                "prompt_version": self.prompt.version,
                "prompt_sha": self.prompt.sha,
                "model": result.model,
            },
        )
        return judgement


def guidance_for(judgement: Judgement) -> str:
    note = clean_note(judgement.note)
    if note:
        return note
    if judgement.differs_in:
        return f"The previous reading was wrong in: {', '.join(judgement.differs_in)}."[
            :MAX_GUIDANCE_CHARS
        ]
    return GENERIC_GUIDANCE


__all__ = [
    "CHECK_CODE",
    "Interpreter",
    "Judgement",
    "clean_note",
    "guidance_for",
    "load_interp_prompt",
    "reading_forecast",
    "reading_reporting",
]
