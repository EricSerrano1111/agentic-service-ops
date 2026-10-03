"""The golden set item contract (ADR-074, ADR-075).

`expected_behaviour` is the owner's vocabulary; `acceptable_outcomes` uses the
orchestrator's real `outcome` names, so a Sprint 5 run can be scored mechanically on
outcome and by review on `must`/`must_not`.

v1 named a clarification's code as `error_code`, which the API never returned; v2 uses
`reason`, the field `AskResponse` returns for `needs_clarification` (ADR-075), and adds the
`ambiguous` route. v1's file is unchanged and still validates.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Route = Literal["reporting", "sentiment", "forecast", "multi_domain", "out_of_scope", "ambiguous"]
Behaviour = Literal["answer", "partial", "decline", "clarify", "no_match", "split", "withheld"]
Outcome = Literal["answered", "not_available", "split_required", "declined", "needs_clarification"]
ErrorCode = Literal["technician_not_found", "technician_ambiguous"]
Reason = Literal["technician_not_found", "technician_ambiguous", "intent_ambiguous"]


class AcceptableOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome: Outcome
    error_code: ErrorCode | None = Field(default=None, description="v1 only; see `reason`.")
    reason: Reason | None = Field(default=None, description="v2: AskResponse.reason.")
    route: Route | None = Field(default=None, description="Only with this route, if set.")

    @property
    def code(self) -> str | None:
        return self.reason or self.error_code

    @model_validator(mode="after")
    def _one_code_field(self) -> AcceptableOutcome:
        if self.error_code is not None and self.reason is not None:
            raise ValueError("give reason (v2) or error_code (v1), not both")
        if (self.reason is not None) and self.outcome != "needs_clarification":
            raise ValueError("reason is only for needs_clarification (ADR-075)")
        return self


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
        codes = {o.code for o in self.acceptable_outcomes}
        if self.expected_behaviour == "no_match" and codes != {"technician_not_found"}:
            raise ValueError(f"{self.id}: no_match is technician_not_found")
        if self.expected_behaviour == "clarify" and not (
            codes and codes <= {"technician_ambiguous", "intent_ambiguous"}
        ):
            raise ValueError(f"{self.id}: clarify is technician_ambiguous or intent_ambiguous")
        if self.expected_behaviour == "decline":
            for o in self.acceptable_outcomes:
                scope = self.acceptable_routes == ["out_of_scope"]
                if (o.outcome == "declined") != scope:
                    raise ValueError(
                        f"{self.id}: agent declines are not_available, out of scope declined"
                    )
        return self
