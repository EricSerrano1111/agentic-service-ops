"""Offline tests for the corpus model bake-off: spec determinism/counts and response parsing."""

import importlib.util
from collections import Counter
from pathlib import Path

import pytest

_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "generator" / "experiments" / "model_bakeoff.py"
)
_spec = importlib.util.spec_from_file_location("model_bakeoff", _PATH)
bakeoff = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bakeoff)


@pytest.fixture(scope="module")
def specs():
    return bakeoff.build_specs()


def test_specs_deterministic_for_seed(specs):
    assert bakeoff.build_specs() == specs
    assert bakeoff.build_specs(seed=1) != specs


def test_spec_style_sentiment_counts(specs):
    assert len(specs) == 100
    assert [s["id"] for s in specs] == list(range(1, 101))
    mix = Counter((s["style"], s["sentiment"]) for s in specs)
    assert mix == Counter(bakeoff.SPEC_MIX)
    styles = Counter(s["style"] for s in specs)
    assert styles == {"plain": 40, "sarcastic": 30, "implicit": 30}


def test_spec_incidents(specs):
    incident = [s for s in specs if s["incident_type"]]
    assert len(incident) == 40
    assert Counter(s["incident_severity"] for s in incident) == {"minor": 20, "serious": 20}
    serious_pn = [
        s
        for s in incident
        if s["incident_severity"] == "serious" and s["sentiment"] in ("positive", "neutral")
    ]
    assert len(serious_pn) >= 8
    assert all(s["service_type"] is None for s in incident)
    assert all(s["incident_type"] in bakeoff.INCIDENT_PHRASES for s in incident)


def test_spec_service_channel_writer(specs):
    clean = [s for s in specs if not s["incident_type"]]
    assert Counter(s["service_type"] for s in clean) == {t: 12 for t in bakeoff.SERVICE_TYPES}
    for s in specs:
        assert (s["min_words"], s["max_words"]) == bakeoff.CHANNEL_BANDS[s["channel"]]
        assert s["writer"] in bakeoff.WRITERS


def test_batches_and_prompt(specs):
    bs = bakeoff.batches(specs)
    assert [len(b) for b in bs] == [20] * 5
    prompt = bakeoff.render_prompt(bs[0])
    assert "{numbered spec lines}" not in prompt
    assert prompt.count("\n1. sentiment:") == 1


IDS = [1, 2, 3]
VALID = '[{"id": 1, "text": "a"}, {"id": 2, "text": "b"}, {"id": 3, "text": "c"}]'


def test_parse_valid_json():
    r = bakeoff.parse_response(VALID, IDS)
    assert r["ok"] and r["comments"] == {1: "a", 2: "b", 3: "c"}
    assert r["missing_ids"] == r["extra_ids"] == r["duplicate_ids"] == []


@pytest.mark.parametrize(
    "wrapped",
    [f"```json\n{VALID}\n```", f"```\n{VALID}\n```", f"Here you go:\n{VALID}\nDone."],
)
def test_parse_fenced_or_embedded_json(wrapped):
    r = bakeoff.parse_response(wrapped, IDS)
    assert r["ok"] and len(r["comments"]) == 3


def test_parse_count_mismatch():
    text = '[{"id": 1, "text": "a"}, {"id": 1, "text": "dup"}, {"id": 9, "text": "x"}]'
    r = bakeoff.parse_response(text, IDS)
    assert r["ok"]
    assert r["comments"] == {1: "a"}
    assert r["missing_ids"] == [2, 3]
    assert r["extra_ids"] == [9]
    assert r["duplicate_ids"] == [1]


@pytest.mark.parametrize("bad", [None, "", "not json at all", '{"id": 1, "text": "a"}'])
def test_parse_failure_reported_not_raised(bad):
    r = bakeoff.parse_response(bad, IDS)
    assert not r["ok"] and r["missing_ids"] == IDS and r["error"]
