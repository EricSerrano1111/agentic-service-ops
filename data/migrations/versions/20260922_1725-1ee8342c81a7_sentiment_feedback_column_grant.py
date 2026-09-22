"""Sentiment reads service_feedback by column; rating withheld

Replaces `app_sentiment`'s table-level SELECT on `service_feedback` with a column-level
grant on exactly `feedback_id`, `request_id`, `submitted_at` and `feedback_text`.
`rating` is the QA agent's independent cross-check on sentiment classification (R-04);
if the sentiment agent can read it, the check is no longer independent. See ADR-027,
which supersedes ADR-025 in this respect.

**Frozen.** Like every migration from here on (ADR-027), this carries its grant as
literal data rather than importing `db_models.access_matrix`. A later change to what the
sentiment role may read is a new migration, not an edit to this one. Drift between the
matrix and the database is caught by `tests/integration/test_access_matrix_grants.py`.

**Order matters.** Postgres keeps table and column GRANTs independent, but REVOKE on a
table also revokes that privilege on every one of its columns. So the table-level
REVOKE has to come first: the other way round would strip the column grant just
made and leave the role with no access at all. The upside is convergence — whatever
this role held on the table before (a table grant, stray column grants, or already the
target state), REVOKE-then-GRANT ends at exactly the four columns.

Revision ID: 1ee8342c81a7
Revises: 7d54e0c9a318
Create Date: 2026-09-22 17:25:29.598483+00:00

"""

from __future__ import annotations

import os
from collections.abc import Sequence

from alembic import op
from psycopg import sql

revision: str = "1ee8342c81a7"
down_revision: str | None = "7d54e0c9a318"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# --------------------------------------------------------------------------- #
# Frozen — do not edit. The grant this migration applies, as literal data.
# --------------------------------------------------------------------------- #

_ROLE_USER_VAR = "DB_ROLE_SENTIMENT_USER"
_TABLE = "service_feedback"
_COLUMNS: tuple[str, ...] = ("feedback_id", "request_id", "submitted_at", "feedback_text")


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


def _revoke_table_select(cur, role: sql.Identifier) -> None:
    # Also clears any column-level SELECT this role holds on the table.
    cur.execute(
        sql.SQL("REVOKE SELECT ON TABLE {table} FROM {role}").format(
            table=sql.Identifier(_TABLE), role=role
        )
    )


def upgrade() -> None:
    role = _role()
    cur = _cursor()

    _revoke_table_select(cur, role)
    cur.execute(
        sql.SQL("GRANT SELECT ({columns}) ON TABLE {table} TO {role}").format(
            columns=sql.SQL(", ").join(sql.Identifier(c) for c in _COLUMNS),
            table=sql.Identifier(_TABLE),
            role=role,
        )
    )


def downgrade() -> None:
    """Restore ADR-025's state: table-level SELECT on the whole of service_feedback."""
    role = _role()
    cur = _cursor()

    _revoke_table_select(cur, role)
    cur.execute(
        sql.SQL("GRANT SELECT ON TABLE {table} TO {role}").format(
            table=sql.Identifier(_TABLE), role=role
        )
    )
