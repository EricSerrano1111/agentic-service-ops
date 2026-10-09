"""The reporting checks against a canned database (ADR-087): each check family passes on a
correct answer and fails, with its own code, when one thing is wrong."""

from __future__ import annotations

import datetime as dt

import pytest
from agent_qa import reporting
from agent_qa.db import UNATTRIBUTED
from agent_qa.repeats import compute
from agent_qa.reporting import Checker, decline_reasons, last_full_month
from agent_qa.stats import fisher_two_sided, rate_string
from qa_fakes import AS_OF, SETTINGS, FakeSource, row
from schemas import (
    FirstTimeFixResult,
    GroupCount,
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


def failed(checks) -> set[str]:
    return {c.code for c in checks if not c.passed}


def request(metric="incident_count", **fields) -> ReportingRequest:
    return ReportingRequest(metric=metric, start=JULY[0], end=JULY[1], **fields)


def answer(
    figures, req=None, assumed=False, span=JULY, as_of=AS_OF, validate=True
) -> ReportingAnswer:
    """`validate=False` builds an answer the schema would refuse, to show QA catches it on its
    own: the checks do not rely on the schema's consistency rules."""
    build = ReportingAnswer if validate else ReportingAnswer.model_construct
    return build(
        request=req or request(figures.metric),
        start=span[0],
        end=span[1],
        range_assumed=assumed,
        as_of=as_of,
        figures=figures,
    )


def counts(low=93, medium=54, high=25):
    return {"low": low, "medium": medium, "high": high}


def summary(**fields) -> IncidentSummary:
    base = {
        "start": JULY[0],
        "end": JULY[1],
        "incident_count": 172,
        "by_severity": SeverityCounts(low=93, medium=54, high=25),
    }
    return IncidentSummary(**(base | fields))


def checker(**canned) -> Checker:
    return Checker(FakeSource(**canned), SETTINGS)


TEXT = "As of 2026-08-30: 172 incidents reported from 2026-07-01 to 2026-07-31 (inclusive, UTC)."


# --------------------------------------------------------------------------- the request rules


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"metric": "unsupported"}, {"unsupported_metric"}),
        ({"metric": "sla_compliance", "group_by": "unsupported"}, {"unsupported_breakdown"}),
        ({"metric": "sla_compliance", "group_by": "severity"}, {"breakdown_not_offered"}),
        ({"metric": "incident_rate", "group_by": "incident_type"}, {"breakdown_not_offered"}),
        ({"metric": "repeat_visit_drivers", "group_by": "severity"}, {"breakdown_not_offered"}),
        ({"metric": "incident_count", "region": "unsupported"}, {"unsupported_area"}),
        (
            {"metric": "repeat_visit_drivers", "region": "west"},
            {"repeat_region_or_account"},
        ),
        (
            {"metric": "repeat_visit_drivers", "account_name": "Bluewater"},
            {"repeat_region_or_account"},
        ),
        ({"metric": "repeat_visit_drivers", "technician_name": "Ben"}, {"repeat_technician"}),
        (
            {"metric": "incident_count", "region": "west", "group_by": "region"},
            {"region_same_dimension"},
        ),
        (
            {"metric": "incident_count", "account_name": "Bluewater", "group_by": "account"},
            {"account_same_dimension"},
        ),
        (
            {"metric": "sla_compliance", "technician_name": "Ben", "group_by": "region"},
            {"technician_breakdown"},
        ),
        # several reasons at once: every true one is reported, so any may be the one stated
        (
            {
                "metric": "repeat_visit_drivers",
                "region": "unsupported",
                "technician_name": "Ben",
                "group_by": "region",
            },
            {
                "unsupported_area",
                "repeat_region_or_account",
                "repeat_technician",
                "technician_breakdown",
            },
        ),
    ],
)
def test_the_rules_that_decline_a_request(fields, expected):
    assert decline_reasons(ReportingRequest(**fields)) == expected


@pytest.mark.parametrize(
    "fields",
    [
        {"metric": "incident_count"},
        {"metric": "incident_count", "group_by": "severity"},
        {"metric": "sla_compliance", "group_by": "region", "account_name": "Bluewater"},
        {"metric": "incident_rate", "region": "west", "group_by": "account"},
        {"metric": "incident_count", "technician_name": "Ben", "region": "west"},
        {"metric": "repeat_visit_drivers", "group_by": "technician"},
        {"metric": "repeat_visit_drivers"},
    ],
)
def test_supported_requests_have_no_decline_reason(fields):
    assert decline_reasons(ReportingRequest(**fields)) == set()


def test_the_default_range_is_the_last_full_calendar_month():
    assert last_full_month(dt.date(2026, 8, 30)) == JULY
    assert last_full_month(dt.date(2026, 1, 15)) == (dt.date(2025, 12, 1), dt.date(2025, 12, 31))
    assert last_full_month(dt.date(2026, 3, 1)) == (dt.date(2026, 2, 1), dt.date(2026, 2, 28))


# --------------------------------------------------------------------------- range and request


def test_a_correct_incident_count_passes_every_check():
    c = checker(severity_counts=counts())
    checks = c.check_answer(answer(summary()), TEXT)
    assert failed(checks) == set() and len(checks) == 5


def test_an_answer_for_a_request_that_must_be_declined_fails_first():
    figures = summary()
    req = request("incident_count", region="west", group_by="region")
    with pytest.raises(ValueError):  # the schema already refuses this combination
        answer(figures, req)


def test_a_range_that_differs_from_the_request_fails():
    c = checker(severity_counts=counts())
    other = answer(summary(), span=JULY).model_copy(
        update={"start": dt.date(2026, 6, 1), "end": dt.date(2026, 6, 30)}
    )
    assert "range_matches_request" in failed(c.check_answer(other, TEXT))


def test_an_assumed_range_must_be_the_last_full_month_of_the_as_of_date():
    req = ReportingRequest(metric="incident_count")
    good = answer(summary(), req, assumed=True)
    assert failed(checker(severity_counts=counts()).check_answer(good, TEXT)) == set()
    off = answer(
        summary(start=dt.date(2026, 6, 1), end=dt.date(2026, 6, 30)),
        req,
        assumed=True,
        span=(dt.date(2026, 6, 1), dt.date(2026, 6, 30)),
    )
    assert "range_matches_request" in failed(
        checker(severity_counts=counts()).check_answer(off, "")
    )


def test_a_different_as_of_date_fails():
    stale = answer(summary(), as_of=dt.date(2026, 8, 1))
    assert "range_matches_request" in failed(
        checker(severity_counts=counts()).check_answer(stale, "")
    )


def test_a_range_outside_the_dataset_window_fails():
    early = (dt.date(2023, 1, 1), dt.date(2023, 1, 31))
    figures = summary(start=early[0], end=early[1])
    req = ReportingRequest(metric="incident_count", start=early[0], end=early[1])
    checks = checker(severity_counts=counts()).check_answer(answer(figures, req, span=early), "")
    assert "range_matches_request" in failed(checks)


# --------------------------------------------------------------------------- incident counts


@pytest.mark.parametrize(
    ("figures", "code"),
    [
        (summary(incident_count=173, by_severity=SeverityCounts(low=94, medium=54, high=25)), None),
        (summary(by_severity=SeverityCounts(low=92, medium=55, high=25)), None),
    ],
)
def test_a_wrong_total_or_split_is_caught(figures, code):
    checks = checker(severity_counts=counts()).check_answer(answer(figures), "")
    assert "figures_match_database" in failed(checks)


def _count_groups(cap_more=0):
    names = [("b", 40), ("a", 40), ("c", 30)] + [(f"z{i:02d}", 1) for i in range(cap_more)]
    return [row(n, c, key=n) for n, c in names]


def test_count_groups_are_checked_in_order_with_ties_by_name():
    rows = _count_groups()
    total = sum(r.numerator for r in rows)
    figures = summary(
        incident_count=total,
        by_severity=SeverityCounts(low=total, medium=0, high=0),
        group_by="service_type",
        groups=[
            GroupCount(group="a", count=40),
            GroupCount(group="b", count=40),
            GroupCount(group="c", count=30),
        ],
        group_count=3,
    )
    req = request("incident_count", group_by="service_type")
    c = checker(
        severity_counts={"low": total, "medium": 0, "high": 0},
        count_groups=rows,
    )
    assert failed(c.check_answer(answer(figures, req), "")) - {"text_matches_data"} == set()
    swapped = figures.model_copy(
        update={
            "groups": [
                GroupCount(group="b", count=40),
                GroupCount(group="a", count=40),
                GroupCount(group="c", count=30),
            ]
        }
    )
    assert "figures_match_database" in failed(c.check_answer(answer(swapped, req), ""))


def test_count_groups_over_25_are_capped_and_flagged():
    rows = _count_groups(cap_more=27)  # 30 groups
    total = sum(r.numerator for r in rows)
    ordered = sorted(rows, key=lambda r: (-r.numerator, r.label))
    shown = [GroupCount(group=r.label, count=r.numerator) for r in ordered[:25]]
    figures = summary(
        incident_count=total,
        by_severity=SeverityCounts(low=total, medium=0, high=0),
        group_by="service_type",
        groups=shown,
        group_count=30,
        truncated=True,
    )
    req = request("incident_count", group_by="service_type")
    c = checker(severity_counts={"low": total, "medium": 0, "high": 0}, count_groups=rows)
    assert "figures_match_database" not in failed(c.check_answer(answer(figures, req), ""))
    wrong = figures.model_copy(update={"group_count": 29})
    assert "figures_match_database" in failed(c.check_answer(answer(wrong, req), ""))


def test_unattributed_technician_incidents_form_their_own_group():
    rows = [
        row("Ben Okafor", 10, group_id=9, key=9),
        row(UNATTRIBUTED, 4, group_id=None, key=None),
    ]
    figures = summary(
        incident_count=14,
        by_severity=SeverityCounts(low=14, medium=0, high=0),
        group_by="technician",
        groups=[
            GroupCount(group="Ben Okafor", group_id=9, count=10),
            GroupCount(group=UNATTRIBUTED, count=4),
        ],
        group_count=2,
    )
    req = request("incident_count", group_by="technician")
    c = checker(severity_counts={"low": 14, "medium": 0, "high": 0}, count_groups=rows)
    assert "figures_match_database" not in failed(c.check_answer(answer(figures, req), ""))


# --------------------------------------------------------------------------- rate metrics


def sla_figures(**fields) -> SlaComplianceResult:
    base = {"start": JULY[0], "end": JULY[1], "numerator": 461, "denominator": 508}
    base["rate"] = rate_string(base["numerator"], base["denominator"])
    return SlaComplianceResult(**(base | fields))


def test_a_correct_sla_total_passes_and_a_wrong_one_fails():
    c = checker(metric_counts=(461, 508))
    good = answer(sla_figures())
    assert "figures_match_database" not in failed(c.check_answer(good, ""))
    bad = answer(sla_figures(numerator=460, rate=rate_string(460, 508)))
    assert "figures_match_database" in failed(c.check_answer(bad, ""))
    wrong_rate = answer(sla_figures(rate="0.9999"))
    assert "figures_match_database" in failed(c.check_answer(wrong_rate, ""))


def test_incident_rate_is_per_100_completed_requests():
    figures = IncidentRateResult(
        start=JULY[0],
        end=JULY[1],
        numerator=54,
        denominator=510,
        rate=rate_string(54, 510, 100),
    )
    c = checker(metric_counts=(54, 510))
    assert "figures_match_database" not in failed(c.check_answer(answer(figures), ""))
    unscaled = figures.model_copy(update={"rate": rate_string(54, 510)})
    assert "figures_match_database" in failed(c.check_answer(answer(unscaled), ""))


def group_rate(label, num, den, scale=1, gid=None):
    return GroupRate(
        group=label, group_id=gid, numerator=num, denominator=den, rate=rate_string(num, den, scale)
    )


def ftf(groups, group_count=None, truncated=False, group_by="region") -> FirstTimeFixResult:
    return FirstTimeFixResult(
        start=JULY[0],
        end=JULY[1],
        numerator=9,
        denominator=10,
        rate=rate_string(9, 10),
        group_by=group_by,
        groups=groups,
        group_count=len(groups) if group_count is None else group_count,
        truncated=truncated,
    )


def ftf_checker(rows):
    return checker(metric_counts=(9, 10), metric_groups=rows)


def test_rate_groups_are_ranked_lowest_first_for_a_rate_where_higher_is_better():
    rows = [row("west", 8, 10), row("east", 9, 10), row("north", 10, 10)]
    ordered = [group_rate("west", 8, 10), group_rate("east", 9, 10), group_rate("north", 10, 10)]
    req = request("first_time_fix_rate", group_by="region")
    c = ftf_checker(rows)
    assert "figures_match_database" not in failed(c.check_answer(answer(ftf(ordered), req), ""))
    backwards = list(reversed(ordered))
    assert "figures_match_database" in failed(c.check_answer(answer(ftf(backwards), req), ""))


def test_tied_rates_may_come_in_either_order():
    rows = [row("a", 8, 10), row("b", 8, 10), row("c", 9, 10)]
    req = request("first_time_fix_rate", group_by="region")
    c = ftf_checker(rows)
    for order in (("a", "b", "c"), ("b", "a", "c")):
        groups = [group_rate(n, *{"a": (8, 10), "b": (8, 10), "c": (9, 10)}[n]) for n in order]
        assert "figures_match_database" not in failed(c.check_answer(answer(ftf(groups), req), ""))


def test_a_group_with_no_rate_must_come_last():
    rows = [row("a", 0, 0), row("b", 5, 10)]
    req = request("first_time_fix_rate", group_by="region")
    c = ftf_checker(rows)
    last = [group_rate("b", 5, 10), group_rate("a", 0, 0)]
    assert "figures_match_database" not in failed(c.check_answer(answer(ftf(last), req), ""))
    first = list(reversed(last))
    assert "figures_match_database" in failed(c.check_answer(answer(ftf(first), req), ""))


def test_a_group_the_database_does_not_have_is_caught():
    rows = [row("a", 8, 10)]
    req = request("first_time_fix_rate", group_by="region")
    groups = [group_rate("ghost", 8, 10)]
    assert "figures_match_database" in failed(
        ftf_checker(rows).check_answer(answer(ftf(groups), req), "")
    )


def test_a_cutoff_that_kept_a_better_group_over_a_worse_one_is_caught():
    rows = [row(f"g{i:02d}", i, 100) for i in range(30)]
    best_first = sorted(rows, key=lambda r: (r.numerator / r.denominator, r.label))
    kept = best_first[:25]
    groups = [group_rate(r.label, r.numerator, r.denominator) for r in kept]
    req = request("first_time_fix_rate", group_by="region")
    c = ftf_checker(rows)
    good = ftf(groups, group_count=30, truncated=True)
    assert "figures_match_database" not in failed(c.check_answer(answer(good, req), ""))
    # keep the 26th-worst group instead of the 25th: a worse group was cut
    swapped = groups[:-1] + [group_rate(best_first[25].label, best_first[25].numerator, 100)]
    bad = ftf(swapped, group_count=30, truncated=True)
    assert "figures_match_database" in failed(c.check_answer(answer(bad, req), ""))


def test_group_count_and_truncation_flag_are_checked():
    rows = [row("a", 8, 10)]
    req = request("first_time_fix_rate", group_by="region")
    groups = [group_rate("a", 8, 10)]
    assert "figures_match_database" in failed(
        ftf_checker(rows).check_answer(answer(ftf(groups, group_count=2, truncated=True), req), "")
    )


# --------------------------------------------------------------------------- filters


def test_a_technician_filter_must_be_the_technician_the_name_picks_out():
    figures = summary(technician_id=9, technician_name="Ben Okafor")
    c = checker(severity_counts=counts())
    ok_req = request("incident_count", technician_name="Ben Okafor")
    assert "filters_match_request" not in failed(c.check_answer(answer(figures, ok_req), TEXT))
    wrong = summary(technician_id=7, technician_name="Priya Kim")
    assert "filters_match_request" in failed(c.check_answer(answer(wrong, ok_req), ""))
    ambiguous = request("incident_count", technician_name="Priya")
    assert "filters_match_request" in failed(c.check_answer(answer(wrong, ambiguous), ""))


def test_an_account_filter_must_be_the_account_the_name_picks_out():
    c = checker(severity_counts=counts())
    figures = summary(account_id=5, account_name="Cedar Ridge Retail Inc.")
    ok_req = request("incident_count", account_name="Cedar Ridge Retail")
    assert "filters_match_request" not in failed(c.check_answer(answer(figures, ok_req), TEXT))
    other = summary(account_id=3, account_name="Bluewater Energy Inc.")
    assert "filters_match_request" in failed(c.check_answer(answer(other, ok_req), ""))
    renamed = summary(account_id=5, account_name="Cedar Ridge Retail")
    assert "filters_match_request" in failed(c.check_answer(answer(renamed, ok_req), ""))


def test_a_filter_the_request_did_not_ask_for_is_caught():
    c = checker(severity_counts=counts())
    extra = summary(region="west")
    assert "filters_match_request" in failed(c.check_answer(answer(extra, validate=False), ""))


def test_a_breakdown_the_request_did_not_ask_for_is_caught():
    c = checker(severity_counts=counts(), count_groups=[row("a", 172, key="a")])
    grouped = summary(
        group_by="severity", groups=[GroupCount(group="low", count=172)], group_count=1
    )
    plain_req = request("incident_count")
    assert "filters_match_request" in failed(
        c.check_answer(answer(grouped, plain_req, validate=False), "")
    )


# --------------------------------------------------------------------------- repeat drivers


def jobs(spec):
    """spec: list of (service_type, repeated) -> job dicts and an empty type map."""
    out = []
    for i, (service, repeated) in enumerate(spec):
        out.append(
            {
                "request_id": i,
                "service_type": service,
                "region": "west",
                "account_id": 1,
                "account_name": "A",
                "technician_id": None,
                "technician_name": None,
                "repeated": repeated,
            }
        )
    return out


def test_fisher_matches_scipy_including_ties():
    scipy_stats = pytest.importorskip("scipy.stats")
    for table in [
        (3, 17, 9, 111),
        (0, 20, 5, 95),
        (12, 8, 8, 12),
        (30, 70, 10, 90),
        (1, 49, 1, 49),
    ]:
        want = scipy_stats.fisher_exact([[table[0], table[1]], [table[2], table[3]]])[1]
        assert fisher_two_sided(*table) == pytest.approx(want, rel=1e-6, abs=1e-12)


def test_a_group_stands_out_only_when_big_enough_higher_and_significant_after_bonferroni():
    spec = [("repair", True)] * 15 + [("repair", False)] * 15  # 30 jobs, 50% repeat
    spec += [("install", True)] * 5 + [("install", False)] * 295  # 300 jobs, ~1.7%
    spec += [("upgrade", True)] * 3 + [("upgrade", False)] * 7  # 10 jobs: too few to compare
    out = compute(jobs(spec), {}, "service_type")
    by = {g.label: g for g in out.groups}
    assert out.groups_compared == 2 and out.overall.jobs == 340
    assert by["upgrade"].compared is False and by["upgrade"].p_value is None
    assert by["repair"].stands_out is True and by["install"].stands_out is False
    assert by["repair"].p_adjusted == pytest.approx(min(1.0, by["repair"].p_value * 2))
    assert [g.label for g in out.groups] == ["repair", "upgrade", "install"]  # rate, jobs, name


def test_repeat_group_order_breaks_rate_ties_by_jobs_then_name():
    spec = [("b", True), ("b", False)] * 2 + [("a", True), ("a", False)] * 2
    spec += [("c", True), ("c", False)]
    out = compute(jobs(spec), {}, "service_type")
    labels = [g.label for g in out.groups]
    assert labels == ["a", "b", "c"]
    # all 50%: the larger groups (a and b, 4 jobs each) first, tied on jobs so by name, then c


def test_incident_type_groups_exclude_the_defining_type_and_add_the_any_other_comparison():
    js = jobs([("repair", i % 4 == 0) for i in range(120)])
    types = {}
    for j in js:
        if j["request_id"] % 3 == 0:
            types[j["request_id"]] = {"missed_sla"}
        elif j["request_id"] % 5 == 0:
            types[j["request_id"]] = {"repeat_visit_required", "equipment_damage"}
        else:
            types[j["request_id"]] = {"repeat_visit_required"}
    out = compute(js, types, "incident_type")
    assert {g.label for g in out.groups} == {"missed_sla", "equipment_damage"}
    a, b, compared, p, higher = out.other
    assert a.jobs + b.jobs == 120 and compared and 0 <= p <= 1
    assert higher == (a.repeated * b.jobs > b.repeated * a.jobs and p < 0.05)


def repeat_answer(by="service_type", **fields):
    spec = [("repair", True)] * 15 + [("repair", False)] * 15 + [("install", True)] * 5
    spec += [("install", False)] * 295
    out = compute(jobs(spec), {}, by)
    groups = [
        RepeatGroup(
            group=g.label,
            group_id=g.group_id,
            this=JobsRepeated(jobs=g.this.jobs, repeated=g.this.repeated, rate=g.this.rate),
            rest=JobsRepeated(jobs=g.rest.jobs, repeated=g.rest.repeated, rate=g.rest.rate),
            compared=g.compared,
            p_value=g.p_value,
            p_adjusted=g.p_adjusted,
            stands_out=g.stands_out,
        )
        for g in out.groups
    ]
    result = RepeatDriversResult(
        start=JULY[0],
        end=JULY[1],
        group_by=by,
        overall=JobsRepeated(
            jobs=out.overall.jobs, repeated=out.overall.repeated, rate=out.overall.rate
        ),
        groups=groups,
        group_count=len(groups),
        groups_compared=out.groups_compared,
    )
    return result.model_copy(update=fields), jobs(spec)


def test_repeat_drivers_match_when_computed_the_same_way_and_catch_each_kind_of_change():
    figures, js = repeat_answer()
    req = request("repeat_visit_drivers", group_by="service_type")
    c = checker(repeat_jobs=(js, {}))
    assert "figures_match_database" not in failed(c.check_answer(answer(figures, req), ""))

    flipped = [g.model_copy(update={"stands_out": not g.stands_out}) for g in figures.groups[:1]]
    for update in (
        {"groups": flipped + figures.groups[1:]},
        {"groups_compared": 3},
        {"overall": JobsRepeated(jobs=340, repeated=29, rate=rate_string(29, 340))},
        {"groups": list(reversed(figures.groups))},
        {"group_count": 3},
    ):
        wrong = figures.model_copy(update=update)
        try:
            checks = c.check_answer(answer(wrong, req), "")
        except ValueError:
            continue
        assert "figures_match_database" in failed(checks), update


def test_a_wrong_p_value_is_caught():
    figures, js = repeat_answer()
    req = request("repeat_visit_drivers", group_by="service_type")
    first = figures.groups[0]
    wrong = figures.model_copy(
        update={"groups": [first.model_copy(update={"p_value": 0.5}), *figures.groups[1:]]}
    )
    assert "figures_match_database" in failed(
        checker(repeat_jobs=(js, {})).check_answer(answer(wrong, req), "")
    )


def test_an_incident_type_with_no_job_may_be_listed_with_zero_jobs_or_left_out():
    js = jobs([("repair", i % 4 == 0) for i in range(80)])
    types = {j["request_id"]: {"missed_sla"} for j in js}
    out = compute(js, types, "incident_type")
    a, b, compared, p, higher = out.other
    groups = [
        RepeatGroup(
            group=g.label,
            this=JobsRepeated(jobs=g.this.jobs, repeated=g.this.repeated, rate=g.this.rate),
            rest=JobsRepeated(jobs=g.rest.jobs, repeated=g.rest.repeated, rate=g.rest.rate),
            compared=g.compared,
            p_value=g.p_value,
            p_adjusted=g.p_adjusted,
            stands_out=g.stands_out,
        )
        for g in out.groups
    ]
    zero = RepeatGroup(
        group="billing_dispute",
        this=JobsRepeated(jobs=0, repeated=0, rate=None),
        rest=JobsRepeated(jobs=80, repeated=20, rate=rate_string(20, 80)),
        compared=False,
        stands_out=False,
    )

    def figures(gs, count):
        return RepeatDriversResult(
            start=JULY[0],
            end=JULY[1],
            group_by="incident_type",
            overall=JobsRepeated(jobs=80, repeated=20, rate=rate_string(20, 80)),
            groups=gs,
            group_count=count,
            groups_compared=out.groups_compared,
            any_other_incident=JobsRepeated(jobs=a.jobs, repeated=a.repeated, rate=a.rate),
            no_other_incident=JobsRepeated(jobs=b.jobs, repeated=b.repeated, rate=b.rate),
            other_incident_compared=compared,
            other_incident_p_value=p,
            other_incident_higher=higher,
        )

    req = request("repeat_visit_drivers", group_by="incident_type")
    c = checker(repeat_jobs=(js, types))
    for gs, count in ((groups, len(groups)), (groups + [zero], len(groups) + 1)):
        assert "figures_match_database" not in failed(
            c.check_answer(answer(figures(gs, count), req), "")
        )


# --------------------------------------------------------------------------- the text


def test_text_must_state_the_headline_number():
    c = checker(severity_counts=counts())
    silent = "As of 2026-08-30: incidents reported from 2026-07-01 to 2026-07-31."
    assert "text_matches_data" in failed(c.check_answer(answer(summary()), silent))


def test_text_with_a_number_that_is_in_no_figure_is_caught():
    c = checker(severity_counts=counts())
    stale = TEXT + " That is 7,777 high severity."
    assert "text_matches_data" in failed(c.check_answer(answer(summary()), stale))


def test_text_stating_another_date_is_caught():
    c = checker(severity_counts=counts())
    other = TEXT.replace("2026-07-01", "2026-06-01")
    assert "text_matches_data" in failed(c.check_answer(answer(summary()), other))


def test_a_name_with_a_digit_is_not_mistaken_for_a_figure():
    figures = summary(account_id=5, account_name="Cedar Ridge 3M Retail")
    accounts = [(5, "Cedar Ridge 3M Retail")]
    c = Checker(FakeSource(severity_counts=counts(), accounts=accounts), SETTINGS)
    req = request("incident_count", account_name="Cedar Ridge 3M Retail")
    assert req.account_name
    text = TEXT.replace("172 incidents", "172 incidents for Cedar Ridge 3M Retail")
    assert "text_matches_data" not in failed(c.check_answer(answer(figures, req), text))


def test_the_text_check_is_skipped_when_a_figures_check_already_failed():
    c = checker(severity_counts=counts(low=1))
    checks = c.check_answer(answer(summary()), "garbage 999")
    assert "text_matches_data" not in {x.code for x in checks}


# --------------------------------------------------------------------------- declines


def test_a_not_supported_decline_must_state_a_reason_that_applies():
    c = checker()
    req = ReportingRequest(metric="unsupported")
    text = "That metric isn't supported yet. I can report incident counts."
    assert failed(c.check_decline(req, "not_supported", text)) == set()
    wrong_reason = "That breakdown isn't supported yet. I can report incident counts."
    assert "decline_matches_reason" in failed(c.check_decline(req, "not_supported", wrong_reason))
    unknown = "Sorry."
    assert "decline_matches_reason" in failed(c.check_decline(req, "not_supported", unknown))


def test_a_decline_of_a_request_that_could_be_answered_is_caught():
    c = checker()
    req = ReportingRequest(metric="incident_count")
    text = "That metric isn't supported yet."
    assert "decline_matches_reason" in failed(c.check_decline(req, "not_supported", text))


@pytest.mark.parametrize(
    ("fields", "text"),
    [
        (
            {"metric": "incident_count", "region": "unsupported"},
            "I can only restrict a question to one of four regions: northeast, southeast, "
            "central or west.",
        ),
        (
            {"metric": "repeat_visit_drivers", "region": "west"},
            "Repeat-visit drivers can't be filtered to one region or account yet.",
        ),
        (
            {"metric": "incident_count", "region": "west", "group_by": "region"},
            "A single region's figures can't also be broken down by region.",
        ),
        (
            {"metric": "sla_compliance", "technician_name": "Ben", "group_by": "region"},
            "A single technician's figures can't also be broken down.",
        ),
    ],
)
def test_each_unsupported_class_is_recognised_in_its_text(fields, text):
    assert (
        failed(checker().check_decline(ReportingRequest(**fields), "not_supported", text)) == set()
    )


def test_a_decline_text_carrying_a_number_fails_the_no_figures_check():
    req = ReportingRequest(metric="unsupported")
    text = "That metric isn't supported yet. We had 172 incidents last month."
    assert "decline_no_figures" in failed(checker().check_decline(req, "not_supported", text))


def test_a_not_found_decline_is_true_only_when_the_name_matches_nobody():
    c = checker()
    gone = ReportingRequest(metric="sla_compliance", technician_name="Dave")
    assert (
        failed(c.check_decline(gone, "technician_not_found", "No technician matches Dave."))
        == set()
    )
    there = ReportingRequest(metric="sla_compliance", technician_name="Ben")
    assert "decline_matches_reason" in failed(
        c.check_decline(there, "technician_not_found", "No technician matches Ben.")
    )
    pattern = ReportingRequest(metric="sla_compliance", technician_name="P%")
    assert (
        failed(c.check_decline(pattern, "technician_not_found", "No technician matches P%."))
        == set()
    )
    digits = ReportingRequest(metric="sla_compliance", technician_name="R2D2")
    assert (
        failed(c.check_decline(digits, "technician_not_found", "No technician matches R2D2."))
        == set()
    )


def test_an_ambiguous_decline_must_state_the_true_count_and_list_real_matches():
    c = checker()
    req = ReportingRequest(metric="sla_compliance", technician_name="Priya")
    good = (
        "2 technicians match Priya: Priya Castillo and Priya Kim. "
        "Please ask again with the full name."
    )
    assert failed(c.check_decline(req, "technician_ambiguous", good)) == set()
    wrong_count = good.replace("2 technicians", "3 technicians")
    assert "decline_matches_reason" in failed(
        c.check_decline(req, "technician_ambiguous", wrong_count)
    )
    missing = "2 technicians match Priya: Priya Castillo and Someone Else."
    assert "decline_matches_reason" in failed(c.check_decline(req, "technician_ambiguous", missing))
    single = ReportingRequest(metric="sla_compliance", technician_name="Ben")
    assert "decline_matches_reason" in failed(
        c.check_decline(single, "technician_ambiguous", "1 technicians match Ben: Ben Okafor.")
    )


def test_account_declines_use_the_account_list():
    c = checker()
    req = ReportingRequest(metric="sla_compliance", account_name="Bluewater")
    text = (
        "2 accounts match Bluewater: Bluewater Energy Inc. and Bluewater Hospitality Partners. "
        "Please ask again with the full name."
    )
    assert failed(c.check_decline(req, "account_ambiguous", text)) == set()
    nobody = ReportingRequest(metric="sla_compliance", account_name="Acme Corp")
    assert (
        failed(c.check_decline(nobody, "account_not_found", "No account matches Acme Corp."))
        == set()
    )
    assert "decline_matches_reason" in failed(
        c.check_decline(req, "account_not_found", "No account matches Bluewater.")
    )


def test_a_decline_code_qa_does_not_know_fails():
    checks = checker().check_decline(ReportingRequest(metric="unsupported"), "tool_error", "x")
    assert failed(checks) == {"decline_matches_reason"}


def test_the_decline_phrases_cover_every_reason_class():
    assert set(reporting.DECLINE_PHRASES) == {
        "unsupported_metric",
        "unsupported_breakdown",
        "breakdown_not_offered",
        "unsupported_area",
        "repeat_region_or_account",
        "repeat_technician",
        "region_same_dimension",
        "account_same_dimension",
        "technician_breakdown",
    }


def test_a_group_that_is_every_job_is_not_checked_for_significance_but_its_counts_are():
    """§6 is silent on a group with no 'rest' (L-72): the significance fields are not compared,
    the counts and rates still are."""
    spec = [("repair", True)] * 6 + [("repair", False)] * 24
    js = jobs(spec)
    group = RepeatGroup(
        group="repair",
        this=JobsRepeated(jobs=30, repeated=6, rate=rate_string(6, 30)),
        rest=JobsRepeated(jobs=0, repeated=0, rate=None),
        compared=False,  # the specialist's reading; QA's would say compared
        stands_out=False,
    )
    figures = RepeatDriversResult(
        start=JULY[0],
        end=JULY[1],
        group_by="service_type",
        overall=JobsRepeated(jobs=30, repeated=6, rate=rate_string(6, 30)),
        groups=[group],
        group_count=1,
        groups_compared=0,
    )
    req = request("repeat_visit_drivers", group_by="service_type")
    c = checker(repeat_jobs=(js, {}))
    assert "figures_match_database" not in failed(c.check_answer(answer(figures, req), ""))
    wrong = figures.model_copy(
        update={
            "groups": [
                group.model_copy(
                    update={"this": JobsRepeated(jobs=30, repeated=7, rate=rate_string(7, 30))}
                )
            ]
        }
    )
    assert "figures_match_database" in failed(c.check_answer(answer(wrong, req), ""))
