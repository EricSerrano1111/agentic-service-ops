"""Shared runtime helpers: JSON-line logging, trace-id propagation, and the database
connect timeout the host-side scripts use.

Deliberately dependency-free, so it costs nothing in any container that installs it.
"""

from __future__ import annotations

from .breaker import COOLDOWN_S, FAILURE_THRESHOLD, BreakerOpen, CircuitBreaker
from .cost import (
    COST_KEY,
    DEFAULT_MAX_COST_PER_RUN_USD,
    RequestCost,
    add_cost,
    current_cost_usd,
    max_cost_per_run_usd,
    parse_cost_usd,
    track_request_cost,
)
from .db import (
    CLOUD_SQL_INSTANCE_VAR,
    CONNECT_TIMEOUT_VAR,
    DEFAULT_CONNECT_TIMEOUT_S,
    connect_timeout_s,
    database_host,
)
from .deadline import (
    DEADLINE_KEY,
    REQUEST_BUDGET_S,
    RESERVE_S,
    Deadline,
    DeadlineExceeded,
    bind_deadline,
    clamp_to_deadline,
    current_deadline,
)
from .guidance import (
    GUIDANCE_KEY,
    MAX_GUIDANCE_CHARS,
    clean_guidance,
    with_reviewer_note,
)
from .logging import (
    TRACE_ID_KEY,
    JsonFormatter,
    bind_trace_id,
    configure_logging,
    current_trace_id,
    new_trace_id,
    redact_secrets,
)

__all__ = [
    "BreakerOpen",
    "CircuitBreaker",
    "COOLDOWN_S",
    "COST_KEY",
    "DEADLINE_KEY",
    "DEFAULT_MAX_COST_PER_RUN_USD",
    "Deadline",
    "DeadlineExceeded",
    "FAILURE_THRESHOLD",
    "REQUEST_BUDGET_S",
    "RESERVE_S",
    "RequestCost",
    "add_cost",
    "bind_deadline",
    "clamp_to_deadline",
    "current_cost_usd",
    "current_deadline",
    "max_cost_per_run_usd",
    "parse_cost_usd",
    "track_request_cost",
    "GUIDANCE_KEY",
    "MAX_GUIDANCE_CHARS",
    "clean_guidance",
    "with_reviewer_note",
    "CLOUD_SQL_INSTANCE_VAR",
    "database_host",
    "CONNECT_TIMEOUT_VAR",
    "DEFAULT_CONNECT_TIMEOUT_S",
    "connect_timeout_s",
    "TRACE_ID_KEY",
    "JsonFormatter",
    "bind_trace_id",
    "configure_logging",
    "current_trace_id",
    "new_trace_id",
    "redact_secrets",
]
