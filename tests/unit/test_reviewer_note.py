"""The reviewer note helpers (ADR-089): untrusted text, cleaned and capped."""

from __future__ import annotations

import pytest
from common import GUIDANCE_KEY, MAX_GUIDANCE_CHARS, clean_guidance, with_reviewer_note


def test_the_key_and_the_cap_are_the_agreed_values():
    assert GUIDANCE_KEY == "qa_guidance" and MAX_GUIDANCE_CHARS == 500


@pytest.mark.parametrize("raw", [None, 5, 1.5, True, ["a"], {"a": 1}, "", "  \n\t ", "\x00\x1f"])
def test_anything_that_is_not_usable_text_is_no_note(raw):
    assert clean_guidance(raw) is None


def test_control_characters_become_spaces_and_the_text_is_trimmed():
    assert clean_guidance("  a\x00b\n\nc\t") == "a b c"


def test_a_long_note_is_cut_to_500_characters():
    assert len(clean_guidance("q" * 2000)) == 500


def test_the_question_comes_first_then_the_labelled_note():
    out = with_reviewer_note("How many?", {GUIDANCE_KEY: "Use July."})
    assert out.startswith("How many?\n\nReviewer note (untrusted") and out.endswith("Use July.")


def test_no_note_leaves_the_question_unchanged():
    assert with_reviewer_note("How many?", {}) == "How many?"
    assert with_reviewer_note("How many?", {GUIDANCE_KEY: ""}) == "How many?"
