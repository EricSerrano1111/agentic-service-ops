"""Offline tests for the feedback MCP server (ADR-067). Assembled, not observed.

No model and no database: a stub classifier and an in-memory `Store` stand in for BERT
and Postgres, and the tools are exercised through a real MCP client connected in-process.
The SQL store is covered against Postgres by tests/integration/test_mcp_feedback_figures.py.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import get_args

import numpy as np
import pytest
from db_models import Region, TrueSentiment, values
from mcp import Client
from mcp_feedback.artifact import ArtifactIntegrityError, load_verified
from mcp_feedback.classifier import Prediction, container_cpus, to_predictions
from mcp_feedback.config import DEFAULT_BATCH_SIZE, DEFAULT_SCORE_CAP, Settings
from mcp_feedback.scoring import (
    CountRow,
    ExampleRow,
    Scope,
    ensure_scored,
    example_order_key,
)
from mcp_feedback.server import (
    EXAMPLES,
    SUMMARY,
    Backend,
    InvalidInput,
    check_limit,
    create_app,
    create_server,
    parse_scope,
)
from schemas import SENTIMENT_LABELS, SiteRegion
from starlette.testclient import TestClient

pytestmark = pytest.mark.anyio
SETTINGS = Settings(db_host="unused", db_port=5432, db_name="unused", db_user="unused")
V1, V2 = "a" * 64, "b" * 64
T0 = dt.datetime(2026, 1, 1, 12, tzinfo=dt.UTC)


@pytest.fixture
def anyio_backend():
    return "asyncio"


# --------------------------------------------------------------------------- doubles


class StubClassifier:
    """Label and confidence from the text: "<label> <confidence>". Counts its calls."""

    def __init__(self, threshold: float = 0.84) -> None:
        self.threshold = threshold
        self.calls: list[int] = []

    def predict(self, texts: Sequence[str]) -> list[Prediction]:
        self.calls.append(len(texts))
        out = []
        for t in texts:
            label, conf = t.split()[:2]
            out.append(Prediction(label, float(conf), float(conf) < self.threshold))
        return out


class MemoryStore:
    """The `Store` contract over lists; ordering and filters as the SQL store's."""

    def __init__(self, comments: list[tuple[int, dt.datetime, str, str]]) -> None:
        self.comments = comments  # (feedback_id, submitted_at, region, text)
        self.predictions: dict[tuple[int, str], Prediction] = {}

    def _in(self, scope: Scope):
        return [
            c
            for c in self.comments
            if scope.lo <= c[1] < scope.hi and (scope.region in (None, c[2]))
        ]

    def count_comments(self, scope):
        return len(self._in(scope))

    def count_scored(self, version, scope):
        return sum((c[0], version) in self.predictions for c in self._in(scope))

    def unscored(self, version, scope, limit):
        todo = [c for c in self._in(scope) if (c[0], version) not in self.predictions]
        todo.sort(key=lambda c: (c[1], c[0]), reverse=True)
        return [(c[0], c[3]) for c in todo[:limit]]

    def insert(self, version, rows):
        n = 0
        for fid, p in rows:
            if (fid, version) not in self.predictions:
                self.predictions[(fid, version)] = Prediction(
                    p.label, round(p.confidence, 4), p.flagged
                )
                n += 1
        return n

    def label_bucket_counts(self, version, scope, bucket):
        counts: dict[tuple[str, str], list[int]] = {}
        for fid, at, _, _ in self._in(scope):
            p = self.predictions.get((fid, version))
            if p is None:
                continue
            key = f"{at:%Y-%m}" if bucket == "month" else f"{at.year}-Q{(at.month - 1) // 3 + 1}"
            agg = counts.setdefault((p.label, key), [0, 0])
            agg[0] += 1
            agg[1] += p.flagged
        return [CountRow(lab, b, n, f) for (lab, b), (n, f) in counts.items()]

    def examples(self, version, scope, label, flagged_only, limit):
        rows = []
        for fid, at, region, text in self._in(scope):
            p = self.predictions.get((fid, version))
            if p is None or (label and p.label != label) or (flagged_only and not p.flagged):
                continue
            rows.append(ExampleRow(fid, at, region, p.label, p.confidence, p.flagged, text))
        return sorted(rows, key=example_order_key(flagged_only))[:limit]


def comments(n: int, label: str = "positive", conf: float = 0.99, region: str = "west"):
    """n comments, one minute apart, ids descending so id order != time order."""
    return [(10_000 - i, T0 + dt.timedelta(minutes=i), region, f"{label} {conf}") for i in range(n)]


def backend(store, classifier=None, version=V1, cap=DEFAULT_SCORE_CAP) -> Backend:
    return Backend(store, classifier or StubClassifier(), version, cap, ready=lambda: None)


SCOPE = Scope(dt.date(2026, 1, 1), dt.date(2026, 1, 31))


# --------------------------------------------------------------------------- the cap


def test_at_most_the_cap_everything_is_scored_and_complete():
    store, clf = MemoryStore(comments(300)), StubClassifier()
    cov = ensure_scored(store, clf, V1, SCOPE, 300)
    assert (cov.n_comments, cov.n_scored, cov.complete, cov.n_new) == (300, 300, True, 300)
    assert clf.calls == [300]


def test_above_the_cap_the_newest_are_scored_and_coverage_is_partial():
    rows = comments(301)
    store = MemoryStore(rows)
    cov = ensure_scored(store, StubClassifier(), V1, SCOPE, 300)
    assert (cov.n_comments, cov.n_scored, cov.complete) == (301, 300, False)
    oldest = min(rows, key=lambda c: c[1])
    assert (oldest[0], V1) not in store.predictions  # the oldest is the one left out
    newest = sorted(rows, key=lambda c: c[1], reverse=True)[:300]
    assert {(c[0], V1) for c in newest} == set(store.predictions)
    again = ensure_scored(store, StubClassifier(), V1, SCOPE, 300)
    assert (again.n_scored, again.complete, again.n_new) == (301, True, 1)


def test_ties_on_submitted_at_go_to_the_highest_id():
    rows = [(i, T0, "west", "neutral 0.9") for i in (5, 9, 7)]
    store = MemoryStore(rows)
    ensure_scored(store, StubClassifier(), V1, SCOPE, 2)
    assert set(store.predictions) == {(9, V1), (7, V1)}


def test_a_second_call_scores_nothing():
    store, clf = MemoryStore(comments(5)), StubClassifier()
    ensure_scored(store, clf, V1, SCOPE, 300)
    cov = ensure_scored(store, clf, V1, SCOPE, 300)
    assert (cov.n_new, cov.complete) == (0, True)
    assert clf.calls == [5]  # no second inference


def test_the_cap_and_batch_follow_the_real_container_measurement():
    """Largest multiple of 50 with cap / 9.28 comments/s (slowest repeat, batch 8) <= 30 s."""
    slowest_per_s = 9.28
    assert DEFAULT_SCORE_CAP == 250 == SETTINGS.score_cap
    assert DEFAULT_SCORE_CAP / slowest_per_s <= 30 < (DEFAULT_SCORE_CAP + 50) / slowest_per_s
    assert DEFAULT_BATCH_SIZE == 8 == SETTINGS.batch_size


# --------------------------------------------------------------------------- flags and versions


def test_flag_is_strictly_below_tau():
    tau = 0.84
    proba = np.array([[0.84, 0.16, 0, 0], [0.8399, 0.1601, 0, 0], [0.1, 0.1, 0.1, 0.7]])
    preds = to_predictions(proba, SENTIMENT_LABELS, tau)
    assert [(p.label, p.flagged) for p in preds] == [
        ("positive", False),  # exactly tau: not flagged
        ("positive", True),
        ("mixed", True),
    ]


def test_predictions_are_keyed_by_model_version():
    store = MemoryStore(comments(3))
    ensure_scored(store, StubClassifier(), V1, SCOPE, 300)
    cov = ensure_scored(store, StubClassifier(), V2, SCOPE, 300)
    assert (cov.n_new, cov.n_scored) == (3, 3)  # a new version needs its own scoring
    assert len(store.predictions) == 6
    assert ensure_scored(store, StubClassifier(), V1, SCOPE, 300).n_new == 0


# --------------------------------------------------------------------------- validation

WINDOW = (SETTINGS.window_start, SETTINGS.window_end)


@pytest.mark.parametrize(
    ("start", "end", "region", "message"),
    [
        ("2026-01-02", "2026-01-01", None, "after end"),
        ("20260101", "2026-01-31", None, "ISO date"),
        ("2026-1-1", "2026-01-31", None, "ISO date"),
        ("2024-01-01", "2026-01-01", None, "more than 731 days"),
        ("2023-01-01", "2023-12-31", None, "outside the dataset window"),
        ("2026-01-01", "2026-01-31", "atlantis", "region must be one of"),
        ("2026-01-01", "2026-01-31", "West", "region must be one of"),
        ("2026-01-01'; DROP TABLE x;--", "2026-01-31", None, "ISO date"),
    ],
)
def test_invalid_scopes_are_rejected(start, end, region, message):
    with pytest.raises(InvalidInput, match=message):
        parse_scope(start, end, region, *WINDOW)


def test_span_of_exactly_731_days_is_allowed():
    s = parse_scope("2024-08-30", "2026-08-30", None, *WINDOW)
    assert (s.end - s.start).days + 1 == 731


@pytest.mark.parametrize("limit", [0, 6, 100, -1, True, 2.5, "5"])
def test_limit_outside_1_to_5_is_rejected(limit):
    with pytest.raises(InvalidInput, match="limit must be an integer from 1 to 5"):
        check_limit(limit)


def test_vocabularies_match_the_database():
    assert set(get_args(SiteRegion)) == set(values(Region))
    assert set(SENTIMENT_LABELS) == set(values(TrueSentiment))


# --------------------------------------------------------------------------- MCP contract


async def test_only_the_two_read_tools_are_exposed():
    """ADR-023/ADR-067: no generic query tool, no tool that writes."""
    async with Client(create_server(SETTINGS, backend(MemoryStore([])))) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == {SUMMARY, EXAMPLES}
    assert set(tools[SUMMARY].input_schema["properties"]) == {"start", "end", "region", "bucket"}
    assert set(tools[EXAMPLES].input_schema["properties"]) == {
        "start",
        "end",
        "region",
        "label",
        "flagged_only",
        "limit",
    }
    summary_fields = json.dumps(tools[SUMMARY].output_schema)
    assert "feedback_text" not in summary_fields and "feedback_id" not in summary_fields


async def test_summary_counts_shares_buckets_and_flags():
    rows = comments(3, "negative", 0.99) + [
        (1, T0 + dt.timedelta(days=40), "west", "positive 0.5"),  # February, flagged
    ]
    store = MemoryStore(rows)
    async with Client(create_server(SETTINGS, backend(store))) as client:
        result = await client.call_tool(
            SUMMARY, {"start": "2026-01-01", "end": "2026-03-31", "region": "west"}
        )
    s = result.structured_content
    assert (s["n_comments"], s["n_scored"], s["complete"]) == (4, 4, True)
    assert s["counts"] == {"positive": 1, "neutral": 0, "negative": 3, "mixed": 0}
    assert s["shares"]["negative"] == "0.7500" and s["shares"]["neutral"] == "0.0000"
    assert s["flagged_count"] == 1
    assert [(b["bucket"], b["n_scored"], b["flagged_count"]) for b in s["buckets"]] == [
        ("2026-01", 3, 0),
        ("2026-02", 1, 1),
    ]
    assert "feedback_text" not in json.dumps(s)


async def test_region_filters_the_comment_set():
    store = MemoryStore(comments(2, region="west") + [(77, T0, "central", "mixed 0.9")])
    async with Client(create_server(SETTINGS, backend(store))) as client:
        result = await client.call_tool(
            SUMMARY, {"start": "2026-01-01", "end": "2026-01-31", "region": "central"}
        )
    assert result.structured_content["n_comments"] == 1
    assert (77, V1) in store.predictions and (10_000, V1) not in store.predictions


async def test_examples_order_most_confident_first_ties_by_lowest_id():
    store = MemoryStore(
        [
            (5, T0, "west", "negative 0.95"),
            (3, T0, "west", "negative 0.99"),
            (9, T0, "west", "negative 0.99"),
            (4, T0, "west", "negative 0.70"),
            (8, T0, "west", "positive 0.99"),
        ]
    )
    async with Client(create_server(SETTINGS, backend(store))) as client:
        top = await client.call_tool(
            EXAMPLES, {"start": "2026-01-01", "end": "2026-01-31", "label": "negative"}
        )
        low = await client.call_tool(
            EXAMPLES, {"start": "2026-01-01", "end": "2026-01-31", "flagged_only": True}
        )
    assert [e["feedback_id"] for e in top.structured_content["examples"]] == [3, 9, 5, 4]
    assert top.structured_content["examples"][0]["feedback_text"] == "negative 0.99"
    assert [e["feedback_id"] for e in low.structured_content["examples"]] == [4]


async def test_examples_flagged_only_is_least_confident_first():
    store = MemoryStore([(i, T0, "west", f"neutral 0.{50 + i}") for i in range(1, 8)])
    async with Client(create_server(SETTINGS, backend(store))) as client:
        result = await client.call_tool(
            EXAMPLES,
            {"start": "2026-01-01", "end": "2026-01-31", "flagged_only": True, "limit": 3},
        )
    assert [e["feedback_id"] for e in result.structured_content["examples"]] == [1, 2, 3]


async def test_examples_reject_a_limit_above_5():
    async with Client(create_server(SETTINGS, backend(MemoryStore(comments(9))))) as client:
        result = await client.call_tool(
            EXAMPLES, {"start": "2026-01-01", "end": "2026-01-31", "limit": 6}
        )
    assert result.is_error
    assert "limit must be an integer from 1 to 5" in result.content[0].text


async def test_bad_input_is_a_clear_error_and_scores_nothing():
    clf = StubClassifier()
    store = MemoryStore(comments(3))
    async with Client(create_server(SETTINGS, backend(store, clf))) as client:
        bad = await client.call_tool(SUMMARY, {"start": "2026-02-01", "end": "2026-01-01"})
        bucket = await client.call_tool(
            SUMMARY, {"start": "2026-01-01", "end": "2026-01-31", "bucket": "week"}
        )
    assert bad.is_error and "after end" in bad.content[0].text
    assert bucket.is_error
    assert clf.calls == [] and store.predictions == {}


async def test_store_failure_does_not_leak_detail():
    class Broken(MemoryStore):
        def count_comments(self, scope):
            raise RuntimeError("permission denied for table secret_stuff")

    async with Client(create_server(SETTINGS, backend(Broken([])))) as client:
        result = await client.call_tool(SUMMARY, {"start": "2026-01-01", "end": "2026-01-31"})
    assert result.is_error
    assert result.content[0].text.endswith("feedback query failed")
    assert "secret_stuff" not in result.content[0].text


def test_healthz_reports_ready_and_unready():
    ok = backend(MemoryStore([]))
    with TestClient(create_app(SETTINGS, ok)) as client:
        r = client.get("/healthz", headers={"host": "localhost:8102"})
    assert r.status_code == 200 and r.json()["model_version"] == V1

    def down():
        raise OSError("connection refused")

    bad = Backend(MemoryStore([]), StubClassifier(), V1, 300, ready=down)
    with TestClient(create_app(SETTINGS, bad)) as client:
        r = client.get("/healthz", headers={"host": "localhost:8102"})
    assert r.status_code == 503


# --------------------------------------------------------------------------- start-up


def _artifact(tmp_path: Path) -> Path:
    files = {"model.safetensors": b"weights", "tokenizer.json": b"{}"}
    for name, content in files.items():
        (tmp_path / name).write_bytes(content)
    manifest = {
        "artifact": "bert_test",
        "labels": list(SENTIMENT_LABELS),
        "max_length": 64,
        "files": {n: hashlib.sha256(c).hexdigest() for n, c in files.items()},
        "calibration": {"temperature": 1.03, "threshold": 0.84},
    }
    path = tmp_path / "bert_test.manifest.json"
    path.write_bytes(json.dumps(manifest).encode())
    return path


def test_a_verified_artifact_is_versioned_by_its_manifest_hash(tmp_path):
    manifest = _artifact(tmp_path)
    art = load_verified(tmp_path, manifest)
    assert art.model_version == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert (art.temperature, art.threshold, art.max_length) == (1.03, 0.84, 64)


def test_refuses_to_start_on_an_altered_file(tmp_path):
    manifest = _artifact(tmp_path)
    (tmp_path / "model.safetensors").write_bytes(b"tampered")
    with pytest.raises(ArtifactIntegrityError, match="model.safetensors does not match"):
        load_verified(tmp_path, manifest)


def test_refuses_to_start_on_a_missing_file(tmp_path):
    manifest = _artifact(tmp_path)
    (tmp_path / "tokenizer.json").unlink()
    with pytest.raises(ArtifactIntegrityError, match="tokenizer.json is missing"):
        load_verified(tmp_path, manifest)


def test_refuses_to_start_without_calibration(tmp_path):
    manifest = _artifact(tmp_path)
    data = json.loads(manifest.read_bytes())
    data["calibration"]["threshold"] = None
    manifest.write_bytes(json.dumps(data).encode())
    with pytest.raises(ArtifactIntegrityError, match="no calibration"):
        load_verified(tmp_path, manifest)


def test_the_server_process_refuses_to_start_on_a_mismatch(tmp_path, monkeypatch):
    """`__main__` builds the backend (hash check) before it listens."""
    import mcp_feedback.__main__ as entry

    manifest = _artifact(tmp_path)
    (tmp_path / "model.safetensors").write_bytes(b"tampered")
    settings = Settings(
        db_host="unused",
        db_port=5432,
        db_name="unused",
        db_user="unused",
        models_dir=tmp_path,
        manifest_path=manifest,
    )
    monkeypatch.setattr(entry.Settings, "from_env", classmethod(lambda cls: settings))
    served = []
    monkeypatch.setattr(entry.uvicorn, "run", lambda *a, **k: served.append(a))
    with pytest.raises(ArtifactIntegrityError):
        entry.main()
    assert served == []


@pytest.mark.parametrize(
    ("cpu_max", "expected"), [("100000 100000", 1), ("150000 100000", 2), ("max 100000", None)]
)
def test_threads_follow_the_cgroup_quota_not_the_host(tmp_path, cpu_max, expected):
    import os

    (tmp_path / "cpu.max").write_text(cpu_max)
    host = os.cpu_count() or 1
    assert container_cpus(tmp_path) == (min(host, expected) if expected else host)
