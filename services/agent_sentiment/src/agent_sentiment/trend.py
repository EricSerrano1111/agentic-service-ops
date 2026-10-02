"""ADR-068's trend rule, exactly: is the negative share in the latest bucket different from
the pooled negative share of all earlier buckets in range?

"rose" or "fell" only when both sides hold at least `MIN_N` comments and a two-sided
two-proportion z-test (pooled standard error) gives p < `ALPHA`; otherwise "no clear
change". Fewer than two buckets: "needs two periods". Pure: no I/O, no scipy.
"""

from __future__ import annotations

import math

from schemas import SentimentSummary, TrendResult

MIN_N = 20
ALPHA = 0.05


def two_proportion_z(x1: int, n1: int, x2: int, n2: int) -> tuple[float, float]:
    """(z, two-sided p) for x1/n1 against x2/n2, pooled standard error. z=0, p=1 if
    the pooled share is 0 or 1 (no variation to test)."""
    pooled = (x1 + x2) / (n1 + n2)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    if se == 0:
        return 0.0, 1.0
    z = (x1 / n1 - x2 / n2) / se
    return z, math.erfc(abs(z) / math.sqrt(2))


def negative_trend(summary: SentimentSummary) -> TrendResult:
    buckets = sorted(summary.buckets, key=lambda b: b.bucket)
    if len(buckets) < 2:
        return TrendResult(verdict="needs two periods")
    latest, earlier = buckets[-1], buckets[:-1]
    n1, x1 = latest.n_scored, latest.counts.negative
    n2 = sum(b.n_scored for b in earlier)
    x2 = sum(b.counts.negative for b in earlier)
    small = n1 < MIN_N or n2 < MIN_N
    z, p = two_proportion_z(x1, n1, x2, n2) if n1 and n2 else (0.0, 1.0)
    verdict = "no clear change"
    if not small and p < ALPHA:
        verdict = "rose" if x1 / n1 > x2 / n2 else "fell"
    return TrendResult(
        verdict=verdict,
        latest_bucket=latest.bucket,
        latest_n=n1,
        latest_negative=x1,
        earlier_buckets=[b.bucket for b in earlier],
        earlier_n=n2,
        earlier_negative=x2,
        z=round(z, 4),
        p_value=round(p, 4),
        small_sample=small,
    )
