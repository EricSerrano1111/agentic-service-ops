"""Database connection settings shared by the host-side scripts.

Alembic (`data/migrations/env.py`), `data/generator/load.py` and
`data/generator/validate.py` connect from the host. Without a connect timeout, an
unreachable database makes them hang instead of failing: libpq's default is to wait
indefinitely. The trigger seen on 2026-09-25 was Postgres published on 127.0.0.1 only,
while `localhost` resolved to `::1` first and that connection was silently dropped.
"""

from __future__ import annotations

import os

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
