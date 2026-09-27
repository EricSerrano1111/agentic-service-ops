"""MCP client for the incidents server: streamable HTTP, protocol pinned to 2026-07-28."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx2
from common import TRACE_ID_KEY
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from pydantic import BaseModel

#: The spec revision this system targets (R-12, ADR-047). Pinning it skips the
#: `server/discover` probe and fails loudly if the server cannot speak it.
MCP_PROTOCOL_VERSION = "2026-07-28"


class McpToolError(RuntimeError):
    """The tool ran and reported an error (bad input, or its query failed)."""


async def call_tool[R: BaseModel](
    url: str,
    tool: str,
    arguments: dict[str, Any],
    result_model: type[R],
    *,
    trace_id: str | None,
    timeout_s: float,
) -> R:
    """Call one tool once and validate its structured result against `result_model`
    (architecture §11). Raises `TimeoutError` past `timeout_s`, connect included."""
    async with asyncio.timeout(timeout_s):
        async with (
            httpx2.AsyncClient(timeout=timeout_s) as http,
            Client(
                streamable_http_client(url, http_client=http),
                mode=MCP_PROTOCOL_VERSION,
                cache=None,  # figures must be current; never served from a client cache
            ) as client,
        ):
            result = await client.call_tool(
                tool,
                arguments,
                read_timeout_seconds=timeout_s,
                meta={TRACE_ID_KEY: trace_id} if trace_id else None,
            )
    if result.is_error:
        detail = " ".join(getattr(block, "text", "") for block in result.content).strip()
        raise McpToolError(detail or "tool returned an error")
    return result_model.model_validate(result.structured_content)
