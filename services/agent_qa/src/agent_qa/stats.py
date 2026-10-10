"""The repeat-driver significance arithmetic, written again from data dictionary §6 (ADR-087).

QA never imports the incidents server's code; this is its own Fisher's exact test and rate
rounding. The two-sided p-value is the sum of the hypergeometric probabilities of every table
with the observed margins that is no more likely than the observed one (the convention scipy
documents for `fisher_exact`, with its relative tolerance for ties); a unit test checks it
against scipy. §6 says "two-sided Fisher's exact test" without naming the convention; this is
the one the data dictionary's own reference implementation uses, and the gap is recorded in
the limitations log (L-72).
"""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal

_TIE_TOLERANCE = 1e-7


def rate_string(numerator: int, denominator: int, scale: int = 1) -> str | None:
    """`scale * numerator / denominator` rounded half-up to 4 places, as a string; None for a
    zero denominator (§6: a zero denominator gives no rate)."""
    if denominator == 0:
        return None
    value = Decimal(scale * numerator) / Decimal(denominator)
    return str(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def _log_choose(n: int, k: int) -> float:
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def fisher_two_sided(a: int, b: int, c: int, d: int) -> float:
    """p-value for the 2x2 table [[a, b], [c, d]] (group: repeated / not; rest: repeated / not)."""
    if min(a, b, c, d) < 0:
        raise ValueError("counts must not be negative")
    row, col, n = a + b, a + c, a + b + c + d
    if n == 0:
        return 1.0
    lo, hi = max(0, col - (n - row)), min(row, col)
    denom = _log_choose(n, col)

    def log_prob(x: int) -> float:
        return _log_choose(row, x) + _log_choose(n - row, col - x) - denom

    cutoff = log_prob(a) + math.log1p(_TIE_TOLERANCE)
    total = 0.0
    for x in range(lo, hi + 1):
        lp = log_prob(x)
        if lp <= cutoff:
            total += math.exp(lp)
    return min(1.0, total)
