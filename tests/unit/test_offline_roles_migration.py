"""Credential resolution in the offline-read-roles migration (ADR-063).

Same rules as the roles-and-grants migration (`test_roles_migration.py`, ADR-028): every
name and password is required, never defaulted, and every problem is reported at once.
This migration also needs `app_qa`'s name, for the revoke, and reports it with the rest.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_migration() -> ModuleType:
    """Import the migration by path (revision filenames start with a timestamp)."""
    (path,) = (REPO_ROOT / "data" / "migrations" / "versions").glob("*_offline_read_roles.py")
    spec = importlib.util.spec_from_file_location("offline_read_roles", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration = _load_migration()
NEW_ROLES = migration.NEW_ROLES
ROLE_ENV_VARS = migration.ROLE_ENV_VARS
QA_USER_VAR = "DB_ROLE_QA_USER"
ALL_VARS = (*(v for role in NEW_ROLES for v in ROLE_ENV_VARS[role]), QA_USER_VAR)


@pytest.fixture
def valid_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for role in NEW_ROLES:
        user_var, password_var = ROLE_ENV_VARS[role]
        monkeypatch.setenv(user_var, role)
        monkeypatch.setenv(password_var, f"pw-for-{role}")
    monkeypatch.setenv(QA_USER_VAR, "app_qa")


def test_creates_exactly_the_two_offline_roles() -> None:
    assert ROLE_ENV_VARS == {
        "app_eval": ("DB_ROLE_EVAL_USER", "DB_ROLE_EVAL_PASSWORD"),
        "app_train": ("DB_ROLE_TRAIN_USER", "DB_ROLE_TRAIN_PASSWORD"),
    }


def test_resolves_when_every_variable_is_set(valid_env: None) -> None:
    resolved, qa_name = migration._resolve_credentials()

    assert set(resolved) == set(NEW_ROLES)
    for role in NEW_ROLES:
        assert resolved[role] == (role, f"pw-for-{role}")
    assert qa_name == "app_qa"


def test_role_names_come_from_the_environment(
    valid_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DB_ROLE_EVAL_USER", "eval_svc")
    monkeypatch.setenv(QA_USER_VAR, "qa_svc")

    resolved, qa_name = migration._resolve_credentials()
    assert resolved["app_eval"][0] == "eval_svc"
    assert qa_name == "qa_svc"


USER_VARS = tuple(v for v in ALL_VARS if v.endswith("_USER"))
PASSWORD_VARS = tuple(v for v in ALL_VARS if v.endswith("_PASSWORD"))


def _assert_only_blamed(var: str) -> None:
    with pytest.raises(migration.MissingRoleCredentials) as excinfo:
        migration._resolve_credentials()
    message = str(excinfo.value)
    assert f"{var} is unset or empty" in message
    assert [other for other in ALL_VARS if other != var and other in message] == []


@pytest.mark.parametrize("var", USER_VARS)
@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_role_name_fails(
    valid_env: None, monkeypatch: pytest.MonkeyPatch, var: str, blank: str
) -> None:
    """A blank name fails like a blank password (ADR-028); nothing else is blamed."""
    monkeypatch.setenv(var, blank)
    _assert_only_blamed(var)


@pytest.mark.parametrize("var", PASSWORD_VARS)
def test_empty_password_fails(valid_env: None, monkeypatch: pytest.MonkeyPatch, var: str) -> None:
    monkeypatch.setenv(var, "")
    _assert_only_blamed(var)


@pytest.mark.parametrize("var", ALL_VARS)
def test_each_variable_fails_when_unset(
    valid_env: None, monkeypatch: pytest.MonkeyPatch, var: str
) -> None:
    monkeypatch.delenv(var)

    with pytest.raises(migration.MissingRoleCredentials, match=f"{var} is unset or empty"):
        migration._resolve_credentials()


@pytest.mark.parametrize("bad", ["line-one\nline-two", "carriage\rreturn", "nul\x00byte"])
@pytest.mark.parametrize("role", ["app_eval", "app_train"])
def test_password_with_a_nul_or_newline_is_rejected(
    valid_env: None, monkeypatch: pytest.MonkeyPatch, role: str, bad: str
) -> None:
    _, password_var = ROLE_ENV_VARS[role]
    if "\x00" in bad:
        # The OS refuses NUL in environment values; patch the lookup instead.
        real_get = migration.os.environ.get
        monkeypatch.setattr(
            migration.os.environ,
            "get",
            lambda key, default=None: bad if key == password_var else real_get(key, default),
        )
    else:
        monkeypatch.setenv(password_var, bad)

    with pytest.raises(migration.MissingRoleCredentials, match="NUL or newline"):
        migration._resolve_credentials()


def test_every_problem_is_reported_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """One actionable error on a fresh checkout, not five sequential ones."""
    for var in ALL_VARS:
        monkeypatch.delenv(var, raising=False)

    with pytest.raises(migration.MissingRoleCredentials) as excinfo:
        migration._resolve_credentials()

    message = str(excinfo.value)
    for var in ALL_VARS:
        assert f"{var} is unset or empty" in message
    assert "Nothing was changed" in message
