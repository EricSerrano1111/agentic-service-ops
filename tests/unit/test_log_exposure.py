"""Secrets never reach a log line: database URL passwords and Authorization headers.

The Authorization/token side of the orchestrator is covered in its own tests; this file
covers the shared formatter's redaction and the database edge.
"""

from __future__ import annotations

import logging

import pytest
from common import JsonFormatter, redact_secrets
from fastapi.testclient import TestClient
from mcp_incidents.config import Settings
from mcp_incidents.queries import check_connection, make_engine
from mcp_incidents.server import Backend, create_app

FAKE_PASSWORD = "hunter2-fake-pw"  # noqa: S105


@pytest.mark.parametrize(
    ("raw", "forbidden"),
    [
        ("sending Authorization: Bearer abc.def.ghi to host", "abc.def.ghi"),
        ("headers={'authorization': 'Bearer abc.def.ghi', 'host': 'x'}", "abc.def.ghi"),
        ('{"authorization": "Basic dXNlcjpwdw=="}', "dXNlcjpwdw"),
        (
            "connect failed for postgresql+psycopg://app_x:hunter2-fake-pw@db:5432/ops",
            FAKE_PASSWORD,
        ),
        ("postgres://u:p%40ss@h/db", "p%40ss"),
    ],
)
def test_redact_secrets_masks_tokens_headers_and_url_passwords(raw, forbidden):
    cleaned = redact_secrets(raw)
    assert forbidden not in cleaned and "[REDACTED]" in cleaned


def test_redaction_leaves_ordinary_text_alone():
    line = "ask answered outcome=answered route=reporting at http://agent_reporting:8001/"
    assert redact_secrets(line) == line


def test_formatter_masks_a_secret_in_a_message_an_extra_field_and_an_exception():
    record = logging.LogRecord(
        "x", logging.ERROR, "f", 1, "url postgresql://u:%s@h/d", (FAKE_PASSWORD,), None
    )
    record.header = "Authorization: Bearer tok.en.value"
    try:
        raise RuntimeError("see postgresql://u:" + FAKE_PASSWORD + "@h/d")
    except RuntimeError:
        import sys

        record.exc_info = sys.exc_info()
    out = JsonFormatter("svc").format(record)
    assert FAKE_PASSWORD not in out and "tok.en.value" not in out


def _everything_logged():
    records: list[logging.LogRecord] = []

    class Collect(logging.Handler):
        def emit(self, record):
            records.append(record)

    return records, Collect()


def test_database_password_is_never_logged_at_any_level_when_the_database_is_down():
    settings = Settings(
        db_host="127.0.0.1",
        db_port=1,  # nothing listens here: the connection is refused
        db_name="ops",
        db_user="app_reporting",
        db_password=FAKE_PASSWORD,
        connect_timeout_s=1,
    )
    records, handler = _everything_logged()
    root = logging.getLogger()
    before = root.level
    root.addHandler(handler)
    root.setLevel(1)
    names = list(logging.root.manager.loggerDict)
    saved = {n: logging.getLogger(n).level for n in names}
    for n in names:
        logging.getLogger(n).setLevel(1)
    try:
        engine = make_engine(settings)
        backend = Backend(
            incidents=None,  # type: ignore[arg-type]
            incident_rate=None,  # type: ignore[arg-type]
            sla_compliance=None,  # type: ignore[arg-type]
            first_time_fix_rate=None,  # type: ignore[arg-type]
            find_technician=None,  # type: ignore[arg-type]
            find_account=None,  # type: ignore[arg-type]
            repeat_drivers=None,  # type: ignore[arg-type]
            ready=lambda: check_connection(engine),
        )
        with TestClient(create_app(settings, backend)) as client:
            response = client.get("/readyz", headers={"host": "localhost:8101"})
        with pytest.raises(Exception):  # noqa: B017, PT011
            check_connection(engine)
    finally:
        root.removeHandler(handler)
        root.setLevel(before)
        for n, level in saved.items():
            logging.getLogger(n).setLevel(level)

    assert response.status_code == 503
    assert any("readiness" in r.getMessage() for r in records)
    formatter = JsonFormatter("mcp_incidents")
    emitted = "\n".join(formatter.format(r) for r in records)
    raw = "\n".join(r.getMessage() for r in records)
    assert FAKE_PASSWORD not in emitted
    assert FAKE_PASSWORD not in raw  # nothing in the code path even tried to log it
    assert FAKE_PASSWORD not in repr(settings) and FAKE_PASSWORD not in repr(engine)
    assert FAKE_PASSWORD not in response.text
