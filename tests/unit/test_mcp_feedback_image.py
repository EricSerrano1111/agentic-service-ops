"""The `stored` image target carries no model weights and no model stack (ADR-100).

Offline checks on what Cloud Build would send and install, plus one inspection of the built
image that runs only with `RUN_DOCKER_BUILD=1` (it builds; CI does not).

- **Build context:** `.dockerignore` is an allowlist (`*`); the only `models/` path it re-includes
  is the forecast parameter files, and the directories it does include hold no weight file.
- **Stages:** the `build-stored` and `stored` stages copy nothing from `models/` and install
  without the `model` extra.
- **Image (gated):** no `*.safetensors`, and none of the four model packages importable.
"""

from __future__ import annotations

import fnmatch
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO / "services" / "mcp_feedback" / "Dockerfile"
WEIGHT_GLOBS = ("*.safetensors", "*.pt", "*.ckpt", "*.onnx", "pytorch_model.bin")
MODEL_PACKAGES = ("torch", "transformers", "safetensors", "tokenizers")


def _stage(name: str) -> str:
    text = DOCKERFILE.read_text(encoding="utf-8")
    parts = re.split(r"(?m)^FROM ", text)[1:]
    for part in parts:
        if re.match(rf"\S+ AS {re.escape(name)}\b", part):
            return part
    raise AssertionError(f"no stage {name}")


def test_dockerignore_is_an_allowlist_that_admits_no_sentiment_weights():
    rules = [
        line.strip()
        for line in (REPO / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert rules[0] == "*"
    includes = [r[1:] for r in rules if r.startswith("!")]
    models = [r for r in includes if r.startswith("models")]
    assert models == ["models/forecast/volume_v2/*.json"]
    weights = "models/sentiment/bert_v1/model.safetensors"
    for rule in includes:
        assert not fnmatch.fnmatch(weights, rule.rstrip("/") + "/*") and rule != weights
        assert rule == "ml/sentiment/artifacts/bert_v1.manifest.json" or "sentiment" not in rule


def test_no_weight_file_sits_in_a_directory_the_build_context_includes():
    """`!services/` and `!packages/` pull in everything beneath them: none may hold weights."""
    found = []
    for root in ("services", "packages"):
        for path in (REPO / root).rglob("*"):
            if ".venv" in path.parts or "node_modules" in path.parts:
                continue
            if path.is_file() and any(fnmatch.fnmatch(path.name, g) for g in WEIGHT_GLOBS):
                found.append(str(path.relative_to(REPO)))
    assert found == []


def test_the_stored_stages_copy_no_models_and_install_no_model_extra():
    for name in ("build-stored", "stored"):
        stage = _stage(name)
        assert "--extra" not in stage and "--all-extras" not in stage, name
        assert "safetensors" not in stage.lower(), name
        for line in stage.splitlines():
            if line.startswith("COPY"):
                assert "models" not in line.replace("COPY --from=", ""), (name, line)
    stored = _stage("stored")
    assert "MCP_FEEDBACK_SCORING=stored_only" in stored
    assert "HF_HUB_OFFLINE" not in stored  # nothing here loads a model
    assert "--extra model" in _stage("build-full")


def _docker_ready() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


def test_the_built_stored_image_holds_no_weights_and_no_model_packages():
    """Builds the image, so it runs only on request: `RUN_DOCKER_BUILD=1` (not in CI)."""
    if os.environ.get("RUN_DOCKER_BUILD") != "1":
        pytest.skip("set RUN_DOCKER_BUILD=1 to build the stored target and inspect it")
    if not _docker_ready():
        pytest.fail("RUN_DOCKER_BUILD=1 but Docker is not available")
    tag = "mcp-feedback-stored:unit-test"
    build = subprocess.run(
        ["docker", "build", "-f", str(DOCKERFILE), "--target", "stored", "-t", tag, str(REPO)],
        capture_output=True,
        text=True,
    )
    assert build.returncode == 0, build.stderr[-1200:]
    find = " -o ".join(f"-name '{g}'" for g in WEIGHT_GLOBS)
    probe = (
        f"find / -xdev \\( {find} \\) -not -path '/proc/*' 2>/dev/null; "
        'python -c "import importlib.util as u;'
        f'print([m for m in {MODEL_PACKAGES!r} if u.find_spec(m)])"'
    )
    out = subprocess.run(
        ["docker", "run", "--rm", "--entrypoint", "sh", tag, "-c", probe],
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stderr[-600:]
    lines = [x for x in out.stdout.splitlines() if x.strip()]
    assert lines == ["[]"], lines  # no weight file listed, and no model package found
