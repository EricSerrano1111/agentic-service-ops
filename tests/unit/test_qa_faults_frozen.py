"""The fault-injection catalogue, generator and report, checked offline (ADR-091).

Nothing here runs QA or touches a database. It holds the frozen pieces together: every fault in
the catalogue has a mutation and the other way round, the pre-registered rating table is the
rule's own arithmetic, the generator's order is a function of the seed, and the report builds
from a hand-made results file.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest
import yaml

QA_FAULTS = Path(__file__).resolve().parents[2] / "evals" / "qa_faults"
sys.path.insert(0, str(QA_FAULTS))

import faults as F  # noqa: E402
import generate as G  # noqa: E402
import report  # noqa: E402

CATALOGUE = yaml.safe_load((QA_FAULTS / "catalogue_v1.yaml").read_text(encoding="utf-8"))
FAULTS = {f["id"]: f for f in CATALOGUE["faults"]}


def test_every_catalogued_fault_has_a_mutation_and_the_other_way_round():
    assert set(FAULTS) == set(F.REGISTRY)
    for fid, fault in F.REGISTRY.items():
        assert fault.agent == FAULTS[fid]["agent"], fid


def test_the_seed_and_case_limit_are_the_ones_the_prompt_fixed():
    assert CATALOGUE["seed"] == G.SEED == 20261010
    assert CATALOGUE["max_cases_per_fault"] == G.MAX_CASES == 10


def test_every_fault_states_its_expected_outcome_and_the_owner_ones_their_authorship():
    for fid, f in FAULTS.items():
        assert f["expected"] in ("caught", "known_gap", "per_rule"), fid
        assert (f.get("description") or f.get("variant")) and f["mutation"], fid
        if f["class"] == "owner":
            assert f["authorship"] == "owner-selected, AI-co-written", fid
            assert f["owner_wording"] and f["translation"], fid
        if f["expected"] == "known_gap":
            assert f["expected_checks"] == [], fid
    classes = {f["class"] for f in FAULTS.values()}
    assert classes == {"injected", "database", "rating", "misparse", "owner"}


def test_the_owner_variants_are_separate_faults_with_the_owners_expected_outcomes():
    expected = {
        "O1a": "caught",
        "O1b": "caught",
        "O2": "caught",
        "O3a": "caught",
        "O3b": "caught",
        "O4a": "known_gap",
        "O4b": "known_gap",
        "O5": "known_gap",
    }
    for fid, outcome in expected.items():
        assert FAULTS[fid]["expected"] == outcome


def test_the_pre_registered_rating_table_is_the_rules_own_arithmetic():
    table = CATALOGUE["rating_rule"]["threshold_x_by_n"]
    for n, x_star in table.items():
        assert F.rating_rule_fails(n, x_star)
        assert not F.rating_rule_fails(n, x_star - 1)
    for level, spec in CATALOGUE["rating_rule"]["levels"].items():
        assert spec["rate"] == F.RATING_LEVELS[level]
        for n, row in spec["predicted_caught_by_n"].items():
            assert row["x"] == round(spec["rate"] * n)
            assert row["caught"] == F.rating_rule_fails(n, row["x"])


def test_the_rule_needs_20_comments_and_a_contradiction():
    assert not F.rating_rule_fails(19, 19)
    assert not F.rating_rule_fails(5000, 0)
    assert F.rating_rule_fails(20, 3)  # P(X >= 3 | 20, 0.01) is about 0.0010


def test_the_candidate_order_is_a_function_of_the_seed_with_anchors_first():
    applicable = [{"base_id": f"reporting:{i:02d}"} for i in range(30)] + [{"base_id": "owner:A1"}]
    a = G.candidate_order("O1a", applicable, {"owner:A1"})
    assert a == G.candidate_order("O1a", applicable, {"owner:A1"})
    assert a[0] == "owner:A1" and sorted(a) == sorted(b["base_id"] for b in applicable)
    assert a != G.candidate_order("O1b", applicable, {"owner:A1"})
    assert (
        G.case_rng("R01", "reporting:m01").random() == G.case_rng("R01", "reporting:m01").random()
    )


def test_month_shifts_keep_month_ends_and_stay_in_the_window():
    assert F.add_months(dt.date(2026, 1, 31), 1) == dt.date(2026, 2, 28)
    assert F.add_months(dt.date(2026, 2, 28), 1) == dt.date(2026, 3, 31)
    # one month later would pass the window end (2026-08-30), so one month earlier
    assert F.shifted_range(dt.date(2026, 7, 1), dt.date(2026, 7, 31)) == (
        dt.date(2026, 6, 1),
        dt.date(2026, 6, 30),
    )
    with pytest.raises(F.Skip):
        F.shifted_range(dt.date(2023, 9, 4), dt.date(2026, 8, 30))
    s, e = F.shifted_range(dt.date(2026, 10, 1), dt.date(2026, 10, 31), historical=False)
    assert (s, e) == (dt.date(2026, 11, 1), dt.date(2026, 11, 30))


def test_text_edit_helpers():
    assert F.last_digit("0.9881") == "0.9882" and F.last_digit("0.9889") == "0.9880"
    assert F.bump_in_text("As of x: 54 incidents", "54", "55") == "As of x: 55 incidents"
    with pytest.raises(F.Skip):
        F.bump_in_text("540 incidents", "54", "55")
    assert F.percent("0.9881") == "98.81%"


def test_wilson_interval_matches_known_values():
    lo, hi = report.wilson(0, 10)
    assert lo == 0.0 and hi == pytest.approx(0.2775, abs=1e-3)
    lo, hi = report.wilson(10, 10)
    assert hi == pytest.approx(1.0) and lo == pytest.approx(0.7225, abs=1e-3)
    lo, hi = report.wilson(50, 100)
    assert (lo, hi) == (pytest.approx(0.4038, abs=1e-3), pytest.approx(0.5962, abs=1e-3))


def test_the_report_builds_from_a_small_results_file():
    bases = {
        "bases": [
            {"base_id": "reporting:m01", "agent": "reporting", "kind": "answer"},
            {"base_id": "sentiment:p01", "agent": "sentiment", "kind": "decline"},
        ],
        "excluded": [],
    }
    caught = {
        "status": "run",
        "verdict": "fail",
        "failed_checks": ["figures_match_database"],
        "checks_run": [],
        "question": "q",
        "agent": "reporting",
    }
    missed = {
        "status": "run",
        "verdict": "pass",
        "failed_checks": [],
        "checks_run": ["a"],
        "question": "q",
        "agent": "reporting",
    }
    results = {
        "seed": 20261010,
        "started_utc": "x",
        "qa_ran": True,
        "controls": [
            {
                "base_id": "reporting:m01",
                "agent": "reporting",
                "verdict": "pass",
                "failed_checks": [],
                "failed_details": {},
            },
        ],
        "cases": [
            {
                **caught,
                "case_id": "R01|reporting:m01",
                "fault_id": "R01",
                "base_id": "reporting:m01",
            },
            {
                **missed,
                "case_id": "R02|reporting:m01",
                "fault_id": "R02",
                "base_id": "reporting:m01",
            },
        ],
    }
    text = report.build(results, CATALOGUE, bases)
    for heading in (
        "## 1.",
        "## 2.",
        "## 3.",
        "## 4.",
        "## 5.",
        "## 6.",
        "## 7.",
        "## 8.",
        "## 9.",
        "## 10.",
        "## 11.",
    ):
        assert heading in text
    assert "R02|reporting:m01" in text  # the miss is listed
    assert "1/2 = 50.0%" in text
