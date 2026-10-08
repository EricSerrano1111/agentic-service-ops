"""Database connection settings shared by the host-side scripts.

Alembic (`data/migrations/env.py`), `data/generator/load.py` and
`data/generator/validate.py` connect from the host. Without a connect timeout, an
unreachable database makes them hang instead of failing: libpq's default is to wait
indefinitely. The trigger seen on 2026-09-25 was Postgres published on 127.0.0.1 only,
while `localhost` resolved to `::1` first and that connection was silently dropped.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

CONNECT_TIMEOUT_VAR = "POSTGRES_CONNECT_TIMEOUT_S"
DEFAULT_CONNECT_TIMEOUT_S = 10


def connect_timeout_s() -> int:
    """Seconds to wait for a connection, from `POSTGRES_CONNECT_TIMEOUT_S` (default 10).

    An integer, because libpq's `connect_timeout` is whole seconds. With several
    addresses for one host name (IPv6 and IPv4 for `localhost`), each attempt gets
    the full timeout.
    """
    raw = os.environ.get(CONNECT_TIMEOUT_VAR, "").strip()
    if not raw:
        return DEFAULT_CONNECT_TIMEOUT_S
    try:
        value = int(raw)
    except ValueError:
        raise SystemExit(
            f"{CONNECT_TIMEOUT_VAR} must be a whole number of seconds, got {raw!r}"
        ) from None
    if value < 1:
        raise SystemExit(f"{CONNECT_TIMEOUT_VAR} must be at least 1, got {value}")
    return value


HOST_VAR = "POSTGRES_HOST"
CLOUD_SQL_INSTANCE_VAR = "CLOUD_SQL_INSTANCE"
#: Where Cloud Run mounts a Cloud SQL instance: `/cloudsql/<instance-connection-name>`
#: is a directory holding the Unix socket `.s.PGSQL.5432`.
CLOUD_SQL_SOCKET_DIR = "/cloudsql"


def database_host(env: Mapping[str, str] | None = None) -> str:
    """The `host` for a Postgres connection, selected by environment variables only.

    `POSTGRES_HOST` is a TCP host name (compose, the host-side scripts). With
    `CLOUD_SQL_INSTANCE` set to an instance connection name (`project:region:instance`)
    the host is instead the Cloud SQL socket directory, which libpq treats as a Unix
    socket because it begins with a slash; the port still names the socket file.
    Setting both is an error, so a stray `.env` value cannot silently win in the cloud.
    """
    env = os.environ if env is None else env
    host = env.get(HOST_VAR, "").strip()
    instance = env.get(CLOUD_SQL_INSTANCE_VAR, "").strip()
    if host and instance:
        raise RuntimeError(f"set {HOST_VAR} or {CLOUD_SQL_INSTANCE_VAR}, not both")
    if instance:
        return f"{CLOUD_SQL_SOCKET_DIR}/{instance}"
    if host:
        return host
    raise RuntimeError(f"{HOST_VAR} (or {CLOUD_SQL_INSTANCE_VAR} on Cloud Run) must be set")
