"""The incidents MCP server: narrow, aggregate-only tools over streamable HTTP, stateless.

No generic query tool, ever (ADR-023): each tool is a purpose-built function over the
columns it needs, with fixed SQL. Streamable HTTP in stateless mode, on MCP 2026-07-28:
no session is held between requests, so any replica can serve any call.

Tools:
- `get_incidents_by_date_range`: incident count by severity, optionally broken down by
  account, region, service type, technician, incident type or severity (ADR-073).
- `get_incident_rate`, `get_sla_compliance`, `get_first_time_fix_rate`: the §6 metrics,
  optionally broken down by account, region, service type or technician.
- `find_technician`: up to 5 technicians whose display name matches a name (ADR-073).
- `get_repeat_visit_drivers`: repeat-visit rate by group, with a significance rule.

The count and the three metrics also take an optional `technician_id` filter, never
together with a breakdown.
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
    IncidentGroupBy,
    IncidentRateResult,
    IncidentSummary,
    RepeatBy,
    RepeatDriversResult,
    SlaComplianceResult,
    TechnicianMatches,
)
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import metrics, repeats
from .config import Settings
from .queries import (
    MAX_NAME_LENGTH,
    InvalidArgument,
    InvalidRange,
    count_by_severity,
    find_technician,
    make_engine,
    parse_date_range,
)

log = logging.getLogger("mcp_incidents")

TOOL_NAME = "get_incidents_by_date_range"  # the original tool
INCIDENT_RATE = "get_incident_rate"
SLA_COMPLIANCE = "get_sla_compliance"
FIRST_TIME_FIX = "get_first_time_fix_rate"
FIND_TECHNICIAN = "find_technician"
REPEAT_DRIVERS = "get_repeat_visit_drivers"

Start = Annotated[str, Field(description="First day, inclusive: YYYY-MM-DD (UTC).")]
End = Annotated[str, Field(description="Last day, inclusive: YYYY-MM-DD (UTC).")]
GroupByArg = Annotated[
    GroupBy | None,
    Field(
        description="Optional breakdown: account, region (the site's), service_type, or "
        "technician (who did the work). Top 25 groups, worst first."
    ),
]
CountGroupByArg = Annotated[
    IncidentGroupBy | None,
    Field(
        description="Optional breakdown: account, region (the site's), service_type, "
        "technician (attributed; incidents with none form an 'unattributed' group), "
        "incident_type or severity. Top 25 groups, highest count first."
    ),
]
TechnicianArg = Annotated[
    int | None,
    Field(
        ge=1,
        description="Optional: one technician's id, from find_technician. Not combinable "
        "with group_by.",
    ),
]
RepeatByArg = Annotated[
    RepeatBy,
    Field(
        description="incident_type (other incident types on the original job), "
        "service_type, region (the site's), account or technician (assigned to the "
        "original job)."
    ),
]
NameArg = Annotated[
    str,
    Field(
        min_length=1,
        max_length=MAX_NAME_LENGTH,
        description="A technician's name or part of it (whole words), e.g. a first name. "
        "Letters, spaces, apostrophes, hyphens and periods only; no wildcards.",
    ),
]


@dataclass(frozen=True)
class Backend:
    """The query functions behind the tools. Replaced with fakes in the offline tests."""

    incidents: Callable[[dt.date, dt.date, IncidentGroupBy | None, int | None], IncidentSummary]
    incident_rate: Callable[[dt.date, dt.date, GroupBy | None, int | None], IncidentRateResult]
    sla_compliance: Callable[[dt.date, dt.date, GroupBy | None, int | None], SlaComplianceResult]
    first_time_fix_rate: Callable[
        [dt.date, dt.date, GroupBy | None, int | None], FirstTimeFixResult
    ]
    find_technician: Callable[[str], TechnicianMatches]
    repeat_drivers: Callable[[dt.date, dt.date, RepeatBy], RepeatDriversResult]

    @classmethod
    def from_settings(cls, settings: Settings) -> Backend:
        engine = make_engine(settings)
        return cls(
            incidents=lambda s, e, g, t: count_by_severity(engine, s, e, g, t),
            incident_rate=lambda s, e, g, t: metrics.incident_rate(engine, s, e, g, t),
            sla_compliance=lambda s, e, g, t: metrics.sla_compliance(engine, s, e, g, t),
            first_time_fix_rate=lambda s, e, g, t: metrics.first_time_fix_rate(engine, s, e, g, t),
            find_technician=lambda name: find_technician(engine, name),
            repeat_drivers=lambda s, e, by: repeats.repeat_drivers(engine, s, e, by),
        )


def create_server(settings: Settings, backend: Backend | None = None) -> MCPServer:
    backend = backend or Backend.from_settings(settings)
    server = MCPServer(
        "mcp_incidents",
        instructions="Aggregate incident and quality metrics for the field-service dataset. "
        "Counts and rates only; no rows, no free text.",
        version="0.2.0",
    )

    def reject(tool: str, message: str) -> ToolError:
        log.info("tool rejected input", extra={"tool": tool, "error": message})
        return ToolError(message)

    async def call_backend(tool: str, call: Callable, *args) -> Any:
        """Run the fixed query off the event loop and map errors. A caller error (an
        unknown technician id, a bad name) comes back verbatim; anything else is logged
        and the client gets a generic message, never SQL detail."""
        try:
            return await anyio.to_thread.run_sync(call, *args)
        except InvalidArgument as exc:
            raise reject(tool, str(exc)) from None
        except Exception:
            log.exception("tool query failed", extra={"tool": tool})
            raise ToolError("incident query failed") from None

    async def run(
        tool: str,
        ctx: Context,
        start: str,
        end: str,
        call: Callable,
        group_by: str | None = None,
        technician_id: int | None = None,
        *,
        filtered: bool = True,
    ) -> Any:
        """Validate the range (and the filter), run the query, log."""
        meta = ctx.request_context.meta or {}
        with bind_trace_id(meta.get(TRACE_ID_KEY)):
            try:
                s, e = parse_date_range(start, end, settings.window_start, settings.window_end)
            except InvalidRange as exc:
                raise reject(tool, str(exc)) from None
            if group_by is not None and technician_id is not None:
                raise reject(tool, "a technician filter cannot be combined with group_by")
            began = time.perf_counter()
            args = (group_by, technician_id) if filtered else (group_by,)
            result = await call_backend(tool, call, s, e, *args)
            log.info(
                "tool call",
                extra={
                    "tool": tool,
                    "start": s.isoformat(),
                    "end": e.isoformat(),
                    "group_by": group_by,
                    "technician_id": technician_id,
                    "duration_ms": round((time.perf_counter() - began) * 1000, 1),
                },
            )
            return result

    @server.tool(name=TOOL_NAME)
    async def get_incidents_by_date_range(
        start: Start,
        end: End,
        ctx: Context,
        group_by: CountGroupByArg = None,
        technician_id: TechnicianArg = None,
    ) -> IncidentSummary:
        """Count incidents reported in a date range, in total and by severity.

        Optionally broken down (top 25 groups, highest count first; the totals cover
        every group), or only incidents attributed to one technician. Returns aggregates
        only: no incident rows and no free-text fields.
        """
        return await run(TOOL_NAME, ctx, start, end, backend.incidents, group_by, technician_id)

    @server.tool(name=INCIDENT_RATE)
    async def get_incident_rate(
        start: Start,
        end: End,
        ctx: Context,
        group_by: GroupByArg = None,
        technician_id: TechnicianArg = None,
    ) -> IncidentRateResult:
        """Incidents per 100 completed requests (data dictionary §6).

        Date rule: incidents whose reported_at is in the range, over requests whose
        completed_at is in the range. By technician, only incidents attributed to that
        technician count (ADR-033), over the jobs they completed. Rates are strings,
        rounded half-up to 4 places; a zero denominator gives a null rate.

        Groups are sorted worst first: highest rate first. The top 25 are kept.
        """
        return await run(
            INCIDENT_RATE, ctx, start, end, backend.incident_rate, group_by, technician_id
        )

    @server.tool(name=SLA_COMPLIANCE)
    async def get_sla_compliance(
        start: Start,
        end: End,
        ctx: Context,
        group_by: GroupByArg = None,
        technician_id: TechnicianArg = None,
    ) -> SlaComplianceResult:
        """Share of dispatched requests completed within their SLA window (§6).

        Date rule: requests whose dispatched_at is in the range. The SLA clock starts at
        dispatched_at; requests never dispatched, or not completed (null sla_met), are
        excluded from the denominator.

        Groups are sorted worst first: lowest rate first. The top 25 are kept.
        """
        return await run(
            SLA_COMPLIANCE, ctx, start, end, backend.sla_compliance, group_by, technician_id
        )

    @server.tool(name=FIRST_TIME_FIX)
    async def get_first_time_fix_rate(
        start: Start,
        end: End,
        ctx: Context,
        group_by: GroupByArg = None,
        technician_id: TechnicianArg = None,
    ) -> FirstTimeFixResult:
        """Share of completed requests with no follow-up visit (§6).

        Date rule: requests whose completed_at is in the range. A child request
        (parent_request_id pointing back) counts against its parent whatever its date,
        unless it was cancelled: a cancelled follow-up means no return visit happened.

        Groups are sorted worst first: lowest rate first. The top 25 are kept.
        """
        return await run(
            FIRST_TIME_FIX, ctx, start, end, backend.first_time_fix_rate, group_by, technician_id
        )

    @server.tool(name=FIND_TECHNICIAN)
    async def find_technician_tool(name: NameArg, ctx: Context) -> TechnicianMatches:
        """Technicians whose display name matches `name`, case-insensitively: every word
        of `name` must be a whole word of the display name (a first name finds everyone
        with it). At most 5 matches (id and display name), and the total match count.
        No wildcards or patterns.
        """
        meta = ctx.request_context.meta or {}
        with bind_trace_id(meta.get(TRACE_ID_KEY)):
            result = await call_backend(FIND_TECHNICIAN, backend.find_technician, name)
            # The count only: the name a user typed is not logged.
            log.info("tool call", extra={"tool": FIND_TECHNICIAN, "matches": result.total_matches})
            return result

    @server.tool(name=REPEAT_DRIVERS)
    async def get_repeat_visit_drivers(
        start: Start, end: End, ctx: Context, by: RepeatByArg = "incident_type"
    ) -> RepeatDriversResult:
        """Repeat-visit rate of jobs completed in the range, by group (ADR-073).

        A repeat visit is a non-cancelled follow-up request, whatever its date; every one
        is recorded through a repeat_visit_required incident on the original job, so
        by=incident_type leaves that type out and compares jobs with each other type
        against jobs without it. A group stands out only if it has at least 20 jobs, a
        higher rate than the rest, and Fisher's exact p < 0.05 after Bonferroni
        correction. Groups are listed worst first, top 25.
        """
        return await run(
            REPEAT_DRIVERS, ctx, start, end, backend.repeat_drivers, by, filtered=False
        )

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
