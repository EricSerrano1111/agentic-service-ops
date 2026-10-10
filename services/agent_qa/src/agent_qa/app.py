"""FastAPI app: the Agent Card at the well-known path, JSON-RPC at `/`, `/healthz`, `/readyz`."""

from __future__ import annotations

import asyncio
import logging

from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    add_a2a_routes_to_fastapi,
    create_agent_card_routes,
    create_jsonrpc_routes,
)
from a2a.server.tasks import InMemoryTaskStore
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from llm import LLMClient

from .card import build_agent_card
from .config import Settings
from .db import PostgresSource, Source, make_engine
from .executor import QAExecutor
from .forecast import Manifest
from .interpretation import InterpretationLLM, Interpreter
from .sentiment import SentimentManifest
from .verify import Verifier

log = logging.getLogger("agent_qa")


def create_app(
    settings: Settings,
    llm: InterpretationLLM | None = None,
    source: Source | None = None,
    manifest: Manifest | None = None,
    sentiment_manifest: SentimentManifest | None = None,
) -> FastAPI:
    card = build_agent_card(settings.public_url)
    src = source if source is not None else PostgresSource(make_engine(settings))
    verifier = Verifier(
        src,
        settings,
        manifest if manifest is not None else Manifest.load(settings.manifest_path),
        sentiment_manifest
        if sentiment_manifest is not None
        else SentimentManifest.load(settings.sentiment_manifest_path),
        Interpreter(llm if llm is not None else LLMClient.from_env("qa")),
    )
    handler = DefaultRequestHandler(
        agent_executor=QAExecutor(settings, verifier),
        # In-memory is enough: tasks are single-shot and finish inside one call (ADR-031).
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    app = FastAPI(title="agent_qa", version="0.1.0")
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(card),
        jsonrpc_routes=create_jsonrpc_routes(handler, rpc_url="/"),
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "service": "agent_qa"}

    @app.get("/readyz")
    async def readyz() -> JSONResponse:
        """Ready: the database answers as `app_qa`. Startup probes point here."""
        try:
            await asyncio.to_thread(src.ping)
        except Exception:
            log.warning("readiness check failed: database not ready")
            return JSONResponse({"status": "unavailable", "service": "agent_qa"}, status_code=503)
        return JSONResponse({"status": "ready", "service": "agent_qa"})

    return app
