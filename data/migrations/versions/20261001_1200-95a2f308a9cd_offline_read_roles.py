"""Offline read roles app_eval and app_train; gold labels leave app_qa

Creates two read-only login roles used only by offline scripts on the developer machine,
never by a deployed service (ADR-063):

* `app_eval` — table-level SELECT on the ten tables `app_qa` held before this migration.
  Used by `data/generator/validate.py`, the eval harnesses and the Sprint 5
  rating-sensitivity check.
* `app_train` — SELECT on `sentiment_labels`, plus exactly the columns the runtime models
  read: `app_sentiment`'s four `service_feedback` columns and `app_forecast`'s three
  `service_requests` columns. No `rating`, no `generation_parameters`.

and revokes `app_qa`'s SELECT on `sentiment_labels` and `generation_parameters`, so the
runtime QA role never ships holding gold labels (ADR-055).

**Frozen.** Like every migration since ADR-027, this carries its roles and grants as
literal data rather than importing `db_models.access_matrix`. Drift between the matrix and
the database is caught by `tests/integration/test_access_matrix_grants.py`.

**Credentials.** Mirrors the roles-and-grants migration (`7d54e0c9a318`): names and
passwords come from `DB_ROLE_EVAL_*` and `DB_ROLE_TRAIN_*`, required and never defaulted
(ADR-028), and `app_qa`'s name from `DB_ROLE_QA_USER`. Every problem is collected and
reported in one error before the database is touched. An existing role converges: its
password and LOGIN attribute are reset to match the environment.

**PUBLIC.** The `PUBLIC` revokes are repeated here, as in `7d54e0c9a318`, so this
migration's least-privilege baseline does not depend on an earlier one having run them.
They are no-ops on a database at `ab53ceceeffe`. `downgrade()` therefore leaves `PUBLIC`
alone: restoring the Postgres defaults is `7d54e0c9a318`'s downgrade, not this one's.

**Downgrade** restores `app_qa`'s two grants, then revokes everything from and drops both
new roles, leaving the database as `ab53ceceeffe` left it. Roles are cluster-scoped: if
either role holds privileges in another database on the same server, `DROP ROLE` fails
and the downgrade rolls back. Run the downgrade in that database first.

Revision ID: 95a2f308a9cd
Revises: ab53ceceeffe
Create Date: 2026-10-01 12:00

"""

from __future__ import annotations

import os
from collections.abc import Sequence

from alembic import op
from psycopg import sql

revision: str = "95a2f308a9cd"
down_revision: str | None = "ab53ceceeffe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# --------------------------------------------------------------------------- #
# Frozen — do not edit. The roles and grants this migration applies, as literal data.
# --------------------------------------------------------------------------- #

#: Canonical role key → the environment variable pair carrying its name and password.
ROLE_ENV_VARS: dict[str, tuple[str, str]] = {
    "app_eval": ("DB_ROLE_EVAL_USER", "DB_ROLE_EVAL_PASSWORD"),
    "app_train": ("DB_ROLE_TRAIN_USER", "DB_ROLE_TRAIN_PASSWORD"),
}

NEW_ROLES: tuple[str, ...] = tuple(ROLE_ENV_VARS)

#: The existing runtime QA role, whose name is needed for the revoke.
_QA_USER_VAR = "DB_ROLE_QA_USER"

#: Role → tables granted table-level SELECT.
SELECT_GRANTS: dict[str, tuple[str, ...]] = {
    "app_eval": (
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
    "app_train": ("sentiment_labels",),
}

#: Role → table → columns granted column-level SELECT.
COLUMN_SELECT_GRANTS: dict[str, dict[str, tuple[str, ...]]] = {
    "app_train": {
        "service_feedback": ("feedback_id", "request_id", "submitted_at", "feedback_text"),
        "service_requests": ("request_id", "scheduled_datetime", "service_type"),
    },
}

#: Tables whose SELECT `app_qa` loses here, and regains on downgrade.
QA_REVOKED_TABLES: tuple[str, ...] = ("generation_parameters", "sentiment_labels")


class MissingRoleCredentials(RuntimeError):
    """Raised when role names or passwords cannot be read from the environment."""


def _resolve_credentials() -> tuple[dict[str, tuple[str, str]], str]:
    """Map each new role's canonical key to its (actual name, password), plus `app_qa`'s name.

    Every problem is collected before raising, so a fresh checkout gets one actionable
    error rather than several sequential ones.
    """
    resolved: dict[str, tuple[str, str]] = {}
    problems: list[str] = []

    for role_key in NEW_ROLES:
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

    qa_name = (os.environ.get(_QA_USER_VAR) or "").strip()
    if not qa_name:
        problems.append(f"{_QA_USER_VAR} is unset or empty")

    if problems:
        raise MissingRoleCredentials(
            "Cannot create the offline read roles. "
            + "; ".join(problems)
            + ". Set them in .env (see .env.example) or export them before running "
            "alembic. Nothing was changed."
        )

    return resolved, qa_name


def _cursor():
    """A raw psycopg cursor on Alembic's connection — see the roles_and_grants migration."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        raise RuntimeError(
            f"This migration is Postgres-specific; got dialect {bind.dialect.name!r}."
        )
    return bind.connection.driver_connection.cursor()


def _database_name() -> str:
    return os.environ["POSTGRES_DB"]


def _qa_table_select(cur, verb: str, qa_name: str) -> None:
    """GRANT ... TO or REVOKE ... FROM `app_qa` on the two gold tables."""
    template = (
        "GRANT SELECT ON TABLE {tables} TO {role}"
        if verb == "grant"
        else "REVOKE SELECT ON TABLE {tables} FROM {role}"
    )
    cur.execute(
        sql.SQL(template).format(
            tables=sql.SQL(", ").join(sql.Identifier(t) for t in QA_REVOKED_TABLES),
            role=sql.Identifier(qa_name),
        )
    )


def upgrade() -> None:
    credentials, qa_name = _resolve_credentials()
    database = sql.Identifier(_database_name())
    cur = _cursor()

    # Roles: create, or converge an existing one.
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

    # Baseline, as in 7d54e0c9a318: close the PUBLIC defaults before opening anything.
    cur.execute(sql.SQL("REVOKE CONNECT ON DATABASE {db} FROM PUBLIC").format(db=database))
    cur.execute(sql.SQL("REVOKE ALL ON SCHEMA public FROM PUBLIC"))

    for role_name, _ in credentials.values():
        role = sql.Identifier(role_name)
        cur.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {db} TO {role}").format(db=database, role=role)
        )
        cur.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {role}").format(role=role))

    # Table-level SELECT.
    for role_key, tables in SELECT_GRANTS.items():
        role = sql.Identifier(credentials[role_key][0])
        for table in sorted(tables):
            cur.execute(
                sql.SQL("GRANT SELECT ON TABLE {table} TO {role}").format(
                    table=sql.Identifier(table), role=role
                )
            )

    # Column-level SELECT: training reads exactly what the runtime models read.
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

    # Gold labels and generator parameters leave the runtime QA role (ADR-055).
    _qa_table_select(cur, "revoke", qa_name)


def downgrade() -> None:
    """Restore `ab53ceceeffe`: `app_qa` regains both grants, both new roles are dropped."""
    credentials, qa_name = _resolve_credentials()
    database = sql.Identifier(_database_name())
    cur = _cursor()

    _qa_table_select(cur, "grant", qa_name)

    for role_name, _ in credentials.values():
        role = sql.Identifier(role_name)
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role_name,))
        if cur.fetchone() is None:
            continue

        # DROP OWNED BY revokes every privilege the role holds in this database (it owns
        # no objects); database-level privileges are cluster-shared and revoked separately.
        cur.execute(sql.SQL("DROP OWNED BY {role}").format(role=role))
        cur.execute(
            sql.SQL("REVOKE ALL ON DATABASE {db} FROM {role}").format(db=database, role=role)
        )
        cur.execute(sql.SQL("DROP ROLE {role}").format(role=role))
