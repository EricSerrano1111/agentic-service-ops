"""Offline tests for data/generator/validate.py: every check passes on a generated dataset,
and each deliberately broken input fails the check it targets. No database."""

from __future__ import annotations

import copy
import json
import sys
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest

_GEN = Path(__file__).resolve().parents[2] / "data" / "generator"
sys.path.insert(0, str(_GEN))
import generate as gen  # noqa: E402
import parameters as prm  # noqa: E402
import validate as val  # noqa: E402

P = prm.PARAMS
CHANNELS = list(P.feedback.channel_mix.value)


def _write_corpus(path: Path, scale: float) -> Path:
    """Synthetic corpus in feedback_text.jsonl's schema, enough for `scale`."""
    rng = np.random.default_rng(0)
    n = 0
    with open(path, "w", encoding="utf-8") as fh:
        for c in prm.expected_cell_counts(P):
            key = prm.corpus_cell_key(
                c["sentiment"], c["style"], c["context"], c["service_type"] or c["incident_type"]
            )
            for _ in range(int(c["required"] * scale) + 4):
                n += 1
                fh.write(
                    json.dumps(
                        {
                            "corpus_id": f"fb-{n:06d}",
                            "text": f"synthetic comment {n}",
                            "intended_sentiment": c["sentiment"],
                            "style": c["style"],
                            "hard_case_type": prm.HARD_CASE_BY_STYLE[c["style"]],
                            "cell": key,
                            "context": c["context"],
                            "service_type": c["service_type"],
                            "incident_type": c["incident_type"],
                            "channel": CHANNELS[int(rng.integers(len(CHANNELS)))],
                        }
                    )
                    + "\n"
                )
    return path


@pytest.fixture(scope="module")
def full(tmp_path_factory):
    """Full-scale dataset (about 5 s): distribution and signal checks need full volume."""
    corpus = _write_corpus(tmp_path_factory.mktemp("c") / "full.jsonl", 1.0)
    return gen.generate(corpus)


@pytest.fixture(scope="module")
def small(tmp_path_factory):
    corpus = _write_corpus(tmp_path_factory.mktemp("c") / "small.jsonl", 0.15)
    return gen.generate(corpus, scale=0.1)


def weekly(t):
    return [
        {k: r[k] for k in ("request_id", "scheduled_datetime", "service_type")}
        for r in t["service_requests"]
    ]


def truth(t):
    return val.Truth(t["generation_parameters"])


def broken(t, table: str) -> dict:
    """A copy whose `table` rows are deep-copied (so edits don't leak), others shared."""
    out = dict(t)
    out[table] = copy.deepcopy(t[table])
    return out


def by_id(checks) -> dict:
    return {c.id: c for c in checks}


# --------------------------------------------------------------------------- truth


def test_truth_from_generation_parameters_agrees_with_parameters(full):
    tr = truth(full)
    for key, value, _group, _notes in prm.to_generation_parameters_rows(P):
        assert tr[key] == value, key
    assert tr.start == P.window.start_monday.value
    assert tr.as_of == tr.window_end + timedelta(hours=P.window.snapshot_offset_hours.value)
    assert tr["derived_incidents.incident_rate_given_sla"] == pytest.approx(
        prm.incident_rates_by_sla(P)
    )
    assert tr.allowed_hard_types() == {
        "positive": {"none", "implicit"},
        "neutral": {"none"},
        "negative": {"none", "implicit", "sarcastic"},
        "mixed": {"none"},
    }
    days = [P.window.start_monday.value + timedelta(days=i) for i in range(400)]
    assert [tr.raw_daily_season(d) for d in days] == list(
        prm.daily_seasonal_factors(days, P, normalized=False)
    )


def test_truth_missing_key_is_an_error(full):
    with pytest.raises(KeyError, match="generation_parameters has no"):
        val.Truth([])["window.n_weeks"]


# --------------------------------------------------------------------------- clean data


def test_every_hard_check_passes_on_generated_data(full):
    checks, data = val.run_checks(full, weekly(full), truth(full))
    failed = [(c.id, c.value) for c in checks if c.hard and not c.passed]
    assert not failed
    assert {c.group for c in checks} == {
        "A invariants",
        "B distributions",
        "C signal recovery",
        "D anomalies",
        "E couplings",
        "F corpus",
    }


def test_invariants_pass_on_small_dataset(small):
    assert all(c.passed for c in val.check_invariants(small, truth(small)))
    assert all(c.passed for c in val.check_corpus(small, truth(small)))


def test_weekly_series_uses_only_forecast_columns(full):
    rows = weekly(full)
    assert set(rows[0]) == {"request_id", "scheduled_datetime", "service_type"}
    counts = val.weekly_counts(rows, truth(full))
    assert counts.sum() == len(full["service_requests"])


# --------------------------------------------------------------------------- A. broken


def _failing(checks) -> set[str]:
    return {c.id for c in checks if not c.passed}


def test_invariant_missing_archive_row(small):
    t = broken(small, "archived_requests")
    t["archived_requests"].pop()
    assert "A01" in _failing(val.check_invariants(t, truth(small)))


def test_invariant_credit_over_invoice(small):
    t = broken(small, "incidents")
    i = next(i for i in t["incidents"] if i["credit_issued_amount"] is not None)
    i["credit_issued_amount"] = Decimal("1000000.00")
    assert "A04" in _failing(val.check_invariants(t, truth(small)))


def test_invariant_feedback_without_label(small):
    t = dict(small)
    t["sentiment_labels"] = small["sentiment_labels"][1:]
    assert "A05" in _failing(val.check_invariants(t, truth(small)))


def test_invariant_missed_sla_on_met_request(small):
    t = broken(small, "incidents")
    arch = {a["request_id"]: a for a in small["archived_requests"]}
    req = {r["request_id"]: r for r in small["service_requests"]}
    i = next(
        i
        for i in t["incidents"]
        if i["incident_type"] != "missed_sla"
        and val.sla_met(req[i["request_id"]], arch[i["request_id"]])
    )
    i["incident_type"] = "missed_sla"
    assert "A11" in _failing(val.check_invariants(t, truth(small)))


def test_invariant_child_removed(small):
    t = dict(small)
    t["service_requests"] = [r for r in small["service_requests"] if r["parent_request_id"] is None]
    assert "A13" in _failing(val.check_invariants(t, truth(small)))


def test_invariant_old_pending_invoice(small):
    t = broken(small, "archived_requests")
    a = t["archived_requests"][0]
    a["payment_status"], a["payment_reference"] = "pending", None
    assert "A18" in _failing(val.check_invariants(t, truth(small)))


def test_invariant_event_after_snapshot(small):
    t = broken(small, "service_feedback")
    t["service_feedback"][0]["submitted_at"] = truth(small).as_of + timedelta(days=1)
    assert "A21" in _failing(val.check_invariants(t, truth(small)))


def test_invariant_wrong_incident_link(small):
    t = broken(small, "service_feedback")
    multi = {}
    for i in small["incidents"]:
        multi.setdefault(i["request_id"], []).append(i)
    f = next(
        f
        for f in t["service_feedback"]
        if f["incident_id"] is not None and len(multi[f["request_id"]]) > 1
    )
    f["incident_id"] = next(
        i["incident_id"] for i in multi[f["request_id"]] if i["incident_id"] != f["incident_id"]
    )
    assert "A15" in _failing(val.check_invariants(t, truth(small)))


# --------------------------------------------------------------------------- B. broken


def test_distribution_sentiment_shift_fails(full):
    t = broken(full, "sentiment_labels")
    flipped = 0
    for x in t["sentiment_labels"]:
        if x["true_sentiment"] == "positive" and x["hard_case_type"] == "none" and flipped < 300:
            x["true_sentiment"] = "negative"
            flipped += 1
    failed = _failing(val.check_distributions(t, truth(full)))
    assert {"B-sent-positive", "B-sent-negative"} <= failed


def test_distribution_cancellation_rate_fails(full):
    t = broken(full, "service_requests")
    for r in t["service_requests"][:1500]:
        r["request_status"] = "cancelled"
    assert "B-cancel" in _failing(val.check_distributions(t, truth(full)))


def test_distribution_pending_fails(full):
    t = broken(full, "archived_requests")
    for a in t["archived_requests"][:1000]:
        a["payment_status"] = "pending"
    assert "B-pending" in _failing(val.check_distributions(t, truth(full)))


# --------------------------------------------------------------------------- C/D. broken


def test_signal_flat_series_fails_trend_and_season(full):
    tr = truth(full)
    flat = [
        {
            "request_id": i,
            "scheduled_datetime": datetime.combine(
                tr.start + timedelta(weeks=w, days=1), time(12), tzinfo=UTC
            ),
            "service_type": "repair",
        }
        for w in range(tr.n_weeks)
        for i in range(120)
    ]
    checks, _ = val.check_signal(val.weekly_counts(flat, tr), tr)
    failed = _failing(checks)
    assert {"C-trend", "C-season", "C-noise"} <= failed  # noise 0 is below the band


def test_signal_extra_noise_fails(full):
    tr = truth(full)
    counts = val.weekly_counts(weekly(full), tr)
    rng = np.random.default_rng(1)
    noisy = counts * np.exp(rng.normal(0, 0.25, len(counts)))
    checks, _ = val.check_signal(noisy, tr)
    assert "C-noise" in _failing(checks)


def test_anomaly_regional_missing_fails(full):
    tr = truth(full)
    counts = val.weekly_counts(weekly(full), tr)
    _, fit = val.check_signal(counts, tr)
    x = val.design_matrix(np.arange(tr.n_weeks, dtype=float))
    filled = counts.copy()
    for w in tr.anomaly_weeks()["regional"]:
        filled[w] = np.exp(x[w] @ fit["coefs"])
    assert "D-regional" in _failing(val.check_anomalies(full, filled, fit, tr))


def test_anomaly_billing_outside_window_fails(full):
    tr = truth(full)
    t = broken(full, "archived_requests")
    weeks = set(tr.anomaly_weeks()["billing"])
    a = next(
        a
        for a in t["archived_requests"]
        if a["payment_method_final"] == "direct_bill" and tr.week_of(a["completed_at"]) not in weeks
    )
    a["surcharge_rate"] = Decimal("0.1000")
    counts = val.weekly_counts(weekly(full), tr)
    _, fit = val.check_signal(counts, tr)
    assert "D-billing" in _failing(val.check_anomalies(t, counts, fit, tr))


def test_anomaly_account_drop_missing_fails(full):
    tr = truth(full)
    counts = val.weekly_counts(weekly(full), tr)
    _, fit = val.check_signal(counts, tr)
    t = broken(full, "service_requests")
    # Move every request of every account out of the account-drop weeks' neighbourhood so
    # the top account's weekly volume looks the same inside and outside the window.
    weeks = tr.anomaly_weeks()["account"]
    top = val.Counter(r["account_id"] for r in t["service_requests"]).most_common(1)[0][0]
    donors = [
        r
        for r in t["service_requests"]
        if r["account_id"] == top and tr.week_of(r["scheduled_datetime"]) == weeks[0] - 1
    ]
    extra = []
    for w in weeks:
        for r in donors:
            c = dict(r)
            c["scheduled_datetime"] = r["scheduled_datetime"] + timedelta(weeks=w - weeks[0] + 1)
            extra.append(c)
    t["service_requests"] = t["service_requests"] + extra
    assert "D-account" in _failing(val.check_anomalies(t, counts, fit, tr))


# --------------------------------------------------------------------------- E/F. broken


def test_coupling_severity_sentiment_broken_fails(full):
    t = broken(full, "sentiment_labels")
    inc_rows = {f["feedback_id"] for f in full["service_feedback"] if f["incident_id"] is not None}
    for x in t["sentiment_labels"]:
        if x["feedback_id"] in inc_rows:
            x["true_sentiment"] = "positive"
    failed = _failing(val.check_couplings(t, truth(full))[0])
    assert {"E-sev-low", "E-sev-medium", "E-sev-high"} <= failed


def test_coupling_neutral_on_incident_row_fails(full):
    t = broken(full, "sentiment_labels")
    inc_rows = {f["feedback_id"] for f in full["service_feedback"] if f["incident_id"] is not None}
    x = next(x for x in t["sentiment_labels"] if x["feedback_id"] in inc_rows)
    x["true_sentiment"] = "neutral"
    checks = val.check_couplings(t, truth(full))[0]
    assert any(c.id.startswith("E-sev") and not c.passed for c in checks)
    assert "F-cells" in _failing(val.check_corpus(t, truth(full)))


def test_coupling_sla_incident_rate_broken_fails(full):
    t = dict(full)
    arch = {a["request_id"]: a for a in full["archived_requests"]}
    req = {r["request_id"]: r for r in full["service_requests"]}
    t["incidents"] = [
        i for i in full["incidents"] if val.sla_met(req[i["request_id"]], arch[i["request_id"]])
    ]
    assert "E-sla_missed" in _failing(val.check_couplings(t, truth(full))[0])


def test_coupling_ratings_broken_fails(full):
    t = broken(full, "service_feedback")
    for f in t["service_feedback"]:
        if f["rating"] is not None:
            f["rating"] = 3
    failed = _failing(val.check_couplings(t, truth(full))[0])
    assert {"E-rating-positive", "E-rating-negative"} <= failed


def test_corpus_duplicate_text_and_id_fail(small):
    t = broken(small, "service_feedback")
    t["service_feedback"][1]["feedback_text"] = t["service_feedback"][0]["feedback_text"]
    t = dict(t)
    t["sentiment_labels"] = copy.deepcopy(small["sentiment_labels"])
    t["sentiment_labels"][1]["corpus_id"] = t["sentiment_labels"][0]["corpus_id"]
    assert {"F-text", "F-id"} <= _failing(val.check_corpus(t, truth(small)))


def test_corpus_sarcastic_positive_fails(small):
    t = broken(small, "sentiment_labels")
    x = next(x for x in t["sentiment_labels"] if x["true_sentiment"] == "positive")
    x["hard_case_type"] = "sarcastic"
    assert "F-cells" in _failing(val.check_corpus(t, truth(small)))


# --------------------------------------------------------------------------- outputs


def test_outputs_and_spot_check(full, tmp_path):
    tr = truth(full)
    checks, data = val.run_checks(full, weekly(full), tr)
    val.write_outputs(tmp_path, checks, data, full, tr, {"source": "test"})
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["tolerances_fixed_before_results"]["regional_z_min"] == 3.0
    assert all(c["status"] in ("PASS", "FAIL", "NOTE") for c in report["checks"])
    for png in (
        "weekly_volume_fit",
        "seasonal_profile",
        "sentiment_mix",
        "severity_sentiment_heatmap",
        "incident_rate_by_sla",
    ):
        assert (tmp_path / f"{png}.png").stat().st_size > 10_000
    rows = val.spot_check_rows(full)
    assert len(rows) == 30 and rows == val.spot_check_rows(full)  # fixed seed
    assert set(rows[0]) == {
        "corpus_id",
        "feedback_text",
        "true_sentiment",
        "hard_case_type",
        "incident_type",
        "incident_severity",
        "unusable_yn",
        "notes",
    }
    assert all(r["unusable_yn"] == "" and r["notes"] == "" for r in rows)


def test_sql_checks_wrap_counts():
    checks = val.sql_checks({"a": 0, "b": 2})
    assert [c.passed for c in checks] == [True, False]
    assert set(val.SQL_INVARIANTS) and all("SELECT" in q for q in val.SQL_INVARIANTS.values())
