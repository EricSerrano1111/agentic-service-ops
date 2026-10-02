"""Fold and holdout evaluation, exactly as ADR-069 fixes it.

    python -m ml.forecast.evaluate folds   [--out-date YYYY-MM-DD]
    python -m ml.forecast.evaluate holdout [--out-date YYYY-MM-DD]

Windows (week indices from Monday 2023-09-04; each fitted only on weeks before its origin):
- Fold A: test 2024-09-02 to 2025-03-02, about one year of history. Reported, not gated.
- Fold B: test 2025-09-01 to 2026-03-01, about two years of history. Sets the gate.
- Headline holdout: test 2026-03-02 to 2026-08-30. Scored once per model (`ledger.py`).

Per slice (the total and each service type), for the model and seasonal naive: MAPE and
RMSE overall and by horizon band (1-4, 5-13, 14-26 weeks), and the model's 80% and 95%
interval coverage. `folds` also applies the release gate on fold B and exits non-zero if
the total slice fails any band (the stop rule). `holdout` refuses to run on a dirty tree
or for a model already in the ledger.

The planted anomaly periods are read as `app_eval` from `generation_parameters` *after*
fitting, only to say which fall in each window's training or test weeks. They never reach
the model (ADR-058, L-21).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ml.forecast import baseline, data, ledger, metrics, model

RESULTS = ledger.ROOT / "evals" / "results" / "forecast"
MODEL_NAME = "loglinear_robust_v1"
BASELINE_NAME = "seasonal_naive"


class LeakageError(AssertionError):
    """A fit saw a week at or after its origin."""


@dataclass(frozen=True)
class Window:
    name: str
    test_start: dt.date
    test_end: dt.date
    gated: bool

    @property
    def origin(self) -> int:
        return (self.test_start - data.WINDOW_START).days // 7

    @property
    def test_weeks(self) -> np.ndarray:
        last = (self.test_end - data.WINDOW_START).days // 7
        return np.arange(self.origin, last + 1)


FOLD_A = Window("fold_A", dt.date(2024, 9, 2), dt.date(2025, 3, 2), gated=False)
FOLD_B = Window("fold_B", dt.date(2025, 9, 1), dt.date(2026, 3, 1), gated=True)
HOLDOUT = Window("holdout", dt.date(2026, 3, 2), dt.date(2026, 8, 30), gated=False)


def assert_no_leakage(train_weeks: np.ndarray, origin: int) -> None:
    if len(train_weeks) and int(np.max(train_weeks)) >= origin:
        raise LeakageError(
            f"training week {int(np.max(train_weeks))} is at or after the origin {origin}"
        )


def evaluate_slice(counts: np.ndarray, window: Window) -> dict:
    """Fit on weeks before the origin, forecast the test weeks, score model and baseline."""
    train_t = np.arange(0, window.origin)
    assert_no_leakage(train_t, window.origin)
    f = model.fit(counts[train_t], train_t)
    assert_no_leakage(f.train_t, window.origin)
    test_t = window.test_weeks
    assert len(test_t) == 26 and test_t.min() == window.origin
    fc = model.forecast(f, test_t)
    naive = baseline.seasonal_naive(counts, window.origin, test_t)
    y = counts[test_t].astype(np.float64)
    return {
        "series_sha256": data.series_sha256(counts),
        "train": [data.week_start(0).isoformat(), data.week_start(window.origin - 1).isoformat()],
        "test": [window.test_start.isoformat(), window.test_end.isoformat()],
        "k": f.k,
        "aicc": {str(k): round(v, 4) for k, v in f.aicc.items()},
        "robust_scale": f.scale,
        "downweighted_weeks": [data.week_start(w).isoformat() for w in f.downweighted()],
        "model": metrics.scores(y, fc["median"]),
        "baseline": metrics.scores(y, naive),
        "coverage": {
            "80": metrics.coverage(y, fc["lo80"], fc["hi80"]),
            "95": metrics.coverage(y, fc["lo95"], fc["hi95"]),
        },
        "weeks": [
            {
                "week_start": data.week_start(w).isoformat(),
                "h": int(w - window.origin + 1),
                "actual": int(counts[w]),
                "median": round(float(fc["median"][i]), 4),
                "lo80": round(float(fc["lo80"][i]), 4),
                "hi80": round(float(fc["hi80"][i]), 4),
                "lo95": round(float(fc["lo95"][i]), 4),
                "hi95": round(float(fc["hi95"][i]), 4),
                "seasonal_naive": int(naive[i]),
            }
            for i, w in enumerate(test_t)
        ],
    }


def evaluate_window(series: dict[str, np.ndarray], window: Window) -> dict[str, dict]:
    return {name: evaluate_slice(counts, window) for name, counts in series.items()}


def gate_table(fold: dict[str, dict]) -> dict[str, dict[str, dict]]:
    """ADR-069's gate for every slice and band of one fold's results."""
    return {
        name: {
            band: {
                "model_mape": r["model"][band]["mape"],
                "naive_mape": r["baseline"][band]["mape"],
                "model_rmse": r["model"][band]["rmse"],
                "naive_rmse": r["baseline"][band]["rmse"],
                **metrics.gate(r["model"][band]["mape"], r["baseline"][band]["mape"]),
            }
            for band in metrics.BANDS
        }
        for name, r in fold.items()
    }


# --------------------------------------------------------------------------- reporting only


def anomaly_periods() -> dict[str, list[str]]:
    """The planted anomaly periods, as `app_eval`, for interpretation only (never modelled)."""
    from ml.sentiment.data import connect

    with connect("app_eval") as conn:
        rows = dict(
            conn.execute(
                "SELECT param_key, param_value FROM generation_parameters "
                "WHERE param_key IN ('anomalies.volume_drop', 'anomalies.regional_drop', "
                "'anomalies.billing_surcharge')"
            ).fetchall()
        )
    out = {}
    for key, v in rows.items():
        start = (
            dt.date.fromisoformat(v["start"]) if "start" in v else data.week_start(v["start_week"])
        )
        first = (start - data.WINDOW_START).days // 7
        out[key.split(".", 1)[1]] = [
            data.week_start(first).isoformat(),
            (data.week_start(first + int(v["n_weeks"])) - dt.timedelta(days=1)).isoformat(),
        ]
    return out


def placement(periods: dict[str, list[str]], window: Window) -> dict[str, str]:
    """Where each anomaly period falls relative to a window: train, test, both or neither."""
    out = {}
    for name, (first, last) in periods.items():
        a, b = dt.date.fromisoformat(first), dt.date.fromisoformat(last)
        in_train = a < window.test_start  # training is every week before the origin
        in_test = a <= window.test_end and b >= window.test_start
        if in_train and in_test:
            out[name] = "train and test"
        elif in_train:
            out[name] = "train"
        elif in_test:
            out[name] = "test"
        else:
            out[name] = "after test"
    return out


def _write(path: Path, obj) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, indent=2) + "\n"
    path.write_bytes(text.encode("utf-8"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_folds(out_date: str) -> int:
    series = data.load_series()
    periods = anomaly_periods()
    out = RESULTS / f"{out_date}_folds"
    for window in (FOLD_A, FOLD_B):
        result = evaluate_window(series, window)
        _write(
            out / f"{window.name}.json",
            {
                "evidence": "observed",
                "window": window.name,
                "gated": window.gated,
                "origin": window.test_start.isoformat(),
                "anomaly_placement": placement(periods, window),
                "slices": result,
            },
        )
        if window is FOLD_B:
            gates = gate_table(result)
    _write(
        out / "gate.json",
        {
            "evidence": "observed",
            "rule": "fold B, per slice and band: model MAPE <= 30% and <= seasonal naive MAPE "
            "(ADR-069)",
            "ceiling_mape": metrics.MAPE_CEILING,
            "anomaly_periods": periods,
            "slices": gates,
        },
    )
    total_fails = [b for b, g in gates["total"].items() if not g["pass"]]
    print(f"wrote {out}")
    if total_fails:
        print(f"STOP: the total slice fails the gate in band(s) {total_fails}", file=sys.stderr)
        return 1
    return 0


def run_holdout(out_date: str) -> int:
    commit, dirty = ledger.git_state()
    if dirty:
        raise SystemExit("the holdout runs on a clean commit only (ADR-069)")
    for name in (MODEL_NAME, BASELINE_NAME):
        ledger.check_not_scored(name)  # before the holdout is scored
    series = data.load_series()
    result = evaluate_window(series, HOLDOUT)
    periods = anomaly_periods()
    path = RESULTS / f"{out_date}_holdout" / "holdout.json"
    sha = _write(
        path,
        {
            "evidence": "observed",
            "window": HOLDOUT.name,
            "origin": HOLDOUT.test_start.isoformat(),
            "anomaly_placement": placement(periods, HOLDOUT),
            "slices": result,
        },
    )
    total = result[data.TOTAL]
    beats = total["model"]["overall"]["mape"] < total["baseline"]["overall"]["mape"]
    common = {
        "date": dt.date.today().isoformat(),
        "window": [HOLDOUT.test_start.isoformat(), HOLDOUT.test_end.isoformat()],
        "git_commit": commit,
        "git_dirty": dirty,
        "series_sha256": {n: r["series_sha256"] for n, r in result.items()},
        "results": path.relative_to(ledger.ROOT).as_posix(),
        "results_sha256": sha,
    }
    for name, key, config in (
        (
            MODEL_NAME,
            "model",
            {"adr": "ADR-069", "period": model.PERIOD, "k_range": [0, 6], "tukey_c": model.TUKEY_C},
        ),
        (BASELINE_NAME, "baseline", {"season_weeks": baseline.SEASON}),
    ):
        ledger.append(
            {
                **common,
                "model": name,
                "config": config,
                "mape_overall": {n: round(r[key]["overall"]["mape"], 4) for n, r in result.items()},
            }
        )
    print(f"wrote {path}; ledger appended ({MODEL_NAME}, {BASELINE_NAME})")
    print(f"beats seasonal naive on the total (ADR-069): {beats}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("what", choices=("folds", "holdout"))
    ap.add_argument("--out-date", default=dt.date.today().isoformat())
    args = ap.parse_args(argv)
    return run_folds(args.out_date) if args.what == "folds" else run_holdout(args.out_date)


if __name__ == "__main__":
    sys.exit(main())
