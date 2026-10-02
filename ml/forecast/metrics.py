"""Forecast metrics and the release gate (ADR-069). Pure: no I/O.

MAPE (primary, in percent) and RMSE, overall and by horizon band; interval coverage. The
gate: a slice and band passes if, on fold B, the model's MAPE is at most 30% and no higher
than seasonal naive's.
"""

from __future__ import annotations

import numpy as np

BANDS = {"1-4": (1, 4), "5-13": (5, 13), "14-26": (14, 26)}
MAPE_CEILING = 30.0


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


def gate(model_mape: float, naive_mape: float, ceiling: float = MAPE_CEILING) -> dict:
    """ADR-069's rule for one slice and band, with the reason when it fails."""
    reasons = []
    if model_mape > ceiling:
        reasons.append(f"MAPE {model_mape:.2f}% above the {ceiling:g}% ceiling")
    if model_mape > naive_mape:
        reasons.append(f"MAPE {model_mape:.2f}% above seasonal naive's {naive_mape:.2f}%")
    return {"pass": not reasons, "reasons": reasons}
