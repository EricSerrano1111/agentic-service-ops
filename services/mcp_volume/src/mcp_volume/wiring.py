"""Assemble the real backend: the verified artifact and the SQL store as app_forecast."""

from __future__ import annotations

import logging
import time

from .artifact import load_verified
from .config import Settings
from .server import Backend
from .store import SqlStore, make_engine

log = logging.getLogger("mcp_volume")


def build_backend(settings: Settings) -> Backend:
    began = time.perf_counter()
    artifact = load_verified(settings.models_dir, settings.manifest_path)
    log.info(
        "artifact verified",
        extra={
            "model_version": artifact.model_version,
            "slices": len(artifact.slices),
            "seconds": round(time.perf_counter() - began, 3),
        },
    )
    store = SqlStore(make_engine(settings))
    return Backend(artifact=artifact, history=store.history, ready=store.ping)
