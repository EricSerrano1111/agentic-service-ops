"""ADR-114 P1's scorer: it reproduces ADR-101's figures from the committed `route_v6` `minimal`
runs, and applies G1 to G5 as written. Counts and IDs only. No model is called."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "fr03_p1_score_under_test", ROOT / "evals" / "fr03_v3" / "p1_score.py"
)
sc = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = sc
spec.loader.exec_module(sc)

AMBIGUOUS_PER_SET = {
    "seed_v2.jsonl": 4,
    "routing_v2.jsonl": 1,
    "fr03_fresh_v2.jsonl": 8,
    "routing_heldout_v1.jsonl": 7,
}


def test_it_reproduces_adr_101s_fresh_and_development_figures():
    v = sc.validate()
    assert (v["c1_files"], v["a1_files"]) == (3, 6)
    fresh = v["fresh_recognised"]
    assert (fresh["count"], fresh["of"]) == (4, 8)
    assert fresh["missed_3_of_3_ids"] == [f"ambiguous/AMB-{n}" for n in ("08", "11", "17", "18")]
    assert v["fresh_flagged_item_runs"] == 0
    assert v["fresh_non_ambiguous_correct"] == [7, 7, 7]
    assert v["dev_non_ambiguous_correct"] == [43, 43, 43]


# ---------------------------------------------------------------- synthetic runs


def make_run(name, run_at, rows):
    return {
        "seed_set": name,
        "run_at": run_at,
        "answered": sc.SET_SIZES[name],
        "stopped_early": None,
        "rows": rows,
    }


def rows_for(name, *, amb_hit, nonamb_flagged=0, nonamb_wrong=0):
    """A run of `name`: ambiguous items return `ambiguous` if amb_hit(id); the first
    `nonamb_flagged` non-ambiguous items are routed `ambiguous`, the next `nonamb_wrong` wrong."""
    n_amb = AMBIGUOUS_PER_SET[name]
    rows = []
    for i in range(sc.SET_SIZES[name]):
        if i < n_amb:
            iid = f"{name}:A{i}"
            predicted = "ambiguous" if amb_hit(iid) else "reporting"
            rows.append({"id": iid, "expected": "ambiguous", "predicted": predicted})
        else:
            j = i - n_amb
            pred = "ambiguous" if j < nonamb_flagged else "reporting"
            if nonamb_flagged <= j < nonamb_flagged + nonamb_wrong:
                pred = "sentiment"
            rows.append({"id": f"{name}:N{j}", "expected": "reporting", "predicted": pred})
    return rows


def level_files(*, amb_hit=lambda i: True, flagged=0, wrong_v2=0):
    files = []
    for rep in range(3):
        for name in sc.SET_SIZES:
            rows = rows_for(
                name,
                amb_hit=amb_hit,
                nonamb_flagged=flagged if name == "routing_heldout_v1.jsonl" else 0,
                nonamb_wrong=wrong_v2 if name == "seed_v2.jsonl" else 0,
            )
            files.append(make_run(name, f"2026102{rep}", rows))
    return files


GOOD_CALLS = [{"latency_s": 2.0, "cost_usd": 0.001, "thinking_tokens": 300}] * 10
BASE = {"count": 8}


def test_a_level_meeting_every_criterion_passes():
    s = sc.score_level(level_files(), GOOD_CALLS, BASE)
    assert s["complete"] and s["pass"] and s["failed"] == []
    assert s["criteria"]["G1"]["count"] == 15 and s["criteria"]["G2"]["gain"] == 7
    assert s["criteria"]["G4"]["counts"] == [44, 44, 44]


def test_g1_needs_eleven_of_fifteen():
    def missing(n):
        def hit(iid):
            return not (iid.startswith("fr03_fresh_v2") and int(iid.rsplit("A", 1)[1]) < n)

        return hit

    s = sc.score_level(level_files(amb_hit=missing(4)), GOOD_CALLS, {"count": 0})
    assert s["criteria"]["G1"]["count"] == 11 and s["criteria"]["G1"]["pass"]
    assert len(s["discriminating_missed_3_of_3_ids"]) == 4
    s = sc.score_level(level_files(amb_hit=missing(5)), GOOD_CALLS, {"count": 0})
    assert s["criteria"]["G1"]["count"] == 10 and "G1" in s["failed"]


def test_g1_counts_an_item_recognised_in_exactly_two_of_three_runs():
    files = level_files()
    first = files[2]  # the first run (rep 0) of fr03_fresh_v2
    assert first["seed_set"] == "fr03_fresh_v2.jsonl"
    for r in first["rows"]:
        if r["expected"] == "ambiguous":
            r["predicted"] = "reporting"
    assert sc.score_level(files, GOOD_CALLS, BASE)["criteria"]["G1"]["count"] == 15


def test_g2_is_the_gain_over_the_minimal_baseline():
    s = sc.score_level(level_files(), GOOD_CALLS, {"count": 13})
    assert s["criteria"]["G2"]["gain"] == 2 and "G2" in s["failed"]
    assert sc.score_level(level_files(), GOOD_CALLS, {"count": 12})["criteria"]["G2"]["pass"]


def test_g3_allows_eleven_of_285_and_no_more():
    # flagging k heldout non-ambiguous items in every run flags 3k item-runs
    nine = sc.score_level(level_files(flagged=3), GOOD_CALLS, BASE)
    assert nine["criteria"]["G3"]["item_runs"] == 9 and nine["criteria"]["G3"]["pass"]
    s = sc.score_level(level_files(flagged=4), GOOD_CALLS, BASE)
    assert s["criteria"]["G3"]["item_runs"] == 12 and "G3" in s["failed"]
    assert len(s["flagged_in_2plus_runs_ids"]) == 4


def test_g4_floor_is_42_and_counts_a_failed_call_as_wrong():
    assert sc.score_level(level_files(wrong_v2=1), GOOD_CALLS, BASE)["criteria"]["G4"]["pass"]
    s = sc.score_level(level_files(wrong_v2=3), GOOD_CALLS, BASE)
    assert s["criteria"]["G4"]["mean"] == 41.0 and "G4" in s["failed"]
    files = level_files()
    for r in files[0]["rows"]:  # a failed call has no route
        r["predicted"] = None
    assert sc.score_level(files, GOOD_CALLS, BASE)["criteria"]["G4"]["counts"][0] < 44


def test_g5_latency_and_cost_ceilings():
    def calls(latency, cost):
        return [{"latency_s": latency, "cost_usd": cost, "thinking_tokens": 1}] * 10

    assert "G5" in sc.score_level(level_files(), calls(11.0, 0.001), BASE)["failed"]
    assert "G5" in sc.score_level(level_files(), calls(1.0, 0.0031), BASE)["failed"]
    assert "G5" in sc.score_level(level_files(), calls(5.5, 0.001), BASE)["failed"]
    assert sc.score_level(level_files(), calls(5.0, 0.003), BASE)["criteria"]["G5"]["pass"]


def test_an_incomplete_level_cannot_pass():
    s = sc.score_level(level_files()[:-1], GOOD_CALLS, BASE)
    assert not s["complete"] and not s["pass"] and s["notes"]


def test_v2_ambiguous_items_are_reported_not_counted():
    s = sc.score_level(level_files(), GOOD_CALLS, BASE)
    assert s["v2_ambiguous_reported_not_counted"]["of"] == 5
    assert s["criteria"]["G1"]["of"] == 15
