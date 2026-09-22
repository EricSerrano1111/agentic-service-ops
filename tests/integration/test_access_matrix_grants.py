"""The live database enforces the §7 access matrix.

`tests/unit/test_access_matrix.py` proves the matrix *says* the right thing. This
proves the database *does* it: after `alembic upgrade head`, each role is logged in
with its own `.env` credentials and every table and column is probed.

Every expectation is computed from `db_models.access_matrix` — nothing below
restates a grant by hand — so the matrix, the migration that applies it, and this
test cannot drift apart. The named tests further down spotlight the §7 properties
worth reading on their own; the parametrized sweeps are what make the coverage
exhaustive.

Probes use `LIMIT 0`: Postgres checks privileges when the executor starts, before any
row is read, so an empty or unseeded database gives the same answers as a full one.
"""

from __future__ import annotations

import os
from collections.abc import Callable

import db_models as m
import psycopg
import pytest
from db_models import access_matrix as am
from psycopg import sql

pytestmark = pytest.mark.integration

ConnectAs = Callable[[str], psycopg.Connection]

# The generator is an offline script, not an agent; §7 point 3 is about agents.
AGENT_ROLES = tuple(role for role in am.ALL_ROLES if role != am.ROLE_GENERATOR)


# --------------------------------------------------------------------------- #
# Expectations, derived from the matrix
# --------------------------------------------------------------------------- #


def _all_columns(table: str) -> tuple[str, ...]:
    return tuple(m.metadata.tables[table].columns.keys())


def _has_full_select(role: str, table: str) -> bool:
    return table in am.SELECT_GRANTS.get(role, frozenset()) | am.ALL_GRANTS.get(role, frozenset())


def _readable_columns(role: str, table: str) -> frozenset[str]:
    if _has_full_select(role, table):
        return frozenset(_all_columns(table))
    return frozenset(am.COLUMN_SELECT_GRANTS.get(role, {}).get(table, ()))


_COLUMN_SCOPED_TABLES = sorted(
    {table for grants in am.COLUMN_SELECT_GRANTS.values() for table in grants}
)

_ROLE_TABLE_CASES = [
    pytest.param(role, table, id=f"{role}-{table}")
    for role in am.ALL_ROLES
    for table in am.ALL_TABLES
]

_ROLE_COLUMN_CASES = [
    pytest.param(role, table, column, id=f"{role}-{table}.{column}")
    for role in am.ALL_ROLES
    for table in _COLUMN_SCOPED_TABLES
    for column in _all_columns(table)
]


# --------------------------------------------------------------------------- #
# Probes
# --------------------------------------------------------------------------- #


def _select(conn: psycopg.Connection, table: str, columns: sql.Composable) -> None:
    conn.execute(
        sql.SQL("SELECT {columns} FROM {table} LIMIT 0").format(
            columns=columns, table=sql.Identifier(table)
        )
    )


def _assert_allowed(conn: psycopg.Connection, table: str, columns: sql.Composable) -> None:
    _select(conn, table, columns)  # any exception fails the test with its own message


def _assert_denied(conn: psycopg.Connection, table: str, columns: sql.Composable) -> None:
    # InsufficientPrivilege specifically (SQLSTATE 42501). A missing table or a typo'd
    # column raises something else, and must not pass as "correctly denied".
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _select(conn, table, columns)


def _column(name: str) -> sql.Composable:
    return sql.Identifier(name)


_EVERY_COLUMN = sql.SQL("*")
# Needs SELECT on at least one column of the table, so it fails only when the role has
# no read access to the table in any form — the strictest "not granted" probe.
_ANY_COLUMN = sql.SQL("count(*)")


# --------------------------------------------------------------------------- #
# Exhaustive sweeps
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("role", am.ALL_ROLES)
def test_role_logs_in_under_its_configured_name(connect_as: ConnectAs, role: str) -> None:
    """Guards the sweeps below against probing as the wrong identity."""
    user_var, _ = am.ROLE_ENV_VARS[role]
    (current_user,) = connect_as(role).execute("SELECT current_user").fetchone()
    assert current_user == os.environ[user_var]


@pytest.mark.parametrize(("role", "table"), _ROLE_TABLE_CASES)
def test_table_level_select_matches_matrix(connect_as: ConnectAs, role: str, table: str) -> None:
    conn = connect_as(role)

    if _has_full_select(role, table):
        _assert_allowed(conn, table, _EVERY_COLUMN)
    elif table in am.tables_readable_by(role):
        # Column-scoped: some columns only, so SELECT * must be refused.
        # Which columns is the column sweep's job.
        _assert_denied(conn, table, _EVERY_COLUMN)
    else:
        _assert_denied(conn, table, _ANY_COLUMN)


@pytest.mark.parametrize(("role", "table", "column"), _ROLE_COLUMN_CASES)
def test_column_level_select_matches_matrix(
    connect_as: ConnectAs, role: str, table: str, column: str
) -> None:
    """Every column of every column-scoped table, for every role."""
    conn = connect_as(role)

    if column in _readable_columns(role, table):
        _assert_allowed(conn, table, _column(column))
    else:
        _assert_denied(conn, table, _column(column))


# --------------------------------------------------------------------------- #
# §7 properties, named
# --------------------------------------------------------------------------- #


def test_reporting_reads_feedback_aggregates_but_not_feedback_text(
    connect_as: ConnectAs,
) -> None:
    """§7 footnote 1 / ADR-025: "SELECT (aggregate)" is a column grant minus the text."""
    conn = connect_as(am.ROLE_REPORTING)
    granted = am.COLUMN_SELECT_GRANTS[am.ROLE_REPORTING]["service_feedback"]

    _assert_allowed(conn, "service_feedback", sql.SQL(", ").join(map(_column, granted)))
    _assert_denied(conn, "service_feedback", _column("feedback_text"))


def test_sentiment_reads_feedback_text(connect_as: ConnectAs) -> None:
    """feedback_text is the sentiment agent's entire input."""
    _assert_allowed(connect_as(am.ROLE_SENTIMENT), "service_feedback", _column("feedback_text"))


@pytest.mark.parametrize("table", sorted(am.PII_RESTRICTED_TABLES))
@pytest.mark.parametrize("role", AGENT_ROLES)
def test_no_agent_role_reads_pii(connect_as: ConnectAs, role: str, table: str) -> None:
    """§7 point 3: customer PII never enters an LLM context window."""
    _assert_denied(connect_as(role), table, _ANY_COLUMN)
