"""QA's own SQL over the `app_qa` role (data dictionary §6, §7; ADR-055, ADR-087).

Every query is written from the data dictionary's metric definitions, not from the incidents or
volume servers' code, and none of it imports them or `db_models`. Bound parameters only; the
few identifiers that vary (a join, a column) come from closed tables in this file, never from
the answer or the question. Counts, never rows with free text: `incident_notes` and
`feedback_text` are never selected.

The `Source` protocol is what the checks need, so they can be unit tested against a fake and
integration tested against the loaded database.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL

from .config import Settings

SEVERITIES = ("low", "medium", "high")
UNATTRIBUTED = "unattributed"


@dataclass(frozen=True)
class GroupRow:
    """One group's raw counts. `key` identifies the group; `label` is its display name."""

    key: Any
    label: str
    group_id: int | None
    numerator: int
    denominator: int


class Source(Protocol):
    def ping(self) -> None: ...

    def severity_counts(
        self,
        lo: dt.datetime,
        hi: dt.datetime,
        region: str | None,
        account_id: int | None,
        technician_id: int | None,
    ) -> dict[str, int]: ...

    def count_groups(
        self,
        lo: dt.datetime,
        hi: dt.datetime,
        group_by: str,
        region: str | None,
        account_id: int | None,
    ) -> list[GroupRow]: ...

    def metric_counts(
        self,
        metric: str,
        lo: dt.datetime,
        hi: dt.datetime,
        region: str | None,
        account_id: int | None,
        technician_id: int | None,
    ) -> tuple[int, int]: ...

    def metric_groups(
        self,
        metric: str,
        lo: dt.datetime,
        hi: dt.datetime,
        group_by: str,
        region: str | None,
        account_id: int | None,
    ) -> list[GroupRow]: ...

    def repeat_jobs(
        self, lo: dt.datetime, hi: dt.datetime
    ) -> tuple[list[dict[str, Any]], dict[int, set[str]]]: ...

    def technicians(self) -> list[tuple[int, str]]: ...

    def accounts(self) -> list[tuple[int, str]]: ...

    def weekly_counts(
        self, slice_: str, first_week: dt.date, last_week: dt.date
    ) -> dict[dt.date, int]: ...


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
            "application_name": "agent_qa",
        },
    )


def utc_bounds(start: dt.date, end: dt.date) -> tuple[dt.datetime, dt.datetime]:
    """Inclusive UTC days as a half-open timestamp range [lo, hi) (§6 date filters)."""
    lo = dt.datetime.combine(start, dt.time.min, dt.UTC)
    hi = dt.datetime.combine(end + dt.timedelta(days=1), dt.time.min, dt.UTC)
    return lo, hi


# --------------------------------------------------------------------------- SQL fragments

# Each event table joined to its request, the request's site and its account. Every join is
# on a NOT NULL foreign key, so none drops a row.
_JOINS = (
    " JOIN service_requests r ON r.request_id = {t}.request_id"
    " JOIN locations l ON l.location_id = r.location_id"
    " JOIN accounts ac ON ac.account_id = r.account_id"
)


@dataclass(frozen=True)
class _Events:
    """The rows a metric part counts: where they come from, the timestamp §6 filters on, the
    technician column its technician breakdown and filter use, and the `hit` condition."""

    source: str
    when: str
    technician: str
    hit: str = "TRUE"


# §6 date filters: incidents by reported_at; completed requests by completed_at; SLA by
# dispatched_at over completed requests (a request never completed has no sla_met, so it is
# not counted); first-time fix by completed_at, a child counting whatever its own date.
_INCIDENTS = _Events(
    "incidents i" + _JOINS.format(t="i"), "i.reported_at", "i.attributed_technician_id"
)
_COMPLETED = _Events(
    "archived_requests ar" + _JOINS.format(t="ar"), "ar.completed_at", "ar.technician_id"
)
_SLA = _Events(
    "archived_requests ar" + _JOINS.format(t="ar"),
    "r.dispatched_at",
    "ar.technician_id",
    "ar.completed_at <= r.dispatched_at + r.sla_window_minutes * interval '1 minute'",
)
_FIXED_FIRST_TIME = (
    "NOT EXISTS (SELECT 1 FROM service_requests c WHERE c.parent_request_id = r.request_id"
    " AND c.request_status <> 'cancelled')"
)
_FTF = _Events(
    "archived_requests ar" + _JOINS.format(t="ar"),
    "ar.completed_at",
    "ar.technician_id",
    _FIXED_FIRST_TIME,
)

#: metric -> (numerator events, denominator events, scale)
_METRICS: dict[str, tuple[_Events, _Events, int]] = {
    "incident_rate": (_INCIDENTS, _COMPLETED, 100),
    "sla_compliance": (_SLA, _SLA, 1),
    "first_time_fix_rate": (_FTF, _FTF, 1),
}

# group_by -> (key, label, id) expressions over r, l, ac; technician is added per events.
_DIMENSIONS = {
    "account": ("ac.account_id", "ac.account_name", "ac.account_id"),
    "region": ("l.region", "l.region", "NULL"),
    "service_type": ("r.service_type", "r.service_type", "NULL"),
}


def _group_by(key: str, label: str, gid: str) -> str:
    """The GROUP BY list: Postgres rejects a constant in it, so a NULL id is left out."""
    return ", ".join([key, label] + ([] if gid == "NULL" else [gid]))


def _filters(
    ev: _Events, region: str | None, account_id: int | None, technician_id: int | None
) -> tuple[str, dict[str, Any]]:
    conds, params = [f"{ev.when} >= :lo", f"{ev.when} < :hi"], {}
    if region is not None:
        conds.append("l.region = :region")
        params["region"] = region
    if account_id is not None:
        conds.append("r.account_id = :account_id")
        params["account_id"] = account_id
    if technician_id is not None:
        conds.append(f"{ev.technician} = :technician_id")
        params["technician_id"] = technician_id
    return " AND ".join(conds), params


class PostgresSource:
    """The loaded database, read as `app_qa`."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def _rows(self, sql: str, params: dict[str, Any] | None = None) -> list[Any]:
        with self.engine.connect() as conn:
            return list(conn.execute(text(sql), params or {}))

    def ping(self) -> None:
        self._rows("SELECT 1")

    # ------------------------------------------------------------------ incident counts

    def severity_counts(self, lo, hi, region, account_id, technician_id) -> dict[str, int]:
        where, params = _filters(_INCIDENTS, region, account_id, technician_id)
        rows = self._rows(
            f"SELECT i.severity, count(*) FROM {_INCIDENTS.source} WHERE {where} "
            "GROUP BY i.severity",
            {"lo": lo, "hi": hi, **params},
        )
        counts = dict.fromkeys(SEVERITIES, 0)
        for severity, n in rows:
            counts[severity] = int(n)
        return counts

    def count_groups(self, lo, hi, group_by, region, account_id) -> list[GroupRow]:
        """Incident counts by a breakdown (§6): by the incident's request for account, region
        and service type; by its own column for incident type and severity; by the attributed
        technician, with incidents attributed to no one as their own group."""
        where, params = _filters(_INCIDENTS, region, account_id, None)
        source = _INCIDENTS.source
        if group_by in ("incident_type", "severity"):
            column = f"i.{group_by}"
            key, label, gid = column, column, "NULL"
        elif group_by == "technician":
            source += " LEFT JOIN technicians t ON t.technician_id = i.attributed_technician_id"
            key, label, gid = "i.attributed_technician_id", "t.full_name", "t.technician_id"
        else:
            key, label, gid = _DIMENSIONS[group_by]
        rows = self._rows(
            f"SELECT {key} AS k, {label} AS lbl, {gid} AS gid, count(*) AS n FROM {source} "
            f"WHERE {where} GROUP BY {_group_by(key, label, gid)}",
            {"lo": lo, "hi": hi, **params},
        )
        return [
            GroupRow(
                key=r.k,
                label=UNATTRIBUTED if (group_by == "technician" and r.k is None) else str(r.lbl),
                group_id=None if r.gid is None else int(r.gid),
                numerator=int(r.n),
                denominator=0,
            )
            for r in rows
        ]

    # ------------------------------------------------------------------ rate metrics

    def metric_counts(self, metric, lo, hi, region, account_id, technician_id) -> tuple[int, int]:
        numer, denom, _ = _METRICS[metric]
        where, params = _filters(numer, region, account_id, technician_id)
        n = self._rows(
            f"SELECT count(*) FILTER (WHERE {numer.hit}) FROM {numer.source} WHERE {where}",
            {"lo": lo, "hi": hi, **params},
        )[0][0]
        where, params = _filters(denom, region, account_id, technician_id)
        d = self._rows(
            f"SELECT count(*) FROM {denom.source} WHERE {where}",
            {"lo": lo, "hi": hi, **params},
        )[0][0]
        return int(n), int(d)

    def metric_groups(self, metric, lo, hi, group_by, region, account_id) -> list[GroupRow]:
        """Numerator and denominator per group. A group is any that has a numerator or a
        denominator row. Technician groups are those in `technicians`: an incident attributed
        to no technician belongs to no group (rate metrics have no "unattributed" row)."""
        numer, denom, _ = _METRICS[metric]
        found: dict[Any, list] = {}
        for index, ev in enumerate((numer, denom)):
            where, params = _filters(ev, region, account_id, None)
            source = ev.source
            if group_by == "technician":
                source += f" JOIN technicians t ON t.technician_id = {ev.technician}"
                key, label, gid = "t.technician_id", "t.full_name", "t.technician_id"
            else:
                key, label, gid = _DIMENSIONS[group_by]
            hit = ev.hit if index == 0 else "TRUE"
            rows = self._rows(
                f"SELECT {key} AS k, {label} AS lbl, {gid} AS gid, "
                f"count(*) FILTER (WHERE {hit}) AS n FROM {source} WHERE {where} "
                f"GROUP BY {_group_by(key, label, gid)}",
                {"lo": lo, "hi": hi, **params},
            )
            for r in rows:
                entry = found.setdefault(
                    r.k, [str(r.lbl), None if r.gid is None else int(r.gid), 0, 0]
                )
                entry[2 + index] = int(r.n)
        return [GroupRow(k, v[0], v[1], v[2], v[3]) for k, v in found.items()]

    # ------------------------------------------------------------------ repeat drivers

    def repeat_jobs(self, lo, hi):
        """Jobs completed in the range (§6), each with whether it repeated, plus each job's
        incident types."""
        params = {"lo": lo, "hi": hi}
        jobs = [
            {
                "request_id": r.request_id,
                "service_type": r.service_type,
                "region": r.region,
                "account_id": r.account_id,
                "account_name": r.account_name,
                "technician_id": r.assigned_technician_id,
                "technician_name": r.full_name,
                "repeated": bool(r.repeated),
            }
            for r in self._rows(
                "SELECT r.request_id, r.service_type, l.region AS region, r.account_id,"
                " ac.account_name, r.assigned_technician_id, t.full_name,"
                " EXISTS (SELECT 1 FROM service_requests c WHERE c.parent_request_id ="
                " r.request_id AND c.request_status <> 'cancelled') AS repeated"
                " FROM archived_requests ar"
                " JOIN service_requests r ON r.request_id = ar.request_id"
                " JOIN locations l ON l.location_id = r.location_id"
                " JOIN accounts ac ON ac.account_id = r.account_id"
                " LEFT JOIN technicians t ON t.technician_id = r.assigned_technician_id"
                " WHERE ar.completed_at >= :lo AND ar.completed_at < :hi",
                params,
            )
        ]
        types: dict[int, set[str]] = {}
        for rid, itype in self._rows(
            "SELECT DISTINCT i.request_id, i.incident_type FROM incidents i"
            " JOIN archived_requests ar ON ar.request_id = i.request_id"
            " WHERE ar.completed_at >= :lo AND ar.completed_at < :hi",
            params,
        ):
            types.setdefault(rid, set()).add(itype)
        return jobs, types

    # ------------------------------------------------------------------ lookups, history

    def technicians(self) -> list[tuple[int, str]]:
        return [
            (int(r[0]), str(r[1]))
            for r in self._rows("SELECT technician_id, full_name FROM technicians")
        ]

    def accounts(self) -> list[tuple[int, str]]:
        return [
            (int(r[0]), str(r[1]))
            for r in self._rows("SELECT account_id, account_name FROM accounts")
        ]

    def weekly_counts(self, slice_, first_week, last_week) -> dict[dt.date, int]:
        """Requests by `scheduled_datetime`, in ISO weeks (Monday, UTC), all statuses (§6:
        the target is demand, not completions); a service-type slice filters on the column."""
        lo = dt.datetime.combine(first_week, dt.time.min, dt.UTC)
        hi = dt.datetime.combine(last_week + dt.timedelta(days=7), dt.time.min, dt.UTC)
        extra = "" if slice_ == "total" else " AND service_type = :slice"
        params: dict[str, Any] = {"lo": lo, "hi": hi}
        if slice_ != "total":
            params["slice"] = slice_
        rows = self._rows(
            "SELECT (date_trunc('week', scheduled_datetime AT TIME ZONE 'UTC'))::date AS wk,"
            " count(*) AS n FROM service_requests"
            f" WHERE scheduled_datetime >= :lo AND scheduled_datetime < :hi{extra} GROUP BY wk",
            params,
        )
        return {r.wk: int(r.n) for r in rows}
