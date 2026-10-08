"""FastAPI app: the Agent Card at the well-known path, JSON-RPC at `/`, and `/healthz`."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

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
from .executor import SentimentExecutor
from .mcp_client import mcp_ready
from .parsing import ParsingLLM

log = logging.getLogger("agent_sentiment")


def create_app(
    settings: Settings,
    llm: ParsingLLM | None = None,
    ready: Callable[[], Awaitable[bool]] | None = None,
) -> FastAPI:
    card = build_agent_card(settings.public_url)
    handler = DefaultRequestHandler(
        agent_executor=SentimentExecutor(
            settings, llm if llm is not None else LLMClient.from_env("specialist")
        ),
        # In-memory is enough: tasks are single-shot and finish inside one call
        # (ADR-031), so no task outlives its request or needs another replica.
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    app = FastAPI(title="agent_sentiment", version="0.1.0")

    async def check_mcp() -> bool:
        return await (ready or (lambda: mcp_ready(settings.mcp_feedback_url)))()

    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(card),
        jsonrpc_routes=create_jsonrpc_routes(handler, rpc_url="/"),
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "service": "agent_sentiment"}

    @app.get("/readyz")
    async def readyz() -> JSONResponse:
        """Ready: the MCP server answers (and so its database). Startup probes point here."""
        if await check_mcp():
            return JSONResponse({"status": "ready", "service": "agent_sentiment"})
        log.warning("readiness check failed: MCP server not ready")
        return JSONResponse(
            {"status": "unavailable", "service": "agent_sentiment"}, status_code=503
        )

    return app
