"""The volume forecast contracts: `mcp_volume`'s tool results and the forecast agent's
request and answer (ADR-072).

Served-only numbers: a forecast week in a slice-band the `volume_v2` manifest marks
unserved (ADR-071) carries its flag and nothing else; the validators reject a payload
that breaks that, so no layer can pass an unserved figure on.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ForecastSlice = Literal["total", "inspection", "install", "maintenance", "repair", "upgrade"]
FORECAST_SLICES: tuple[ForecastSlice, ...] = (
    "total",
    "inspection",
    "install",
    "maintenance",
    "repair",
    "upgrade",
)
HorizonBand = Literal["1-4", "5-13", "14-26"]
HORIZON_BANDS: tuple[HorizonBand, ...] = ("1-4", "5-13", "14-26")
MAX_HORIZON_WEEKS = 26
MAX_HISTORY_WEEKS = 52
ForecastUnsupported = Literal[
    "sla", "incidents", "sentiment", "region", "account", "technician", "past_period", "other"
]


def band_of(horizon: int) -> HorizonBand:
    if 1 <= horizon <= 4:
        return "1-4"
    if 5 <= horizon <= 13:
        return "5-13"
    if 14 <= horizon <= MAX_HORIZON_WEEKS:
        return "14-26"
    raise ValueError(f"horizon {horizon} is outside 1 to {MAX_HORIZON_WEEKS}")


class ForecastWeek(BaseModel):
    """One forecast week. The numbers are present exactly when the week's band is served."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    week_start: dt.date = Field(description="Monday of the week (UTC).")
    horizon: int = Field(ge=1, le=MAX_HORIZON_WEEKS)
    band: HorizonBand
    served: bool
    point: float | None = Field(default=None, description="Median forecast (requests).")
    lo80: float | None = None
    hi80: float | None = None
    lo95: float | None = None
    hi95: float | None = None

    @model_validator(mode="after")
    def _served_only_numbers(self) -> ForecastWeek:
        numbers = (self.point, self.lo80, self.hi80, self.lo95, self.hi95)
        if self.band != band_of(self.horizon):
            raise ValueError("band must match the horizon")
        if self.served and any(n is None for n in numbers):
            raise ValueError("a served week carries its point and both ranges")
        if not self.served and any(n is not None for n in numbers):
            raise ValueError("an unserved week carries no numbers (ADR-071, ADR-072)")
        return self


class BandVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    served: bool
    shown_error: float = Field(ge=0, description="The larger of fold B and holdout MAPE (%).")


class VolumeForecast(BaseModel):
    """`get_volume_forecast`: weekly forecasts for horizons 1..horizon_weeks."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_version: str = Field(description="SHA-256 of the volume_v2 manifest.")
    trained_through: dt.date
    slice: ForecastSlice
    horizon_weeks: int = Field(ge=1, le=MAX_HORIZON_WEEKS)
    weeks: list[ForecastWeek]
    bands: dict[HorizonBand, BandVerdict]
    year_end_weeks: list[dt.date] = Field(
        description="Weeks in the horizon that the year-end indicator marks (ADR-070)."
    )


class HistoryWeek(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    week_start: dt.date
    count: int = Field(ge=0)


class VolumeHistory(BaseModel):
    """`get_order_volume_history`: actual weekly counts, the most recent complete weeks."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    slice: ForecastSlice
    weeks: list[HistoryWeek]


class ForecastRequest(BaseModel):
    """What the parsing call extracts (ADR-072). Either a horizon in weeks or a target
    period; neither when the question names none, and code applies the default."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    slice: ForecastSlice = "total"
    horizon_weeks: int | None = Field(default=None, ge=1, le=520)
    period_start: dt.date | None = None
    period_end: dt.date | None = None
    want_history: bool = False
    unsupported: ForecastUnsupported | None = None

    @model_validator(mode="after")
    def _one_way_to_say_when(self) -> ForecastRequest:
        if (self.period_start is None) != (self.period_end is None):
            raise ValueError("give both period_start and period_end, or neither")
        if self.period_start and self.period_end and self.period_start > self.period_end:
            raise ValueError("period_start is after period_end")
        if self.horizon_weeks is not None and self.period_start is not None:
            raise ValueError("give a horizon or a period, not both")
        return self


class ForecastAnswer(BaseModel):
    """The data part of the forecast agent's artifact: everything the text shows."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request: ForecastRequest
    as_of: dt.date
    trained_through: dt.date
    model_version: str
    range_assumed: bool
    requested_first_week: dt.date
    requested_last_week: dt.date
    beyond_horizon_weeks: int = Field(ge=0, description="Requested weeks past the 26-week cap.")
    weeks: list[ForecastWeek] = Field(description="The requested weeks within the horizon.")
    bands: dict[HorizonBand, BandVerdict] = Field(description="Bands the shown weeks fall in.")
    period_total: float | None = Field(
        default=None, description="Sum of the weekly forecasts; only when every week is served."
    )
    year_end_weeks: list[dt.date] = Field(default_factory=list)
    history: list[HistoryWeek] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> ForecastAnswer:
        if self.request.unsupported is not None:
            raise ValueError("an unsupported request is declined, never answered")
        if {w.band for w in self.weeks} != set(self.bands):
            raise ValueError("bands must be exactly those of the shown weeks")
        if any(self.bands[w.band].served != w.served for w in self.weeks):
            raise ValueError("a week's served flag must match its band's")
        served = [w for w in self.weeks if w.served]
        if self.period_total is not None:
            if len(self.weeks) < 2 or len(served) != len(self.weeks):
                raise ValueError("a period total needs two or more weeks, all served")
            if abs(self.period_total - sum(w.point for w in served)) > 1e-6:
                raise ValueError("the period total is the sum of the weekly forecasts")
        if any(d not in {w.week_start for w in self.weeks} for d in self.year_end_weeks):
            raise ValueError("year_end_weeks must be among the shown weeks")
        if self.range_assumed != (
            self.request.horizon_weeks is None and self.request.period_start is None
        ):
            raise ValueError("range_assumed must match whether the request named a period")
        return self
