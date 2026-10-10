"""The sentiment checks against a canned database (ADR-087, ADR-090): each check family passes on
a correct answer and fails, with its own code, when one thing is wrong.

The correct answers are built with the sentiment agent's and the feedback server's own code
(in these tests only; QA imports neither), so a pass here means QA's independent reading of
data dictionary §6 agrees with the code that produced the answer."""

from __future__ import annotations

import datetime as dt
import math

import pytest
from agent_qa.sentiment import (
    Checker,
    expected_trend,
    previous_month,
    recompute,
    resolved_range,
    trend_default,
    two_proportion,
)
from agent_sentiment.render import decline_message, render_answer
from agent_sentiment.trend import negative_trend
from mcp_feedback.scoring import CountRow, Coverage, Scope, build_summary
from qa_fakes import AS_OF, SETTINGS, FakeSource, sentiment_manifest
from schemas import FeedbackExample, SentimentAnswer, SentimentRequest

MANIFEST = sentiment_manifest()
VERSION = MANIFEST.version
TREND_RANGE = (dt.date(2026, 3, 1), dt.date(2026, 8, 30))
MONTHS = ["2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]


def failed(checks) -> set[str]:
    return {c.code for c in checks if not c.passed}


def month_rows(negative_by_month: dict[str, int]) -> list[tuple[str, str, int, int]]:
    """(label, bucket, n, flagged): 20 positive, 10 neutral, 5 mixed and the given negatives."""
    rows = []
    for month in MONTHS:
        for label, n in (
            ("positive", 20),
            ("neutral", 10),
            ("negative", negative_by_month[month]),
            ("mixed", 5),
        ):
            rows.append((label, month, n, 1 if label == "negative" and n else 0))
    return rows


RISING = month_rows(dict.fromkeys(MONTHS[:-1], 4) | {"2026-08": 18})
FLAT = month_rows(dict.fromkeys(MONTHS, 4))


def quote(i: int, label="negative", text="The technician never showed up.") -> dict:
    return {
        "submitted_at": dt.datetime(2026, 8, 20, 10, 0, tzinfo=dt.UTC),
        "region": "west",
        "text": text,
        "label": label,
        "confidence": "0.9876",
        "flagged": False,
    }


def example(i: int, fact: dict) -> FeedbackExample:
    return FeedbackExample(
        feedback_id=i,
        submitted_at=fact["submitted_at"],
        region=fact["region"],
        label=fact["label"],
        confidence=fact["confidence"],
        flagged=fact["flagged"],
        feedback_text=fact["text"],
    )


class World:
    """One consistent database state: the counts, the quotes and the cross-check counts."""

    def __init__(self, rows=RISING, n_comments=None, quotes=None, rating=(4715, 7), inconsistent=0):
        self.rows = rows
        self.n_scored = sum(r[2] for r in rows)
        self.n_comments = self.n_scored if n_comments is None else n_comments
        self.quotes = quotes or {}
        self.rating = rating
        self.inconsistent = inconsistent
        self.top: list[int] = []  # what §6 rule 7 says is quoted, fixed when the answer is built

    def source(self) -> FakeSource:
        return FakeSource(
            sentiment_coverage=(self.n_comments, self.n_scored),
            sentiment_buckets=self.rows,
            sentiment_inconsistent_flags=self.inconsistent,
            sentiment_quotes=lambda version, ids: {
                i: self.quotes[i] for i in ids if i in self.quotes
            },
            sentiment_top_quotes=lambda *args: self.top,
            sentiment_rating_counts=self.rating,
        )

    def answer(self, request: SentimentRequest | None = None, quoted=(), span=TREND_RANGE):
        request = request or SentimentRequest(want_trend=True)
        start, end, bucket, assumed = resolved_range(request, AS_OF)
        coverage = Coverage(self.n_comments, self.n_scored, self.n_comments == self.n_scored, 0)
        summary = build_summary(
            VERSION,
            Scope(start, end, request.region),
            bucket,
            coverage,
            [CountRow(*r) for r in self.rows],
        )
        examples = [example(i, self.quotes[i]) for i in quoted]
        honest = [i for i, f in self.quotes.items() if request.example_label in (None, f["label"])]
        honest.sort(key=lambda i: (-float(self.quotes[i]["confidence"]), i))
        self.top = honest[:3] if request.want_examples else []
        answer = SentimentAnswer(
            request=request,
            start=start,
            end=end,
            range_assumed=assumed,
            as_of=AS_OF,
            summary=summary,
            trend=negative_trend(summary) if request.want_trend else None,
            examples=examples,
            quoted_feedback_ids=list(quoted),
        )
        return answer, render_answer(answer)

    def check(self, answer, text):
        return Checker(self.source(), SETTINGS, MANIFEST).check_answer(answer, text)


# --------------------------------------------------------------------------- correct answers


def test_a_correct_trend_answer_passes_every_check_and_reports_the_cross_check():
    world = World()
    answer, text = world.answer()
    checks = world.check(answer, text)
    assert failed(checks) == set()
    rating = next(c for c in checks if c.code == "rating_contradiction")
    assert rating.detail == "n=4715, x=7, p0=0.01: pass" and rating.check_class == "figures"
    assert answer.trend.verdict == "rose"


@pytest.mark.parametrize(
    "request_",
    [
        SentimentRequest(want_trend=True),
        SentimentRequest(want_trend=True, region="west"),
        SentimentRequest(start=dt.date(2026, 3, 1), end=dt.date(2026, 8, 30), want_trend=True),
        SentimentRequest(start=dt.date(2026, 3, 1), end=dt.date(2026, 8, 30), bucket="quarter"),
        SentimentRequest(),
    ],
)
def test_the_range_rules_and_buckets_agree_with_the_agent(request_):
    world = World(rows=RISING if request_.bucket == "month" else RISING)
    answer, text = world.answer(request_)
    # quarter requests pass the monthly labels through the canned database; only the range,
    # coverage and the pieces that do not depend on bucket names are asserted here
    checks = world.check(answer, text)
    assert "range_matches_request" not in failed(checks)
    assert "coverage_matches_database" not in failed(checks)


def test_a_partial_answer_opens_with_its_coverage_line_and_passes():
    world = World(n_comments=300)
    answer, text = world.answer()
    assert text.startswith("Based on ") and not answer.summary.complete
    assert failed(world.check(answer, text)) == set()


def test_a_flat_trend_is_no_clear_change_and_passes():
    world = World(rows=FLAT)
    answer, text = world.answer()
    assert answer.trend.verdict == "no clear change"
    assert failed(world.check(answer, text)) == set()


# --------------------------------------------------------------------------- the range


def test_default_ranges_follow_adr_068():
    assert trend_default(AS_OF) == (dt.date(2026, 3, 1), AS_OF)
    assert previous_month(AS_OF) == (dt.date(2026, 7, 1), dt.date(2026, 7, 31))
    assert resolved_range(SentimentRequest(want_trend=True, bucket="quarter"), AS_OF) == (
        dt.date(2026, 3, 1),
        AS_OF,
        "month",
        True,
    )
    assert resolved_range(SentimentRequest(bucket="quarter"), AS_OF)[2:] == ("quarter", True)
    named = SentimentRequest(start=dt.date(2025, 1, 1), end=dt.date(2025, 3, 31), bucket="quarter")
    assert resolved_range(named, AS_OF) == (
        dt.date(2025, 1, 1),
        dt.date(2025, 3, 31),
        "quarter",
        False,
    )


@pytest.mark.parametrize(
    "update",
    [
        {"as_of": dt.date(2026, 8, 1)},
        {"range_assumed": False},
        {"start": dt.date(2026, 2, 1)},
    ],
)
def test_a_wrong_range_as_of_or_assumed_flag_is_caught(update):
    world = World()
    answer, text = world.answer()
    bad = answer.model_copy(update=update)
    assert "range_matches_request" in failed(world.check(bad, text))


# --------------------------------------------------------------------------- coverage and figures


@pytest.mark.parametrize(
    "update",
    [{"n_comments": 400}, {"n_scored": 100}, {"complete": False}, {"model_version": "0" * 64}],
)
def test_wrong_coverage_is_caught(update):
    world = World()
    answer, text = world.answer()
    bad = answer.model_copy(update={"summary": answer.summary.model_copy(update=update)})
    assert "coverage_matches_database" in failed(world.check(bad, text))


def test_wrong_counts_shares_flags_and_buckets_are_caught():
    world = World()
    answer, text = world.answer()
    s = answer.summary
    for update in (
        {"counts": s.counts.model_copy(update={"positive": s.counts.positive + 1})},
        {"shares": s.shares.model_copy(update={"mixed": "0.5000"})},
        {"flagged_count": s.flagged_count + 1},
        {"buckets": s.buckets[:-1]},
        {"buckets": [s.buckets[1], s.buckets[0], *s.buckets[2:]]},
        {
            "buckets": [
                s.buckets[0].model_copy(update={"flagged_count": 9}),
                *s.buckets[1:],
            ]
        },
    ):
        bad = answer.model_copy(update={"summary": s.model_copy(update=update)})
        assert "figures_match_database" in failed(world.check(bad, text)), update


def test_a_non_finite_or_negative_count_cannot_even_be_built():
    from pydantic import ValidationError
    from schemas import LabelCounts

    for bad in (-1, math.nan, math.inf):
        with pytest.raises(ValidationError):
            LabelCounts(positive=bad, neutral=0, negative=0, mixed=0)


# --------------------------------------------------------------------------- flags


def test_a_prediction_whose_flag_disagrees_with_its_confidence_fails_the_answer():
    world = World(inconsistent=1)
    answer, text = world.answer()
    assert "flags_consistent" in failed(world.check(answer, text))


def test_the_flag_check_uses_tau_from_the_manifest():
    world = World()
    source = world.source()
    answer, text = world.answer()
    Checker(source, SETTINGS, MANIFEST).check_answer(answer, text)
    call = next(c for c in source.calls if c[0] == "sentiment_inconsistent_flags")
    assert call[-1] == MANIFEST.tau == pytest.approx(0.840840745682907)


# --------------------------------------------------------------------------- the trend


def test_the_z_test_is_pooled_two_sided_and_matches_a_hand_calculation():
    z, p = two_proportion(18, 53, 20, 195)
    pooled = 38 / 248
    se = math.sqrt(pooled * (1 - pooled) * (1 / 53 + 1 / 195))
    assert z == pytest.approx((18 / 53 - 20 / 195) / se) and p == pytest.approx(
        math.erfc(abs(z) / math.sqrt(2))
    )
    assert two_proportion(0, 30, 0, 30) == (0.0, 1.0)  # nothing to test
    assert two_proportion(30, 30, 30, 30) == (0.0, 1.0)
    assert two_proportion(1, 0, 3, 10) == (0.0, 1.0)  # an empty side


def test_the_agent_and_qa_agree_on_the_z_test_over_many_tables():
    from agent_sentiment.trend import two_proportion_z

    for n1 in (5, 20, 21, 60):
        for n2 in (5, 20, 150):
            for x1 in range(0, n1 + 1, max(1, n1 // 4)):
                for x2 in range(0, n2 + 1, max(1, n2 // 4)):
                    assert two_proportion(x1, n1, x2, n2) == two_proportion_z(x1, n1, x2, n2)


def test_the_trend_must_equal_qas_own_recomputation_field_by_field():
    world = World()
    answer, text = world.answer()
    t = answer.trend
    for update in (
        {"verdict": "fell"},
        {"verdict": "no clear change"},
        {"p_value": 0.5},
        {"z": 0.1},
        {"latest_negative": t.latest_negative + 1},
        {"earlier_n": t.earlier_n + 1},
        {"latest_bucket": "2026-07"},
        {"earlier_buckets": t.earlier_buckets[1:]},
        {"small_sample": True},
    ):
        bad = answer.model_copy(update={"trend": t.model_copy(update=update)})
        assert "trend_matches" in failed(world.check(bad, text)), update


def test_a_verdict_that_contradicts_its_own_numbers_is_caught():
    world = World(rows=FLAT)
    answer, text = world.answer()
    t = answer.trend
    assert t.verdict == "no clear change" and t.p_value > 0.05
    bad = answer.model_copy(update={"trend": t.model_copy(update={"verdict": "rose"})})
    assert "trend_matches" in failed(world.check(bad, text))


def test_a_small_side_is_never_called():
    rows = [("negative", "2026-07", 5, 0), ("positive", "2026-07", 6, 0)] + [
        ("negative", "2026-08", 9, 0),
        ("positive", "2026-08", 1, 0),
    ]
    world = World(rows=rows)
    answer, text = world.answer()
    assert answer.trend.small_sample and answer.trend.verdict == "no clear change"
    assert failed(world.check(answer, text)) == set()
    flipped = answer.model_copy(
        update={"trend": answer.trend.model_copy(update={"verdict": "rose"})}
    )
    assert "trend_matches" in failed(world.check(flipped, text))


def test_one_period_needs_two_periods_and_sets_no_other_field():
    rows = [("negative", "2026-08", 30, 0), ("positive", "2026-08", 30, 0)]
    world = World(rows=rows)
    answer, text = world.answer()
    assert answer.trend.verdict == "needs two periods"
    assert failed(world.check(answer, text)) == set()
    assert expected_trend(recompute(world.source(), VERSION, *TREND_RANGE, None, "month")) == {
        "verdict": "needs two periods"
    }


def test_a_trend_nobody_asked_for_or_a_missing_one_is_caught():
    world = World()
    answer, text = world.answer(SentimentRequest())
    extra = answer.model_construct(**{**dict(answer), "trend": negative_trend(answer.summary)})
    assert "trend_matches" in failed(world.check(extra, text))
    asked, text2 = world.answer()
    missing = asked.model_construct(**{**dict(asked), "trend": None})
    assert "trend_matches" in failed(world.check(missing, text2))


# --------------------------------------------------------------------------- quotes

REQUEST_WITH_QUOTES = SentimentRequest(
    start=dt.date(2026, 8, 1),
    end=dt.date(2026, 8, 30),
    want_examples=True,
    example_label="negative",
)
QUOTES = {1: quote(1), 2: quote(2, text="Rude on the phone, 3 times."), 3: quote(3)}


def quoted_answer(quoted=(1, 2, 3), request=REQUEST_WITH_QUOTES, quotes=None, **world):
    w = World(rows=FLAT, quotes=QUOTES if quotes is None else quotes, **world)
    answer, text = w.answer(request, quoted=quoted)
    return w, answer, text


def test_valid_quotes_pass_and_digits_in_a_comment_are_not_figures():
    w, answer, text = quoted_answer()
    assert "3 times" in text
    assert failed(w.check(answer, text)) == set()


def test_no_quotes_are_fine_when_none_match():
    w, answer, text = quoted_answer(quoted=(), quotes={9: quote(9, label="positive")})
    assert "none match" in text
    assert failed(w.check(answer, text)) == set()


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (lambda q: q.pop(1), "quote_id_does_not_exist"),
        (lambda q: q[1].update(region="central"), "quote_details_differ"),
        (
            lambda q: q[1].update(submitted_at=dt.datetime(2026, 9, 5, tzinfo=dt.UTC)),
            "quote_outside_the_set",
        ),
        (
            lambda q: q[1].update(submitted_at=dt.datetime(2026, 7, 31, 23, tzinfo=dt.UTC)),
            "quote_outside_the_set",
        ),
        (lambda q: q[1].update(label=None, confidence=None, flagged=None), "quote_is_not_scored"),
        (lambda q: q[1].update(label="positive"), "quote_label_is_not_the_one_asked_for"),
        (lambda q: q[1].update(text="The technician never showed up!"), "quoted_text_differs"),
        (lambda q: q[1].update(confidence="0.9875"), "quote_details_differ"),
        (lambda q: q[1].update(flagged=True), "quote_details_differ"),
    ],
)
def test_a_quote_that_breaks_the_rule_is_caught(mutation, expected):
    # the answer is built from the honest facts; the database then differs from what it quotes
    request = SentimentRequest(
        start=dt.date(2026, 8, 1),
        end=dt.date(2026, 8, 30),
        want_examples=True,
        example_label="negative",
    )
    honest = {i: dict(f) for i, f in QUOTES.items()}
    world = World(rows=FLAT, quotes=honest)
    answer, text = world.answer(request, quoted=(1, 2))
    changed = {i: dict(f) for i, f in QUOTES.items()}
    mutation(changed)
    world.quotes = changed
    checks = world.check(answer, text)
    assert "quotes_valid" in failed(checks)
    detail = next(c.detail for c in checks if c.code == "quotes_valid")
    assert expected in detail


def test_text_that_differs_by_one_character_is_caught():
    request = SentimentRequest(
        start=dt.date(2026, 8, 1), end=dt.date(2026, 8, 30), want_examples=True
    )
    world = World(rows=FLAT, quotes={1: quote(1)})
    answer, text = world.answer(request, quoted=(1,))
    world.quotes = {1: quote(1, text="The technician never showed up")}
    assert "quotes_valid" in failed(world.check(answer, text))


def test_quotes_nobody_asked_for_and_more_than_three_are_caught():
    request = SentimentRequest(start=dt.date(2026, 8, 1), end=dt.date(2026, 8, 30))
    world = World(rows=FLAT, quotes=QUOTES)
    answer, text = world.answer(SentimentRequest(want_examples=True), quoted=(1,))
    unrequested = answer.model_construct(**{**dict(answer), "request": request})
    assert "quotes_valid" in failed(world.check(unrequested, text))


def test_a_quote_listed_twice_or_a_wrong_id_list_is_caught():
    world = World(rows=FLAT, quotes=QUOTES)
    answer, text = world.answer(REQUEST_WITH_QUOTES, quoted=(1, 2))
    wrong = answer.model_construct(**{**dict(answer), "quoted_feedback_ids": [2, 1]})
    assert "quotes_valid" in failed(world.check(wrong, text))
    twice = answer.model_construct(
        **{
            **dict(answer),
            "examples": [answer.examples[0], answer.examples[0]],
            "quoted_feedback_ids": [1, 1],
        }
    )
    assert "quotes_valid" in failed(world.check(twice, text))


# --------------------------------------------------------------------------- the rating cross-check


@pytest.mark.parametrize(
    ("n", "x", "passes", "status"),
    [
        (4715, 7, True, "pass"),
        (4715, 80, False, "fail"),
        (100, 5, False, "fail"),
        (100, 3, True, "pass"),
        (19, 19, True, "insufficient_coverage"),
        (0, 0, True, "insufficient_coverage"),
        (20, 20, False, "fail"),
    ],
)
def test_the_rating_cross_check_follows_adr_087(n, x, passes, status):
    world = World(rating=(n, x))
    answer, text = world.answer()
    checks = world.check(answer, text)
    rating = next(c for c in checks if c.code == "rating_contradiction")
    assert rating.passed is passes and rating.detail == f"n={n}, x={x}, p0=0.01: {status}"
    assert ("rating_contradiction" in failed(checks)) is (not passes)


def test_a_failed_rating_check_is_a_figures_failure_so_it_escalates():
    world = World(rating=(100, 6))
    answer, text = world.answer()
    verdict_checks = world.check(answer, text)
    [bad] = [c for c in verdict_checks if not c.passed]
    assert bad.code == "rating_contradiction" and bad.check_class == "figures"


# --------------------------------------------------------------------------- the text


def test_text_with_a_number_in_no_figure_or_without_the_headline_is_caught():
    world = World()
    answer, text = world.answer()
    assert "text_matches_data" in failed(world.check(answer, text + " 9,999 comments."))
    assert "text_matches_data" in failed(
        world.check(answer, text.replace(f"{answer.summary.n_scored:,} comments", "some comments"))
    )
    assert "text_matches_data" in failed(world.check(answer, text.replace("2026-03", "2026-02")))
    assert "text_matches_data" in failed(
        world.check(
            answer, text.replace("Two-proportion test p = ", "Two-proportion test p = 0.5 ")
        )
    )


def test_the_text_check_is_skipped_once_a_figures_check_failed():
    world = World(inconsistent=1)
    answer, text = world.answer()
    assert "text_matches_data" not in {c.code for c in world.check(answer, text + " 9999")}


# --------------------------------------------------------------------------- declines


@pytest.mark.parametrize("reason", ["account", "technician", "service_type", "other"])
def test_each_decline_is_recognised_and_carries_no_figures(reason):
    request = SentimentRequest(unsupported=reason)
    text = decline_message(reason)
    assert failed(Checker(FakeSource(), SETTINGS, MANIFEST).check_decline(request, text)) == set()


def test_a_decline_must_state_the_reason_the_parse_reported():
    c = Checker(FakeSource(), SETTINGS, MANIFEST)
    request = SentimentRequest(unsupported="account")
    assert "decline_matches_reason" in failed(
        c.check_decline(request, decline_message("technician"))
    )
    assert "decline_matches_reason" in failed(c.check_decline(request, "Sorry, no."))
    both = decline_message("account") + " Also " + decline_message("technician")
    assert "decline_matches_reason" in failed(c.check_decline(request, both))


def test_declining_a_request_the_parse_says_is_supported_is_caught():
    c = Checker(FakeSource(), SETTINGS, MANIFEST)
    assert "decline_matches_reason" in failed(
        c.check_decline(SentimentRequest(), decline_message("other"))
    )


def test_a_decline_text_with_a_number_fails_the_no_figures_check():
    c = Checker(FakeSource(), SETTINGS, MANIFEST)
    request = SentimentRequest(unsupported="account")
    assert "decline_no_figures" in failed(
        c.check_decline(request, decline_message("account") + " 4,715 comments in total.")
    )


def test_the_sentiment_manifest_is_read_as_a_file():
    assert MANIFEST.tau == pytest.approx(0.840840745682907) and len(MANIFEST.version) == 64


def test_a_quote_from_another_region_is_outside_a_regional_set():
    request = SentimentRequest(
        start=dt.date(2026, 8, 1), end=dt.date(2026, 8, 30), region="west", want_examples=True
    )
    world = World(rows=FLAT, quotes={1: quote(1)})
    answer, text = world.answer(request, quoted=(1,))
    assert failed(world.check(answer, text)) == set()
    world.quotes = {1: quote(1) | {"region": "central"}}
    checks = world.check(answer, text)
    assert "quote_outside_the_set" in next(c.detail for c in checks if c.code == "quotes_valid")


# ------------------------------------------------------------------ which comments are quoted

RANKED = {
    1: quote(1) | {"confidence": "0.9900"},
    2: quote(2) | {"confidence": "0.9876"},
    3: quote(3) | {"confidence": "0.9876"},  # ties with 2: the lower id comes first
    4: quote(4) | {"confidence": "0.9500"},
    5: quote(5, label="positive") | {"confidence": "0.9999"},  # the wrong label never ranks
}


def ranked(quoted):
    w = World(rows=FLAT, quotes=RANKED)
    answer, text = w.answer(REQUEST_WITH_QUOTES, quoted=quoted)
    return w, answer, text


def test_the_quotes_are_the_top_three_by_confidence_then_lowest_id_for_the_asked_label():
    w, answer, text = ranked((1, 2, 3))
    assert w.top == [1, 2, 3] and failed(w.check(answer, text)) == set()


@pytest.mark.parametrize(
    "quoted",
    [(1, 2, 4), (1, 3, 2), (2, 1, 3), (1, 2), (1,), (4, 3, 2), (1, 2, 3, 4)],
)
def test_any_other_selection_or_order_is_caught(quoted):
    w, answer, text = ranked((1, 2, 3))
    w.top = [1, 2, 3]
    other = w.answer(REQUEST_WITH_QUOTES, quoted=quoted)[0] if len(quoted) <= 3 else None
    if other is None:  # more than three cannot be built; build the contract-breaking one by hand
        other = answer.model_construct(
            **{
                **dict(answer),
                "examples": [example(i, RANKED[i]) for i in quoted],
                "quoted_feedback_ids": list(quoted),
            }
        )
    w.top = [1, 2, 3]
    checks = w.check(other, text)
    assert "quotes_not_the_top_by_confidence" in next(
        (c.detail for c in checks if c.code == "quotes_valid"), ""
    )


def test_selection_uses_the_label_the_question_asked_for():
    request = SentimentRequest(
        start=dt.date(2026, 8, 1), end=dt.date(2026, 8, 30), want_examples=True
    )
    w = World(rows=FLAT, quotes=RANKED)
    answer, text = w.answer(request, quoted=(5, 1, 2))  # no label asked: the 0.9999 positive leads
    assert w.top == [5, 1, 2] and failed(w.check(answer, text)) == set()


# ---------------------------------------------------- the compared bucket and nothing to test


def test_the_text_must_name_the_compared_buckets():
    w = World()
    answer, text = w.answer()
    assert "Latest month, 2026-08:" in text and "2026-03 to 2026-07:" in text
    assert "text_matches_data" in failed(w.check(answer, text.replace("2026-08:", "2026-07:")))
    assert "text_matches_data" in failed(
        w.check(answer, text.replace("2026-03 to 2026-07:", "2026-04 to 2026-07:"))
    )


def test_nothing_to_test_must_read_no_clear_change():
    rows = [("positive", "2026-07", 30, 0), ("positive", "2026-08", 30, 0)]  # no negatives at all
    w = World(rows=rows)
    answer, text = w.answer()
    t = answer.trend
    assert (t.z, t.p_value, t.verdict) == (0.0, 1.0, "no clear change")
    assert failed(w.check(answer, text)) == set()
    bad = answer.model_copy(update={"trend": t.model_copy(update={"verdict": "rose"})})
    detail = next(c.detail for c in w.check(bad, text) if c.code == "trend_matches")
    assert "nothing_to_test_must_be_no_clear_change" in detail
