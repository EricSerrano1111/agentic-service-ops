"""Offline tests for the repeat-visit drivers computation and technician name matching
(ADR-073). The live queries are covered by tests/integration/test_mcp_metrics_figures.py.
"""

from __future__ import annotations

import datetime as dt
import random

import pytest
from mcp_incidents.queries import InvalidArgument, match_technicians
from mcp_incidents.repeats import compute, fisher_exact
from scipy.stats import fisher_exact as scipy_fisher

START, END = dt.date(2024, 1, 1), dt.date(2024, 3, 31)

# --------------------------------------------------------------------------- Fisher's test


def _scipy(a, b, c, d) -> float:
    return float(scipy_fisher([[a, b], [c, d]], alternative="two-sided").pvalue)


def test_fisher_matches_scipy_on_random_tables():
    rng = random.Random(73)
    for _ in range(400):
        table = [rng.randint(0, 40) for _ in range(4)]
        assert fisher_exact(*table) == pytest.approx(_scipy(*table), rel=1e-9, abs=1e-12)


@pytest.mark.parametrize(
    "table",
    [
        (14, 558, 8, 1096),  # 2026 Q2 repair against the rest
        (103, 1406, 261, 16293),  # a full-window incident-type comparison
        (0, 37, 22, 1617),
        (3, 0, 0, 3),
        (0, 0, 0, 0),
        (5, 5, 5, 5),
        (0, 20, 0, 1000),
    ],
)
def test_fisher_matches_scipy_on_edge_and_realistic_tables(table):
    assert fisher_exact(*table) == pytest.approx(_scipy(*table), rel=1e-9, abs=1e-12)


# --------------------------------------------------------------------------- drivers


def _row(i, repeated, *, service="repair", region="west", account=1, tech=1, types=()):
    return {
        "request_id": i,
        "service_type": service,
        "region": region,
        "account_id": account,
        "account_name": f"Account {account}",
        "assigned_technician_id": tech,
        "full_name": None if tech is None else f"Tech {tech}",
        "repeated": repeated,
        "types": set(types),
    }


def _jobs(n, repeated, start=0, **kw):
    return [_row(start + i, i < repeated, **kw) for i in range(n)]


def test_a_clear_difference_stands_out_and_is_listed_first():
    rows = _jobs(100, 30, service="repair") + _jobs(400, 4, start=100, service="install")
    r = compute(rows, START, END, "service_type")
    assert r.overall.jobs == 500 and r.overall.repeated == 34 and r.overall.rate == "0.0680"
    assert [g.group for g in r.groups] == ["repair", "install"]  # worst first
    repair = r.groups[0]
    assert repair.stands_out and repair.compared and repair.p_adjusted < 0.05
    assert repair.rest.jobs == 400 and repair.rest.repeated == 4
    # The lower group differs just as significantly, but a lower rate never stands out.
    assert not r.groups[1].stands_out
    assert r.groups_compared == 2


def test_noise_does_not_stand_out_but_is_still_listed_worst_first():
    rows = _jobs(200, 5, region="west") + _jobs(200, 3, start=200, region="east")
    r = compute(rows, START, END, "region")
    assert [g.group for g in r.groups] == ["west", "east"]
    assert not any(g.stands_out for g in r.groups)


def test_groups_under_20_jobs_are_listed_but_never_compared():
    rows = _jobs(19, 19, service="upgrade") + _jobs(500, 5, start=100, service="install")
    r = compute(rows, START, END, "service_type")
    upgrade = next(g for g in r.groups if g.group == "upgrade")
    assert r.groups[0].group == "upgrade"  # still worst first
    assert not upgrade.compared and upgrade.p_value is None and not upgrade.stands_out
    assert r.groups_compared == 1


def test_bonferroni_multiplies_by_the_number_of_groups_compared():
    rows = []
    for k in range(4):
        rows += _jobs(50, 2 + k, start=100 * k, account=k + 1)
    rows += _jobs(10, 1, start=900, account=9)  # under 20: not counted
    r = compute(rows, START, END, "account")
    assert r.groups_compared == 4
    for g in r.groups:
        if g.compared:
            assert g.p_adjusted == pytest.approx(min(1.0, g.p_value * 4))
            assert g.group_id is not None


def test_incident_type_leaves_out_the_defining_type_and_compares_any_other():
    rows = (
        _jobs(40, 8, types=("repeat_visit_required", "billing_dispute"))
        + _jobs(60, 0, start=100, types=("missed_sla",))
        + _jobs(400, 6, start=200, types=())
    )
    # A repeat whose original only has repeat_visit_required counts as "none other".
    rows += [_row(900, True, types=("repeat_visit_required",))]
    r = compute(rows, START, END, "incident_type")
    assert {g.group for g in r.groups} == {"billing_dispute", "missed_sla"}
    billing = r.groups[0]
    assert billing.group == "billing_dispute" and billing.this.jobs == 40
    assert billing.rest.jobs == 461 and billing.rest.repeated == 7
    assert r.any_other_incident.jobs == 100 and r.any_other_incident.repeated == 8
    assert r.no_other_incident.jobs == 401 and r.no_other_incident.repeated == 7


def test_unassigned_jobs_are_their_own_technician_group():
    rows = _jobs(30, 1, tech=None) + _jobs(30, 1, start=100, tech=4)
    r = compute(rows, START, END, "technician")
    assert {(g.group, g.group_id) for g in r.groups} == {("unassigned", None), ("Tech 4", 4)}


def test_more_than_25_groups_are_cut_after_ranking():
    rows = []
    for k in range(30):
        rows += _jobs(20, k % 5, start=100 * k, account=k + 1)
    r = compute(rows, START, END, "account")
    assert r.group_count == 30 and len(r.groups) == 25 and r.truncated
    # Six groups at each of 0..4 repeats: the five cut are all from the best level.
    assert r.groups[0].this.repeated == 4
    assert sum(g.this.repeated == 0 for g in r.groups) == 1


def test_an_empty_range_has_a_null_rate_and_no_groups():
    r = compute([], START, END, "region")
    assert r.overall.jobs == 0 and r.overall.rate is None and r.groups == []


# --------------------------------------------------------------------------- name matching

TECHS = [
    (1, "Priya Kim"),
    (2, "Priya Castillo"),
    (3, "Ben Okafor"),
    (4, "Dan O'Neil"),
    (5, "Ana-Lucia Reyes"),
] + [(10 + i, f"Sam Number{chr(65 + i)}") for i in range(7)]


@pytest.mark.parametrize(
    ("name", "found"),
    [
        ("Nobody", []),
        ("Pri", []),  # whole words only
        ("Priya Kim", ["Priya Kim"]),
        ("kim priya", ["Priya Kim"]),
        ("PRIYA", ["Priya Castillo", "Priya Kim"]),
        ("O'Neil", ["Dan O'Neil"]),
        ("Ana-Lucia", ["Ana-Lucia Reyes"]),
    ],
)
def test_matching_is_case_insensitive_and_by_whole_word(name, found):
    result = match_technicians(name, TECHS)
    assert [m.full_name for m in result.matches] == found
    assert result.total_matches == len(found)


def test_at_most_five_matches_are_returned_with_the_total():
    result = match_technicians("Sam", TECHS)
    assert len(result.matches) == 5 and result.total_matches == 7


@pytest.mark.parametrize(
    "name", ["", "   ", "%", "Pri%", "_", "Pri_a", "*", "?", "[a]", "a\\b", "^Priya$", "1", "a;b"]
)
def test_patterns_and_non_name_characters_are_rejected(name):
    with pytest.raises(InvalidArgument, match="wildcards"):
        match_technicians(name, TECHS)
