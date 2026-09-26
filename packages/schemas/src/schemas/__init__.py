"""Pydantic contracts shared across services.

Pydantic only, never ORM models (ADR-026): a tool's input/output shape and a table's
column structure change for different reasons. No dependency on `db_models`, so an
agent container that must not touch the database never installs it.
"""

from __future__ import annotations

from .incidents import IncidentSummary, SeverityCounts
from .reporting import (
    DATASET_WINDOW_END,
    DATASET_WINDOW_START,
    ReportingAnswer,
    ReportingRequest,
)
from .routing import Domain, Route, RouteDecision

__all__ = [
    "DATASET_WINDOW_END",
    "DATASET_WINDOW_START",
    "Domain",
    "IncidentSummary",
    "ReportingAnswer",
    "ReportingRequest",
    "Route",
    "RouteDecision",
    "SeverityCounts",
]
