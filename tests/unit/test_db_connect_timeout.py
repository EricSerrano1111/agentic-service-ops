"""Host-side scripts fail with a clear error, within the connect timeout, when the database
is unreachable, instead of hanging.

The "unreachable" database is a local socket that accepts TCP connections but never
answers, which is the failure mode that actually occurred: Postgres was published on
127.0.0.1 only, `localhost` resolved to `::1` first, and that connection was silently
dropped rather than refused. It needs no network and behaves the same in CI. The elapsed
time has a lower bound as well as an upper one, so the test proves the timeout fired,
rather than passing on an instant refusal.
"""

from __future__ import annotations

import socket
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from common import CONNECT_TIMEOUT_VAR, DEFAULT_CONNECT_TIMEOUT_S, connect_timeout_s

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data" / "generator"))
import load  # noqa: E402
import validate  # noqa: E402

TIMEOUT_S = 2


@pytest.fixture
def black_hole() -> Iterator[int]:
    """A port that accepts TCP but never speaks Postgres: every connect attempt waits."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(8)  # never accept(): the kernel completes the handshake, nobody replies
    try:
        yield sock.getsockname()[1]
    finally:
        sock.close()


@pytest.fixture
def unreachable_env(monkeypatch, black_hole) -> None:
    monkeypatch.setenv("POSTGRES_HOST", "127.0.0.1")
    monkeypatch.setenv("POSTGRES_PORT", str(black_hole))
    monkeypatch.setenv("POSTGRES_DB", "service_ops")
    for role in ("GENERATOR", "QA"):
        monkeypatch.setenv(f"DB_ROLE_{role}_USER", f"app_{role.lower()}")
        monkeypatch.setenv(f"DB_ROLE_{role}_PASSWORD", "unused")
    monkeypatch.setenv(CONNECT_TIMEOUT_VAR, str(TIMEOUT_S))


# --------------------------------------------------------------------------- the setting


def test_default_timeout(monkeypatch):
    monkeypatch.delenv(CONNECT_TIMEOUT_VAR, raising=False)
    assert connect_timeout_s() == DEFAULT_CONNECT_TIMEOUT_S == 10


def test_timeout_is_configurable(monkeypatch):
    monkeypatch.setenv(CONNECT_TIMEOUT_VAR, "25")
    assert connect_timeout_s() == 25


@pytest.mark.parametrize("bad", ["0", "-3", "2.5", "ten"])
def test_invalid_timeout_is_rejected(monkeypatch, bad):
    monkeypatch.setenv(CONNECT_TIMEOUT_VAR, bad)
    with pytest.raises(SystemExit, match=CONNECT_TIMEOUT_VAR):
        connect_timeout_s()


# --------------------------------------------------------------------------- load.py


def test_load_passes_the_timeout_to_psycopg(unreachable_env):
    assert load.connection_kwargs()["connect_timeout"] == TIMEOUT_S


def test_load_fails_within_the_timeout_on_an_unreachable_database(unreachable_env):
    began = time.monotonic()
    with pytest.raises(SystemExit, match=r"Cannot connect to Postgres at 127\.0\.0\.1:\d+"):
        load.connect(load.connection_kwargs())
    elapsed = time.monotonic() - began
    assert TIMEOUT_S * 0.75 <= elapsed < TIMEOUT_S + 3, elapsed


# --------------------------------------------------------------------------- validate.py


def test_validate_fails_within_the_timeout_on_an_unreachable_database(unreachable_env):
    began = time.monotonic()
    with pytest.raises(SystemExit, match="as app_qa"):
        validate._conn("DB_ROLE_QA_USER", "DB_ROLE_QA_PASSWORD")
    elapsed = time.monotonic() - began
    assert TIMEOUT_S * 0.75 <= elapsed < TIMEOUT_S + 3, elapsed
