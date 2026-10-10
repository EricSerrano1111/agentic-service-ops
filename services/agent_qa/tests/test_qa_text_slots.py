"""The answer text is checked by position, against the real renderers (ADR-092; data dictionary
§6 "Answer text"; L-81, L-82, L-84).

Each case builds a data part, renders it with the specialist's own renderer, and asks QA's text
check about it. The renderers are imported here, in the test, and not in QA: QA writes the slot
list from §6 alone. The fixed cases are measurement 1's findings: the zero-denominator false
alarm (`reporting:f09`), the four forecast text figures that passed, and owner faults 4a and 4b.
"""

from __future__ import annotations

import datetime as dt
import re

import pytest
from agent_forecast.render import render_answer as render_forecast
from agent_qa import slots
from agent_qa.forecast import Checker as ForecastChecker
from agent_qa.reporting import Checker
from agent_reporting.render import TOO_FEW
from agent_reporting.render import render_answer as render_reporting
from qa_fakes import AS_OF, SETTINGS, FakeSource, manifest
from schemas import (
    BandVerdict,
    FirstTimeFixResult,
    ForecastAnswer,
    ForecastRequest,
    ForecastWeek,
    GroupRate,
    IncidentRateResult,
    IncidentSummary,
    JobsRepeated,
    RepeatDriversResult,
    RepeatGroup,
    ReportingAnswer,
    ReportingRequest,
    SeverityCounts,
    SlaComplianceResult,
)

JULY = (dt.date(2026, 7, 1), dt.date(2026, 7, 31))
MIN = 20


def text_problems(answer: ReportingAnswer, text: str | None = None) -> list[str]:
    checker = Checker(FakeSource(), SETTINGS)
    result = checker._check_text(
        answer, text if text is not None else render_reporting(answer, MIN)
    )
    return [] if result.passed else [result.detail]


def reporting(figures, **request) -> ReportingAnswer:
    return ReportingAnswer(
        request=ReportingRequest(metric=figures.metric, start=JULY[0], end=JULY[1], **request),
        start=JULY[0],
        end=JULY[1],
        range_assumed=False,
        as_of=AS_OF,
        figures=figures,
    )


def sla(numerator, denominator, **fields):
    rate = None if denominator == 0 else f"{numerator / denominator:.4f}"
    return SlaComplianceResult(
        start=JULY[0],
        end=JULY[1],
        numerator=numerator,
        denominator=denominator,
        rate=rate,
        **fields,
    )


# --------------------------------------------------------------------------- L-81


@pytest.mark.parametrize(
    "figures",
    [
        IncidentRateResult(start=JULY[0], end=JULY[1], numerator=3, denominator=0, rate=None),
        sla(0, 0),
        FirstTimeFixResult(start=JULY[0], end=JULY[1], numerator=0, denominator=0, rate=None),
        sla(0, 0, region="west"),
        sla(0, 0, account_id=7, account_name="Summit Distribution Co.", region="west"),
        FirstTimeFixResult(
            start=JULY[0],
            end=JULY[1],
            numerator=0,
            denominator=0,
            rate=None,
            technician_id=4,
            technician_name="Priya Kim",
        ),
        IncidentRateResult(
            start=JULY[0], end=JULY[1], numerator=0, denominator=0, rate=None, region="central"
        ),
    ],
    ids=["incident-rate", "sla", "ftf", "sla-region", "f09", "ftf-technician", "rate-region"],
)
def test_a_zero_denominator_answer_passes_whatever_its_wording(figures):
    answer = reporting(
        figures,
        **{
            k: v
            for k, v in {
                "region": figures.region,
                "account_name": figures.account_name,
                "technician_name": figures.technician_name,
            }.items()
            if v
        },
    )
    assert text_problems(answer) == []


def test_a_repeat_driver_answer_with_no_jobs_passes():
    none = JobsRepeated(jobs=0, repeated=0, rate=None)
    figures = RepeatDriversResult(
        start=JULY[0],
        end=JULY[1],
        group_by="region",
        overall=none,
        groups=[],
        group_count=0,
        groups_compared=0,
    )
    assert text_problems(reporting(figures, group_by="region")) == []


def test_the_incident_rate_zero_case_states_the_incident_count():
    figures = IncidentRateResult(start=JULY[0], end=JULY[1], numerator=3, denominator=0, rate=None)
    answer = reporting(figures)
    assert slots.reporting(answer)[0] == ["3"]
    text = render_reporting(answer, MIN).replace("3 incidents", "4 incidents")
    assert text_problems(answer, text)


# --------------------------------------------------------------------------- L-82, reporting


def counts_answer():
    figures = IncidentSummary(
        start=JULY[0],
        end=JULY[1],
        incident_count=172,
        by_severity=SeverityCounts(low=93, medium=54, high=25),
    )
    return reporting(figures)


def test_a_correct_count_text_passes_and_each_wrong_form_fails_differently():
    answer = counts_answer()
    text = render_reporting(answer, MIN)
    assert text_problems(answer, text) == []
    assert (
        "text_number_differs_from_its_slot@0"
        in text_problems(answer, text.replace("172", "173"))[0]
    )
    # the high and medium counts swapped are two real figures in the wrong slots
    swapped = text.replace("25 high, 54 medium", "54 high, 25 medium")
    assert "text_number_differs_from_its_slot@1" in text_problems(answer, swapped)[0]
    assert (
        "text_states_a_number_with_no_slot" in text_problems(answer, text + " That is 7 more.")[0]
    )
    assert (
        "text_misses_a_slot_number"
        in text_problems(answer, text.replace(": 25 high, 54 medium, 93 low severity", ""))[0]
    )


# --------------------------------------------------------------------------- L-82, forecast


def week(h: int, point: float, lo: float, hi: float) -> ForecastWeek:
    return ForecastWeek(
        week_start=dt.date(2026, 8, 31) + dt.timedelta(weeks=h - 1),
        horizon=h,
        band="1-4",
        served=True,
        point=point,
        lo80=lo,
        hi80=hi,
        lo95=lo * 0.9,
        hi95=hi * 1.1,
    )


def forecast_answer(weeks: list[ForecastWeek]) -> ForecastAnswer:
    m = manifest()
    return ForecastAnswer(
        request=ForecastRequest(slice="total", horizon_weeks=len(weeks)),
        as_of=AS_OF,
        trained_through=m.trained_through,
        model_version=m.version,
        range_assumed=False,
        requested_first_week=weeks[0].week_start,
        requested_last_week=weeks[-1].week_start,
        beyond_horizon_weeks=0,
        weeks=weeks,
        bands={"1-4": BandVerdict(served=True, shown_error=13.6)},
        period_total=sum(w.point for w in weeks),
    )


def forecast_problems(answer: ForecastAnswer, text: str) -> list[str]:
    c = ForecastChecker(FakeSource(), SETTINGS, manifest())
    result = c._text(answer, text)
    return [] if result.passed else [result.detail]


def test_a_correct_forecast_text_passes():
    answer = forecast_answer(
        [week(1, 61.07, 50.0, 72.0), week(2, 62.4, 51.0, 73.0), week(3, 63.9, 52.0, 74.0)]
    )
    assert forecast_problems(answer, render_forecast(answer)) == []


@pytest.mark.parametrize(
    ("weeks", "old", "new"),
    [
        # measurement 1, forecast:f05: 62 is the ceiling of the true 61.07, once accepted
        (
            [week(1, 61.07, 50.0, 72.0), week(2, 70.0, 60.0, 80.0)],
            "about 61 requests",
            "about 62 requests",
        ),
        # forecast:f14 and f04: the changed figure equals another week's point
        (
            [week(1, 62.15, 50.0, 72.0), week(2, 63.4, 51.0, 74.0)],
            "about 62 requests",
            "about 63 requests",
        ),
        (
            [week(1, 28.26, 20.0, 36.0), week(2, 29.4, 21.0, 37.0)],
            "about 28 requests",
            "about 29 requests",
        ),
        # forecast:f02: the changed figure equals another week's range bound
        (
            [week(1, 150.87, 135.0, 166.0), week(2, 168.0, 152.0, 184.0)],
            "about 151 requests",
            "about 152 requests",
        ),
    ],
    ids=["ceiling", "another-point-a", "another-point-b", "another-range-bound"],
)
def test_measurement_ones_four_forecast_misses_are_now_caught(weeks, old, new):
    answer = forecast_answer(weeks)
    text = render_forecast(answer)
    assert old in text
    problems = forecast_problems(answer, text.replace(old, new, 1))
    assert problems and "text_number_differs_from_its_slot@1" in problems[0]


def test_a_forecast_text_with_an_extra_or_a_missing_number_fails():
    answer = forecast_answer([week(1, 61.07, 50.0, 72.0), week(2, 62.4, 51.0, 73.0)])
    text = render_forecast(answer)
    assert "no_slot" in forecast_problems(answer, text + " About 5 more.")[0]
    assert (
        "misses_a_slot"
        in forecast_problems(answer, re.sub(r"\(80% range [^)]*\)", "", text, count=1))[0]
    )


def test_qas_own_total_check_fails_a_total_that_is_not_the_sum_without_the_contract():
    """Measurement 1's F04: the shared contract's validator rejected this shape before QA's own
    arithmetic ran. Built without the validator, QA's check must fail it on its own."""
    answer = forecast_answer([week(1, 100.0, 90.0, 110.0), week(2, 110.0, 99.0, 121.0)])
    lying = answer.model_copy(update={"period_total": answer.period_total + 1.0})
    c = ForecastChecker(FakeSource(), SETTINGS, manifest())
    checks = c.check_answer(lying, render_forecast(lying))
    assert "forecast_arithmetic" in {x.code for x in checks if not x.passed}


# --------------------------------------------------------------------------- L-84


def technician_rate(n: int) -> ReportingAnswer:
    figures = sla(n, n, technician_id=4, technician_name="Priya Kim")
    return reporting(figures, technician_name="Priya Kim")


def test_a_filtered_rate_under_20_cases_carries_the_marking_and_at_20_does_not():
    small, enough = technician_rate(19), technician_rate(20)
    assert TOO_FEW in render_reporting(small, MIN) and text_problems(small) == []
    assert TOO_FEW not in render_reporting(enough, MIN) and text_problems(enough) == []


def test_owner_fault_4b_the_marking_removed_from_a_single_job_answer_fails():
    answer = technician_rate(1)
    text = render_reporting(answer, MIN)
    assert TOO_FEW in text
    problems = text_problems(answer, text.replace(f" That is {TOO_FEW}.", ""))
    assert problems and "small_sample_marking_missing" in problems[0]


def test_a_marking_where_the_rule_does_not_call_for_one_fails():
    answer = technician_rate(25)
    text = render_reporting(answer, MIN) + f" That is {TOO_FEW}."
    assert "small_sample_marking_not_called_for" in text_problems(answer, text)[0]


def grouped(denominators: list[int]) -> ReportingAnswer:
    groups = [
        GroupRate(group=f"Tech {i}", group_id=i, numerator=d, denominator=d, rate="1.0000")
        for i, d in enumerate(denominators, 1)
    ]
    figures = sla(
        sum(denominators),
        sum(denominators),
        group_by="technician",
        groups=groups,
        group_count=len(groups),
    )
    return reporting(figures, group_by="technician")


def test_owner_fault_4a_a_group_under_20_ranked_with_no_minimum_fails():
    answer = grouped([1, 25, 30])
    honest = render_reporting(answer, MIN)
    assert "1 technician left out of the ranking" in honest and text_problems(answer, honest) == []
    ranked_anyway = render_reporting(answer, 0)
    problems = text_problems(answer, ranked_anyway)
    assert problems and "text_" in problems[0]


def test_the_left_out_count_is_qas_own_and_a_wrong_one_fails():
    answer = grouped([1, 2, 25])
    text = render_reporting(answer, MIN)
    assert text_problems(answer, text) == []
    wrong = text.replace("2 technicians left out", "1 technicians left out")
    assert wrong != text and text_problems(answer, wrong)


def test_with_no_group_reaching_the_minimum_the_text_says_so_and_still_counts_the_rest():
    answer = grouped([3, 4])
    text = render_reporting(answer, MIN)
    assert "no technician has at least 20 cases to rank" in text
    assert text_problems(answer, text) == []


def test_the_minimum_is_the_rules_not_a_setting():
    assert slots.MIN_CASES == 20
    assert not hasattr(SETTINGS, "min_group_denominator")


def test_a_repeat_driver_text_is_checked_by_position():
    def jobs(n, r):
        return JobsRepeated(jobs=n, repeated=r, rate=f"{r / n:.4f}")

    group = RepeatGroup(
        group="west",
        this=jobs(30, 6),
        rest=jobs(100, 5),
        compared=True,
        p_value=0.01,
        p_adjusted=0.04,
        stands_out=True,
    )
    figures = RepeatDriversResult(
        start=JULY[0],
        end=JULY[1],
        group_by="region",
        overall=jobs(130, 11),
        groups=[group],
        group_count=1,
        groups_compared=1,
    )
    answer = reporting(figures, group_by="region")
    text = render_reporting(answer, MIN)
    assert text_problems(answer, text) == []
    assert text_problems(answer, text.replace("(6 of 30 jobs)", "(7 of 30 jobs)", 1))
