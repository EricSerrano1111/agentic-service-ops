"""The fixed queries behind the three metric tools, exactly as data dictionary §6 defines
them. SQLAlchemy Core over the `db_models` tables, bound parameters only; each tool has
its own queries (ADR-023: no generic query builder is exposed).

Date rules (§6), each applied to the event its definition is about:
- Incident rate: incidents by `reported_at` in range, over requests with
  `archived_requests.completed_at` in range. Per 100 completed requests.
- SLA compliance: requests by `dispatched_at` in range. Requests never dispatched or not
  completed have a null `sla_met` and are left out of the denominator.
- First-time fix: completed requests by `completed_at` in range; a non-cancelled child
  request counts against its parent whatever the child's own date.

Breakdowns: `account`, `region` (the site's, ADR-051), `service_type`, and `technician`,
who is the technician who did the work (`archived_requests.technician_id`). For incident
rate by technician, the numerator is incidents attributed to that technician
(`attributed_technician_id`); unattributed incidents are left out (ADR-033).

Single-technician filter (ADR-073): `technician_id` restricts each metric to the same
columns its `group_by=technician` uses, so a filtered figure equals that technician's
group. It cannot be combined with a breakdown.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from db_models import Account, ArchivedRequest, Incident, Location, ServiceRequest, Technician
from schemas import (
    MAX_GROUPS,
    FirstTimeFixResult,
    GroupBy,
    GroupRate,
    IncidentRateResult,
    SlaComplianceResult,
    rate_string,
)
from sqlalchemy import Engine, and_, exists, func, select
from sqlalchemy.sql import ColumnElement, Select

from .queries import InvalidArgument, technician_name

sr = ServiceRequest.__table__
ar = ArchivedRequest.__table__
inc = Incident.__table__
loc = Location.__table__
acc = Account.__table__
tech = Technician.__table__
child = sr.alias("child")


def _bounds(start: dt.date, end: dt.date) -> tuple[dt.datetime, dt.datetime]:
    """Inclusive UTC days as a half-open timestamp range [lo, hi)."""
    lo = dt.datetime.combine(start, dt.time.min, dt.UTC)
    hi = dt.datetime.combine(end + dt.timedelta(days=1), dt.time.min, dt.UTC)
    return lo, hi


def _in_range(column: ColumnElement, lo: dt.datetime, hi: dt.datetime) -> ColumnElement:
    return and_(column >= lo, column < hi)


@dataclass(frozen=True)
class _Counts:
    key: object
    label: str
    count: int


def _grouped(
    engine: Engine,
    base: Select,
    group_by: GroupBy,
    technician_column: ColumnElement,
    count: ColumnElement,
) -> dict[object, _Counts]:
    """Run `base` (which selects from service_requests `sr`) grouped by a dimension."""
    if group_by == "region":
        key = label = loc.c.region
        query = base.join(loc, loc.c.location_id == sr.c.location_id)
    elif group_by == "service_type":
        key = label = sr.c.service_type
        query = base
    elif group_by == "account":
        key, label = acc.c.account_id, acc.c.account_name
        query = base.join(acc, acc.c.account_id == sr.c.account_id)
    else:  # technician
        key, label = tech.c.technician_id, tech.c.full_name
        query = base.join(tech, tech.c.technician_id == technician_column)
    query = query.with_only_columns(key.label("key"), label.label("label"), count.label("n"))
    query = query.group_by(key, label)
    with engine.connect() as conn:
        rows = conn.execute(query).all()
    return {r.key: _Counts(r.key, str(r.label), int(r.n)) for r in rows}


def _rank(
    numerators: dict[object, _Counts],
    denominators: dict[object, _Counts],
    group_by: GroupBy,
    scale: int,
    higher_is_worse: bool,
) -> tuple[list[GroupRate], int]:
    """Merge, compute rates, sort worst first, cap at 25.

    Worst first: highest rate first when a higher rate is worse (incident rate), lowest
    first otherwise (SLA compliance, first-time fix). Null rates go last, ties by group
    name. The cap applies after sorting, so truncation keeps the worst groups.
    """
    keys = set(numerators) | set(denominators)
    groups = []
    for key in keys:
        entry = denominators.get(key) or numerators[key]
        num = numerators[key].count if key in numerators else 0
        den = denominators[key].count if key in denominators else 0
        groups.append(
            GroupRate(
                group=entry.label,
                group_id=key if group_by in ("account", "technician") else None,
                numerator=num,
                denominator=den,
                rate=rate_string(num, den, scale),
            )
        )

    def worst_first(g: GroupRate):
        value = Decimal(g.rate or 0)
        return (g.rate is None, -value if higher_is_worse else value, g.group)

    groups.sort(key=worst_first)
    return groups[:MAX_GROUPS], len(groups)


def _technician(
    engine: Engine, group_by: GroupBy | None, technician_id: int | None
) -> dict[str, object]:
    """Validate a technician filter; the fields it adds to the result."""
    if technician_id is None:
        return {}
    if group_by is not None:
        raise InvalidArgument(
            "a technician filter cannot be combined with a breakdown",
            argument="technician_id,group_by",
            kind="conflicting_arguments",
        )
    name = technician_name(engine, technician_id)
    return {"technician_id": technician_id, "technician_name": name}


def _only(query: Select, column: ColumnElement, technician_id: int | None) -> Select:
    return query if technician_id is None else query.where(column == technician_id)


def _result(model: Callable, start, end, group_by, num, den, scale, groups_fn, extra):
    fields = extra | {
        "start": start,
        "end": end,
        "group_by": group_by,
        "numerator": num,
        "denominator": den,
        "rate": rate_string(num, den, scale),
    }
    if group_by is not None:
        groups, total = groups_fn()
        fields |= {"groups": groups, "group_count": total, "truncated": total > len(groups)}
    return model(**fields)


# --------------------------------------------------------------------------- incident rate


def incident_rate(
    engine: Engine,
    start: dt.date,
    end: dt.date,
    group_by: GroupBy | None = None,
    technician_id: int | None = None,
) -> IncidentRateResult:
    extra = _technician(engine, group_by, technician_id)
    lo, hi = _bounds(start, end)
    incidents = _only(
        select(sr.c.request_id)
        .select_from(inc.join(sr, sr.c.request_id == inc.c.request_id))
        .where(_in_range(inc.c.reported_at, lo, hi)),
        inc.c.attributed_technician_id,
        technician_id,
    )
    completed = _only(
        select(sr.c.request_id)
        .select_from(ar.join(sr, sr.c.request_id == ar.c.request_id))
        .where(_in_range(ar.c.completed_at, lo, hi)),
        ar.c.technician_id,
        technician_id,
    )
    with engine.connect() as conn:
        num = conn.execute(incidents.with_only_columns(func.count())).scalar_one()
        den = conn.execute(completed.with_only_columns(func.count())).scalar_one()

    def groups():
        numerators = _grouped(
            engine, incidents, group_by, inc.c.attributed_technician_id, func.count()
        )
        denominators = _grouped(engine, completed, group_by, ar.c.technician_id, func.count())
        return _rank(numerators, denominators, group_by, 100, higher_is_worse=True)

    return _result(IncidentRateResult, start, end, group_by, num, den, 100, groups, extra)


# --------------------------------------------------------------------------- SLA compliance


def sla_compliance(
    engine: Engine,
    start: dt.date,
    end: dt.date,
    group_by: GroupBy | None = None,
    technician_id: int | None = None,
) -> SlaComplianceResult:
    extra = _technician(engine, group_by, technician_id)
    lo, hi = _bounds(start, end)
    # §6: sla_met = completed_at <= dispatched_at + sla_window_minutes. The inner join to
    # archived_requests and the dispatched_at filter leave out every null sla_met.
    sla_met = ar.c.completed_at <= sr.c.dispatched_at + func.make_interval(
        0, 0, 0, 0, 0, sr.c.sla_window_minutes
    )
    dispatched = _only(
        select(sr.c.request_id)
        .select_from(sr.join(ar, ar.c.request_id == sr.c.request_id))
        .where(_in_range(sr.c.dispatched_at, lo, hi)),
        ar.c.technician_id,
        technician_id,
    )
    with engine.connect() as conn:
        num, den = conn.execute(
            dispatched.with_only_columns(func.count().filter(sla_met), func.count())
        ).one()

    def groups():
        met = _grouped(
            engine, dispatched, group_by, ar.c.technician_id, func.count().filter(sla_met)
        )
        total = _grouped(engine, dispatched, group_by, ar.c.technician_id, func.count())
        return _rank(met, total, group_by, 1, higher_is_worse=False)

    return _result(SlaComplianceResult, start, end, group_by, int(num), int(den), 1, groups, extra)


# --------------------------------------------------------------------------- first-time fix


def first_time_fix_rate(
    engine: Engine,
    start: dt.date,
    end: dt.date,
    group_by: GroupBy | None = None,
    technician_id: int | None = None,
) -> FirstTimeFixResult:
    extra = _technician(engine, group_by, technician_id)
    lo, hi = _bounds(start, end)
    # A non-cancelled child, of any date, means a return visit happened.
    fixed = ~exists().where(
        child.c.parent_request_id == sr.c.request_id, child.c.request_status != "cancelled"
    )
    completed = _only(
        select(sr.c.request_id)
        .select_from(ar.join(sr, sr.c.request_id == ar.c.request_id))
        .where(_in_range(ar.c.completed_at, lo, hi)),
        ar.c.technician_id,
        technician_id,
    )
    with engine.connect() as conn:
        num, den = conn.execute(
            completed.with_only_columns(func.count().filter(fixed), func.count())
        ).one()

    def groups():
        fixes = _grouped(
            engine, completed, group_by, ar.c.technician_id, func.count().filter(fixed)
        )
        total = _grouped(engine, completed, group_by, ar.c.technician_id, func.count())
        return _rank(fixes, total, group_by, 1, higher_is_worse=False)

    return _result(FirstTimeFixResult, start, end, group_by, int(num), int(den), 1, groups, extra)
