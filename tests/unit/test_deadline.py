"""The request deadline (ADR-088): setting, propagating, clamping, and never trusting it."""

from __future__ import annotations

import math

import pytest
from common import (
    DEADLINE_KEY,
    REQUEST_BUDGET_S,
    RESERVE_S,
    Deadline,
    DeadlineExceeded,
)

NOW = 1_800_000_000.0  # an arbitrary epoch second


def test_a_request_gets_120_seconds_from_its_arrival():
    d = Deadline.start(NOW)
    assert d.at_ms == int((NOW + 120) * 1000) and REQUEST_BUDGET_S == 120.0
    assert d.remaining_s(NOW) == pytest.approx(120.0)
    assert d.remaining_s(NOW + 30) == pytest.approx(90.0)


def test_it_travels_as_absolute_epoch_milliseconds_in_metadata():
    d = Deadline.start(NOW)
    assert d.as_metadata() == {DEADLINE_KEY: d.at_ms} and DEADLINE_KEY == "deadline_ms"
    received = Deadline.from_metadata(d.as_metadata(), NOW + 1)
    assert received.at_ms == d.at_ms and received.origin == "metadata"


def test_a_protobuf_float_is_accepted():
    d = Deadline.start(NOW)
    assert Deadline.from_metadata({DEADLINE_KEY: float(d.at_ms)}, NOW).at_ms == d.at_ms


# ------------------------------------------------------------------ the hop timeout


def test_a_hop_gets_the_smaller_of_its_cap_and_the_time_left_minus_the_reserve():
    d = Deadline.start(NOW)
    assert d.hop_timeout(30.0, NOW) == 30.0  # plenty of time: the cap rules
    assert d.hop_timeout(200.0, NOW) == pytest.approx(120.0 - RESERVE_S)  # the deadline rules
    assert d.hop_timeout(60.0, NOW + 100) == pytest.approx(20.0 - RESERVE_S)  # clamped hop
    assert RESERVE_S == 5.0


def test_a_hop_with_no_usable_time_raises():
    d = Deadline.start(NOW)
    with pytest.raises(DeadlineExceeded):
        d.hop_timeout(30.0, NOW + 115)  # exactly the reserve left
    with pytest.raises(DeadlineExceeded):
        d.hop_timeout(30.0, NOW + 130)  # already past
    assert d.expired(NOW + 115) and not d.expired(NOW + 114)


# ------------------------------------------------------------------ never trusted


@pytest.mark.parametrize(
    ("raw", "origin"),
    [
        (None, "missing"),
        ("1800000120000", "malformed"),  # a string
        (True, "malformed"),  # a bool is an int in Python
        (False, "malformed"),
        ([1], "malformed"),
        ({"x": 1}, "malformed"),
        (0, "malformed"),
        (-5, "malformed"),
        (-1.5e12, "malformed"),
        (math.nan, "malformed"),
        (math.inf, "malformed"),
        (-math.inf, "malformed"),
    ],
)
def test_a_missing_or_malformed_deadline_is_replaced_by_the_receivers_default(raw, origin):
    metadata = {} if raw is None else {DEADLINE_KEY: raw}
    d = Deadline.from_metadata(metadata, NOW)
    assert d.origin == origin
    assert d.at_ms == Deadline.start(NOW).at_ms  # now + 120 s, not the sender's value


def test_no_metadata_at_all_is_the_default_too():
    assert Deadline.from_metadata(None, NOW).origin == "missing"


def test_an_absurdly_far_deadline_is_clamped_to_the_budget():
    far = {DEADLINE_KEY: (NOW + 86_400 * 365) * 1000}
    d = Deadline.from_metadata(far, NOW)
    assert d.origin == "clamped" and d.at_ms == Deadline.start(NOW).at_ms
    just_over = Deadline.from_metadata({DEADLINE_KEY: (NOW + 121) * 1000}, NOW)
    assert just_over.origin == "clamped" and just_over.remaining_s(NOW) == pytest.approx(120.0)


def test_a_deadline_already_in_the_past_is_kept_and_expired():
    d = Deadline.from_metadata({DEADLINE_KEY: (NOW - 10) * 1000}, NOW)
    assert d.origin == "metadata" and d.expired(NOW)
    with pytest.raises(DeadlineExceeded):
        d.hop_timeout(30.0, NOW)


def test_a_deadline_within_the_budget_is_kept_as_sent():
    d = Deadline.from_metadata({DEADLINE_KEY: (NOW + 40) * 1000}, NOW)
    assert d.origin == "metadata" and d.remaining_s(NOW) == pytest.approx(40.0)
