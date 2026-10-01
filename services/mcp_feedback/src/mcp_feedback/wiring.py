"""Assemble the real backend: verified artifact, lazy BERT, SQL store as app_sentiment."""

from __future__ import annotations

import logging
import time

from .artifact import load_verified
from .classifier import BertClassifier
from .config import Settings
from .server import Backend
from .store import SqlStore, make_engine

log = logging.getLogger("mcp_feedback")


def build_backend(settings: Settings) -> Backend:
    began = time.perf_counter()
    artifact = load_verified(settings.models_dir, settings.manifest_path)
    log.info(
        "artifact verified",
        extra={
            "artifact": artifact.name,
            "model_version": artifact.model_version,
            "files": len(artifact.files),
            "seconds": round(time.perf_counter() - began, 2),
        },
    )
    store = SqlStore(make_engine(settings))
    return Backend(
        store=store,
        classifier=BertClassifier(artifact, settings.batch_size),
        model_version=artifact.model_version,
        score_cap=settings.score_cap,
        ready=store.ping,
    )
