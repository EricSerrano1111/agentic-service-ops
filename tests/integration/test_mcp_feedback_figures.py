"""The feedback MCP tools' figures equal an independent SQL computation (ADR-067).

The tools run in-process through a real MCP client against the live database as
`app_sentiment`, with that role's own credentials and the real SQL store; only the model
is replaced, by a deterministic stub. Expected figures come from hand-written SQL run as
`app_eval` (ADR-063): a different role, a different code path, no SQLAlchemy.

Each test writes under its own throwaway `model_version` and deletes it afterwards as
the admin role (`app_sentiment` can't delete), so real predictions are never touched and
an empty table stays empty.

Needs a migrated *and loaded* database.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import uuid
from collections.abc import Callable, Iterator, Sequence

import psycopg
import pytest
from db_models.access_matrix import ROLE_EVAL
from mcp import Client
from mcp_feedback.classifier import Prediction
from mcp_feedback.config import Settings
from mcp_feedback.server import EXAMPLES, SUMMARY, Backend, create_server
from mcp_feedback.store import SqlStore, make_engine
from schemas import SENTIMENT_LABELS

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

ConnectAs = Callable[[str], psycopg.Connection]


class HashClassifier:
    """Deterministic stand-in for BERT: label and confidence from the text's hash."""

    def __init__(self) -> None:
        self.scored = 0

    def predict(self, texts: Sequence[str]) -> list[Prediction]:
        self.scored += len(texts)
        out = []
        for t in texts:
            h = int(hashlib.sha256(t.encode()).hexdigest(), 16)
            conf = 0.5 + (h % 5000) / 10000  # 0.5000 .. 0.9999
            out.append(Prediction(SENTIMENT_LABELS[h % 4], conf, conf < 0.84))
        return out


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
def sentiment_settings(live_database: None) -> Settings:
    return Settings(
        db_host=os.environ["POSTGRES_HOST"],
        db_port=int(os.environ["POSTGRES_PORT"]),
        db_name=os.environ["POSTGRES_DB"],
        db_user=os.environ["DB_ROLE_SENTIMENT_USER"],
        db_password=os.environ["DB_ROLE_SENTIMENT_PASSWORD"],
    )


@pytest.fixture
def version(loaded_database) -> Iterator[str]:
    v = f"itest-{uuid.uuid4().hex}"
    yield v
    with psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_ADMIN_USER"],
        password=os.environ["POSTGRES_ADMIN_PASSWORD"],
        autocommit=True,
    ) as admin:
        admin.execute("DELETE FROM sentiment_predictions WHERE model_version = %s", (v,))


def _backend(settings: Settings, version: str, cap: int = 250) -> tuple[Backend, HashClassifier]:
    store = SqlStore(make_engine(settings))
    clf = HashClassifier()
    return Backend(store, clf, version, cap, ready=store.ping), clf


# Independent of the store: literal SQL, UTC day boundaries, inclusive end day.
IN_SCOPE = """
    FROM service_feedback f
    JOIN service_requests r ON r.request_id = f.request_id
    JOIN locations l ON l.location_id = r.location_id
    WHERE f.submitted_at >= (%(start)s::date)::timestamp AT TIME ZONE 'UTC'
      AND f.submitted_at <  ((%(end)s::date + 1))::timestamp AT TIME ZONE 'UTC'
      AND f.feedback_text IS NOT NULL
      AND (%(region)s::text IS NULL OR l.region = %(region)s::text)
"""
COUNT_COMMENTS = "SELECT count(*) " + IN_SCOPE
BY_LABEL_MONTH = (
    "SELECT p.predicted_label, to_char(f.submitted_at AT TIME ZONE 'UTC', 'YYYY-MM'),"
    " count(*), count(*) FILTER (WHERE p.flagged) "
    + IN_SCOPE.replace(
        "WHERE",
        "JOIN sentiment_predictions p ON p.feedback_id = f.feedback_id"
        " AND p.model_version = %(version)s WHERE",
    )
    + " GROUP BY 1, 2"
)
STORED = "SELECT count(*) FROM sentiment_predictions WHERE model_version = %s"


def _params(start, end, region, version=None) -> dict:
    return {"start": start, "end": end, "region": region, "version": version}


@pytest.mark.parametrize(
    ("start", "end", "region"),
    [
        (dt.date(2026, 4, 1), dt.date(2026, 6, 30), "west"),
        (dt.date(2025, 11, 1), dt.date(2025, 12, 31), "central"),
        (dt.date(2026, 8, 1), dt.date(2026, 8, 30), None),
    ],
)
async def test_summary_matches_independent_sql(
    connect_as: ConnectAs, sentiment_settings, version, start, end, region
):
    backend, _ = _backend(sentiment_settings, version)
    args = {"start": start.isoformat(), "end": end.isoformat()}
    if region:
        args["region"] = region
    async with Client(create_server(sentiment_settings, backend)) as client:
        result = await client.call_tool(SUMMARY, args)
    assert not result.is_error, result.content
    s = result.structured_content

    eval_conn = connect_as(ROLE_EVAL)
    (n,) = eval_conn.execute(COUNT_COMMENTS, _params(start, end, region)).fetchone()
    assert 0 < n <= 250, "pick ranges under the cap so the answer is complete"
    rows = eval_conn.execute(BY_LABEL_MONTH, _params(start, end, region, version)).fetchall()

    assert (s["n_comments"], s["n_scored"], s["complete"]) == (n, n, True)
    totals = {label: 0 for label in SENTIMENT_LABELS}
    for label, _, count, _ in rows:
        totals[label] += count
    assert s["counts"] == totals
    assert s["flagged_count"] == sum(r[3] for r in rows)
    got_buckets = {
        (b["bucket"], label): c for b in s["buckets"] for label, c in b["counts"].items() if c
    }
    assert got_buckets == {(month, label): c for label, month, c, _ in rows}


async def test_a_second_call_inserts_nothing(connect_as: ConnectAs, sentiment_settings, version):
    backend, clf = _backend(sentiment_settings, version)
    args = {"start": "2026-07-01", "end": "2026-07-31", "region": "southeast"}
    async with Client(create_server(sentiment_settings, backend)) as client:
        first = await client.call_tool(SUMMARY, args)
        (stored,) = connect_as(ROLE_EVAL).execute(STORED, (version,)).fetchone()
        scored = clf.scored
        second = await client.call_tool(SUMMARY, args)
    (after,) = connect_as(ROLE_EVAL).execute(STORED, (version,)).fetchone()
    assert stored == first.structured_content["n_comments"] > 0
    assert (after, clf.scored) == (stored, scored)
    assert second.structured_content == first.structured_content


async def test_above_the_cap_the_oldest_are_stored(
    connect_as: ConnectAs, sentiment_settings, version
):
    backend, _ = _backend(sentiment_settings, version, cap=50)
    start, end = dt.date(2026, 1, 1), dt.date(2026, 3, 31)
    async with Client(create_server(sentiment_settings, backend)) as client:
        result = await client.call_tool(
            SUMMARY, {"start": start.isoformat(), "end": end.isoformat()}
        )
    s = result.structured_content
    eval_conn = connect_as(ROLE_EVAL)
    (n,) = eval_conn.execute(COUNT_COMMENTS, _params(start, end, None)).fetchone()
    assert (s["n_comments"], s["n_scored"], s["complete"]) == (n, 50, False)
    oldest = [
        r[0]
        for r in eval_conn.execute(
            "SELECT f.feedback_id " + IN_SCOPE + " ORDER BY f.submitted_at, f.feedback_id LIMIT 50",
            _params(start, end, None),
        )
    ]
    stored = sorted(
        r[0]
        for r in eval_conn.execute(
            "SELECT feedback_id FROM sentiment_predictions WHERE model_version = %s", (version,)
        )
    )
    assert stored == sorted(oldest)


@pytest.mark.parametrize("flagged_only", [False, True])
async def test_examples_order_matches_independent_sql(
    connect_as: ConnectAs, sentiment_settings, version, flagged_only
):
    backend, _ = _backend(sentiment_settings, version)
    args = {
        "start": "2026-05-01",
        "end": "2026-05-31",
        "region": "northeast",
        "label": "negative",
        "flagged_only": flagged_only,
        "limit": 5,
    }
    async with Client(create_server(sentiment_settings, backend)) as client:
        result = await client.call_tool(EXAMPLES, args)
    got = result.structured_content["examples"]
    order = "p.confidence ASC" if flagged_only else "p.confidence DESC"
    expected = (
        connect_as(ROLE_EVAL)
        .execute(
            "SELECT f.feedback_id, l.region, p.predicted_label, p.flagged "
            + IN_SCOPE.replace(
                "WHERE",
                "JOIN sentiment_predictions p ON p.feedback_id = f.feedback_id"
                " AND p.model_version = %(version)s WHERE",
            )
            + " AND p.predicted_label = 'negative'"
            + (" AND p.flagged" if flagged_only else "")
            + f" ORDER BY {order}, f.feedback_id LIMIT 5",
            _params(dt.date(2026, 5, 1), dt.date(2026, 5, 31), "northeast", version),
        )
        .fetchall()
    )
    assert [(e["feedback_id"], e["region"], e["label"], e["flagged"]) for e in got] == [
        tuple(r) for r in expected
    ]
    assert expected, "the range should hold at least one matching comment"
    assert all(e["feedback_text"] for e in got)


def test_insert_returns_the_number_actually_inserted(sentiment_settings, version):
    """A conflict inserts nothing and says so; the backfill's total depends on it."""
    store = SqlStore(make_engine(sentiment_settings))
    scope_ids = store.unscored(version, _scope(), 3)
    rows = [
        (fid, p)
        for (fid, _), p in zip(
            scope_ids, HashClassifier().predict([t for _, t in scope_ids]), strict=True
        )
    ]
    assert store.insert(version, rows) == 3
    assert store.insert(version, rows) == 0
    assert store.insert(version, []) == 0


def _scope():
    from mcp_feedback.scoring import Scope

    return Scope(dt.date(2026, 8, 1), dt.date(2026, 8, 30))
