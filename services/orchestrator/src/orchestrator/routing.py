"""Question routing: one LLM call per question, into a validated `RouteDecision`.

The decision is logged with the prompt's version and content hash, so any routing result
can be traced to the exact prompt text that produced it. Errors from the call propagate
as `llm` errors for the API layer to map. An unparseable decision is never defaulted to
a route.

An `ambiguous` decision (ADR-075) is answered with `clarification_message`: what each
candidate domain answers, with an example rephrasing. Candidate values dropped during
validation are each logged with the trace ID.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Protocol

from common import bind_trace_id
from llm import LLMResult
from llm.prompts import Prompt, load_prompt
from schemas import DATASET_WINDOW_END, Domain, RouteDecision

log = logging.getLogger("orchestrator")

PROMPT_NAME = "route_v5"

DOMAIN_LABELS: dict[Domain, str] = {
    "reporting": "incident and quality reporting",
    "sentiment": "customer feedback sentiment",
    "forecast": "operational forecasts (volumes, SLA outlook)",
}


class RoutingLLM(Protocol):
    async def generate(self, prompt: str, *, model=None, response_model=None, trace_id): ...


def load_route_prompt() -> Prompt:
    return load_prompt("orchestrator", PROMPT_NAME, __file__)


class Router:
    def __init__(
        self,
        llm: RoutingLLM,
        prompt: Prompt | None = None,
        model: str | None = None,
        as_of: dt.date = DATASET_WINDOW_END,
    ) -> None:
        self.llm = llm
        self.prompt = prompt or load_route_prompt()
        self.model = model  # None: the client's configured orchestrator model
        self.as_of = as_of  # the reporting agent's as-of date (ADR-050, ADR-054)

    def render(self, question: str) -> str:
        values = {"question": question}
        if "{{as_of}}" in self.prompt.text:  # route_v3 on; route_v1 and v2 carry no date
            values["as_of"] = self.as_of.isoformat()
        return self.prompt.render(**values)

    async def classify(self, question: str, *, trace_id: str) -> RouteDecision:
        result: LLMResult = await self.llm.generate(
            self.render(question),
            model=self.model,
            response_model=RouteDecision,
            trace_id=trace_id,
        )
        decision = result.parsed
        with bind_trace_id(trace_id):
            for value in decision.dropped_candidates:
                log.warning(
                    "route candidate dropped",
                    extra={"route": decision.route, "candidate": value[:50]},
                )
        log.info(
            "route decision",
            extra={
                "route": decision.route,
                "domains": list(decision.domains),
                "candidates": list(decision.candidates),
                "reason": decision.reason,
                "prompt_version": self.prompt.version,
                "prompt_sha": self.prompt.sha,
                "model": result.model,
            },
        )
        return decision


def _join(labels: list[str]) -> str:
    return labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + " and " + labels[-1]


def out_of_scope_message() -> str:
    return (
        "Sorry, that's outside what I can help with. I answer questions about this "
        "field-service operation's records: incident and quality reporting, customer "
        "sentiment, and request-volume forecasts."
    )


#: ADR-075: what each domain answers, and one example rephrasing for it.
CLARIFY_OPTIONS: dict[Domain, tuple[str, str]] = {
    "reporting": (
        "Incident and quality reporting: counts and rates from the operation's records, "
        "such as incidents, SLA compliance and first-time fix rate.",
        "What was our SLA compliance in the Southeast last month?",
    ),
    "sentiment": (
        "Customer feedback sentiment: how customers feel, from the words in their "
        "post-visit feedback.",
        "How did customers in the Southeast feel last month?",
    ),
    "forecast": (
        "Request-volume forecasts: how many service requests to expect in the coming weeks.",
        "How many requests should we expect next month?",
    ),
}


def clarification_message(decision: RouteDecision) -> str:
    """ADR-075: the question could mean several things; say what each candidate answers,
    with an example. Fewer than two valid candidates: list all three domains."""
    candidates = list(decision.candidates)
    if len(candidates) < 2:
        candidates = list(CLARIFY_OPTIONS)
    lines = [
        "Your question could mean different things, and each would get a different "
        "answer. Please ask again, naming what you'd like measured:"
    ]
    for domain in candidates:
        what, example = CLARIFY_OPTIONS[domain]
        lines.append(f'- {what} For example: "{example}"')
    return "\n".join(lines)


def split_message(decision: RouteDecision) -> str:
    """ADR-032: name the domains detected and ask for one question per domain."""
    labels = [DOMAIN_LABELS[d] for d in dict.fromkeys(decision.domains)]
    return (
        f"Your question covers more than one area: {_join(labels)}. I answer one area per "
        "question, so please ask about each separately."
    )
