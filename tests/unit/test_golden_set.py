"""Golden set v1 (ADR-074): the items' contract, the oracle names, the manifest hashes, and
the independence guard. Offline; the oracles' figures are checked in
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


@pytest.fixture(scope="module")
def items() -> list[Item]:
    lines = (GOLDEN / "golden_v1.jsonl").read_text(encoding="utf-8").splitlines()
    return [Item.model_validate_json(line) for line in lines if line]


def test_every_item_validates_and_the_set_is_complete(items):
    assert [i.id for i in items] == [f"G{n:02d}" for n in range(1, 37)]
    assert sum(i.author == "owner" for i in items) == 10
    assert all(i.author == "owner" for i in items[:10])
    assert {i.id for i in items if i.stretch} == {"G02", "G04", "G05", "G10"}


def test_every_oracle_name_exists_and_every_oracle_is_used(items):
    named = {i.oracle for i in items if i.oracle is not None}
    assert named <= set(oracles.ORACLES)
    assert set(oracles.ORACLES) == named


def test_expected_file_covers_exactly_the_oracle_items(items):
    expected = json.loads((GOLDEN / "golden_v1.expected.json").read_text(encoding="utf-8"))
    assert set(expected["items"]) == {i.id for i in items if i.oracle is not None}
    assert expected["sentiment_model_version"] == oracles.SENTIMENT_MODEL_VERSION


def test_manifest_hashes_match_the_committed_files():
    """The questions and expected figures are frozen; an edit changes the hash (ADR-074)."""
    manifest = json.loads((GOLDEN / "golden_v1.manifest.json").read_text(encoding="utf-8"))
    for part in ("questions", "expected"):
        path = GOLDEN / manifest[part]["file"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest[part]["sha256"], part


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
