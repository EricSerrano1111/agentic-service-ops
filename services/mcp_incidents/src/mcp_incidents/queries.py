"""Input validation and the one query behind `get_incidents_by_date_range`.

SQLAlchemy Core over the `db_models` tables, bound parameters only. It reads two
columns of `incidents` (`severity`, `reported_at`), both inside `app_reporting`'s grant
(data dictionary §7), and returns counts, never rows.
"""

from __future__ import annotations

import datetime as dt

from db_models import Incident, Severity, values
from schemas import IncidentSummary, SeverityCounts
from sqlalchemy import Engine, bindparam, create_engine, func, select
from sqlalchemy.engine import URL

from .config import Settings

_incidents = Incident.__table__


class InvalidRange(ValueError):
    """A caller error: the message is safe to return to the client verbatim."""


def _parse(name: str, raw: str) -> dt.date:
    if not isinstance(raw, str) or len(raw) != 10:
        raise InvalidRange(f"{name} must be an ISO date (YYYY-MM-DD), got {raw!r}")
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        raise InvalidRange(f"{name} must be an ISO date (YYYY-MM-DD), got {raw!r}") from None


def parse_date_range(
    start: str, end: str, window_start: dt.date, window_end: dt.date
) -> tuple[dt.date, dt.date]:
    """Validate an inclusive date range against the dataset window.

    Strict `YYYY-MM-DD` only: `date.fromisoformat` also accepts `20240101` and week
    dates, which a model is more likely to produce by mistake than on purpose.
    """
    s, e = _parse("start", start), _parse("end", end)
    if s > e:
        raise InvalidRange(f"start ({s}) is after end ({e})")
    if s < window_start or e > window_end:
        raise InvalidRange(
            f"range {s} to {e} is outside the dataset window "
            f"{window_start} to {window_end} (inclusive)"
        )
    return s, e


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
            "application_name": "mcp_incidents",
        },
    )


# Counts by severity in a half-open UTC timestamp range [lo, hi).
_SEVERITY_COUNTS = (
    select(_incidents.c.severity, func.count().label("n"))
    .where(
        _incidents.c.reported_at >= bindparam("lo"),
        _incidents.c.reported_at < bindparam("hi"),
    )
    .group_by(_incidents.c.severity)
)


def count_by_severity(engine: Engine, start: dt.date, end: dt.date) -> IncidentSummary:
    """Incidents with `reported_at` on `start`..`end` inclusive, in UTC days."""
    lo = dt.datetime.combine(start, dt.time.min, dt.UTC)
    hi = dt.datetime.combine(end + dt.timedelta(days=1), dt.time.min, dt.UTC)
    with engine.connect() as conn:
        rows = conn.execute(_SEVERITY_COUNTS, {"lo": lo, "hi": hi}).all()
    counts = dict.fromkeys(values(Severity), 0)
    for severity, n in rows:
        # A value outside the vocabulary would mean the CHECK constraint is gone.
        if severity not in counts:
            raise RuntimeError(f"unexpected severity {severity!r} in incidents")
        counts[severity] = n
    return IncidentSummary(
        start=start,
        end=end,
        incident_count=sum(counts.values()),
        by_severity=SeverityCounts(**counts),
    )
