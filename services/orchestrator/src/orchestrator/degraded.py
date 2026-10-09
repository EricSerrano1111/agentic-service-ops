"""The degraded result (FR-13, NFR-1, NFR-4; ADR-088).

When the request cannot be answered and verified, the orchestrator returns a normal response
(HTTP 200, `outcome: degraded`) with `escalate: true`, a warning, and, when a dependency is
down, the capability that is unavailable. The other domains keep answering.

Everything the user sees here is a fixed string with at most a capability name and the QA
check codes filled in. No exception text, traceback, token or URL is ever put in the
response (L-60).

Rules for the answer text:
- the best available answer is included only if one exists, and only marked "not verified";
- an answer that **failed** QA is never shown as an answer: the warning names the failed
  checks instead.
"""

from __future__ import annotations

import re
from typing import Literal

Trigger = Literal["deadline", "dependency", "cost_cap", "qa_unavailable", "qa_failed"]

#: Capabilities, as the user reads them.
REPORTING = "reporting"
SENTIMENT = "sentiment"
FORECAST = "forecast"
QA = "verification (QA)"
ROUTING = "routing"

#: Appended to an answer no QA check exists for yet (sentiment, until M2): the user is told
#: plainly that it was not verified (ADR-089).
NOT_VERIFIED_LINE = "Not verified: sentiment answers are not yet checked by the verification agent."

_CODE = re.compile(r"^[a-z0-9_]{1,64}$")
MAX_CODES = 10


class DegradedResult(Exception):
    """Unwinds the request handler to the degraded response."""

    def __init__(
        self,
        trigger: Trigger,
        capability: str | None = None,
        *,
        failed_checks: tuple[str, ...] = (),
        best_answer: str | None = None,
    ) -> None:
        super().__init__(trigger)
        self.trigger = trigger
        self.capability = capability
        # Codes are machine identifiers; anything else is dropped, never echoed.
        self.failed_checks = tuple(c for c in failed_checks if _CODE.match(c))[:MAX_CODES]
        self.best_answer = best_answer


def qa_status_for(d: DegradedResult) -> str:
    """`unavailable` when QA was needed and could not run; otherwise no check ran."""
    return "unavailable" if d.trigger == "qa_unavailable" else "not_checked"


def warning_for(d: DegradedResult) -> str:
    if d.trigger == "deadline":
        return (
            "Time limit reached: the request ran out of its 120 seconds, so it was stopped "
            "and sent for follow-up."
        )
    if d.trigger == "dependency":
        what = d.capability or "a required"
        return (
            f"The {what} service is temporarily unavailable, so this question could not be "
            "answered. Questions in other areas are unaffected."
        )
    if d.trigger == "cost_cap":
        return "Cost limit reached: this request used its cost allowance, so it was stopped."
    if d.trigger == "qa_unavailable":
        return (
            "Verification (QA) is temporarily unavailable, so this answer could not be "
            "checked and is not verified."
        )
    checks = ", ".join(d.failed_checks) or "unspecified"
    return (
        f"The answer failed verification (checks: {checks}) and is not shown. "
        "It has been sent for follow-up."
    )


def answer_for(d: DegradedResult) -> str:
    """The text of a degraded response: the warning, then the best answer marked unverified
    when there is one. A QA-failed answer is never included."""
    text = warning_for(d)
    if d.best_answer and d.trigger != "qa_failed":
        text += f"\n\nNot verified: {d.best_answer}"
    return text
