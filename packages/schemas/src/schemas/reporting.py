"""The reporting agent's parsed request and its answer payload (ADR-046, ADR-050)."""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .incidents import IncidentSummary
from .metrics import FirstTimeFixResult, IncidentRateResult, SlaComplianceResult

#: What the parsing call may ask for. "unsupported" lets the model say a question asks
#: for a metric or breakdown the agent doesn't offer, instead of guessing the nearest.
Metric = Literal[
    "incident_count", "incident_rate", "sla_compliance", "first_time_fix_rate", "unsupported"
]
RequestGroupBy = Literal["account", "region", "service_type", "technician", "unsupported"]

Figures = Annotated[
    IncidentSummary | IncidentRateResult | SlaComplianceResult | FirstTimeFixResult,
    Field(discriminator="metric"),
]

# The history window of the loaded dataset (data/generator/parameters.py, Window): 156
# weeks from Monday 2023-09-04, ending Monday 2026-08-31 00:00 UTC, so the last day
# inside it is 2026-08-30. The MCP server validates ranges against it; the reporting
# agent's as-of date defaults to its end (ADR-050). A unit test holds these to the
# generator's parameters.
DATASET_WINDOW_START = dt.date(2023, 9, 4)
DATASET_WINDOW_END = dt.date(2026, 8, 30)


class ReportingRequest(BaseModel):
    """What the parsing call extracts from the question: the metric, an optional
    breakdown, and an inclusive date range, or no dates when the question states none.
    It never guesses a default range: code applies that (ADR-050). The agent, not the
    model, picks the tool from `metric`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    metric: Metric
    group_by: RequestGroupBy | None = None
    start: dt.date | None = Field(default=None, description="First day, inclusive.")
    end: dt.date | None = Field(default=None, description="Last day, inclusive.")

    @model_validator(mode="after")
    def _both_or_neither(self) -> ReportingRequest:
        if (self.start is None) != (self.end is None):
            raise ValueError("give both start and end, or neither")
        return self


class ReportingAnswer(BaseModel):
    """The data part of the reporting agent's artifact: what was asked, how it was read,
    and the figures. The orchestrator validates it on receipt (architecture §11)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request: ReportingRequest  # as parsed from the question
    start: dt.date  # the range actually queried
    end: dt.date
    range_assumed: bool  # True when the question named no dates (ADR-050 default)
    as_of: dt.date
    figures: Figures

    @model_validator(mode="after")
    def _consistent(self) -> ReportingAnswer:
        if (self.figures.start, self.figures.end) != (self.start, self.end):
            raise ValueError("figures must cover the queried range")
        if self.figures.metric != self.request.metric:
            raise ValueError("figures must be for the requested metric")
        if getattr(self.figures, "group_by", None) != self.request.group_by:
            raise ValueError("figures must use the requested breakdown")
        if self.range_assumed != (self.request.start is None):
            raise ValueError("range_assumed must match whether the request had dates")
        return self
