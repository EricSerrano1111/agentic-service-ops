"""Question parsing (ADR-046) and date resolution (ADR-050).

One LLM call maps the question to a `ReportingRequest`: an inclusive date range, or no
dates when the question states none. Code, not the model, then applies the default for
a dateless question: the calendar month before the as-of date's month. Figures stay
deterministic; only this step uses a model.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from typing import Protocol

from llm import LLMResult
from llm.prompts import Prompt, load_prompt
from schemas import DATASET_WINDOW_END, DATASET_WINDOW_START, ReportingRequest

log = logging.getLogger("agent_reporting")

PROMPT_NAME = "parse_v1"


class ParsingLLM(Protocol):
    async def generate(self, prompt: str, *, model=None, response_model=None, trace_id): ...


def load_parse_prompt() -> Prompt:
    return load_prompt("agent_reporting", PROMPT_NAME, __file__)


def previous_month(as_of: dt.date) -> tuple[dt.date, dt.date]:
    """The whole calendar month before `as_of`'s month (ADR-050's default range)."""
    end = as_of.replace(day=1) - dt.timedelta(days=1)
    return end.replace(day=1), end


@dataclass(frozen=True)
class Resolved:
    request: ReportingRequest  # as parsed
    start: dt.date
    end: dt.date
    assumed: bool


def resolve(request: ReportingRequest, as_of: dt.date) -> Resolved:
    if request.start is None or request.end is None:
        start, end = previous_month(as_of)
        return Resolved(request, start, end, assumed=True)
    return Resolved(request, request.start, request.end, assumed=False)


class Parser:
    def __init__(self, llm: ParsingLLM, as_of: dt.date, prompt: Prompt | None = None) -> None:
        self.llm = llm
        self.as_of = as_of
        self.prompt = prompt or load_parse_prompt()

    async def parse(self, question: str, *, trace_id: str | None) -> Resolved:
        result: LLMResult = await self.llm.generate(
            self.prompt.render(
                question=question,
                as_of=self.as_of.isoformat(),
                window_start=DATASET_WINDOW_START.isoformat(),
                window_end=DATASET_WINDOW_END.isoformat(),
            ),
            response_model=ReportingRequest,
            trace_id=trace_id,
        )
        resolved = resolve(result.parsed, self.as_of)
        log.info(
            "question parsed",
            extra={
                "parsed_start": _iso(result.parsed.start),
                "parsed_end": _iso(result.parsed.end),
                "start": resolved.start.isoformat(),
                "end": resolved.end.isoformat(),
                "range_assumed": resolved.assumed,
                "as_of": self.as_of.isoformat(),
                "prompt_version": self.prompt.version,
                "prompt_sha": self.prompt.sha,
                "model": result.model,
            },
        )
        return resolved


def _iso(d: dt.date | None) -> str | None:
    return None if d is None else d.isoformat()
