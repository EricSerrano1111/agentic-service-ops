"""Live-database fixtures for the integration suite.

Everything here connects to a real Postgres, so the whole directory skips cleanly
when none is reachable — `tests/unit` stays runnable offline, and a bare `pytest`
from the repo root reports these as skipped rather than failed.

The skip is deliberately narrow. Only "no server to talk to" (missing admin config,
or the admin connection failing) skips. Once the server is up, a role that cannot
log in is a real failure: it means the roles migration and `.env` disagree, which is
exactly what these tests exist to catch.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from pathlib import Path

import psycopg
import pytest
from db_models.access_matrix import ROLE_ENV_VARS
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]

# Same precedence as data/migrations/env.py: real environment variables win.
load_dotenv(REPO_ROOT / ".env", override=False)

_ADMIN_VARS = (
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "POSTGRES_ADMIN_USER",
    "POSTGRES_ADMIN_PASSWORD",
)

# Short enough that an offline run skips in seconds rather than hanging.
_CONNECT_TIMEOUT_S = 3


def _connect(user: str, password: str) -> psycopg.Connection:
    # Keyword arguments rather than a URL, so passwords need no percent-encoding.
    # Autocommit: an expected permission error must not abort the transaction the
    # next assertion runs in.
    return psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        dbname=os.environ["POSTGRES_DB"],
        user=user,
        password=password,
        connect_timeout=_CONNECT_TIMEOUT_S,
        autocommit=True,
    )


@pytest.fixture(scope="session")
def live_database() -> None:
    """Skip the dependent test unless a migrated database is reachable."""
    missing = [name for name in _ADMIN_VARS if not os.environ.get(name)]
    if missing:
        pytest.skip(f"no database configured (missing {', '.join(missing)})")

    try:
        with _connect(
            os.environ["POSTGRES_ADMIN_USER"], os.environ["POSTGRES_ADMIN_PASSWORD"]
        ) as conn:
            migrated = conn.execute("SELECT to_regclass('public.alembic_version')").fetchone()
    except psycopg.OperationalError as exc:
        pytest.skip(f"no database reachable: {exc}".splitlines()[0])

    if migrated is None or migrated[0] is None:
        pytest.skip("database reachable but not migrated — run `alembic upgrade head`")


@pytest.fixture(scope="session")
def connect_as(live_database: None) -> Iterator[Callable[[str], psycopg.Connection]]:
    """Return a function giving a connection logged in as a canonical role key.

    The actual login name and password come from the role's `DB_ROLE_*` pair, the same
    variables the roles migration created it from. One connection per role, reused
    across the session.
    """
    connections: dict[str, psycopg.Connection] = {}

    def _get(role: str) -> psycopg.Connection:
        if role not in connections:
            user_var, password_var = ROLE_ENV_VARS[role]
            user, password = os.environ.get(user_var), os.environ.get(password_var)
            if not user or not password:
                pytest.fail(f"{user_var} / {password_var} must be set to test {role}")
            connections[role] = _connect(user, password)
        return connections[role]

    yield _get

    for conn in connections.values():
        conn.close()
