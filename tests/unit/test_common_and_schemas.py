"""Offline tests for the shared packages: JSON-line logging with trace ids, and the
IncidentSummary contract."""

from __future__ import annotations

import datetime as dt
import io
import json
import logging

import pytest
from common import JsonFormatter, bind_trace_id, configure_logging, current_trace_id, new_trace_id
from db_models import Severity, values
from pydantic import ValidationError
from schemas import IncidentSummary, SeverityCounts

# --------------------------------------------------------------------------- logging


def _emit(logger_name: str, msg: str, **extra) -> dict:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter("svc"))
    logger = logging.getLogger(logger_name)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        logger.info(msg, extra=extra)
    finally:
        logger.removeHandler(handler)
    return json.loads(stream.getvalue())


def test_log_line_is_json_with_trace_id_and_extras():
    with bind_trace_id("abc123"):
        line = _emit("t.one", "hello", task_id="t-1")
    assert line["trace_id"] == "abc123"
    assert line["service"] == "svc"
    assert line["msg"] == "hello"
    assert line["task_id"] == "t-1"
    assert line["level"] == "INFO"


def test_trace_id_unbinds_after_block():
    with bind_trace_id("abc"):
        assert current_trace_id() == "abc"
    assert current_trace_id() is None
    assert _emit("t.two", "x")["trace_id"] is None


def test_new_trace_id_is_32_hex():
    trace_id = new_trace_id()
    assert len(trace_id) == 32
    int(trace_id, 16)


def test_configure_logging_replaces_root_handlers():
    root = logging.getLogger()
    saved = list(root.handlers), root.level
    try:
        root.addHandler(logging.NullHandler())
        configure_logging("svc")
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, JsonFormatter)
    finally:
        root.handlers[:] = saved[0]
        root.setLevel(saved[1])


# --------------------------------------------------------------------------- schemas


def _summary(**overrides) -> dict:
    data = {
        "start": "2024-01-01",
        "end": "2024-01-31",
        "incident_count": 6,
        "by_severity": {"low": 3, "medium": 2, "high": 1},
    }
    return data | overrides


def test_severity_counts_match_the_vocabulary():
    """`schemas` does not import `db_models` (ADR-026); this keeps them in step."""
    assert tuple(SeverityCounts.model_fields) == values(Severity)


def test_summary_round_trips_as_json():
    summary = IncidentSummary.model_validate(_summary())
    assert summary.start == dt.date(2024, 1, 1)
    assert IncidentSummary.model_validate_json(summary.model_dump_json()) == summary


@pytest.mark.parametrize(
    "bad",
    [
        _summary(incident_count=7),  # severities do not sum to the total
        _summary(start="2024-02-01"),  # start after end
        _summary(by_severity={"low": -1, "medium": 6, "high": 1}),
        _summary(notes="free text"),  # no extra fields: no free text can ride along
    ],
)
def test_summary_rejects_inconsistent_data(bad):
    with pytest.raises(ValidationError):
        IncidentSummary.model_validate(bad)
