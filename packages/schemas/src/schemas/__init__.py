"""Pydantic contracts shared across services.

Pydantic only, never ORM models (ADR-026): a tool's input/output shape and a table's
column structure change for different reasons. No dependency on `db_models`, so an
agent container that must not touch the database never installs it.
"""

from __future__ import annotations

from .incidents import IncidentSummary, SeverityCounts

__all__ = ["IncidentSummary", "SeverityCounts"]
