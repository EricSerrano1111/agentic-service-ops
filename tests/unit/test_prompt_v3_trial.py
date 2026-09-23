"""Offline tests for the prompt v3 trial: spec plan, the five spec rules, and prompt edits."""

import importlib.util
import sys
from collections import Counter
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parents[2] / "data" / "generator" / "experiments"
sys.path.insert(0, str(_DIR))
_spec = importlib.util.spec_from_file_location("prompt_v3_trial", _DIR / "prompt_v3_trial.py")
v3 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v3)


@pytest.fixture(scope="module")
def specs():
    return v3.build_specs()


def test_deterministic(specs):
    assert v3.build_specs() == specs
    assert v3.build_specs(seed=1) != specs


def test_groups_and_counts(specs):
    assert len(specs) == 60
    assert Counter(s["group"] for s in specs) == {
        "neutral": 20,
        "positive_serious": 10,
        "mixed_incident": 8,
        "distractor": 22,
    }
    assert Counter(s["neutral_kind"] for s in specs if s["neutral_kind"]) == v3.NEUTRAL_KINDS
    ps = [s for s in specs if s["group"] == "positive_serious"]
    assert all(s["incident_severity"] == "serious" for s in ps)
    assert Counter(s["style"] for s in ps) == {"plain": 6, "implicit": 4}
    mi = [s for s in specs if s["group"] == "mixed_incident"]
    assert all(s["incident_severity"] == "minor" and s["style"] == "plain" for s in mi)
    d = [s for s in specs if s["group"] == "distractor"]
    assert Counter((s["sentiment"], s["style"]) for s in d) == {
        ("positive", "plain"): 6,
        ("positive", "implicit"): 4,
        ("negative", "plain"): 2,
        ("negative", "implicit"): 2,
        ("negative", "sarcastic"): 4,
        ("mixed", "plain"): 4,
    }
    assert sum(bool(s["incident_type"]) for s in d if s["sentiment"] == "negative") == 4
    assert all(not s["incident_type"] for s in d if s["sentiment"] != "negative")


def test_neutral_rule(specs):
    for s in specs:
        if s["sentiment"] == "neutral":
            assert s["style"] == "plain" and s["incident_type"] is None


def test_mixed_rule(specs):
    for s in specs:
        if s["sentiment"] == "mixed":
            assert s["style"] == "plain" and s["incident_severity"] in (None, "minor")


def test_sarcastic_and_implicit_rules(specs):
    for s in specs:
        if s["style"] == "sarcastic":
            assert s["sentiment"] == "negative"
        if s["style"] == "implicit":
            assert s["sentiment"] in ("positive", "negative")


def test_question_opening_rule(specs):
    for s in specs:
        if s["opening"] == "question":
            assert s["sentiment"] == "negative" or s["neutral_kind"] == "administrative"


def test_all_rules_hold_across_seeds():
    for seed in range(50):
        for s in v3.build_specs(seed=seed):
            assert v3.check_spec_rules(s) == []


@pytest.mark.parametrize(
    "patch",
    [
        {"sentiment": "neutral", "style": "implicit"},
        {"sentiment": "neutral", "incident_type": "missed_sla", "incident_severity": "minor"},
        {"sentiment": "mixed", "incident_type": "missed_sla", "incident_severity": "serious"},
        {"sentiment": "mixed", "style": "sarcastic"},
        {"sentiment": "mixed", "style": "plain", "opening": "question"},
        {"sentiment": "positive", "style": "sarcastic"},
        {
            "sentiment": "neutral",
            "style": "plain",
            "neutral_kind": "minimal",
            "opening": "question",
        },
    ],
)
def test_check_spec_rules_rejects(patch):
    base = {
        "sentiment": "negative",
        "style": "plain",
        "incident_type": None,
        "incident_severity": None,
        "opening": "outcome first",
        "neutral_kind": None,
    }
    assert v3.check_spec_rules({**base, **patch})


def test_minimal_band_overrides_channel(specs):
    for s in specs:
        if s["neutral_kind"] == "minimal":
            assert (s["min_words"], s["max_words"]) == v3.MINIMAL_BAND
        else:
            assert (s["min_words"], s["max_words"]) == v3.v0.CHANNEL_BANDS[s["channel"]]


def test_prompt_edits():
    assert v3.MIXED_V3 in v3.PROMPT_V3 and v3.MIXED_V3 in v3.JUDGE_PROMPT_V3
    assert v3.MIXED_V2 not in v3.PROMPT_V3 and v3.MIXED_V2 not in v3.JUDGE_PROMPT_V3
    assert v3.LABEL_DEFINITIONS in v3.PROMPT_V3 and v3.LABEL_DEFINITIONS in v3.JUDGE_PROMPT_V3
    assert "handled well" not in v3.PROMPT_V3
    assert '"/s"' in v3.PROMPT_V3 and "No greetings or sign-offs" in v3.PROMPT_V3


def test_spec_line_notes(specs):
    for s in specs:
        line = v3.spec_line(s)
        assert (v3.ADMIN_NOTE in line) == (s["neutral_kind"] == "administrative")
        pos_inc = s["sentiment"] == "positive" and bool(s["incident_type"])
        assert (v3.POSITIVE_INCIDENT_NOTE in line) == pos_inc


def test_review_selection(specs):
    ids = v3.select_review_ids(specs, {s["id"] for s in specs}, seed=1)
    by = {s["id"]: s for s in specs}
    assert len(set(ids)) == 24
    assert Counter(by[i]["group"] for i in ids) == {
        "neutral": 10,
        "positive_serious": 6,
        "mixed_incident": 4,
        "distractor": 4,
    }
