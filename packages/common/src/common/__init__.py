"""Shared runtime helpers for every service: JSON-line logging and trace-id propagation.

Deliberately dependency-free, so it costs nothing in any container that installs it.
"""

from __future__ import annotations

from .logging import (
    TRACE_ID_KEY,
    JsonFormatter,
    bind_trace_id,
    configure_logging,
    current_trace_id,
    new_trace_id,
)

__all__ = [
    "TRACE_ID_KEY",
    "JsonFormatter",
    "bind_trace_id",
    "configure_logging",
    "current_trace_id",
    "new_trace_id",
]
