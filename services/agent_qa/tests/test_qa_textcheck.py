"""The text-matches-data check's reading of numbers (ADR-087)."""

from __future__ import annotations

import pytest
from agent_qa import textcheck


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("172 incidents", ["172"]),
        ("1,234 incidents and 0.8881 rate", ["1234", "0.8881"]),
        ("from 2026-07-01 to 2026-07-31", []),
        ("(ADR-033) and 20 jobs", ["20"]),
        ("Item 3, then 4.", ["3", "4"]),
    ],
)
def test_numbers_are_read_without_dates_or_adr_references(text, expected):
    assert textcheck.numbers_in(text) == expected


def test_names_are_removed_before_numbers_are_read():
    assert textcheck.numbers_in("3M Corp had 5", names=["3M Corp"]) == ["5"]
    # the longest name first, so a name holding a shorter one is removed whole
    assert textcheck.numbers_in("Plant 12 North: 7", names=["Plant 12", "Plant 12 North"]) == ["7"]


def test_percent_is_exact():
    assert textcheck.percent("0.8881") == "88.81"
    assert textcheck.percent("1.0000") == "100.00"
    assert textcheck.percent("0.0050") == "0.50"


def test_whole_number_figures_are_matched_by_either_neighbour():
    assert textcheck.approx_forms(100.4) == {"100", "101"}
    assert textcheck.approx_forms(100.0) == {"100"}
    assert textcheck.approx_forms(100.5) >= {"100", "101"}


def test_compare_reports_an_unsupported_number_and_a_missing_headline():
    assert textcheck.compare("172 now", {"172"}, [{"172"}]) == []
    assert textcheck.compare("173 now", {"172"}, [{"172"}]) == [
        "text_states_unsupported_number",
        "text_misses_headline_number",
    ]
    assert textcheck.compare("nothing", {"172"}, [{"172"}]) == ["text_misses_headline_number"]
    assert textcheck.compare("172 and 9", {"172"}, [{"172"}]) == ["text_states_unsupported_number"]
