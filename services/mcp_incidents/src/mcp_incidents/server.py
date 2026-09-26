"""The incidents MCP server: one narrow tool over streamable HTTP, stateless.

No generic query tool, ever (ADR-023): each tool is a purpose-built function over the
columns it needs. Streamable HTTP in stateless mode, on MCP 2026-07-28: no session is
held between requests, so any replica can serve any call.
"""

from __future__ import annotations

import datetime as dt
import logging
import time
from collections.abc import Callable
from typing import Annotated

import anyio
from common import TRACE_ID_KEY, bind_trace_id
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field
from schemas import IncidentSummary
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse

from .config import Settings
from .queries import InvalidRange, count_by_severity, make_engine, parse_date_range

log = logging.getLogger("mcp_incidents")

TOOL_NAME = "get_incidents_by_date_range"

#: (start, end) -> summary. Swapped for a fake in the offline unit tests.
Summarize = Callable[[dt.date, dt.date], IncidentSummary]


def create_server(settings: Settings, summarize: Summarize | None = None) -> MCPServer:
    if summarize is None:
        engine = make_engine(settings)

        def summarize(start: dt.date, end: dt.date) -> IncidentSummary:
            return count_by_severity(engine, start, end)

    server = MCPServer(
        "mcp_incidents",
        instructions="Aggregate incident metrics for the field-service dataset. Counts only.",
        version="0.1.0",
    )

    @server.tool(name=TOOL_NAME)
    async def get_incidents_by_date_range(
        start: Annotated[str, Field(description="First day, inclusive: YYYY-MM-DD (UTC).")],
        end: Annotated[str, Field(description="Last day, inclusive: YYYY-MM-DD (UTC).")],
        ctx: Context,
    ) -> IncidentSummary:
        """Count incidents reported in a date range, in total and by severity.

        Returns aggregates only: no incident rows and no free-text fields.
        """
        meta = ctx.request_context.meta or {}
        with bind_trace_id(meta.get(TRACE_ID_KEY)):
            try:
                s, e = parse_date_range(start, end, settings.window_start, settings.window_end)
            except InvalidRange as exc:
                log.info("tool rejected input", extra={"tool": TOOL_NAME, "error": str(exc)})
                raise ToolError(str(exc)) from None
            began = time.perf_counter()
            try:
                result = await anyio.to_thread.run_sync(summarize, s, e)
            except Exception:
                # Log the cause here; the client gets a generic message, never SQL detail.
                log.exception("tool query failed", extra={"tool": TOOL_NAME})
                raise ToolError("incident query failed") from None
            log.info(
                "tool call",
                extra={
                    "tool": TOOL_NAME,
                    "start": s.isoformat(),
                    "end": e.isoformat(),
                    "incident_count": result.incident_count,
                    "duration_ms": round((time.perf_counter() - began) * 1000, 1),
                },
            )
            return result

    @server.custom_route("/healthz", methods=["GET"])
    async def healthz(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "service": "mcp_incidents"})

    return server


def create_app(settings: Settings, summarize: Summarize | None = None) -> Starlette:
    server = create_server(settings, summarize)
    return server.streamable_http_app(
        stateless_http=True,
        json_response=True,  # blocking request/response; nothing here streams
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=list(settings.allowed_hosts),
            allowed_origins=[],
        ),
    )
