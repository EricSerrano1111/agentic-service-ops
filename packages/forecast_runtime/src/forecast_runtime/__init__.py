"""The forecast prediction path, shared by `ml/forecast` and `mcp_volume` (ADR-072).

Moved verbatim from `ml/forecast` (`data.py`, `model.py`, `export.py`) so serving and
evaluation run one code path while no training code is deployed (ADR-062): week
indexing, the calendar year-end indicator (ADR-070), the design matrix, the forecast
from saved coefficients with 80%/95% intervals and the 26-week cap (ADR-069), and the
hash-checked artifact load. numpy and `schemas` only; nothing here fits a model.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from schemas import DATASET_WINDOW_END, DATASET_WINDOW_START

WINDOW_START = DATASET_WINDOW_START
N_WEEKS = ((DATASET_WINDOW_END - DATASET_WINDOW_START).days + 1) // 7


def week_start(index: int) -> dt.date:
    return WINDOW_START + dt.timedelta(weeks=int(index))


def week_of(t: dt.datetime) -> int:
    return (t.astimezone(dt.UTC).date() - WINDOW_START).days // 7


PERIOD = 52.1775
HORIZON_CAP = 26
Z = {"80": 1.2815515655446004, "95": 1.959963984540054}


class HorizonError(ValueError):
    """A forecast beyond the 26-week cap, or not after the training window."""


def _is_year_end(monday: dt.date) -> bool:
    days = [monday + dt.timedelta(days=i) for i in range(7)]
    return any((d.month, d.day) in ((12, 25), (1, 1)) for d in days)


def year_end_indicator(t: np.ndarray) -> np.ndarray:
    """1.0 for weeks (by index from the window start) containing Dec 25 or Jan 1."""
    return np.array([float(_is_year_end(week_start(int(w)))) for w in np.asarray(t)])


def design(t: np.ndarray, k: int, year_end: bool = False) -> np.ndarray:
    """Columns: 1, t, [year-end indicator,] then sin(2πjt/P), cos(2πjt/P) for j = 1..k."""
    t_int = np.asarray(t)
    t = np.asarray(t, dtype=np.float64)
    cols = [np.ones_like(t), t]
    if year_end:
        cols.append(year_end_indicator(t_int))
    for j in range(1, k + 1):
        angle = 2 * math.pi * j * t / PERIOD
        cols += [np.sin(angle), np.cos(angle)]
    return np.column_stack(cols)


def forecast_from(
    k: int,
    params: np.ndarray,
    scale: float,
    xtwx_inv: np.ndarray,
    last_t: int,
    t: np.ndarray,
    year_end: bool = False,
) -> dict[str, np.ndarray]:
    """Median and 80%/95% intervals for weeks `t`; pure numpy, so a reloaded fit matches."""
    t = np.asarray(t, dtype=np.int64)
    if len(t) == 0 or t.min() <= last_t or t.max() > last_t + HORIZON_CAP:
        raise HorizonError(
            f"forecast weeks must be 1 to {HORIZON_CAP} weeks after the last training week"
        )
    x = design(t, k, year_end)
    mu = x @ params
    h = np.einsum("ij,jk,ik->i", x, xtwx_inv, x)
    se = scale * np.sqrt(1.0 + h)
    out = {"median": np.exp(mu)}
    for level, z in Z.items():
        out[f"lo{level}"] = np.exp(mu - z * se)
        out[f"hi{level}"] = np.exp(mu + z * se)
    return out


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(directory: Path, manifest: dict) -> dict[str, dict]:
    """Every slice's record, hash-checked against the manifest."""
    out = {}
    for name, expected in manifest["files"].items():
        path = directory / name
        if _sha(path) != expected:
            raise RuntimeError(f"{name} does not match the manifest's SHA-256")
        rec = json.loads(path.read_text(encoding="utf-8"))
        out[rec["slice"]] = rec
    return out


def forecast_record(rec: dict, t: np.ndarray) -> dict[str, np.ndarray]:
    return forecast_from(
        rec["k"],
        np.array(rec["params"]),
        rec["scale"],
        np.array(rec["xtwx_inv"]),
        rec["last_t"],
        t,
        rec["year_end"],
    )
