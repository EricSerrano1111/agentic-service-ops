"""Credential resolution in the roles-and-grants migration.

The migration runs as the database admin and creates login roles, so the cost of it
guessing at a missing value is high: a silently wrong role name produces grants on a
role nothing connects as, and the failure surfaces later as an opaque "permission
denied" from an agent. Every variable is therefore required, and every problem is
reported at once.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from db_models.access_matrix import ALL_ROLES, ROLE_ENV_VARS

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_migration() -> ModuleType:
    """Import the migration by path.

    Alembic revision filenames start with a timestamp, so they are not importable
    as modules by name.
    """
    (path,) = (REPO_ROOT / "data" / "migrations" / "versions").glob("*_roles_and_grants.py")
    spec = importlib.util.spec_from_file_location("roles_and_grants", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration = _load_migration()


@pytest.fixture
def valid_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """A complete, valid set of role credentials."""
    for role in ALL_ROLES:
        user_var, password_var = ROLE_ENV_VARS[role]
        monkeypatch.setenv(user_var, role)
        monkeypatch.setenv(password_var, f"pw-for-{role}")


def test_resolves_when_every_variable_is_set(valid_env: None) -> None:
    resolved = migration._resolve_credentials()

    assert set(resolved) == set(ALL_ROLES)
    for role in ALL_ROLES:
        name, password = resolved[role]
        assert name == role
        assert password == f"pw-for-{role}"


def test_role_name_comes_from_the_environment(
    valid_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Role names are configurable, not hardcoded."""
    user_var, _ = ROLE_ENV_VARS["app_reporting"]
    monkeypatch.setenv(user_var, "reporting_svc")

    assert migration._resolve_credentials()["app_reporting"][0] == "reporting_svc"


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_username_fails_even_when_the_password_is_set(
    valid_env: None, monkeypatch: pytest.MonkeyPatch, blank: str
) -> None:
    """A missing role name is as fatal as a missing password.

    It previously fell back to the canonical `app_*` name. That is the wrong
    default for a migration running as admin: it would create and grant to a role
    the deployment never connects as, and the mistake would only surface later as
    an agent's "permission denied".
    """
    user_var, password_var = ROLE_ENV_VARS["app_sentiment"]
    monkeypatch.setenv(user_var, blank)

    with pytest.raises(migration.MissingRoleCredentials) as excinfo:
        migration._resolve_credentials()

    message = str(excinfo.value)
    assert f"{user_var} is unset or empty" in message
    # The password was fine, so it must not be blamed as well.
    assert password_var not in message


def test_missing_password_still_fails(valid_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _, password_var = ROLE_ENV_VARS["app_qa"]
    monkeypatch.setenv(password_var, "")

    with pytest.raises(migration.MissingRoleCredentials, match=password_var):
        migration._resolve_credentials()


def test_password_with_a_newline_is_rejected(
    valid_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, password_var = ROLE_ENV_VARS["app_forecast"]
    monkeypatch.setenv(password_var, "line-one\nline-two")

    with pytest.raises(migration.MissingRoleCredentials, match="NUL or newline"):
        migration._resolve_credentials()


def test_every_problem_is_reported_at_once(
    valid_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One actionable error on a fresh checkout, not five sequential ones."""
    reporting_user, _ = ROLE_ENV_VARS["app_reporting"]
    _, generator_password = ROLE_ENV_VARS["app_generator"]
    monkeypatch.setenv(reporting_user, "")
    monkeypatch.setenv(generator_password, "")

    with pytest.raises(migration.MissingRoleCredentials) as excinfo:
        migration._resolve_credentials()

    message = str(excinfo.value)
    assert reporting_user in message
    assert generator_password in message
