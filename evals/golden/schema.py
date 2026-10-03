"""The golden set v1 item contract (ADR-074).

`expected_behaviour` is the owner's vocabulary; `acceptable_outcomes` uses the
orchestrator's real `outcome` names, with the agent's error code where one applies, so a
Sprint 5 run can be scored mechanically on outcome and by review on `must`/`must_not`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Route = Literal["reporting", "sentiment", "forecast", "multi_domain", "out_of_scope"]
Behaviour = Literal["answer", "partial", "decline", "clarify", "no_match", "split", "withheld"]
Outcome = Literal["answered", "not_available", "split_required", "declined", "needs_clarification"]
ErrorCode = Literal["technician_not_found", "technician_ambiguous"]


class AcceptableOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome: Outcome
    error_code: ErrorCode | None = None
    route: Route | None = Field(default=None, description="Only with this route, if set.")


#: The mapping the owner set (2026-10-02): behaviour -> outcomes it may come back as.
BEHAVIOUR_OUTCOMES: dict[str, set[str]] = {
    "answer": {"answered"},
    "partial": {"answered", "not_available"},
    "withheld": {"answered", "not_available"},
    "decline": {"not_available", "declined"},
    "clarify": {"needs_clarification"},
    "no_match": {"needs_clarification"},
    "split": {"split_required"},
}


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^G\d{2}$")
    author: Literal["owner", "drafted"]
    question: str = Field(min_length=1)
    acceptable_routes: list[Route] = Field(min_length=1)
    expected_behaviour: Behaviour
    acceptable_outcomes: list[AcceptableOutcome] = Field(min_length=1)
    stretch: bool
    intent: str = Field(min_length=1)
    expected: dict
    must: list[str]
    must_not: list[str]
    oracle: str | None

    @model_validator(mode="after")
    def _consistent(self) -> Item:
        allowed = BEHAVIOUR_OUTCOMES[self.expected_behaviour]
        for o in self.acceptable_outcomes:
            if o.outcome not in allowed:
                raise ValueError(f"{self.id}: {o.outcome} doesn't fit {self.expected_behaviour}")
            if o.route is not None and o.route not in self.acceptable_routes:
                raise ValueError(f"{self.id}: outcome route {o.route} isn't an acceptable route")
        codes = {o.error_code for o in self.acceptable_outcomes}
        if self.expected_behaviour == "no_match" and codes != {"technician_not_found"}:
            raise ValueError(f"{self.id}: no_match is technician_not_found")
        if self.expected_behaviour == "clarify" and codes != {"technician_ambiguous"}:
            raise ValueError(f"{self.id}: clarify is technician_ambiguous")
        if self.expected_behaviour == "decline":
            for o in self.acceptable_outcomes:
                scope = self.acceptable_routes == ["out_of_scope"]
                if (o.outcome == "declined") != scope:
                    raise ValueError(
                        f"{self.id}: agent declines are not_available, out of scope declined"
                    )
        return self
