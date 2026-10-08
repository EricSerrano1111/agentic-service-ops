"""The volume MCP server: served-only forecasts and weekly history, over streamable HTTP.

No generic query tool (ADR-023) and no tool that writes. Every input is validated against
types and vocabularies before anything runs. Streamable HTTP in stateless mode, as the
other MCP servers.

Tools (ADR-072):
- `get_volume_forecast(slice, horizon_weeks)`: weekly `volume_v2` forecasts for the next
  1-26 weeks after 2026-08-30. Numbers appear only for weeks in served slice-bands
  (ADR-071); every band carries its served flag and shown error.
- `get_order_volume_history(slice, weeks)`: actual weekly request counts for the most
  recent 1-52 complete weeks up to 2026-08-30.
"""

from __future__ import annotations

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
    FORECAST_SLICES,
    MAX_HISTORY_WEEKS,
    MAX_HORIZON_WEEKS,
    ForecastSlice,
    VolumeForecast,
    VolumeHistory,
)
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse

from .artifact import Artifact
from .config import Settings

log = logging.getLogger("mcp_volume")

FORECAST = "get_volume_forecast"
HISTORY = "get_order_volume_history"

SliceArg = Annotated[
    ForecastSlice,
    Field(
        description="total, or a service type: install, repair, maintenance, inspection, upgrade."
    ),
]


class InvalidInput(ValueError):
    """A caller error: the message is safe to return to the client verbatim. `argument` and
    `kind` say which argument was rejected and why, with no value: they are what the log
    records, since a rejected value may be text from a user's question."""

    def __init__(self, message: str, *, argument: str, kind: str) -> None:
        super().__init__(message)
        self.argument = argument
        self.kind = kind


def check_int(name: str, value: Any, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise InvalidInput(
            f"{name} must be an integer from {low} to {high}",
            argument=name,
            kind="out_of_range",
        )
    return value


def check_slice(value: Any) -> str:
    if value not in FORECAST_SLICES:
        raise InvalidInput(
            f"slice must be one of {', '.join(FORECAST_SLICES)}",
            argument="slice",
            kind="not_in_vocabulary",
        )
    return value


@dataclass(frozen=True)
class Backend:
    """What the tools run on. Offline tests pass a hand-built artifact and a fake history."""

    artifact: Artifact
    history: Callable[[str, int], VolumeHistory]
    ready: Callable[[], None]


def create_server(settings: Settings, backend: Backend) -> MCPServer:
    server = MCPServer(
        "mcp_volume",
        instructions="Weekly request-volume forecasts (volume_v2) and recent weekly history. "
        "Forecast numbers are returned only for slice-bands with an adequate track record.",
        version="0.1.0",
    )

    async def run(tool: str, ctx: Context, validate: Callable, call: Callable) -> Any:
        meta = ctx.request_context.meta or {}
        with bind_trace_id(meta.get(TRACE_ID_KEY)):
            try:
                args = validate()
            except InvalidInput as exc:
                log.info(
                    "tool rejected input",
                    extra={"tool": tool, "argument": exc.argument, "error_type": exc.kind},
                )
                raise ToolError(str(exc)) from None
            began = time.perf_counter()
            try:
                result = await anyio.to_thread.run_sync(call, *args)
            except Exception:
                log.exception("tool failed", extra={"tool": tool})
                raise ToolError("volume query failed") from None
            log.info(
                "tool call",
                extra={
                    "tool": tool,
                    "slice": args[0],
                    "n": args[1],
                    "duration_ms": round((time.perf_counter() - began) * 1000, 1),
                },
            )
            return result

    @server.tool(name=FORECAST)
    async def get_volume_forecast(
        slice: SliceArg,
        horizon_weeks: Annotated[int, Field(strict=True, description="Weeks ahead, 1 to 26.")],
        ctx: Context,
    ) -> VolumeForecast:
        """Weekly request-volume forecasts for the next `horizon_weeks` weeks after the data
        ends (2026-08-30): the median and 80%/95% ranges per week.

        Numbers are returned only for horizon bands (1-4, 5-13, 14-26 weeks) whose forecasts
        were accurate enough on held-out data; other weeks carry `served: false` and no
        numbers. Every band carries `shown_error`, its average error on held-out weeks (%),
        which must be shown with any forecast. `year_end_weeks` lists Christmas and New Year
        weeks, whose holiday adjustment hasn't been validated on held-out data.
        """

        def validate():
            return check_slice(slice), check_int(
                "horizon_weeks", horizon_weeks, 1, MAX_HORIZON_WEEKS
            )

        return await run(FORECAST, ctx, validate, backend.artifact.forecast)

    @server.tool(name=HISTORY)
    async def get_order_volume_history(
        slice: SliceArg,
        weeks: Annotated[int, Field(strict=True, description="How many recent weeks, 1 to 52.")],
        ctx: Context,
    ) -> VolumeHistory:
        """Actual weekly request counts (all statuses, by scheduled date) for the most recent
        `weeks` complete weeks up to 2026-08-30, oldest first."""

        def validate():
            return check_slice(slice), check_int("weeks", weeks, 1, MAX_HISTORY_WEEKS)

        return await run(HISTORY, ctx, validate, backend.history)

    @server.custom_route("/healthz", methods=["GET"])
    @server.custom_route("/readyz", methods=["GET"])
    async def healthz(request: Request) -> JSONResponse:
        """Ready: the artifact hashes verified at start-up and the database answers.

        `/readyz` is the same check under the name the Cloud Run probes use.
        """
        try:
            await anyio.to_thread.run_sync(backend.ready)
        except Exception:
            log.warning("readiness check failed: database unreachable")
            return JSONResponse({"status": "unavailable", "service": "mcp_volume"}, status_code=503)
        return JSONResponse(
            {
                "status": "ok",
                "service": "mcp_volume",
                "model_version": backend.artifact.model_version,
            }
        )

    return server


def create_app(settings: Settings, backend: Backend) -> Starlette:
    server = create_server(settings, backend)
    return server.streamable_http_app(
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=list(settings.allowed_hosts),
            allowed_origins=[],
        ),
    )
