"""The full-system trigger's file filter (ADR-099): what a push to main does and does not build.

Cloud Build's glob is Go's `filepath.Match` plus `**` and brace alternation; a build starts when
at least one changed file matches `includedFiles` and is not matched by `ignoredFiles`
(https://docs.cloud.google.com/build/docs/automating-builds/create-manage-triggers, read
2026-10-12). The matcher below implements that and is checked against the documentation's own
examples before it is used on the trigger.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

TRIGGER = yaml.safe_load(
    (Path(__file__).resolve().parents[2] / "deploy" / "trigger_full.yaml").read_text("utf-8")
)


def glob_match(pattern: str, path: str) -> bool:
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**", i):
            out += ".*"
            i += 2
            if pattern.startswith("/", i):
                # `a/**/b` also matches `a/b`: the slash after ** may be empty
                out = out[:-2] + "(?:.*/)?"
                i += 1
        elif pattern[i] == "*":
            out += "[^/]*"
            i += 1
        elif pattern[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(pattern[i])
            i += 1
    return re.fullmatch(out, path) is not None


def builds(changed: list[str], trigger: dict = TRIGGER) -> bool:
    included = trigger.get("includedFiles", [])
    ignored = trigger.get("ignoredFiles", [])
    return any(
        any(glob_match(p, f) for p in included) and not any(glob_match(p, f) for p in ignored)
        for f in changed
    )


def test_the_matcher_agrees_with_the_documentation_examples():
    # "`src/*` matches `src/code.py` but not `src/sub/code.py`, while `src/**` matches both."
    assert glob_match("src/*", "src/code.py") and not glob_match("src/*", "src/sub/code.py")
    assert glob_match("src/**", "src/code.py") and glob_match("src/**", "src/sub/code.py")
    # "ignore `**/README.md` and include `src/*`: a change to `src/README.md` does not build."
    doc = {"includedFiles": ["src/*"], "ignoredFiles": ["**/README.md"]}
    assert not builds(["src/README.md"], doc)
    assert builds(["src/code.py"], doc)


def test_the_trigger_ships_disabled_with_its_own_name_and_the_pipeline_file():
    assert TRIGGER["disabled"] is True
    assert TRIGGER["name"] == "deploy-reporting-slice"
    assert TRIGGER["filename"] == "deploy/cloudbuild.yaml"
    assert TRIGGER["repositoryEventConfig"]["push"]["branch"] == "^main$"


def test_a_docs_only_change_cannot_deploy():
    changed = [
        "docs/decisions-log.md",
        "docs/sprint-log.md",
        "docs/screenshots/gateway.png",
        "docs/academic/01-Project-Proposal.md",
        "README.md",
        "CLAUDE.md",
        "deploy/README.md",
        "deploy/RUNBOOK_V.md",
        "services/api_gateway/README.md",
    ]
    assert not builds(changed)
    for one in changed:
        assert not builds([one]), one


def test_a_docs_change_alongside_code_still_builds():
    assert builds(["docs/sprint-log.md", "services/agent_qa/src/agent_qa/app.py"])


@pytest.mark.parametrize(
    "path",
    [
        "services/orchestrator/prompts/route_v5.md",  # baked into the image: must redeploy
        "services/agent_reporting/prompts/parse_v4.md",
        "services/agent_qa/src/agent_qa/forecast.py",
        "services/api_gateway/src/api_gateway/app.py",
        "packages/schemas/src/schemas/__init__.py",
        "web/app/page.jsx",
        "web/package-lock.json",
        "deploy/cloudrun/gateway.yaml",
        "deploy/cloudbuild.yaml",
        "ml/forecast/artifacts/volume_v2.manifest.json",
        "ml/sentiment/artifacts/bert_v1.manifest.json",
        "models/forecast/volume_v2/total.json",
        "pyproject.toml",
        "uv.lock",
    ],
)
def test_a_change_to_anything_baked_into_an_image_builds(path):
    assert builds([path]), path


@pytest.mark.parametrize(
    "path",
    [
        "tests/unit/test_deploy_full.py",
        "evals/results/qa_faults/x.json",
        "data/generator/generate.py",
        "scripts/invites.py",
        ".github/workflows/ci.yml",
        "models/sentiment/bert_v1/config.json",
    ],
)
def test_changes_outside_the_images_do_not_build(path):
    assert not builds([path]), path


def test_the_ignore_list_does_not_swallow_the_prompts():
    assert not any(
        glob_match(p, "services/orchestrator/prompts/route_v5.md") for p in TRIGGER["ignoredFiles"]
    )
    assert "**/*.md" not in TRIGGER["ignoredFiles"]
