"""The orchestrator's routing decision: the structured output of its one LLM call."""

from __future__ import annotations

from typing import Annotated, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, WithJsonSchema, model_validator

Domain = Literal["reporting", "sentiment", "forecast"]
Route = Literal["reporting", "sentiment", "forecast", "multi_domain", "out_of_scope", "ambiguous"]
DOMAINS: tuple[str, ...] = get_args(Domain)

#: Candidates are validated leniently (ADR-075): the JSON schema the model sees still
#: restricts them to the three domains, but an invalid or repeated value is dropped and
#: recorded in `dropped_candidates` rather than failing the whole routing call.
Candidates = Annotated[
    list[str],
    WithJsonSchema({"type": "array", "items": {"type": "string", "enum": list(DOMAINS)}}),
]


class RouteDecision(BaseModel):
    """Where a question goes. No self-reported confidence: it is not calibrated, and the
    routing eval measures accuracy instead.

    `domains` lists the domains the question touches: one for a single-domain route,
    two or more for `multi_domain` (ADR-032, named back to the user), none for
    `out_of_scope` or `ambiguous` (domains given on `ambiguous` are read as candidates).
    `candidates` lists, for `ambiguous` only (ADR-075),
    the two or three domains the question could mean; it is empty for every other
    route. Field order is the order the model writes keys in and must match the routing
    prompt's JSON template (L-51).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    route: Route
    domains: list[Domain] = Field(default_factory=list)
    candidates: Candidates = Field(default_factory=list)
    reason: str = Field(min_length=1, max_length=300, description="One short sentence.")

    _dropped: list[str] = PrivateAttr(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> RouteDecision:
        distinct = set(self.domains)
        if self.route == "multi_domain" and len(distinct) < 2:
            raise ValueError("multi_domain needs at least two distinct domains")
        if self.route == "out_of_scope" and distinct:
            raise ValueError("out_of_scope takes no domains")
        if self.route in DOMAINS and distinct - {self.route}:
            raise ValueError("a single-domain route lists only its own domain")
        raw = list(self.candidates)
        if self.route == "ambiguous" and self.domains:
            # Domains given where candidates belong: read them as candidates rather than
            # failing the call, and clear `domains` so `ambiguous` never carries any.
            raw = raw + [d for d in self.domains if d not in raw]
            object.__setattr__(self, "domains", [])
        kept: list[str] = []
        dropped: list[str] = []
        for c in raw:
            if self.route == "ambiguous" and c in DOMAINS and c not in kept:
                kept.append(c)
            else:
                dropped.append(c)
        # Frozen model: set the cleaned list directly, once, during validation.
        object.__setattr__(self, "candidates", kept)
        self._dropped = dropped
        return self

    @property
    def dropped_candidates(self) -> list[str]:
        """Candidate values removed during validation: invalid, repeated, or given on a
        route other than `ambiguous`. The router logs each one (ADR-075)."""
        return list(self._dropped)
