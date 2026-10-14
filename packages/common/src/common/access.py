"""One access line per HTTP request, carrying the request's trace id (ADR-108).

A pure ASGI middleware, so it needs nothing beyond the standard library and works under
FastAPI and under the MCP SDK's Starlette app alike. It replaces Uvicorn's own access log
(turned off in each `__main__`), which was written outside the request's context and so
could never carry the id.

The id comes from the `X-Trace-Id` request header when it is a valid one (32 lowercase hex);
anything else is ignored. With `mint=True` (the gateway and the orchestrator) a request with
no valid id is given a fresh one; without it (an agent, QA, an MCP server) the line simply
has none until the executor binds the id from the A2A message metadata. The id is returned
as a response header when there is one.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from .logging import TRACE_ID_HEADER, bind_trace_id, new_trace_id, valid_trace_id

log = logging.getLogger("access")

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]

#: Probes fire every few seconds; their lines are DEBUG so they do not bury real requests.
PROBE_PATHS = frozenset({"/healthz", "/readyz", "/health"})

_HEADER = TRACE_ID_HEADER.lower().encode("ascii")


class TraceAccessLog:
    def __init__(self, app: Callable[..., Awaitable[None]], *, mint: bool = False) -> None:
        self.app = app
        self.mint = mint

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = None
        for name, value in scope.get("headers", ()):
            if name == _HEADER:
                incoming = valid_trace_id(value.decode("latin-1"))
                break
        trace_id = incoming or (new_trace_id() if self.mint else None)
        status = 500  # what a request that raised before responding will have got
        began = time.perf_counter()

        async def send_with_id(message: MutableMapping[str, Any]) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                if trace_id is not None:
                    headers = [
                        (k, v) for k, v in message.get("headers", ()) if k.lower() != _HEADER
                    ]
                    headers.append((_HEADER, trace_id.encode("ascii")))
                    message = {**message, "headers": headers}
            await send(message)

        with bind_trace_id(trace_id):
            try:
                await self.app(scope, receive, send_with_id)
            finally:
                path = scope.get("path", "")
                log.log(
                    logging.DEBUG if path in PROBE_PATHS else logging.INFO,
                    "request",
                    extra={
                        "method": scope.get("method"),
                        "path": path,  # never the query string
                        "status": status,
                        "duration_ms": round((time.perf_counter() - began) * 1000, 1),
                    },
                )
