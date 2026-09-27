"""Results of the incidents MCP server's metric tools (data dictionary §6, FR-06).

One model per tool (ADR-023: no generic query tool). Counts are integers; each rate is a
string, computed with `Decimal` and rounded half-up to 4 decimal places, because
decimals travel as strings (architecture §11). A zero denominator gives a null rate,
never an error. Grouped results list at most `MAX_GROUPS`, worst first (highest rate
first for incident rate, lowest first for SLA compliance and first-time fix), with
`truncated` set when more groups existed; truncation keeps the worst groups.
"""

from __future__ import annotations

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

GroupBy = Literal["account", "region", "service_type", "technician"]
MAX_GROUPS = 25
_PLACES = Decimal("0.0001")
_RATE_PATTERN = r"^\d+\.\d{4}$"


def rate_string(numerator: int, denominator: int, scale: int = 1) -> str | None:
    """`scale * numerator / denominator`, half-up to 4 places, as a string.

    `None` for a zero denominator. Exact `Decimal` arithmetic: the division is carried
    to far more places than kept, so the half-up rounding decides ties correctly.
    """
    if denominator == 0:
        return None
    value = Decimal(scale * numerator) / Decimal(denominator)
    return str(value.quantize(_PLACES, rounding=ROUND_HALF_UP))


class GroupRate(BaseModel):
    """One group's figures. `group` is the dimension value (a region, a service type),
    or a name for account and technician groups, whose id is in `group_id`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    group: str
    group_id: int | None = None
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    rate: str | None = Field(default=None, pattern=_RATE_PATTERN)


class _MetricResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start: dt.date = Field(description="First day, inclusive (UTC).")
    end: dt.date = Field(description="Last day, inclusive (UTC).")
    group_by: GroupBy | None = None
    numerator: int = Field(ge=0, description="Whole-range numerator, ungrouped.")
    denominator: int = Field(ge=0, description="Whole-range denominator, ungrouped.")
    rate: str | None = Field(default=None, pattern=_RATE_PATTERN)
    groups: list[GroupRate] | None = None
    group_count: int | None = Field(default=None, ge=0, description="Groups before the cap.")
    truncated: bool = False

    @model_validator(mode="after")
    def _consistent(self):
        if self.start > self.end:
            raise ValueError("start must not be after end")
        if (self.group_by is None) != (self.groups is None):
            raise ValueError("groups are present exactly when group_by is set")
        if self.groups is not None:
            if len(self.groups) > MAX_GROUPS:
                raise ValueError(f"at most {MAX_GROUPS} groups")
            if self.truncated != (self.group_count > len(self.groups)):
                raise ValueError("truncated must say whether groups were cut")
        return self


class IncidentRateResult(_MetricResult):
    """Incidents per 100 completed requests (§6).

    Numerator: incidents with `reported_at` in the range. Denominator: requests whose
    `archived_requests.completed_at` is in the range. The rate is per 100, so it can
    exceed 1. Grouped by technician, the numerator counts only incidents attributed to
    that technician (`attributed_technician_id`, ADR-033); the denominator counts that
    technician's completed jobs.
    """

    metric: Literal["incident_rate"] = "incident_rate"
    per: Literal[100] = 100


class SlaComplianceResult(_MetricResult):
    """Share of dispatched requests completed within their SLA window (§6).

    Denominator: requests with `dispatched_at` in the range and a non-null `sla_met`,
    so requests never dispatched or not completed are excluded. Numerator: those with
    `completed_at <= dispatched_at + sla_window_minutes`.
    """

    metric: Literal["sla_compliance"] = "sla_compliance"


class FirstTimeFixResult(_MetricResult):
    """Share of completed requests with no follow-up visit (§6).

    Denominator: requests whose `completed_at` is in the range. Numerator: those with no
    non-cancelled child request (`parent_request_id` pointing back), whatever the
    child's date. A cancelled follow-up does not count against its parent.
    """

    metric: Literal["first_time_fix_rate"] = "first_time_fix_rate"
