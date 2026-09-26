"""Question routing: one LLM call per question, into a validated `RouteDecision`.

The decision is logged with the prompt's version and content hash, so any routing result
can be traced to the exact prompt text that produced it. Errors from the call propagate
as `llm` errors for the API layer to map. An unparseable decision is never defaulted to
a route.
"""

from __future__ import annotations

import logging
from typing import Protocol

from llm import LLMResult
from llm.prompts import Prompt, load_prompt
from schemas import Domain, RouteDecision

log = logging.getLogger("orchestrator")

PROMPT_NAME = "route_v1"

DOMAIN_LABELS: dict[Domain, str] = {
    "reporting": "incident and quality reporting",
    "sentiment": "customer feedback sentiment",
    "forecast": "service request volume forecasting",
}


class RoutingLLM(Protocol):
    async def generate(self, prompt: str, *, model=None, response_model=None, trace_id): ...


def load_route_prompt() -> Prompt:
    return load_prompt("orchestrator", PROMPT_NAME, __file__)


class Router:
    def __init__(
        self, llm: RoutingLLM, prompt: Prompt | None = None, model: str | None = None
    ) -> None:
        self.llm = llm
        self.prompt = prompt or load_route_prompt()
        self.model = model  # None: the client's configured orchestrator model

    async def classify(self, question: str, *, trace_id: str) -> RouteDecision:
        result: LLMResult = await self.llm.generate(
            self.prompt.render(question=question),
            model=self.model,
            response_model=RouteDecision,
            trace_id=trace_id,
        )
        decision = result.parsed
        log.info(
            "route decision",
            extra={
                "route": decision.route,
                "domains": list(decision.domains),
                "reason": decision.reason,
                "prompt_version": self.prompt.version,
                "prompt_sha": self.prompt.sha,
                "model": result.model,
            },
        )
        return decision


def _join(labels: list[str]) -> str:
    return labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + " and " + labels[-1]


def not_available_message(decision: RouteDecision) -> str:
    label = DOMAIN_LABELS[decision.route]  # type: ignore[index]
    return (
        f"Questions about {label} aren't supported yet. Right now I can answer questions "
        "about incidents and quality metrics over a date range."
    )


def out_of_scope_message() -> str:
    return (
        "Sorry, that's outside what I can help with. I answer questions about this "
        "field-service operation's records: incidents and quality metrics today, with "
        "customer sentiment and request-volume forecasts to follow."
    )


def split_message(decision: RouteDecision) -> str:
    """ADR-032: name the domains detected and ask for one question per domain."""
    labels = [DOMAIN_LABELS[d] for d in dict.fromkeys(decision.domains)]
    return (
        f"Your question covers more than one area: {_join(labels)}. I answer one area per "
        "question, so please ask about each separately."
    )
