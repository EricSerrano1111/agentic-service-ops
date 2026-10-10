"""The QA agent is independent of what it checks (ADR-055, ADR-087).

QA recomputes every figure from the data dictionary with its own SQL. If it imported the
incidents server's queries, the forecast runtime or a specialist's renderer, the two would
agree because they share code, and a bug in the shared part would pass its own check. So this
suite fails if `services/agent_qa` imports any of them, depends on them, calls the specialists,
or reaches a database role, a table or a column it has no business with.
"""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "services" / "agent_qa"
SOURCES = sorted((QA / "src" / "agent_qa").glob("*.py"))

#: Everything QA must not import: the specialists, their servers, the shared forecast code, the
#: ORM models (QA writes SQL from the data dictionary) and the MCP SDK (QA calls no tool).
FORBIDDEN_MODULES = {
    "mcp",
    "mcp_incidents",
    "mcp_feedback",
    "mcp_volume",
    "agent_reporting",
    "agent_sentiment",
    "agent_forecast",
    "orchestrator",
    "forecast_runtime",
    "db_models",
    "torch",
    "transformers",
    "tokenizers",
    "safetensors",
    "ml",
    "evals",
    "data",
}
FORBIDDEN_DISTRIBUTIONS = {
    "mcp",
    "mcp-incidents",
    "mcp-feedback",
    "mcp-volume",
    "agent-reporting",
    "agent-sentiment",
    "agent-forecast",
    "orchestrator",
    "forecast-runtime",
    "db-models",
    "service-ops-forecast-runtime",
    "service-ops-db-models",
    "numpy",
    "scipy",
    "torch",
    "transformers",
    "tokenizers",
    "safetensors",
}


def imported_modules(path: Path) -> set[str]:
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module)
    return found


def test_the_sources_are_found():
    assert {p.name for p in SOURCES} >= {"reporting.py", "forecast.py", "db.py", "executor.py"}


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_no_module_imports_a_specialist_a_server_or_shared_forecast_code(path):
    roots = {m.split(".")[0] for m in imported_modules(path)}
    assert roots & FORBIDDEN_MODULES == set(), path.name


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_qa_makes_no_a2a_client_calls(path):
    """QA is called; it never calls a specialist (or anything else) over A2A."""
    modules = imported_modules(path)
    assert not {m for m in modules if m.startswith("a2a.client")}, path.name


def test_the_package_does_not_depend_on_what_it_checks():
    project = tomllib.loads((QA / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    names = {re.split(r"[\[<>=!~ ]", dep, maxsplit=1)[0].lower() for dep in project["dependencies"]}
    assert names & FORBIDDEN_DISTRIBUTIONS == set()


def test_the_image_installs_only_the_qa_package_and_bakes_in_only_the_manifest():
    dockerfile = (QA / "Dockerfile").read_text(encoding="utf-8")
    assert "--package agent-qa" in dockerfile
    copies = [line for line in dockerfile.splitlines() if line.startswith("COPY ml/")]
    # Two JSON manifests and nothing else: the forecast's (served flags, shown errors) and the
    # sentiment model's (the predictions' model_version and the threshold τ). No weights, no code.
    assert copies == [
        "COPY ml/forecast/artifacts/volume_v2.manifest.json /app/artifacts/volume_v2.manifest.json",
        "COPY ml/sentiment/artifacts/bert_v1.manifest.json /app/artifacts/bert_v1.manifest.json",
    ]
    assert "USER app" in dockerfile and "useradd --system --uid 10001 app" in dockerfile


def test_qa_reads_only_its_own_role_credentials():
    text = "\n".join(p.read_text(encoding="utf-8") for p in SOURCES)
    roles = set(re.findall(r"DB_ROLE_[A-Z]+_(?:USER|PASSWORD)", text))
    assert roles == {"DB_ROLE_QA_USER", "DB_ROLE_QA_PASSWORD"}
    assert "POSTGRES_ADMIN" not in text


def test_qas_sql_never_names_a_table_or_column_it_has_no_business_with():
    """`app_qa` can read these (data dictionary §7), but the checks never need them: staff
    notes (`incident_notes`) and PII (`contacts`) stay out of QA's code, and QA holds no grant on
    gold labels or generator parameters (ADR-063). The one customer text QA reads is
    `feedback_text`, to compare a quoted comment with the original (ADR-090); see below."""
    sql = (QA / "src" / "agent_qa" / "db.py").read_text(encoding="utf-8")
    for name in (
        "incident_notes",
        "contacts",
        "internal_users",
        "sentiment_labels",
        "generation_parameters",
        "payment_reference",
        "labor_charge",
    ):
        assert name not in sql, name


def test_qas_sql_is_read_only_and_parameterised():
    sql = (QA / "src" / "agent_qa" / "db.py").read_text(encoding="utf-8")
    assert not re.search(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|GRANT|COPY)\b", sql)
    assert "text(" in sql and "execute(text(sql), params or {})" in sql


def test_the_workspace_lists_agent_qa_and_the_lock_pins_it():
    workspace = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "services/agent_qa" in workspace["tool"]["uv"]["workspace"]["members"]
    assert 'name = "agent-qa"' in (ROOT / "uv.lock").read_text(encoding="utf-8")


def test_the_sentiment_checks_import_only_shared_contracts_and_stats():
    """`agent_qa/sentiment.py` may use the shared schemas and `common.stats` (the cross-check's
    binomial tail, shared with the baseline script); not the sentiment agent, the feedback
    server, or any model or ML library."""
    roots = {m.split(".")[0] for m in imported_modules(QA / "src" / "agent_qa" / "sentiment.py")}
    assert roots - {
        "__future__",
        "datetime",
        "hashlib",
        "json",
        "math",
        "re",
        "dataclasses",
        "decimal",
        "pathlib",
        "typing",
        "common",
        "schemas",
    } <= {""}
    assert "common.stats" in imported_modules(QA / "src" / "agent_qa" / "sentiment.py")


def test_qa_never_names_the_models_files_or_scoring_code():
    for path in SOURCES:
        source = path.read_text(encoding="utf-8")
        for needle in ("classifier", "mcp_feedback", "agent_sentiment", ".safetensors", "torch"):
            assert needle not in source.replace("mcp_feedback server", ""), (path.name, needle)


def test_a_comments_text_is_selected_in_one_place_only_and_never_leaves_the_checks():
    """QA reads `feedback_text` once, to compare a quote with the original, and `rating` once, for
    the cross-check. Neither reaches the language model: the interpretation reading is built from
    the parsed request alone (`test_qa_sentiment_service.py` records the model's input)."""
    db = (QA / "src" / "agent_qa" / "db.py").read_text(encoding="utf-8")
    assert db.count("f.feedback_text,") == 1 and db.count("f.rating") == 3
    interp = (QA / "src" / "agent_qa" / "interpretation.py").read_text(encoding="utf-8")
    for needle in ("feedback_text", ".examples", "quote", ".summary", ".counts", "answer.text"):
        assert needle not in interp, needle
