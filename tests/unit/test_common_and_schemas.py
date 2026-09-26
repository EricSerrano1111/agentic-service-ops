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


# --------------------------------------------------------------------------- metric results


def test_rate_rounds_half_up_at_the_boundary():
    from schemas import rate_string

    # 1/32 = 0.03125: the fifth place is exactly 5. Half-up gives 0.0313; banker's
    # rounding (Python's round, Decimal's default) would give 0.0312.
    assert rate_string(1, 32) == "0.0313"
    assert round(1 / 32, 4) == 0.0312  # the trap this avoids
    assert rate_string(3, 32) == "0.0938"  # 0.09375 -> up
    assert rate_string(2067, 18063, scale=100) == "11.4433"  # per-100 incident rate


def test_zero_denominator_gives_a_null_rate():
    from schemas import IncidentRateResult, rate_string

    assert rate_string(5, 0) is None
    result = IncidentRateResult(
        start=dt.date(2024, 1, 1), end=dt.date(2024, 1, 1), numerator=5, denominator=0
    )
    assert result.rate is None


def test_rate_is_a_4_place_string_not_a_float():
    from schemas import SlaComplianceResult

    base = dict(start="2024-01-01", end="2024-01-31", numerator=1, denominator=2)
    assert SlaComplianceResult(**base, rate="0.5000").rate == "0.5000"
    for bad in (0.5, "0.5", "0.50000"):
        with pytest.raises(ValidationError):
            SlaComplianceResult(**base, rate=bad)


def test_truncated_flag_must_match_the_group_count():
    from schemas import MAX_GROUPS, FirstTimeFixResult, GroupRate

    groups = [GroupRate(group=f"g{i}", numerator=1, denominator=2, rate="0.5000") for i in range(3)]
    base = dict(start="2024-01-01", end="2024-01-31", group_by="region", numerator=3, denominator=6)
    assert FirstTimeFixResult(**base, groups=groups, group_count=3).truncated is False
    FirstTimeFixResult(**base, groups=groups, group_count=40, truncated=True)
    with pytest.raises(ValidationError, match="truncated"):
        FirstTimeFixResult(**base, groups=groups, group_count=40, truncated=False)
    with pytest.raises(ValidationError, match="groups"):
        FirstTimeFixResult(**{**base, "group_by": None}, groups=groups, group_count=3)
    assert MAX_GROUPS == 25
