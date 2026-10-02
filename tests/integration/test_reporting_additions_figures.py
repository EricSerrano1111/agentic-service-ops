"""ADR-073 figures equal independent SQL: incident counts by breakdown, the
single-technician filter on every tool, `find_technician`, and repeat-visit drivers.

Each tool runs in-process through a real MCP client as `app_reporting`. The expected
figures come from hand-written SQL run as `app_eval`, written separately from the tools'
SQLAlchemy queries; repeat-driver p-values are checked against scipy's Fisher test on the
SQL's own counts, and the stands-out flag is recomputed from them.

Needs a migrated and loaded database; CI loads it before this runs.
"""

from __future__ import annotations

import datetime as dt
import os
from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal

import psycopg
import pytest
from db_models.access_matrix import ROLE_EVAL
from mcp import Client
from mcp_incidents.config import DEFAULT_WINDOW_END, DEFAULT_WINDOW_START, Settings
from mcp_incidents.server import (
    FIND_TECHNICIAN,
    FIRST_TIME_FIX,
    INCIDENT_RATE,
    REPEAT_DRIVERS,
    SLA_COMPLIANCE,
    TOOL_NAME,
    create_server,
)
from scipy.stats import fisher_exact

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

ConnectAs = Callable[[str], psycopg.Connection]

RANGES = [
    (DEFAULT_WINDOW_START, DEFAULT_WINDOW_END),
    (dt.date(2026, 4, 1), dt.date(2026, 6, 30)),
    (dt.date(2026, 7, 1), dt.date(2026, 7, 31)),
]
LO = "(%(start)s::date)::timestamp AT TIME ZONE 'UTC'"
HI = "((%(end)s::date + 1))::timestamp AT TIME ZONE 'UTC'"


def rate(num: int, den: int, scale: int = 1) -> str | None:
    if den == 0:
        return None
    exact = Decimal(num * scale) / Decimal(den)
    return str(exact.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
def settings(live_database: None) -> Settings:
    return Settings(
        db_host=os.environ["POSTGRES_HOST"],
        db_port=int(os.environ["POSTGRES_PORT"]),
        db_name=os.environ["POSTGRES_DB"],
        db_user=os.environ["DB_ROLE_REPORTING_USER"],
        db_password=os.environ["DB_ROLE_REPORTING_PASSWORD"],
    )


async def call(settings: Settings, tool: str, arguments: dict) -> dict:
    async with Client(create_server(settings)) as client:
        result = await client.call_tool(tool, arguments)
    assert not result.is_error, result.content
    return result.structured_content


def _range(start, end) -> dict:
    return {"start": start.isoformat(), "end": end.isoformat()}


# --------------------------------------------------------------------------- incident counts

COUNT_SQL = {
    "account": (
        "acc.account_id, acc.account_name",
        "JOIN service_requests r ON r.request_id = i.request_id "
        "JOIN accounts acc ON acc.account_id = r.account_id",
    ),
    "region": (
        "NULL::bigint, loc.region",
        "JOIN service_requests r ON r.request_id = i.request_id "
        "JOIN locations loc ON loc.location_id = r.location_id",
    ),
    "service_type": (
        "NULL::bigint, r.service_type::text",
        "JOIN service_requests r ON r.request_id = i.request_id",
    ),
    "technician": (
        "i.attributed_technician_id, coalesce(t.full_name, 'unattributed')",
        "LEFT JOIN technicians t ON t.technician_id = i.attributed_technician_id",
    ),
    "incident_type": ("NULL::bigint, i.incident_type::text", ""),
    "severity": ("NULL::bigint, i.severity::text", ""),
}


@pytest.mark.parametrize("group_by", list(COUNT_SQL))
@pytest.mark.parametrize(("start", "end"), RANGES, ids=lambda d: d.isoformat())
async def test_incident_count_breakdowns_match_independent_sql(
    loaded_database, connect_as: ConnectAs, settings, group_by, start, end
):
    got = await call(settings, TOOL_NAME, _range(start, end) | {"group_by": group_by})
    cols, joins = COUNT_SQL[group_by]
    rows = (
        connect_as(ROLE_EVAL)
        .execute(
            f"""SELECT {cols}, count(*) FROM incidents i {joins}
                WHERE i.reported_at >= {LO} AND i.reported_at < {HI}
                GROUP BY 1, 2""",
            {"start": start, "end": end},
        )
        .fetchall()
    )
    expected = [
        {
            "group": str(label),
            "group_id": key if group_by in ("account", "technician") else None,
            "count": int(n),
        }
        for key, label, n in rows
    ]
    expected.sort(key=lambda g: (-g["count"], g["group"]))
    assert got["incident_count"] == sum(g["count"] for g in expected)
    assert got["group_count"] == len(expected)
    assert got["truncated"] == (len(expected) > 25)
    assert got["groups"] == expected[:25]


# --------------------------------------------------------------------------- one technician


@pytest.fixture(scope="module")
def technicians(connect_as: ConnectAs, loaded_database) -> list[tuple[int, str]]:
    rows = connect_as(ROLE_EVAL).execute(
        "SELECT technician_id, full_name FROM technicians ORDER BY technician_id"
    )
    return [(int(i), n) for i, n in rows]


def _technician_sql(conn, tool: str, tid: int, params: dict) -> tuple[int, int]:
    p = params | {"tid": tid}
    if tool == TOOL_NAME:
        return conn.execute(
            f"""SELECT count(*), 0 FROM incidents i WHERE i.attributed_technician_id = %(tid)s
                AND i.reported_at >= {LO} AND i.reported_at < {HI}""",
            p,
        ).fetchone()
    if tool == INCIDENT_RATE:
        (num,) = conn.execute(
            f"""SELECT count(*) FROM incidents i WHERE i.attributed_technician_id = %(tid)s
                AND i.reported_at >= {LO} AND i.reported_at < {HI}""",
            p,
        ).fetchone()
        (den,) = conn.execute(
            f"""SELECT count(*) FROM archived_requests a WHERE a.technician_id = %(tid)s
                AND a.completed_at >= {LO} AND a.completed_at < {HI}""",
            p,
        ).fetchone()
        return num, den
    if tool == SLA_COMPLIANCE:
        return conn.execute(
            f"""SELECT count(*) FILTER (WHERE a.completed_at
                         <= r.dispatched_at + r.sla_window_minutes * interval '1 minute'),
                       count(*)
                FROM service_requests r JOIN archived_requests a ON a.request_id = r.request_id
                WHERE a.technician_id = %(tid)s
                  AND r.dispatched_at >= {LO} AND r.dispatched_at < {HI}""",
            p,
        ).fetchone()
    return conn.execute(
        f"""SELECT count(*) FILTER (WHERE NOT EXISTS (
                       SELECT 1 FROM service_requests c WHERE c.parent_request_id = a.request_id
                         AND c.request_status <> 'cancelled')),
                   count(*)
            FROM archived_requests a
            WHERE a.technician_id = %(tid)s
              AND a.completed_at >= {LO} AND a.completed_at < {HI}""",
        p,
    ).fetchone()


@pytest.mark.parametrize("tool", [TOOL_NAME, INCIDENT_RATE, SLA_COMPLIANCE, FIRST_TIME_FIX])
@pytest.mark.parametrize(("start", "end"), RANGES[1:], ids=lambda d: d.isoformat())
async def test_technician_filter_matches_independent_sql(
    loaded_database, connect_as: ConnectAs, settings, technicians, tool, start, end
):
    oracle = connect_as(ROLE_EVAL)
    params = {"start": start, "end": end}
    for tid, name in technicians[::4]:  # every fourth: 8 technicians, both large and small
        got = await call(settings, tool, _range(start, end) | {"technician_id": tid})
        num, den = _technician_sql(oracle, tool, tid, params)
        assert (got["technician_id"], got["technician_name"]) == (tid, name)
        if tool == TOOL_NAME:
            assert got["incident_count"] == num
            continue
        assert (got["numerator"], got["denominator"]) == (num, den)
        assert got["rate"] == rate(num, den, 100 if tool == INCIDENT_RATE else 1)


async def test_unknown_technician_id_is_rejected(loaded_database, settings):
    async with Client(create_server(settings)) as client:
        result = await client.call_tool(
            SLA_COMPLIANCE, _range(*RANGES[2]) | {"technician_id": 999_999}
        )
    assert result.is_error and "no technician has id 999999" in result.content[0].text


async def test_find_technician_matches_sql_by_full_name_and_first_name(
    loaded_database, connect_as: ConnectAs, settings, technicians
):
    oracle = connect_as(ROLE_EVAL)
    for tid, name in technicians:
        got = await call(settings, FIND_TECHNICIAN, {"name": name.upper()})
        assert got["total_matches"] == 1 and got["matches"] == [
            {"technician_id": tid, "full_name": name}
        ]
    shared = oracle.execute(
        """SELECT split_part(full_name, ' ', 1), count(*) FROM technicians
           GROUP BY 1 HAVING count(*) > 1"""
    ).fetchall()
    assert shared, "expected first names shared by more than one technician"
    for first, n in shared:
        got = await call(settings, FIND_TECHNICIAN, {"name": first.lower()})
        assert got["total_matches"] == n and len(got["matches"]) == min(n, 5)


# --------------------------------------------------------------------------- repeat drivers

ORIGINALS = f"""
    SELECT r.request_id, r.service_type::text AS service_type, loc.region,
           r.account_id, acc.account_name, r.assigned_technician_id AS tech, t.full_name,
           EXISTS (SELECT 1 FROM service_requests c WHERE c.parent_request_id = r.request_id
                   AND c.request_status <> 'cancelled') AS repeated,
           ARRAY(SELECT DISTINCT i.incident_type::text FROM incidents i
                 WHERE i.request_id = r.request_id) AS types
    FROM archived_requests a
    JOIN service_requests r ON r.request_id = a.request_id
    JOIN locations loc ON loc.location_id = r.location_id
    JOIN accounts acc ON acc.account_id = r.account_id
    LEFT JOIN technicians t ON t.technician_id = r.assigned_technician_id
    WHERE a.completed_at >= {LO} AND a.completed_at < {HI}
"""
RVR = "repeat_visit_required"


def _expected_groups(rows, by):
    """{label: (group_id, jobs, repeated)} from the SQL rows."""
    out: dict[str, list] = {}
    for r in rows:
        if by == "incident_type":
            keys = [(t, None) for t in r["types"] if t != RVR]
        elif by == "account":
            keys = [(r["account_name"], r["account_id"])]
        elif by == "technician":
            keys = [(r["full_name"] or "unassigned", r["tech"])]
        else:
            keys = [(r[by], None)]
        for label, gid in keys:
            entry = out.setdefault(label, [gid, 0, 0])
            entry[1] += 1
            entry[2] += r["repeated"]
    return out


@pytest.mark.parametrize("by", ["incident_type", "service_type", "region", "account", "technician"])
@pytest.mark.parametrize(("start", "end"), RANGES, ids=lambda d: d.isoformat())
async def test_repeat_drivers_match_independent_sql_and_scipy(
    loaded_database, connect_as: ConnectAs, settings, by, start, end
):
    got = await call(settings, REPEAT_DRIVERS, _range(start, end) | {"by": by})
    cur = connect_as(ROLE_EVAL).cursor(row_factory=psycopg.rows.dict_row)
    rows = cur.execute(ORIGINALS, {"start": start, "end": end}).fetchall()
    n, rep = len(rows), sum(r["repeated"] for r in rows)
    assert got["overall"] == {"jobs": n, "repeated": rep, "rate": rate(rep, n)}

    expected = _expected_groups(rows, by)
    compared = sum(1 for _, jobs, _ in expected.values() if jobs >= 20 and n - jobs > 0)
    assert got["group_count"] == len(expected) and got["groups_compared"] == compared
    assert all(g["group"] != RVR for g in got["groups"])
    for g in got["groups"]:
        gid, jobs, r = expected[g["group"]]
        assert g["group_id"] == gid
        assert g["this"] == {"jobs": jobs, "repeated": r, "rate": rate(r, jobs)}
        rest_j, rest_r = n - jobs, rep - r
        assert g["rest"] == {"jobs": rest_j, "repeated": rest_r, "rate": rate(rest_r, rest_j)}
        assert g["compared"] == (jobs >= 20 and rest_j > 0)
        if not g["compared"]:
            assert g["p_value"] is None and not g["stands_out"]
            continue
        p = float(fisher_exact([[r, jobs - r], [rest_r, rest_j - rest_r]]).pvalue)
        assert g["p_value"] == pytest.approx(p, rel=1e-9, abs=1e-12)
        adjusted = min(1.0, p * compared)
        assert g["p_adjusted"] == pytest.approx(adjusted, rel=1e-9, abs=1e-12)
        higher = r * rest_j > rest_r * jobs
        assert g["stands_out"] == (higher and adjusted < 0.05)
    # Worst first: highest repeat rate, then more jobs, then name.
    order = [
        (-Decimal(g["this"]["repeated"]) / g["this"]["jobs"], -g["this"]["jobs"], g["group"])
        for g in got["groups"]
    ]
    assert order == sorted(order)

    if by == "incident_type":
        other = [r for r in rows if set(r["types"]) - {RVR}]
        none = [r for r in rows if not set(r["types"]) - {RVR}]
        for key, part in (("any_other_incident", other), ("no_other_incident", none)):
            k, kr = len(part), sum(r["repeated"] for r in part)
            assert got[key] == {"jobs": k, "repeated": kr, "rate": rate(kr, k)}
    else:
        assert got["any_other_incident"] is None and got["no_other_incident"] is None


async def test_every_repeat_has_a_repeat_visit_required_incident(
    loaded_database, connect_as: ConnectAs
):
    """The coherence fact every repeat-drivers answer states (ADR-073)."""
    (missing,) = (
        connect_as(ROLE_EVAL)
        .execute(
            f"""SELECT count(*) FROM service_requests c
                WHERE c.parent_request_id IS NOT NULL AND c.request_status <> 'cancelled'
                  AND NOT EXISTS (SELECT 1 FROM incidents i
                                  WHERE i.request_id = c.parent_request_id
                                    AND i.incident_type = '{RVR}')"""
        )
        .fetchone()
    )
    assert missing == 0
