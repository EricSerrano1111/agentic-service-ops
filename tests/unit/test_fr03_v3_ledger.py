"""ADR-114's harness ledger and the P0 probe's pure parts. No model is called."""

from __future__ import annotations

import datetime as dt
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "fr03_v3_ledger_under_test", ROOT / "evals" / "fr03_v3" / "ledger.py"
)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

NOW = dt.datetime(2026, 10, 25, 12, 0, tzinfo=dt.UTC)


def run(level="low", items=10, k=1, phase="P0"):
    return {"phase": phase, "level": level, "items": items, "k": k}


def end(ledger, level="low", *, requests=10, calls=10, cost=0.02, phase="P0"):
    ledger.run_end(
        {"phase": phase, "level": level},
        {"calls": calls, "requests": requests, "cost_usd": cost},
    )


@pytest.fixture
def ledger(tmp_path):
    led = mod.Ledger(tmp_path / "ledger.jsonl", dirty=lambda: [])
    led.record_balance(10.0)
    return led


def test_the_caps_are_adr_114s():
    assert (mod.REQUEST_CAP, mod.SPEND_CAP_USD) == (1550, 2.50)
    assert (mod.PROJECTION_FACTOR, mod.MIN_BALANCE_USD) == (1.25, 7.50)


def test_projection_uses_the_ceiling_before_a_probe_result_and_the_mean_after(ledger):
    p = ledger.project("low", 10, 1)
    assert (p.requests, p.basis) == (10, "ceiling")
    assert p.usd == pytest.approx(0.003 * 10 * 1 * 1.25)
    end(ledger, "low", calls=10, cost=0.02)  # mean $0.002 per call
    p = ledger.project("low", 115, 3)
    assert (p.requests, p.basis) == (345, "probe")
    assert p.usd == pytest.approx(0.002 * 115 * 3 * 1.25)
    assert ledger.project("high", 10, 1).basis == "ceiling"  # other levels have no result yet


def test_a_non_probe_run_does_not_set_a_levels_probe_mean(ledger):
    end(ledger, "low", calls=10, cost=0.5, phase="P1")
    assert ledger.project("low", 10, 1).basis == "ceiling"


def test_refuses_one_request_over_the_cap_and_allows_the_cap_exactly(ledger):
    end(ledger, "low", requests=1550 - 11, calls=1, cost=0.0)
    assert ledger.authorize(run(items=11), now=NOW).requests == 11  # lands on 1550
    with pytest.raises(mod.Refused, match="request cap"):
        ledger.authorize(run(items=12), now=NOW)
    last = ledger.events()[-1]
    assert last["event"] == "refused" and "request cap" in last["reason"]


def test_refuses_one_cent_over_the_spend_cap_and_allows_the_cap_exactly(ledger):
    projected = 0.003 * 10 * 1.25  # $0.0375 at the ceiling
    end(ledger, "medium", requests=0, calls=1, cost=round(2.50 - projected, 6))
    ledger.authorize(run(), now=NOW)  # lands exactly on $2.50
    end(ledger, "medium", requests=0, calls=1, cost=0.01)
    with pytest.raises(mod.Refused, match="spend cap"):
        ledger.authorize(run(), now=NOW)


def test_dry_run_refusal_writes_nothing(ledger):
    end(ledger, "low", requests=1550, calls=1, cost=0.0)
    before = ledger.path.read_text(encoding="utf-8")
    with pytest.raises(mod.Refused):
        ledger.authorize(run(), now=NOW, dry_run=True)
    assert ledger.path.read_text(encoding="utf-8") == before


def test_a_balance_below_the_minimum_is_refused(tmp_path):
    led = mod.Ledger(tmp_path / "l.jsonl", dirty=lambda: [])
    with pytest.raises(mod.Refused, match="no balance_reading"):
        led.authorize(run(), now=NOW)
    led.record_balance(7.49)
    with pytest.raises(mod.Refused, match="below"):
        led.authorize(run(), now=NOW)
    led.record_balance(7.50)  # the latest reading counts
    led.authorize(run(), now=NOW)


def test_refuses_an_unknown_level_and_a_run_after_the_timebox(ledger):
    with pytest.raises(mod.Refused, match="unknown thinking level"):
        ledger.authorize(run(level="ultra"), now=NOW)
    ledger.authorize(run(), now=dt.datetime(2026, 11, 8, 5, 58, tzinfo=dt.UTC))
    with pytest.raises(mod.Refused, match="timebox"):
        ledger.authorize(run(), now=dt.datetime(2026, 11, 8, 6, 0, tzinfo=dt.UTC))


def test_the_ledger_is_append_only(tmp_path, monkeypatch):
    path = tmp_path / "ledger.jsonl"
    led = mod.Ledger(path, dirty=lambda: [])
    led.record_balance(10.0)
    first = path.read_bytes()
    opened = []
    real_open = Path.open

    def spy(self, mode="r", *a, **kw):
        if self == path:
            opened.append(mode)
        return real_open(self, mode, *a, **kw)

    monkeypatch.setattr(Path, "open", spy)
    led.stop("a reason")
    led.level_verdict("low", "kept", "fine")
    assert opened == ["a", "a"]
    data = path.read_bytes()
    assert data.startswith(first) and data.count(b"\n") == 3
    assert [e["event"] for e in led.events()] == ["balance_reading", "stop", "level_verdict"]


def test_totals_read_back_and_sum_only_run_ends(ledger):
    ledger.run_start({"phase": "P0", "level": "low"})
    end(ledger, "low", requests=10, calls=10, cost=0.02)
    end(ledger, "medium", requests=11, calls=10, cost=0.05)
    ledger.stop("x")
    t = ledger.totals()
    assert (t["requests"], t["calls"], t["cost_usd"]) == (21, 20, 0.07)
    assert t["probe_mean_cost_per_call"] == {"low": pytest.approx(0.002), "medium": 0.005}


def test_the_zero_thinking_stop():
    assert mod.all_zero_thinking("low", [0, 0, 0])
    assert not mod.all_zero_thinking("low", [0, 12, 0])
    assert not mod.all_zero_thinking("minimal", [0, 0])  # minimal may think nothing
    assert not mod.all_zero_thinking("high", [])  # no responses is a different failure


def test_probe_verdict_drops_on_cost_or_p95():
    assert mod.probe_verdict(0.003, 10.0)[0]  # at the ceiling is kept
    assert not mod.probe_verdict(0.0031, 2.0)[0]
    kept, why = mod.probe_verdict(0.001, 10.01)
    assert not kept and "p95" in why


def test_percentiles():
    assert mod.percentile_95([]) is None
    assert mod.percentile_95(list(map(float, range(1, 11)))) == 10.0  # nearest rank, n=10
    assert mod.percentile_95(list(map(float, range(1, 101)))) == 95.0
    assert mod.latency_summary([1.0, 2.0, 3.0]) == {"median_s": 2.0, "p95_s": 3.0}


def test_probe_summary_separates_thinking_and_keeps_errors():
    probe_spec = importlib.util.spec_from_file_location(
        "fr03_probe_under_test", ROOT / "evals" / "fr03_v3" / "probe.py"
    )
    probe = importlib.util.module_from_spec(probe_spec)
    sys.modules[probe_spec.name] = probe
    probe_spec.loader.exec_module(probe)
    call = {
        "requests": 1,
        "input_tokens": 1000,
        "output_tokens": 300,
        "thinking_tokens": 250,
        "cost_usd": 0.001,
        "latency_s": 2.0,
        "error": None,
    }
    s = probe.summarize([call, {**call, "error": "LLMOutputInvalid", "latency_s": 4.0}])
    assert (s["calls"], s["requests"], s["thinking_tokens"], s["output_tokens"]) == (2, 2, 500, 600)
    assert s["mean_cost_per_call_usd"] == 0.001 and s["errors"] == {"LLMOutputInvalid": 1}
    assert s["latency"] == {"median_s": 3.0, "p95_s": 4.0}


def test_a_dirty_tree_is_refused_and_recorded(ledger):
    ledger._dirty = lambda: [" M evals/fr03_v3/probe.py"]
    with pytest.raises(mod.Refused, match="dirty_tree"):
        ledger.authorize(run(), now=NOW)
    last = ledger.events()[-1]
    assert last["event"] == "refused" and last["reason"] == "dirty_tree"
    assert last["dirty_paths"] == [" M evals/fr03_v3/probe.py"]


def git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def test_dirty_tree_sees_code_but_not_the_run_outputs_or_ignored_files(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / ".gitignore").write_text("ignored.txt\n")
    (tmp_path / "evals" / "fr03_v3").mkdir(parents=True)
    (tmp_path / "evals" / "results" / "fr03_v3").mkdir(parents=True)
    (tmp_path / "evals" / "fr03_v3" / "ledger.jsonl").write_text("{}\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "base")
    assert mod.dirty_tree(tmp_path) == []
    (tmp_path / "ignored.txt").write_text("x")
    (tmp_path / "evals" / "fr03_v3" / "ledger.jsonl").write_text("{}\n{}\n")  # the run's own
    (tmp_path / "evals" / "results" / "fr03_v3" / "r.json").write_text("{}")
    assert mod.dirty_tree(tmp_path) == []
    assert mod.dirty_tree(tmp_path / "evals" / "fr03_v3") == []  # from the subfolder, as run
    (tmp_path / "evals" / "fr03_v3" / "probe.py").write_text("changed")
    assert len(mod.dirty_tree(tmp_path)) == 1


def test_a_zero_thinking_level_is_dropped_without_stopping_while_another_remains(ledger):
    ledger.level_verdict("low", "dropped", "zero_thinking")
    ledger.level_verdict("medium", "dropped", "zero_thinking")
    assert not ledger.every_probed_level_is_zero_thinking(["high"])


def test_the_session_stops_when_every_probed_level_is_zero_thinking(ledger):
    ledger.level_verdict("low", "dropped", "zero_thinking")
    assert not ledger.every_probed_level_is_zero_thinking(["medium", "high"])  # still to run
    ledger.level_verdict("medium", "dropped", "zero_thinking")
    ledger.level_verdict("high", "dropped", "zero_thinking")
    assert ledger.every_probed_level_is_zero_thinking([])


def test_a_level_that_thinks_or_was_dropped_for_cost_prevents_the_stop(ledger):
    ledger.level_verdict("low", "dropped", "zero_thinking")
    ledger.level_verdict("medium", "dropped", "mean cost $0.004 per call is above $0.003")
    assert not ledger.every_probed_level_is_zero_thinking([])
    empty = mod.Ledger(ledger.path.with_name("empty.jsonl"))
    assert not empty.every_probed_level_is_zero_thinking([])


def test_verdicts_are_read_back_per_level(ledger):
    ledger.level_verdict("low", "dropped", "zero_thinking", source="run_end")
    assert set(ledger.verdicts()) == {"low"} and ledger.verdicts()["low"]["source"] == "run_end"
