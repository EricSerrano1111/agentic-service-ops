"""Repeat-visit drivers (ADR-073): where repeat visits happen, and which other incident
types they co-occur with, with a significance rule so noise is not reported as a driver.

Original jobs are requests completed in the range (`archived_requests.completed_at`, the
§6 first-time-fix rule). A job "repeated" if it has a non-cancelled child request, whatever
the child's date. `by`:
- `service_type`, `region` (the site's), `account`, `technician` (the original job's
  `assigned_technician_id`): each group's jobs against every other job in range;
- `incident_type`: for each type except `repeat_visit_required` (which defines a repeat),
  jobs with that type against jobs without it; plus jobs with any other incident against
  jobs with none other, a single comparison (at least 20 jobs on each side, Fisher's
  p < 0.05, no Bonferroni).

A group stands out only if it has at least 20 jobs, its rate is above the rest's, and
Fisher's exact test (two-sided) gives p < 0.05 after Bonferroni correction across the
groups compared. Fisher's test is plain Python here (`mcp_incidents` doesn't depend on
scipy); a unit test checks it against scipy.
"""

from __future__ import annotations

import datetime as dt
import math
from fractions import Fraction

from db_models import Account, ArchivedRequest, Incident, Location, ServiceRequest, Technician
from schemas import (
    MAX_REPEAT_GROUPS,
    MIN_GROUP_JOBS,
    JobsRepeated,
    RepeatBy,
    RepeatDriversResult,
    RepeatGroup,
    rate_string,
)
from sqlalchemy import Engine, and_, exists, select

from .metrics import _bounds

sr = ServiceRequest.__table__
ar = ArchivedRequest.__table__
inc = Incident.__table__
loc = Location.__table__
acc = Account.__table__
tech = Technician.__table__
child = sr.alias("child")

DEFINING_TYPE = "repeat_visit_required"
ALPHA = 0.05


def _log_comb(n: int, k: int) -> float:
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def fisher_exact(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher's exact test p-value for the 2x2 table [[a, b], [c, d]].

    The sum of the hypergeometric probabilities of every table with the same margins that
    is no more likely than the observed one (scipy's definition, with the same relative
    tolerance for ties).
    """
    row1, col1, n = a + b, a + c, a + b + c + d
    lo, hi = max(0, col1 - (n - row1)), min(row1, col1)
    log_denom = _log_comb(n, col1)

    def logp(x: int) -> float:
        return _log_comb(row1, x) + _log_comb(n - row1, col1 - x) - log_denom

    observed = logp(a)
    cutoff = observed + math.log1p(1e-7)
    total = sum(math.exp(lp) for x in range(lo, hi + 1) if (lp := logp(x)) <= cutoff)
    return min(1.0, total)


def _jr(jobs: int, repeated: int) -> JobsRepeated:
    return JobsRepeated(jobs=jobs, repeated=repeated, rate=rate_string(repeated, jobs))


def _originals(engine: Engine, start: dt.date, end: dt.date) -> list[dict]:
    """Every completed original in range: its attributes, incident types and repeat flag."""
    lo, hi = _bounds(start, end)
    repeated = exists().where(
        child.c.parent_request_id == sr.c.request_id, child.c.request_status != "cancelled"
    )
    q = (
        select(
            sr.c.request_id,
            sr.c.service_type,
            loc.c.region,
            sr.c.account_id,
            acc.c.account_name,
            sr.c.assigned_technician_id,
            tech.c.full_name,
            repeated.label("repeated"),
        )
        .select_from(
            ar.join(sr, sr.c.request_id == ar.c.request_id)
            .join(loc, loc.c.location_id == sr.c.location_id)
            .join(acc, acc.c.account_id == sr.c.account_id)
            .outerjoin(tech, tech.c.technician_id == sr.c.assigned_technician_id)
        )
        .where(and_(ar.c.completed_at >= lo, ar.c.completed_at < hi))
    )
    types_q = (
        select(inc.c.request_id, inc.c.incident_type)
        .select_from(inc.join(ar, ar.c.request_id == inc.c.request_id))
        .where(and_(ar.c.completed_at >= lo, ar.c.completed_at < hi))
    )
    with engine.connect() as conn:
        rows = [dict(r._mapping) for r in conn.execute(q)]
        types: dict[int, set[str]] = {}
        for rid, itype in conn.execute(types_q):
            types.setdefault(rid, set()).add(itype)
    for r in rows:
        r["types"] = types.get(r["request_id"], set())
    return rows


def _group_key(r: dict, by: RepeatBy) -> tuple[object, str, int | None]:
    if by == "service_type":
        return r["service_type"], r["service_type"], None
    if by == "region":
        return r["region"], r["region"], None
    if by == "account":
        return r["account_id"], r["account_name"], r["account_id"]
    tid = r["assigned_technician_id"]  # technician
    return tid, r["full_name"] or "unassigned", tid


def compute(rows: list[dict], start: dt.date, end: dt.date, by: RepeatBy) -> RepeatDriversResult:
    """Pure: rows as `_originals` returns them."""
    n = len(rows)
    total_rep = sum(r["repeated"] for r in rows)
    members: list[tuple[str, int | None, list[dict]]] = []
    if by == "incident_type":
        all_types = sorted({t for r in rows for t in r["types"]} - {DEFINING_TYPE})
        for t in all_types:
            members.append((t, None, [r for r in rows if t in r["types"]]))
    else:
        grouped: dict[object, tuple[str, int | None, list[dict]]] = {}
        for r in rows:
            key, label, gid = _group_key(r, by)
            grouped.setdefault(key, (label, gid, []))[2].append(r)
        members = list(grouped.values())

    raw = []
    for label, gid, items in members:
        jobs, rep = len(items), sum(r["repeated"] for r in items)
        rest_jobs, rest_rep = n - jobs, total_rep - rep
        compared = jobs >= MIN_GROUP_JOBS and rest_jobs > 0
        p = fisher_exact(rep, jobs - rep, rest_rep, rest_jobs - rest_rep) if compared else None
        raw.append((label, gid, jobs, rep, rest_jobs, rest_rep, compared, p))
    m = sum(1 for x in raw if x[6])
    groups = []
    for label, gid, jobs, rep, rest_jobs, rest_rep, compared, p in raw:
        p_adj = min(1.0, p * m) if p is not None else None
        higher = rest_jobs > 0 and jobs > 0 and rep * rest_jobs > rest_rep * jobs
        groups.append(
            RepeatGroup(
                group=str(label),
                group_id=gid,
                this=_jr(jobs, rep),
                rest=_jr(rest_jobs, rest_rep),
                compared=compared,
                p_value=p,
                p_adjusted=p_adj,
                stands_out=bool(compared and higher and p_adj < ALPHA),
            )
        )
    # Worst first: highest rate, then more jobs, then name.
    groups.sort(key=lambda g: (-Fraction(g.this.repeated, g.this.jobs), -g.this.jobs, g.group))
    extra = {}
    if by == "incident_type":
        other = [r for r in rows if r["types"] - {DEFINING_TYPE}]
        none = [r for r in rows if not (r["types"] - {DEFINING_TYPE})]
        a, a_rep = len(other), sum(r["repeated"] for r in other)
        b, b_rep = len(none), sum(r["repeated"] for r in none)
        # One comparison, so no Bonferroni; the same 20-job and p < 0.05 rule as the groups.
        compared = a >= MIN_GROUP_JOBS and b >= MIN_GROUP_JOBS
        p = fisher_exact(a_rep, a - a_rep, b_rep, b - b_rep) if compared else None
        extra = {
            "any_other_incident": _jr(a, a_rep),
            "no_other_incident": _jr(b, b_rep),
            "other_incident_compared": compared,
            "other_incident_p_value": p,
            "other_incident_higher": bool(compared and a_rep * b > b_rep * a and p < ALPHA),
        }
    return RepeatDriversResult(
        start=start,
        end=end,
        group_by=by,
        overall=_jr(n, total_rep),
        groups=groups[:MAX_REPEAT_GROUPS],
        group_count=len(groups),
        truncated=len(groups) > MAX_REPEAT_GROUPS,
        groups_compared=m,
        **extra,
    )


def repeat_drivers(
    engine: Engine, start: dt.date, end: dt.date, by: RepeatBy
) -> RepeatDriversResult:
    return compute(_originals(engine, start, end), start, end, by)
