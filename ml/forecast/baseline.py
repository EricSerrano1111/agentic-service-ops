"""Seasonal naive (ADR-058, ADR-069): each week is predicted by the value 52 weeks earlier."""

from __future__ import annotations

import numpy as np

SEASON = 52


def seasonal_naive(counts: np.ndarray, origin: int, t: np.ndarray) -> np.ndarray:
    """Forecast weeks `t` from the series as known before week `origin`.

    Uses week t - 52 only, which must lie before the origin: with a horizon of at most 26
    weeks it always does, and a forecast that would look at or past the origin is refused.
    """
    t = np.asarray(t, dtype=np.int64)
    source = t - SEASON
    if (source < 0).any() or (source >= origin).any():
        raise ValueError("seasonal naive would read a week outside the known history")
    return np.asarray(counts, dtype=np.float64)[source]
