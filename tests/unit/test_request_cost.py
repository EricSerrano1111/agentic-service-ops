"""Per-request cost accounting (ADR-088): the running total, validation, the configured cap."""

from __future__ import annotations

import asyncio
import math

import pytest
from common import (
    COST_KEY,
    DEFAULT_MAX_COST_PER_RUN_USD,
    add_cost,
    max_cost_per_run_usd,
    parse_cost_usd,
    track_request_cost,
)


def test_the_total_collects_only_what_is_added_inside_the_request():
    add_cost(0.5)  # no request is being tracked: ignored
    with track_request_cost() as cost:
        add_cost(0.001)
        add_cost(0.0025)
        add_cost(None)  # an unpriced call adds a call but no dollars
    assert cost.total_usd == pytest.approx(0.0035) and cost.calls == 3
    add_cost(0.5)
    assert cost.total_usd == pytest.approx(0.0035)  # the finished request is not touched


@pytest.mark.anyio
async def test_concurrent_requests_keep_separate_totals():
    async def handle(amount, pause):
        with track_request_cost() as cost:
            await asyncio.sleep(pause)
            add_cost(amount)
            await asyncio.sleep(pause)
            return cost.total_usd

    a, b = await asyncio.gather(handle(0.004, 0.01), handle(0.009, 0.0))
    assert (a, b) == (0.004, 0.009)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.parametrize("raw", [0, 0.0, 0.0003, 1, 12.5])
def test_a_valid_cost_is_accepted_as_a_float(raw):
    assert parse_cost_usd(raw) == float(raw)


@pytest.mark.parametrize(
    "raw",
    [None, "0.01", True, False, -0.0001, -5, math.nan, math.inf, -math.inf, [0.1], {"a": 1}],
)
def test_a_malformed_or_negative_cost_is_rejected(raw):
    assert parse_cost_usd(raw) is None


def test_the_cap_defaults_to_two_cents_and_a_blank_value_means_the_default():
    assert DEFAULT_MAX_COST_PER_RUN_USD == 0.02 and COST_KEY == "cost_usd"
    assert max_cost_per_run_usd({}) == 0.02
    assert max_cost_per_run_usd({"MAX_COST_PER_RUN_USD": ""}) == 0.02  # .env.example's blank
    assert max_cost_per_run_usd({"MAX_COST_PER_RUN_USD": "  "}) == 0.02
    assert max_cost_per_run_usd({"MAX_COST_PER_RUN_USD": "0.005"}) == 0.005


@pytest.mark.parametrize("bad", ["abc", "0", "-1", "nan", "inf"])
def test_a_bad_cap_is_a_configuration_error(bad):
    with pytest.raises(ValueError, match="MAX_COST_PER_RUN_USD"):
        max_cost_per_run_usd({"MAX_COST_PER_RUN_USD": bad})
