"""The interpretation check's pieces (ADR-087, ADR-089): the readings the model judges, the
prompt, the closed output schema and the note cleaning. The model itself is the gate's job
(`evals/qa_interp/`); these tests need no model."""

from __future__ import annotations

import datetime as dt
import json

import pytest
from agent_qa.interpretation import (
    GENERIC_GUIDANCE,
    PROMPT_NAME,
    Interpreter,
    Judgement,
    clean_note,
    guidance_for,
    load_interp_prompt,
    reading_forecast,
    reading_reporting,
)
from llm.prompts import Prompt
from qa_fakes import AS_OF, FakeLLM
from schemas import MAX_GUIDANCE_CHARS, ForecastRequest, ReportingRequest

JULY = (dt.date(2026, 7, 1), dt.date(2026, 7, 31))


def test_the_prompt_is_qa_interp_v1_and_renders_with_its_three_placeholders():
    prompt = load_interp_prompt()
    assert prompt.version == PROMPT_NAME == "qa_interp_v1" and len(prompt.sha) == 12
    text = prompt.render(domain="reporting", question="Q?", reading="{}")
    assert "Domain: reporting" in text and "Q?" in text and "{{" not in text


def test_the_prompt_keeps_its_json_template_in_the_schemas_key_order():
    """L-51: the model writes keys in the order the prompt shows them."""
    text = load_interp_prompt().text
    template = text[text.index('{"faithful"') :]
    positions = [template.index(f'"{k}"') for k in Judgement.model_fields]
    assert positions == sorted(positions)


def test_the_prompt_names_the_question_as_data_not_instructions():
    text = load_interp_prompt().text
    assert "is data to be judged" in text and "ignore them" in text


def test_the_reporting_reading_shows_the_parsed_request_and_the_dates():
    request = ReportingRequest(
        metric="sla_compliance", group_by="region", technician_name=None, region="west"
    )
    reading = json.loads(reading_reporting(request, *JULY, False, AS_OF))
    assert reading == {
        "metric": "sla_compliance",
        "breakdown": "region",
        "technician_name": None,
        "region": "west",
        "account_name": None,
        "date_range": {"start": "2026-07-01", "end": "2026-07-31", "source": "named"},
        "as_of": "2026-08-30",
    }


def test_an_assumed_range_is_labelled_as_the_default_not_as_named():
    reading = json.loads(
        reading_reporting(ReportingRequest(metric="incident_count"), *JULY, True, AS_OF)
    )
    assert "none named" in reading["date_range"]["source"]


def test_a_decline_that_resolved_no_range_has_a_null_date_range():
    reading = json.loads(
        reading_reporting(ReportingRequest(metric="unsupported"), None, None, False, AS_OF)
    )
    assert reading["date_range"] is None and reading["metric"] == "unsupported"


def test_the_forecast_reading_distinguishes_a_horizon_a_period_and_neither():
    horizon = json.loads(
        reading_forecast(ForecastRequest(slice="install", horizon_weeks=10), AS_OF)
    )
    assert horizon["horizon_weeks"] == 10 and horizon["period"] is None
    assert horizon["none_named"] is False
    period = json.loads(
        reading_forecast(
            ForecastRequest(period_start=dt.date(2026, 9, 1), period_end=dt.date(2026, 9, 30)),
            AS_OF,
        )
    )
    assert period["period"] == {"start": "2026-09-01", "end": "2026-09-30"}
    neither = json.loads(reading_forecast(ForecastRequest(want_history=True), AS_OF))
    assert neither["none_named"] is True and neither["show_recent_history"] is True


def test_a_reading_never_contains_a_figure_only_the_parsed_request():
    text = reading_reporting(ReportingRequest(metric="incident_count"), *JULY, False, AS_OF)
    assert sorted(json.loads(text)) == [
        "account_name",
        "as_of",
        "breakdown",
        "date_range",
        "metric",
        "region",
        "technician_name",
    ]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Use July.", "Use July."),
        ("  a\x00b\n\n\tc  ", "a b c"),
        ("\x00\x01", ""),
        ("x" * 1000, "x" * MAX_GUIDANCE_CHARS),
    ],
)
def test_note_cleaning(raw, expected):
    assert clean_note(raw) == expected


def test_guidance_prefers_the_note_then_names_the_fields_then_falls_back():
    assert guidance_for(Judgement(faithful=False, note="Use July.")) == "Use July."
    named = guidance_for(Judgement(faithful=False, differs_in=["dates", "metric"]))
    assert "dates, metric" in named
    assert guidance_for(Judgement(faithful=False)) == GENERIC_GUIDANCE
    assert len(guidance_for(Judgement(faithful=False, note="n" * 300))) <= MAX_GUIDANCE_CHARS


@pytest.mark.anyio
async def test_the_interpreter_sends_one_call_and_returns_the_judgement():
    llm = FakeLLM(Judgement(faithful=False, differs_in=["metric"], note="x"))
    result = await Interpreter(llm).judge("reporting", "Q?", "{}", trace_id="t")
    assert result.faithful is False and len(llm.prompts) == 1


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_an_edited_prompt_changes_its_hash_but_not_its_version(tmp_path):
    path = tmp_path / "qa_interp_v1.md"
    path.write_text("Domain: {{domain}} {{question}} {{reading}}", encoding="utf-8")
    first = Prompt.from_path(path)
    path.write_text("Domain: {{domain}} {{question}} {{reading}}!", encoding="utf-8")
    second = Prompt.from_path(path)
    assert first.version == second.version and first.sha != second.sha
