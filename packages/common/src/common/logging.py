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
import hashlib
import json
import logging
import re
import sys
import traceback
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

#: The key the trace id travels under, in both A2A message metadata and MCP `_meta`.
TRACE_ID_KEY = "trace_id"

#: The HTTP header it also travels under, so a server's own access line can carry it (ADR-108).
TRACE_ID_HEADER = "X-Trace-Id"

# The width `new_trace_id()` mints. Nothing else is accepted from a caller: a client-supplied
# value must not be able to put its own text, or a newline, into a log line.
_VALID_TRACE_ID = re.compile(r"[0-9a-f]{32}")

_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)

# Attributes every LogRecord has; anything else on a record came from `extra=`.
_RESERVED = frozenset(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {
    "message",
    "asctime",
    "taskName",
}


_REDACTED = "[REDACTED]"
# Secrets that third-party libraries log on their own at DEBUG: the A2A server prints the
# whole call context, request headers included, and a database error can quote the URL.
_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # `Bearer <token>`, however it is quoted.
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]+"), r"\1 " + _REDACTED),
    # An `authorization` header or field of any scheme: `'authorization': 'Basic xyz'`
    # (also inside a JSON-escaped string, hence the optional backslashes).
    (
        re.compile(r"""(?i)(authorization\\*['"]?\s*[:=]\s*\\*['"]?)[^'"\\,}]+"""),
        r"\1" + _REDACTED,
    ),
    # The password in `scheme://user:password@host`.
    (re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://[^\s/:@]*:)[^\s/@]+(@)"), r"\1" + _REDACTED + r"\2"),
)


def redact_secrets(text: str) -> str:
    """Mask bearer tokens, authorization headers and URL passwords in a log line."""
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def text_fields(prefix: str, text: str) -> dict[str, object]:
    """What a log line may say about text that can hold what the user typed: its length and
    a short SHA-256 prefix (ADR-108). Two equal texts show as equal; the text is not logged."""
    digest = hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:12]
    return {f"{prefix}_chars": len(text), f"{prefix}_sha": digest}


class ToolErrorTextFilter(logging.Filter):
    """The MCP SDK logs a tool's error message verbatim at INFO (`Tool %r failed: %r`). That
    message can carry values parsed from the question (L-98), so the line is rewritten to a
    code, the message's length and a short hash (ADR-108). The client still gets the message."""

    SDK_MESSAGE = "Tool %r failed: %r"

    def filter(self, record: logging.LogRecord) -> bool:
        if (
            record.msg == self.SDK_MESSAGE
            and isinstance(record.args, tuple)
            and len(record.args) == 2
        ):
            tool, message = record.args
            record.msg, record.args = "tool failed", None
            record.__dict__.update({"tool": tool, "code": "tool_error"})
            record.__dict__.update(text_fields("error", str(message)))
        return True


def safe_exception(exc_info: tuple) -> str:
    """An exception as class names and `file:line in function` frames, never its message.

    The message can carry text the user typed (a technician's name in a failed lookup, a
    phrase in a validation error), so it is dropped whatever it says (ADR-108, L-60). The
    chain (`__cause__`, `__context__`) and an exception group's members are named by class.
    """
    _, value, tb = exc_info
    lines = ["Traceback (exception messages omitted):"]
    for frame in traceback.extract_tb(tb):
        lines.append(f"  {frame.filename}:{frame.lineno} in {frame.name}")
    names: list[str] = []
    seen: set[int] = set()

    def walk(exc: BaseException | None) -> None:
        if exc is None or id(exc) in seen:
            return
        seen.add(id(exc))
        names.append(type(exc).__name__)
        for member in getattr(exc, "exceptions", ()):  # ExceptionGroup
            walk(member)
        walk(exc.__cause__)
        if not exc.__suppress_context__:
            walk(exc.__context__)

    walk(value)
    lines.append("  raised: " + " <- ".join(names) if names else "  raised: unknown")
    return "\n".join(lines)


def new_trace_id() -> str:
    """A fresh trace id: 32 hex characters, the W3C trace-context width."""
    return uuid.uuid4().hex


def valid_trace_id(value: object) -> str | None:
    """`value` if it is a trace id this system would mint (32 lowercase hex), else None."""
    if isinstance(value, str) and _VALID_TRACE_ID.fullmatch(value):
        return value
    return None


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
            line["exc"] = safe_exception(record.exc_info)
        # Last step, over the finished line, so no field or library message escapes it.
        return redact_secrets(json.dumps(line, default=str))


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
    # The A2A SDK logs the whole server call context, request headers included, at DEBUG.
    # Hold its loggers at INFO or above whatever LOG_LEVEL says; redaction stays as a second
    # layer.
    logging.getLogger("a2a").setLevel(max(logging.INFO, root.level))
    # The MCP SDK can log request payloads (tool arguments, so what the user typed) at DEBUG.
    logging.getLogger("mcp").setLevel(max(logging.INFO, root.level))
    sdk = logging.getLogger("mcp.server.mcpserver.server")
    if not any(isinstance(f, ToolErrorTextFilter) for f in sdk.filters):
        sdk.addFilter(ToolErrorTextFilter())
