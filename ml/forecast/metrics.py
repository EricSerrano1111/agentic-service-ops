"""Forecast metrics and the release gates (ADR-069, ADR-070). Pure: no I/O.

MAPE (primary, in percent) and RMSE, overall and by horizon band; interval coverage.

- `gate` (ADR-070, the rule in force): on fold B, a slice is eligible only if its model
  MAPE over the full 26 weeks is no higher than seasonal naive's; each band of an eligible
  slice passes if its band MAPE is at most 20%.
- `gate_v1` (ADR-069, pre-registered, superseded): a slice and band passes if its model
  MAPE is at most 30% and no higher than seasonal naive's in that band. Kept so v1's
  recorded verdicts can be reproduced.
"""

from __future__ import annotations

import numpy as np

BANDS = {"1-4": (1, 4), "5-13": (5, 13), "14-26": (14, 26)}
MAPE_CEILING_V1 = 30.0
BAND_CEILING = 20.0


def mape(y: np.ndarray, yhat: np.ndarray) -> float:
    y, yhat = np.asarray(y, dtype=np.float64), np.asarray(yhat, dtype=np.float64)
    return float(np.mean(np.abs(y - yhat) / y) * 100)


def rmse(y: np.ndarray, yhat: np.ndarray) -> float:
    y, yhat = np.asarray(y, dtype=np.float64), np.asarray(yhat, dtype=np.float64)
    return float(np.sqrt(np.mean((y - yhat) ** 2)))


def coverage(y: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> float:
    y = np.asarray(y, dtype=np.float64)
    return float(np.mean((y >= lo) & (y <= hi)))


def scores(y: np.ndarray, yhat: np.ndarray) -> dict:
    """Overall and per-band MAPE and RMSE; horizon h = 1..len(y) in order."""
    y, yhat = np.asarray(y, dtype=np.float64), np.asarray(yhat, dtype=np.float64)
    h = np.arange(1, len(y) + 1)
    out = {"overall": {"mape": mape(y, yhat), "rmse": rmse(y, yhat), "n": len(y)}}
    for band, (lo, hi) in BANDS.items():
        m = (h >= lo) & (h <= hi)
        out[band] = {"mape": mape(y[m], yhat[m]), "rmse": rmse(y[m], yhat[m]), "n": int(m.sum())}
    return out


def gate_v1(model_mape: float, naive_mape: float, ceiling: float = MAPE_CEILING_V1) -> dict:
    """ADR-069's rule for one slice and band, with the reason when it fails."""
    reasons = []
    if model_mape > ceiling:
        reasons.append(f"MAPE {model_mape:.2f}% above the {ceiling:g}% ceiling")
    if model_mape > naive_mape:
        reasons.append(f"MAPE {model_mape:.2f}% above seasonal naive's {naive_mape:.2f}%")
    return {"pass": not reasons, "reasons": reasons}


def gate(slice_scores: dict, naive_scores: dict, ceiling: float = BAND_CEILING) -> dict:
    """ADR-070's rule for one slice: eligibility over 26 weeks, then a ceiling per band.

    `slice_scores` and `naive_scores` are `scores()` outputs for the model and the baseline.
    """
    model_26, naive_26 = slice_scores["overall"]["mape"], naive_scores["overall"]["mape"]
    eligible = model_26 <= naive_26
    bands = {}
    for band in BANDS:
        m = slice_scores[band]["mape"]
        reasons = []
        if not eligible:
            reasons.append(
                f"slice ineligible: 26-week MAPE {model_26:.2f}% above seasonal naive's "
                f"{naive_26:.2f}%"
            )
        if m > ceiling:
            reasons.append(f"band MAPE {m:.2f}% above the {ceiling:g}% ceiling")
        bands[band] = {"model_mape": m, "pass": not reasons, "reasons": reasons}
    return {
        "eligible": eligible,
        "model_mape_26": model_26,
        "naive_mape_26": naive_26,
        "bands": bands,
    }
