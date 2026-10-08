"""Every service image runs as a non-root user and carries no secrets."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILES = sorted((ROOT / "services").glob("*/Dockerfile"))
SECRET_NAME = re.compile(r"(?i)(password|passwd|secret|token|api_?key|credential)")


def test_every_service_has_a_dockerfile():
    names = {p.parent.name for p in DOCKERFILES}
    assert {"orchestrator", "agent_reporting", "mcp_incidents"} <= names


@pytest.mark.parametrize("path", DOCKERFILES, ids=lambda p: p.parent.name)
def test_final_stage_runs_as_a_non_root_user(path):
    lines = [ln.strip() for ln in path.read_text().splitlines()]
    final_from = max(i for i, ln in enumerate(lines) if ln.startswith("FROM "))
    users = [ln.split()[1] for ln in lines[final_from:] if ln.startswith("USER ")]
    assert users and users[-1] not in {"root", "0"}, f"{path.parent.name} may run as root"


@pytest.mark.parametrize("path", DOCKERFILES, ids=lambda p: p.parent.name)
def test_no_credentials_are_baked_into_the_image(path):
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith(("ENV ", "ARG ")):
            assert not SECRET_NAME.search(stripped), f"{path.parent.name}: {stripped}"
        assert not re.search(r"COPY\s+.*\.env", stripped), f"{path.parent.name}: {stripped}"


def test_dockerignore_is_an_allowlist_that_keeps_env_files_out():
    lines = (ROOT / ".dockerignore").read_text().splitlines()
    rules = [ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")]
    assert rules[0] == "*", "the context must start from nothing"
    for secret in ("**/.env", "**/.env.*", "**/*.pem", "**/*.key"):
        assert secret in rules
    assert ".env" not in [r.lstrip("!") for r in rules if r.startswith("!")]
