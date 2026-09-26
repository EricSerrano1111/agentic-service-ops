"""Container isolation, checked on the running docker-compose stack. No model calls.

Local only: skipped unless `RUN_E2E=1`, with the stack up:

    docker compose up -d --build
    $env:RUN_E2E=1; .venv\\Scripts\\python -m pytest tests/e2e -q -rs

The running agent containers hold no database variables, and the MCP container holds no
model key. tests/unit/test_compose_isolation.py checks the same from the compose config;
this checks what the containers actually received. The full question-to-answer path,
which calls Gemini, is in test_checkpoint_e2e.py.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(os.environ.get("RUN_E2E") != "1", reason="set RUN_E2E=1 with compose up"),
]


def container_env(service: str) -> list[str]:
    container = subprocess.run(
        ["docker", "compose", "ps", "-q", service],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout.strip()
    assert container, f"{service} is not running"
    return json.loads(
        subprocess.run(
            ["docker", "inspect", "--format", "{{json .Config.Env}}", container],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )


def _names(env: list[str], prefixes: tuple[str, ...]) -> list[str]:
    return [kv.split("=", 1)[0] for kv in env if kv.startswith(prefixes)]


@pytest.mark.parametrize("service", ["agent_reporting", "orchestrator"])
def test_running_agent_containers_hold_no_database_variables(service):
    assert _names(container_env(service), ("POSTGRES_", "DB_ROLE_")) == []


def test_running_mcp_container_holds_no_model_key():
    assert _names(container_env("mcp_incidents"), ("GOOGLE_", "GEMINI_", "LLM_")) == []


@pytest.mark.parametrize("service", ["agent_reporting", "orchestrator"])
def test_running_agent_containers_never_get_the_paid_key(service):
    env = container_env(service)
    assert _names(env, ("GOOGLE_AI_API_KEY_PAID",)) == []
    assert "LLM_MODE=free" in env
