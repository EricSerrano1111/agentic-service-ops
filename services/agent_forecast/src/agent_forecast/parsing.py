"""Question parsing (ADR-046) and ADR-072's period rules.

One LLM call maps the question to a `ForecastRequest`. Code, not the model, then turns it
into forecast weeks:

- Forecasts cover future weeks only: the first is the Monday after the as-of date.
- A horizon of N weeks means the next N weeks.
- A period maps to the ISO weeks whose Monday falls inside it, keeping future weeks only.
  A period with no future Monday is in the past and is declined.
- Weeks past the 26-week cap are counted, not forecast.
- No period at all: next month (the calendar month after the as-of date's), stated as
  assumed. ADR-072 doesn't set this default; it mirrors ADR-050's.

The model reads the question only; it never sees a forecast figure.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from typing import Protocol

from llm import LLMResult
from llm.prompts import Prompt, load_prompt
from schemas import MAX_HORIZON_WEEKS, ForecastRequest

log = logging.getLogger("agent_forecast")

PROMPT_NAME = "parse_v1"


class ParsingLLM(Protocol):
    async def generate(self, prompt: str, *, model=None, response_model=None, trace_id): ...


def load_parse_prompt(name: str = PROMPT_NAME) -> Prompt:
    return load_prompt("agent_forecast", name, __file__)


def first_forecast_week(as_of: dt.date) -> dt.date:
    """The Monday after the as-of date: horizon 1."""
    return as_of + dt.timedelta(days=7 - as_of.weekday())


def next_month(as_of: dt.date) -> tuple[dt.date, dt.date]:
    start = (as_of.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
    end = (start + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)
    return start, end


def mondays(start: dt.date, end: dt.date) -> list[dt.date]:
    first = start + dt.timedelta(days=(7 - start.weekday()) % 7)
    out = []
    while first <= end:
        out.append(first)
        first += dt.timedelta(weeks=1)
    return out


@dataclass(frozen=True)
class Resolved:
    request: ForecastRequest
    assumed: bool
    past: bool
    #: Every requested week's Monday, within the horizon or beyond it.
    requested: tuple[dt.date, ...]
    #: Horizons (1..26) of the requested weeks inside the forecast horizon.
    horizons: tuple[int, ...]
    beyond: int


def resolve(request: ForecastRequest, as_of: dt.date) -> Resolved:
    first = first_forecast_week(as_of)
    assumed = False
    if request.horizon_weeks is not None:
        weeks = [first + dt.timedelta(weeks=i) for i in range(request.horizon_weeks)]
        past = False
    else:
        if request.period_start is None:
            start, end = next_month(as_of)
            assumed = True
        else:
            start, end = request.period_start, request.period_end
        weeks = [m for m in mondays(start, end) if m >= first]
        past = not weeks and end < first
    horizons = [(m - first).days // 7 + 1 for m in weeks]
    inside = tuple(h for h in horizons if h <= MAX_HORIZON_WEEKS)
    return Resolved(
        request=request,
        assumed=assumed,
        past=past,
        requested=tuple(weeks),
        horizons=inside,
        beyond=len(horizons) - len(inside),
    )


class Parser:
    def __init__(self, llm: ParsingLLM, as_of: dt.date, prompt: Prompt | None = None) -> None:
        self.llm = llm
        self.as_of = as_of
        self.prompt = prompt or load_parse_prompt()

    def render(self, question: str) -> str:
        return self.prompt.render(
            question=question,
            as_of=self.as_of.isoformat(),
            first_week=first_forecast_week(self.as_of).isoformat(),
        )

    async def parse_request(self, question: str, *, trace_id: str | None) -> ForecastRequest:
        """The model's reading of the question, before code applies any rule."""
        result: LLMResult = await self.llm.generate(
            self.render(question), response_model=ForecastRequest, trace_id=trace_id
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
