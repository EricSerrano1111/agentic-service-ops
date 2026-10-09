"""Result of the incidents MCP server's `get_incidents_by_date_range` tool.

Aggregates only: no row identifiers and no free-text columns (`incident_notes` never
leaves the database through this contract). The same model is the MCP tool's output
schema, the data part of the reporting agent's A2A artifact, and what the orchestrator
validates that data part against.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .sentiment import SiteRegion

#: Breakdowns of incident counts (ADR-073). `technician` is the attributed technician;
#: incidents with none form an "unattributed" group.
IncidentGroupBy = Literal[
    "account", "region", "service_type", "technician", "incident_type", "severity"
]
MAX_COUNT_GROUPS = 25
UNATTRIBUTED = "unattributed"


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


class GroupCount(BaseModel):
    """One group's incident count. `group_id` is set for account and technician groups."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    group: str
    group_id: int | None = None
    count: int = Field(ge=0)


class IncidentSummary(BaseModel):
    """Incidents reported in an inclusive UTC date range, by severity; optionally broken
    down (highest count first, at most 25 groups) or filtered to one attributed technician
    (ADR-073)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    metric: Literal["incident_count"] = "incident_count"
    start: dt.date = Field(description="First day of the range, inclusive (UTC).")
    end: dt.date = Field(description="Last day of the range, inclusive (UTC).")
    incident_count: int = Field(ge=0, description="Incidents with reported_at in the range.")
    by_severity: SeverityCounts
    group_by: IncidentGroupBy | None = None
    groups: list[GroupCount] | None = None
    group_count: int | None = Field(default=None, ge=0, description="Groups before the cap.")
    truncated: bool = False
    technician_id: int | None = None
    technician_name: str | None = None
    #: Region and account filters (ADR-086): the figures are then that region's and/or
    #: that account's alone. A filter is never combined with a breakdown by the same
    #: dimension.
    region: SiteRegion | None = None
    account_id: int | None = None
    account_name: str | None = None

    @model_validator(mode="after")
    def _consistent(self) -> IncidentSummary:
        if self.start > self.end:
            raise ValueError("start must not be after end")
        if self.by_severity.total != self.incident_count:
            raise ValueError("by_severity must sum to incident_count")
        if (self.group_by is None) != (self.groups is None):
            raise ValueError("groups are present exactly when group_by is set")
        if self.groups is not None:
            if len(self.groups) > MAX_COUNT_GROUPS:
                raise ValueError(f"at most {MAX_COUNT_GROUPS} groups")
            if self.truncated != (self.group_count > len(self.groups)):
                raise ValueError("truncated must say whether groups were cut")
            if not self.truncated and sum(g.count for g in self.groups) != self.incident_count:
                raise ValueError("untruncated groups must sum to incident_count")
        if (self.technician_id is None) != (self.technician_name is None):
            raise ValueError("technician_id and technician_name go together")
        if self.technician_id is not None and self.group_by is not None:
            raise ValueError("a single-technician count has no breakdown")
        if (self.account_id is None) != (self.account_name is None):
            raise ValueError("account_id and account_name go together")
        if self.region is not None and self.group_by == "region":
            raise ValueError("a region filter has no breakdown by region")
        if self.account_id is not None and self.group_by == "account":
            raise ValueError("an account filter has no breakdown by account")
        return self
