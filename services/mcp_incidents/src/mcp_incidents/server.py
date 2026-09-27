"""The incidents MCP server: narrow, aggregate-only tools over streamable HTTP, stateless.

No generic query tool, ever (ADR-023): each tool is a purpose-built function over the
columns it needs, with fixed SQL. Streamable HTTP in stateless mode, on MCP 2026-07-28:
no session is held between requests, so any replica can serve any call.

Tools:
- `get_incidents_by_date_range`: incident count by severity.
- `get_incident_rate`, `get_sla_compliance`, `get_first_time_fix_rate`: the §6 metrics,
  optionally broken down by account, region, service type or technician.
"""

from __future__ import annotations

import datetime as dt
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any

import anyio
from common import TRACE_ID_KEY, bind_trace_id
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field
from schemas import (
    FirstTimeFixResult,
    GroupBy,
    IncidentRateResult,
    IncidentSummary,
    SlaComplianceResult,
)
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import metrics
from .config import Settings
from .queries import InvalidRange, count_by_severity, make_engine, parse_date_range

log = logging.getLogger("mcp_incidents")

TOOL_NAME = "get_incidents_by_date_range"  # the original tool
INCIDENT_RATE = "get_incident_rate"
SLA_COMPLIANCE = "get_sla_compliance"
FIRST_TIME_FIX = "get_first_time_fix_rate"

Start = Annotated[str, Field(description="First day, inclusive: YYYY-MM-DD (UTC).")]
End = Annotated[str, Field(description="Last day, inclusive: YYYY-MM-DD (UTC).")]
GroupByArg = Annotated[
    GroupBy | None,
    Field(
        description="Optional breakdown: account, region (the site's), service_type, or "
        "technician (who did the work). Top 25 groups, worst first."
    ),
]


@dataclass(frozen=True)
class Backend:
    """The query functions behind the tools. Replaced with fakes in the offline tests."""

    incidents: Callable[[dt.date, dt.date], IncidentSummary]
    incident_rate: Callable[[dt.date, dt.date, GroupBy | None], IncidentRateResult]
    sla_compliance: Callable[[dt.date, dt.date, GroupBy | None], SlaComplianceResult]
    first_time_fix_rate: Callable[[dt.date, dt.date, GroupBy | None], FirstTimeFixResult]

    @classmethod
    def from_settings(cls, settings: Settings) -> Backend:
        engine = make_engine(settings)
        return cls(
            incidents=lambda s, e: count_by_severity(engine, s, e),
            incident_rate=lambda s, e, g: metrics.incident_rate(engine, s, e, g),
            sla_compliance=lambda s, e, g: metrics.sla_compliance(engine, s, e, g),
            first_time_fix_rate=lambda s, e, g: metrics.first_time_fix_rate(engine, s, e, g),
        )


def create_server(settings: Settings, backend: Backend | None = None) -> MCPServer:
    backend = backend or Backend.from_settings(settings)
    server = MCPServer(
        "mcp_incidents",
        instructions="Aggregate incident and quality metrics for the field-service dataset. "
        "Counts and rates only; no rows, no free text.",
        version="0.2.0",
    )

    async def run(tool: str, ctx: Context, start: str, end: str, call: Callable, *args) -> Any:
        """Validate the range, run the fixed query off the event loop, log, map errors."""
        meta = ctx.request_context.meta or {}
        with bind_trace_id(meta.get(TRACE_ID_KEY)):
            try:
                s, e = parse_date_range(start, end, settings.window_start, settings.window_end)
            except InvalidRange as exc:
                log.info("tool rejected input", extra={"tool": tool, "error": str(exc)})
                raise ToolError(str(exc)) from None
            began = time.perf_counter()
            try:
                result = await anyio.to_thread.run_sync(call, s, e, *args)
            except Exception:
                # Log the cause here; the client gets a generic message, never SQL detail.
                log.exception("tool query failed", extra={"tool": tool})
                raise ToolError("incident query failed") from None
            log.info(
                "tool call",
                extra={
                    "tool": tool,
                    "start": s.isoformat(),
                    "end": e.isoformat(),
                    "group_by": args[0] if args else None,
                    "duration_ms": round((time.perf_counter() - began) * 1000, 1),
                },
            )
            return result

    @server.tool(name=TOOL_NAME)
    async def get_incidents_by_date_range(start: Start, end: End, ctx: Context) -> IncidentSummary:
        """Count incidents reported in a date range, in total and by severity.

        Returns aggregates only: no incident rows and no free-text fields.
        """
        return await run(TOOL_NAME, ctx, start, end, backend.incidents)

    @server.tool(name=INCIDENT_RATE)
    async def get_incident_rate(
        start: Start, end: End, ctx: Context, group_by: GroupByArg = None
    ) -> IncidentRateResult:
        """Incidents per 100 completed requests (data dictionary §6).

        Date rule: incidents whose reported_at is in the range, over requests whose
        completed_at is in the range. By technician, only incidents attributed to that
        technician count (ADR-033), over the jobs they completed. Rates are strings,
        rounded half-up to 4 places; a zero denominator gives a null rate.

        Groups are sorted worst first: highest rate first. The top 25 are kept.
        """
        return await run(INCIDENT_RATE, ctx, start, end, backend.incident_rate, group_by)

    @server.tool(name=SLA_COMPLIANCE)
    async def get_sla_compliance(
        start: Start, end: End, ctx: Context, group_by: GroupByArg = None
    ) -> SlaComplianceResult:
        """Share of dispatched requests completed within their SLA window (§6).

        Date rule: requests whose dispatched_at is in the range. The SLA clock starts at
        dispatched_at; requests never dispatched, or not completed (null sla_met), are
        excluded from the denominator.

        Groups are sorted worst first: lowest rate first. The top 25 are kept.
        """
        return await run(SLA_COMPLIANCE, ctx, start, end, backend.sla_compliance, group_by)

    @server.tool(name=FIRST_TIME_FIX)
    async def get_first_time_fix_rate(
        start: Start, end: End, ctx: Context, group_by: GroupByArg = None
    ) -> FirstTimeFixResult:
        """Share of completed requests with no follow-up visit (§6).

        Date rule: requests whose completed_at is in the range. A child request
        (parent_request_id pointing back) counts against its parent whatever its date,
        unless it was cancelled: a cancelled follow-up means no return visit happened.

        Groups are sorted worst first: lowest rate first. The top 25 are kept.
        """
        return await run(FIRST_TIME_FIX, ctx, start, end, backend.first_time_fix_rate, group_by)

    @server.custom_route("/healthz", methods=["GET"])
    async def healthz(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "service": "mcp_incidents"})

    return server


def create_app(settings: Settings, backend: Backend | None = None) -> Starlette:
    server = create_server(settings, backend)
    return server.streamable_http_app(
        stateless_http=True,
        json_response=True,  # blocking request/response; nothing here streams
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=list(settings.allowed_hosts),
            allowed_origins=[],
        ),
    )
