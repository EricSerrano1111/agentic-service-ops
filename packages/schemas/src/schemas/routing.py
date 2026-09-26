"""The orchestrator's routing decision: the structured output of its one LLM call."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Domain = Literal["reporting", "sentiment", "forecast"]
Route = Literal["reporting", "sentiment", "forecast", "multi_domain", "out_of_scope"]


class RouteDecision(BaseModel):
    """Where a question goes. No self-reported confidence: it is not calibrated, and the
    Sprint 3 routing eval measures accuracy instead.

    `domains` lists the domains the question touches: one for a single-domain route,
    two or more for `multi_domain` (ADR-032, named back to the user), none for
    `out_of_scope`.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    route: Route
    domains: list[Domain] = Field(default_factory=list)
    reason: str = Field(min_length=1, max_length=300, description="One short sentence.")

    @model_validator(mode="after")
    def _consistent(self) -> RouteDecision:
        distinct = set(self.domains)
        if self.route == "multi_domain" and len(distinct) < 2:
            raise ValueError("multi_domain needs at least two distinct domains")
        if self.route == "out_of_scope" and distinct:
            raise ValueError("out_of_scope takes no domains")
        if self.route in ("reporting", "sentiment", "forecast") and distinct - {self.route}:
            raise ValueError("a single-domain route lists only its own domain")
        return self
