"""Shared runtime helpers: JSON-line logging, trace-id propagation, and the database
connect timeout the host-side scripts use.

Deliberately dependency-free, so it costs nothing in any container that installs it.
"""

from __future__ import annotations

from .db import CONNECT_TIMEOUT_VAR, DEFAULT_CONNECT_TIMEOUT_S, connect_timeout_s
from .logging import (
    TRACE_ID_KEY,
    JsonFormatter,
    bind_trace_id,
    configure_logging,
    current_trace_id,
    new_trace_id,
)

__all__ = [
    "CONNECT_TIMEOUT_VAR",
    "DEFAULT_CONNECT_TIMEOUT_S",
    "connect_timeout_s",
    "TRACE_ID_KEY",
    "JsonFormatter",
    "bind_trace_id",
    "configure_logging",
    "current_trace_id",
    "new_trace_id",
]
