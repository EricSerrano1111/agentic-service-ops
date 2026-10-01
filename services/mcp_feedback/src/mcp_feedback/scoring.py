"""Scoring on arrival and the answers built from stored predictions (ADR-067).

`ensure_scored` is internal, never a tool: before a tool answers, it scores the comments
in range that have no prediction for the current model version, at most `cap` of them
(oldest first), and stores them with `ON CONFLICT DO NOTHING`. The tools then answer
from stored predictions only.

The database sits behind `Store`, so this logic is tested offline with an in-memory
store and a stub classifier, and against Postgres in the integration suite.
"""

from __future__ import annotations

import datetime as dt
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from schemas import (
    SENTIMENT_LABELS,
    BucketCounts,
    LabelCounts,
    LabelShares,
    SentimentSummary,
    rate_string,
)

from .classifier import Classifier, Prediction

log = logging.getLogger("mcp_feedback")


@dataclass(frozen=True)
class Scope:
    """A validated request range: inclusive UTC days, optional site region."""

    start: dt.date
    end: dt.date
    region: str | None = None

    @property
    def lo(self) -> dt.datetime:
        return dt.datetime.combine(self.start, dt.time.min, dt.UTC)

    @property
    def hi(self) -> dt.datetime:
        return dt.datetime.combine(self.end + dt.timedelta(days=1), dt.time.min, dt.UTC)


@dataclass(frozen=True)
class CountRow:
    """Stored predictions in scope, counted by label and bucket."""

    label: str
    bucket: str
    n: int
    flagged: int


@dataclass(frozen=True)
class ExampleRow:
    feedback_id: int
    submitted_at: dt.datetime
    region: str | None
    label: str
    confidence: float
    flagged: bool
    feedback_text: str


class Store(Protocol):
    def count_comments(self, scope: Scope) -> int: ...

    def count_scored(self, version: str, scope: Scope) -> int: ...

    def unscored(self, version: str, scope: Scope, limit: int) -> list[tuple[int, str]]:
        """(feedback_id, text) without a prediction for `version`, oldest first."""
        ...

    def insert(self, version: str, rows: Sequence[tuple[int, Prediction]]) -> int:
        """Store predictions; existing (feedback_id, version) pairs are left alone."""
        ...

    def label_bucket_counts(self, version: str, scope: Scope, bucket: str) -> list[CountRow]: ...

    def examples(
        self, version: str, scope: Scope, label: str | None, flagged_only: bool, limit: int
    ) -> list[ExampleRow]: ...


@dataclass(frozen=True)
class Coverage:
    n_comments: int
    n_scored: int
    complete: bool
    n_new: int


def ensure_scored(
    store: Store, classifier: Classifier, version: str, scope: Scope, cap: int
) -> Coverage:
    """Score up to `cap` unscored comments in scope, oldest first; report coverage."""
    n_comments = store.count_comments(scope)
    todo = store.unscored(version, scope, cap)
    n_new = 0
    if todo:
        began = time.perf_counter()
        predictions = classifier.predict([text for _, text in todo])
        n_new = store.insert(
            version, [(fid, p) for (fid, _), p in zip(todo, predictions, strict=True)]
        )
        log.info(
            "scored on demand",
            extra={
                "n_scored_now": n_new,
                "n_requested": len(todo),
                "seconds": round(time.perf_counter() - began, 2),
            },
        )
    n_scored = store.count_scored(version, scope)
    return Coverage(n_comments, n_scored, n_scored == n_comments, n_new)


def example_order_key(flagged_only: bool):
    """Highest confidence first, ties by lowest id; flagged-only: lowest confidence first."""
    if flagged_only:
        return lambda r: (r.confidence, r.feedback_id)
    return lambda r: (-r.confidence, r.feedback_id)


def _counts(by_label: dict[str, int]) -> LabelCounts:
    return LabelCounts(**{label: by_label.get(label, 0) for label in SENTIMENT_LABELS})


def build_summary(
    version: str, scope: Scope, bucket: str, coverage: Coverage, rows: Sequence[CountRow]
) -> SentimentSummary:
    """Assemble the summary from stored counts. No text, no ids."""
    totals: dict[str, int] = {}
    flagged = 0
    by_bucket: dict[str, dict[str, int]] = {}
    flagged_by_bucket: dict[str, int] = {}
    for r in rows:
        totals[r.label] = totals.get(r.label, 0) + r.n
        flagged += r.flagged
        by_bucket.setdefault(r.bucket, {})[r.label] = r.n
        flagged_by_bucket[r.bucket] = flagged_by_bucket.get(r.bucket, 0) + r.flagged
    n = sum(totals.values())
    return SentimentSummary(
        model_version=version,
        n_comments=coverage.n_comments,
        n_scored=coverage.n_scored,
        complete=coverage.complete,
        start=scope.start,
        end=scope.end,
        region=scope.region,
        bucket=bucket,
        counts=_counts(totals),
        shares=LabelShares(
            **{label: rate_string(totals.get(label, 0), n) for label in SENTIMENT_LABELS}
        ),
        flagged_count=flagged,
        buckets=[
            BucketCounts(
                bucket=b,
                n_scored=sum(by_bucket[b].values()),
                counts=_counts(by_bucket[b]),
                flagged_count=flagged_by_bucket[b],
            )
            for b in sorted(by_bucket)
        ],
    )
