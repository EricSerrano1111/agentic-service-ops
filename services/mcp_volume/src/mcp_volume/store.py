"""The history query, as `app_forecast`: fixed SQL, bound parameters only.

Reads exactly the three columns `app_forecast` is granted on `service_requests`
(`request_id`, `scheduled_datetime`, `service_type`; ADR-035) and aggregates them with the
same week rule as `ml/forecast/data.py` (`forecast_runtime.week_of`: Monday-start ISO
weeks, UTC), over the most recent complete weeks up to 2026-08-30.
"""

from __future__ import annotations

import datetime as dt

from db_models import ServiceRequest
from forecast_runtime import N_WEEKS, week_of, week_start
from schemas import HistoryWeek, VolumeHistory
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.engine import URL

from .config import Settings

_r = ServiceRequest.__table__


def make_engine(settings: Settings) -> Engine:
    url = URL.create(
        "postgresql+psycopg",
        username=settings.db_user,
        password=settings.db_password,
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
    )
    return create_engine(
        url,
        pool_size=2,
        max_overflow=2,
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": settings.connect_timeout_s,
            "options": f"-c statement_timeout={settings.statement_timeout_ms}",
            "application_name": "mcp_volume",
        },
    )


class SqlStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def ping(self) -> None:
        with self.engine.connect() as conn:
            conn.execute(select(1))

    def history(self, slice_: str, weeks: int) -> VolumeHistory:
        first = N_WEEKS - weeks
        lo = dt.datetime.combine(week_start(first), dt.time.min, dt.UTC)
        hi = dt.datetime.combine(week_start(N_WEEKS), dt.time.min, dt.UTC)
        q = select(_r.c.scheduled_datetime).where(
            _r.c.scheduled_datetime >= lo, _r.c.scheduled_datetime < hi
        )
        if slice_ != "total":
            q = q.where(_r.c.service_type == slice_)
        counts = [0] * weeks
        with self.engine.connect() as conn:
            for (t,) in conn.execute(q):
                counts[week_of(t) - first] += 1
        return VolumeHistory(
            slice=slice_,
            weeks=[
                HistoryWeek(week_start=week_start(first + i), count=n) for i, n in enumerate(counts)
            ],
        )
