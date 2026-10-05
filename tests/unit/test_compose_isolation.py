"""The compose config gives database and model credentials only where they belong.

Asserted from `docker compose config`, the resolved configuration Docker actually runs
(anchors, merges and env_file expanded), rather than from the YAML text. Run with
`--no-interpolate`, so no `.env` is needed and CI checks the same thing a laptop does.

- The reporting agent and orchestrator get no `POSTGRES_*` or `DB_ROLE_*` at all: they
  reach data only through MCP, so a compromised agent has no credentials to misuse.
- `mcp_incidents` gets `app_reporting`'s credentials and nothing else: no admin
  password, no other role (ADR-023).
- Only the orchestrator and the two agents get the Gemini key (they make LLM
  calls), and only the free one, with `LLM_MODE` pinned to free. `mcp_incidents` gets
  no model key or setting: it holds database credentials, so it must not also hold a
  key (ADR-048).
- `mcp_feedback` gets `app_sentiment`'s credentials and nothing else, no model key,
  and the models folder read-only (ADR-067).
- Only the orchestrator publishes a host port among the application services.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PREFIXES = ("POSTGRES_", "DB_ROLE_")
NO_DB_SERVICES = ("agent_reporting", "agent_sentiment", "agent_forecast", "orchestrator")
APP_SERVICES = (
    "mcp_incidents",
    "mcp_feedback",
    "mcp_volume",
    "agent_reporting",
    "agent_sentiment",
    "agent_forecast",
    "orchestrator",
)
LLM_SERVICES = ("agent_reporting", "agent_sentiment", "agent_forecast", "orchestrator")
LLM_PREFIXES = ("GOOGLE_", "GEMINI_", "LLM_", "ANTHROPIC_")


@pytest.fixture(scope="module")
def compose() -> dict:
    if shutil.which("docker") is None:
        if os.environ.get("CI"):
            pytest.fail("docker is required in CI for the compose isolation test")
        pytest.skip("docker not installed")
    result = subprocess.run(
        ["docker", "compose", "config", "--no-interpolate", "--format", "json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)["services"]


def _env(service: dict) -> dict:
    return service.get("environment") or {}


def test_all_skeleton_services_are_defined(compose):
    assert set(APP_SERVICES) <= set(compose)


@pytest.mark.parametrize("name", NO_DB_SERVICES)
def test_agents_hold_no_database_variables(compose, name):
    service = compose[name]
    leaked = [key for key in _env(service) if key.startswith(DB_PREFIXES)]
    assert leaked == [], f"{name} must not see database variables: {leaked}"
    assert "env_file" not in service, f"{name} must not load an env_file"


def test_mcp_incidents_holds_only_app_reporting_credentials(compose):
    service = compose["mcp_incidents"]
    assert "env_file" not in service
    db_vars = {key for key in _env(service) if key.startswith(DB_PREFIXES)}
    assert db_vars == {
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_DB",
        "DB_ROLE_REPORTING_USER",
        "DB_ROLE_REPORTING_PASSWORD",
    }


def test_no_secret_literals_in_compose(compose):
    """Every credential is interpolated from .env, never written into the file."""
    for name, service in compose.items():
        for key, value in _env(service).items():
            if "PASSWORD" in key or key.endswith(("_USER", "_KEY", "_KEY_PAID")):
                assert str(value).startswith("${"), f"{name}.{key} is a literal"


def test_only_orchestrator_publishes_a_port(compose):
    published = {name for name in APP_SERVICES if compose[name].get("ports")}
    assert published == {"orchestrator"}


def _bind_address(port) -> str:
    """The host address a published port binds to. With `--no-interpolate`, a port whose
    mapping holds a `${...}` variable stays a string; the others come back as mappings."""
    if isinstance(port, dict):
        return port.get("host_ip", "0.0.0.0")
    # `${VAR:-default}` holds a colon of its own: collapse it before splitting.
    parts = re.sub(r"\$\{[^}]*\}", "VAR", str(port)).split(":")
    return parts[0] if len(parts) == 3 else "0.0.0.0"


def test_every_published_port_binds_loopback_only(compose):
    """/ask is unauthenticated and spends the model quota, and Postgres holds dev
    passwords, so nothing is published on every host interface (security-model.md)."""
    published = [
        (name, _bind_address(port))
        for name, service in compose.items()
        for port in service.get("ports") or []
    ]
    assert {n for n, _ in published} == {"orchestrator", "postgres"}
    assert [(n, a) for n, a in published if a != "127.0.0.1"] == []


def test_bind_address_reads_both_port_forms():
    assert _bind_address("8000:8000") == "0.0.0.0"
    assert _bind_address("127.0.0.1:${PORT:-8000}:8000") == "127.0.0.1"
    assert (
        _bind_address({"host_ip": "127.0.0.1", "published": "5432", "target": 5432}) == "127.0.0.1"
    )
    assert _bind_address({"published": "5432", "target": 5432}) == "0.0.0.0"


def test_mcp_incidents_holds_no_model_key_or_setting(compose):
    leaked = [k for k in _env(compose["mcp_incidents"]) if k.startswith(LLM_PREFIXES)]
    assert leaked == []


@pytest.mark.parametrize("name", LLM_SERVICES)
def test_llm_callers_get_only_the_free_key(compose, name):
    env = _env(compose[name])
    assert "GOOGLE_AI_API_KEY" in env
    assert "GOOGLE_AI_API_KEY_PAID" not in env
    assert env.get("LLM_MODE") == "free"


def test_no_service_gets_the_paid_key(compose):
    assert not [n for n, svc in compose.items() if "GOOGLE_AI_API_KEY_PAID" in _env(svc)]


def test_mcp_feedback_holds_only_app_sentiment_credentials(compose):
    service = compose["mcp_feedback"]
    assert "env_file" not in service
    db_vars = {key for key in _env(service) if key.startswith(DB_PREFIXES)}
    assert db_vars == {
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_DB",
        "DB_ROLE_SENTIMENT_USER",
        "DB_ROLE_SENTIMENT_PASSWORD",
    }


def test_mcp_feedback_holds_no_model_key_or_setting(compose):
    leaked = [k for k in _env(compose["mcp_feedback"]) if k.startswith(LLM_PREFIXES)]
    assert leaked == []


def test_mcp_feedback_mounts_models_read_only_at_the_proxy_limits(compose):
    service = compose["mcp_feedback"]
    (mount,) = service["volumes"]
    assert (mount["target"], mount.get("read_only")) == ("/models", True)
    assert float(service["cpus"]) == 1.0
    assert str(service["mem_limit"]) in ("2g", "2147483648")


def test_mcp_volume_holds_only_app_forecast_credentials_and_no_model_key(compose):
    service = compose["mcp_volume"]
    assert "env_file" not in service
    db_vars = {key for key in _env(service) if key.startswith(DB_PREFIXES)}
    assert db_vars == {
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_DB",
        "DB_ROLE_FORECAST_USER",
        "DB_ROLE_FORECAST_PASSWORD",
    }
    assert [k for k in _env(service) if k.startswith(LLM_PREFIXES)] == []


def test_mcp_volume_mounts_only_the_forecast_models_read_only(compose):
    (mount,) = compose["mcp_volume"]["volumes"]
    assert (mount["target"], mount.get("read_only")) == ("/models/forecast", True)
