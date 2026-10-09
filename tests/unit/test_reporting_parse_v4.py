"""The parse_v4 eval set, its scoring and the pre-registered gate (ADR-086). Offline: nothing
here calls a model."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pytest
from schemas import ReportingRequest

EVALS = Path(__file__).resolve().parents[2] / "evals" / "reporting_parse"
PROMPTS = Path(__file__).resolve().parents[2] / "services" / "agent_reporting" / "prompts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"parse_eval_{name}", EVALS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gate = _load("gate")
run = _load("run")


def items(name: str) -> list[dict]:
    text = (EVALS / f"{name}.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line]


# ------------------------------------------------------------------------------ the set


def test_parse_v4_is_the_16_old_items_unchanged_plus_12_new_ones():
    old_lines = (EVALS / "parse_v3.jsonl").read_text(encoding="utf-8").splitlines()
    new_lines = (EVALS / "parse_v4.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(old_lines) == 16 and len(new_lines) == 28
    assert new_lines[:16] == old_lines  # byte for byte: the labels never change
    assert [i["id"] for i in items("parse_v4")[16:]] == [f"f{n:02d}" for n in range(1, 13)]


def test_the_new_items_cover_the_pre_registered_mix():
    new = items("parse_v4")[16:]
    counts = Counter(i["category"] for i in new)
    assert counts["region"] == 4
    assert counts["account"] + counts["account_ambiguous"] + counts["account_no_match"] == 4
    assert counts["account_ambiguous"] == 1 and counts["account_no_match"] == 1
    assert counts["combined"] == 2 and counts["unsupported_area"] == 2
    unsupported = [i for i in new if i["category"] == "unsupported_area"]
    assert all(i["expected"]["region"] == "unsupported" for i in unsupported)
    assert {i["id"] for i in unsupported} == set(gate.UNSUPPORTED_IDS)


def test_every_label_is_a_valid_reporting_request():
    for item in items("parse_v4"):
        expected = item["expected"]
        ReportingRequest.model_validate(expected | {})  # extra="forbid": unknown keys fail
        assert set(expected) <= set(run.FIELDS) | set(), item["id"]


def test_no_prompt_example_is_an_eval_question():
    """The parse_v4 prompt's examples must not be eval items (contamination)."""
    prompt = (PROMPTS / "parse_v4.md").read_text(encoding="utf-8")
    quoted = set(re.findall(r'"([^"\n]{12,})"', prompt))
    for item in items("parse_v4"):
        assert item["question"] not in quoted, item["id"]
    for needle in ("Texas", "Midwest", "Cedar Ridge", "Meridian Foods", "Silver Creek", "Summit"):
        assert needle not in prompt, needle


def test_parse_v4_template_keys_follow_the_schema_property_order_exactly():
    """L-51: the template and the schema agree, region and account_name before the dates."""
    template = next(
        line
        for line in (PROMPTS / "parse_v4.md").read_text(encoding="utf-8").splitlines()
        if line.startswith('{"metric"')
    )
    keys = re.findall(r'"(\w+)":', template)
    assert keys == list(ReportingRequest.model_json_schema()["properties"])
    assert keys[-2:] == ["start", "end"]


def test_parse_v3_is_still_in_the_repo_unchanged_in_its_template():
    template = next(
        line
        for line in (PROMPTS / "parse_v3.md").read_text(encoding="utf-8").splitlines()
        if line.startswith('{"metric"')
    )
    assert "region" not in template and "account_name" not in template


# ------------------------------------------------------------------------------ scoring


def test_account_names_compare_like_technician_names():
    assert run.same("account_name", "  cedar   RIDGE retail ", "Cedar Ridge Retail")
    assert not run.same("account_name", "Cedar Ridge", "Cedar Ridge Retail")
    assert not run.same("account_name", None, "Cedar Ridge Retail")
    assert run.same("account_name", None, None)
    assert run.same("region", "west", "west") and not run.same("region", "West", "west")


# ------------------------------------------------------------------------------ the gate


def _row(item_id, exact=True, region=None):
    return {
        "id": item_id,
        "exact": exact,
        "got": {"region": region},
        "fields": {"region": True},
    }


def _result(prompt, runs, expected_ids):
    return {"prompt": prompt, "expected": dict.fromkeys(expected_ids, {}), "runs": runs}


OLD = [f"o{n:02d}" for n in range(16)]


def _baseline(correct_per_run):
    runs = [[_row(i, exact=n < k) for n, i in enumerate(OLD)] for k in correct_per_run]
    return _result("parse_v3", runs, OLD)


def _candidate(old_correct, new_correct, unsupported_ok=(True, True)):
    runs = []
    for k_old, k_new, ok in zip(old_correct, new_correct, [unsupported_ok] * 3, strict=False):
        rows = [_row(i, exact=n < k_old) for n, i in enumerate(OLD)]
        for n, i in enumerate(gate.NEW_IDS):
            region = None
            if i in gate.UNSUPPORTED_IDS:
                region = "unsupported" if ok[gate.UNSUPPORTED_IDS.index(i)] else "west"
            rows.append(_row(i, exact=n < k_new, region=region))
        runs.append(rows)
    return _result("parse_v4", runs, OLD + gate.NEW_IDS)


def test_the_gate_passes_when_all_three_criteria_hold():
    verdict = gate.evaluate(_baseline([15, 15, 15]), _candidate([15, 14, 15], [10, 11, 12]))
    assert verdict["passes"] and verdict["candidate_old_mean"] == pytest.approx(14.667, abs=1e-3)


def test_criterion_a_allows_one_below_the_baseline_mean_and_no_more():
    base = _baseline([15, 15, 15])
    assert gate.evaluate(base, _candidate([14, 14, 14], [12] * 3))["a_old_items_hold"]
    assert not gate.evaluate(base, _candidate([14, 14, 13], [12] * 3))["a_old_items_hold"]


def test_criterion_b_needs_ten_of_twelve_in_every_run():
    base = _baseline([15, 15, 15])
    assert gate.evaluate(base, _candidate([15] * 3, [10, 10, 10]))["b_new_items_10_of_12_every_run"]
    assert not gate.evaluate(base, _candidate([15] * 3, [12, 12, 9]))[
        "b_new_items_10_of_12_every_run"
    ]


def test_criterion_c_fails_if_an_unsupported_area_is_ever_mapped():
    base = _baseline([15, 15, 15])
    verdict = gate.evaluate(base, _candidate([15] * 3, [12] * 3, unsupported_ok=(True, False)))
    assert not verdict["c_unsupported_never_mapped"] and not verdict["passes"]


def test_the_gate_constants_are_the_pre_registered_ones():
    assert gate.MIN_NEW_PER_RUN == 10 and gate.TOLERANCE == 1.0
    assert gate.UNSUPPORTED_IDS == ["f11", "f12"]
