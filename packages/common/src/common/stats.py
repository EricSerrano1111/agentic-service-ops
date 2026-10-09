"""The sentiment rating cross-check's statistics (ADR-087), in plain Python.

`rating_cross_check` is the rule fixed in ADR-087 before the baseline was measured, and it
never changes after a result is seen: `p0 = max(p_hat, 0.01)`; an answer fails if its covered
count is at least 20 and the one-sided exact binomial P(X >= x | n, p0) is below 0.01;
below 20 covered comments it reports `insufficient_coverage` and does not fail.

Dependency-free like the rest of this package, so the baseline script, the QA agent and the
tests share one implementation. Tests check it against scipy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

#: ADR-087: the owner's judgement, standing for real-world rating/text disagreement that the
#: synthetic data lacks (L-24).
P0_FLOOR = 0.01
#: ADR-087: fail only below this one-sided p-value.
ALPHA = 0.01
#: ADR-087: with fewer covered comments the check is reported, not applied.
MIN_COVERED = 20

Status = Literal["pass", "fail", "insufficient_coverage"]


def binomial_upper_tail(n: int, x: int, p: float) -> float:
    """P(X >= x) for X ~ Binomial(n, p), exactly (a sum of terms in log space, which stays
    finite for the few thousand comments an answer can cover)."""
    if n < 0 or not 0.0 <= p <= 1.0:
        raise ValueError("n must be non-negative and p within [0, 1]")
    if x <= 0:
        return 1.0
    if x > n:
        return 0.0
    if p == 0.0:
        return 0.0
    if p == 1.0:
        return 1.0
    log_p, log_q = math.log(p), math.log1p(-p)
    log_n_fact = math.lgamma(n + 1)
    total = 0.0
    for k in range(x, n + 1):
        log_term = (
            log_n_fact - math.lgamma(k + 1) - math.lgamma(n - k + 1) + k * log_p + (n - k) * log_q
        )
        total += math.exp(log_term)
    return min(1.0, total)


def p0_for(p_hat: float) -> float:
    """The null contradiction rate the cross-check tests against (ADR-087)."""
    return max(p_hat, P0_FLOOR)


@dataclass(frozen=True)
class CrossCheck:
    """One answer's rating cross-check. `n` and `x` are reported on every verdict."""

    status: Status
    n: int
    x: int
    p0: float
    p_value: float | None  # None when the check was not applied

    @property
    def failed(self) -> bool:
        return self.status == "fail"


def rating_cross_check(n: int, x: int, p_hat: float) -> CrossCheck:
    """Apply ADR-087's rule to an answer with `n` covered comments, `x` of them clear
    contradictions, against the measured baseline rate `p_hat`."""
    if n < 0 or x < 0 or x > n:
        raise ValueError("need 0 <= x <= n")
    p0 = p0_for(p_hat)
    if n < MIN_COVERED:
        return CrossCheck("insufficient_coverage", n, x, p0, None)
    p_value = binomial_upper_tail(n, x, p0)
    return CrossCheck("fail" if p_value < ALPHA else "pass", n, x, p0, p_value)
