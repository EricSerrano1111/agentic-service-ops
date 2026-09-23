"""Forecast reads service_requests by column; no other table

Replaces `app_forecast`'s table-level SELECT on `service_requests` with a column-level
grant on exactly `request_id`, `scheduled_datetime` and `service_type`, and revokes its
SELECT on `accounts`, `locations` and `archived_requests`. The forecast is univariate
(ADR-018): a weekly count by `scheduled_datetime`, optionally broken out by
`service_type`. Nothing else in those four tables, billing included, is needed. See
ADR-035.

**Frozen.** Like every migration from here on (ADR-027), this carries its grants as
literal data rather than importing `db_models.access_matrix`. A later change to what the
forecast role may read is a new migration, not an edit to this one. Drift between the
matrix and the database is caught by `tests/integration/test_access_matrix_grants.py`.

**Order matters.** REVOKE on a table also revokes that privilege on every one of its
columns, so the table-level REVOKE on `service_requests` has to come before the column
GRANT — see `1ee8342c81a7` for the same reasoning.

Revision ID: fae4b8c9814c
Revises: 1ee8342c81a7
Create Date: 2026-09-23 01:44:19.925420+00:00

"""

from __future__ import annotations

import os
from collections.abc import Sequence

from alembic import op
from psycopg import sql

revision: str = "fae4b8c9814c"
down_revision: str | None = "1ee8342c81a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# --------------------------------------------------------------------------- #
# Frozen — do not edit. The grants this migration applies, as literal data.
# --------------------------------------------------------------------------- #

_ROLE_USER_VAR = "DB_ROLE_FORECAST_USER"
_COLUMN_TABLE = "service_requests"
_COLUMNS: tuple[str, ...] = ("request_id", "scheduled_datetime", "service_type")
#: Tables whose table-level SELECT is revoked outright.
_REVOKED_TABLES: tuple[str, ...] = ("accounts", "locations", "archived_requests")
#: The roles-and-grants migration's original forecast grants, restored on downgrade.
_ORIGINAL_TABLES: tuple[str, ...] = (
    "accounts",
    "archived_requests",
    "locations",
    "service_requests",
)


def _role() -> sql.Identifier:
    name = (os.environ.get(_ROLE_USER_VAR) or "").strip()
    if not name:
        raise RuntimeError(
            f"{_ROLE_USER_VAR} is unset or empty. Set it in .env (see .env.example) or "
            "export it before running alembic. Nothing was changed."
        )
    return sql.Identifier(name)


def _cursor():
    """A raw psycopg cursor on Alembic's connection — see the roles_and_grants migration."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        raise RuntimeError(
            f"This migration is Postgres-specific; got dialect {bind.dialect.name!r}."
        )
    return bind.connection.driver_connection.cursor()


def _revoke_table_select(cur, role: sql.Identifier, tables: Sequence[str]) -> None:
    # Also clears any column-level SELECT this role holds on these tables.
    cur.execute(
        sql.SQL("REVOKE SELECT ON TABLE {tables} FROM {role}").format(
            tables=sql.SQL(", ").join(sql.Identifier(t) for t in tables), role=role
        )
    )


def upgrade() -> None:
    role = _role()
    cur = _cursor()

    _revoke_table_select(cur, role, (_COLUMN_TABLE, *_REVOKED_TABLES))
    cur.execute(
        sql.SQL("GRANT SELECT ({columns}) ON TABLE {table} TO {role}").format(
            columns=sql.SQL(", ").join(sql.Identifier(c) for c in _COLUMNS),
            table=sql.Identifier(_COLUMN_TABLE),
            role=role,
        )
    )


def downgrade() -> None:
    """Restore the roles-and-grants state: table-level SELECT on all four tables."""
    role = _role()
    cur = _cursor()

    # Clear the column grant first, so the restored state carries no leftover column ACL.
    _revoke_table_select(cur, role, (_COLUMN_TABLE,))
    cur.execute(
        sql.SQL("GRANT SELECT ON TABLE {tables} TO {role}").format(
            tables=sql.SQL(", ").join(sql.Identifier(t) for t in _ORIGINAL_TABLES),
            role=role,
        )
    )
