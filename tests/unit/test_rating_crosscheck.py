"""The rating cross-check's exact binomial rule on fixed numbers (ADR-087)."""

from __future__ import annotations

import pytest
from common.stats import (
    ALPHA,
    MIN_COVERED,
    P0_FLOOR,
    binomial_upper_tail,
    p0_for,
    rating_cross_check,
)
from scipy.stats import binom

# (n, x, p, P(X >= x)): reference values from scipy.stats.binom.sf(x - 1, n, p)
FIXED = [
    (100, 3, 0.01, 0.07937320225218046),
    (100, 4, 0.01, 0.018374036444649678),
    (100, 5, 0.01, 0.0034323215877545238),
    (20, 2, 0.01, 0.01685933763565178),
    (20, 3, 0.01, 0.0010035761681001167),
    (500, 10, 0.01, 0.031102106648487914),
    (500, 12, 0.01, 0.0052080442541713266),
    (1000, 20, 0.01, 0.003288359787727457),
    (60, 1, 0.01, 0.45284335760923855),
    (2000, 5, 0.0025, 0.5597263512923809),
]


@pytest.mark.parametrize(("n", "x", "p", "expected"), FIXED)
def test_the_exact_tail_matches_scipy_on_fixed_numbers(n, x, p, expected):
    assert binomial_upper_tail(n, x, p) == pytest.approx(expected, rel=1e-9)


def test_the_tail_edges():
    assert binomial_upper_tail(50, 0, 0.01) == 1.0
    assert binomial_upper_tail(50, -3, 0.01) == 1.0
    assert binomial_upper_tail(50, 51, 0.01) == 0.0
    assert binomial_upper_tail(50, 1, 0.0) == 0.0
    assert binomial_upper_tail(50, 50, 1.0) == 1.0
    with pytest.raises(ValueError):
        binomial_upper_tail(50, 1, 1.5)


def test_the_tail_is_finite_for_thousands_of_comments():
    # Combinations of this size overflow a float if computed directly.
    assert binomial_upper_tail(7500, 80, 0.01) == pytest.approx(binom.sf(79, 7500, 0.01), rel=1e-6)
    assert binomial_upper_tail(7500, 3, 0.01) == pytest.approx(1.0)


def test_the_constants_are_the_pre_registered_ones():
    assert (P0_FLOOR, ALPHA, MIN_COVERED) == (0.01, 0.01, 20)


@pytest.mark.parametrize(
    ("p_hat", "p0"),
    [(0.0, 0.01), (0.002, 0.01), (0.01, 0.01), (0.034, 0.034)],
)
def test_p0_is_the_baseline_with_a_one_percent_floor(p_hat, p0):
    assert p0_for(p_hat) == p0


@pytest.mark.parametrize(
    ("n", "x", "status"),
    [
        (100, 3, "pass"),  # P = 0.079
        (100, 4, "pass"),  # P = 0.018, not below 0.01
        (100, 5, "fail"),  # P = 0.0034
        (20, 2, "pass"),  # exactly the minimum coverage, P = 0.017
        (20, 3, "fail"),  # P = 0.0010
        (500, 10, "pass"),
        (500, 12, "fail"),
        (60, 0, "pass"),
    ],
)
def test_the_rule_at_p_hat_zero_uses_the_floor(n, x, status):
    verdict = rating_cross_check(n, x, 0.0)
    assert verdict.status == status and verdict.p0 == 0.01
    assert verdict.failed == (status == "fail")
    assert verdict.p_value == pytest.approx(binom.sf(x - 1, n, 0.01), rel=1e-9) if x else True


@pytest.mark.parametrize("n", [0, 1, 19])
def test_under_twenty_covered_is_insufficient_and_never_fails(n):
    verdict = rating_cross_check(n, n, 0.0)  # even if every covered comment contradicts
    assert verdict.status == "insufficient_coverage" and not verdict.failed
    assert (verdict.n, verdict.x, verdict.p_value) == (n, n, None)


def test_a_higher_baseline_raises_the_bar():
    # p_hat 0.034: five contradictions in 100 is unremarkable (P = 0.27), unlike under the floor.
    assert rating_cross_check(100, 5, 0.034).status == "pass"
    assert rating_cross_check(100, 5, 0.0).status == "fail"


def test_bad_counts_are_rejected():
    for n, x in [(-1, 0), (10, -1), (10, 11)]:
        with pytest.raises(ValueError):
            rating_cross_check(n, x, 0.0)
