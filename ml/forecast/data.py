"""The weekly volume series (ADR-018, ADR-069), read as `app_train`.

Weekly counts of `service_requests` by `scheduled_datetime`, all statuses, ISO weeks
(Monday start, UTC), over the dataset window: 156 complete weeks from Monday 2023-09-04
to Sunday 2026-08-30. Slices: the total and each `service_type`.

Same week rule as `data/generator/validate.py` (week index = (UTC date - window start)
// 7), but the window comes from `schemas.DATASET_WINDOW_*`, not `generation_parameters`,
which `app_train` can't read; a unit test holds those constants to the generator.
`app_train` reads exactly `request_id`, `scheduled_datetime` and `service_type` (ADR-063).

Every result carries the SHA-256 of the series it was computed on (`series_sha256`).
"""

from __future__ import annotations

import datetime as dt
import hashlib
from collections.abc import Mapping

import numpy as np
from schemas import DATASET_WINDOW_END, DATASET_WINDOW_START

WINDOW_START = DATASET_WINDOW_START
N_WEEKS = ((DATASET_WINDOW_END - DATASET_WINDOW_START).days + 1) // 7
TOTAL = "total"


def week_start(index: int) -> dt.date:
    return WINDOW_START + dt.timedelta(weeks=int(index))


def week_of(t: dt.datetime) -> int:
    return (t.astimezone(dt.UTC).date() - WINDOW_START).days // 7


def weekly_series(rows: list[tuple[dt.datetime, str]]) -> dict[str, np.ndarray]:
    """(scheduled_datetime, service_type) rows -> {slice: counts per week}, total first."""
    types = sorted({s for _, s in rows})
    series = {name: np.zeros(N_WEEKS, dtype=np.int64) for name in (TOTAL, *types)}
    for t, service_type in rows:
        w = week_of(t)
        if 0 <= w < N_WEEKS:
            series[TOTAL][w] += 1
            series[service_type][w] += 1
    return series


def series_sha256(counts: np.ndarray) -> str:
    """SHA-256 of the series as `week_start,count` lines: stable across numpy versions."""
    text = "".join(f"{week_start(i).isoformat()},{int(n)}\n" for i, n in enumerate(counts))
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def series_hashes(series: Mapping[str, np.ndarray]) -> dict[str, str]:
    return {name: series_sha256(counts) for name, counts in series.items()}


def load_series() -> dict[str, np.ndarray]:
    """The weekly series for every slice, read as `app_train`."""
    from ml.sentiment.data import connect

    with connect("app_train") as conn:
        rows = conn.execute(
            "SELECT scheduled_datetime, service_type FROM service_requests"
        ).fetchall()
    return weekly_series(rows)
