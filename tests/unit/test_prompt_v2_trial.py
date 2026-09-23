"""Offline tests for the prompt v2 trial: spec plan, style/incident rules, prompts, greetings."""

import importlib.util
import sys
from collections import Counter
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parents[2] / "data" / "generator" / "experiments"
sys.path.insert(0, str(_DIR))
_spec = importlib.util.spec_from_file_location("prompt_v2_trial", _DIR / "prompt_v2_trial.py")
v2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v2)


@pytest.fixture(scope="module")
def specs():
    return v2.build_specs()


def test_deterministic(specs):
    assert v2.build_specs() == specs
    assert v2.build_specs(seed=1) != specs


def test_groups(specs):
    assert len(specs) == 60
    assert Counter(s["group"] for s in specs) == {
        "neutral": 20,
        "positive_serious": 10,
        "mixed_incident": 8,
        "distractor": 22,
    }


def test_neutral_rules(specs):
    neutral = [s for s in specs if s["sentiment"] == "neutral"]
    assert len(neutral) == 20
    assert all(s["style"] == "plain" and s["incident_type"] is None for s in neutral)
    assert Counter(s["neutral_kind"] for s in neutral) == v2.NEUTRAL_KINDS
    assert all(s["neutral_kind"] is None for s in specs if s["sentiment"] != "neutral")


def test_style_sentiment_rules(specs):
    for s in specs:
        if s["style"] == "implicit":
            assert s["sentiment"] in ("positive", "negative")
        if s["style"] == "sarcastic":
            assert s["sentiment"] in ("negative", "mixed")


def test_target_incidents(specs):
    ps = [s for s in specs if s["group"] == "positive_serious"]
    assert all(s["incident_severity"] == "serious" for s in ps)
    assert Counter(s["style"] for s in ps) == {"plain": 6, "implicit": 4}
    mi = [s for s in specs if s["group"] == "mixed_incident"]
    assert Counter(s["incident_severity"] for s in mi) == {"minor": 4, "serious": 4}
    assert Counter(s["style"] for s in mi) == {"plain": 6, "sarcastic": 2}


def test_distractors(specs):
    d = [s for s in specs if s["group"] == "distractor"]
    assert Counter(s["sentiment"] for s in d) == {"positive": 10, "negative": 8, "mixed": 4}
    neg = [s for s in d if s["sentiment"] == "negative"]
    assert sum(bool(s["incident_type"]) for s in neg) == 4
    assert Counter(s["style"] for s in neg) == {"plain": 4, "implicit": 2, "sarcastic": 2}
    assert all(not s["incident_type"] for s in d if s["sentiment"] != "negative")


def test_openings_and_prompt_lines(specs):
    assert all(s["opening"] in v2.OPENINGS for s in specs)
    assert "addressed to the company" not in v2.OPENINGS
    for s in specs:
        line = v2.spec_line(s)
        assert ("neutral kind:" in line) == (s["sentiment"] == "neutral")
        has_note = s["sentiment"] == "positive" and bool(s["incident_type"])
        assert (v2.POSITIVE_INCIDENT_NOTE in line) == has_note
    p = v2.render_prompt(specs[:20])
    assert "{numbered spec lines}" not in p and "{{" not in p


def test_definitions_shared_verbatim():
    assert v2.LABEL_DEFINITIONS in v2.PROMPT_V2
    assert v2.LABEL_DEFINITIONS in v2.JUDGE_PROMPT_V2
    assert '"/s"' in v2.PROMPT_V2 and "Deadpan" in v2.PROMPT_V2


@pytest.mark.parametrize(
    ("text", "hit"),
    [
        ("To whom it may concern, the switch works.", True),
        ("Hi team, all done.", True),
        ("Router swapped. Thanks, Dana", True),
        ("Router swapped. Thanks!", True),
        ("Thanks for the quick fix on the router.", False),
        ("fine", False),
        ("Where do we send the invoice?", False),
    ],
)
def test_greeting_or_signoff(text, hit):
    assert v2.greeting_or_signoff(text) is hit


def test_review_selection(specs):
    ids = v2.select_review_ids(specs, {s["id"] for s in specs}, seed=1)
    assert len(ids) == 24 and len(set(ids)) == 24
    by = {s["id"]: s for s in specs}
    assert Counter(by[i]["group"] for i in ids) == {
        "neutral": 10,
        "positive_serious": 6,
        "mixed_incident": 4,
        "distractor": 4,
    }
