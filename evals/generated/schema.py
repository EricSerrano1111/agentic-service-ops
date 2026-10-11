"""Item schema of brief_v1.md (ADR-094), as a Pydantic model. `schema.json` is exported from it.

Validation here is per item: a bad item is a filter removal, never a retry (plan.md).
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

Category = Literal[
    "clear_reporting",
    "clear_sentiment",
    "clear_forecast",
    "underspecified",
    "ambiguous",
    "multi_domain",
    "out_of_scope",
    "near_miss",
    "technician",
    "filtered",
    "unsupported_in_area",
]
Route = Literal["reporting", "sentiment", "forecast", "multi_domain", "ambiguous", "out_of_scope"]
Area = Literal["reporting", "sentiment", "forecast"]
Measure = Literal[
    "incident_count",
    "incident_rate",
    "sla_compliance",
    "first_time_fix_rate",
    "followup_drivers",
    "sentiment_mix",
    "sentiment_trend",
    "example_comments",
    "weekly_volume",
    "other",
]
Region = Literal["northeast", "southeast", "central", "west", "unsupported"]
Breakdown = Literal[
    "account", "region", "work_type", "technician", "incident_type", "severity", "month", "quarter"
]
WorkType = Literal["install", "repair", "maintenance", "inspection", "upgrade"]
SentimentLabel = Literal["positive", "neutral", "negative", "mixed"]

#: Categories whose `intent` is null; every other category carries one.
NULL_INTENT_CATEGORIES = frozenset({"ambiguous", "multi_domain", "out_of_scope", "near_miss"})
#: Categories whose `candidate_areas` has at least two entries; every other category: empty.
CANDIDATE_CATEGORIES = frozenset({"ambiguous", "multi_domain"})

MEASURES_BY_AREA: dict[str, frozenset[str]] = {
    "reporting": frozenset(
        {
            "incident_count",
            "incident_rate",
            "sla_compliance",
            "first_time_fix_rate",
            "followup_drivers",
            "other",
        }
    ),
    "sentiment": frozenset({"sentiment_mix", "sentiment_trend", "example_comments", "other"}),
    "forecast": frozenset({"weekly_volume", "other"}),
}


class Intent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    area: Area
    measure: Measure | None
    period_stated: bool
    period_text: str | None
    period_start: dt.date | None
    period_end: dt.date | None
    horizon_weeks: int | None
    region: Region | None
    account_name: str | None
    technician_name: str | None
    breakdown: Breakdown | None
    work_type: WorkType | None
    sentiment_label: SentimentLabel | None
    examples_requested: bool

    @model_validator(mode="after")
    def _measure_fits_area(self) -> Self:
        if self.measure is not None and self.measure not in MEASURES_BY_AREA[self.area]:
            raise ValueError(f"measure {self.measure!r} does not belong to area {self.area!r}")
        return self


class Item(BaseModel):
    """`intent` is required as a key and may be null."""

    model_config = ConfigDict(extra="forbid")

    id: str
    category: Category
    question: str
    expected_route: Route
    candidate_areas: list[Area]
    intent: Intent | None
    rationale: str

    @model_validator(mode="after")
    def _category_rules(self) -> Self:
        if not self.question.strip():
            raise ValueError("empty question")
        null_intent = self.category in NULL_INTENT_CATEGORIES
        if null_intent and self.intent is not None:
            raise ValueError(f"intent must be null for {self.category}")
        if not null_intent and self.intent is None:
            raise ValueError(f"intent must be set for {self.category}")
        if self.category in CANDIDATE_CATEGORIES:
            if len(set(self.candidate_areas)) < 2:
                raise ValueError(f"{self.category} needs at least 2 candidate_areas")
        elif self.candidate_areas:
            raise ValueError(f"candidate_areas must be empty for {self.category}")
        return self


def export_json_schema(path: Path | None = None) -> dict:
    schema = Item.model_json_schema()
    if path is not None:
        path.write_text(
            json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
        )
    return schema


if __name__ == "__main__":
    export_json_schema(Path(__file__).with_name("schema.json"))
