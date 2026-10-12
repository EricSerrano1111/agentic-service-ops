"""Assemble the real backend: the artifact and the SQL store as app_sentiment, and either lazy
BERT (`lazy`) or stored predictions only (`stored_only`, ADR-100)."""

from __future__ import annotations

import logging
import time

from .artifact import load_manifest, load_verified
from .config import Settings
from .server import Backend
from .store import SqlStore, make_engine

log = logging.getLogger("mcp_feedback")


def build_backend(settings: Settings) -> Backend:
    began = time.perf_counter()
    stored_only = settings.scoring_mode == "stored_only"
    if stored_only:
        # No weights in this image and no torch: the manifest alone is checked (ADR-100).
        artifact = load_manifest(settings.manifest_path)
    else:
        artifact = load_verified(settings.models_dir, settings.manifest_path)
    log.info(
        "artifact verified",
        extra={
            "artifact": artifact.name,
            "model_version": artifact.model_version,
            "scoring_mode": settings.scoring_mode,
            "files": len(artifact.files),
            "seconds": round(time.perf_counter() - began, 2),
        },
    )
    store = SqlStore(make_engine(settings))
    classifier = None
    if not stored_only:
        from .classifier import BertClassifier

        classifier = BertClassifier(artifact, settings.batch_size)
    return Backend(
        store=store,
        classifier=classifier,
        model_version=artifact.model_version,
        score_cap=settings.score_cap,
        ready=store.ping,
        stored_only=stored_only,
    )
