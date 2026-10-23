"""The answer journey through the gateway (data dictionary section 6 rule 10): passed through
unchanged apart from the gateway's own `forward` hop, and changing no displayed answer field."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from api_gateway.interpret import journey_view, view
from gateway_testkit import Kit, answered

JOURNEY = {
    "hops": [
        {
            "service": "orchestrator",
            "step": "route",
            "attempt": 1,
            "start_ms": 0.0,
            "duration_ms": 410.2,
            "status": "ok",
        },
        {
            "service": "qa",
            "step": "figures_check",
            "attempt": 1,
            "start_ms": 900.0,
            "duration_ms": 30.0,
            "status": "ok",
        },
    ],
    "qa": {
        "verdict": "pass",
        "checks": [{"code": "figures_match_database", "class": "figures", "passed": True}],
        "interpretation": "faithful",
        "mode": "advisory",
    },
    "model_calls": 3,
    "cost_usd": 0.0012,
}
FIXTURE = Path(__file__).parent / "fixtures" / "view_before_journey.json"
RECORDED = Path(__file__).parents[3] / "evals/results/golden_v2/2026-10-13/run1.json"


@pytest.fixture
def kit(tmp_path) -> Kit:
    return Kit(tmp_path)


def test_the_journey_is_passed_through_with_the_gateways_forward_hop_first(kit):
    kit.upstream.body = answered() | {"journey": JOURNEY}
    kit.sign_in()
    body = kit.ask().json()
    j = body["journey"]
    forward, *rest = j["hops"]
    assert forward["service"] == "gateway" and forward["step"] == "forward"
    assert forward["attempt"] == 1 and forward["start_ms"] == 0 and forward["status"] == "ok"
    assert forward["duration_ms"] >= 0
    assert rest == JOURNEY["hops"]  # the orchestrator's hops, unchanged
    assert {k: v for k, v in j.items() if k != "hops"} == {
        k: v for k, v in JOURNEY.items() if k != "hops"
    }


def test_no_journey_from_the_orchestrator_means_none(kit):
    kit.sign_in()
    assert kit.ask().json()["journey"] is None  # an older orchestrator: the UI hides the button


@pytest.mark.parametrize("bad", ["x", 3, [], {"hops": "no"}, {"model_calls": 1}])
def test_a_journey_that_is_not_the_expected_shape_is_dropped(bad):
    assert journey_view({"journey": bad}, 5.0) is None


def test_the_view_does_not_alter_the_original_journey():
    body = {"journey": json.loads(json.dumps(JOURNEY))}
    journey_view(body, 12.3)
    assert body["journey"] == JOURNEY


@pytest.mark.skipif(
    not RECORDED.exists(), reason="the recorded golden_v2 run is not in this checkout"
)
def test_the_displayed_fields_of_the_recorded_responses_are_byte_identical():
    """The journey is telemetry: for the recorded responses used in PR #85 (G11, a headline
    answer; G16, a clarification) every field the view carried before is unchanged. The fixture
    holds the view produced by the code before the journey existed."""
    before = json.loads(FIXTURE.read_text(encoding="utf-8"))
    rows = {r["id"]: r for r in json.loads(RECORDED.read_text(encoding="utf-8"))["rows"]}
    for rid, expected in before.items():
        after = view(rows[rid]["question"], rows[rid]["response"], forward_ms=7.0)
        assert after.pop("journey") is None  # recorded before the journey existed
        assert json.dumps(after, sort_keys=True) == json.dumps(expected, sort_keys=True), rid
    assert before["G11"]["headline"] is not None  # the headline is among what was compared
