"""Offline tests for the prompt v1 trial: spec counts, incident rules, prompt, violation checks."""

import importlib.util
import sys
from collections import Counter
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parents[2] / "data" / "generator" / "experiments"
sys.path.insert(0, str(_DIR))
_spec = importlib.util.spec_from_file_location("prompt_v1_trial", _DIR / "prompt_v1_trial.py")
v1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v1)


@pytest.fixture(scope="module")
def specs():
    return v1.build_specs()


def test_deterministic(specs):
    assert v1.build_specs() == specs
    assert v1.build_specs(seed=1) != specs


def test_mix(specs):
    assert len(specs) == 80
    assert Counter((s["style"], s["sentiment"]) for s in specs) == Counter(v1.SPEC_MIX)
    neutral = [s for s in specs if s["sentiment"] == "neutral"]
    assert Counter(s["style"] for s in neutral) == {"plain": 10, "implicit": 10}


def test_incidents(specs):
    inc = [s for s in specs if s["incident_type"]]
    assert len(inc) == 32
    assert Counter(s["incident_severity"] for s in inc) == {"serious": 16, "minor": 16}
    neutral_inc = [s for s in inc if s["sentiment"] == "neutral"]
    assert len(neutral_inc) == 8
    assert all(s["incident_severity"] == "minor" for s in neutral_inc)
    assert not {s["incident_type"] for s in neutral_inc} & v1.NEUTRAL_EXCLUDED_INCIDENTS
    serious_pn = [
        s for s in inc if s["incident_severity"] == "serious" and s["sentiment"] == "positive"
    ]
    assert len(serious_pn) >= 8
    assert all(s["service_type"] is None for s in inc)


def test_focus_opening_and_prompt(specs):
    assert all(s["focus"] in v1.FOCUSES and s["opening"] in v1.OPENINGS for s in specs)
    p = v1.render_prompt(specs[:20])
    assert "{numbered spec lines}" not in p
    assert "; focus: " in p and "; opening: " in p
    assert "Never start with 'The technician'." in p


def test_judge_prompt_is_text_only(specs):
    p = v1.render_judge_prompt([(1, "fine\nvisit"), (2, "ok")])
    assert "1. fine visit" in p and "2. ok" in p
    assert "sarcastic" not in p and "implicit" not in p


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("Paid $300 for this.", "money"),
        ("He showed up at 9:30.", "time"),
        ("came at 10am", "time"),
        ("Booked for March 4 and nobody came.", "date"),
        ("Came back Tuesday.", "date"),
        ("Thanks to Dave for the help.", "name_like"),
    ],
)
def test_rule_violations_detect(text, kind):
    counts = v1.rule_violations([{"id": 1, "text": text}])["counts"]
    assert counts[kind] == 1


def test_rule_violations_clean():
    text = "Switch swapped. Wi-Fi is stable now. Is the UPS covered? Ethernet runs look tidy."
    assert sum(v1.rule_violations([{"id": 1, "text": text}])["counts"].values()) == 0


def test_parse_label_field():
    import model_bakeoff as v0

    r = v0.parse_response('[{"id": 1, "label": "Mixed"}]', [1], field="label")
    assert r["ok"] and r["comments"] == {1: "Mixed"}
