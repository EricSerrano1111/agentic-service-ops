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

from pydantic import BaseModel, ConfigDict, Field

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
