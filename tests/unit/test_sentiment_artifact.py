"""Artifact files come from the manifest, and every one is hash-checked (ADR-066).

Assembled: a hand-built two-file artifact, no model.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from ml.sentiment import config, export  # noqa: E402


def _artifact(tmp_path: Path) -> dict:
    files = {"model.safetensors": b"weights", "tokenizer.json": b"{}"}
    for name, content in files.items():
        (tmp_path / name).write_bytes(content)
    return {"files": {n: hashlib.sha256(c).hexdigest() for n, c in files.items()}}


def test_matching_files_verify(tmp_path: Path) -> None:
    export.verify_files(tmp_path, _artifact(tmp_path))


def test_a_missing_file_fails(tmp_path: Path) -> None:
    manifest = _artifact(tmp_path)
    (tmp_path / "tokenizer.json").unlink()
    with pytest.raises(export.ArtifactIntegrityError, match="tokenizer.json is missing"):
        export.verify_files(tmp_path, manifest)


def test_an_altered_file_fails(tmp_path: Path) -> None:
    manifest = _artifact(tmp_path)
    (tmp_path / "model.safetensors").write_bytes(b"weightz")
    with pytest.raises(export.ArtifactIntegrityError, match="model.safetensors does not match"):
        export.verify_files(tmp_path, manifest)


def test_no_hard_coded_file_list() -> None:
    """The manifest is the only list of artifact files."""
    assert not hasattr(config, "MODEL_FILES")
