"""Repo-wide test guard: no test can reach the developer's real gcloud state.

A Z2a test touched IAM on 2026-10-14. For the whole session, `CLOUDSDK_CONFIG` points at a
fresh empty folder (gcloud finds no account, project or application-default credentials in it)
and the two variables that name a credential or a project are unset. Done in `pytest_configure`,
before collection, so imports and subprocesses started at collection time see it too.
"""

from __future__ import annotations

import os
import shutil
import tempfile

_GUARDED_UNSET = ("GOOGLE_APPLICATION_CREDENTIALS", "CLOUDSDK_CORE_PROJECT")
_saved: dict[str, str | None] = {}
_folder: str | None = None


def pytest_configure(config) -> None:
    global _folder
    if _folder is not None:  # configured already (nested pytest in one process)
        return
    for name in ("CLOUDSDK_CONFIG", *_GUARDED_UNSET):
        _saved[name] = os.environ.get(name)
    _folder = tempfile.mkdtemp(prefix="empty-gcloud-config-")
    os.environ["CLOUDSDK_CONFIG"] = _folder
    for name in _GUARDED_UNSET:
        os.environ.pop(name, None)


def pytest_unconfigure(config) -> None:
    global _folder
    if _folder is None:
        return
    for name, value in _saved.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
    shutil.rmtree(_folder, ignore_errors=True)
    _saved.clear()
    _folder = None
