"""The three metric tools' figures equal independent SQL (data dictionary §6, FR-06).

Each tool runs in-process through a real MCP client, querying the live database as
`app_reporting`. The expected figures come from hand-written SQL run as `app_qa`,
written separately from the tools' SQLAlchemy queries: raw SQL, `interval`
multiplication where the tool uses `make_interval`, and this file's own Decimal
rounding. Numerator, denominator and rate are compared, overall and for every group,
over several ranges and every allowed breakdown. One range is the regional-outage
fortnight (2025-02-17, two weeks), where the northeast is visibly skewed.

Needs a migrated and loaded database; CI loads it before this runs.
"""

from __future__ import annotations

import datetime as dt
import os
from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal

import psycopg
import pytest
from db_models.access_matrix import ROLE_QA
from mcp import Client
from mcp_incidents.config import DEFAULT_WINDOW_END, DEFAULT_WINDOW_START, Settings
from mcp_incidents.server import FIRST_TIME_FIX, INCIDENT_RATE, SLA_COMPLIANCE, create_server

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

ConnectAs = Callable[[str], psycopg.Connection]

ANOMALY = (dt.date(2025, 2, 17), dt.date(2025, 3, 2))  # parameters.py regional_drop
RANGES = [
    (DEFAULT_WINDOW_START, DEFAULT_WINDOW_END),
    (dt.date(2026, 7, 1), dt.date(2026, 7, 31)),
    (dt.date(2025, 4, 1), dt.date(2025, 6, 30)),
    ANOMALY,
]
GROUP_BYS = [None, "account", "region", "service_type", "technician"]

# --------------------------------------------------------------------------- independent SQL

LO = "(%(start)s::date)::timestamp AT TIME ZONE 'UTC'"
HI = "((%(end)s::date + 1))::timestamp AT TIME ZONE 'UTC'"


def _dimension(group_by: str | None, technician: str) -> tuple[str, str, str]:
    """(key, label, joins) for a breakdown; `technician` is whose technician counts."""
    if group_by is None:
        return "NULL", "NULL", ""
    if group_by == "account":
        return (
            "acc.account_id",
            "acc.account_name",
            ("JOIN accounts acc ON acc.account_id = r.account_id"),
        )
    if group_by == "region":
        return "loc.region", "loc.region", "JOIN locations loc ON loc.location_id = r.location_id"
    if group_by == "service_type":
        return "r.service_type", "r.service_type", ""
    return (
        "t.technician_id",
        "t.full_name",
        (f"JOIN technicians t ON t.technician_id = {technician}"),
    )


def _counts(conn, sql: str, params: dict) -> dict:
    return {(k, label): (int(a), int(b)) for k, label, a, b in conn.execute(sql, params)}


def incident_rate_sql(conn, group_by, params):
    key, label, joins = _dimension(group_by, "i.attributed_technician_id")
    incidents = _counts(
        conn,
        f"""SELECT {key}, {label}, count(*), 0
            FROM incidents i JOIN service_requests r ON r.request_id = i.request_id {joins}
            WHERE i.reported_at >= {LO} AND i.reported_at < {HI}
            GROUP BY 1, 2""",
        params,
    )
    key, label, joins = _dimension(group_by, "a.technician_id")
    completed = _counts(
        conn,
        f"""SELECT {key}, {label}, 0, count(*)
            FROM archived_requests a JOIN service_requests r ON r.request_id = a.request_id
            {joins}
            WHERE a.completed_at >= {LO} AND a.completed_at < {HI}
            GROUP BY 1, 2""",
        params,
    )
    keys = set(incidents) | set(completed)
    return {k: (incidents.get(k, (0, 0))[0], completed.get(k, (0, 0))[1]) for k in keys}, 100


def sla_sql(conn, group_by, params):
    key, label, joins = _dimension(group_by, "a.technician_id")
    return _counts(
        conn,
        f"""SELECT {key}, {label},
                   sum(CASE WHEN a.completed_at
                            <= r.dispatched_at + r.sla_window_minutes * interval '1 minute'
                       THEN 1 ELSE 0 END),
                   count(*)
            FROM service_requests r JOIN archived_requests a ON a.request_id = r.request_id
            {joins}
            WHERE r.dispatched_at >= {LO} AND r.dispatched_at < {HI}
            GROUP BY 1, 2""",
        params,
    ), 1


def ftf_sql(conn, group_by, params):
    key, label, joins = _dimension(group_by, "a.technician_id")
    return _counts(
        conn,
        f"""SELECT {key}, {label},
                   sum(CASE WHEN NOT EXISTS (
                         SELECT 1 FROM service_requests c
                         WHERE c.parent_request_id = r.request_id
                           AND c.request_status <> 'cancelled') THEN 1 ELSE 0 END),
                   count(*)
            FROM archived_requests a JOIN service_requests r ON r.request_id = a.request_id
            {joins}
            WHERE a.completed_at >= {LO} AND a.completed_at < {HI}
            GROUP BY 1, 2""",
        params,
    ), 1


def expected_rate(num: int, den: int, scale: int) -> str | None:
    if den == 0:
        return None
    exact = Decimal(num * scale) / Decimal(den)
    return str(exact.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


TOOLS = {
    INCIDENT_RATE: incident_rate_sql,
    SLA_COMPLIANCE: sla_sql,
    FIRST_TIME_FIX: ftf_sql,
}

# --------------------------------------------------------------------------- fixtures


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
def reporting_settings(live_database: None) -> Settings:
    return Settings(
        db_host=os.environ["POSTGRES_HOST"],
        db_port=int(os.environ["POSTGRES_PORT"]),
        db_name=os.environ["POSTGRES_DB"],
        db_user=os.environ["DB_ROLE_REPORTING_USER"],
        db_password=os.environ["DB_ROLE_REPORTING_PASSWORD"],
    )


async def call(settings: Settings, tool: str, start, end, group_by) -> dict:
    arguments = {"start": start.isoformat(), "end": end.isoformat()}
    if group_by is not None:
        arguments["group_by"] = group_by
    async with Client(create_server(settings)) as client:
        result = await client.call_tool(tool, arguments)
    assert not result.is_error, result.content
    return result.structured_content


# --------------------------------------------------------------------------- the comparison


@pytest.mark.parametrize("group_by", GROUP_BYS)
@pytest.mark.parametrize(("start", "end"), RANGES, ids=lambda d: d.isoformat())
@pytest.mark.parametrize("tool", list(TOOLS))
async def test_tool_figures_match_independent_sql(
    loaded_database, connect_as: ConnectAs, reporting_settings, tool, start, end, group_by
):
    got = await call(reporting_settings, tool, start, end, group_by)
    params = {"start": start, "end": end}
    qa = connect_as(ROLE_QA)
    totals, scale = TOOLS[tool](qa, None, params)
    [(num, den)] = totals.values() if totals else [(0, 0)]

    assert (got["numerator"], got["denominator"]) == (num, den)
    assert got["rate"] == expected_rate(num, den, scale)
    assert isinstance(got["rate"], str | None)  # a Decimal string, never a float

    if group_by is None:
        assert got["groups"] is None
        return
    groups, _ = TOOLS[tool](qa, group_by, params)
    expected = [
        {
            "group": str(label),
            "group_id": key if group_by in ("account", "technician") else None,
            "numerator": n,
            "denominator": d,
            "rate": expected_rate(n, d, scale),
        }
        for (key, label), (n, d) in groups.items()
    ]
    expected.sort(key=lambda g: (g["rate"] is None, -Decimal(g["rate"] or 0), g["group"]))
    assert got["group_count"] == len(expected)
    assert got["truncated"] == (len(expected) > 25)
    assert got["groups"] == expected[:25]


async def test_regional_outage_is_visible_by_region(loaded_database, reporting_settings):
    """The two-week northeast outage (85% drop) shows as a skewed grouped result."""
    got = await call(reporting_settings, SLA_COMPLIANCE, *ANOMALY, "region")
    size = {g["group"]: g["denominator"] for g in got["groups"]}
    others = [n for region, n in size.items() if region != "northeast"]
    # The northeast holds ~30% of volume by design, the largest share; in the outage
    # it has the fewest dispatched requests of any region, under half of any other's.
    assert size["northeast"] < 0.5 * min(others)


async def test_technician_incident_rate_counts_attributable_incidents_only(
    loaded_database, connect_as, reporting_settings
):
    """ADR-033: by technician, the numerator is incidents attributed to them, not every
    incident on a job they did. The data has technicians where the two differ, and the
    tool must report the attributed figure."""
    got = await call(reporting_settings, INCIDENT_RATE, *RANGES[0], "technician")
    rows = (
        connect_as(ROLE_QA)
        .execute(
            """SELECT a.technician_id,
                  count(*) FILTER (WHERE i.attributed_technician_id = a.technician_id),
                  count(*)
           FROM incidents i JOIN archived_requests a ON a.request_id = i.request_id
           GROUP BY a.technician_id"""
        )
        .fetchall()
    )
    attributed = {tech: n for tech, n, _ in rows}
    on_their_jobs = {tech: n for tech, _, n in rows}
    differs = [t for t in attributed if attributed[t] != on_their_jobs[t]]
    assert differs, "expected technicians whose attributed and on-job counts differ"
    for group in got["groups"]:
        assert group["numerator"] == attributed.get(group["group_id"], 0)
