"""No deployed service can hold the offline read roles' credentials (ADR-063).

`app_eval` reads the gold labels and the generator's parameters; `app_train` reads the
labels. Both are for scripts on the developer machine. If either credential reached a
service, the runtime would hold gold labels again, which is what ADR-055 and ADR-063
remove from `app_qa`.

A plain text scan, deliberately: any mention of `DB_ROLE_EVAL_*` or `DB_ROLE_TRAIN_*` in a
compose file, a Dockerfile or anything under `services/` fails, whether it would be
interpolated, copied into an image or read by code. Compose has no `env_file` (asserted by
`test_compose_isolation.py`), so a service can't receive these variables without naming
them.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from db_models.access_matrix import OFFLINE_READ_ROLES, ROLE_ENV_VARS

REPO_ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "pgdata"}

OFFLINE_VARS = tuple(var for role in OFFLINE_READ_ROLES for var in ROLE_ENV_VARS[role])
FORBIDDEN = re.compile(r"DB_ROLE_(EVAL|TRAIN)_")


def _walk(root: Path):
    for path in root.iterdir():
        if path.name in SKIP_DIRS:
            continue
        if path.is_dir():
            yield from _walk(path)
        elif path.is_file():
            yield path


def _deployed_files() -> list[Path]:
    everything = list(_walk(REPO_ROOT))
    compose = [p for p in everything if re.fullmatch(r"(docker-)?compose.*\.ya?ml", p.name)]
    dockerfiles = [p for p in everything if p.name.startswith("Dockerfile")]
    services = [p for p in _walk(REPO_ROOT / "services") if p.suffix != ".pyc"]
    return sorted(set(compose) | set(dockerfiles) | set(services))


def test_pattern_covers_every_offline_variable() -> None:
    """The scan's pattern matches each offline role's variables, and nothing runtime."""
    assert OFFLINE_VARS
    assert all(FORBIDDEN.match(var) for var in OFFLINE_VARS)
    runtime = [v for r, pair in ROLE_ENV_VARS.items() if r not in OFFLINE_READ_ROLES for v in pair]
    assert not [var for var in runtime if FORBIDDEN.match(var)]


def test_scan_is_not_vacuous() -> None:
    files = _deployed_files()
    names = {p.name for p in files}
    assert "docker-compose.yml" in names
    assert "Dockerfile" in names
    assert any(p.suffix == ".py" for p in files)


def _id(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


@pytest.mark.parametrize("path", _deployed_files(), ids=_id)
def test_no_deployed_file_references_offline_role_credentials(path: Path) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    hits = sorted({m.group(0) for m in FORBIDDEN.finditer(text)})
    assert hits == [], f"{path.relative_to(REPO_ROOT)} references {hits} (ADR-063)"
