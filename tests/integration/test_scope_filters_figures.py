"""Region and account filters equal their group's row (ADR-086, data dictionary §6).

The invariant: **a filtered figure equals that group's row in the matching unfiltered
breakdown**, for the incident count and the three metrics, by region and by account. Every
expectation here comes from hand-written SQL run as `app_eval`, separate from the tools'
SQLAlchemy queries: the filtered scalar from a raw `WHERE`, the group row from a raw
`GROUP BY`. The tool's own breakdown row is compared too where the 25-group cap leaves it
in the list. Needs a migrated and loaded database; CI loads it before this runs.
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
    FIRST_TIME_FIX,
    INCIDENT_RATE,
    SLA_COMPLIANCE,
    TOOL_NAME,
    create_server,
)

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

ConnectAs = Callable[[str], psycopg.Connection]

REGIONS = ["northeast", "southeast", "central", "west"]
JULY = (dt.date(2026, 7, 1), dt.date(2026, 7, 31))
ANOMALY = (dt.date(2025, 2, 17), dt.date(2025, 3, 2))  # the regional-outage fortnight
FULL = (DEFAULT_WINDOW_START, DEFAULT_WINDOW_END)
RANGES = [JULY, ANOMALY, FULL]
METRICS = [INCIDENT_RATE, SLA_COMPLIANCE, FIRST_TIME_FIX]
ALL_TOOLS = [TOOL_NAME, *METRICS]
SCALE = {INCIDENT_RATE: 100, SLA_COMPLIANCE: 1, FIRST_TIME_FIX: 1}

LO = "(%(start)s::date)::timestamp AT TIME ZONE 'UTC'"
HI = "((%(end)s::date + 1))::timestamp AT TIME ZONE 'UTC'"
LOC = "JOIN locations loc ON loc.location_id = r.location_id"


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


async def call(settings: Settings, tool: str, start, end, **arguments) -> dict:
    arguments = {"start": start.isoformat(), "end": end.isoformat(), **arguments}
    async with Client(create_server(settings)) as client:
        result = await client.call_tool(tool, arguments)
    assert not result.is_error, result.content
    return result.structured_content


def rate(num: int, den: int, scale: int) -> str | None:
    if den == 0:
        return None
    return str((Decimal(num * scale) / Decimal(den)).quantize(Decimal("0.0001"), ROUND_HALF_UP))


# --------------------------------------------------------------------------- independent SQL


def _where(region, account, tech_column, technician):
    joins, preds = [], []
    if region is not None:
        joins.append(LOC)
        preds.append("loc.region = %(region)s")
    if account is not None:
        preds.append("r.account_id = %(account)s")
    if technician is not None:
        preds.append(f"{tech_column} = %(technician)s")
    return " ".join(joins), "".join(f" AND {p}" for p in preds)


def raw_scalar(conn, tool, start, end, region=None, account=None, technician=None):
    """(numerator, denominator) for one filter combination, as raw SQL."""
    params = {
        "start": start,
        "end": end,
        "region": region,
        "account": account,
        "technician": technician,
    }
    if tool in (INCIDENT_RATE, TOOL_NAME):
        j, w = _where(region, account, "i.attributed_technician_id", technician)
        (incidents,) = conn.execute(
            f"""SELECT count(*) FROM incidents i
                JOIN service_requests r ON r.request_id = i.request_id {j}
                WHERE i.reported_at >= {LO} AND i.reported_at < {HI}{w}""",
            params,
        ).fetchone()
        if tool == TOOL_NAME:
            return int(incidents), 0
        j, w = _where(region, account, "a.technician_id", technician)
        (completed,) = conn.execute(
            f"""SELECT count(*) FROM archived_requests a
                JOIN service_requests r ON r.request_id = a.request_id {j}
                WHERE a.completed_at >= {LO} AND a.completed_at < {HI}{w}""",
            params,
        ).fetchone()
        return int(incidents), int(completed)
    j, w = _where(region, account, "a.technician_id", technician)
    if tool == SLA_COMPLIANCE:
        num, den = conn.execute(
            f"""SELECT coalesce(sum(CASE WHEN a.completed_at
                            <= r.dispatched_at + r.sla_window_minutes * interval '1 minute'
                       THEN 1 ELSE 0 END), 0), count(*)
                FROM service_requests r JOIN archived_requests a ON a.request_id = r.request_id {j}
                WHERE r.dispatched_at >= {LO} AND r.dispatched_at < {HI}{w}""",
            params,
        ).fetchone()
        return int(num), int(den)
    num, den = conn.execute(
        f"""SELECT coalesce(sum(CASE WHEN NOT EXISTS (
                      SELECT 1 FROM service_requests c
                      WHERE c.parent_request_id = r.request_id
                        AND c.request_status <> 'cancelled') THEN 1 ELSE 0 END), 0), count(*)
            FROM archived_requests a JOIN service_requests r ON r.request_id = a.request_id {j}
            WHERE a.completed_at >= {LO} AND a.completed_at < {HI}{w}""",
        params,
    ).fetchone()
    return int(num), int(den)


def raw_group_rows(conn, tool, start, end, dimension):
    """{group key: (numerator, denominator)} for the unfiltered breakdown by `region` or
    `account`, as raw `GROUP BY` SQL (account groups are keyed by account_id)."""
    key = "loc.region" if dimension == "region" else "r.account_id"
    join = LOC if dimension == "region" else ""
    params = {"start": start, "end": end}
    rows: dict = {}
    if tool in (INCIDENT_RATE, TOOL_NAME):
        for k, n in conn.execute(
            f"""SELECT {key}, count(*) FROM incidents i
                JOIN service_requests r ON r.request_id = i.request_id {join}
                WHERE i.reported_at >= {LO} AND i.reported_at < {HI} GROUP BY 1""",
            params,
        ):
            rows[k] = [int(n), 0]
        if tool == INCIDENT_RATE:
            for k, n in conn.execute(
                f"""SELECT {key}, count(*) FROM archived_requests a
                    JOIN service_requests r ON r.request_id = a.request_id {join}
                    WHERE a.completed_at >= {LO} AND a.completed_at < {HI} GROUP BY 1""",
                params,
            ):
                rows.setdefault(k, [0, 0])[1] = int(n)
        return {k: tuple(v) for k, v in rows.items()}
    if tool == SLA_COMPLIANCE:
        sql = f"""SELECT {key}, coalesce(sum(CASE WHEN a.completed_at
                        <= r.dispatched_at + r.sla_window_minutes * interval '1 minute'
                    THEN 1 ELSE 0 END), 0), count(*)
                FROM service_requests r JOIN archived_requests a ON a.request_id = r.request_id
                {join} WHERE r.dispatched_at >= {LO} AND r.dispatched_at < {HI} GROUP BY 1"""
    else:
        sql = f"""SELECT {key}, coalesce(sum(CASE WHEN NOT EXISTS (
                        SELECT 1 FROM service_requests c WHERE c.parent_request_id = r.request_id
                          AND c.request_status <> 'cancelled') THEN 1 ELSE 0 END), 0), count(*)
                FROM archived_requests a JOIN service_requests r ON r.request_id = a.request_id
                {join} WHERE a.completed_at >= {LO} AND a.completed_at < {HI} GROUP BY 1"""
    return {k: (int(n), int(d)) for k, n, d in conn.execute(sql, params)}


def figure(tool: str, got: dict) -> tuple[int, int]:
    if tool == TOOL_NAME:
        return got["incident_count"], 0
    return got["numerator"], got["denominator"]


def tool_group_row(tool: str, got: dict, key) -> tuple[int, int] | None:
    for g in got["groups"] or []:
        if (g["group_id"] if g["group_id"] is not None else g["group"]) == key:
            return (g["count"], 0) if tool == TOOL_NAME else (g["numerator"], g["denominator"])
    return None


def check_scalar(tool, got, expected):
    assert figure(tool, got) == expected
    if tool != TOOL_NAME:
        assert got["rate"] == rate(*expected, SCALE[tool])
        assert isinstance(got["rate"], str | None)


# --------------------------------------------------------------------------- region filter


@pytest.mark.parametrize(("start", "end"), RANGES, ids=lambda d: d.isoformat())
@pytest.mark.parametrize("region", REGIONS)
@pytest.mark.parametrize("tool", ALL_TOOLS)
async def test_a_region_filter_equals_its_group_row(
    loaded_database, connect_as: ConnectAs, settings, tool, region, start, end
):
    oracle = connect_as(ROLE_EVAL)
    got = await call(settings, tool, start, end, region=region)
    assert got["region"] == region and got["account_id"] is None and got["groups"] is None

    check_scalar(tool, got, raw_scalar(oracle, tool, start, end, region=region))
    # The invariant: the same as that region's row of the unfiltered breakdown.
    assert figure(tool, got) == raw_group_rows(oracle, tool, start, end, "region")[region]
    breakdown = await call(settings, tool, start, end, group_by="region")
    assert tool_group_row(tool, breakdown, region) == figure(tool, got)


# --------------------------------------------------------------------------- account filter


@pytest.fixture(scope="module")
def accounts(connect_as: ConnectAs, loaded_database) -> list[tuple[int, str]]:
    rows = connect_as(ROLE_EVAL).execute(
        "SELECT account_id, account_name FROM accounts ORDER BY account_id"
    )
    return [(int(i), n) for i, n in rows]


@pytest.mark.parametrize("tool", ALL_TOOLS)
async def test_an_account_filter_equals_its_group_row_for_every_account(
    loaded_database, connect_as: ConnectAs, settings, accounts, tool
):
    """All 50 accounts, July 2026: the filtered figure, the raw filtered SQL and the raw
    breakdown row agree, and the result names the account."""
    oracle = connect_as(ROLE_EVAL)
    rows = raw_group_rows(oracle, tool, *JULY, "account")
    seen = 0
    for account_id, name in accounts:
        got = await call(settings, tool, *JULY, account_id=account_id)
        assert got["account_id"] == account_id and got["account_name"] == name
        expected = raw_scalar(oracle, tool, *JULY, account=account_id)
        check_scalar(tool, got, expected)
        assert expected == rows.get(account_id, (0, 0))
        seen += 1
    assert seen == len(accounts) == 50


@pytest.mark.parametrize(("start", "end"), [ANOMALY, FULL], ids=lambda d: d.isoformat())
@pytest.mark.parametrize("tool", ALL_TOOLS)
async def test_account_filters_match_the_tool_breakdown_row_over_other_ranges(
    loaded_database, connect_as: ConnectAs, settings, accounts, tool, start, end
):
    oracle = connect_as(ROLE_EVAL)
    breakdown = await call(settings, tool, start, end, group_by="account")
    compared = 0
    for account_id, _ in accounts[:6]:
        got = await call(settings, tool, start, end, account_id=account_id)
        check_scalar(tool, got, raw_scalar(oracle, tool, start, end, account=account_id))
        row = tool_group_row(tool, breakdown, account_id)
        if row is not None:  # the breakdown keeps at most 25 groups
            assert row == figure(tool, got)
            compared += 1
    assert compared >= 1


# --------------------------------------------------------------------------- combinations


@pytest.mark.parametrize("region", REGIONS)
@pytest.mark.parametrize("tool", ALL_TOOLS)
async def test_region_and_account_together_are_an_and(
    loaded_database, connect_as: ConnectAs, settings, accounts, tool, region
):
    oracle = connect_as(ROLE_EVAL)
    for account_id, _ in accounts[:5]:
        got = await call(settings, tool, *JULY, region=region, account_id=account_id)
        assert got["region"] == region and got["account_id"] == account_id
        check_scalar(tool, got, raw_scalar(oracle, tool, *JULY, region=region, account=account_id))


@pytest.mark.parametrize("tool", ALL_TOOLS)
async def test_a_region_filter_with_an_account_breakdown_is_the_cross_tab(
    loaded_database, connect_as: ConnectAs, settings, tool
):
    """The West broken down by account: each account's row is that account's figure in the
    West, and equals the combined filter."""
    oracle = connect_as(ROLE_EVAL)
    got = await call(settings, tool, *JULY, region="west", group_by="account")
    assert got["region"] == "west" and got["group_by"] == "account" and got["groups"]
    for g in got["groups"][:8]:
        expected = raw_scalar(oracle, tool, *JULY, region="west", account=g["group_id"])
        row = (g["count"], 0) if tool == TOOL_NAME else (g["numerator"], g["denominator"])
        assert row == expected, g["group"]
    whole = raw_scalar(oracle, tool, *JULY, region="west")
    assert figure(tool, got) == whole  # the totals still cover every group


@pytest.mark.parametrize("tool", ALL_TOOLS)
async def test_an_account_filter_with_a_region_breakdown_is_the_cross_tab(
    loaded_database, connect_as: ConnectAs, settings, accounts, tool
):
    oracle = connect_as(ROLE_EVAL)
    account_id = accounts[0][0]
    got = await call(settings, tool, *FULL, account_id=account_id, group_by="region")
    assert got["account_id"] == account_id and got["groups"]
    for g in got["groups"]:
        expected = raw_scalar(oracle, tool, *FULL, region=g["group"], account=account_id)
        row = (g["count"], 0) if tool == TOOL_NAME else (g["numerator"], g["denominator"])
        assert row == expected, g["group"]


@pytest.mark.parametrize("tool", ALL_TOOLS)
async def test_a_technician_filter_and_a_region_filter_are_an_and(
    loaded_database, connect_as: ConnectAs, settings, tool
):
    oracle = connect_as(ROLE_EVAL)
    (technician_id,) = oracle.execute(
        """SELECT technician_id FROM archived_requests
           GROUP BY 1 ORDER BY count(*) DESC, 1 LIMIT 1"""
    ).fetchone()
    got = await call(settings, tool, *FULL, technician_id=technician_id, region="central")
    assert got["technician_id"] == technician_id and got["region"] == "central"
    check_scalar(
        tool,
        got,
        raw_scalar(oracle, tool, *FULL, region="central", technician=technician_id),
    )


# --------------------------------------------------------------------------- bad input


async def test_an_unknown_account_id_is_a_caller_error(loaded_database, settings):
    async with Client(create_server(settings)) as client:
        result = await client.call_tool(
            SLA_COMPLIANCE,
            {"start": "2026-07-01", "end": "2026-07-31", "account_id": 999999},
        )
    assert result.is_error and "no account has id" in result.content[0].text


async def test_find_account_matches_sql(loaded_database, connect_as: ConnectAs, settings, accounts):
    """Whole-word, case-insensitive matches over the fixed list, checked against SQL."""
    oracle = connect_as(ROLE_EVAL)
    async with Client(create_server(settings)) as client:
        for query in (
            "Bluewater",
            "bluewater hospitality",
            "LLC",
            "Inc.",
            "Inc",
            "Summit Distribution Co",
            "Zzyzx",
            "Blue",
        ):
            result = await client.call_tool("find_account", {"name": query})
            assert not result.is_error

            def words_of(text):  # §6: whitespace words, edge punctuation stripped (ruling 5)
                return [w.strip(".,'-") for w in text.casefold().split() if w.strip(".,'-")]

            words = words_of(query)
            expected = sorted(
                (
                    n
                    for _, n in oracle.execute("SELECT account_id, account_name FROM accounts")
                    if all(w in words_of(n) for w in words)
                ),
                key=str.casefold,
            )
            got = result.structured_content
            assert got["total_matches"] == len(expected)
            assert [m["account_name"] for m in got["matches"]] == expected[:5]
