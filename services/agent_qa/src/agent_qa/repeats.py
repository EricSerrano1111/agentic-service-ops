"""Repeat-visit drivers, recomputed from data dictionary §6 (ADR-073 rules, ADR-087).

Jobs are requests completed in the range; a job repeated if it has a non-cancelled child
request, whatever the child's date. Each group is compared with every other job in range by a
two-sided Fisher's exact test, Bonferroni-corrected across the groups that have at least 20
jobs; a group stands out only if it has at least 20 jobs, a repeat rate above the rest's and a
corrected p below 0.05. Groups are listed by repeat rate (highest first), then more jobs, then
name; at most 25. By incident type, each type except `repeat_visit_required` is compared jobs
with it against jobs without it, plus one comparison of any-other-incident against none (at
least 20 jobs on each side, p < 0.05, no Bonferroni).

Where §6 is silent and the code reads it one way, the gap is recorded in L-72: an incident
type with no job in range (listed with zero jobs, or left out), and a group that leaves no
"rest" to compare with.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from .stats import fisher_two_sided, rate_string

MIN_JOBS = 20
ALPHA = 0.05
MAX_GROUPS = 25
DEFINING_TYPE = "repeat_visit_required"


@dataclass(frozen=True)
class Tally:
    jobs: int
    repeated: int

    @property
    def rate(self) -> str | None:
        return rate_string(self.repeated, self.jobs)


@dataclass(frozen=True)
class Group:
    label: str
    group_id: int | None
    this: Tally
    rest: Tally
    compared: bool
    p_value: float | None
    p_adjusted: float | None
    stands_out: bool


@dataclass(frozen=True)
class Drivers:
    overall: Tally
    groups: list[Group]  # sorted, uncapped
    groups_compared: int
    other: tuple[Tally, Tally, bool, float | None, bool] | None  # incident_type only


def _key(job: dict[str, Any], by: str) -> tuple[Any, str, int | None]:
    if by == "service_type":
        return job["service_type"], job["service_type"], None
    if by == "region":
        return job["region"], job["region"], None
    if by == "account":
        return job["account_id"], job["account_name"], job["account_id"]
    # technician: the original job's assigned technician; none is "unassigned" (§6)
    tid = job["technician_id"]
    return tid, job["technician_name"] or "unassigned", tid


def compute(jobs: list[dict[str, Any]], types: dict[int, set[str]], by: str) -> Drivers:
    total = Tally(len(jobs), sum(j["repeated"] for j in jobs))
    members: list[tuple[str, int | None, list[dict[str, Any]]]] = []
    if by == "incident_type":
        seen = {t for ts in types.values() for t in ts} - {DEFINING_TYPE}
        for t in sorted(seen):
            members.append((t, None, [j for j in jobs if t in types.get(j["request_id"], ())]))
    else:
        grouped: dict[Any, tuple[str, int | None, list]] = {}
        for j in jobs:
            key, label, gid = _key(j, by)
            grouped.setdefault(key, (label, gid, []))[2].append(j)
        members = list(grouped.values())

    raw = []
    for label, gid, items in members:
        this = Tally(len(items), sum(j["repeated"] for j in items))
        rest = Tally(total.jobs - this.jobs, total.repeated - this.repeated)
        compared = this.jobs >= MIN_JOBS
        p = None
        if compared and rest.jobs > 0:
            p = fisher_two_sided(
                this.repeated, this.jobs - this.repeated, rest.repeated, rest.jobs - rest.repeated
            )
        raw.append((label, gid, this, rest, compared, p))
    m = sum(1 for r in raw if r[4])
    groups = []
    for label, gid, this, rest, compared, p in raw:
        adjusted = None if p is None else min(1.0, p * m)
        higher = rest.jobs > 0 and this.repeated * rest.jobs > rest.repeated * this.jobs
        groups.append(
            Group(
                label,
                gid,
                this,
                rest,
                compared,
                p,
                adjusted,
                bool(compared and higher and adjusted is not None and adjusted < ALPHA),
            )
        )
    groups.sort(key=lambda g: (-Fraction(g.this.repeated, g.this.jobs), -g.this.jobs, g.label))

    other = None
    if by == "incident_type":
        with_other = [j for j in jobs if types.get(j["request_id"], set()) - {DEFINING_TYPE}]
        without = [j for j in jobs if not (types.get(j["request_id"], set()) - {DEFINING_TYPE})]
        a = Tally(len(with_other), sum(j["repeated"] for j in with_other))
        b = Tally(len(without), sum(j["repeated"] for j in without))
        compared = a.jobs >= MIN_JOBS and b.jobs >= MIN_JOBS
        p = (
            fisher_two_sided(a.repeated, a.jobs - a.repeated, b.repeated, b.jobs - b.repeated)
            if compared
            else None
        )
        higher = bool(compared and a.repeated * b.jobs > b.repeated * a.jobs and p < ALPHA)
        other = (a, b, compared, p, higher)
    return Drivers(total, groups, m, other)
