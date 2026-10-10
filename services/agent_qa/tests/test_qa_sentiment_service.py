"""Sentiment answers through the QA service in process (ADR-090): the verdict, the rating line,
and what the model and the logs never see."""

from __future__ import annotations

import datetime as dt
import json

import pytest
from qa_fakes import FakeLLM
from schemas import SentimentRequest
from test_qa_sentiment_checks import FLAT, QUOTES, World
from test_qa_service import advisory_app, captured_logs, send, verdict_of

CANARY = "CANARYCOMMENT zebra-7731 never reply"
REQUEST = SentimentRequest(
    start=dt.date(2026, 8, 1),
    end=dt.date(2026, 8, 30),
    want_examples=True,
    example_label="negative",
)


def verification(world: World, **fields) -> dict:
    answer, text = world.answer(REQUEST, quoted=(1,))
    return {
        "domain": "sentiment",
        "kind": "answer",
        "question": "Show me some negative comments from August",
        "text": text,
        "answer": answer.model_dump(mode="json"),
    } | fields


def world(**kw) -> World:
    quotes = {1: QUOTES[1] | {"text": CANARY}}
    return World(rows=FLAT, quotes=quotes, **kw)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_a_sentiment_answer_is_verified_with_the_cross_check_line():
    w = world()
    llm = FakeLLM()
    app, _ = advisory_app(llm, w.source())
    verdict = verdict_of(await send(app, data=verification(w)))
    assert verdict.verdict == "pass" and verdict.failed == []
    rating = next(c for c in verdict.checks if c.code == "rating_contradiction")
    assert rating.detail == "n=4715, x=7, p0=0.01: pass"
    assert {c.code for c in verdict.checks} >= {
        "coverage_matches_database",
        "figures_match_database",
        "flags_consistent",
        "trend_matches",
        "quotes_valid",
        "text_matches_data",
    }
    assert len(llm.prompts) == 1  # the advisory interpretation call


@pytest.mark.anyio
async def test_no_comment_text_and_no_figure_reaches_the_language_model_or_the_logs():
    w = world()
    llm = FakeLLM()
    app, _ = advisory_app(llm, w.source())
    with captured_logs() as lines:
        await send(app, data=verification(w))
        logged = lines()
    prompt = llm.prompts[0]
    assert CANARY not in prompt and "zebra" not in prompt
    assert '"route": "sentiment"' in prompt and '"wants_example_comments": true' in prompt
    assert "248" not in prompt and "4715" not in prompt  # no count of any kind
    text = json.dumps(logged)
    assert CANARY not in text and "zebra" not in text and "never reply" not in text
    done = next(x for x in logged if x["msg"] == "task completed")
    assert done["rating_check"] == "n=4715, x=7, p0=0.01: pass"


@pytest.mark.anyio
async def test_a_failed_cross_check_is_a_figures_failure_and_the_model_is_not_called():
    w = world(rating=(100, 6))
    llm = FakeLLM()
    app, _ = advisory_app(llm, w.source())
    verdict = verdict_of(await send(app, data=verification(w)))
    assert verdict.verdict == "fail" and verdict.figures_failed
    assert [c.code for c in verdict.failed] == ["rating_contradiction"]
    assert llm.prompts == []


@pytest.mark.anyio
async def test_a_quote_id_that_does_not_exist_fails_the_answer():
    w = world()
    data = verification(w)
    w.quotes = {}
    app, _ = advisory_app(FakeLLM(), w.source())
    verdict = verdict_of(await send(app, data=data))
    assert verdict.verdict == "fail" and "quotes_valid" in {c.code for c in verdict.failed}
    assert CANARY not in json.dumps(verdict.model_dump(mode="json"))


@pytest.mark.anyio
async def test_a_decline_is_verified_with_no_database_read():
    from agent_sentiment.render import decline_message
    from qa_fakes import FakeSource

    parsed = SentimentRequest(unsupported="account").model_dump(mode="json")
    data = {
        "domain": "sentiment",
        "kind": "decline",
        "question": "Which account is unhappiest?",
        "text": decline_message("account"),
        "error_code": "not_supported",
        "parsed_request": parsed,
    }
    source = FakeSource()
    llm = FakeLLM()
    app, _ = advisory_app(llm, source)
    verdict = verdict_of(await send(app, data=data))
    assert verdict.verdict == "pass" and source.calls == []
    assert '"unsupported_breakdown": "account"' in llm.prompts[0]


@pytest.mark.anyio
async def test_a_sentiment_answer_that_breaks_its_contract_is_a_failing_verdict():
    w = world()
    data = verification(w)
    data["answer"]["summary"]["counts"]["positive"] = -3
    app, source = advisory_app(FakeLLM(), w.source())
    verdict = verdict_of(await send(app, data=data))
    assert [c.code for c in verdict.failed] == ["answer_malformed"] and source.calls == []
