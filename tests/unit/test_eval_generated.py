"""evals/generated: period resolution, item schema and route mapping (ADR-094)."""

from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from pathlib import Path

import pytest

GEN = Path(__file__).resolve().parents[2] / "evals" / "generated"
AS_OF = dt.date(2026, 8, 30)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"evalgen_{name}", GEN / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


periods = _load("periods")
schema = _load("schema")
mapping = _load("mapping")
D = dt.date


@pytest.mark.parametrize(
    ("text", "area", "start", "end"),
    [
        ("last month", "reporting", D(2026, 7, 1), D(2026, 7, 31)),
        ("in July 2026", "sentiment", D(2026, 7, 1), D(2026, 7, 31)),
        ("this month", "reporting", D(2026, 8, 1), D(2026, 8, 30)),
        ("last quarter", "reporting", D(2026, 4, 1), D(2026, 6, 30)),
        ("the past 30 days", "reporting", D(2026, 8, 1), D(2026, 8, 30)),
        ("Q2 2026?", "sentiment", D(2026, 4, 1), D(2026, 6, 30)),
        ("next month", "forecast", D(2026, 9, 1), D(2026, 9, 30)),
        ("the next 6 weeks", "forecast", D(2026, 8, 31), D(2026, 10, 11)),
        ("September", "forecast", D(2026, 9, 1), D(2026, 9, 30)),
        ("January", "forecast", D(2027, 1, 1), D(2027, 1, 31)),
        ("Q4", "forecast", D(2026, 10, 1), D(2026, 12, 31)),
        ("Q1", "forecast", D(2027, 1, 1), D(2027, 3, 31)),
    ],
)
def test_recognised_phrases(text, area, start, end):
    res = periods.resolve_period(text, AS_OF, area)
    assert res is not None
    assert (res.start, res.end) == (start, end)


@pytest.mark.parametrize(
    ("text", "area"),
    [
        ("July", "reporting"),  # bare month in a past question: L-38
        ("this quarter", "reporting"),  # not defined by ADR-050
        ("year to date", "reporting"),
        ("the past 4 weeks", "sentiment"),
        ("last month", "forecast"),  # a past phrase in a forecast question
        ("August", "forecast"),  # the current month: not guessed
        ("Q3", "forecast"),  # the current quarter: not guessed
        ("next quarter", "forecast"),
        ("recently", "reporting"),
        (None, "reporting"),
        ("last month", "other"),
    ],
)
def test_unrecognised_phrases_are_none(text, area):
    assert periods.resolve_period(text, AS_OF, area) is None


def _intent(**kw):
    base = {
        "area": "reporting",
        "measure": "incident_count",
        "period_stated": False,
        "period_text": None,
        "period_start": None,
        "period_end": None,
        "horizon_weeks": None,
        "region": None,
        "account_name": None,
        "technician_name": None,
        "breakdown": None,
        "work_type": None,
        "sentiment_label": None,
        "examples_requested": False,
    }
    return base | kw


def test_check_item_period():
    ok = _intent(
        period_stated=True,
        period_text="last month",
        period_start="2026-07-01",
        period_end="2026-07-31",
    )
    assert periods.check_item_period(ok, AS_OF) == (True, "ok")
    wrong = ok | {"period_end": "2026-07-30"}
    assert not periods.check_item_period(wrong, AS_OF)[0]
    assert not periods.check_item_period(ok | {"period_text": "July"}, AS_OF)[0]
    assert periods.check_item_period(_intent(), AS_OF)[0]
    assert not periods.check_item_period(_intent(period_text="last month"), AS_OF)[0]


def test_check_forecast_horizon():
    weeks = _intent(
        area="forecast",
        measure="weekly_volume",
        period_stated=True,
        period_text="next 6 weeks",
        period_start="2026-08-31",
        period_end="2026-10-11",
        horizon_weeks=6,
    )
    assert periods.check_item_period(weeks, AS_OF)[0]
    assert not periods.check_item_period(weeks | {"horizon_weeks": 5}, AS_OF)[0]
    month = weeks | {
        "period_text": "next month",
        "period_start": "2026-09-01",
        "period_end": "2026-09-30",
        "horizon_weeks": 5,
    }
    assert periods.check_item_period(month, AS_OF)[0]
    assert not periods.check_item_period(month | {"horizon_weeks": 9}, AS_OF)[0]
    bare = _intent(area="forecast", measure="weekly_volume", horizon_weeks=40)
    assert not periods.check_item_period(bare, AS_OF)[0]


def _item(**kw):
    base = {
        "id": "X-01",
        "category": "clear_reporting",
        "question": "How many incidents last month?",
        "expected_route": "reporting",
        "candidate_areas": [],
        "intent": _intent(),
        "rationale": "one area",
    }
    return base | kw


def test_schema_accepts_valid_items():
    schema.Item.model_validate(_item())
    schema.Item.model_validate(
        _item(
            category="ambiguous",
            expected_route="ambiguous",
            intent=None,
            candidate_areas=["reporting", "sentiment"],
        )
    )


@pytest.mark.parametrize(
    "bad",
    [
        _item(intent=None),  # intent required for a clear category
        _item(category="near_miss", expected_route="out_of_scope"),  # intent must be null
        _item(
            category="ambiguous",
            expected_route="ambiguous",
            intent=None,
            candidate_areas=["reporting"],
        ),
        _item(candidate_areas=["reporting", "sentiment"]),  # must be empty
        _item(category="bogus"),
        _item(intent=_intent(region="midwest")),
        _item(intent=_intent(measure="weekly_volume")),  # not a reporting measure
        _item(unexpected="x"),
        _item(question="  "),
    ],
)
def test_schema_rejects_invalid_items(bad):
    with pytest.raises(ValueError):
        schema.Item.model_validate(bad)


def test_schema_requires_intent_key_and_allows_other_measure_and_unsupported_region():
    no_key = _item(category="out_of_scope", expected_route="out_of_scope")
    del no_key["intent"]
    with pytest.raises(ValueError):
        schema.Item.model_validate(no_key)
    schema.Item.model_validate(
        _item(intent=_intent(measure="other", region="unsupported")),
    )


def test_schema_json_is_current():
    import json

    assert json.loads((GEN / "schema.json").read_text(encoding="utf-8")) == json.loads(
        json.dumps(schema.Item.model_json_schema())
    )


def test_mapping_is_total_over_the_brief_routes():
    for route in (
        "reporting",
        "sentiment",
        "forecast",
        "multi_domain",
        "ambiguous",
        "out_of_scope",
    ):
        assert mapping.system_route(route) == route
    with pytest.raises(ValueError):
        mapping.system_route("billing")
    assert mapping.CATEGORY_ROUTE["near_miss"] == "out_of_scope"
