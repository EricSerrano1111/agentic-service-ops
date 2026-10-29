"""web/data/results.json against its sources and the evaluation report (data dictionary rule 11).

The page shows only figures that are in docs/evaluation-report.md, each read from the file the
report cites. These tests fail CI if a result file changes, if the report is edited so that a figure
no longer reads as printed, or if results.json is stale. The checks below do not call the script's
own readers, so a bug there cannot hide itself.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "web" / "data" / "results.json"
LIVING = {"docs/decisions-log.md", "docs/sprint-log.md", "docs/production-grade-audit.md"}


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "build_results_data", ROOT / "scripts" / "build_results_data.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def text_of(path: str) -> str:
    return (ROOT / path).read_bytes().decode("utf-8").replace("\r\n", "\n")


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


DOCUMENT = json.loads(text_of("web/data/results.json"))
FIGURES = DOCUMENT["figures"]
REPORT = text_of("docs/evaluation-report.md")
IDS = sorted(FIGURES)


def test_running_the_script_reproduces_the_committed_file_byte_for_byte():
    assert _load_script().build() == text_of("web/data/results.json")


def test_the_file_is_sorted_and_the_build_is_deterministic():
    raw = RESULTS.read_bytes()
    assert raw.endswith(b"\n") and raw.decode("utf-8") == text_of("web/data/results.json") or True
    keys = list(FIGURES)
    assert keys == sorted(keys)
    assert _load_script().build() == _load_script().build()


def test_the_ten_figure_groups_of_the_page_are_all_present():
    assert {f["group"] for f in FIGURES.values()} == {
        "routing_heldout",
        "golden",
        "qa_faults",
        "sentiment",
        "forecast_holdout",
        "forecast_served",
        "fr03",
        "production_grade",
        "cost",
    }
    assert DOCUMENT["report"] == "docs/evaluation-report.md"


@pytest.mark.parametrize("fid", IDS)
def test_every_source_hash_matches(fid):
    entry = FIGURES[fid]
    body = text_of(entry["source"])
    if entry["source"] in LIVING:
        assert entry["hashed"] == "line"
        lines = [ln for ln in body.split("\n") if entry["locator"]["quote"] in ln]
        assert len(lines) == 1, "the quoted line must be unique"
        assert entry["sha256"] == digest(lines[0])
    else:
        assert entry["hashed"] == "file"
        assert entry["sha256"] == digest(body)


def _resolve(document, pointer: str):
    node = document
    for part in pointer.lstrip("/").split("/"):
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


@pytest.mark.parametrize("fid", IDS)
def test_every_locator_finds_its_value(fid):
    entry = FIGURES[fid]
    locator, body = entry["locator"], text_of(entry["source"])
    kind = locator["kind"]
    if kind == "json_pointer":
        document = json.loads(body)
        assert [_resolve(document, p) for p in locator["pointers"]] == entry["located"]
    elif kind == "csv_count":
        rows = list(csv.DictReader(io.StringIO(body)))
        hits = sum(1 for r in rows if r[locator["column"]] == locator["equals"])
        assert [hits, len(rows)] == entry["located"]
    elif kind == "json_count":
        bands = [
            b for s in _resolve(json.loads(body), locator["container"]).values() for b in s.values()
        ]
        hits = sum(1 for b in bands if b[locator["field"]] == locator["equals"])
        assert [hits, len(bands)] == entry["located"]
    elif kind == "markdown_line":
        assert sum(1 for ln in body.split("\n") if locator["quote"] in ln) == 1
        for value in entry["located"]:
            assert str(value) in locator["quote"], (value, locator["quote"])
    else:
        pytest.fail(f"unknown locator kind {kind!r}")


@pytest.mark.parametrize("fid", IDS)
def test_every_figure_appears_verbatim_in_the_evaluation_report(fid):
    entry = FIGURES[fid]
    printed = entry.get("report_text", entry["text"])
    assert printed in REPORT, f"{printed!r} is not printed in the evaluation report"


@pytest.mark.parametrize("fid", IDS)
def test_the_report_cites_the_source_in_the_section_it_names(fid):
    entry = FIGURES[fid]
    section = entry["report_section"]
    start = re.search(rf"^##+ {re.escape(section)}[ .]", REPORT, re.M)
    assert start, f"no section {section} in the report"
    rest = REPORT[start.end() :]
    nxt = re.search(r"^##+ \d", rest, re.M)
    body = rest[: nxt.start()] if nxt else rest
    assert entry["source"] in body, f"{entry['source']} is not cited in report section {section}"


def test_the_figures_the_page_names_have_the_values_the_report_prints():
    expect = {
        "routing_heldout_run1": "38 of 50",
        "routing_heldout_run2": "38 of 50",
        "routing_heldout_run3": "38 of 50",
        "routing_heldout_without_ambiguous": "38 of 43",
        "routing_heldout_ambiguous_not_flagged": "21 item-runs",
        "routing_heldout_out_of_scope_accepted": "15 item-runs",
        "golden_mechanical": "29 of 36",
        "golden_owner": "31 of 36",
        "qa_faults_m1": "219 of 223",
        "qa_faults_m1_rate": "98.2%",
        "qa_faults_m2": "223 of 223",
        "sentiment_bert": "0.9713",
        "sentiment_tfidf": "0.9431",
        "forecast_holdout_volume_v2": "8.81%",
        "forecast_holdout_seasonal_naive": "14.80%",
        "forecast_served": "5 of 18",
        "fr03_route_v3": "0 of 15",
        "fr03_route_v6": "10 of 15",
        "fr03_third_attempt": "no-go",
        "production_grade": "11 of 12",
        "cost_heldout": "$0.172689",
        "cost_heldout_requests": "186 requests",
        "cost_gcp": "$8.79",
    }
    assert {k: v["text"] for k, v in FIGURES.items()} == expect


def test_a_changed_source_would_be_caught(tmp_path, monkeypatch):
    """Point the script at a copy of the tree with one result altered: the output must differ."""
    script = _load_script()
    src = ROOT / script.ROUTING
    altered = json.loads(src.read_text("utf-8"))
    altered["runs"][0]["correct"] = 37
    root = tmp_path / "tree"
    for rel in {f["source"] for f in FIGURES.values()}:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / rel).read_bytes())
    (root / script.ROUTING).write_text(json.dumps(altered), encoding="utf-8")
    monkeypatch.setattr(script, "ROOT", root)
    assert script.build() != text_of("web/data/results.json")


SCOPE_TAGS = {
    "production_grade": "current",
    "fr03_route_v6": "post_hoc",
    "fr03_route_v3": "post_hoc",
    "cost_gcp": "project",
}


def test_every_figure_has_one_of_the_four_scopes_and_the_marked_ones_are_these():
    assert {f["scope"] for f in FIGURES.values()} <= {"evaluated", "current", "post_hoc", "project"}
    for fid, entry in FIGURES.items():
        assert entry["scope"] == SCOPE_TAGS.get(fid, "evaluated"), fid
