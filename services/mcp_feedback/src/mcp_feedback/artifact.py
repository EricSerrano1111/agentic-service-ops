"""The model artifact: manifest, hash check, and the version predictions are stored under.

Read at start-up. Every file the manifest lists must exist under `MODELS_DIR` with its
recorded SHA-256, or the server refuses to start (ADR-066, ADR-067). The model itself is
not loaded here; see `classifier.py`.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


class ArtifactIntegrityError(RuntimeError):
    """A listed file is missing or does not match the manifest. The server won't start."""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class Artifact:
    directory: Path
    #: SHA-256 of the manifest file: `sentiment_predictions.model_version`.
    model_version: str
    name: str
    labels: tuple[str, ...]
    max_length: int
    temperature: float
    threshold: float
    files: dict[str, str]


def load_verified(directory: Path, manifest_path: Path) -> Artifact:
    """Read the manifest, verify every listed file, and return the artifact."""
    if not manifest_path.is_file():
        raise ArtifactIntegrityError(f"manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_bytes())
    for name, expected in manifest["files"].items():
        path = directory / name
        if not path.is_file():
            raise ArtifactIntegrityError(f"{name} is missing from {directory}")
        if _sha256(path) != expected:
            raise ArtifactIntegrityError(f"{name} does not match the manifest's SHA-256")
    calibration = manifest["calibration"]
    if calibration.get("temperature") is None or calibration.get("threshold") is None:
        raise ArtifactIntegrityError("manifest has no calibration values (ADR-066)")
    return Artifact(
        directory=directory,
        model_version=_sha256(manifest_path),
        name=manifest["artifact"],
        labels=tuple(manifest["labels"]),
        max_length=int(manifest["max_length"]),
        temperature=float(calibration["temperature"]),
        threshold=float(calibration["threshold"]),
        files=dict(manifest["files"]),
    )
