"""Declarative base, constraint naming convention, and shared column mixins.

Conventions here implement `docs/data-dictionary.md` §6 ("Storage conventions").
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import TIMESTAMP, BigInteger, Identity, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Deterministic constraint names. Without this, SQLAlchemy emits anonymous names for
# indexes, unique constraints and foreign keys, Postgres invents its own, and every
# subsequent `alembic revision --autogenerate` produces churn it cannot reverse.
#
# There is deliberately no "ck" entry. The usual template,
# `ck_%(table_name)s_%(constraint_name)s`, is a known Alembic footgun: `op.create_table`
# inherits this convention from `target_metadata` and re-applies it to names that are
# already resolved, yielding `ck_accounts_ck_accounts_account_status`. CHECK
# constraints therefore carry their full name at the definition site — see
# :func:`db_models.enums.check_in` — which also makes the migration files readable
# without knowing the convention.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata_obj = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    """Declarative base for every table in the service-ops schema."""

    metadata = metadata_obj


def surrogate_pk() -> Mapped[int]:
    """BIGINT GENERATED ALWAYS AS IDENTITY primary key.

    §6 / ADR-015: a single-writer generator makes UUIDs pure overhead, and
    `reservation_number` already carries the human-facing identity.
    """
    return mapped_column(BigInteger, Identity(always=True), primary_key=True)


def tz_timestamp(*, nullable: bool = False, server_now: bool = False) -> Mapped[dt.datetime]:
    """TIMESTAMPTZ column, stored UTC.

    §6 forbids naive TIMESTAMP outright: a multi-region field-service dataset with
    naive timestamps produces wrong SLA math and wrong hour-of-day seasonality. Two
    columns in the dictionary tables are written as bare `TIMESTAMP`
    (`service_requests.scheduled_datetime`, `archived_requests.completed_at`); §6
    governs, and those are TIMESTAMPTZ here.
    """
    return mapped_column(
        TIMESTAMP(timezone=True),
        nullable=nullable,
        server_default=func.now() if server_now else None,
    )


class TimestampMixin:
    """`created_at` / `updated_at` audit columns.

    Server defaults keep the DDL self-sufficient; the synthetic data generator
    writes explicit backdated values, which override them.
    """

    created_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
