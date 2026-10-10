"""QA's sentiment checks against the loaded database and the real feedback server (ADR-090).

The sentiment agent runs in process through the real A2A SDK with a fixed parse; its MCP calls
go to the real `mcp_feedback` server code, which answers from the stored predictions of the
current model version (no scoring: the server's cap is 0, so nothing is written). QA, written
from data dictionary §6 alone and reading as `app_qa`, then checks what the agent returned.
A pass means QA's recomputation equals the server's figures; a perturbed figure is caught.

The partial-coverage case removes some predictions inside one open transaction on a shared
connection, runs the server and QA on that connection, and rolls back: the database is never
changed for anyone else. Needs the loaded database and the stored predictions for the current
`bert_v1` manifest (a local backfill; CI loads the data but holds no predictions, so the
tests that need them skip there).
"""

from __future__ import annotations

import datetime as dt
import os
import uuid
from pathlib import Path

import httpx
import psycopg
import pytest
from a2a.client import ClientConfig, create_client
from a2a.types import Message, Part, Role, SendMessageRequest, TaskState
from agent_qa import sentiment as qa
from agent_qa.config import Settings as QASettings
from agent_qa.db import PostgresSource, utc_bounds
from agent_sentiment import executor as executor_mod
from agent_sentiment.app import create_app
from agent_sentiment.config import Settings as AgentSettings
from agent_sentiment.render import render_answer
from google.protobuf.json_format import MessageToDict
from llm import LLMResult
from mcp import Client
from mcp_feedback.config import Settings as FeedbackSettings
from mcp_feedback.server import Backend, create_server
from mcp_feedback.store import SqlStore
from schemas import (
    DATASET_WINDOW_END,
    DATASET_WINDOW_START,
    FeedbackExamples,
    SentimentAnswer,
    SentimentRequest,
)
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool, StaticPool

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

REPO = Path(__file__).resolve().parents[2]
MANIFEST = qa.SentimentManifest.load(
    REPO / "ml" / "sentiment" / "artifacts" / "bert_v1.manifest.json"
)
BASE = "http://agent.test"
AS_OF = DATASET_WINDOW_END


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _url(user_var: str, password_var: str) -> URL:
    return URL.create(
        "postgresql+psycopg",
        username=os.environ[user_var],
        password=os.environ[password_var],
        host=os.environ["POSTGRES_HOST"],
        port=int(os.environ["POSTGRES_PORT"]),
        database=os.environ["POSTGRES_DB"],
    )


class NoScoring:
    def predict(self, texts):  # the server's cap is 0: it never asks
        raise AssertionError("the server tried to score a comment")


@pytest.fixture(scope="module")
def stored_predictions(live_database, loaded_database):
    engine = create_engine(_url("DB_ROLE_QA_USER", "DB_ROLE_QA_PASSWORD"), poolclass=NullPool)
    with engine.connect() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM sentiment_predictions WHERE model_version = :v"),
            {"v": MANIFEST.version},
        ).scalar_one()
    engine.dispose()
    if n == 0:
        pytest.skip("no stored predictions for the current model version (run the backfill)")
    return n


def feedback_settings() -> FeedbackSettings:
    return FeedbackSettings(
        db_host=os.environ["POSTGRES_HOST"],
        db_port=int(os.environ["POSTGRES_PORT"]),
        db_name=os.environ["POSTGRES_DB"],
        db_user=os.environ["DB_ROLE_SENTIMENT_USER"],
        db_password=os.environ["DB_ROLE_SENTIMENT_PASSWORD"],
    )


class World:
    """The feedback server over some engine, and QA over some engine."""

    def __init__(self, server_engine, qa_engine) -> None:
        store = SqlStore(server_engine)
        self.server = create_server(
            feedback_settings(), Backend(store, NoScoring(), MANIFEST.version, 0, store.ping)
        )
        self.qa = PostgresSource(qa_engine)
        self.checker = qa.Checker(
            self.qa,
            QASettings(db_host="x", db_port=5432, db_name="x", db_user="x", as_of=AS_OF),
            MANIFEST,
        )

    async def call(self, tool, arguments, model):
        async with Client(self.server) as client:
            result = await client.call_tool(tool, arguments)
        assert not result.is_error, result.content
        return model.model_validate(result.structured_content)

    async def ask(self, request: SentimentRequest, monkeypatch) -> tuple[SentimentAnswer, str]:
        async def in_process(url, tool, arguments, result_model, *, trace_id, timeout_s):
            return await self.call(tool, arguments, result_model)

        monkeypatch.setattr(executor_mod, "call_tool", in_process)

        class Fixed:
            async def generate(self, prompt, *, model=None, response_model=None, trace_id):
                return LLMResult(
                    text=request.model_dump_json(),
                    parsed=request,
                    model="fixed",
                    input_tokens=0,
                    output_tokens=0,
                    cost_usd=0.0,
                    latency_s=0.0,
                    attempts=1,
                )

        app = create_app(AgentSettings(public_url=f"{BASE}/"), Fixed())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as http:
            client = await create_client(
                BASE, client_config=ClientConfig(streaming=False, httpx_client=http)
            )
            message = Message(
                message_id=uuid.uuid4().hex, role=Role.ROLE_USER, parts=[Part(text="q")]
            )
            async for event in client.send_message(SendMessageRequest(message=message)):
                task = event.task
                break
        assert task.status.state == TaskState.TASK_STATE_COMPLETED
        part_text, data = task.artifacts[0].parts
        answer = SentimentAnswer.model_validate(MessageToDict(data.data))
        assert part_text.text == render_answer(answer)
        return answer, part_text.text


class HeldOpen(psycopg.Connection):
    """A connection that ignores commit, rollback and close, so SQLAlchemy cannot end the test's
    transaction; the test ends it itself with `end`."""

    def commit(self):
        return None

    def rollback(self):
        return None

    def close(self):
        return None

    def end(self):
        psycopg.Connection.rollback(self)
        psycopg.Connection.close(self)


@pytest.fixture
def world(stored_predictions):
    server = create_engine(
        _url("DB_ROLE_SENTIMENT_USER", "DB_ROLE_SENTIMENT_PASSWORD"), poolclass=NullPool
    )
    qa_engine = create_engine(_url("DB_ROLE_QA_USER", "DB_ROLE_QA_PASSWORD"), poolclass=NullPool)
    yield World(server, qa_engine)
    server.dispose()
    qa_engine.dispose()


def failed(checks) -> dict[str, str]:
    return {c.code: c.detail for c in checks if not c.passed}


D = dt.date
CASES = {
    "all-sites-default-trend": SentimentRequest(want_trend=True),
    "northeast-trend": SentimentRequest(want_trend=True, region="northeast"),
    "southeast-trend": SentimentRequest(want_trend=True, region="southeast"),
    "central-trend": SentimentRequest(want_trend=True, region="central"),
    "west-trend": SentimentRequest(want_trend=True, region="west"),
    "all-sites-previous-month": SentimentRequest(),
    "all-sites-quarterly-2025": SentimentRequest(
        start=D(2025, 1, 1), end=D(2025, 12, 31), bucket="quarter"
    ),
    "west-quarterly-trend": SentimentRequest(
        start=D(2024, 7, 1), end=D(2026, 6, 30), bucket="quarter", want_trend=True, region="west"
    ),
    "monthly-two-years-trend": SentimentRequest(
        start=D(2024, 9, 1), end=D(2026, 8, 30), want_trend=True
    ),
    "one-month-no-trend-possible": SentimentRequest(
        start=D(2026, 7, 1), end=D(2026, 7, 31), want_trend=True
    ),
    "negative-quotes": SentimentRequest(want_examples=True, example_label="negative"),
    "positive-quotes-west": SentimentRequest(
        want_examples=True, example_label="positive", region="west"
    ),
    "mixed-quotes": SentimentRequest(
        start=D(2025, 1, 1), end=D(2025, 12, 31), want_examples=True, example_label="mixed"
    ),
    "neutral-quotes": SentimentRequest(
        start=D(2025, 1, 1), end=D(2025, 12, 31), want_examples=True, example_label="neutral"
    ),
    "trend-with-quotes": SentimentRequest(want_trend=True, want_examples=True, region="central"),
}


@pytest.mark.parametrize("name", list(CASES))
async def test_qas_recompute_equals_what_the_feedback_server_returned(world, monkeypatch, name):
    answer, text_ = await world.ask(CASES[name], monkeypatch)
    checks = world.checker.check_answer(answer, text_)
    assert failed(checks) == {}, failed(checks)
    assert {c.code for c in checks} >= {
        "range_matches_request",
        "coverage_matches_database",
        "figures_match_database",
        "flags_consistent",
        "trend_matches",
        "quotes_valid",
        "rating_contradiction",
        "text_matches_data",
    }
    assert answer.summary.complete and answer.summary.model_version == MANIFEST.version


async def test_the_default_trend_over_the_window_is_a_real_comparison(world, monkeypatch):
    answer, _ = await world.ask(SentimentRequest(want_trend=True), monkeypatch)
    assert answer.trend.verdict in ("rose", "fell", "no clear change")
    assert answer.trend.latest_bucket == "2026-08" and answer.trend.earlier_buckets[0] == "2026-03"


async def test_a_flagged_only_quotes_case_passes_and_a_swapped_flag_is_caught(world, monkeypatch):
    """The agent never asks for flagged-only comments, but the server can return them; QA's quote
    rule must hold for them too. Built by hand from the server's own flagged-only examples."""
    request = SentimentRequest(start=D(2025, 1, 1), end=D(2025, 12, 31), want_examples=True)
    answer, _ = await world.ask(request, monkeypatch)
    flagged = await world.call(
        "get_feedback_examples",
        {"start": "2025-01-01", "end": "2025-12-31", "limit": 3, "flagged_only": True},
        FeedbackExamples,
    )
    assert flagged.examples and all(e.flagged for e in flagged.examples)
    quoted = flagged.examples[:3]
    built = answer.model_copy(
        update={"examples": quoted, "quoted_feedback_ids": [e.feedback_id for e in quoted]}
    )
    text_ = render_answer(built)
    assert failed(world.checker.check_answer(built, text_)) == {}
    swapped = built.model_copy(
        update={"examples": [quoted[0].model_copy(update={"flagged": False}), *quoted[1:]]}
    )
    assert "quotes_valid" in failed(world.checker.check_answer(swapped, render_answer(swapped)))


async def test_perturbed_figures_texts_and_quotes_are_caught_on_real_data(world, monkeypatch):
    request = SentimentRequest(want_trend=True, want_examples=True, example_label="negative")
    answer, text_ = await world.ask(request, monkeypatch)
    s = answer.summary
    counts = s.counts.model_copy(update={"negative": s.counts.negative + 1})
    assert "figures_match_database" in failed(
        world.checker.check_answer(
            answer.model_copy(update={"summary": s.model_copy(update={"counts": counts})}), text_
        )
    )
    trend = answer.trend.model_copy(
        update={"p_value": 0.0001 if answer.trend.p_value > 0.001 else 0.9}
    )
    assert "trend_matches" in failed(
        world.checker.check_answer(answer.model_copy(update={"trend": trend}), text_)
    )
    first = answer.examples[0]
    one_off = first.model_copy(update={"feedback_text": first.feedback_text + "."})
    bad = answer.model_copy(update={"examples": [one_off, *answer.examples[1:]]})
    assert "quotes_valid" in failed(world.checker.check_answer(bad, render_answer(bad)))
    ghost = first.model_copy(update={"feedback_id": 10**9})
    gone = answer.model_copy(update={"examples": [ghost], "quoted_feedback_ids": [10**9]})
    assert "quotes_valid" in failed(world.checker.check_answer(gone, render_answer(gone)))


async def test_a_quote_from_another_region_or_outside_the_range_is_caught(world, monkeypatch):
    west = SentimentRequest(
        start=D(2026, 7, 1), end=D(2026, 7, 31), region="west", want_examples=True
    )
    answer, _ = await world.ask(west, monkeypatch)
    other = await world.call(
        "get_feedback_examples",
        {"start": "2026-07-01", "end": "2026-07-31", "region": "central", "limit": 1},
        FeedbackExamples,
    )
    alien = other.examples[0]
    bad = answer.model_copy(
        update={"examples": [alien], "quoted_feedback_ids": [alien.feedback_id]}
    )
    detail = failed(world.checker.check_answer(bad, render_answer(bad)))["quotes_valid"]
    assert "quote_outside_the_set" in detail
    june = await world.call(
        "get_feedback_examples",
        {"start": "2026-06-01", "end": "2026-06-30", "region": "west", "limit": 1},
        FeedbackExamples,
    )
    early = june.examples[0]
    bad = answer.model_copy(
        update={"examples": [early], "quoted_feedback_ids": [early.feedback_id]}
    )
    assert (
        "quote_outside_the_set"
        in failed(world.checker.check_answer(bad, render_answer(bad)))["quotes_valid"]
    )


# --------------------------------------------------------------------------- the cross-check


def test_the_full_window_cross_check_is_the_adr_087_baseline_and_passes(world):
    lo, hi = utc_bounds(DATASET_WINDOW_START, DATASET_WINDOW_END)
    n, x = world.qa.sentiment_rating_counts(MANIFEST.version, lo, hi, None)
    assert (n, x) == (4715, 7)
    lo2, hi2 = lo, hi
    check = world.checker._rating(lo2, hi2, None)
    assert check.passed and check.detail == "n=4715, x=7, p0=0.01: pass"


@pytest.mark.parametrize("region", ["northeast", "southeast", "central", "west"])
def test_the_regional_cross_checks_sum_to_the_baseline(world, region):
    lo, hi = utc_bounds(DATASET_WINDOW_START, DATASET_WINDOW_END)
    n, x = world.qa.sentiment_rating_counts(MANIFEST.version, lo, hi, region)
    assert 0 < n < 4715 and x <= 3  # ADR-087's per-region figures: 2, 1, 3 and 1 of 4,715


def test_the_regions_add_up_to_the_whole_window(world):
    lo, hi = utc_bounds(DATASET_WINDOW_START, DATASET_WINDOW_END)
    parts = [
        world.qa.sentiment_rating_counts(MANIFEST.version, lo, hi, r)
        for r in ("northeast", "southeast", "central", "west")
    ]
    assert (sum(p[0] for p in parts), sum(p[1] for p in parts)) == (4715, 7)


def test_every_stored_flag_matches_its_confidence_over_the_whole_window(world):
    lo, hi = utc_bounds(DATASET_WINDOW_START, DATASET_WINDOW_END)
    assert world.qa.sentiment_inconsistent_flags(MANIFEST.version, lo, hi, None, MANIFEST.tau) == 0
    n_comments, n_scored = world.qa.sentiment_coverage(MANIFEST.version, lo, hi, None)
    assert n_comments == n_scored == 7521


# --------------------------------------------------------------------------- partial coverage


async def test_a_partial_answer_is_checked_inside_a_transaction_that_is_rolled_back(
    stored_predictions, monkeypatch
):
    """Delete 40 predictions in one open transaction on a shared connection; the server and QA
    both read that connection; roll back. Nobody else ever sees the change."""
    conn = HeldOpen.connect(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_ADMIN_USER"],
        password=os.environ["POSTGRES_ADMIN_PASSWORD"],
    )
    shared = create_engine(
        "postgresql+psycopg://",
        creator=lambda: conn,
        poolclass=StaticPool,
        pool_reset_on_return=None,
    )
    try:
        with shared.connect() as first:  # let the dialect initialise before anything is deleted
            first.execute(text("SELECT 1"))

        removed = conn.execute(
            "DELETE FROM sentiment_predictions WHERE model_version = %s AND feedback_id IN ("
            " SELECT p.feedback_id FROM sentiment_predictions p"
            " JOIN service_feedback f ON f.feedback_id = p.feedback_id"
            " WHERE p.model_version = %s AND f.submitted_at >= '2026-08-01'"
            " ORDER BY p.feedback_id LIMIT 40)",
            (MANIFEST.version, MANIFEST.version),
        ).rowcount
        assert removed == 40
        world = World(shared, shared)
        request = SentimentRequest(start=D(2026, 8, 1), end=D(2026, 8, 30), want_trend=False)
        answer, text_ = await world.ask(request, monkeypatch)
        assert not answer.summary.complete
        assert answer.summary.n_comments - answer.summary.n_scored == 40
        assert text_.startswith("Based on ")
        assert failed(world.checker.check_answer(answer, text_)) == {}
        # an answer that hides the gap is caught
        lying = answer.model_copy(
            update={"summary": answer.summary.model_copy(update={"complete": True})}
        )
        assert "coverage_matches_database" in failed(world.checker.check_answer(lying, text_))
    finally:
        conn.end()
        shared.dispose()
    check = psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_ADMIN_USER"],
        password=os.environ["POSTGRES_ADMIN_PASSWORD"],
    )
    (count,) = check.execute(
        "SELECT count(*) FROM sentiment_predictions WHERE model_version = %s", (MANIFEST.version,)
    ).fetchone()
    check.close()
    assert count == stored_predictions
