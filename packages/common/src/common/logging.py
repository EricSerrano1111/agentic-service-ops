"""JSON-line logging with a trace id correlated across service hops.

The orchestrator mints one trace id per request. It travels in the A2A message metadata
to the specialist and in the MCP request `_meta` to the MCP server, under the same key,
`TRACE_ID_KEY`. Each service binds it to a context variable on arrival; every log line
written while handling that request then carries it, including lines from the SDKs,
because the formatter is installed on the root logger.

A log line is one JSON object: `ts`, `level`, `service`, `logger`, `trace_id`, `msg`,
plus any `extra={...}` fields passed to the logging call.
"""

from __future__ import annotations

import contextvars
import datetime as dt
import json
import logging
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

#: The key the trace id travels under, in both A2A message metadata and MCP `_meta`.
TRACE_ID_KEY = "trace_id"

_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)

# Attributes every LogRecord has; anything else on a record came from `extra=`.
_RESERVED = frozenset(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {
    "message",
    "asctime",
    "taskName",
}


def new_trace_id() -> str:
    """A fresh trace id: 32 hex characters, the W3C trace-context width."""
    return uuid.uuid4().hex


def current_trace_id() -> str | None:
    return _trace_id.get()


@contextmanager
def bind_trace_id(trace_id: str | None) -> Iterator[None]:
    """Attach `trace_id` to every log line written inside the block."""
    token = _trace_id.set(trace_id)
    try:
        yield
    finally:
        _trace_id.reset(token)


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        line = {
            "ts": dt.datetime.fromtimestamp(record.created, dt.UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "service": self.service,
            "logger": record.name,
            "trace_id": _trace_id.get(),
            "msg": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in _RESERVED and key not in line:
                line[key] = value
        if record.exc_info:
            line["exc"] = self.formatException(record.exc_info)
        return json.dumps(line, default=str)


def configure_logging(service: str, level: str = "INFO") -> None:
    """Route every logger, SDK loggers included, to stdout as JSON lines.

    Replaces any root handlers already installed. The MCP SDK installs its own handler
    when an `MCPServer` is constructed, so call this after building the server.
    Uvicorn must be started with `log_config=None` so its loggers propagate here.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service))
    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)
    # Per-request HTTP client lines, and the A2A resolver dumping the whole Agent Card on
    # every fetch, add noise without adding a trace-correlated fact.
    for noisy in ("httpx", "httpx2", "httpcore", "a2a.client.card_resolver"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
