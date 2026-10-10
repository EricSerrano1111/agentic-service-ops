"""`Prompt.render` fills the template in one pass: user text is data, not template syntax.

Before 2026-10-04 the question was substituted first and the result then checked for any
leftover `{{`, so a question holding `{{x}}` raised (HTTP 500 at the orchestrator) and one
holding `{{as_of}}` was silently rewritten by a later substitution. The fix must not change a
single character of any ordinary render: `LEGACY` is the old algorithm, kept here as the
reference, and every question in the repository's evaluation sets must render identically
under both through every prompt file of every service.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from llm.prompts import PLACEHOLDER_CLOSE, PLACEHOLDER_OPEN, Prompt

ROOT = Path(__file__).resolve().parents[2]
QUESTION_FILES = [
    "evals/routing/seed_v1.jsonl",
    "evals/routing/routing_v1.jsonl",
    "evals/routing/seed_v2.jsonl",
    "evals/routing/routing_v2.jsonl",
    "evals/routing/fr03_fresh_v1.jsonl",
    "evals/golden/golden_v1.jsonl",
    "evals/golden/golden_v2.jsonl",
    "evals/reporting_parse/parse_v3.jsonl",
    "evals/sentiment_parse/parse_v1.jsonl",
    "evals/forecast_parse/parse_v1.jsonl",
]
SAMPLE = {
    "as_of": "2026-08-30",
    "first_week": "2026-08-31",
    "window_start": "2023-09-04",
    "window_end": "2026-08-30",
    "domain": "reporting",
    "reading": '{"metric": "incident_count"}',
}


TEMPLATE = "Today is {{as_of}}.\n<question>\n{{question}}\n</question>\n"


def legacy_render(text: str, **values: str) -> str:
    """The algorithm `Prompt.render` had until 2026-10-04: fill each value in turn, then
    reject any leftover `{{`."""
    out = text
    for name, value in values.items():
        token = f"{PLACEHOLDER_OPEN}{name}{PLACEHOLDER_CLOSE}"
        if token not in out:
            raise KeyError(f"no placeholder {token}")
        out = out.replace(token, value)
    if PLACEHOLDER_OPEN in out:
        raise KeyError("left unfilled")
    return out


def questions() -> list[str]:
    seen: dict[str, None] = {}
    for rel in QUESTION_FILES:
        for line in (ROOT / rel).read_text(encoding="utf-8").splitlines():
            if line:
                seen[json.loads(line)["question"]] = None
    return list(seen)


PROMPT_FILES = sorted((ROOT / "services").glob("*/prompts/*.md"))


def _values(prompt: Prompt, question: str) -> dict[str, str]:
    names = set(re.findall(r"\{\{(\w+)\}\}", prompt.text))
    return {n: question if n == "question" else SAMPLE[n] for n in names}


def test_the_evaluation_sets_and_prompt_files_are_found():
    assert len(questions()) >= 130
    assert {p.parent.parent.name for p in PROMPT_FILES} == {
        "orchestrator",
        "agent_reporting",
        "agent_sentiment",
        "agent_forecast",
        "agent_qa",
    }


@pytest.mark.parametrize("path", PROMPT_FILES, ids=lambda p: f"{p.parent.parent.name}/{p.stem}")
def test_ordinary_questions_render_exactly_as_before(path):
    prompt = Prompt.from_path(path)
    for question in questions():
        assert "{{" not in question
        values = _values(prompt, question)
        assert prompt.render(**values) == legacy_render(prompt.text, **values), question


@pytest.mark.parametrize(
    "question",
    ["what is {{x}}?", "show {0} incidents", "odd }}{{ braces", "{{as_of}} {{question}} {1}", "{{"],
)
def test_template_syntax_in_a_value_is_inserted_literally(tmp_path, question):
    path = tmp_path / "p_v1.md"
    path.write_text(TEMPLATE, encoding="utf-8")
    prompt = Prompt.from_path(path)
    out = prompt.render(as_of="2026-08-30", question=question)
    assert out == f"Today is 2026-08-30.\n<question>\n{question}\n</question>\n"


def test_the_old_algorithm_failed_on_template_syntax():
    """The regression this fix closes, kept as a witness."""
    text = TEMPLATE
    with pytest.raises(KeyError):
        legacy_render(text, as_of="2026-08-30", question="what is {{x}}?")


def test_values_are_never_rescanned(tmp_path):
    path = tmp_path / "p_v1.md"
    path.write_text("{{a}} | {{b}}", encoding="utf-8")
    assert Prompt.from_path(path).render(a="{{b}}", b="X") == "{{b}} | X"


def test_the_template_still_must_be_filled_exactly(tmp_path):
    path = tmp_path / "p_v1.md"
    path.write_text("{{a}} and {{b}} and {{ stray", encoding="utf-8")
    prompt = Prompt.from_path(path)
    with pytest.raises(KeyError, match="left unfilled"):
        prompt.render(a="x", b="y")  # a stray `{{` in the template itself
    with pytest.raises(KeyError, match="no placeholder"):
        prompt.render(a="x", b="y", c="z")
    path.write_text("{{a}} and {{b}}", encoding="utf-8")
    with pytest.raises(KeyError, match="left unfilled"):
        Prompt.from_path(path).render(a="x")
