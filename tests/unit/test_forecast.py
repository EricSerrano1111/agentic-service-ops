"""The forecast protocol's pieces (ADR-069), on hand-built and synthetic data. Assembled.

No project data and no database: synthetic series with a planted K and a planted outlier,
and hand-computed metrics. The live series is covered by the evaluation runs.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("statsmodels")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from ml.forecast import baseline, data, evaluate, ledger, metrics, model  # noqa: E402

UTC = dt.UTC


def synthetic(k: int = 2, noise: float = 0.03, seed: int = 7, n: int = 156) -> np.ndarray:
    """exp(4.8 + 0.001 t + planted harmonics + noise): K = `k` pairs are real."""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    amp = [(0.25, 0.15), (0.10, -0.08), (0.06, 0.05)]
    log = 4.8 + 0.001 * t + rng.normal(0, noise, n)
    for j in range(1, k + 1):
        a, b = amp[j - 1]
        log += a * np.sin(2 * math.pi * j * t / model.PERIOD) + b * np.cos(
            2 * math.pi * j * t / model.PERIOD
        )
    return np.round(np.exp(log)).astype(np.int64)


# --------------------------------------------------------------------------- series and design


def test_weeks_are_monday_start_utc_over_156_weeks():
    assert dt.date(2023, 9, 4) == data.WINDOW_START and data.N_WEEKS == 156
    assert data.week_of(dt.datetime(2023, 9, 4, 0, 0, tzinfo=UTC)) == 0
    assert data.week_of(dt.datetime(2023, 9, 10, 23, 59, tzinfo=UTC)) == 0  # Sunday
    assert data.week_of(dt.datetime(2023, 9, 11, 0, 0, tzinfo=UTC)) == 1
    # Late Sunday in New York is already Monday in UTC: the week follows UTC.
    ny = dt.timezone(dt.timedelta(hours=-4))
    assert data.week_of(dt.datetime(2023, 9, 10, 21, 0, tzinfo=ny)) == 1
    assert data.week_start(155) == dt.date(2026, 8, 24)
    assert data.week_of(dt.datetime(2026, 8, 30, 23, 0, tzinfo=UTC)) == 155


def test_weekly_series_counts_total_and_each_type_and_drops_outside_weeks():
    rows = [
        (dt.datetime(2023, 9, 5, tzinfo=UTC), "repair"),
        (dt.datetime(2023, 9, 6, tzinfo=UTC), "install"),
        (dt.datetime(2023, 9, 12, tzinfo=UTC), "repair"),
        (dt.datetime(2026, 8, 31, tzinfo=UTC), "repair"),  # after the window
    ]
    s = data.weekly_series(rows)
    assert list(s) == ["total", "install", "repair"]
    assert (s["total"][:2].tolist(), s["repair"][:2].tolist(), int(s["total"].sum())) == (
        [2, 1],
        [1, 1],
        3,
    )
    assert data.series_sha256(s["total"]) != data.series_sha256(s["repair"])


def test_design_matrix_on_a_known_date_range():
    """Weeks of 2023-09-04 and 2024-09-02 (indices 0 and 52), K = 1, by hand."""
    t = np.array(
        [
            data.week_of(dt.datetime(2023, 9, 4, tzinfo=UTC)),
            data.week_of(dt.datetime(2024, 9, 2, tzinfo=UTC)),
        ]
    )
    assert t.tolist() == [0, 52]
    x = model.design(t, 1)
    angle = 2 * math.pi * 52 / 52.1775
    assert x[0].tolist() == [1.0, 0.0, 0.0, 1.0]
    assert x[1] == pytest.approx([1.0, 52.0, math.sin(angle), math.cos(angle)])
    assert model.design(t, 6).shape == (2, 14) and model.design(t, 0).shape == (2, 2)


# --------------------------------------------------------------------------- K, robust fit, horizon


def test_k_selection_recovers_a_planted_k():
    y = synthetic(k=2)
    k, scores = model.select_k(np.log(y), np.arange(156))
    assert k == 2
    assert set(scores) == set(range(7))


def test_robust_fit_downweights_a_planted_outlier():
    y = synthetic(k=2).copy()
    y[60] = round(y[60] * 0.4)  # a one-week collapse
    f = model.fit(y, np.arange(156))
    assert f.weights[60] < 0.5
    assert 60 in f.downweighted().tolist()
    assert int(np.argmin(f.weights)) == 60  # the collapse gets the smallest weight


def test_intervals_nest_around_the_median_and_horizon_is_capped():
    f = model.fit(synthetic(k=2)[:130], np.arange(130))
    fc = model.forecast(f, np.arange(130, 156))
    assert (fc["lo95"] < fc["lo80"]).all() and (fc["lo80"] < fc["median"]).all()
    assert (fc["median"] < fc["hi80"]).all() and (fc["hi80"] < fc["hi95"]).all()
    with pytest.raises(model.HorizonError):
        model.forecast(f, np.arange(130, 157))  # 27 weeks
    with pytest.raises(model.HorizonError):
        model.forecast(f, np.array([129]))  # inside the training window


def test_log_model_refuses_a_zero_week():
    y = synthetic(k=1)
    y[3] = 0
    with pytest.raises(ValueError, match="positive counts"):
        model.fit(y, np.arange(156))


# --------------------------------------------------------------------------- windows and leakage


def test_windows_match_adr_069():
    assert (evaluate.FOLD_A.origin, evaluate.FOLD_A.test_weeks[[0, -1]].tolist()) == (52, [52, 77])
    assert (evaluate.FOLD_B.origin, evaluate.FOLD_B.test_weeks[[0, -1]].tolist()) == (
        104,
        [104, 129],
    )
    assert (evaluate.HOLDOUT.origin, evaluate.HOLDOUT.test_weeks[[0, -1]].tolist()) == (
        130,
        [130, 155],
    )
    assert evaluate.FOLD_B.test_weeks[-1] < evaluate.HOLDOUT.origin  # folds end first
    assert (evaluate.FOLD_A.gated, evaluate.FOLD_B.gated) == (False, True)


def test_origin_assertion_fires_on_leakage():
    evaluate.assert_no_leakage(np.arange(0, 52), 52)
    with pytest.raises(evaluate.LeakageError, match="at or after the origin"):
        evaluate.assert_no_leakage(np.arange(0, 53), 52)


def test_a_window_fit_never_sees_its_test_weeks():
    """Changing every week from the origin on leaves the fold's fit unchanged."""
    y = synthetic(k=2)
    a = evaluate.evaluate_slice(y, evaluate.FOLD_B)
    y2 = y.copy()
    y2[104:] = y2[104:] * 3
    b = evaluate.evaluate_slice(y2, evaluate.FOLD_B)
    assert a["k"] == b["k"] and a["robust_scale"] == b["robust_scale"]
    assert [w["median"] for w in a["weeks"]] == [w["median"] for w in b["weeks"]]


# --------------------------------------------------------------------------- baseline and metrics


def test_seasonal_naive_is_the_week_52_earlier():
    counts = np.arange(200)
    assert baseline.seasonal_naive(counts, 100, np.arange(100, 104)).tolist() == [48, 49, 50, 51]
    with pytest.raises(ValueError):
        baseline.seasonal_naive(counts, 100, np.array([152]))  # would read week 100


def test_metrics_against_hand_computation():
    """APE 10%, 10%, 0%, 25% -> MAPE 11.25; squared errors 100, 400, 0, 400 -> RMSE 15."""
    y, yhat = np.array([100, 200, 50, 80]), np.array([110, 180, 50, 100])
    assert metrics.mape(y, yhat) == pytest.approx(11.25)
    assert metrics.rmse(y, yhat) == pytest.approx(15.0)
    assert metrics.coverage(y, y - 5, y + 5) == 1.0
    assert metrics.coverage(y, yhat, yhat) == 0.25  # only the exact hit


def test_band_scores_split_by_horizon():
    """26 weeks of 100; forecasts 110 in weeks 1-4 only: band 1-4 MAPE 10, others 0."""
    y = np.full(26, 100.0)
    yhat = y.copy()
    yhat[:4] = 110
    s = metrics.scores(y, yhat)
    assert (s["1-4"]["mape"], s["5-13"]["mape"], s["14-26"]["mape"]) == (10.0, 0.0, 0.0)
    assert (s["1-4"]["n"], s["5-13"]["n"], s["14-26"]["n"]) == (4, 9, 13)
    assert s["overall"]["mape"] == pytest.approx(40 / 26)


@pytest.mark.parametrize(
    ("model_mape", "naive_mape", "passes", "n_reasons"),
    [
        (25.0, 30.0, True, 0),  # under the ceiling and better than naive
        (30.0, 30.0, True, 0),  # at the ceiling and equal to naive: "at most", "no higher"
        (31.0, 40.0, False, 1),  # above the ceiling only
        (20.0, 15.0, False, 1),  # worse than naive only
        (35.0, 20.0, False, 2),  # both
    ],
)
def test_gate_v1_rule_branches(model_mape, naive_mape, passes, n_reasons):
    g = metrics.gate_v1(model_mape, naive_mape)
    assert (g["pass"], len(g["reasons"])) == (passes, n_reasons)


# --------------------------------------------------------------------------- ledger


def test_the_ledger_refuses_a_second_holdout_scoring(tmp_path):
    path = tmp_path / "test_ledger.jsonl"
    ledger.append({"model": "loglinear_robust_v1", "mape": 9.1}, path)
    ledger.append({"model": "seasonal_naive", "mape": 11.0}, path)
    with pytest.raises(ledger.LedgerRefusal, match="already scored on the holdout"):
        ledger.append({"model": "loglinear_robust_v1", "mape": 8.0}, path)
    assert [json.loads(x)["model"] for x in path.read_text().splitlines()] == [
        "loglinear_robust_v1",
        "seasonal_naive",
    ]


def test_git_dirty_ignores_the_ledger_only(tmp_path):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    path = tmp_path / "evals" / "results" / "forecast" / "test_ledger.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text('{"model": "a"}\n')
    (tmp_path / "code.py").write_text("x = 1\n")
    git("init", "-q")
    git("-c", "user.name=t", "-c", "user.email=t@t", "add", ".")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init")
    path.write_text('{"model": "a"}\n{"model": "b"}\n')
    assert ledger.git_state(tmp_path, path)[1] is False
    (tmp_path / "code.py").write_text("x = 2\n")
    assert ledger.git_state(tmp_path, path)[1] is True


# --------------------------------------------------------------------------- ADR-070


def _week(d: dt.date) -> int:
    return (d - data.WINDOW_START).days // 7


@pytest.mark.parametrize(
    ("monday", "expected"),
    [
        (dt.date(2023, 12, 18), 0),
        (dt.date(2023, 12, 25), 1),  # contains Dec 25 (a Monday); Jan 1 is next week
        (dt.date(2024, 1, 1), 1),  # contains Jan 1 (a Monday)
        (dt.date(2024, 1, 8), 0),
        (dt.date(2024, 12, 16), 0),
        (dt.date(2024, 12, 23), 1),  # Dec 25 is a Wednesday
        (dt.date(2024, 12, 30), 1),  # Jan 1 2025 is a Wednesday: a different week
        (dt.date(2025, 1, 6), 0),
        (dt.date(2026, 12, 21), 1),  # past the window: forecast weeks use the same calendar
        (dt.date(2026, 12, 28), 1),
        (dt.date(2027, 1, 4), 0),
    ],
)
def test_year_end_indicator_around_year_ends(monday, expected):
    assert model.year_end_indicator(np.array([_week(monday)])).tolist() == [expected]


def test_dec_25_and_jan_1_always_fall_in_different_weeks_so_two_per_year_end():
    t = np.arange(data.N_WEEKS)
    weeks = [data.week_start(w).isoformat() for w in t[model.year_end_indicator(t) == 1]]
    assert weeks == [
        "2023-12-25",
        "2024-01-01",
        "2024-12-23",
        "2024-12-30",
        "2025-12-22",
        "2025-12-29",
    ]


def test_year_end_column_only_in_v2_and_v1_design_unchanged():
    t = np.array([_week(dt.date(2024, 12, 23)), _week(dt.date(2024, 12, 16))])
    v1, v2 = model.design(t, 1), model.design(t, 1, year_end=True)
    assert v1.shape == (2, 4) and v2.shape == (2, 5)
    assert v2[:, 2].tolist() == [1.0, 0.0]
    assert np.array_equal(np.delete(v2, 2, axis=1), v1)


def test_year_end_fit_recovers_a_planted_dip():
    t = np.arange(156)
    y = np.round(synthetic(k=2) * np.exp(-0.3 * model.year_end_indicator(t))).astype(np.int64)
    f = model.fit(y, t, year_end=True)
    effect = f.year_end_effect()
    assert effect["coef"] == pytest.approx(-0.3, abs=0.08)
    assert effect["ci95"][0] < -0.3 < effect["ci95"][1]
    assert model.fit(y, t).year_end_effect() is None  # v1 has no indicator


def _scores(overall: float, bands: tuple[float, float, float]) -> dict:
    out = {"overall": {"mape": overall}}
    out.update({b: {"mape": m} for b, m in zip(metrics.BANDS, bands, strict=True)})
    return out


@pytest.mark.parametrize(
    ("model_26", "naive_26", "bands", "eligible", "passes"),
    [
        (9.7, 10.6, (11.9, 5.5, 11.9), True, [True, True, True]),  # v1's total on fold B
        (10.0, 10.0, (20.0, 5.0, 20.0), True, [True, True, True]),  # "no higher", "at most"
        (10.0, 12.0, (20.1, 5.0, 25.0), True, [False, True, False]),  # band ceiling only
        (12.0, 11.0, (5.0, 5.0, 5.0), False, [False, False, False]),  # ineligible slice
    ],
)
def test_corrected_gate_branches(model_26, naive_26, bands, eligible, passes):
    g = metrics.gate(_scores(model_26, bands), _scores(naive_26, (0, 0, 0)))
    assert g["eligible"] is eligible
    assert [g["bands"][b]["pass"] for b in metrics.BANDS] == passes


V1_FOLDS = REPO_ROOT / "evals" / "results" / "forecast" / "2026-10-02_folds"


@pytest.mark.skipif(not V1_FOLDS.exists(), reason="committed v1 fold results not present")
def test_gate_v1_reproduces_the_committed_v1_verdicts_exactly():
    fold_b = json.loads((V1_FOLDS / "fold_B.json").read_text(encoding="utf-8"))
    recorded = json.loads((V1_FOLDS / "gate.json").read_text(encoding="utf-8"))
    assert evaluate.gate_table_v1(fold_b["slices"]) == recorded["slices"]
    assert [b for b, g in recorded["slices"]["total"].items() if not g["pass"]] == ["1-4", "14-26"]
