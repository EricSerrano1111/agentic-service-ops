"""The owner's 2026-10-09 rulings on data dictionary §6 (L-72), pinned on the incidents tools:
tie order at the 25-group cap, a repeat-driver group that is every job, incident types with no
job, and the words of a name. The live figures are in tests/integration/test_qa_agrees_with_tools.py
and test_section6_rulings_figures.py."""

from __future__ import annotations

import datetime as dt

import pytest
from mcp_incidents.metrics import _Counts, _rank
from mcp_incidents.queries import match_accounts, match_technicians
from mcp_incidents.repeats import compute

START, END = dt.date(2024, 1, 1), dt.date(2024, 3, 31)


# ----------------------------------------------------------- ruling 2: ties at the cap


def _tied(denominators: dict[str, int]):
    nums = {k: _Counts(k, k, d) for k, d in denominators.items()}  # every job a success: rate 1.0
    dens = {k: _Counts(k, k, d) for k, d in denominators.items()}
    return nums, dens


def test_equal_rates_are_ordered_by_larger_denominator_then_name():
    nums, dens = _tied({"b": 5, "a": 5, "big": 50, "mid": 20})
    groups, _ = _rank(nums, dens, "region", 1, higher_is_worse=False)
    assert [g.group for g in groups] == ["big", "mid", "a", "b"]


def test_the_tie_at_the_cap_keeps_the_group_resting_on_more_jobs():
    """First-time fix by account, 2026-08-01 to 08-30: 39 accounts tie at 1.0000. Ordering ties by
    name alone cut Summit Distribution Co. (34 of 34 jobs); it must be in the 25 shown."""
    sizes = {f"Account {i:02d}": 3 + i % 5 for i in range(38)}
    sizes["Summit Distribution Co."] = 34
    sizes["Pinecrest Manufacturing Group"] = 50
    nums, dens = _tied(sizes)
    groups, total = _rank(nums, dens, "region", 1, higher_is_worse=False)
    names = [g.group for g in groups]
    assert total == 40 and len(groups) == 25
    assert names[:2] == ["Pinecrest Manufacturing Group", "Summit Distribution Co."]
    # then the 23 largest of the rest, larger first and by name within a size
    assert [g.denominator for g in groups] == sorted((g.denominator for g in groups), reverse=True)


def test_a_worse_rate_still_beats_a_larger_denominator():
    nums = {"low": _Counts("low", "low", 5), "high": _Counts("high", "high", 90)}
    dens = {"low": _Counts("low", "low", 10), "high": _Counts("high", "high", 100)}
    groups, _ = _rank(nums, dens, "region", 1, higher_is_worse=False)
    assert [g.group for g in groups] == ["low", "high"]  # 0.5 before 0.9


def test_groups_with_no_rate_come_last_ordered_by_name():
    nums, dens = _tied({"a": 4, "z": 9})
    nums["n2"], dens["n2"] = _Counts("n2", "n2", 0), _Counts("n2", "n2", 0)
    nums["n1"], dens["n1"] = _Counts("n1", "n1", 0), _Counts("n1", "n1", 0)
    groups, _ = _rank(nums, dens, "region", 1, higher_is_worse=False)
    assert [g.group for g in groups] == ["z", "a", "n1", "n2"]
    assert groups[-1].rate is None


# ----------------------------------------------------------- rulings 3 and 4: drivers


def _row(i, repeated, service="repair", types=()):
    return {
        "request_id": i,
        "service_type": service,
        "region": "west",
        "account_id": 1,
        "account_name": "Account 1",
        "assigned_technician_id": 1,
        "full_name": "Tech 1",
        "repeated": repeated,
        "types": set(types),
    }


def test_a_group_that_is_every_job_is_listed_with_its_rate_but_not_compared():
    rows = [_row(i, i < 6) for i in range(30)]  # 30 repair jobs, 6 repeated, nothing else
    r = compute(rows, START, END, "service_type")
    [g] = r.groups
    assert (g.this.jobs, g.this.repeated, g.this.rate) == (30, 6, "0.2000")
    assert g.rest.jobs == 0 and g.rest.rate is None
    assert g.compared is False and g.p_value is None and g.p_adjusted is None
    assert g.stands_out is False and r.groups_compared == 0 and r.group_count == 1


def test_a_group_with_no_rest_is_left_out_of_the_bonferroni_count():
    """Two regions: the big one is every job of its kind in the range only when alone, so build a
    range with one group of 30 plus a 25-job group; the multiplier is the groups compared (2)."""
    rows = [_row(i, i < 15) for i in range(30)] + [
        _row(100 + i, i < 1, service="install") for i in range(25)
    ]
    r = compute(rows, START, END, "service_type")
    assert r.groups_compared == 2
    by = {g.group: g for g in r.groups}
    assert by["repair"].p_adjusted == pytest.approx(min(1.0, by["repair"].p_value * 2))


def test_incident_types_with_no_job_in_the_range_are_not_listed():
    rows = [_row(i, i % 4 == 0, types={"missed_sla"}) for i in range(40)]
    r = compute(rows, START, END, "incident_type")
    assert [g.group for g in r.groups] == ["missed_sla"] and r.group_count == 1


# ----------------------------------------------------------- ruling 5: name words

ACCOUNTS = [
    (1, "Summit Distribution Co."),
    (2, "Summit Properties Partners"),
    (3, "Redstone Logistics Co."),
    (4, "Mary-Ann Foods LLC"),
]


@pytest.mark.parametrize(
    ("query", "found"),
    [
        ("Summit Distribution Co", ["Summit Distribution Co."]),  # the example that found 0
        ("Summit Distribution Co.", ["Summit Distribution Co."]),
        ("summit distribution co", ["Summit Distribution Co."]),
        ("Co", ["Redstone Logistics Co.", "Summit Distribution Co."]),
        ("Co.", ["Redstone Logistics Co.", "Summit Distribution Co."]),
        ("Mary-Ann", ["Mary-Ann Foods LLC"]),  # inner punctuation stays
        ("Mary", []),  # so a part of a hyphenated word is not a word
        ("Summit Distr", []),
    ],
)
def test_account_words_ignore_leading_and_trailing_punctuation(query, found):
    result = match_accounts(query, ACCOUNTS)
    assert [m.account_name for m in result.matches] == found and result.total_matches == len(found)


def test_technician_words_follow_the_same_rule():
    techs = [(1, "Priya Kim"), (2, "Dan O'Neil"), (3, "St. John Reyes")]
    assert [m.full_name for m in match_technicians("St John", techs).matches] == ["St. John Reyes"]
    assert [m.full_name for m in match_technicians("St. John Reyes.", techs).matches] == [
        "St. John Reyes"
    ]
    assert [m.full_name for m in match_technicians("O'Neil", techs).matches] == ["Dan O'Neil"]
    assert match_technicians("Neil", techs).total_matches == 0


def test_pattern_characters_are_still_rejected():
    from mcp_incidents.queries import InvalidArgument

    for bad in ("Summit%", "Co_", "a*", "x[1]", "(Co.)"):
        with pytest.raises(InvalidArgument):
            match_accounts(bad, ACCOUNTS)
