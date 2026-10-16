"""The degraded-answer alert as code (ADR-112): the config files, the synthetic entry, `plan`.

Offline. The fixture below fails any test that starts a real process or opens a connection, so
none of these can reach gcloud or GCP (the root conftest.py already points gcloud at an empty
config folder).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MONITORING = REPO / "ops" / "monitoring"
CHANNEL = "1234567890"


def _load():
    spec = importlib.util.spec_from_file_location(
        "alert_degraded", REPO / "scripts" / "alert_degraded.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


alert = _load()
ENV = {"PROJECT_ID": "proj-x", "REGION": "region-y"}


@pytest.fixture(autouse=True)
def no_process_no_network(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("a test started a process or opened a connection")

    monkeypatch.setattr(subprocess, "Popen", boom)
    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(urllib.request, "urlopen", boom)


def entry(**overrides):
    return alert.synthetic_entry("proj-x", "region-y", **overrides)


# --------------------------------------------------------------------------- the synthetic entry


def test_the_synthetic_entry_satisfies_every_condition_in_the_metric_file():
    conditions = alert.metric_conditions()
    assert len(conditions) == 3  # resource.type, service_name, msg: nothing loosened
    assert alert.entry_matches(entry(), conditions)


def test_the_synthetic_entry_is_marked_and_its_trace_id_is_prefixed():
    payload = entry()["jsonPayload"]
    assert payload["synthetic_alert_test"] is True
    assert payload["trace_id"].startswith("alerttest-") and len(payload["trace_id"]) > 12


def test_the_write_command_sends_that_entry_and_no_other():
    e = entry()
    argv = alert.write_argv(e, "proj-x")
    assert argv[:3] == ["logging", "write", alert.TEST_LOG]
    assert json.loads(argv[3]) == e["jsonPayload"]
    assert "--payload-type=json" in argv
    assert "--monitored-resource-type=cloud_run_revision" in argv
    [flag] = [a for a in argv if a.startswith("--monitored-resource-labels=")]
    labels = dict(p.split("=", 1) for p in flag.split("=", 1)[1].split(","))
    assert labels == e["resource"]["labels"]


def test_a_payload_with_a_cmd_metacharacter_is_refused():
    e = entry()
    e["jsonPayload"]["trigger"] = "a&b"
    with pytest.raises(ValueError, match="metacharacters"):
        alert.write_argv(e, "proj-x")


def test_the_filter_is_not_loosened_a_wrong_service_or_message_does_not_match():
    conditions = alert.metric_conditions()
    wrong_service = entry()
    wrong_service["resource"]["labels"]["service_name"] = "ops-gateway"
    wrong_msg = entry()
    wrong_msg["jsonPayload"]["msg"] = "ask answered"
    assert not alert.entry_matches(wrong_service, conditions)
    assert not alert.entry_matches(wrong_msg, conditions)


def test_the_metric_file_is_terms_joined_by_and_with_the_two_extractors():
    metric = json.loads((MONITORING / "degraded_metric.json").read_text(encoding="utf-8"))
    assert set(alert.metric_conditions()) == {
        ("resource.type", "cloud_run_revision"),
        ("resource.labels.service_name", "ops-orchestrator"),
        ("jsonPayload.msg", "ask degraded"),
    }
    assert metric["metricDescriptor"]["metricKind"] == "DELTA"
    assert set(metric["labelExtractors"]) == {"trigger", "capability"}
    assert {x["key"] for x in metric["metricDescriptor"]["labels"]} == {"trigger", "capability"}


# --------------------------------------------------------------------------- the policy


def test_the_policy_file_says_what_the_adr_says():
    policy = json.loads((MONITORING / "degraded_policy.json").read_text(encoding="utf-8"))
    [condition] = policy["conditions"]
    threshold = condition["conditionThreshold"]
    assert threshold["comparison"] == "COMPARISON_GT" and threshold["thresholdValue"] == 0
    assert threshold["duration"] == "0s"
    [agg] = threshold["aggregations"]
    assert agg == {
        "alignmentPeriod": "300s",
        "perSeriesAligner": "ALIGN_SUM",
        "crossSeriesReducer": "REDUCE_SUM",
    }
    assert policy["alertStrategy"]["autoClose"] == "1800s"
    assert "trace_id" in policy["documentation"]["content"]
    assert "ADR-088" in policy["documentation"]["content"]


# --------------------------------------------------------------------------- no secrets


def test_no_config_file_holds_an_address_or_a_channel():
    for name in ("degraded_metric.json", "degraded_policy.json"):
        text = (MONITORING / name).read_text(encoding="utf-8")
        assert "@" not in text, name
        assert "notificationChannels" not in text, name  # filled in at apply time only
    policy = alert.load(alert.POLICY_FILE)
    assert "notificationChannels" not in policy


def test_the_channel_is_added_only_in_the_body_built_at_apply_time():
    body = alert.policy_body(alert.channel_name("proj-x", CHANNEL))
    assert body["notificationChannels"] == [f"projects/proj-x/notificationChannels/{CHANNEL}"]
    assert alert.channel_name("p", "projects/p/notificationChannels/9") == (
        "projects/p/notificationChannels/9"
    )


# --------------------------------------------------------------------------- plan


def test_plan_makes_no_process_call_and_no_connection(capsys):
    # The autouse fixture raises on any Popen, run or urlopen.
    assert alert.main(["plan"], env=ENV) == 0
    out = capsys.readouterr().out
    assert "gcloud logging metrics create orchestrator_degraded_answers" in out
    assert "gcloud logging write" in out
    assert "proj-x" in out and "region-y" in out


def test_plan_is_the_default_and_runs_with_nothing_configured(capsys):
    assert alert.main([], env={}) == 0
    out = capsys.readouterr().out
    assert "<PROJECT_ID>" in out and "<CHANNEL_ID>" in out and "unset" in out


def test_parsing_arguments_starts_nothing():
    assert alert.parse_args(["apply", "--channel", "1"]).command == "apply"
    assert alert.parse_args(["test"]).command == "test"
    with pytest.raises(SystemExit):
        alert.parse_args(["apply"])  # --channel is required


def test_apply_and_test_refuse_without_configuration(capsys):
    assert alert.main(["apply", "--channel", "1"], env={}) == 1
    assert alert.main(["test"], env={}) == 1
    assert "unset PROJECT_ID, REGION" in capsys.readouterr().out


# --------------------------------------------------------------------------- apply and test logic


def test_subset_diff_ignores_server_additions_and_proto_defaults():
    expected = {"a": 1, "b": {"c": 0, "d": "x"}, "e": [{"f": 2}]}
    actual = {"a": 1, "b": {"d": "x", "name": "n"}, "e": [{"f": 2, "g": 3}], "extra": 1}
    assert alert.subset_diff(expected, actual) == []
    assert alert.subset_diff({"a": 1}, {"a": 2}) == ["a: expected 1, got 2"]
    assert alert.subset_diff({"a": "x"}, {}) == ["a: missing"]


class FakeGcloud:
    """Stands in for the Gcloud wrapper: records calls, answers the two listings."""

    def __init__(self):
        self.calls: list[tuple] = []
        self.timeout = 1.0
        self._run = lambda argv, timeout: "SECRET-TOKEN-VALUE"

    def __call__(self, *args, label=None):
        self.calls.append(args)
        return ""

    def json(self, *args, label=None):
        self.calls.append(args)
        return [{"name": "projects/proj-x/alertPolicies/1"}]


def test_the_test_polls_until_both_stages_fire(capsys):
    gc = FakeGcloud()
    clock = {"t": 1000.0}
    answers = iter(
        [
            ({"timeSeries": []}, {"alerts": []}),
            ({"timeSeries": [{"points": [{"value": {"int64Value": "1"}}]}]}, {"alerts": []}),
            (
                {"timeSeries": [{"points": [{"value": {"int64Value": "1"}}]}]},
                {"alerts": [{"state": "OPEN"}]},
            ),
        ]
    )
    pending: list[dict] = []

    def get(token, path, params):
        if not pending:
            pending.extend(next(answers))
        return pending.pop(0)

    def sleep(seconds):
        clock["t"] += seconds

    cfg = alert.Config(ENV)
    rc = alert.run_test(cfg, gc, get=get, now=lambda: clock["t"], sleep=sleep)
    out = capsys.readouterr().out
    assert rc == 0 and "PASS" in out
    assert gc.calls[0][:2] == ("logging", "write")
    assert "SECRET-TOKEN-VALUE" not in out


def test_the_test_reports_the_stage_that_did_not_fire(capsys):
    gc = FakeGcloud()
    clock = {"t": 0.0}

    def get(token, path, params):
        return {"timeSeries": [], "alerts": []}

    def sleep(seconds):
        clock["t"] += seconds

    rc = alert.run_test(
        alert.Config(ENV), gc, get=get, now=lambda: clock["t"], sleep=sleep, poll_for=90
    )
    out = capsys.readouterr().out
    assert rc == 1 and "the metric never counted the entry" in out
    assert "alerttest-" in out  # the trace id is printed so the entry can be found
