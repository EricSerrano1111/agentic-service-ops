"""Alembic environment.

The admin connection string is assembled from environment variables and never
hardcoded, so the same migrations run unchanged against local Docker Postgres and
Cloud SQL (ADR-007). In deployment those variables come from GCP Secret Manager; in
development they come from the gitignored `.env`.

Autogenerate targets `db_models.Base.metadata` — the SQLAlchemy models are the single
source of truth for the schema, and `alembic check` is what asserts the committed
migrations still match them.
"""

from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path
from urllib.parse import quote_plus

import db_models
from alembic import context
from common import connect_timeout_s
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

REPO_ROOT = Path(__file__).resolve().parents[2]

# `override=False`: real environment variables (CI, Cloud Run, Secret Manager) win
# over the local file. The file is a development convenience, not the authority.
load_dotenv(REPO_ROOT / ".env", override=False)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = db_models.Base.metadata

REQUIRED_VARS = (
    "POSTGRES_ADMIN_USER",
    "POSTGRES_ADMIN_PASSWORD",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DB",
)


class MissingDatabaseConfig(RuntimeError):
    """Raised when the admin connection cannot be assembled from the environment."""


def build_admin_url() -> str:
    """Build the admin connection URL from the environment.

    Reports every missing variable at once rather than failing on the first, so a
    fresh checkout gets one actionable error instead of five sequential ones.
    """
    missing = [name for name in REQUIRED_VARS if not os.environ.get(name)]
    if missing:
        raise MissingDatabaseConfig(
            "Cannot build the database URL. Missing or empty environment "
            f"variable(s): {', '.join(missing)}. Copy .env.example to .env and fill "
            "them in, or export them before running alembic."
        )

    user = quote_plus(os.environ["POSTGRES_ADMIN_USER"])
    # Passwords routinely contain @ : / # ? — percent-encode or the URL silently
    # parses into the wrong host.
    password = quote_plus(os.environ["POSTGRES_ADMIN_PASSWORD"])
    host = os.environ["POSTGRES_HOST"]
    port = os.environ["POSTGRES_PORT"]
    database = os.environ["POSTGRES_DB"]

    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{database}"


# Shared between offline and online so `alembic check` compares the same way the
# migrations were generated.
COMPARE_OPTIONS = {
    "compare_type": True,
    "compare_server_default": True,
    "include_schemas": False,
}


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting — `alembic upgrade head --sql`.

    Note that 0002 (roles and grants) cannot run offline: it needs a live psycopg
    connection to quote role passwords safely. That is deliberate — rendering
    passwords into a SQL script would defeat the point.
    """
    context.configure(
        url=build_admin_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **COMPARE_OPTIONS,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect and run migrations against a live database."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = build_admin_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        # Fail, don't hang, when the database is unreachable (POSTGRES_CONNECT_TIMEOUT_S).
        connect_args={"connect_timeout": connect_timeout_s()},
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            **COMPARE_OPTIONS,
        )

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
