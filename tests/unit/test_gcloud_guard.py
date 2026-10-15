"""The root conftest.py guard: a test session cannot reach the real gcloud config."""

from __future__ import annotations

import os
from pathlib import Path


def _real_default_gcloud_config() -> Path:
    appdata = os.environ.get("APPDATA")
    if os.name == "nt" and appdata:
        return Path(appdata) / "gcloud"
    return Path.home() / ".config" / "gcloud"


def test_cloudsdk_config_is_an_empty_folder_that_is_not_the_real_one():
    folder = Path(os.environ["CLOUDSDK_CONFIG"])
    assert folder.is_dir()
    assert list(folder.iterdir()) == []
    assert folder.resolve() != _real_default_gcloud_config().resolve()
    assert folder.resolve() not in _real_default_gcloud_config().resolve().parents
    assert Path(__file__).resolve().parents[2] not in folder.resolve().parents  # outside the repo


def test_credential_and_project_variables_are_unset():
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ
    assert "CLOUDSDK_CORE_PROJECT" not in os.environ
