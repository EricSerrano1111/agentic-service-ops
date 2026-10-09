"""Repeat-visit drivers and technician lookup: results of two incidents MCP tools (ADR-073).

A repeat visit is a non-cancelled child request; its original job is the parent, a request
completed in the range (the §6 first-time-fix date rule). Every repeat visit is recorded
through a repeat-visit-required incident on the original job, so `by=incident_type` leaves
that type out and compares the other types.

A group "stands out" only if it has at least 20 jobs, its repeat rate is above the rest's,
and Fisher's exact test (two-sided) against the rest gives p < 0.05 after Bonferroni
correction across the groups compared. Groups are listed worst first.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RepeatBy = Literal["incident_type", "service_type", "region", "account", "technician"]
MAX_REPEAT_GROUPS = 25
MIN_GROUP_JOBS = 20
MAX_TECHNICIAN_MATCHES = 5
MAX_ACCOUNT_MATCHES = 5
_RATE = r"^\d+\.\d{4}$"


class JobsRepeated(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    jobs: int = Field(ge=0, description="Completed original jobs.")
    repeated: int = Field(ge=0, description="Of those, with a repeat visit.")
    rate: str | None = Field(default=None, pattern=_RATE)

    @model_validator(mode="after")
    def _counts(self) -> JobsRepeated:
        if self.repeated > self.jobs:
            raise ValueError("repeated cannot exceed jobs")
        return self


class RepeatGroup(BaseModel):
    """One group against every other job in range."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    group: str
    group_id: int | None = None
    this: JobsRepeated
    rest: JobsRepeated
    compared: bool = Field(description="At least 20 jobs, so included in the test.")
    p_value: float | None = Field(default=None, ge=0, le=1, description="Fisher, two-sided.")
    p_adjusted: float | None = Field(default=None, ge=0, le=1, description="Bonferroni.")
    stands_out: bool


class RepeatDriversResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    metric: Literal["repeat_visit_drivers"] = "repeat_visit_drivers"
    start: dt.date
    end: dt.date
    group_by: RepeatBy
    overall: JobsRepeated
    groups: list[RepeatGroup] = Field(max_length=MAX_REPEAT_GROUPS)
    group_count: int = Field(ge=0, description="Groups before the cap.")
    truncated: bool = False
    groups_compared: int = Field(ge=0, description="Groups with at least 20 jobs.")
    #: incident_type only: jobs with any incident other than repeat_visit_required, against
    #: jobs with none other. One comparison, so no Bonferroni: compared when both sides have
    #: at least 20 jobs; `other_incident_higher` when Fisher's p < 0.05 and the any-other
    #: rate is the higher (ADR-073).
    any_other_incident: JobsRepeated | None = None
    no_other_incident: JobsRepeated | None = None
    other_incident_compared: bool | None = None
    other_incident_p_value: float | None = Field(default=None, ge=0, le=1)
    other_incident_higher: bool | None = None

    @model_validator(mode="after")
    def _consistent(self) -> RepeatDriversResult:
        if self.start > self.end:
            raise ValueError("start must not be after end")
        if self.truncated != (self.group_count > len(self.groups)):
            raise ValueError("truncated must say whether groups were cut")
        typed = self.group_by == "incident_type"
        other = (
            self.any_other_incident,
            self.no_other_incident,
            self.other_incident_compared,
            self.other_incident_higher,
        )
        if any(typed != (x is not None) for x in other):
            raise ValueError("the any-other-incident comparison is for incident_type only")
        if typed:
            if self.other_incident_compared != (self.other_incident_p_value is not None):
                raise ValueError("a p-value is present exactly when the comparison was made")
            if self.other_incident_higher and not self.other_incident_compared:
                raise ValueError("only a compared result can be higher")
        elif self.other_incident_p_value is not None:
            raise ValueError("the any-other-incident comparison is for incident_type only")
        if any(g.group == "repeat_visit_required" for g in self.groups):
            raise ValueError("repeat_visit_required defines a repeat and is left out")
        for g in self.groups:
            if g.stands_out and not g.compared:
                raise ValueError("a group under 20 jobs cannot stand out")
        return self


class TechnicianMatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    technician_id: int
    full_name: str


class TechnicianMatches(BaseModel):
    """`find_technician`: at most 5 matches, and how many there were."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    matches: list[TechnicianMatch] = Field(max_length=MAX_TECHNICIAN_MATCHES)
    total_matches: int = Field(ge=0)


class AccountMatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    account_id: int
    account_name: str


class AccountMatches(BaseModel):
    """`find_account` (ADR-086): at most 5 matches, and how many there were."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    matches: list[AccountMatch] = Field(max_length=MAX_ACCOUNT_MATCHES)
    total_matches: int = Field(ge=0)
