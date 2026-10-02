"""Question parsing (ADR-046, ADR-068) and date resolution (ADR-050, ADR-068).

One LLM call maps the question to a `SentimentRequest`. Code, not the model, applies the
range when the question names none: for a trend question, the six calendar months ending
at the as-of date's month, in monthly buckets; otherwise ADR-050's previous calendar
month. Figures stay deterministic; only this step uses a model, and it sees the question
only, never a customer comment.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from typing import Protocol

from llm import LLMResult
from llm.prompts import Prompt, load_prompt
from schemas import DATASET_WINDOW_END, DATASET_WINDOW_START, SentimentRequest

log = logging.getLogger("agent_sentiment")

PROMPT_NAME = "parse_v1"
TREND_DEFAULT_MONTHS = 6


class ParsingLLM(Protocol):
    async def generate(self, prompt: str, *, model=None, response_model=None, trace_id): ...


def load_parse_prompt(name: str = PROMPT_NAME) -> Prompt:
    return load_prompt("agent_sentiment", name, __file__)


def previous_month(as_of: dt.date) -> tuple[dt.date, dt.date]:
    """The whole calendar month before `as_of`'s month (ADR-050's default range)."""
    end = as_of.replace(day=1) - dt.timedelta(days=1)
    return end.replace(day=1), end


def trend_default(as_of: dt.date, months: int = TREND_DEFAULT_MONTHS) -> tuple[dt.date, dt.date]:
    """The `months` calendar months ending at `as_of`'s month, through `as_of` (ADR-068)."""
    index = as_of.year * 12 + (as_of.month - 1) - (months - 1)
    return dt.date(index // 12, index % 12 + 1, 1), as_of


@dataclass(frozen=True)
class Resolved:
    request: SentimentRequest  # as parsed
    start: dt.date
    end: dt.date
    bucket: str
    assumed: bool


def resolve(request: SentimentRequest, as_of: dt.date) -> Resolved:
    if request.start is not None and request.end is not None:
        return Resolved(request, request.start, request.end, request.bucket, assumed=False)
    if request.want_trend:
        start, end = trend_default(as_of)
        return Resolved(request, start, end, "month", assumed=True)
    start, end = previous_month(as_of)
    return Resolved(request, start, end, request.bucket, assumed=True)


class Parser:
    def __init__(self, llm: ParsingLLM, as_of: dt.date, prompt: Prompt | None = None) -> None:
        self.llm = llm
        self.as_of = as_of
        self.prompt = prompt or load_parse_prompt()

    def render(self, question: str) -> str:
        return self.prompt.render(
            question=question,
            as_of=self.as_of.isoformat(),
            window_start=DATASET_WINDOW_START.isoformat(),
            window_end=DATASET_WINDOW_END.isoformat(),
        )

    async def parse_request(self, question: str, *, trace_id: str | None) -> SentimentRequest:
        """The model's reading of the question, before any default is applied."""
        result: LLMResult = await self.llm.generate(
            self.render(question), response_model=SentimentRequest, trace_id=trace_id
        )
        log.info(
            "question parsed",
            extra={
                **result.parsed.model_dump(mode="json"),
                "prompt_version": self.prompt.version,
                "prompt_sha": self.prompt.sha,
                "model": result.model,
            },
        )
        return result.parsed

    async def parse(self, question: str, *, trace_id: str | None) -> Resolved:
        return resolve(await self.parse_request(question, trace_id=trace_id), self.as_of)
