"""Golden sets v1 and v2 (ADR-074, ADR-075): the items' contract, the oracle names, the
manifest hashes, and the independence guard. Offline; the oracles' figures are checked in
tests/integration/test_golden_oracles.py."""

from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "evals" / "golden"
sys.path.insert(0, str(GOLDEN))

import oracles  # noqa: E402
from schema import Item  # noqa: E402

SETS = ["golden_v1", "golden_v2"]


def load(name: str) -> list[Item]:
    lines = (GOLDEN / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
    return [Item.model_validate_json(line) for line in lines if line]


@pytest.mark.parametrize("name", SETS)
def test_every_item_validates_and_the_set_is_complete(name):
    items = load(name)
    assert [i.id for i in items] == [f"G{n:02d}" for n in range(1, 37)]
    assert sum(i.author == "owner" for i in items) == 10
    assert all(i.author == "owner" for i in items[:10])
    assert {i.id for i in items if i.stretch} == {"G02", "G04", "G05", "G10"}


@pytest.mark.parametrize("name", SETS)
def test_every_oracle_name_exists(name):
    assert {i.oracle for i in load(name) if i.oracle is not None} <= set(oracles.ORACLES)


def test_every_oracle_is_used_by_some_set():
    used = {i.oracle for name in SETS for i in load(name) if i.oracle is not None}
    assert used == set(oracles.ORACLES)


@pytest.mark.parametrize("name", SETS)
def test_expected_file_covers_exactly_the_oracle_items(name):
    expected = json.loads((GOLDEN / f"{name}.expected.json").read_text(encoding="utf-8"))
    assert set(expected["items"]) == {i.id for i in load(name) if i.oracle is not None}
    assert expected["sentiment_model_version"] == oracles.SENTIMENT_MODEL_VERSION


@pytest.mark.parametrize("name", SETS)
def test_manifest_hashes_match_the_committed_files(name):
    """The questions and expected figures are frozen; an edit changes the hash (ADR-074)."""
    manifest = json.loads((GOLDEN / f"{name}.manifest.json").read_text(encoding="utf-8"))
    for part in ("questions", "expected"):
        path = GOLDEN / manifest[part]["file"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest[part]["sha256"], part


def test_v2_changes_only_g01_g16_g35_and_says_why():
    """ADR-075: G35 expects intent_ambiguous; G01/G16 are scored on `reason`, which the API
    returns, not on v1's error codes; every other item is v1's, apart from the field name."""
    v1 = {i.id: i for i in load("golden_v1")}
    v2 = {i.id: i for i in load("golden_v2")}
    [g35] = v2["G35"].acceptable_outcomes
    assert v2["G35"].acceptable_routes == ["ambiguous"]
    assert (v2["G35"].expected_behaviour, g35.outcome, g35.reason) == (
        "clarify",
        "needs_clarification",
        "intent_ambiguous",
    )
    assert [o.reason for o in v2["G01"].acceptable_outcomes] == ["technician_not_found"]
    assert [o.reason for o in v2["G16"].acceptable_outcomes] == ["technician_ambiguous"]
    assert all(o.error_code is None for i in v2.values() for o in i.acceptable_outcomes)
    for gid in set(v1) - {"G01", "G16", "G35"}:
        a, b = v1[gid].model_dump(), v2[gid].model_dump()
        for item in (a, b):
            for o in item["acceptable_outcomes"]:
                o.pop("error_code"), o.pop("reason")
        assert a == b, gid
    manifest = json.loads((GOLDEN / "golden_v2.manifest.json").read_text(encoding="utf-8"))
    assert manifest["derived_from"] == "golden_v1"
    assert "not been run" in manifest["disclosure"] and "G35" in manifest["reason"]


def _service_packages() -> set[str]:
    return {p.name for p in (ROOT / "services").glob("*/src/*") if (p / "__init__.py").is_file()}


def test_golden_code_imports_nothing_from_the_system():
    """Oracles must not share code with what they check: no service package and no LLM
    client. `forecast_runtime` is ADR-074's documented exception."""
    forbidden = _service_packages() | {"llm"}
    assert {"mcp_incidents", "mcp_feedback", "agent_sentiment", "orchestrator"} <= forbidden
    for path in GOLDEN.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            else:
                continue
            for name in names:
                assert name.split(".")[0] not in forbidden, f"{path.name} imports {name}"
