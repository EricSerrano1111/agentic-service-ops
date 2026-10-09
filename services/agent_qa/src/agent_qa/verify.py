"""Run every check on one `VerificationRequest` and assemble the `Verdict` (ADR-087, ADR-089).

Order: the deterministic figures checks first. If any fails, the verdict is `fail` at once and
the interpretation call is not made (a request ends at a figures failure, so the call would be
wasted spend). Otherwise the interpretation call runs. A database or model failure is not a
verdict: it propagates, and the executor reports QA as unavailable.
"""

from __future__ import annotations

import asyncio
import logging

from llm import LLMError
from pydantic import ValidationError
from schemas import (
    CheckResult,
    ForecastAnswer,
    ForecastRequest,
    ReportingAnswer,
    ReportingRequest,
    Verdict,
    VerificationRequest,
)

from . import forecast, reporting
from .config import Settings
from .db import Source
from .interpretation import (
    CHECK_CODE,
    Interpreter,
    guidance_for,
    reading_forecast,
    reading_reporting,
)

log = logging.getLogger("agent_qa")


def _malformed(what: str) -> Verdict:
    return Verdict(
        verdict="fail",
        checks=[CheckResult(code=what, check_class="figures", passed=False, detail="")],
    )


class Verifier:
    def __init__(
        self,
        src: Source,
        settings: Settings,
        manifest: forecast.Manifest,
        interpreter: Interpreter,
    ) -> None:
        self.settings = settings
        self.interpreter = interpreter
        self.reporting = reporting.Checker(src, settings)
        self.forecast = forecast.Checker(src, settings, manifest)

    async def verify(self, req: VerificationRequest, *, trace_id: str | None) -> Verdict:
        if req.kind == "answer":
            parsed = self._parse_answer(req)
            if parsed is None:
                return _malformed("answer_malformed")
            checks = await asyncio.to_thread(self._answer_checks, req, parsed)
        else:
            request = self._parse_request(req)
            if request is None:
                return _malformed("parsed_request_malformed")
            checks = await asyncio.to_thread(self._decline_checks, req, request)
        if any(not c.passed for c in checks):
            return Verdict(verdict="fail", checks=checks)

        advisory = self.settings.interp_mode == "advisory"
        try:
            judgement = await self.interpreter.judge(
                req.domain, req.question, self._reading_of(req), trace_id=trace_id
            )
        except (LLMError, TimeoutError) as exc:
            if not advisory:
                raise
            # Advisory: a check that could not run is reported, not a reason to withhold a
            # verdict the deterministic checks have already given.
            log.warning("advisory interpretation not run", extra={"error": type(exc).__name__})
            return Verdict(
                verdict="pass",
                checks=checks,
                advisories=[
                    CheckResult(
                        code=CHECK_CODE,
                        check_class="interpretation",
                        passed=False,
                        detail="advisory: the check could not run",
                    )
                ],
            )
        if advisory:
            return Verdict(
                verdict="pass",
                checks=checks,
                advisories=[
                    CheckResult(
                        code=CHECK_CODE,
                        check_class="interpretation",
                        passed=judgement.faithful,
                        detail=""
                        if judgement.faithful
                        else "advisory: differs in "
                        + (", ".join(judgement.differs_in) or "unspecified"),
                    )
                ],
            )
        if judgement.faithful:
            return Verdict(
                verdict="pass",
                checks=[
                    *checks,
                    CheckResult(code=CHECK_CODE, check_class="interpretation", passed=True),
                ],
            )
        detail = (
            "differs in: " + ", ".join(judgement.differs_in)
            if judgement.differs_in
            else "reading does not match the question"
        )
        return Verdict(
            verdict="fail",
            checks=[
                *checks,
                CheckResult(
                    code=CHECK_CODE, check_class="interpretation", passed=False, detail=detail
                ),
            ],
            guidance=guidance_for(judgement),
        )

    # ------------------------------------------------------------------ parsing the input

    def _parse_answer(self, req: VerificationRequest):
        model = ReportingAnswer if req.domain == "reporting" else ForecastAnswer
        try:
            return model.model_validate(req.answer)
        except ValidationError:
            return None

    def _parse_request(self, req: VerificationRequest):
        model = ReportingRequest if req.domain == "reporting" else ForecastRequest
        try:
            return model.model_validate(req.parsed_request or {})
        except ValidationError:
            return None

    # ------------------------------------------------------------------ the checks

    def _answer_checks(self, req: VerificationRequest, parsed) -> list[CheckResult]:
        if req.domain == "reporting":
            return self.reporting.check_answer(parsed, req.text)
        return self.forecast.check_answer(parsed, req.text)

    def _decline_checks(self, req: VerificationRequest, request) -> list[CheckResult]:
        if req.domain == "reporting":
            return self.reporting.check_decline(request, req.error_code, req.text)
        if req.error_code != "not_supported":
            return [
                CheckResult(
                    code="decline_matches_reason",
                    check_class="figures",
                    passed=False,
                    detail="not a decline code QA knows",
                )
            ]
        return self.forecast.check_decline(request, req.text)

    def _reading_of(self, req: VerificationRequest) -> str:
        as_of = self.settings.as_of
        if req.kind == "answer":
            parsed = self._parse_answer(req)
            if req.domain == "reporting":
                return reading_reporting(
                    parsed.request, parsed.start, parsed.end, parsed.range_assumed, as_of
                )
            return reading_forecast(parsed.request, as_of)
        request = self._parse_request(req)
        if req.domain == "reporting":
            named = request.start is not None
            return reading_reporting(
                request,
                request.start if named else None,
                request.end if named else None,
                False,
                as_of,
            )
        return reading_forecast(request, as_of)
