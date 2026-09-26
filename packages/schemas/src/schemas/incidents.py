"""Result of the incidents MCP server's `get_incidents_by_date_range` tool.

Aggregates only: no row identifiers and no free-text columns (`incident_notes` never
leaves the database through this contract). The same model is the MCP tool's output
schema, the data part of the reporting agent's A2A artifact, and what the orchestrator
validates that data part against.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SeverityCounts(BaseModel):
    """Incident counts per severity. Fields mirror `db_models.Severity`; a unit test
    holds them in step, since this package deliberately does not import `db_models`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    low: int = Field(ge=0)
    medium: int = Field(ge=0)
    high: int = Field(ge=0)

    @property
    def total(self) -> int:
        return self.low + self.medium + self.high


class IncidentSummary(BaseModel):
    """Incidents reported in an inclusive UTC date range, by severity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    start: dt.date = Field(description="First day of the range, inclusive (UTC).")
    end: dt.date = Field(description="Last day of the range, inclusive (UTC).")
    incident_count: int = Field(ge=0, description="Incidents with reported_at in the range.")
    by_severity: SeverityCounts

    @model_validator(mode="after")
    def _consistent(self) -> IncidentSummary:
        if self.start > self.end:
            raise ValueError("start must not be after end")
        if self.by_severity.total != self.incident_count:
            raise ValueError("by_severity must sum to incident_count")
        return self
