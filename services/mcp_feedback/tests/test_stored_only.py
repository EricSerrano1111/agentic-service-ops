"""`stored_only` scoring mode (ADR-100): no model, no scoring, fail closed on a gap.

Offline, like test_mcp_feedback.py, whose in-memory store and stub it reuses. The lazy path's
own tests are in that file and are unchanged.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from mcp import Client
from mcp_feedback.artifact import ArtifactIntegrityError, load_manifest
from mcp_feedback.classifier import Prediction
from mcp_feedback.config import SCORING_MODES, Settings
from mcp_feedback.server import EXAMPLES, SUMMARY, Backend, create_server
from mcp_feedback.wiring import build_backend
from test_mcp_feedback import SETTINGS, V1, V2, MemoryStore, StubClassifier, _artifact, comments

pytestmark = pytest.mark.anyio
MANIFEST = Path(__file__).resolve().parents[3] / "ml/sentiment/artifacts/bert_v1.manifest.json"
JAN = {"start": "2026-01-01", "end": "2026-01-31"}


@pytest.fixture
def anyio_backend():
    return "asyncio"


def stored(store, version=V1) -> Backend:
    return Backend(store, None, version, 0, ready=lambda: None, stored_only=True)


def prescored(n: int, version=V1) -> MemoryStore:
    """n comments, every one with a stored prediction under `version`."""
    store = MemoryStore(comments(n))
    for fid, _, _, text in store.comments:
        label, conf = text.split()
        store.predictions[(fid, version)] = Prediction(label, float(conf), float(conf) < 0.84)
    return store


async def _call(backend: Backend, tool: str, args: dict):
    async with Client(create_server(SETTINGS, backend)) as client:
        return await client.call_tool(tool, args)


# --------------------------------------------------------------------- configuration


def test_scoring_defaults_to_lazy_and_rejects_an_unknown_mode(monkeypatch):
    for k, v in {
        "POSTGRES_HOST": "h",
        "POSTGRES_DB": "d",
        "DB_ROLE_SENTIMENT_USER": "u",
        "DB_ROLE_SENTIMENT_PASSWORD": "p",
    }.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("MCP_FEEDBACK_SCORING", raising=False)
    monkeypatch.delenv("CLOUD_SQL_INSTANCE", raising=False)
    assert SCORING_MODES == ("lazy", "stored_only")
    assert Settings.from_env().scoring_mode == "lazy"
    monkeypatch.setenv("MCP_FEEDBACK_SCORING", "stored_only")
    assert Settings.from_env().scoring_mode == "stored_only"
    monkeypatch.setenv("MCP_FEEDBACK_SCORING", "eager")
    with pytest.raises(RuntimeError, match="MCP_FEEDBACK_SCORING"):
        Settings.from_env()


# --------------------------------------------------------------------- start-up


def test_the_manifest_alone_is_enough_and_is_the_model_version(tmp_path):
    manifest = _artifact(tmp_path)
    for weight in tmp_path.iterdir():
        if weight != manifest:
            weight.unlink()  # no weights anywhere
    art = load_manifest(manifest)
    import hashlib

    assert art.model_version == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert (art.temperature, art.threshold) == (1.03, 0.84)


def test_a_missing_manifest_or_calibration_still_stops_start_up(tmp_path):
    with pytest.raises(ArtifactIntegrityError, match="manifest not found"):
        load_manifest(tmp_path / "absent.json")
    manifest = _artifact(tmp_path)
    data = json.loads(manifest.read_bytes())
    data["calibration"]["temperature"] = None
    manifest.write_bytes(json.dumps(data).encode())
    with pytest.raises(ArtifactIntegrityError, match="no calibration"):
        load_manifest(manifest)


def test_stored_only_wiring_builds_no_classifier_and_needs_no_weights(tmp_path):
    settings = Settings(
        db_host="unused",
        db_port=5432,
        db_name="unused",
        db_user="unused",
        models_dir=tmp_path / "absent",
        manifest_path=MANIFEST,
        scoring_mode="stored_only",
    )
    backend = build_backend(settings)
    assert backend.stored_only and backend.classifier is None
    import hashlib

    assert backend.model_version == hashlib.sha256(MANIFEST.read_bytes()).hexdigest()


def test_stored_only_never_imports_torch_after_start_up_and_a_query():
    """In a clean interpreter, so another test's import cannot mask or cause it."""
    script = textwrap.dedent(
        """
        import asyncio, json, sys
        from pathlib import Path
        from mcp import Client
        from mcp_feedback.config import Settings
        from mcp_feedback.server import SUMMARY, EXAMPLES, create_server
        from mcp_feedback.scoring import CountRow
        from mcp_feedback.wiring import build_backend
        import dataclasses

        class Store:
            def count_comments(self, scope): return 2
            def count_scored(self, version, scope): return 2
            def label_bucket_counts(self, version, scope, bucket):
                return [CountRow("positive", "2026-01", 2, 0)]
            def examples(self, *a): return []
            def ping(self): pass

        s = Settings(db_host="unused", db_port=5432, db_name="unused", db_user="unused",
                     models_dir=Path("/nonexistent"), manifest_path=Path(sys.argv[1]),
                     scoring_mode="stored_only")
        backend = dataclasses.replace(build_backend(s), store=Store())
        after_startup = sorted(m for m in sys.modules if m.split(".")[0] in
                               ("torch", "transformers", "safetensors", "tokenizers"))

        async def go():
            async with Client(create_server(s, backend)) as c:
                a = await c.call_tool(SUMMARY, {"start": "2026-01-01", "end": "2026-01-31"})
                b = await c.call_tool(EXAMPLES, {"start": "2026-01-01", "end": "2026-01-31"})
                return a.is_error, b.is_error
        errors = asyncio.run(go())
        after_query = sorted(m for m in sys.modules if m.split(".")[0] in
                             ("torch", "transformers", "safetensors", "tokenizers"))
        print(json.dumps({"startup": after_startup, "query": after_query, "errors": errors}))
        """
    )
    out = subprocess.run(
        [sys.executable, "-I", "-c", script, str(MANIFEST)], capture_output=True, text=True
    )
    assert out.returncode == 0, out.stderr[-800:]
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result == {"startup": [], "query": [], "errors": [False, False]}


# --------------------------------------------------------------------- answers


async def test_complete_predictions_answer_exactly_as_lazy_does_and_nothing_is_scored():
    lazy_clf = StubClassifier()
    lazy = Backend(prescored(7), lazy_clf, V1, 250, ready=lambda: None)
    only = stored(prescored(7))
    for tool, args in (
        (SUMMARY, {**JAN, "bucket": "month"}),
        (SUMMARY, {**JAN, "bucket": "quarter", "region": "west"}),
        (EXAMPLES, {**JAN, "limit": 3}),
        (EXAMPLES, {**JAN, "flagged_only": True}),
    ):
        a, b = await _call(lazy, tool, args), await _call(only, tool, args)
        assert not a.is_error and not b.is_error
        assert a.content[0].text == b.content[0].text
    assert lazy_clf.calls == []  # lazy had nothing to score either: that is the premise


async def test_a_comment_without_a_prediction_fails_closed_with_no_partial_answer():
    store = prescored(5)
    store.comments.append((1, store.comments[0][1], "west", "negative 0.95"))  # unscored
    before = dict(store.predictions)
    for tool in (SUMMARY, EXAMPLES):
        result = await _call(stored(store), tool, JAN)
        assert result.is_error
        text = result.content[0].text
        assert text.endswith("predictions_incomplete")
        assert "n_scored" not in text and "positive" not in text  # no figure, no count
    assert store.predictions == before  # nothing scored, nothing stored


async def test_predictions_under_another_model_version_fail_closed():
    store = prescored(4, version=V2)
    result = await _call(stored(store, version=V1), SUMMARY, JAN)
    assert result.is_error and result.content[0].text.endswith("predictions_incomplete")
    ok = await _call(stored(store, version=V2), SUMMARY, JAN)
    assert not ok.is_error


async def test_the_incomplete_log_carries_counts_and_no_text():
    import logging

    class Collect(logging.Handler):
        def __init__(self) -> None:
            super().__init__(logging.ERROR)
            self.records: list[logging.LogRecord] = []

        def emit(self, record: logging.LogRecord) -> None:
            self.records.append(record)

    # A handler on the logger itself: other tests in the session reconfigure the root logger.
    handler, logger = Collect(), logging.getLogger("mcp_feedback")
    was = (logger.disabled, logger.level)
    logger.disabled, logger.level = False, logging.ERROR  # an earlier test may have disabled it
    logger.addHandler(handler)
    store = prescored(3)
    store.comments.append((2, store.comments[0][1], "west", "negative 0.95"))
    try:
        await _call(stored(store), SUMMARY, JAN)
    finally:
        logger.removeHandler(handler)
        logger.disabled, logger.level = was
    [rec] = [r for r in handler.records if r.getMessage() == "stored predictions incomplete"]
    assert (rec.n_comments, rec.n_scored) == (4, 3)
    assert "negative" not in rec.getMessage()


async def test_an_empty_range_is_complete():
    result = await _call(stored(MemoryStore([])), SUMMARY, JAN)
    assert not result.is_error
