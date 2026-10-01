"""sentiment_predictions, and region access for app_sentiment (ADR-067)

Creates `sentiment_predictions`: the deployed sentiment model's stored output, one row
per comment per model version, keyed on (`feedback_id`, `model_version`). The foreign
key to `service_feedback` cascades on delete; a regeneration clears the table in the
same TRUNCATE as `service_feedback` (`data/generator/load.py`).

Grants:

* `app_sentiment` — SELECT and INSERT on `sentiment_predictions` (no UPDATE, no DELETE:
  `ON CONFLICT DO NOTHING` needs neither), plus column SELECT on `service_requests`
  (`request_id`, `location_id`) and `locations` (`location_id`, `region`), so it can
  resolve a comment's region and nothing else about the site or account.
* `app_qa` and `app_eval` — SELECT on `sentiment_predictions`.
* `app_generator` — ALL on `sentiment_predictions` (its TRUNCATE during a reload).
* Nothing for `app_reporting`, `app_forecast` or `app_train`: the model never trains on
  its own output.

`app_sentiment` held no table-level grant on `service_requests` or `locations` before
this migration, so there is no table-level revoke to order the column grants after
(ADR-027's rule); the column grants run last regardless.

**Frozen.** Table definition, vocabulary and grants are literal data (ADR-027). Grants
are plain SQL quoted by psycopg without a connection, so `alembic upgrade --sql` renders
this migration like the schema migrations before it.

**Credentials.** Role names come from `DB_ROLE_*_USER`, required and never defaulted
(ADR-028); every missing name is reported in one error before anything runs.

**Downgrade** revokes the two column grants and drops the table, which takes its grants
with it, leaving the database exactly as `95a2f308a9cd` left it.

Revision ID: 3d7e1a9c5b20
Revises: 95a2f308a9cd
Create Date: 2026-10-01 22:45

"""

from __future__ import annotations

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from psycopg import sql

revision: str = "3d7e1a9c5b20"
down_revision: str | None = "95a2f308a9cd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# --------------------------------------------------------------------------- #
# Frozen — do not edit. What this migration applies, as literal data.
# --------------------------------------------------------------------------- #

_TABLE = "sentiment_predictions"
_LABELS: tuple[str, ...] = ("positive", "neutral", "negative", "mixed")

#: Canonical role key → the environment variable carrying its actual name.
_ROLE_USER_VARS: dict[str, str] = {
    "app_sentiment": "DB_ROLE_SENTIMENT_USER",
    "app_qa": "DB_ROLE_QA_USER",
    "app_eval": "DB_ROLE_EVAL_USER",
    "app_generator": "DB_ROLE_GENERATOR_USER",
}

#: Role → privileges on `sentiment_predictions`.
TABLE_GRANTS: dict[str, str] = {
    "app_sentiment": "SELECT, INSERT",
    "app_qa": "SELECT",
    "app_eval": "SELECT",
    "app_generator": "ALL",
}

#: Role → table → columns granted column-level SELECT.
COLUMN_SELECT_GRANTS: dict[str, dict[str, tuple[str, ...]]] = {
    "app_sentiment": {
        "service_requests": ("request_id", "location_id"),
        "locations": ("location_id", "region"),
    },
}


class MissingRoleNames(RuntimeError):
    """Raised when role names cannot be read from the environment."""


def _role_names() -> dict[str, str]:
    names = {key: (os.environ.get(var) or "").strip() for key, var in _ROLE_USER_VARS.items()}
    missing = [_ROLE_USER_VARS[key] for key, name in names.items() if not name]
    if missing:
        raise MissingRoleNames(
            f"Cannot grant on {_TABLE}: {', '.join(missing)} unset or empty. Set them in "
            ".env (see .env.example) or export them before running alembic. Nothing was "
            "changed."
        )
    return names


def _execute(statement: sql.Composable) -> None:
    op.execute(statement.as_string())


def _column_grant(verb: str, role: str, table: str, columns: tuple[str, ...]) -> sql.Composable:
    template = (
        "GRANT SELECT ({columns}) ON TABLE {table} TO {role}"
        if verb == "grant"
        else "REVOKE SELECT ({columns}) ON TABLE {table} FROM {role}"
    )
    return sql.SQL(template).format(
        columns=sql.SQL(", ").join(sql.Identifier(c) for c in columns),
        table=sql.Identifier(table),
        role=sql.Identifier(role),
    )


def upgrade() -> None:
    names = _role_names()
    op.create_table(
        _TABLE,
        sa.Column("feedback_id", sa.BigInteger(), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("predicted_label", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("flagged", sa.Boolean(), nullable=False),
        sa.Column(
            "scored_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "predicted_label IN (" + ", ".join(f"'{v}'" for v in _LABELS) + ")",
            name="ck_sentiment_predictions_predicted_label",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_sentiment_predictions_confidence_range",
        ),
        sa.ForeignKeyConstraint(
            ["feedback_id"],
            ["service_feedback.feedback_id"],
            name="fk_sentiment_predictions_feedback_id_service_feedback",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("feedback_id", "model_version", name="pk_sentiment_predictions"),
    )

    for role_key, privileges in TABLE_GRANTS.items():
        _execute(
            sql.SQL("GRANT {privileges} ON TABLE {table} TO {role}").format(
                privileges=sql.SQL(privileges),
                table=sql.Identifier(_TABLE),
                role=sql.Identifier(names[role_key]),
            )
        )

    for role_key, table_columns in COLUMN_SELECT_GRANTS.items():
        for table, columns in table_columns.items():
            _execute(_column_grant("grant", names[role_key], table, columns))


def downgrade() -> None:
    """Restore `95a2f308a9cd`: column grants revoked, table (and its grants) dropped."""
    names = _role_names()
    for role_key, table_columns in COLUMN_SELECT_GRANTS.items():
        for table, columns in table_columns.items():
            _execute(_column_grant("revoke", names[role_key], table, columns))
    op.drop_table(_TABLE)
