"""The volume_v2 parameter files are committed and baked into two images (ADR-098).

Checks the repo, not a running container: the files are tracked and un-ignored, they match
the manifest, the two Dockerfiles copy them, the build context lets exactly those through,
and both consumers refuse to start when a file is altered or missing.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from agent_qa.forecast import Manifest as QAManifest
from agent_qa.forecast_model import ModelUnavailable
from mcp_volume.artifact import ArtifactIntegrityError, load_verified

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "ml" / "forecast" / "artifacts" / "volume_v2.manifest.json"
MODEL_DIR = REPO_ROOT / "models" / "forecast" / "volume_v2"
MAX_BYTES = 1_000_000


def _manifest() -> dict:
    return json.loads(MANIFEST.read_bytes())


def test_the_six_files_are_the_manifests_files_and_match_its_hashes():
    files = _manifest()["files"]
    assert len(files) == 6
    assert {p.name for p in MODEL_DIR.iterdir()} == set(files)
    for name, expected in files.items():
        assert hashlib.sha256((MODEL_DIR / name).read_bytes()).hexdigest() == expected, name


def test_each_file_is_small_enough_to_commit():
    assert all(p.stat().st_size < MAX_BYTES for p in MODEL_DIR.iterdir())


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_gitignore_lets_exactly_the_parameter_files_through():
    def ignored(rel: str) -> bool:
        r = subprocess.run(
            ["git", "check-ignore", "-q", rel], cwd=REPO_ROOT, capture_output=True, check=False
        )
        return r.returncode == 0

    for name in _manifest()["files"]:
        assert not ignored(f"models/forecast/volume_v2/{name}"), name
    assert ignored("models/sentiment/bert_v1/model.safetensors")
    assert ignored("models/sentiment/bert_v1/config.json")
    assert ignored("models/forecast/volume_v2/notes.txt")
    assert ignored("models/forecast/other_v1/total.json")


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_the_files_are_tracked_in_git():
    out = subprocess.run(
        ["git", "ls-files", "models"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    assert sorted(out) == sorted(f"models/forecast/volume_v2/{n}" for n in _manifest()["files"])


@pytest.mark.parametrize("service", ["mcp_volume", "agent_qa"])
def test_the_dockerfile_copies_the_files_and_the_manifest(service):
    text = (REPO_ROOT / "services" / service / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY models/forecast/volume_v2/ /models/forecast/volume_v2/" in text
    assert "COPY ml/forecast/artifacts/volume_v2.manifest.json" in text


def test_dockerignore_allows_the_json_files_and_nothing_else_under_models():
    lines = [
        line.strip()
        for line in (REPO_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    allowed = [line for line in lines if line.startswith("!models")]
    assert allowed == ["!models/forecast/volume_v2/*.json"]


def _copy(tmp_path: Path) -> Path:
    shutil.copytree(MODEL_DIR, tmp_path / "m")
    return tmp_path / "m"


def test_both_consumers_start_on_the_committed_files(tmp_path):
    assert load_verified(MODEL_DIR, MANIFEST).slices
    assert QAManifest.load(MANIFEST, MODEL_DIR).model is not None


def test_both_consumers_refuse_to_start_on_an_altered_file(tmp_path):
    d = _copy(tmp_path)
    (d / "total.json").write_bytes((d / "total.json").read_bytes() + b" ")
    with pytest.raises(ArtifactIntegrityError):
        load_verified(d, MANIFEST)
    with pytest.raises(ModelUnavailable, match="SHA-256"):
        QAManifest.load(MANIFEST, d)


def test_both_consumers_refuse_to_start_on_a_missing_file(tmp_path):
    d = _copy(tmp_path)
    (d / "repair.json").unlink()
    with pytest.raises(ArtifactIntegrityError, match="missing"):
        load_verified(d, MANIFEST)
    with pytest.raises(ModelUnavailable):
        QAManifest.load(MANIFEST, d)
