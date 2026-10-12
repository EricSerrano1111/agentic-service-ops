"""QA's recompute of served forecast numbers (ADR-095, data dictionary §6, "Forecast recompute
(QA)"): each formula, the display rule and the boundary rule, the total from unrounded points,
the unchecked items, and what happens when the parameter files are wrong.

The records are synthetic (the real `volume_v2` files are not in git); the equivalence of this
code with `forecast_runtime` on them, and on the real files when present, is
`tests/unit/test_qa_forecast_equivalence.py`.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from pathlib import Path

import pytest
from agent_forecast.render import render_answer
from agent_qa.forecast import Checker, Manifest, band_name
from agent_qa.forecast_model import BOUNDARY_REL_TOL, ForecastModel, ModelUnavailable
from qa_fakes import AS_OF, SETTINGS, FakeSource, manifest
from schemas import BandVerdict, ForecastAnswer, ForecastRequest, ForecastWeek

REAL = manifest()
Z80, Z95 = 1.2815515655446004, 1.959963984540054


def record(slice_: str = "total", **over) -> dict:
    """k=1, no year-end term: width 4, a diagonal A so the leverage is easy to compute by hand."""
    rec = {
        "slice": slice_,
        "k": 1,
        "year_end": False,
        "params": [4.0, 0.002, 0.05, -0.03],
        "scale": 0.1,
        "xtwx_inv": [
            [0.02, 0, 0, 0],
            [0, 0.00001, 0, 0],
            [0, 0, 0.03, 0],
            [0, 0, 0, 0.04],
        ],
        "last_t": 155,
        "period": 52.1775,
        "horizon_cap": 26,
    }
    return rec | over


def write_model(tmp_path: Path, recs: list[dict]) -> dict:
    """Write the records and return a manifest document whose `files` hashes match them."""
    doc = json.loads(_manifest_path().read_text(encoding="utf-8"))
    doc["files"] = {}
    for rec in recs:
        name = f"{rec['slice']}.json"
        raw = json.dumps(rec).encode()
        (tmp_path / name).write_bytes(raw)
        doc["files"][name] = hashlib.sha256(raw).hexdigest()
    return doc


def _manifest_path() -> Path:
    from qa_fakes import MANIFEST_PATH

    return MANIFEST_PATH


def hand(rec: dict, h: int, start=dt.date(2023, 9, 4)) -> dict:
    """The formulas of §6 written out once more, for k=1 and no year-end term."""
    t = rec["last_t"] + h
    x = [1.0, float(t)]
    for j in range(1, rec["k"] + 1):
        a = 2 * math.pi * j * t / rec["period"]
        x += [math.sin(a), math.cos(a)]
    mu = sum(c * b for c, b in zip(x, rec["params"], strict=True))
    lev = sum(x[i] * x[i] * rec["xtwx_inv"][i][i] for i in range(len(x)))
    se = rec["scale"] * math.sqrt(1 + lev)
    return {
        "point": math.exp(mu),
        "lo80": math.exp(mu - Z80 * se),
        "hi80": math.exp(mu + Z80 * se),
        "lo95": math.exp(mu - Z95 * se),
        "hi95": math.exp(mu + Z95 * se),
    }


@pytest.fixture
def model(tmp_path) -> ForecastModel:
    doc = write_model(tmp_path, [record("total")])
    return ForecastModel.load(tmp_path, doc)


# --------------------------------------------------------------------------- formulas


@pytest.mark.parametrize("h", [1, 2, 13, 26])
def test_each_formula_matches_a_hand_computation(model, h):
    got = model.predict("total", h)
    want = hand(record(), h)
    for key, value in want.items():
        assert got[key] == pytest.approx(value, rel=1e-12), key


def test_intervals_widen_with_the_level_and_contain_the_point(model):
    w = model.predict("total", 5)
    assert w["lo95"] < w["lo80"] < w["point"] < w["hi80"] < w["hi95"]


def test_the_year_end_indicator_enters_only_for_marked_weeks(tmp_path):
    rec = record(
        year_end=True,
        k=0,
        params=[4.0, 0.001, -0.2],
        xtwx_inv=[[0.01, 0, 0], [0, 0, 0], [0, 0, 0.01]],
    )
    doc = write_model(tmp_path, [rec])
    m = ForecastModel.load(tmp_path, doc)
    # trained_on[0] 2023-09-04 + t weeks; t = 155 + h. h=17 is the week of 2026-12-21
    # (contains Dec 25), so the indicator is 1 and the point is exp(4 + 0.001 t - 0.2).
    t = 155 + 17
    assert dt.date(2023, 9, 4) + dt.timedelta(weeks=t) == dt.date(2026, 12, 21)
    assert m.predict("total", 17)["point"] == pytest.approx(math.exp(4.0 + 0.001 * t - 0.2))
    t = 155 + 5
    assert m.predict("total", 5)["point"] == pytest.approx(math.exp(4.0 + 0.001 * t))


def test_a_horizon_outside_one_to_26_is_refused(model):
    for h in (0, 27):
        with pytest.raises(ValueError):
            model.predict("total", h)


# --------------------------------------------------------------------------- display and boundary


def test_the_display_rule_is_nearest_whole_with_ties_to_even(model):
    assert model.same_when_displayed(10.4, 10.2)
    assert not model.same_when_displayed(10.6, 10.2)
    assert model.same_when_displayed(10.5, 10.4)  # 10.5 rounds to 10 (even), 10.4 to 10
    assert not model.same_when_displayed(11.5, 10.4)  # 11.5 rounds to 12


def test_inside_the_boundary_tolerance_either_neighbour_passes_and_it_is_counted(model):
    near = 100.5 * (1 + BOUNDARY_REL_TOL / 2)
    assert model.same_when_displayed(100.0, near)
    assert model.same_when_displayed(101.0, near)
    assert not model.same_when_displayed(102.0, near)
    assert model.boundary_fired == 3


def test_outside_the_tolerance_there_is_none(model):
    away = 100.5 * (1 + 10 * BOUNDARY_REL_TOL)
    assert model.same_when_displayed(101.0, away)
    assert not model.same_when_displayed(100.0, away)
    assert model.boundary_fired == 0


# --------------------------------------------------------------------------- the check


def answer_for(model: ForecastModel, horizons=range(1, 5)) -> ForecastAnswer:
    weeks = []
    for h in horizons:
        p = model.predict("total", h)
        weeks.append(
            ForecastWeek(
                week_start=REAL.week(h),
                horizon=h,
                band=band_name(h),
                served=True,
                point=p["point"],
                lo80=p["lo80"],
                hi80=p["hi80"],
                lo95=p["lo95"],
                hi95=p["hi95"],
            )
        )
    total = sum(w.point for w in weeks)
    return ForecastAnswer(**_dump(weeks, total, weeks[0].week_start, weeks[-1].week_start))


def _dump(weeks, total, first, last) -> dict:
    return {
        "request": ForecastRequest(slice="total", horizon_weeks=len(weeks)),
        "as_of": AS_OF,
        "trained_through": REAL.trained_through,
        "model_version": REAL.version,
        "range_assumed": False,
        "requested_first_week": first,
        "requested_last_week": last,
        "beyond_horizon_weeks": 0,
        "weeks": weeks,
        "bands": {
            "1-4": BandVerdict(
                served=True, shown_error=float(REAL.serving["total"]["1-4"]["shown_error"])
            )
        },
        "period_total": total,
        "year_end_weeks": [],
        "history": [],
    }


@pytest.fixture
def checker(model) -> Checker:
    m = Manifest(
        version=REAL.version,
        last_training_week=REAL.last_training_week,
        serving=REAL.serving,
        model=model,
    )
    return Checker(FakeSource(), SETTINGS, m)


def test_an_unmodified_answer_passes_and_says_what_it_did_not_check(checker, model):
    res = checker._recompute(answer_for(model))
    assert res.passed
    assert "unchecked" in res.detail and "total interval" in res.detail
    assert "lo95" not in res.detail and "hi95" not in res.detail  # compared since ADR-096


def test_a_changed_point_fails_naming_the_field_and_no_value(checker, model):
    a = answer_for(model)
    w = a.weeks[1]
    bumped = w.model_copy(update={"point": w.point + 3, "hi80": w.hi80 + 3, "lo80": w.lo80 + 3})
    a = a.model_copy(update={"weeks": [a.weeks[0], bumped, *a.weeks[2:]]})
    res = checker._recompute(a)
    assert not res.passed
    assert "point_differs_from_the_model" in res.detail
    assert str(round(bumped.point)) not in res.detail


def test_a_changed_range_end_fails(checker, model):
    a = answer_for(model)
    w = a.weeks[0].model_copy(update={"hi80": a.weeks[0].hi80 + 5})
    res = checker._recompute(a.model_copy(update={"weeks": [w, *a.weeks[1:]]}))
    assert not res.passed and "hi80_differs_from_the_model" in res.detail


def test_the_total_is_rounded_from_the_unrounded_sum_not_summed_from_rounded_weeks(model):
    # Three weeks whose points are x.4: the rounded weeks sum to 3x, the exact sum rounds to
    # 3x + 1. The answer that carries the exact sum's rounding must pass, the other must not.
    points = [100.4, 100.4, 100.4]
    assert sum(round(p) for p in points) == 300 and round(sum(points)) == 301
    assert model.same_when_displayed(301.2, sum(points))
    assert not model.same_when_displayed(300.0, sum(points))


def test_a_changed_total_fails(checker, model):
    a = answer_for(model)
    res = checker._recompute(a.model_copy(update={"period_total": a.period_total + 4}))
    assert not res.passed and "period_total_differs_from_the_model" in res.detail


def test_a_tampered_lo95_fails_naming_the_field_and_no_value(checker, model):
    """The 95% ends are compared like the 80% ends (owner ruling 2026-10-11, ADR-096)."""
    a = answer_for(model)
    w = a.weeks[0].model_copy(update={"lo95": a.weeks[0].lo95 - 1})
    res = checker._recompute(a.model_copy(update={"weeks": [w, *a.weeks[1:]]}))
    assert not res.passed
    assert "lo95_differs_from_the_model" in res.detail
    assert str(round(w.lo95)) not in res.detail


def test_a_tampered_hi95_fails_naming_the_field_and_no_value(checker, model):
    a = answer_for(model)
    w = a.weeks[0].model_copy(update={"hi95": a.weeks[0].hi95 + 1})
    res = checker._recompute(a.model_copy(update={"weeks": [w, *a.weeks[1:]]}))
    assert not res.passed
    assert "hi95_differs_from_the_model" in res.detail
    assert str(round(w.hi95)) not in res.detail


def test_a_95_end_inside_the_whole_number_rounding_passes(checker, model):
    """Same rule as the 80% ends: a value that rounds to the same whole request passes."""
    a = answer_for(model)
    want = model.predict(a.request.slice, a.weeks[0].horizon)["lo95"]
    w = a.weeks[0].model_copy(update={"lo95": round(want) + 0.2})
    if round(want) + 0.2 > a.weeks[0].lo80:
        pytest.skip("slice too narrow for the nudge to keep the ordering")
    res = checker._recompute(a.model_copy(update={"weeks": [w, *a.weeks[1:]]}))
    assert res.passed


def test_the_check_is_in_check_answer_when_a_model_is_loaded_and_absent_otherwise(checker, model):
    a = answer_for(model)
    text = render_answer(a)
    codes = {c.code for c in checker.check_answer(a, text)}
    assert "forecast_numbers_recomputed" in codes
    off = Checker(FakeSource(), SETTINGS, manifest())
    assert "forecast_numbers_recomputed" not in {c.code for c in off.check_answer(a, text)}


def test_an_altered_file_makes_the_model_unavailable(tmp_path):
    doc = write_model(tmp_path, [record("total")])
    (tmp_path / "total.json").write_bytes(b'{"slice": "total"}')
    with pytest.raises(ModelUnavailable, match="SHA-256"):
        ForecastModel.load(tmp_path, doc)


def test_a_missing_file_and_a_missing_parameter_make_it_unavailable(tmp_path):
    doc = write_model(tmp_path, [record("total")])
    (tmp_path / "total.json").unlink()
    with pytest.raises(ModelUnavailable, match="not readable"):
        ForecastModel.load(tmp_path, doc)
    broken = record("total")
    del broken["scale"]
    doc = write_model(tmp_path, [broken])
    with pytest.raises(ModelUnavailable, match="lacks a parameter"):
        ForecastModel.load(tmp_path, doc)


def test_manifest_load_with_a_model_dir_refuses_to_start_without_the_files(tmp_path):
    with pytest.raises(ModelUnavailable):
        Manifest.load(_manifest_path(), tmp_path)
