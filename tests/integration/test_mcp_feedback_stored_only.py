"""`stored_only` against the live database (ADR-100): same answers, and fail closed on a gap.

Two kinds of test:

- Equivalence, on the real stored `bert_v1` predictions: the `lazy` and `stored_only` servers
  return byte-identical tool results for the same questions, and the lazy classifier is never
  called (there is nothing to score). Skipped when the database holds no stored predictions,
  as CI's does (no model runs in CI), like the sentiment golden-oracle check.
- Fail closed, on throwaway model versions: a range that is partly scored, or scored under
  another version, gives `predictions_incomplete` and writes nothing. These run in CI.

Reads as `app_sentiment`; the throwaway rows are deleted as the admin role afterwards.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from collections.abc import Iterator, Sequence
from pathlib import Path

import psycopg
import pytest
from mcp import Client
from mcp_feedback.classifier import Prediction
from mcp_feedback.config import Settings
from mcp_feedback.server import EXAMPLES, SUMMARY, Backend, create_server
from mcp_feedback.store import SqlStore, make_engine
from schemas import SENTIMENT_LABELS

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

MANIFEST = Path(__file__).resolve().parents[2] / "ml/sentiment/artifacts/bert_v1.manifest.json"
REAL_VERSION = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
# The dataset window is 1,091 days and a request may span at most 731: two halves cover it.
WINDOW = {"start": "2024-09-01", "end": "2026-08-30"}
EARLY = {"start": "2023-09-04", "end": "2024-08-31"}
QUESTIONS = [
    (SUMMARY, {**WINDOW, "bucket": "month"}),
    (SUMMARY, {**WINDOW, "bucket": "quarter"}),
    (SUMMARY, {"start": "2026-07-01", "end": "2026-07-31", "region": "west"}),
    (SUMMARY, {"start": "2026-08-29", "end": "2026-08-30"}),
    (SUMMARY, {**EARLY, "bucket": "month"}),
    (EXAMPLES, {**EARLY, "limit": 5}),
    (EXAMPLES, {**WINDOW, "limit": 5}),
    (EXAMPLES, {**WINDOW, "flagged_only": True, "limit": 5}),
    (EXAMPLES, {"start": "2026-07-01", "end": "2026-07-31", "label": "negative"}),
]


class NeverCalled:
    """A classifier that fails the test if anything is scored."""

    def predict(self, texts: Sequence[str]) -> list[Prediction]:
        raise AssertionError(f"scoring was attempted for {len(texts)} comments")


class HashClassifier:
    def predict(self, texts: Sequence[str]) -> list[Prediction]:
        out = []
        for t in texts:
            h = int(hashlib.sha256(t.encode()).hexdigest(), 16)
            conf = 0.5 + (h % 5000) / 10000
            out.append(Prediction(SENTIMENT_LABELS[h % 4], conf, conf < 0.84))
        return out


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
def settings(live_database: None) -> Settings:
    return Settings(
        db_host=os.environ["POSTGRES_HOST"],
        db_port=int(os.environ["POSTGRES_PORT"]),
        db_name=os.environ["POSTGRES_DB"],
        db_user=os.environ["DB_ROLE_SENTIMENT_USER"],
        db_password=os.environ["DB_ROLE_SENTIMENT_PASSWORD"],
    )


@pytest.fixture
def throwaway(loaded_database) -> Iterator[list[str]]:
    versions: list[str] = []
    yield versions
    with psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_ADMIN_USER"],
        password=os.environ["POSTGRES_ADMIN_PASSWORD"],
        autocommit=True,
    ) as admin:
        for v in versions:
            admin.execute("DELETE FROM sentiment_predictions WHERE model_version = %s", (v,))


async def _text(server, tool: str, args: dict) -> tuple[bool, str]:
    async with Client(server) as client:
        result = await client.call_tool(tool, args)
    return result.is_error, result.content[0].text


def _real_predictions_present(settings: Settings) -> bool:
    store = SqlStore(make_engine(settings))
    with store.engine.connect() as conn:
        from sqlalchemy import text

        n = conn.execute(
            text("SELECT count(*) FROM sentiment_predictions WHERE model_version = :v"),
            {"v": REAL_VERSION},
        ).scalar_one()
    return int(n) > 0


async def test_lazy_and_stored_only_return_identical_results_on_the_real_predictions(
    settings, loaded_database
):
    if not _real_predictions_present(settings):
        pytest.skip("no stored bert_v1 predictions (CI's database holds none)")
    store = SqlStore(make_engine(settings))
    lazy = create_server(
        settings, Backend(store, NeverCalled(), REAL_VERSION, 250, ready=store.ping)
    )
    only = create_server(
        settings,
        Backend(store, None, REAL_VERSION, 0, ready=store.ping, stored_only=True),
    )
    for tool, args in QUESTIONS:
        a, b = await _text(lazy, tool, args), await _text(only, tool, args)
        assert a[0] is False and b[0] is False, (tool, args)
        assert a == b, (tool, args)


async def test_a_partly_scored_range_fails_closed_and_writes_nothing(settings, throwaway):
    version = f"itest-stored-{uuid.uuid4().hex}"
    throwaway.append(version)
    store = SqlStore(make_engine(settings))
    # Score the 5 newest comments under the throwaway version, leaving the rest unscored.
    lazy = create_server(settings, Backend(store, HashClassifier(), version, 5, ready=store.ping))
    partial = await _text(lazy, SUMMARY, {"start": "2026-08-01", "end": "2026-08-30"})
    assert partial[0] is False and '"complete":false' in partial[1].replace(" ", "")

    only = create_server(
        settings, Backend(store, None, version, 0, ready=store.ping, stored_only=True)
    )
    for tool, args in (
        (SUMMARY, {"start": "2026-08-01", "end": "2026-08-30"}),
        (EXAMPLES, {"start": "2026-08-01", "end": "2026-08-30"}),
    ):
        is_error, text = await _text(only, tool, args)
        assert is_error and text.endswith("predictions_incomplete")
    with store.engine.connect() as conn:
        from sqlalchemy import text as sql

        n = conn.execute(
            sql("SELECT count(*) FROM sentiment_predictions WHERE model_version = :v"),
            {"v": version},
        ).scalar_one()
    assert n == 5  # stored_only added none


async def test_predictions_under_another_version_do_not_count(settings, throwaway):
    other = f"itest-other-{uuid.uuid4().hex}"
    throwaway.append(other)
    store = SqlStore(make_engine(settings))
    full = create_server(settings, Backend(store, HashClassifier(), other, 250, ready=store.ping))
    # one day, scored completely under `other`
    rng = {"start": "2026-08-29", "end": "2026-08-30"}  # the weekend G05 lists: not empty
    done = await _text(full, SUMMARY, rng)
    assert done[0] is False
    mismatch = create_server(
        settings,
        Backend(
            store, None, f"itest-expected-{uuid.uuid4().hex}", 0, ready=store.ping, stored_only=True
        ),
    )
    is_error, text = await _text(mismatch, SUMMARY, rng)
    assert is_error and text.endswith("predictions_incomplete")
