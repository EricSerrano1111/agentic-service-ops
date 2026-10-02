"""Template-rendered sentiment answers (ADR-068). No model writes any of this text.

Every figure is a field of the `SentimentAnswer` data part, formatted: counts as integers
with thousands separators, shares as percentages to one decimal place (half-up). Customer
comments are quoted verbatim from the data part; they reach this template and the user,
never an LLM.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from schemas import SENTIMENT_LABELS, SentimentAnswer, TrendResult, rate_string

REGION_NAMES = {
    "northeast": "the Northeast",
    "southeast": "the Southeast",
    "central": "the Central region",
    "west": "the West",
}
SUPPORTED = (
    "I can report customer feedback sentiment over a date range, for all sites or one "
    "region (Northeast, Southeast, Central or West), as a trend by month or quarter, and "
    "quote example comments."
)
DECLINES = {
    "account": "Sentiment can't be broken down by account.",
    "technician": "Sentiment can't be broken down by technician.",
    "service_type": "Sentiment can't be broken down by service type.",
    "other": "That breakdown of sentiment isn't supported.",
}


def decline_message(unsupported: str) -> str:
    return f"{DECLINES[unsupported]} {SUPPORTED}"


def percent(share: str | None) -> str:
    """'0.4978' -> '49.8%' (half-up). A null share (nothing scored) -> 'n/a'."""
    if share is None:
        return "n/a"
    value = (Decimal(share) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{value}%"


def coverage_line(n_scored: int, n_comments: int) -> str:
    return (
        f"Based on {n_scored:,} of {n_comments:,} comments in this range; the rest are still "
        "being scored, so the oldest period may be under-represented."
    )


def _where(answer: SentimentAnswer) -> str:
    region = answer.summary.region
    return f" in {REGION_NAMES[region]}" if region else ""


def _trend_lines(trend: TrendResult, bucket: str) -> list[str]:
    if trend.verdict == "needs two periods":
        return [
            f"A trend needs at least two periods; this range has fewer than two "
            f"{bucket}s with comments."
        ]
    earlier = trend.earlier_buckets
    span = earlier[0] if len(earlier) == 1 else f"{earlier[0]} to {earlier[-1]}"
    verdict = {
        "rose": "the negative share rose",
        "fell": "the negative share fell",
        "no clear change": "no clear change in the negative share",
    }[trend.verdict]
    lines = [
        f"Trend: {verdict}. Latest {bucket}, {trend.latest_bucket}: "
        f"{trend.latest_negative:,} of {trend.latest_n:,} negative "
        f"({percent(rate_string(trend.latest_negative, trend.latest_n))}). "
        f"Earlier {bucket}s, {span}: {trend.earlier_negative:,} of {trend.earlier_n:,} "
        f"negative ({percent(rate_string(trend.earlier_negative, trend.earlier_n))}). "
        f"Two-proportion test p = {trend.p_value:.4f}."
    ]
    if trend.small_sample:
        lines.append(
            "Each side needs at least 20 comments before a change is called, so this is "
            "reported as no clear change."
        )
    return lines


def render_answer(answer: SentimentAnswer) -> str:
    s = answer.summary
    lines: list[str] = []
    if not s.complete:
        lines.append(coverage_line(s.n_scored, s.n_comments))
    assumed = "; no period was named, so this range was assumed" if answer.range_assumed else ""
    lines.append(
        f"Customer feedback sentiment{_where(answer)} from {answer.start.isoformat()} to "
        f"{answer.end.isoformat()} (inclusive, UTC), as of {answer.as_of.isoformat()}{assumed}."
    )
    if s.n_scored == 0:
        lines.append("No scored comments in this range.")
    else:
        counts = s.counts.model_dump()
        shares = s.shares.model_dump()
        parts = ", ".join(
            f"{label} {counts[label]:,} ({percent(shares[label])})" for label in SENTIMENT_LABELS
        )
        lines.append(f"{s.n_scored:,} comments: {parts}.")
        lines.append(
            f"{s.flagged_count:,} comments ({percent(rate_string(s.flagged_count, s.n_scored))}) "
            "are low-confidence and flagged for review."
        )
    if answer.trend is not None:
        lines.extend(_trend_lines(answer.trend, s.bucket))
    if answer.request.want_examples:
        label = answer.request.example_label
        heading = f"Example {label} comments" if label else "Example comments"
        if not answer.examples:
            lines.append(f"{heading}: none match in this range.")
        else:
            lines.append(f"{heading}, quoted as written:")
            for e in answer.examples:
                region = f", {REGION_NAMES[e.region]}" if e.region else ""
                lines.append(
                    f'- [{e.label}, confidence {e.confidence}] "{e.feedback_text}" '
                    f"(feedback {e.feedback_id}, {e.submitted_at.date().isoformat()}{region})"
                )
    return "\n".join(lines)
