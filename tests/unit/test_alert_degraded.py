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
    """Stands in for the Gcloud wrapper: records calls, answers the policy listing and the
    read-back of whatever was written. `stored`: "same", "missing" or "different"."""

    def __init__(self, stored="same"):
        self.calls: list[tuple] = []
        self.timeout = 1.0
        self._run = lambda argv, timeout: "SECRET-TOKEN-VALUE"
        self.stored = stored
        self.written: dict | None = None
        self.labels: dict = {}

    def __call__(self, *args, label=None):
        self.calls.append(args)
        if args[:2] == ("logging", "write"):
            self.written = json.loads(args[3])
            flag = next(a for a in args if a.startswith("--monitored-resource-labels="))
            self.labels = dict(p.split("=", 1) for p in flag.split("=", 1)[1].split(","))
        return ""

    def json(self, *args, label=None):
        self.calls.append(args)
        if args[:2] == ("logging", "read"):
            if self.stored == "missing":
                return []
            payload = dict(self.written)
            if self.stored == "different":
                payload["capability"] = "forecast"
            resource = {"type": "cloud_run_revision", "labels": self.labels}
            return [{"jsonPayload": payload, "resource": resource}]
        return [{"name": "projects/proj-x/alertPolicies/1"}]


SERIES_1 = {"timeSeries": [{"points": [{"value": {"int64Value": "1"}}]}]}


def run(gc, get, *, poll_for=1000, clock=None):
    clock = clock if clock is not None else {"t": 1000.0}

    def sleep(seconds):
        clock["t"] += seconds

    return alert.run_test(
        alert.Config(ENV), gc, get=get, now=lambda: clock["t"], sleep=sleep, poll_for=poll_for
    )


def test_the_test_polls_until_both_stages_fire(capsys):
    gc = FakeGcloud()
    answers = iter(
        [
            ({"timeSeries": []}, {"alerts": []}),
            (SERIES_1, {"alerts": []}),
            (SERIES_1, {"alerts": [{"state": "OPEN"}]}),
        ]
    )
    pending: list[dict] = []

    def get(token, path, params):
        if not pending:
            pending.extend(next(answers))
        return pending.pop(0)

    assert run(gc, get) == 0
    out = capsys.readouterr().out
    assert "PASS  the metric counted the entry and the policy opened an incident" in out
    assert gc.calls[0][:2] == ("logging", "write")
    assert gc.calls[1][:2] == ("logging", "read")  # read back before anything is waited for
    assert "SECRET-TOKEN-VALUE" not in out


def test_the_test_reports_the_stage_that_did_not_fire(capsys):
    def get(token, path, params):
        return {"timeSeries": [], "alerts": []}

    assert run(FakeGcloud(), get, poll_for=90) == 1
    out = capsys.readouterr().out
    assert "the metric never counted the entry" in out
    assert "alerttest-" in out  # the trace id is printed so the entry can be found


def test_an_entry_that_is_not_found_on_read_back_stops_the_test(capsys):
    calls = []

    def get(token, path, params):
        calls.append(path)
        return {}

    assert run(FakeGcloud("missing"), get) == 1
    out = capsys.readouterr().out
    assert "was not found on read-back" in out
    assert calls == []  # no polling of the metric or the alerts


def test_the_read_back_is_bounded_and_waits_between_tries():
    gc = FakeGcloud("missing")
    gc.written = {}
    sleeps: list[float] = []
    assert alert.readback(gc, entry(), "proj-x", sleeps.append) is None
    assert len([c for c in gc.calls if c[:2] == ("logging", "read")]) == alert.READBACK_TRIES
    assert len(sleeps) == alert.READBACK_TRIES - 1


def test_an_entry_whose_payload_differs_on_read_back_stops_the_test(capsys):
    calls = []

    def get(token, path, params):
        calls.append(path)
        return {}

    assert run(FakeGcloud("different"), get) == 1
    out = capsys.readouterr().out
    assert "differs from what was written" in out and "jsonPayload.capability" in out
    assert calls == []


def test_the_read_back_filter_is_by_trace_id_and_has_no_cmd_metacharacter():
    e = entry()
    argv = alert.readback_argv(e, "proj-x")
    assert e["jsonPayload"]["trace_id"] in argv[2]
    assert "--limit=1" in argv and "--freshness=10m" in argv
    assert not alert.CMD_METACHARACTERS & set("".join(argv))


@pytest.mark.parametrize("code", [403, 404])
def test_an_alerts_endpoint_403_or_404_leaves_the_incident_stage_unverified(capsys, code):
    def get(token, path, params):
        if path.endswith("/alerts"):
            raise alert.ApiHttpError(path, code)
        return SERIES_1

    assert run(FakeGcloud(), get) == 0  # not a failure
    out = capsys.readouterr().out
    assert f"incident stage: unverified (alerts endpoint gave HTTP {code})" in out
    assert "UNVERIFIED  incident stage" in out and "check the console" in out
    assert "PASS  the metric counted the entry" in out


def test_an_unverified_incident_stage_still_fails_when_the_metric_never_counts(capsys):
    def get(token, path, params):
        if path.endswith("/alerts"):
            raise alert.ApiHttpError(path, 404)
        return {"timeSeries": []}

    assert run(FakeGcloud(), get, poll_for=60) == 1
    assert "the metric never counted the entry" in capsys.readouterr().out


def test_any_other_alerts_error_is_a_failure():
    def get(token, path, params):
        if path.endswith("/alerts"):
            raise alert.ApiHttpError(path, 500)
        return SERIES_1

    with pytest.raises(alert.ApiHttpError):
        run(FakeGcloud(), get)
