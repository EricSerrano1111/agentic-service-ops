"""The forecast checks against the committed `volume_v2` manifest (ADR-087, ADR-071, ADR-072).

QA cannot say a point forecast is the right number; these tests pin what it can say: the weeks
shown are the weeks the request names, served and unserved bands and their shown errors come
from the manifest, intervals contain their points, a total is the sum of its weeks, history is
the database's, the year-end caveat is stated, and the text states only those numbers.
"""

from __future__ import annotations

import datetime as dt

import pytest
from agent_forecast.render import render_answer
from agent_qa.forecast import (
    Checker,
    band_name,
    decline_reasons,
    first_forecast_week,
    is_year_end,
    resolve,
)
from qa_fakes import AS_OF, SETTINGS, FakeSource, manifest
from schemas import (
    BandVerdict,
    ForecastAnswer,
    ForecastRequest,
    ForecastWeek,
    HistoryWeek,
)

FIRST = dt.date(2026, 8, 31)
MANIFEST = manifest()


def D(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def failed(checks) -> set[str]:
    return {c.code for c in checks if not c.passed}


def week(horizon: int, slice_: str, point=100.0) -> ForecastWeek:
    entry = MANIFEST.serving[slice_][band_name(horizon)]
    served = bool(entry["served"])
    return ForecastWeek(
        week_start=MANIFEST.week(horizon),
        horizon=horizon,
        band=band_name(horizon),
        served=served,
        point=point if served else None,
        lo80=point * 0.9 if served else None,
        hi80=point * 1.1 if served else None,
        lo95=point * 0.8 if served else None,
        hi95=point * 1.2 if served else None,
    )


def make(request: ForecastRequest, history=None, **overrides) -> tuple[ForecastAnswer, str]:
    assumed, _, requested = resolve(request, AS_OF)
    limit = MANIFEST.week(26)
    inside = [w for w in requested if w <= limit]
    weeks = [week((w - FIRST).days // 7 + 1, request.slice) for w in inside]
    bands = {
        w.band: BandVerdict(
            served=w.served,
            shown_error=MANIFEST.serving[request.slice][w.band]["shown_error"],
        )
        for w in weeks
    }
    total = sum(w.point for w in weeks) if len(weeks) > 1 and all(w.served for w in weeks) else None
    answer = ForecastAnswer(
        request=request,
        as_of=AS_OF,
        trained_through=MANIFEST.trained_through,
        model_version=MANIFEST.version,
        range_assumed=assumed,
        requested_first_week=requested[0],
        requested_last_week=requested[-1],
        beyond_horizon_weeks=len(requested) - len(inside),
        weeks=weeks,
        bands=bands,
        period_total=total,
        year_end_weeks=[w.week_start for w in weeks if is_year_end(w.week_start)],
        history=history or [],
    )
    answer = answer.model_copy(update=overrides)
    return answer, render_answer(answer)


def checker(**canned) -> Checker:
    return Checker(FakeSource(**canned), SETTINGS, MANIFEST)


TOTAL_NEXT_8 = ForecastRequest(slice="total", horizon_weeks=8)
INSTALL_10 = ForecastRequest(slice="install", horizon_weeks=10)


# --------------------------------------------------------------------------- the rules


def test_the_manifest_is_the_committed_one_and_reads_as_expected():
    assert MANIFEST.last_training_week == D("2026-08-24")
    assert MANIFEST.trained_through == D("2026-08-30")
    assert MANIFEST.week(1) == FIRST == first_forecast_week(AS_OF)
    assert len(MANIFEST.version) == 64
    assert MANIFEST.serving["install"]["1-4"]["served"] is False
    assert MANIFEST.serving["install"]["5-13"]["served"] is True


def test_the_year_end_indicator_marks_the_iso_weeks_with_dec_25_or_jan_1():
    assert is_year_end(D("2026-12-21")) and is_year_end(D("2026-12-28"))
    assert not is_year_end(D("2026-12-14")) and not is_year_end(D("2027-01-04"))


@pytest.mark.parametrize(
    ("request_", "expected"),
    [
        (ForecastRequest(horizon_weeks=8), set()),
        (ForecastRequest(), set()),
        (ForecastRequest(horizon_weeks=40), set()),
        (ForecastRequest(horizon_weeks=8, unsupported="region"), {"region"}),
        (ForecastRequest(horizon_weeks=8, unsupported="sla"), {"sla"}),
        (
            ForecastRequest(period_start=D("2026-07-01"), period_end=D("2026-07-31")),
            {"past_period"},
        ),
        (
            ForecastRequest(
                period_start=D("2026-07-01"), period_end=D("2026-07-31"), unsupported="past_period"
            ),
            {"past_period"},
        ),
        (
            ForecastRequest(period_start=D("2026-09-01"), period_end=D("2026-09-06")),
            {"no_week"},
        ),
        (ForecastRequest(period_start=D("2026-08-31"), period_end=D("2026-08-31")), set()),
    ],
)
def test_the_decline_rules(request_, expected):
    assert decline_reasons(request_, AS_OF) == expected


def test_period_resolution_follows_adr_072():
    assumed, past, weeks = resolve(ForecastRequest(), AS_OF)  # next month: September 2026
    assert (
        assumed
        and not past
        and weeks == [D("2026-09-07"), D("2026-09-14"), D("2026-09-21"), D("2026-09-28")]
    )
    _, _, eight = resolve(ForecastRequest(horizon_weeks=8), AS_OF)
    assert eight[0] == FIRST and len(eight) == 8


# --------------------------------------------------------------------------- correct answers


@pytest.mark.parametrize(
    "request_",
    [
        TOTAL_NEXT_8,
        INSTALL_10,
        ForecastRequest(slice="repair"),
        ForecastRequest(slice="total", horizon_weeks=26),
        ForecastRequest(slice="total", period_start=D("2027-04-01"), period_end=D("2027-06-30")),
        ForecastRequest(slice="total", period_start=D("2027-01-01"), period_end=D("2027-12-31")),
        ForecastRequest(slice="upgrade", horizon_weeks=3),
    ],
)
def test_a_correct_answer_passes_every_check(request_):
    answer, text = make(request_)
    checks = checker().check_answer(answer, text)
    assert failed(checks) == set(), [(c.code, c.detail) for c in checks if not c.passed]


def test_all_beyond_the_horizon_is_a_valid_answer_with_no_weeks():
    answer, text = make(
        ForecastRequest(slice="total", period_start=D("2027-04-01"), period_end=D("2027-06-30"))
    )
    assert answer.weeks == [] and answer.beyond_horizon_weeks > 0
    assert failed(checker().check_answer(answer, text)) == set()


# --------------------------------------------------------------------------- the weeks


def test_weeks_that_are_not_the_requested_ones_are_caught():
    answer, text = make(TOTAL_NEXT_8)
    dropped = answer.model_copy(update={"weeks": answer.weeks[:-1]})
    assert "weeks_match_request" in failed(checker().check_answer(dropped, text))


def test_a_wrong_beyond_horizon_count_is_caught():
    answer, text = make(ForecastRequest(slice="total", horizon_weeks=30))
    assert answer.beyond_horizon_weeks == 4
    wrong = answer.model_copy(update={"beyond_horizon_weeks": 3})
    assert "weeks_match_request" in failed(checker().check_answer(wrong, text))


def test_a_stale_model_version_or_training_date_is_caught():
    answer, text = make(TOTAL_NEXT_8)
    for update in ({"model_version": "0" * 64}, {"trained_through": D("2026-08-23")}):
        assert "weeks_match_request" in failed(
            checker().check_answer(answer.model_copy(update=update), text)
        )


def test_a_different_as_of_date_is_caught():
    answer, text = make(TOTAL_NEXT_8)
    assert "weeks_match_request" in failed(
        checker().check_answer(answer.model_copy(update={"as_of": D("2026-08-01")}), text)
    )


def test_a_forecast_answered_when_it_should_have_been_declined_is_caught():
    answer, text = make(TOTAL_NEXT_8)
    bad = answer.model_copy(update={"request": ForecastRequest(horizon_weeks=8, unsupported="sla")})
    assert "weeks_match_request" in failed(checker().check_answer(bad, text))


# --------------------------------------------------------------------------- arithmetic


def test_a_horizon_beyond_26_weeks_is_caught():
    answer, text = make(TOTAL_NEXT_8)
    far = ForecastWeek.model_construct(**{**answer.weeks[0].model_dump(), "horizon": 27})
    bad = answer.model_copy(update={"weeks": [far, *answer.weeks[1:]]})
    assert "forecast_arithmetic" in failed(checker().check_answer(bad, text))


def test_a_week_whose_date_does_not_match_its_horizon_is_caught():
    answer, text = make(TOTAL_NEXT_8)
    moved = answer.weeks[2].model_copy(update={"week_start": D("2026-10-12")})
    bad = answer.model_copy(update={"weeks": [*answer.weeks[:2], moved, *answer.weeks[3:]]})
    assert "forecast_arithmetic" in failed(checker().check_answer(bad, text))


@pytest.mark.parametrize(
    "update",
    [
        {"point": 200.0},  # above the 80% range
        {"lo80": 105.0},  # point below the 80% range
        {"hi95": 105.0},  # 95% range inside the 80% range
        {"point": float("nan")},
    ],
)
def test_an_interval_that_does_not_contain_its_point_is_caught(update):
    answer, text = make(TOTAL_NEXT_8)
    bad_week = ForecastWeek.model_construct(**{**answer.weeks[0].model_dump(), **update})
    bad = answer.model_copy(update={"weeks": [bad_week, *answer.weeks[1:]]})
    assert "forecast_arithmetic" in failed(checker().check_answer(bad, ""))


def test_a_period_total_that_is_not_the_sum_is_caught():
    answer, text = make(TOTAL_NEXT_8)
    assert answer.period_total == pytest.approx(800.0)
    bad = answer.model_copy(update={"period_total": 801.0})
    assert "forecast_arithmetic" in failed(checker().check_answer(bad, text))


def test_a_total_over_weeks_that_are_not_all_shown_is_caught():
    answer, text = make(INSTALL_10)  # install 1-4 is unserved: no total may be given
    assert answer.period_total is None
    bad = answer.model_copy(update={"period_total": 600.0})
    assert "forecast_arithmetic" in failed(checker().check_answer(bad, text))


def test_a_missing_total_when_every_week_is_shown_is_caught():
    answer, text = make(TOTAL_NEXT_8)
    bad = answer.model_copy(update={"period_total": None})
    assert "forecast_arithmetic" in failed(checker().check_answer(bad, text))


# --------------------------------------------------------------------------- the manifest


def test_a_week_marked_served_in_an_unserved_band_is_caught():
    answer, text = make(INSTALL_10)
    first = answer.weeks[0]
    assert first.served is False
    lie = ForecastWeek.model_construct(
        **{
            **first.model_dump(),
            "served": True,
            "point": 90.0,
            "lo80": 80.0,
            "hi80": 100.0,
            "lo95": 70.0,
            "hi95": 110.0,
        }
    )
    bad = answer.model_copy(update={"weeks": [lie, *answer.weeks[1:]]})
    assert "serving_matches_manifest" in failed(checker().check_answer(bad, text))


def test_numbers_on_an_unserved_week_are_caught():
    answer, text = make(INSTALL_10)
    first = answer.weeks[0]
    leaked = ForecastWeek.model_construct(**{**first.model_dump(), "point": 50.0})
    bad = answer.model_copy(update={"weeks": [leaked, *answer.weeks[1:]]})
    assert "serving_matches_manifest" in failed(checker().check_answer(bad, text))


def test_a_served_week_in_a_band_the_manifest_does_not_serve_is_caught():
    answer, text = make(INSTALL_10)
    # the 14-26 band of install is unserved in the manifest; claim the whole answer is served
    far, far_text = make(ForecastRequest(slice="install", horizon_weeks=20))
    flipped_weeks = [
        w
        if w.band != "14-26"
        else ForecastWeek.model_construct(**{**w.model_dump(), "served": True})
        for w in far.weeks
    ]
    bad = far.model_copy(update={"weeks": flipped_weeks})
    assert "serving_matches_manifest" in failed(checker().check_answer(bad, far_text))


def test_a_shown_error_that_is_not_the_manifests_is_caught():
    answer, text = make(TOTAL_NEXT_8)
    band = next(iter(answer.bands))
    wrong = dict(answer.bands)
    wrong[band] = BandVerdict(served=wrong[band].served, shown_error=wrong[band].shown_error + 1.0)
    bad = answer.model_copy(update={"bands": wrong})
    assert "serving_matches_manifest" in failed(checker().check_answer(bad, text))


def test_a_band_flag_that_disagrees_with_the_manifest_is_caught():
    answer, text = make(INSTALL_10)
    band = "1-4"
    wrong = dict(answer.bands)
    wrong[band] = BandVerdict(served=True, shown_error=wrong[band].shown_error)
    bad = answer.model_copy(update={"bands": wrong})
    assert "serving_matches_manifest" in failed(checker().check_answer(bad, text))


# --------------------------------------------------------------------------- year-end


def test_a_year_end_week_must_be_flagged_and_the_caveat_stated():
    request_ = ForecastRequest(slice="total", horizon_weeks=26)  # through late Feb 2027
    answer, text = make(request_)
    assert D("2026-12-21") in answer.year_end_weeks and "holiday adjustment" in text
    assert failed(checker().check_answer(answer, text)) == set()
    no_flags = answer.model_copy(update={"year_end_weeks": []})
    assert "year_end_caveat" in failed(checker().check_answer(no_flags, text))
    no_caveat = text.replace("holiday adjustment", "calendar adjustment")
    assert "year_end_caveat" in failed(checker().check_answer(answer, no_caveat))


def test_the_caveat_is_not_stated_when_no_year_end_week_is_shown():
    answer, text = make(TOTAL_NEXT_8)
    assert answer.year_end_weeks == []
    assert "year_end_caveat" in failed(checker().check_answer(answer, text + " holiday adjustment"))


# --------------------------------------------------------------------------- history


def history_for(weeks, count=140) -> list[HistoryWeek]:
    return [HistoryWeek(week_start=w, count=count) for w in weeks]


def three_weeks():
    return [D("2026-08-10"), D("2026-08-17"), D("2026-08-24")]


def test_history_must_equal_the_databases_weekly_counts():
    request_ = ForecastRequest(slice="total", horizon_weeks=8, want_history=True)
    answer, text = make(request_, history=history_for(three_weeks()))
    good = checker(weekly_counts=lambda s, a, b: dict.fromkeys(three_weeks(), 140))
    assert failed(good.check_answer(answer, text)) == set()
    wrong = checker(
        weekly_counts=lambda s, a, b: {**dict.fromkeys(three_weeks(), 140), D("2026-08-17"): 139}
    )
    assert "history_matches_database" in failed(wrong.check_answer(answer, text))


def test_a_week_the_database_has_no_requests_for_counts_as_zero():
    request_ = ForecastRequest(slice="total", horizon_weeks=8, want_history=True)
    answer, text = make(request_, history=history_for(three_weeks(), count=0))
    c = checker(weekly_counts={})
    assert "history_matches_database" not in failed(c.check_answer(answer, text))


def test_history_that_was_not_asked_for_is_caught():
    answer, text = make(TOTAL_NEXT_8, history=history_for(three_weeks()))
    assert "history_matches_database" in failed(checker().check_answer(answer, text))


def test_history_that_was_asked_for_but_is_missing_is_caught():
    request_ = ForecastRequest(slice="total", horizon_weeks=8, want_history=True)
    answer, text = make(request_)
    assert "history_matches_database" in failed(checker().check_answer(answer, text))


@pytest.mark.parametrize(
    "weeks",
    [
        [D("2026-08-11"), D("2026-08-18")],  # not Mondays
        [D("2026-08-24"), D("2026-08-17")],  # out of order
        [D("2026-08-24"), D("2026-08-31")],  # past the last training week
    ],
)
def test_history_weeks_must_be_ordered_mondays_within_the_training_window(weeks):
    request_ = ForecastRequest(slice="total", horizon_weeks=8, want_history=True)
    answer, text = make(request_, history=history_for(weeks))
    c = checker(weekly_counts=lambda s, a, b: dict.fromkeys(weeks, 140))
    assert "history_matches_database" in failed(c.check_answer(answer, text))


def test_install_history_asks_the_database_for_the_install_slice():
    request_ = ForecastRequest(slice="install", horizon_weeks=10, want_history=True)
    answer, text = make(request_, history=history_for(three_weeks()))
    source = FakeSource(weekly_counts=lambda s, a, b: dict.fromkeys(three_weeks(), 140))
    Checker(source, SETTINGS, MANIFEST).check_answer(answer, text)
    assert source.calls[0][:2] == ("weekly_counts", "install")


# --------------------------------------------------------------------------- text


def test_text_with_a_number_that_is_in_no_figure_is_caught():
    answer, text = make(TOTAL_NEXT_8)
    assert "text_matches_data" in failed(
        checker().check_answer(answer, text + " About 9,999 more.")
    )


def test_text_that_omits_a_served_weeks_number_is_caught():
    answer, text = make(TOTAL_NEXT_8)
    assert "text_matches_data" in failed(
        checker().check_answer(answer, text.replace("about 100 requests", "about some requests"))
    )


def test_text_that_states_a_different_error_is_caught():
    answer, text = make(TOTAL_NEXT_8)
    pct = f"{MANIFEST.serving['total']['1-4']['shown_error']:.1f}%"
    assert pct in text
    assert "text_matches_data" in failed(checker().check_answer(answer, text.replace(pct, "1.1%")))


def test_text_stating_a_date_that_is_not_in_the_answer_is_caught():
    answer, text = make(TOTAL_NEXT_8)
    assert "text_matches_data" in failed(checker().check_answer(answer, text + " See 2027-02-02."))


def test_the_text_check_is_skipped_once_a_figures_check_failed():
    answer, text = make(TOTAL_NEXT_8)
    bad = answer.model_copy(update={"period_total": 1.0})
    assert "text_matches_data" not in {c.code for c in checker().check_answer(bad, "9999")}


# --------------------------------------------------------------------------- declines


@pytest.mark.parametrize(
    ("request_", "text"),
    [
        (
            ForecastRequest(horizon_weeks=8, unsupported="sla"),
            "SLA outlook can't be forecast: there's no model for SLA compliance. I can forecast "
            "weekly request volume, in total or by service type, up to 26 weeks ahead.",
        ),
        (
            ForecastRequest(horizon_weeks=8, unsupported="incidents"),
            "Incidents can't be forecast: there's no incident model. I can forecast weekly "
            "request volume up to 26 weeks ahead.",
        ),
        (
            ForecastRequest(horizon_weeks=8, unsupported="sentiment"),
            "Customer sentiment can't be forecast. I can forecast weekly request volume.",
        ),
        (
            ForecastRequest(horizon_weeks=8, unsupported="region"),
            "Forecasts can't be broken down by region. I can forecast weekly request volume.",
        ),
        (
            ForecastRequest(horizon_weeks=8, unsupported="account"),
            "Forecasts can't be broken down by account. I can forecast weekly request volume.",
        ),
        (
            ForecastRequest(horizon_weeks=8, unsupported="technician"),
            "Forecasts can't be broken down by technician. I can forecast weekly request volume.",
        ),
        (
            ForecastRequest(horizon_weeks=8, unsupported="other"),
            "That isn't something I can forecast. I can forecast weekly request volume.",
        ),
        (
            ForecastRequest(period_start=D("2026-07-01"), period_end=D("2026-07-31")),
            "That period has already happened; forecasts cover weeks after 2026-08-30. I can "
            "forecast weekly request volume.",
        ),
        (
            ForecastRequest(period_start=D("2026-09-01"), period_end=D("2026-09-06")),
            "No forecast week starts in that period (weeks start on Monday). Forecasts cover "
            "weeks after 2026-08-30. I can forecast weekly request volume.",
        ),
    ],
)
def test_each_forecast_decline_is_recognised_and_carries_no_figures(request_, text):
    assert failed(checker().check_decline(request_, text)) == set()


def test_a_decline_stating_a_reason_that_does_not_apply_is_caught():
    request_ = ForecastRequest(horizon_weeks=8, unsupported="region")
    text = "Incidents can't be forecast: there's no incident model."
    assert "decline_matches_reason" in failed(checker().check_decline(request_, text))


def test_declining_a_request_that_can_be_forecast_is_caught():
    text = "That isn't something I can forecast."
    assert "decline_matches_reason" in failed(checker().check_decline(TOTAL_NEXT_8, text))


def test_a_decline_text_carrying_a_number_fails_the_no_figures_check():
    request_ = ForecastRequest(horizon_weeks=8, unsupported="sla")
    text = "SLA outlook can't be forecast. Volume would be 1,234 requests."
    assert "decline_no_figures" in failed(checker().check_decline(request_, text))
