"""Every step image in the deploy pipeline is pinned by digest (ADR-121).

On 2026-11-10 the floating tag `cloud-sdk:slim` moved to an image with no `python3`, and the
first deploy step failed (L-107). A tag can move under the pipeline; a digest cannot. This test
covers the `name:` of each step in `deploy/cloudbuild.yaml` only, not the service Dockerfiles.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

CLOUDBUILD = Path(__file__).resolve().parents[2] / "deploy" / "cloudbuild.yaml"

#: `<repository>@sha256:<64 hex digits>`, and nothing after the digest.
PINNED = re.compile(r"^\S+@sha256:[0-9a-f]{64}$")


def is_pinned(image: str) -> bool:
    return PINNED.match(image) is not None


def test_every_step_image_is_pinned_by_digest():
    steps = yaml.safe_load(CLOUDBUILD.read_text("utf-8"))["steps"]
    assert steps, "no steps found in deploy/cloudbuild.yaml"
    floating = [f"{s.get('id', '?')}: {s['name']}" for s in steps if not is_pinned(s["name"])]
    assert not floating, "step images not pinned by @sha256 digest (ADR-121): " + "; ".join(
        floating
    )


@pytest.mark.parametrize(
    "image",
    [
        "gcr.io/google.com/cloudsdktool/cloud-sdk:slim",
        "gcr.io/google.com/cloudsdktool/cloud-sdk:stable",
        "gcr.io/cloud-builders/docker",
        "python:3.12-slim",
        "python:3.12-slim@sha256:abc",  # a truncated digest is not a pin
        "python@sha256:" + "g" * 64,  # not hex
    ],
)
def test_the_check_rejects_floating_or_malformed_references(image):
    assert not is_pinned(image)


def test_the_check_accepts_a_digest_reference():
    assert is_pinned("python:3.12-slim@sha256:" + "a" * 64)
    assert is_pinned("gcr.io/cloud-builders/docker@sha256:" + "0" * 64)
