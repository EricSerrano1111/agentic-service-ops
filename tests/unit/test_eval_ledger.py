"""The Sprint 5 paid-run ledger (Prompt W): the cap holds across invocations, a refused call is
never sent, and paid mode needs both the flag and LLM_MODE=paid. No model is called."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("sprint5_ledger", ROOT / "evals" / "ledger.py")
ledger_mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ledger_mod
spec.loader.exec_module(ledger_mod)


def client(requests: int = 0, cost: float = 0.0):
    return SimpleNamespace(totals=SimpleNamespace(requests=requests, cost_usd=cost))


def call(ledger, path="A1", *, requests=1, cost=0.001):
    c = client()
    with ledger.call(c, path):
        c.totals.requests += requests
        c.totals.cost_usd += cost


def test_caps_are_the_owner_decision():
    assert (ledger_mod.CAP_REQUESTS, ledger_mod.CAP_USD) == (561, 3.00)


def test_sum_holds_across_separate_ledger_objects(tmp_path):
    f = tmp_path / "l.json"
    for path in ("A1", "A2", "C1"):  # each a new object, as each runner invocation is
        call(ledger_mod.Ledger(f), path, requests=2, cost=0.01)
    s = ledger_mod.Ledger(f).totals()
    assert s["requests"] == 6 and s["calls"] == 3
    assert s["cost_usd"] == pytest.approx(0.03)
    assert s["by_path"]["A2"]["requests"] == 2


def test_request_cap_refuses_the_call_before_it_is_made(tmp_path):
    led = ledger_mod.Ledger(tmp_path / "l.json", cap_requests=3, cap_usd=3.0)
    call(led, requests=3)
    sent = []
    with pytest.raises(ledger_mod.LedgerRefused), led.call(client(), "A1"):
        sent.append(1)
    assert sent == []
    assert led.totals()["requests"] == 3


def test_spend_cap_uses_the_largest_call_seen(tmp_path):
    led = ledger_mod.Ledger(tmp_path / "l.json", cap_requests=100, cap_usd=0.10)
    call(led, cost=0.06)
    with pytest.raises(ledger_mod.LedgerRefused):  # 0.06 spent + 0.06 worst case > 0.10
        led.check("A1")


def test_a_failed_call_is_still_counted(tmp_path):
    led = ledger_mod.Ledger(tmp_path / "l.json")
    c = client()
    with pytest.raises(RuntimeError), led.call(c, "C1"):
        c.totals.requests += 3  # retries before the error
        raise RuntimeError("boom")
    assert led.totals()["requests"] == 3


def test_caps_cannot_be_changed_after_creation(tmp_path):
    f = tmp_path / "l.json"
    ledger_mod.Ledger(f)
    with pytest.raises(ledger_mod.LedgerRefused):
        ledger_mod.Ledger(f, cap_requests=1000)


def test_unknown_path_is_refused(tmp_path):
    with pytest.raises(ledger_mod.LedgerRefused):
        ledger_mod.Ledger(tmp_path / "l.json").check("Z9")


def test_paid_mode_needs_flag_and_env_together():
    require = ledger_mod.require_paid
    require(False, "free", None)  # free mode unchanged
    require(True, "paid", "A1")
    with pytest.raises(SystemExit):
        require(True, "free", "A1")
    with pytest.raises(SystemExit):
        require(False, "paid", "A1")
    with pytest.raises(SystemExit):
        require(True, "paid", None)
