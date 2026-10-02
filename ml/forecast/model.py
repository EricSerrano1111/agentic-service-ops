"""The forecast model, exactly as ADR-069 fixes it (ADR-058). Nothing here is tuned.

- Design matrix: intercept, a linear trend in weeks, and K sine/cosine pairs with period
  `PERIOD` = 52.1775 weeks (365.2425 / 7).
- K: chosen from {0, ..., 6} by AICc on an ordinary least-squares fit of log weekly count.
  Ties go to the smaller K.
- Refit at that K with robust regression: `statsmodels` RLM, Tukey biweight (c = 4.685),
  MAD scale. Down-weighting uses residuals only, never the generator's anomaly list.
- Point forecast: exp(fitted log), the median.
- Intervals: on the log scale, fitted ± z · s · √(1 + h), where s is the robust (MAD)
  scale and h = x₀ᵀ (Xᵀ W X)⁻¹ x₀ is the leverage of the forecast week under the robust
  weights W; then exponentiated. z is the standard normal quantile (80%: 1.2816, 95%: 1.9600).
- Horizon: at most 26 weeks past the last training week; anything longer is rejected.

`Fit` holds everything a forecast needs (coefficients, K, scale, (XᵀWX)⁻¹, the last
training week), so a fit exported to disk forecasts identically without statsmodels.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

PERIOD = 52.1775
K_RANGE = tuple(range(0, 7))
TUKEY_C = 4.685
HORIZON_CAP = 26
Z = {"80": 1.2815515655446004, "95": 1.959963984540054}


class HorizonError(ValueError):
    """A forecast beyond the 26-week cap, or not after the training window."""


def design(t: np.ndarray, k: int) -> np.ndarray:
    """Columns: 1, t, then sin(2πjt/P), cos(2πjt/P) for j = 1..k."""
    t = np.asarray(t, dtype=np.float64)
    cols = [np.ones_like(t), t]
    for j in range(1, k + 1):
        angle = 2 * math.pi * j * t / PERIOD
        cols += [np.sin(angle), np.cos(angle)]
    return np.column_stack(cols)


def aicc(y_log: np.ndarray, t: np.ndarray, k: int) -> float:
    """AICc of the OLS fit at K = k (Gaussian likelihood; p counts the coefficients)."""
    import statsmodels.api as sm

    res = sm.OLS(y_log, design(t, k)).fit()
    n, p = len(y_log), res.df_model + 1
    return float(res.aic + 2 * p * (p + 1) / (n - p - 1))


def select_k(y_log: np.ndarray, t: np.ndarray) -> tuple[int, dict[int, float]]:
    scores = {k: aicc(y_log, t, k) for k in K_RANGE}
    best = min(K_RANGE, key=lambda k: (scores[k], k))
    return best, scores


@dataclass(frozen=True)
class Fit:
    k: int
    params: np.ndarray
    scale: float
    xtwx_inv: np.ndarray
    last_t: int
    weights: np.ndarray = field(repr=False)
    train_t: np.ndarray = field(repr=False)
    aicc: dict[int, float] = field(default_factory=dict, repr=False)

    def downweighted(self, below: float = 0.5) -> np.ndarray:
        """Training week indices whose robust weight is below `below`."""
        return self.train_t[self.weights < below]


def fit(counts: np.ndarray, t: np.ndarray) -> Fit:
    """Select K on OLS, refit robustly at K. `t` are the training weeks' indices."""
    import statsmodels.api as sm

    counts = np.asarray(counts, dtype=np.float64)
    t = np.asarray(t, dtype=np.int64)
    if (counts <= 0).any():
        raise ValueError("a week with no requests: the log model needs positive counts")
    y_log = np.log(counts)
    k, scores = select_k(y_log, t)
    x = design(t, k)
    res = sm.RLM(y_log, x, M=sm.robust.norms.TukeyBiweight(c=TUKEY_C)).fit(scale_est="mad")
    w = np.asarray(res.weights, dtype=np.float64)
    xtwx_inv = np.linalg.inv(x.T @ (w[:, None] * x))
    return Fit(
        k=k,
        params=np.asarray(res.params, dtype=np.float64),
        scale=float(res.scale),
        xtwx_inv=xtwx_inv,
        last_t=int(t.max()),
        weights=w,
        train_t=t,
        aicc=scores,
    )


def forecast_from(
    k: int, params: np.ndarray, scale: float, xtwx_inv: np.ndarray, last_t: int, t: np.ndarray
) -> dict[str, np.ndarray]:
    """Median and 80%/95% intervals for weeks `t`; pure numpy, so a reloaded fit matches."""
    t = np.asarray(t, dtype=np.int64)
    if len(t) == 0 or t.min() <= last_t or t.max() > last_t + HORIZON_CAP:
        raise HorizonError(
            f"forecast weeks must be 1 to {HORIZON_CAP} weeks after the last training week"
        )
    x = design(t, k)
    mu = x @ params
    h = np.einsum("ij,jk,ik->i", x, xtwx_inv, x)
    se = scale * np.sqrt(1.0 + h)
    out = {"median": np.exp(mu)}
    for level, z in Z.items():
        out[f"lo{level}"] = np.exp(mu - z * se)
        out[f"hi{level}"] = np.exp(mu + z * se)
    return out


def forecast(f: Fit, t: np.ndarray) -> dict[str, np.ndarray]:
    return forecast_from(f.k, f.params, f.scale, f.xtwx_inv, f.last_t, t)
