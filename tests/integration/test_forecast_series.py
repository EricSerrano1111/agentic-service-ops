"""The forecast's weekly series, read as app_train, equals independent SQL as app_eval."""

from __future__ import annotations

import pytest
from db_models.access_matrix import ROLE_EVAL

pytestmark = pytest.mark.integration

WEEKLY = """
    SELECT ((scheduled_datetime AT TIME ZONE 'UTC')::date - DATE '2023-09-04') / 7 AS w,
           service_type, count(*)
    FROM service_requests
    WHERE scheduled_datetime >= TIMESTAMPTZ '2023-09-04 00:00+00'
      AND scheduled_datetime <  TIMESTAMPTZ '2026-08-31 00:00+00'
    GROUP BY 1, 2
"""


def test_series_match_independent_sql(loaded_database, connect_as):
    pytest.importorskip("statsmodels")
    from ml.forecast import data

    series = data.load_series()
    rows = connect_as(ROLE_EVAL).execute(WEEKLY).fetchall()
    assert set(series) == {"total"} | {t for _, t, _ in rows}
    for name, counts in series.items():
        assert len(counts) == 156
        expected = [0] * 156
        for w, t, n in rows:
            if name in ("total", t):
                expected[w] += n
        assert counts.tolist() == expected, name
    assert (series["total"] > 0).all()
