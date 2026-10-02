"""Results of the feedback MCP server's two tools (FR-07, ADR-067).

Answers come from stored predictions (`sentiment_predictions`), never from labels. Every
result carries its coverage: `n_comments` in range, `n_scored` of them with a stored
prediction for `model_version`, and `complete` when the two are equal. A partial answer
is an answer over the scored comments only, and says so.

Shares are strings, `Decimal` half-up to 4 places, like the incidents metrics.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SentimentLabel = Literal["positive", "neutral", "negative", "mixed"]
SENTIMENT_LABELS: tuple[SentimentLabel, ...] = ("positive", "neutral", "negative", "mixed")
SiteRegion = Literal["northeast", "southeast", "central", "west"]
Bucket = Literal["month", "quarter"]
MAX_EXAMPLES = 5
MAX_SPAN_DAYS = 731

_SHARE_PATTERN = r"^\d+\.\d{4}$"


class LabelCounts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    positive: int = Field(ge=0)
    neutral: int = Field(ge=0)
    negative: int = Field(ge=0)
    mixed: int = Field(ge=0)


class LabelShares(BaseModel):
    """Each label's share of the scored comments; null when nothing is scored."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    positive: str | None = Field(default=None, pattern=_SHARE_PATTERN)
    neutral: str | None = Field(default=None, pattern=_SHARE_PATTERN)
    negative: str | None = Field(default=None, pattern=_SHARE_PATTERN)
    mixed: str | None = Field(default=None, pattern=_SHARE_PATTERN)


class Coverage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model_version: str = Field(description="SHA-256 of the artifact manifest.")
    n_comments: int = Field(ge=0, description="Comments in range (and region).")
    n_scored: int = Field(ge=0, description="Of those, with a stored prediction.")
    complete: bool = Field(description="n_scored == n_comments.")


class BucketCounts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    bucket: str = Field(description="YYYY-MM for months, YYYY-Qn for quarters (UTC).")
    n_scored: int = Field(ge=0)
    counts: LabelCounts
    flagged_count: int = Field(ge=0)


class SentimentSummary(Coverage):
    """Counts only: no comment text and no comment ids."""

    start: dt.date
    end: dt.date
    region: SiteRegion | None = None
    bucket: Bucket
    counts: LabelCounts
    shares: LabelShares
    flagged_count: int = Field(ge=0, description="Scored comments below τ (human review).")
    buckets: list[BucketCounts]


class FeedbackExample(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    feedback_id: int
    submitted_at: dt.datetime
    region: SiteRegion | None
    label: SentimentLabel
    confidence: str = Field(pattern=_SHARE_PATTERN, description="Calibrated probability.")
    flagged: bool
    feedback_text: str


class FeedbackExamples(Coverage):
    """At most 5 comments, for citation."""

    start: dt.date
    end: dt.date
    region: SiteRegion | None = None
    label: SentimentLabel | None = None
    flagged_only: bool
    examples: list[FeedbackExample] = Field(max_length=MAX_EXAMPLES)


# --------------------------------------------------------------------------- the agent (ADR-068)

#: A breakdown the sentiment agent declines: it reports by time and site region only.
UnsupportedDimension = Literal["account", "technician", "service_type", "other"]
TrendVerdict = Literal["rose", "fell", "no clear change", "needs two periods"]


class SentimentRequest(BaseModel):
    """What the parsing call extracts (ADR-068). Dates are null when the question names no
    period; code then applies the default range, never the model (ADR-050, ADR-068)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    start: dt.date | None = Field(default=None, description="First day, inclusive.")
    end: dt.date | None = Field(default=None, description="Last day, inclusive.")
    region: SiteRegion | None = None
    bucket: Bucket = "month"
    want_trend: bool = False
    want_examples: bool = False
    example_label: SentimentLabel | None = None
    unsupported: UnsupportedDimension | None = None

    @model_validator(mode="after")
    def _both_or_neither(self) -> SentimentRequest:
        if (self.start is None) != (self.end is None):
            raise ValueError("give both start and end, or neither")
        if self.start is not None and self.end is not None and self.start > self.end:
            raise ValueError("start is after end")
        return self


class TrendResult(BaseModel):
    """ADR-068's rule: negative share in the latest bucket against the pooled earlier ones.

    `verdict` is "rose" or "fell" only if both sides hold at least 20 comments and a
    two-sided two-proportion z-test gives p < 0.05; otherwise "no clear change". With
    fewer than two buckets it is "needs two periods" and the comparison fields are null.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    verdict: TrendVerdict
    latest_bucket: str | None = None
    latest_n: int | None = Field(default=None, ge=0)
    latest_negative: int | None = Field(default=None, ge=0)
    earlier_buckets: list[str] = Field(default_factory=list)
    earlier_n: int | None = Field(default=None, ge=0)
    earlier_negative: int | None = Field(default=None, ge=0)
    z: float | None = None
    p_value: float | None = Field(default=None, ge=0, le=1)
    small_sample: bool = Field(default=False, description="Either side under 20 comments.")


class SentimentAnswer(BaseModel):
    """The data part of the sentiment agent's artifact: the request as parsed, the range
    queried, the figures from `mcp_feedback`, the trend test, and the quoted comments.
    Every figure in the answer text comes from here (ADR-068)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request: SentimentRequest
    start: dt.date
    end: dt.date
    range_assumed: bool
    as_of: dt.date
    summary: SentimentSummary
    trend: TrendResult | None = None
    examples: list[FeedbackExample] = Field(default_factory=list, max_length=3)
    quoted_feedback_ids: list[int] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def _consistent(self) -> SentimentAnswer:
        if (self.summary.start, self.summary.end) != (self.start, self.end):
            raise ValueError("summary must cover the queried range")
        if self.summary.region != self.request.region:
            raise ValueError("summary must be for the requested region")
        if self.range_assumed != (self.request.start is None):
            raise ValueError("range_assumed must match whether the request had dates")
        if self.request.unsupported is not None:
            raise ValueError("an unsupported request is declined, never answered")
        if self.quoted_feedback_ids != [e.feedback_id for e in self.examples]:
            raise ValueError("quoted_feedback_ids must list the quoted examples, in order")
        if (self.trend is not None) != self.request.want_trend:
            raise ValueError("a trend is present exactly when one was asked for")
        return self
