"""The Sprint 5 gate scorers (Prompt W, evals/sprint5_gates.md): thresholds and completeness are
what the pre-registration says. No model is called."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(rel: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


interp = load("evals/qa_interp/gate_s5.py", "gate_s5")
fr03 = load("evals/routing/fr03_gate.py", "fr03_gate")

# ---------------------------------------------------------------- interpretation gate

SPLIT = {"reporting": 10, "forecast": 7, "sentiment": 6}


def cells(false_rejects: int, caught: int, *, errors: int = 0) -> list[dict]:
    out, n = [], 0
    for domain, k in SPLIT.items():
        for i in range(k):
            out.append(
                {"id": f"{domain}-{i}-ok", "domain": domain, "label": "matches", "faithful": True}
            )
            out.append(
                {
                    "id": f"{domain}-{i}-bad",
                    "domain": domain,
                    "label": "mismatch",
                    "faithful": False,
                }
            )
    correct = [c for c in out if c["label"] == "matches"]
    wrong = [c for c in out if c["label"] == "mismatch"]
    for c in correct[:false_rejects]:
        c["faithful"] = False
    for c in wrong[: len(wrong) - caught]:
        c["faithful"] = True
    for c in out[:errors]:
        c["faithful"] = None
    n += 1
    return out


def result(*runs: list[dict]) -> dict:
    return {"prompt": "qa_interp_v3", "runs": list(runs)}


def test_the_thresholds_are_the_rounded_rates():
    assert (interp.CORRECT_PAIRS, interp.WRONG_PAIRS, interp.PAIRS_PER_RUN) == (23, 23, 46)
    assert (interp.MAX_FALSE_REJECTS, interp.MIN_CAUGHT) == (1, 19)
    assert int(2 / 42 * 23) == 1  # 1.09 rounded down
    assert -(-34 * 23 // 42) == 19  # 18.62 rounded up


def test_three_runs_at_the_threshold_pass():
    assert interp.evaluate([result(*[cells(1, 19)] * 3)])["passes"]


def test_one_more_false_reject_or_one_fewer_catch_fails():
    assert interp.evaluate([result(cells(2, 23))])["failed"]
    assert interp.evaluate([result(cells(0, 18))])["failed"]


def test_a_complete_failing_run_ends_the_gate_without_more_runs():
    verdict = interp.evaluate([result(cells(3, 20))])
    assert verdict["failed"] and not verdict["passes"]


def test_fewer_than_three_runs_is_open_not_a_pass():
    verdict = interp.evaluate([result(cells(0, 23), cells(0, 23))])
    assert not verdict["passes"] and not verdict["failed"]


def test_a_failed_call_on_a_correct_pair_is_a_false_reject():
    run = cells(0, 23)
    run[0]["faithful"] = None  # first cell is a correct reporting pair
    score = interp.score_run(run)
    assert score["total"]["false_rejects"] == 1 and score["total"]["errors"] == 1


def test_per_domain_counts_are_reported():
    score = interp.score_run(cells(0, 23))
    assert [score[d]["correct_pairs"] for d in interp.DOMAINS] == [10, 7, 6]


def test_an_incomplete_run_does_not_pass():
    verdict = interp.evaluate([result(*[cells(0, 23)[:-2]] * 3)])
    assert not verdict["passes"]


# ---------------------------------------------------------------- FR-03 gate


def routing_file(expected, predicted, *, set_name=None, run_at="1", size=None):
    rows = [
        {"id": f"i{n}", "expected": e, "predicted": p}
        for n, (e, p) in enumerate(zip(expected, predicted, strict=True))
    ]
    return {
        "seed_set": set_name,
        "run_at": run_at,
        "answered": len(rows) if size is None else size,
        "stopped_early": None,
        "rows": rows,
    }


FRESH_EXPECTED = ["ambiguous"] * 8 + ["reporting"] * 8


def fresh(amb_hits: int, non_amb_correct: int = 8, false_amb: int = 0):
    predicted = ["ambiguous"] * amb_hits + ["reporting"] * (8 - amb_hits)
    predicted += ["reporting"] * non_amb_correct + ["sentiment"] * (8 - non_amb_correct)
    for i in range(false_amb):
        predicted[8 + i] = "ambiguous"
    return routing_file(FRESH_EXPECTED, predicted)


def dev_files(correct_per_run: int):
    """Three runs of seed_v2 (31) and routing_v2 (18), with 44 non-ambiguous items between them."""
    files = []
    for run in range(3):
        for name, size, n_amb in (("seed_v2.jsonl", 31, 4), ("routing_v2.jsonl", 18, 1)):
            exp = ["ambiguous"] * n_amb + ["reporting"] * (size - n_amb)
            files.append((name, run, exp))
    out, budget = [], [correct_per_run] * 3
    for name, run, exp in files:
        n_non = sum(1 for e in exp if e != "ambiguous")
        take = min(n_non, budget[run])
        budget[run] -= take
        pred = ["ambiguous" if e == "ambiguous" else "x" for e in exp]
        k = 0
        for i, e in enumerate(exp):
            if e != "ambiguous" and k < take:
                pred[i] = "reporting"
                k += 1
        out.append(routing_file(exp, pred, set_name=name, run_at=str(run)))
    return out


def test_fr03_thresholds():
    assert fr03.C_NEEDED == 6 and fr03.ROUTE_V3_DEV_MEAN == 43.00


def test_fr03_pass_at_every_boundary():
    v6 = [fresh(6, 8, 0), fresh(6, 8, 1), fresh(6, 8, 0)]  # a: exactly 1 flagged
    v3 = [fresh(0, 8)] * 3
    verdict = fr03.evaluate(v6, v3, dev_files(42))
    assert verdict["a"]["pass"] and verdict["b1"]["pass"] and verdict["b2"]["pass"]
    assert verdict["c"]["recognised"] == 6 and verdict["passes"]


def test_fr03_each_criterion_can_fail():
    v3 = [fresh(0, 8)] * 3
    base = [fresh(8, 8)] * 3
    assert fr03.evaluate(base, v3, dev_files(44))["passes"]
    two_false = [fresh(8, 8, 1), fresh(8, 8, 1), fresh(8, 8)]
    assert not fr03.evaluate(two_false, v3, dev_files(44))["a"]["pass"]
    assert not fr03.evaluate(base, v3, dev_files(41))["b1"]["pass"]
    low = [fresh(8, 6)] * 3
    assert not fr03.evaluate(low, v3, dev_files(44))["b2"]["pass"]
    assert not fr03.evaluate([fresh(5, 8)] * 3, v3, dev_files(44))["c"]["pass"]


def test_fr03_part_run_counts_as_failed():
    part = routing_file(FRESH_EXPECTED[:10], ["ambiguous"] * 10, size=10)
    verdict = fr03.evaluate([part, fresh(8), fresh(8)], [fresh(0)] * 3, dev_files(44))
    assert not verdict["passes"] and verdict["notes"]


def test_fr03_c_reports_misses_by_id_and_needs_two_of_three_runs():
    v6 = [fresh(8), fresh(7), fresh(7)]  # item i7 recognised in 1 of 3 runs only
    verdict = fr03.evaluate(v6, [fresh(0)] * 3, dev_files(44))
    assert verdict["c"]["misses"] == ["i7"]
    assert verdict["c"]["recognised"] == 7 and verdict["c"]["pass"]


# ---------------------------------------------------------------- generated-set row mapping


def test_the_runner_maps_the_generated_row_format_without_changing_content():
    run_seed = load("evals/routing/run_seed.py", "run_seed_mod")
    row = {
        "uid": "ambiguous/AMB-01",
        "system_route": "ambiguous",
        "item": {
            "id": "AMB-01",
            "question": "q text",
            "category": "ambiguous",
            "candidate_areas": ["reporting", "sentiment"],
            "rationale": "never used",
        },
    }
    assert run_seed.map_generated(row) == {
        "id": "ambiguous/AMB-01",
        "question": "q text",
        "expected": "ambiguous",
        "tag": "ambiguous",
        "candidates": ["reporting", "sentiment"],
    }
    flat = {"id": "s01", "question": "q", "expected": "reporting", "tag": "clear"}
    assert run_seed.map_generated(flat) == flat
    assert run_seed.is_generated(ROOT / "evals" / "generated" / "sets" / "x.jsonl")
