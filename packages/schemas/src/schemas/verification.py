"""The verification contract between the orchestrator and the QA agent (ADR-087, ADR-089).

The orchestrator sends one `VerificationRequest` per specialist result and gets one `Verdict`
back. The request carries the specialist's answer exactly as the orchestrator received it:
the QA agent re-derives everything it checks itself and trusts nothing in it.

A verdict is `pass` or `fail`. Every check that ran is listed with a code and a class:
`figures` checks are deterministic code (a figure, a rule or a piece of text compared with the
database or the manifest) and `interpretation` is the one language-model check (does the
parsed request match the question). A figures failure ends the request at once; an
interpretation failure may be retried with the verdict's guidance (ADR-089).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: What the user is told about verification. `verified`: QA passed it. `not_checked`: no QA
#: check exists for this answer yet (sentiment until M2) or the request ended before one ran.
#: `unavailable`: QA was needed and could not run, so the answer is never shown as verified.
#: `not_applicable`: no specialist answered (a routing decline, a split or a clarification).
QaStatus = Literal["verified", "not_checked", "unavailable", "not_applicable"]

CheckClass = Literal["figures", "interpretation"]
VerifiedDomain = Literal["reporting", "forecast"]
Kind = Literal["answer", "decline"]

CODE_PATTERN = r"^[a-z0-9_]{1,64}$"
MAX_TEXT_CHARS = 20_000
MAX_QUESTION_CHARS = 2_000
#: The reviewer note handed back to a specialist is capped (ADR-089): it is untrusted text.
MAX_GUIDANCE_CHARS = 300
MAX_DETAIL_CHARS = 200
MAX_CHECKS = 40


class VerificationRequest(BaseModel):
    """One specialist result to verify. For `kind: answer`, `answer` is the specialist's data
    part (a `ReportingAnswer` or `ForecastAnswer` as JSON); for `kind: decline` there are no
    figures, `error_code` is the specialist's stated reason and `parsed_request` how it read
    the question."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    domain: VerifiedDomain
    kind: Kind
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    text: str = Field(max_length=MAX_TEXT_CHARS, description="The answer or decline text.")
    answer: dict[str, Any] | None = None
    error_code: str | None = Field(default=None, pattern=CODE_PATTERN)
    parsed_request: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _shape(self) -> VerificationRequest:
        if self.kind == "answer":
            if self.answer is None or self.error_code is not None:
                raise ValueError("an answer carries its data part and no error code")
        elif self.answer is not None or self.error_code is None:
            raise ValueError("a decline carries an error code and no data part")
        return self


class CheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(pattern=CODE_PATTERN)
    check_class: CheckClass
    passed: bool
    #: Fixed wording naming what differed. It never holds a figure from the answer, so a
    #: verdict can be logged and shown in full.
    detail: str = Field(default="", max_length=MAX_DETAIL_CHARS)


class Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    verdict: Literal["pass", "fail"]
    checks: list[CheckResult] = Field(max_length=MAX_CHECKS)
    #: A reviewer note for the specialist, set only when the sole failure is interpretation.
    guidance: str | None = Field(default=None, max_length=MAX_GUIDANCE_CHARS)

    @property
    def failed(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]

    @property
    def figures_failed(self) -> bool:
        return any(c.check_class == "figures" and not c.passed for c in self.checks)

    @property
    def interpretation_failed(self) -> bool:
        return any(c.check_class == "interpretation" and not c.passed for c in self.checks)

    @model_validator(mode="after")
    def _consistent(self) -> Verdict:
        if (self.verdict == "fail") != bool(self.failed):
            raise ValueError("the verdict is fail exactly when a check failed")
        if self.guidance is not None and (self.figures_failed or not self.interpretation_failed):
            raise ValueError("guidance is only for an interpretation-only failure")
        return self
