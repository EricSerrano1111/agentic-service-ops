"""Input validation, the queries behind `get_incidents_by_date_range`, and technician
lookup (`find_technician`, and the name a technician filter reports).

SQLAlchemy Core over the `db_models` tables, bound parameters only; counts, never rows,
and no free-text column (`incident_notes`) is read. Breakdowns (ADR-073): `account`,
`region` (the site's) and `service_type` through the incident's request; `technician` is
`attributed_technician_id`, with incidents attributed to nobody as their own
"unattributed" group; `incident_type` and `severity` are the incident's own columns.
Groups are ranked highest count first, then by name, and capped at 25.
"""

from __future__ import annotations

import datetime as dt
import re

from db_models import Account, Incident, Location, ServiceRequest, Severity, Technician, values
from schemas import (
    MAX_COUNT_GROUPS,
    MAX_TECHNICIAN_MATCHES,
    UNATTRIBUTED,
    GroupCount,
    IncidentGroupBy,
    IncidentSummary,
    SeverityCounts,
    TechnicianMatch,
    TechnicianMatches,
)
from sqlalchemy import Engine, bindparam, create_engine, func, select, text
from sqlalchemy.engine import URL

from .config import Settings

_incidents = Incident.__table__
_sr = ServiceRequest.__table__
_loc = Location.__table__
_acc = Account.__table__
_tech = Technician.__table__


class InvalidArgument(ValueError):
    """A caller error: the message is safe to return to the client verbatim. `argument` and
    `kind` say which argument was rejected and why, with no value: they are what the log
    records, since a rejected value may be text from a user's question."""

    def __init__(self, message: str, *, argument: str, kind: str) -> None:
        super().__init__(message)
        self.argument = argument
        self.kind = kind


class InvalidRange(InvalidArgument):
    """A date range the tools don't accept."""


def _parse(name: str, raw: str) -> dt.date:
    if not isinstance(raw, str) or len(raw) != 10:
        raise InvalidRange(
            f"{name} must be an ISO date (YYYY-MM-DD)",
            argument=name,
            kind="not_iso_date",
        )
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        raise InvalidRange(
            f"{name} must be an ISO date (YYYY-MM-DD)",
            argument=name,
            kind="not_iso_date",
        ) from None


def parse_date_range(
    start: str, end: str, window_start: dt.date, window_end: dt.date
) -> tuple[dt.date, dt.date]:
    """Validate an inclusive date range against the dataset window.

    Strict `YYYY-MM-DD` only: `date.fromisoformat` also accepts `20240101` and week
    dates, which a model is more likely to produce by mistake than on purpose.
    """
    s, e = _parse("start", start), _parse("end", end)
    if s > e:
        raise InvalidRange(
            f"start ({s}) is after end ({e})", argument="start,end", kind="start_after_end"
        )
    if s < window_start or e > window_end:
        raise InvalidRange(
            f"range {s} to {e} is outside the dataset window "
            f"{window_start} to {window_end} (inclusive)",
            argument="start,end",
            kind="outside_window",
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


def check_connection(engine: Engine) -> None:
    """Raise if the database does not answer `SELECT 1` (the readiness probe)."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))


# Counts by severity in a half-open UTC timestamp range [lo, hi).
_SEVERITY_COUNTS = (
    select(_incidents.c.severity, func.count().label("n"))
    .where(
        _incidents.c.reported_at >= bindparam("lo"),
        _incidents.c.reported_at < bindparam("hi"),
    )
    .group_by(_incidents.c.severity)
)


def count_by_severity(
    engine: Engine,
    start: dt.date,
    end: dt.date,
    group_by: IncidentGroupBy | None = None,
    technician_id: int | None = None,
) -> IncidentSummary:
    """Incidents with `reported_at` on `start`..`end` inclusive, in UTC days; optionally
    broken down, or only those attributed to one technician (not both)."""
    if group_by is not None and technician_id is not None:
        raise InvalidArgument(
            "a technician filter cannot be combined with a breakdown",
            argument="technician_id,group_by",
            kind="conflicting_arguments",
        )
    lo = dt.datetime.combine(start, dt.time.min, dt.UTC)
    hi = dt.datetime.combine(end + dt.timedelta(days=1), dt.time.min, dt.UTC)
    name = technician_name(engine, technician_id) if technician_id is not None else None
    query = _SEVERITY_COUNTS
    if technician_id is not None:
        query = query.where(_incidents.c.attributed_technician_id == technician_id)
    with engine.connect() as conn:
        rows = conn.execute(query, {"lo": lo, "hi": hi}).all()
    counts = dict.fromkeys(values(Severity), 0)
    for severity, n in rows:
        # A value outside the vocabulary would mean the CHECK constraint is gone.
        if severity not in counts:
            raise RuntimeError(f"unexpected severity {severity!r} in incidents")
        counts[severity] = n
    fields = {}
    if group_by is not None:
        groups = _count_groups(engine, lo, hi, group_by)
        fields = {
            "group_by": group_by,
            "groups": groups[:MAX_COUNT_GROUPS],
            "group_count": len(groups),
            "truncated": len(groups) > MAX_COUNT_GROUPS,
        }
    if technician_id is not None:
        fields = {"technician_id": technician_id, "technician_name": name}
    return IncidentSummary(
        start=start,
        end=end,
        incident_count=sum(counts.values()),
        by_severity=SeverityCounts(**counts),
        **fields,
    )


def _count_groups(
    engine: Engine, lo: dt.datetime, hi: dt.datetime, group_by: IncidentGroupBy
) -> list[GroupCount]:
    """Every group's count, highest first, ties by name. The caller applies the cap."""
    src = _incidents
    has_id = group_by in ("account", "technician")
    if group_by == "incident_type":
        key = label = _incidents.c.incident_type
    elif group_by == "severity":
        key = label = _incidents.c.severity
    elif group_by == "technician":
        key, label = _incidents.c.attributed_technician_id, _tech.c.full_name
        src = _incidents.outerjoin(
            _tech, _tech.c.technician_id == _incidents.c.attributed_technician_id
        )
    else:
        src = _incidents.join(_sr, _sr.c.request_id == _incidents.c.request_id)
        if group_by == "service_type":
            key = label = _sr.c.service_type
        elif group_by == "region":
            key = label = _loc.c.region
            src = src.join(_loc, _loc.c.location_id == _sr.c.location_id)
        else:  # account
            key, label = _acc.c.account_id, _acc.c.account_name
            src = src.join(_acc, _acc.c.account_id == _sr.c.account_id)
    query = (
        select(key.label("key"), label.label("label"), func.count().label("n"))
        .select_from(src)
        .where(_incidents.c.reported_at >= lo, _incidents.c.reported_at < hi)
        .group_by(key, label)
    )
    with engine.connect() as conn:
        rows = conn.execute(query).all()
    groups = [
        GroupCount(
            group=UNATTRIBUTED if r.key is None else str(r.label),
            group_id=r.key if has_id else None,
            count=int(r.n),
        )
        for r in rows
    ]
    groups.sort(key=lambda g: (-g.count, g.group))
    return groups


# --------------------------------------------------------------------------- technicians

#: Letters (any script), spaces, apostrophes, hyphens and periods. Everything else,
#: wildcard and pattern characters included (% _ * ? [ ] \ ^ $), is rejected.
_NAME = re.compile(r"^[^\W\d_]+(?:[ '.\-]+[^\W\d_]+)*\.?$")
MAX_NAME_LENGTH = 100


def _words(text: str) -> list[str]:
    return text.casefold().split()


def match_technicians(name: str, technicians: list[tuple[int, str]]) -> TechnicianMatches:
    """Pure: case-insensitive match of `name` against (id, full name) pairs.

    A technician matches if every word of the query is a whole word of the name, which
    covers the whole name ("Priya" finds every Priya; "Pri" finds no one). At most 5
    matches, by name, then id; `total_matches` says how many there were.
    """
    cleaned = " ".join(name.split()) if isinstance(name, str) else ""
    if not cleaned or len(cleaned) > MAX_NAME_LENGTH or not _NAME.match(cleaned):
        raise InvalidArgument(
            "name must be 1 to 100 characters of letters, spaces, apostrophes, hyphens "
            "or periods; wildcards and patterns are not accepted",
            argument="name",
            kind="invalid_characters",
        )
    query = _words(cleaned)
    found = []
    for tid, full_name in technicians:
        words = _words(full_name)
        if all(w in words for w in query):
            found.append(TechnicianMatch(technician_id=tid, full_name=full_name))
    found.sort(key=lambda m: (m.full_name.casefold(), m.technician_id))
    return TechnicianMatches(
        name=cleaned, matches=found[:MAX_TECHNICIAN_MATCHES], total_matches=len(found)
    )


def find_technician(engine: Engine, name: str) -> TechnicianMatches:
    """The fixed technician list is read whole (32 rows) and matched in Python, so the
    name never reaches SQL."""
    with engine.connect() as conn:
        rows = conn.execute(select(_tech.c.technician_id, _tech.c.full_name)).all()
    return match_technicians(name, [(r.technician_id, r.full_name) for r in rows])


def technician_name(engine: Engine, technician_id: int) -> str:
    """The display name a technician filter reports; an unknown id is a caller error."""
    with engine.connect() as conn:
        name = conn.execute(
            select(_tech.c.full_name).where(_tech.c.technician_id == technician_id)
        ).scalar_one_or_none()
    if name is None:
        raise InvalidArgument(
            f"no technician has id {technician_id}", argument="technician_id", kind="unknown_id"
        )
    return name
