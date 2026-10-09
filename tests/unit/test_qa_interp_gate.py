"""The interpretation gate's pairs and scoring (ADR-089): the pairs rebuild identically from
the seed, each wrong pair differs from its correct pair in exactly one thing, and the gate
arithmetic is what the README pre-registered. No model is called."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
QA_INTERP = ROOT / "evals" / "qa_interp"
sys.path.insert(0, str(ROOT / "services" / "agent_qa" / "src"))


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"qa_interp_{name}", QA_INTERP / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


build_sets = load("build_sets")
gate = load("gate")
PAIRS = [
    json.loads(line) for line in (QA_INTERP / "pairs_v1.jsonl").read_text("utf-8").splitlines()
]


def by_label(domain: str, label: str) -> list[dict]:
    return [p for p in PAIRS if p["domain"] == domain and p["label"] == label]


def test_the_committed_pairs_are_what_the_seed_builds():
    assert build_sets.SEED == 20261009
    committed = (QA_INTERP / "pairs_v1.jsonl").read_text("utf-8").replace("\r\n", "\n")
    assert committed == build_sets.render(build_sets.build())


def test_building_twice_gives_the_same_pairs():
    assert build_sets.build() == build_sets.build()


def test_the_pair_counts_are_28_and_14_each_way():
    assert len(by_label("reporting", "matches")) == len(by_label("reporting", "mismatch")) == 28
    assert len(by_label("forecast", "matches")) == len(by_label("forecast", "mismatch")) == 14
    assert len(PAIRS) == 84 == gate.PAIRS_PER_RUN
    assert len({p["id"] for p in PAIRS}) == 84


def test_the_correct_pairs_are_the_labelled_expected_requests_unchanged():
    def read(path):
        return {
            json.loads(line)["id"]: json.loads(line)
            for line in path.read_text("utf-8").splitlines()
        }

    sources = {
        "reporting": read(build_sets.REPORTING_SET),
        "forecast": read(build_sets.FORECAST_SET),
    }
    for pair in PAIRS:
        if pair["label"] == "matches":
            item = sources[pair["domain"]][pair["source_id"]]
            assert pair["request"] == item["expected"] and pair["question"] == item["question"]


def changed_fields(pair: dict) -> set[str]:
    ok = next(p for p in PAIRS if p["id"] == pair["id"].replace("-bad", "-ok"))
    keys = set(pair["request"]) | set(ok["request"])
    return {k for k in keys if pair["request"].get(k) != ok["request"].get(k)}


def test_every_reporting_mutation_changes_exactly_one_thing():
    for pair in by_label("reporting", "mismatch"):
        fields = changed_fields(pair)
        assert fields, pair["id"]
        # the dates move together; everything else is a single field
        assert fields == {"start", "end"} or len(fields) == 1, (pair["id"], fields)
        assert pair["mutation"]["operator"] in build_sets.REPORTING_OPERATORS


def test_every_forecast_mutation_changes_the_slice_the_when_or_the_decline_flag():
    allowed = {"slice", "horizon_weeks", "period_start", "period_end", "unsupported"}
    for pair in by_label("forecast", "mismatch"):
        fields = changed_fields(pair)
        assert fields and fields <= allowed, (pair["id"], fields)
        if pair["mutation"]["operator"] == "slice":
            assert fields == {"slice"}
        if pair["mutation"]["operator"] == "unsupported":
            assert fields == {"unsupported"} and pair["request"]["unsupported"] is None


def test_a_labelled_decline_is_mutated_into_something_that_looks_answerable():
    from agent_qa.reporting import decline_reasons
    from schemas import ReportingRequest

    for source_id in ("r17", "f11", "f12"):
        ok = next(p for p in PAIRS if p["id"] == f"r-{source_id}-ok")
        bad = next(p for p in PAIRS if p["id"] == f"r-{source_id}-bad")
        assert decline_reasons(ReportingRequest(**ok["request"])) == {
            "unsupported_metric" if source_id == "r17" else "unsupported_area"
        }
        assert decline_reasons(ReportingRequest(**bad["request"])) == set()


def test_no_wrong_reporting_pair_is_a_request_the_agent_would_decline():
    from agent_qa.reporting import decline_reasons
    from schemas import ReportingRequest

    for pair in by_label("reporting", "mismatch"):
        assert decline_reasons(ReportingRequest(**pair["request"])) == set(), pair["id"]


def test_the_mutation_values_are_valid_requests():
    from schemas import ForecastRequest, ReportingRequest

    for pair in PAIRS:
        model = ReportingRequest if pair["domain"] == "reporting" else ForecastRequest
        model(**pair["request"])


def test_the_pairs_are_interleaved_so_a_stopped_run_has_seen_both_kinds():
    assert [p["label"] for p in PAIRS[:4]] == ["matches", "mismatch", "matches", "mismatch"]


# --------------------------------------------------------------------------- the gate


def cells(false_rejects: int, caught: int, errors: int = 0) -> list[dict]:
    """One run of 84 judged cells with the given outcomes (errors are wrong pairs' calls)."""
    out = []
    reject_budget, caught_budget, error_budget = false_rejects, caught, errors
    for p in PAIRS:
        faithful: bool | None = True
        if p["label"] == "matches":
            if reject_budget:
                faithful, reject_budget = False, reject_budget - 1
        elif error_budget:
            faithful, error_budget = None, error_budget - 1
        elif caught_budget:
            faithful, caught_budget = False, caught_budget - 1
        out.append(
            {"id": p["id"], "domain": p["domain"], "label": p["label"], "faithful": faithful}
        )
    return out


def result(*runs) -> dict:
    return {"prompt": "qa_interp_v1", "runs": list(runs)}


def test_the_gate_numbers_are_the_ones_pre_registered():
    assert (gate.MAX_FALSE_REJECTS, gate.MIN_CAUGHT) == (2, 34)
    assert (gate.CORRECT_PAIRS, gate.WRONG_PAIRS) == (42, 42)


def test_three_runs_at_the_threshold_pass():
    verdict = gate.evaluate([result(*[cells(2, 34)] * 3)])
    assert verdict["passes"] and verdict["complete"]


@pytest.mark.parametrize(("rejects", "caught"), [(3, 42), (0, 33), (5, 20), (2, 33)])
def test_one_failing_run_fails_the_gate(rejects, caught):
    verdict = gate.evaluate([result(cells(0, 42), cells(rejects, caught), cells(0, 42))])
    assert not verdict["passes"]


def test_a_failed_call_counts_against_the_pair():
    run = cells(0, 36, errors=3)
    scored = gate.evaluate([result(run, run, run)])["runs"][0]["total"]
    assert scored["errors"] == 3 and scored["caught"] == 36
    flawed = cells(0, 42)
    flawed[0]["faithful"] = None  # a correct pair whose call failed is a false reject
    assert gate.score_run({c["id"]: c for c in flawed})["total"]["false_rejects"] == 1
    # and a wrong pair whose call failed is not caught
    short = cells(0, 34, errors=1)
    assert gate.score_run({c["id"]: c for c in short})["total"]["caught"] == 34


def test_fewer_than_three_complete_runs_is_incomplete_not_a_pass():
    assert not gate.evaluate([result(cells(0, 42), cells(0, 42))])["passes"]
    partial = cells(0, 42)[:50]
    verdict = gate.evaluate([result(cells(0, 42), cells(0, 42), partial)])
    assert not verdict["passes"] and not verdict["complete"]


def test_one_complete_failing_run_fails_the_gate_even_if_the_rest_were_never_run():
    verdict = gate.evaluate([result(cells(6, 37), cells(0, 42)[:19])])
    assert verdict["failed"] and not verdict["passes"] and not verdict["complete"]
    assert verdict["runs"][0]["total"]["false_rejects"] == 6
    assert not gate.evaluate([result(cells(0, 42), cells(0, 42)[:19])])["failed"]


def test_a_resumed_file_fills_in_the_cells_the_first_one_missed():
    first = result(cells(0, 42), cells(0, 42), cells(0, 42)[:30])
    second = result([], [], cells(0, 42)[30:])
    assert gate.evaluate([first, second])["passes"]


def test_the_table_names_each_domain_and_the_verdict():
    text = gate.table(gate.evaluate([result(*[cells(1, 40)] * 3)]))
    assert "reporting" in text and "forecast" in text and "total" in text
    assert "gate: PASS" in text
