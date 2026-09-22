"""Least-privilege agent roles and the §7 access-matrix grants

Creates the five per-agent Postgres login roles and applies exactly the privileges in
`docs/data-dictionary.md` §7. This is Layer 2 of the defence-in-depth model in
ADR-023: the forecast agent is *unable* to read the feedback table at the database
permission level, not merely disinclined by convention.

**Frozen.** The role and privilege sets below are a literal snapshot of
`db_models.access_matrix` as it stood when this migration was written (2026-09-20),
including `app_sentiment`'s table-level SELECT on `service_feedback`. This migration
originally imported the live matrix, which meant its effect silently changed whenever
the matrix did: a fresh database no longer reproduced history, and a table added by a
later migration would have broken a fresh `upgrade head` here. It was frozen in place on
2026-09-22 (ADR-027). That edit was safe only because this migration had been applied to
nothing but the local development database, and freezing preserves its original effect
exactly. Every later grant change is its own migration — the first is the sentiment
column-level tightening that follows this one.

After Sprint 5, once this has run against Cloud SQL, editing an applied migration is no
longer acceptable under any circumstances: fix forward with a new migration.

**Credentials.** Role names come from `DB_ROLE_*_USER` and passwords from
`DB_ROLE_*_PASSWORD` (see `.env.example`). Nothing is hardcoded and no password is
logged or written into this file. `upgrade()` validates every variable up front and
aborts before touching the database if any is missing.

**Why not a plain .sql script.** Keeping this as a migration means one
`alembic upgrade head` produces a fully provisioned environment, the teardown path is
written and tested, and the same code runs against local Docker Postgres and Cloud
SQL (ADR-007). A script would need psql, which the deployment path does not have.

**Idempotence.** Re-running converges rather than failing: an existing role has its
password and LOGIN attribute reset to match the environment. Postgres roles are
cluster-scoped and outlive a dropped database, so convergence is the behaviour that
avoids a confusing "password authentication failed" after a database rebuild.

**Two things that deliberately do not appear here:**

* No sequence grants. `GENERATED ALWAYS AS IDENTITY` columns derive their sequence
  permission from the table privilege, unlike `serial`. Granting on the implicit
  sequences would be noise.
* No `ALTER DEFAULT PRIVILEGES`. A table added later should require an explicit,
  reviewed grant rather than silently inheriting one — that is the whole point of
  maintaining the matrix.

Revision ID: 7d54e0c9a318
Revises: 0f3c81a47b21
Create Date: 2026-09-20 12:15:00.000000+00:00

"""

from __future__ import annotations

import os
from collections.abc import Sequence

from alembic import op
from psycopg import sql

revision: str = "7d54e0c9a318"
down_revision: str | None = "0f3c81a47b21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# --------------------------------------------------------------------------- #
# Frozen snapshot of the §7 access matrix as of 2026-09-20 — do not edit.
# --------------------------------------------------------------------------- #

#: Canonical role key → the environment variable pair carrying its name and password.
ROLE_ENV_VARS: dict[str, tuple[str, str]] = {
    "app_reporting": ("DB_ROLE_REPORTING_USER", "DB_ROLE_REPORTING_PASSWORD"),
    "app_sentiment": ("DB_ROLE_SENTIMENT_USER", "DB_ROLE_SENTIMENT_PASSWORD"),
    "app_forecast": ("DB_ROLE_FORECAST_USER", "DB_ROLE_FORECAST_PASSWORD"),
    "app_qa": ("DB_ROLE_QA_USER", "DB_ROLE_QA_PASSWORD"),
    "app_generator": ("DB_ROLE_GENERATOR_USER", "DB_ROLE_GENERATOR_PASSWORD"),
}

ALL_ROLES: tuple[str, ...] = tuple(ROLE_ENV_VARS)

#: Role → tables granted table-level SELECT.
SELECT_GRANTS: dict[str, tuple[str, ...]] = {
    "app_reporting": (
        "accounts",
        "archived_requests",
        "incidents",
        "locations",
        "service_requests",
        "technician_skills",
        "technicians",
    ),
    "app_sentiment": ("service_feedback",),
    "app_forecast": (
        "accounts",
        "archived_requests",
        "locations",
        "service_requests",
    ),
    "app_qa": (
        "accounts",
        "archived_requests",
        "generation_parameters",
        "incidents",
        "locations",
        "sentiment_labels",
        "service_feedback",
        "service_requests",
        "technician_skills",
        "technicians",
    ),
    "app_generator": (),
}

#: Role → table → columns granted column-level SELECT.
COLUMN_SELECT_GRANTS: dict[str, dict[str, tuple[str, ...]]] = {
    "app_reporting": {
        "service_feedback": (
            "feedback_id",
            "request_id",
            "incident_id",
            "submitted_by_contact_id",
            "submitted_at",
            "rating",
            "response_channel",
            "created_at",
        ),
    },
}

#: Role → tables granted ALL PRIVILEGES.
ALL_GRANTS: dict[str, tuple[str, ...]] = {
    "app_generator": (
        "accounts",
        "archived_requests",
        "contacts",
        "generation_parameters",
        "incidents",
        "internal_users",
        "locations",
        "sentiment_labels",
        "service_feedback",
        "service_requests",
        "technician_skills",
        "technicians",
    ),
}


class MissingRoleCredentials(RuntimeError):
    """Raised when role names or passwords cannot be read from the environment."""


def _resolve_credentials() -> dict[str, tuple[str, str]]:
    """Map the matrix's canonical role key to its (actual name, password).

    Every problem is collected before raising, so a fresh checkout gets one
    actionable error rather than five sequential ones.
    """
    resolved: dict[str, tuple[str, str]] = {}
    problems: list[str] = []

    for role_key in ALL_ROLES:
        user_var, password_var = ROLE_ENV_VARS[role_key]
        name = (os.environ.get(user_var) or "").strip()
        password = os.environ.get(password_var) or ""

        if not name:
            problems.append(f"{user_var} is unset or empty")
        if not password:
            problems.append(f"{password_var} is unset or empty")
        elif "\x00" in password or "\n" in password or "\r" in password:
            # psycopg would quote these safely, but Postgres rejects NUL outright
            # and an embedded newline is almost always a copy-paste accident.
            problems.append(f"{password_var} contains a NUL or newline character")

        resolved[role_key] = (name, password)

    if problems:
        raise MissingRoleCredentials(
            "Cannot create database roles. "
            + "; ".join(problems)
            + ". Set them in .env (see .env.example) or export them before running "
            "alembic. Nothing was changed."
        )

    return resolved


def _cursor():
    """A raw psycopg cursor on Alembic's connection.

    Role DDL cannot use bind parameters, so passwords have to be interpolated into
    the statement text. Going through psycopg's own `sql.Literal` / `sql.Identifier`
    composition means the quoting is the driver's, not hand-rolled string
    formatting. The cursor shares Alembic's connection and therefore its
    transaction.
    """
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        raise RuntimeError(
            f"This migration is Postgres-specific; got dialect {bind.dialect.name!r}."
        )
    return bind.connection.driver_connection.cursor()


def _database_name() -> str:
    return os.environ["POSTGRES_DB"]


def upgrade() -> None:
    credentials = _resolve_credentials()
    database = _database_name()
    cur = _cursor()

    # ----------------------------------------------------------------- #
    # Roles
    # ----------------------------------------------------------------- #
    for role_name, password in credentials.values():
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role_name,))
        exists = cur.fetchone() is not None

        verb = sql.SQL("ALTER ROLE") if exists else sql.SQL("CREATE ROLE")
        cur.execute(
            sql.SQL("{verb} {role} WITH LOGIN PASSWORD {password}").format(
                verb=verb,
                role=sql.Identifier(role_name),
                password=sql.Literal(password),
            )
        )

    # ----------------------------------------------------------------- #
    # Baseline: close the defaults before opening anything
    #
    # Not specified in §7, but without it "least privilege" is only partly true:
    # PUBLIC can connect to the database by default, and on Postgres < 15 any role
    # can also create objects in schema public.
    # ----------------------------------------------------------------- #
    cur.execute(
        sql.SQL("REVOKE CONNECT ON DATABASE {db} FROM PUBLIC").format(db=sql.Identifier(database))
    )
    cur.execute(sql.SQL("REVOKE ALL ON SCHEMA public FROM PUBLIC"))

    for role_name, _ in credentials.values():
        role = sql.Identifier(role_name)
        cur.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {db} TO {role}").format(
                db=sql.Identifier(database), role=role
            )
        )
        cur.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {role}").format(role=role))

    # ----------------------------------------------------------------- #
    # §7 table privileges
    # ----------------------------------------------------------------- #
    for role_key, tables in SELECT_GRANTS.items():
        role = sql.Identifier(credentials[role_key][0])
        for table in sorted(tables):
            cur.execute(
                sql.SQL("GRANT SELECT ON TABLE {table} TO {role}").format(
                    table=sql.Identifier(table), role=role
                )
            )

    # §7's "SELECT (aggregate)" on service_feedback for the reporting role. Postgres
    # has no aggregate-only privilege, so it is honoured as a column-level grant that
    # omits `feedback_text`: reporting can count and average ratings and is
    # structurally unable to read a customer's raw words.
    for role_key, table_columns in COLUMN_SELECT_GRANTS.items():
        role = sql.Identifier(credentials[role_key][0])
        for table, columns in table_columns.items():
            cur.execute(
                sql.SQL("GRANT SELECT ({columns}) ON TABLE {table} TO {role}").format(
                    columns=sql.SQL(", ").join(sql.Identifier(c) for c in columns),
                    table=sql.Identifier(table),
                    role=role,
                )
            )

    for role_key, tables in ALL_GRANTS.items():
        role = sql.Identifier(credentials[role_key][0])
        for table in sorted(tables):
            cur.execute(
                sql.SQL("GRANT ALL PRIVILEGES ON TABLE {table} TO {role}").format(
                    table=sql.Identifier(table), role=role
                )
            )


def downgrade() -> None:
    credentials = _resolve_credentials()
    database = sql.Identifier(_database_name())
    cur = _cursor()

    for role_name, _ in credentials.values():
        role = sql.Identifier(role_name)
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role_name,))
        if cur.fetchone() is None:
            continue

        # DROP OWNED BY revokes every privilege the role holds in this database (it
        # owns no objects), which is what otherwise blocks DROP ROLE. Database-level
        # privileges are cluster-shared and have to be revoked separately.
        cur.execute(sql.SQL("DROP OWNED BY {role}").format(role=role))
        cur.execute(
            sql.SQL("REVOKE ALL ON DATABASE {db} FROM {role}").format(db=database, role=role)
        )
        cur.execute(sql.SQL("DROP ROLE {role}").format(role=role))

    # Restore the Postgres 15/16 defaults this migration revoked.
    cur.execute(sql.SQL("GRANT CONNECT ON DATABASE {db} TO PUBLIC").format(db=database))
    cur.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO PUBLIC"))
