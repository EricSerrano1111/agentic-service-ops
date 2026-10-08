"""The database host is configuration: TCP locally, the Cloud SQL socket on Cloud Run.

Both forms are selected by environment variables only; per-role credentials are unchanged.
"""

from __future__ import annotations

import pytest
from common import database_host
from mcp_feedback.config import Settings as FeedbackSettings
from mcp_feedback.store import make_engine as feedback_engine
from mcp_incidents.config import Settings as IncidentsSettings
from mcp_incidents.queries import make_engine as incidents_engine
from mcp_volume.config import Settings as VolumeSettings
from mcp_volume.store import make_engine as volume_engine

INSTANCE = "my-project:us-central1:ops-db"
FAKE_PASSWORD = "not-a-real-password"  # noqa: S105

_BASE = {"POSTGRES_DB": "service_ops", "POSTGRES_PORT": "5432"}
_ROLES = {
    "incidents": (
        IncidentsSettings,
        incidents_engine,
        {"DB_ROLE_REPORTING_USER": "app_reporting", "DB_ROLE_REPORTING_PASSWORD": FAKE_PASSWORD},
    ),
    "feedback": (
        FeedbackSettings,
        feedback_engine,
        {"DB_ROLE_SENTIMENT_USER": "app_sentiment", "DB_ROLE_SENTIMENT_PASSWORD": FAKE_PASSWORD},
    ),
    "volume": (
        VolumeSettings,
        volume_engine,
        {"DB_ROLE_FORECAST_USER": "app_forecast", "DB_ROLE_FORECAST_PASSWORD": FAKE_PASSWORD},
    ),
}


def _set_env(monkeypatch: pytest.MonkeyPatch, extra: dict[str, str]) -> None:
    for name in ("POSTGRES_HOST", "CLOUD_SQL_INSTANCE"):
        monkeypatch.delenv(name, raising=False)
    for name, value in {**_BASE, **extra}.items():
        monkeypatch.setenv(name, value)


def test_tcp_host_is_used_as_given():
    assert database_host({"POSTGRES_HOST": "postgres"}) == "postgres"


def test_cloud_sql_instance_becomes_the_socket_directory():
    assert database_host({"CLOUD_SQL_INSTANCE": INSTANCE}) == f"/cloudsql/{INSTANCE}"


def test_neither_variable_is_an_error():
    with pytest.raises(RuntimeError, match="must be set"):
        database_host({})


def test_both_variables_is_an_error():
    with pytest.raises(RuntimeError, match="not both"):
        database_host({"POSTGRES_HOST": "postgres", "CLOUD_SQL_INSTANCE": INSTANCE})


@pytest.mark.parametrize("which", _ROLES)
def test_tcp_url_form(monkeypatch, which):
    settings_cls, make_engine, creds = _ROLES[which]
    _set_env(monkeypatch, {"POSTGRES_HOST": "postgres", **creds})
    url = make_engine(settings_cls.from_env()).url
    assert (url.host, url.port, url.database) == ("postgres", 5432, "service_ops")
    assert url.password == FAKE_PASSWORD


@pytest.mark.parametrize("which", _ROLES)
def test_unix_socket_url_form(monkeypatch, which):
    settings_cls, make_engine, creds = _ROLES[which]
    _set_env(monkeypatch, {"CLOUD_SQL_INSTANCE": INSTANCE, **creds})
    url = make_engine(settings_cls.from_env()).url
    # libpq reads a host that starts with "/" as a socket directory and appends
    # `.s.PGSQL.<port>`, which is the file Cloud Run's mount provides.
    assert url.host == f"/cloudsql/{INSTANCE}"
    assert url.port == 5432
    # Credentials come from the same per-role variables in both forms.
    assert url.password == FAKE_PASSWORD
    assert url.username == creds[next(k for k in creds if k.endswith("_USER"))]
