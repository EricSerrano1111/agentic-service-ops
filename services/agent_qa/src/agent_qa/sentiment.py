"""Sentiment checks (ADR-087, ADR-090): QA recomputes a sentiment answer from the stored
predictions with its own SQL and compares, checks the flags and the trend, the quoted comments,
the declines, the text, and runs the rating cross-check.

Written from data dictionary §6, "Sentiment answers", alone. It imports nothing from the
sentiment agent or the feedback server (a test fails if it does) and nothing from the model
code: the only things it takes from the model's side are the committed manifest file's bytes
(the `model_version`) and its calibrated threshold τ, read as JSON.

Every check enforces one reading, the one §6 writes. Where §6 says a thing is not specified
(which comments are quoted), nothing is checked about it.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from common.stats import rating_cross_check
from schemas import (
    SENTIMENT_LABELS,
    CheckResult,
    SentimentAnswer,
    SentimentRequest,
)

from . import textcheck
from .config import Settings
from .db import Source, utc_bounds
from .reporting import bad, result
from .stats import rate_string

MIN_N = 20
ALPHA = 0.05
MAX_QUOTES = 3
TREND_MONTHS = 6
#: ADR-087: the baseline contradiction rate measured once over the full window (7 of 4,715). The
#: rule's p0 is max(p̂, 0.01), so 0.01 whatever the baseline's exact value.
BASELINE_P_HAT = 0.001485

DECLINE_PHRASES = {
    "account": "can't be broken down by account",
    "technician": "can't be broken down by technician",
    "service_type": "can't be broken down by service type",
    "other": "That breakdown of sentiment isn't supported",
}


@dataclass(frozen=True)
class SentimentManifest:
    version: str  # SHA-256 of the manifest file's bytes: `sentiment_predictions.model_version`
    tau: float  # `calibration.threshold`

    @classmethod
    def load(cls, path: Path) -> SentimentManifest:
        raw = Path(path).read_bytes()
        return cls(
            hashlib.sha256(raw).hexdigest(), float(json.loads(raw)["calibration"]["threshold"])
        )


# --------------------------------------------------------------------------- the rules


def previous_month(as_of: dt.date) -> tuple[dt.date, dt.date]:
    end = as_of.replace(day=1) - dt.timedelta(days=1)
    return end.replace(day=1), end


def trend_default(as_of: dt.date) -> tuple[dt.date, dt.date]:
    """Six calendar months ending at the as-of date's month, through the as-of date."""
    index = as_of.year * 12 + (as_of.month - 1) - (TREND_MONTHS - 1)
    return dt.date(index // 12, index % 12 + 1, 1), as_of


def resolved_range(request: SentimentRequest, as_of: dt.date) -> tuple[dt.date, dt.date, str, bool]:
    """(start, end, bucket, assumed) by §6 rule 3."""
    if request.start is not None:
        return request.start, request.end, request.bucket, False
    if request.want_trend:
        start, end = trend_default(as_of)
        return start, end, "month", True
    start, end = previous_month(as_of)
    return start, end, request.bucket, True


def percent_one_decimal(share: str | None) -> str | None:
    """'0.4978' -> '49.8' (half-up), as the answer text shows a share."""
    if share is None:
        return None
    return str((Decimal(share) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def two_proportion(x1: int, n1: int, x2: int, n2: int) -> tuple[float, float]:
    """(z, two-sided p), pooled standard error; (0, 1) when there is nothing to test."""
    if not n1 or not n2:
        return 0.0, 1.0
    pooled = (x1 + x2) / (n1 + n2)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    if se == 0:
        return 0.0, 1.0
    z = (x1 / n1 - x2 / n2) / se
    return z, math.erfc(abs(z) / math.sqrt(2))


@dataclass(frozen=True)
class Figures:
    """QA's own recomputation of a sentiment summary."""

    n_comments: int
    n_scored: int
    counts: dict[str, int]
    flagged: int
    buckets: list[dict[str, Any]]  # sorted by name

    @property
    def complete(self) -> bool:
        return self.n_scored == self.n_comments

    def shares(self) -> dict[str, str | None]:
        return {k: rate_string(self.counts[k], self.n_scored) for k in SENTIMENT_LABELS}


def recompute(src: Source, version: str, start, end, region, bucket) -> Figures:
    lo, hi = utc_bounds(start, end)
    n_comments, n_scored = src.sentiment_coverage(version, lo, hi, region)
    rows = src.sentiment_buckets(version, lo, hi, region, bucket)
    counts = dict.fromkeys(SENTIMENT_LABELS, 0)
    by_bucket: dict[str, dict[str, Any]] = {}
    flagged = 0
    for label, name, n, fl in rows:
        counts[label] += n
        flagged += fl
        b = by_bucket.setdefault(
            name,
            {"bucket": name, "n": 0, "flagged": 0, "counts": dict.fromkeys(SENTIMENT_LABELS, 0)},
        )
        b["n"] += n
        b["flagged"] += fl
        b["counts"][label] += n
    return Figures(n_comments, n_scored, counts, flagged, [by_bucket[k] for k in sorted(by_bucket)])


def expected_trend(f: Figures) -> dict[str, Any]:
    if len(f.buckets) < 2:
        return {"verdict": "needs two periods"}
    latest, earlier = f.buckets[-1], f.buckets[:-1]
    n1, x1 = latest["n"], latest["counts"]["negative"]
    n2 = sum(b["n"] for b in earlier)
    x2 = sum(b["counts"]["negative"] for b in earlier)
    small = n1 < MIN_N or n2 < MIN_N
    z, p = two_proportion(x1, n1, x2, n2)
    verdict = "no clear change"
    if not small and p < ALPHA:
        verdict = "rose" if x1 / n1 > x2 / n2 else "fell"
    return {
        "verdict": verdict,
        "latest_bucket": latest["bucket"],
        "latest_n": n1,
        "latest_negative": x1,
        "earlier_buckets": [b["bucket"] for b in earlier],
        "earlier_n": n2,
        "earlier_negative": x2,
        "z": round(z, 4),
        "p_value": round(p, 4),
        "small_sample": small,
    }


# --------------------------------------------------------------------------- the checker


class Checker:
    def __init__(self, src: Source, settings: Settings, manifest: SentimentManifest) -> None:
        self.src = src
        self.settings = settings
        self.manifest = manifest

    def check_answer(self, answer: SentimentAnswer, text: str) -> list[CheckResult]:
        req = answer.request
        start, end, bucket, assumed = resolved_range(req, self.settings.as_of)
        lo, hi = utc_bounds(answer.start, answer.end)
        region = req.region
        checks = [self._check_range(answer, (start, end, bucket, assumed))]
        want = recompute(
            self.src, self.manifest.version, answer.start, answer.end, region, answer.summary.bucket
        )
        checks.append(self._check_coverage(answer, want))
        checks.append(self._check_figures(answer, want))
        checks.append(
            result(
                "flags_consistent",
                ["a_flag_disagrees_with_its_confidence"]
                if self.src.sentiment_inconsistent_flags(
                    self.manifest.version, lo, hi, region, self.manifest.tau
                )
                else [],
            )
        )
        checks.append(self._check_trend(answer, want))
        checks.append(self._check_quotes(answer, lo, hi))
        checks.append(self._rating(lo, hi, region))
        if all(c.passed for c in checks):
            checks.append(self._check_text(answer, want, text))
        return checks

    # ------------------------------------------------------------------ range, coverage, figures

    def _check_range(self, answer: SentimentAnswer, expected) -> CheckResult:
        start, end, bucket, assumed = expected
        problems = []
        if (answer.start, answer.end) != (start, end):
            problems.append("range_differs_from_request")
        if answer.range_assumed != assumed:
            problems.append("range_assumed_flag")
        if answer.summary.bucket != bucket:
            problems.append("bucket_differs")
        if answer.as_of != self.settings.as_of:
            problems.append("as_of_differs")
        if answer.summary.region != answer.request.region:
            problems.append("region_differs")
        return result("range_matches_request", problems)

    def _check_coverage(self, answer: SentimentAnswer, want: Figures) -> CheckResult:
        s, problems = answer.summary, []
        if s.model_version != self.manifest.version:
            problems.append("model_version_differs")
        if s.n_comments != want.n_comments:
            problems.append("n_comments")
        if s.n_scored != want.n_scored:
            problems.append("n_scored")
        if s.complete != want.complete:
            problems.append("complete")
        return result("coverage_matches_database", problems)

    def _check_figures(self, answer: SentimentAnswer, want: Figures) -> CheckResult:
        s, problems = answer.summary, []
        if s.counts.model_dump() != want.counts:
            problems.append("counts")
        if s.shares.model_dump() != want.shares():
            problems.append("shares")
        if s.flagged_count != want.flagged:
            problems.append("flagged_count")
        shown = [
            {
                "bucket": b.bucket,
                "n": b.n_scored,
                "flagged": b.flagged_count,
                "counts": b.counts.model_dump(),
            }
            for b in s.buckets
        ]
        if shown != want.buckets:
            problems.append("buckets")
        return result("figures_match_database", problems)

    # ------------------------------------------------------------------ the trend

    def _check_trend(self, answer: SentimentAnswer, want: Figures) -> CheckResult:
        if not answer.request.want_trend:
            return result(
                "trend_matches", [] if answer.trend is None else ["a_trend_nobody_asked_for"]
            )
        if answer.trend is None:
            return bad("trend_matches", "the trend that was asked for is missing")
        got = answer.trend.model_dump()
        exp = expected_trend(want)
        problems = []
        if got["verdict"] != exp["verdict"]:
            problems.append("verdict")
        for key, value in exp.items():
            if key == "verdict":
                continue
            if isinstance(value, float):
                if got[key] is None or abs(got[key] - value) > 1e-9:
                    problems.append(key)
            elif got[key] != value:
                problems.append(key)
        if (
            exp.get("z") == 0.0
            and exp.get("p_value") == 1.0
            and got["verdict"] != "no clear change"
        ):
            problems.append("nothing_to_test_must_be_no_clear_change")
        if exp["verdict"] == "needs two periods" and any(
            got[k] not in (None, [], False) for k in got if k != "verdict"
        ):
            problems.append("fields_set_for_a_trend_with_one_period")
        return result("trend_matches", problems)

    # ------------------------------------------------------------------ quotes

    def _check_quotes(self, answer: SentimentAnswer, lo, hi) -> CheckResult:
        req, problems = answer.request, []
        examples = answer.examples
        if not req.want_examples and examples:
            problems.append("quotes_nobody_asked_for")
        if len(examples) > MAX_QUOTES:
            problems.append("more_than_three_quotes")
        if answer.quoted_feedback_ids != [e.feedback_id for e in examples]:
            problems.append("quoted_ids_list_differs")
        ids = [e.feedback_id for e in examples]
        if len(set(ids)) != len(ids):
            problems.append("a_comment_quoted_twice")
        expected = (
            self.src.sentiment_top_quotes(
                self.manifest.version, lo, hi, req.region, req.example_label, MAX_QUOTES
            )
            if req.want_examples
            else []
        )
        if ids != expected:
            problems.append("quotes_not_the_top_by_confidence")
        facts = self.src.sentiment_quotes(self.manifest.version, ids)
        for e in examples:
            fact = facts.get(e.feedback_id)
            if fact is None:
                problems.append("quote_id_does_not_exist")
                continue
            at = fact["submitted_at"]
            if not (lo <= at < hi) or (req.region is not None and fact["region"] != req.region):
                problems.append("quote_outside_the_set")
            if fact["label"] is None:
                problems.append("quote_is_not_scored")
                continue
            if req.example_label is not None and fact["label"] != req.example_label:
                problems.append("quote_label_is_not_the_one_asked_for")
            if e.feedback_text != fact["text"]:
                problems.append("quoted_text_differs")
            if (
                e.label != fact["label"]
                or e.confidence != fact["confidence"]
                or e.flagged != fact["flagged"]
                or e.region != fact["region"]
                or e.submitted_at != at
            ):
                problems.append("quote_details_differ")
        return result("quotes_valid", problems)

    # ------------------------------------------------------------------ the rating cross-check

    def _rating(self, lo, hi, region) -> CheckResult:
        n, x = self.src.sentiment_rating_counts(self.manifest.version, lo, hi, region)
        check = rating_cross_check(n, x, BASELINE_P_HAT)
        detail = f"n={n}, x={x}, p0={check.p0:g}: {check.status}"
        return CheckResult(
            code="rating_contradiction",
            check_class="figures",
            passed=not check.failed,
            detail=detail,
        )

    # ------------------------------------------------------------------ the text

    def _check_text(self, answer: SentimentAnswer, want: Figures, text: str) -> CheckResult:
        allowed: set[str] = {str(MIN_N)}
        required: list[set[str]] = []
        compared: list[str] = []
        names: list[str] = [b["bucket"] for b in want.buckets]
        dates = {answer.start.isoformat(), answer.end.isoformat(), answer.as_of.isoformat()}

        def add_int(*values: int) -> None:
            for v in values:
                allowed.add(str(v))

        def add_share(share: str | None) -> set[str]:
            pct = percent_one_decimal(share)
            forms = set() if pct is None else {pct}
            allowed.update(forms)
            return forms

        add_int(want.n_scored, want.n_comments, want.flagged, *want.counts.values())
        if want.n_scored:
            required.append({str(want.n_scored)})
            for label in SENTIMENT_LABELS:
                required.append({str(want.counts[label])})
            for share in want.shares().values():
                add_share(share)
            required.append({percent_one_decimal(rate_string(want.flagged, want.n_scored))})
            add_share(rate_string(want.flagged, want.n_scored))
        if not want.complete:
            required.append({str(want.n_comments)})
        if answer.trend is not None and answer.trend.latest_n is not None:
            t = expected_trend(want)
            add_int(t["latest_n"], t["latest_negative"], t["earlier_n"], t["earlier_negative"])
            names += [t["latest_bucket"], *t["earlier_buckets"]]
            for n, x in (
                (t["latest_n"], t["latest_negative"]),
                (t["earlier_n"], t["earlier_negative"]),
            ):
                add_share(rate_string(x, n))
            allowed.add(f"{t['p_value']:.4f}")
            required.append({f"{t['p_value']:.4f}"})
            # The answer names the buckets it compared (§6 rule 6).
            span = t["earlier_buckets"][0] + (
                "" if len(t["earlier_buckets"]) == 1 else f" to {t['earlier_buckets'][-1]}"
            )
            compared = [f"{t['latest_bucket']}:", span + ":"]
        for e in answer.examples:
            names.append(e.feedback_text)
            add_int(e.feedback_id)
            allowed.add(e.confidence)
            dates.add(e.submitted_at.date().isoformat())
        problems = textcheck.compare(text, allowed, required, names)
        if compared and not all(part in text for part in compared):
            problems.append("text_does_not_name_the_compared_buckets")
        stated = set(re.findall(r"\b\d{4}-\d{2}-\d{2}\b", textcheck.strip_names(text, names)))
        if not stated <= dates:
            problems.append("text_states_another_date")
        return result("text_matches_data", problems)

    # ------------------------------------------------------------------ declines

    def check_decline(self, request: SentimentRequest, text: str) -> list[CheckResult]:
        """A decline carries no figures and states the one reason the parse reported (§6 rule 8)."""
        problems = []
        if request.unsupported is None:
            problems.append("declined_a_request_that_can_be_answered")
        else:
            stated = {k for k, phrase in DECLINE_PHRASES.items() if phrase in text}
            if stated != {request.unsupported}:
                problems.append("reason_stated_is_not_the_reason_reported")
        return [
            result("decline_matches_reason", problems),
            result(
                "decline_no_figures", ["text_carries_a_number"] if re.search(r"\d", text) else []
            ),
        ]


__all__ = ["Checker", "SentimentManifest"]
