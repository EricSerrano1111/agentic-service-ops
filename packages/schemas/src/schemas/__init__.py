"""Pydantic contracts shared across services.

Pydantic only, never ORM models (ADR-026): a tool's input/output shape and a table's
column structure change for different reasons. No dependency on `db_models`, so an
agent container that must not touch the database never installs it.
"""

from __future__ import annotations

from .incidents import IncidentSummary, SeverityCounts
from .metrics import (
    MAX_GROUPS,
    FirstTimeFixResult,
    GroupBy,
    GroupRate,
    IncidentRateResult,
    SlaComplianceResult,
    rate_string,
)
from .reporting import (
    DATASET_WINDOW_END,
    DATASET_WINDOW_START,
    Metric,
    ReportingAnswer,
    ReportingRequest,
    RequestGroupBy,
)
from .routing import Domain, Route, RouteDecision
from .sentiment import (
    MAX_EXAMPLES,
    MAX_SPAN_DAYS,
    SENTIMENT_LABELS,
    Bucket,
    BucketCounts,
    Coverage,
    FeedbackExample,
    FeedbackExamples,
    LabelCounts,
    LabelShares,
    SentimentLabel,
    SentimentSummary,
    SiteRegion,
)

__all__ = [
    "MAX_EXAMPLES",
    "MAX_SPAN_DAYS",
    "SENTIMENT_LABELS",
    "Bucket",
    "BucketCounts",
    "Coverage",
    "FeedbackExample",
    "FeedbackExamples",
    "LabelCounts",
    "LabelShares",
    "SentimentLabel",
    "SentimentSummary",
    "SiteRegion",
    "DATASET_WINDOW_END",
    "DATASET_WINDOW_START",
    "MAX_GROUPS",
    "Domain",
    "FirstTimeFixResult",
    "GroupBy",
    "GroupRate",
    "IncidentRateResult",
    "IncidentSummary",
    "Metric",
    "RequestGroupBy",
    "SlaComplianceResult",
    "rate_string",
    "ReportingAnswer",
    "ReportingRequest",
    "Route",
    "RouteDecision",
    "SeverityCounts",
]
