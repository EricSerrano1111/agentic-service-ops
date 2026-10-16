"""The degraded log line and the alert's metric filter cannot drift apart (ADR-112).

The orchestrator's `"ask degraded"` line is produced through the real handler and the real
`JsonFormatter`, then evaluated against the field conditions parsed from
`ops/monitoring/degraded_metric.json`. A rename of the message, or a move of a field, fails here
instead of silently blinding the alert. Offline: no network, no gcloud.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from llm import LLMUnavailable
from test_orchestrator import FakeLLM, decision
from test_resilience import Hop, ask, captured_logs, client_for

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "alert_degraded.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("alert_degraded_for_line_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


alert = _load_script()


def as_cloud_run_entry(line: dict) -> dict:
    """What Cloud Logging holds for a line the orchestrator wrote: the resource it ran on, and the
    JSON line as `jsonPayload`."""
    return {
        "resource": {
            "type": "cloud_run_revision",
            "labels": {"service_name": alert.SERVICE},
        },
        "jsonPayload": line,
    }


def test_the_real_degraded_line_matches_the_metric_filter(monkeypatch):
    llm = FakeLLM(decision("reporting"), error=LLMUnavailable("503 from google"))
    with captured_logs() as lines:
        body = ask(client_for(monkeypatch, llm, Hop())).json()
    assert body["outcome"] == "degraded"
    degraded = [x for x in lines() if x["msg"] == "ask degraded"]
    assert len(degraded) == 1  # one line per degraded request
    [line] = degraded
    conditions = alert.metric_conditions()
    assert alert.entry_matches(as_cloud_run_entry(line), conditions)
    # The labels the metric extracts are on the line, and the trace id is there to search by.
    assert line["trigger"] == "dependency" and line["capability"] == "routing"
    assert line["trace_id"] == body["trace_id"]


def test_an_answered_line_does_not_match_the_metric_filter(monkeypatch):
    with captured_logs() as lines:
        body = ask(client_for(monkeypatch, FakeLLM(decision("reporting")), Hop())).json()
    assert body["outcome"] == "answered"
    answered = [x for x in lines() if x["msg"] == "ask answered"]
    assert answered
    conditions = alert.metric_conditions()
    assert not any(alert.entry_matches(as_cloud_run_entry(x), conditions) for x in lines())


def test_the_gateways_line_is_not_counted():
    """The gateway logs `ask answered` with outcome=degraded; the filter is scoped to the
    orchestrator service and to the message `ask degraded`, so it cannot double count."""
    gateway_line = {"msg": "ask answered", "outcome": "degraded", "service": "api_gateway"}
    entry = {
        "resource": {"type": "cloud_run_revision", "labels": {"service_name": "ops-gateway"}},
        "jsonPayload": gateway_line,
    }
    assert not alert.entry_matches(entry, alert.metric_conditions())
