"""Offline tests for data/generator/parameters.py: seeds, the sentiment solver, the
ADR-036 cell rules, generation_parameters rows, and validate_parameters()."""

import dataclasses
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

_GEN = Path(__file__).resolve().parents[2] / "data" / "generator"
sys.path.insert(0, str(_GEN))
import parameters as prm  # noqa: E402

# --------------------------------------------------------------------------- validation


def test_default_parameters_validate():
    prm.validate_parameters()


def _replace(domain: str, name: str, value, kind: str | None = None) -> prm.Parameters:
    dom = getattr(prm.PARAMS, domain)
    old = getattr(dom, name)
    new_p = dataclasses.replace(old, value=prm.fz(value) if isinstance(value, dict) else value)
    if kind:
        new_p = dataclasses.replace(new_p, kind=kind)
    return dataclasses.replace(prm.PARAMS, **{domain: dataclasses.replace(dom, **{name: new_p})})


@pytest.mark.parametrize(
    ("domain", "name", "value", "match"),
    [
        ("requests", "priority_mix", {"standard": 0.7, "urgent": 0.2, "critical": 0.08}, "sums to"),
        ("incidents", "request_incident_rate", 0.2, "incidents"),
        ("feedback", "response_rate_no_incident", 0.8, "feedback"),
        ("volume", "expected_new_requests", 30_000, "requests"),
        (
            "anomalies",
            "volume_drop",
            {"account_rank": 1, "drop": 0.9, "start_week": 140, "n_weeks": 2},
            "holdout",
        ),
        (
            "anomalies",
            "billing_surcharge",
            {
                "payment_method": "direct_bill",
                "surcharge_rate": 0.1,
                "start_week": 129,
                "n_weeks": 3,
            },
            "holdout",
        ),
        (
            "sentiment",
            "hard_case_shares",
            {("positive", "implicit"): 0.08, ("mixed", "sarcastic"): 0.07},
            "forbidden",
        ),
        (
            "requests",
            "sla_window_minutes",
            {
                "standard": {"standard": 480, "urgent": 240, "critical": 120},
                "priority": {"standard": 240, "urgent": 120, "critical": 60},
                "enterprise": {"standard": 120, "urgent": 60, "critical": 240},
            },
            "shrink",
        ),
        ("incidents", "severity_mix", {"low": 0.5, "medium": 0.35, "severe": 0.15}, "severity_mix"),
        (
            "sentiment",
            "incident_sentiment_by_severity",
            {
                "low": {"positive": 0.3, "neutral": 0.1, "negative": 0.35, "mixed": 0.25},
                "medium": {"positive": 0.15, "neutral": 0.0, "negative": 0.60, "mixed": 0.25},
                "high": {"positive": 0.10, "neutral": 0.0, "negative": 0.70, "mixed": 0.20},
            },
            "neutral must be 0",
        ),
    ],
)
def test_validate_catches_bad_parameters(domain, name, value, match):
    with pytest.raises(ValueError, match=match):
        prm.validate_parameters(_replace(domain, name, value))


def test_validate_catches_infeasible_sentiment():
    # A huge incident share of feedback forces negative no-incident positives.
    bad = _replace(
        "sentiment",
        "target_mix",
        {"positive": 0.02, "neutral": 0.40, "negative": 0.50, "mixed": 0.08},
    )
    with pytest.raises(ValueError, match="infeasible"):
        prm.validate_parameters(bad)


def test_expected_totals_within_dictionary_ranges():
    t = prm.expected_totals()
    assert 18_000 <= t["new_requests"] <= 22_000
    assert 15_000 <= t["requests"] <= 25_000
    assert 0.35 <= t["feedback_per_completed"] <= 0.50
    assert 0.08 <= t["incidents_per_completed"] <= 0.12
    assert t["missed_sla_incidents"] < t["sla_misses"]


def test_sla_mu_hits_targets():
    from statistics import NormalDist

    sigma = prm.PARAMS.requests.completion_ratio_sigma.value
    for pr, mu in prm.completion_ratio_mu().items():
        met = NormalDist(mu, sigma).cdf(0.0)  # P(log ratio <= 0)
        assert met == pytest.approx(prm.PARAMS.requests.sla_met_target.value[pr], abs=1e-12)


def test_largest_account_share():
    shares = prm.account_volume_shares()
    assert shares[0] == pytest.approx(0.12, abs=1e-6)
    assert sum(shares) == pytest.approx(1.0)
    assert shares == sorted(shares, reverse=True)


# --------------------------------------------------------------------------- seeds


def _seed_state_in_subprocess(stage: str, hashseed: str) -> list[int]:
    code = (
        "import sys, json; sys.path.insert(0, sys.argv[1]); import parameters as p; "
        "print(json.dumps(p.derive_seed(sys.argv[2]).generate_state(4).tolist()))"
    )
    env = {**os.environ, "PYTHONHASHSEED": hashseed}
    out = subprocess.run(
        [sys.executable, "-c", code, str(_GEN), stage],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    return json.loads(out.stdout)


def test_seed_stable_across_processes():
    here = prm.derive_seed(prm.STAGE_VOLUME).generate_state(4).tolist()
    assert _seed_state_in_subprocess(prm.STAGE_VOLUME, "1") == here
    assert _seed_state_in_subprocess(prm.STAGE_VOLUME, "987") == here


def test_new_stage_does_not_change_existing():
    before = {s: prm.derive_seed(s).generate_state(4).tolist() for s in prm.STAGES}
    prm.derive_seed("a_future_stage")
    after = {s: prm.derive_seed(s).generate_state(4).tolist() for s in prm.STAGES}
    assert before == after
    # A stage's seed depends only on its own name and the master seed.
    assert prm.derive_seed(prm.STAGE_FEEDBACK).entropy == [
        prm.MASTER_SEED,
        prm.stage_key(prm.STAGE_FEEDBACK),
    ]


def test_stage_seeds_differ():
    states = {tuple(prm.derive_seed(s).generate_state(4)) for s in prm.STAGES}
    assert len(states) == len(prm.STAGES) == 11
    assert prm.stage_key("volume") != prm.stage_key("Volume")


def test_stage_key_is_sha256_prefix():
    import hashlib

    assert prm.stage_key("reference") == int.from_bytes(
        hashlib.sha256(b"reference").digest()[:8], "big"
    )
    with pytest.raises(ValueError):
        prm.stage_key("")


# --------------------------------------------------------------------------- solver


def test_solver_reproduces_targets():
    t = prm.expected_totals()
    f = t["feedback_incident_share"]
    inc = prm.incident_row_sentiment()
    p0 = prm.no_incident_sentiment()
    for se, target in prm.PARAMS.sentiment.target_mix.value.items():
        assert f * inc[se] + (1 - f) * p0[se] == pytest.approx(target, abs=1e-12)
        assert 0 <= p0[se] <= 1
    assert sum(p0.values()) == pytest.approx(1.0)
    assert inc["neutral"] == 0


def test_solver_rejects_infeasible():
    with pytest.raises(ValueError, match="infeasible"):
        prm.solve_no_incident_distribution(
            {"positive": 0.05, "neutral": 0.25, "negative": 0.6, "mixed": 0.1},
            {"positive": 0.5, "neutral": 0.0, "negative": 0.3, "mixed": 0.2},
            0.5,
        )
    with pytest.raises(ValueError):
        prm.solve_no_incident_distribution({}, {}, 1.0)


def test_max_severity_dist():
    msd = prm.max_severity_dist()
    assert sum(msd.values()) == pytest.approx(1.0)
    # More incidents per request can only push the maximum up.
    assert msd["high"] > prm.PARAMS.incidents.severity_mix.value["high"]


# --------------------------------------------------------------------------- cell rules


@pytest.mark.parametrize(
    "cell",
    [
        ("neutral", "plain", "minor"),
        ("neutral", "plain", "serious"),
        ("neutral", "implicit", "none"),
        ("neutral", "sarcastic", "none"),
        ("mixed", "implicit", "none"),
        ("mixed", "sarcastic", "minor"),
        ("positive", "sarcastic", "none"),
    ],
)
def test_forbidden_cells_excluded(cell):
    assert not prm.is_allowed(*cell)
    assert cell not in prm.ALLOWED_CELLS


def test_allowed_cells():
    assert prm.is_allowed("neutral", "plain", "none")
    assert prm.is_allowed("mixed", "plain", "serious")
    assert prm.is_allowed("negative", "sarcastic", "serious")
    assert prm.is_allowed("positive", "implicit", "minor")
    # 2 positive + 3 negative + 1 mixed styles x 3 contexts, plus neutral/plain/none.
    assert len(prm.ALLOWED_CELLS) == (2 + 3 + 1) * 3 + 1


def test_corpus_cells_all_allowed_and_sized():
    cells = prm.expected_cell_counts()
    s = prm.corpus_summary()
    # 7 (sentiment, style) pairs x 5 service types, plus incident cells for the 4
    # non-positive pairs x 2 levels x 7 types (ADR-039 removed positive x incident).
    assert s["cells"] == len(cells) == 7 * 5 + 4 * 2 * 7
    floor = prm.PARAMS.corpus.cell_floor.value
    doubles = {("neutral", "plain"), ("mixed", "plain")}
    for c in cells:
        assert prm.is_corpus_cell(c["sentiment"], c["style"], c["context"])
        mult = 2.0 if (c["sentiment"], c["style"]) in doubles else 1.2
        q = prm.poisson_ppf(0.99, c["expected"])
        assert c["required"] == max(floor, math.ceil(q * mult))
        assert c["required"] >= c["expected"]
    assert s["expected_rows"] == pytest.approx(prm.expected_totals()["feedback"])


# --------------------------------------------------------------------------- rows


def test_generation_parameters_rows():
    rows = prm.to_generation_parameters_rows()
    groups = {"volume", "incidents", "sentiment", "billing", "anomalies", "world", "feedback"}
    keys = [r[0] for r in rows]
    assert len(keys) == len(set(keys))
    for key, value, group, notes in rows:
        assert len(key) <= 100, key
        assert group in groups
        assert notes.strip()
        json.dumps(value)  # JSON-safe
    assert rows[0] == ("seed.master_seed", prm.MASTER_SEED, "world", rows[0][3])
    n_params = sum(1 for _ in prm.iter_params())
    assert len(rows) == n_params + 2 + 12
    by_key = {r[0]: r for r in rows}
    assert by_key["regions.states"][2] == "world"
    assert by_key["corpus.cell_floor"][2] == "feedback"
    assert by_key["feedback.channel_mix"][2] == "feedback"


def test_param_groups_match_schema_enum():
    import db_models.enums as e

    assert set(prm.GROUP_BY_DOMAIN.values()) <= set(e.values(e.ParamGroup))
    assert {"world", "feedback"} <= set(prm.GROUP_BY_DOMAIN.values())
    # Every parameter domain has a group.
    assert {d for d, _, _ in prm.iter_params()} <= set(prm.GROUP_BY_DOMAIN)


def test_every_parameter_has_a_note():
    for domain, name, p in prm.iter_params():
        assert p.note.strip(), f"{domain}.{name}"
        assert p.kind in {"value", "dist", "dist_by"}


def test_parameters_are_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        prm.PARAMS.volume.weekly_noise_sd = prm.V(0.1, "x")  # type: ignore[misc]
    with pytest.raises(TypeError):
        prm.PARAMS.requests.priority_mix.value["standard"] = 0.5  # type: ignore[index]


# --------------------------------------------------------------------------- ADR-038


def _sla_matrix_from_dictionary() -> dict[str, dict[str, int]]:
    path = Path(__file__).resolve().parents[2] / "docs" / "data-dictionary.md"
    text = path.read_text(encoding="utf-8")
    block = text.split("**SLA defaults by tier (minutes)", 1)[1].split("\n\n", 2)[1]
    out = {}
    for line in block.splitlines():
        m = re.match(r"\|\s*`(\w+)`\s*\|(.*)\|\s*$", line)
        if m:
            nums = [int(re.match(r"\d+", c.strip()).group()) for c in m.group(2).split("|")]
            out[m.group(1)] = dict(zip(prm.PRIORITIES, nums, strict=True))
    return out


def test_sla_matrix_matches_data_dictionary():
    """parameters.py is the authority at generation time; the doc must agree (ADR-038)."""
    encoded = {k: dict(v) for k, v in prm.PARAMS.requests.sla_window_minutes.value.items()}
    assert _sla_matrix_from_dictionary() == encoded


def test_validate_does_not_read_docs():
    import inspect

    assert "docs" not in inspect.getsource(prm.validate_parameters)
    assert not hasattr(prm, "DICTIONARY")


@pytest.mark.parametrize(("q", "lam", "k"), [(0.99, 1.0, 4), (0.99, 10.0, 18), (0.5, 0.0, 0)])
def test_poisson_ppf_known_values(q, lam, k):
    assert prm.poisson_ppf(q, lam) == k


def test_poisson_ppf_large_lambda():
    lam = 1500.0
    k = prm.poisson_ppf(0.99, lam)
    # Normal approximation: lam + 2.326 * sqrt(lam), within a couple of counts.
    assert abs(k - (lam + 2.326 * math.sqrt(lam))) < 3


def test_regions():
    states = prm.PARAMS.regions.states.value
    shares = prm.PARAMS.regions.share.value
    assert set(states) == {"northeast", "southeast", "central", "west"}
    assert dict(shares) == {"northeast": 0.30, "southeast": 0.25, "central": 0.25, "west": 0.20}
    flat = [st for sts in states.values() for st in sts]
    assert len(flat) == len(set(flat)) == 51  # 50 states + DC


def test_anomaly_strength():
    z = {k: v["z_window"] for k, v in prm.anomaly_strength().items()}
    assert z["regional_drop"] >= 3
    assert z["account_drop"] < 2  # invisible in totals by design; visible per account
    assert z["billing_surcharge"] > 10
    reg = prm.anomaly_strength()["regional_drop"]["weeks"]
    assert [w["week_start"] for w in reg] == ["2025-02-17", "2025-02-24"]


@pytest.mark.parametrize(
    ("value", "match"),
    [
        (
            {"region": "northeast", "drop": 0.30, "start": prm.date(2025, 2, 17), "n_weeks": 2},
            "must be >= 3",
        ),
        (
            {"region": "west", "drop": 0.85, "start": prm.date(2025, 2, 17), "n_weeks": 2},
            "largest-share region",
        ),
        (
            {"region": "northeast", "drop": 0.85, "start": prm.date(2025, 2, 18), "n_weeks": 2},
            "not a Monday",
        ),
        (
            {"region": "northeast", "drop": 0.85, "start": prm.date(2026, 4, 6), "n_weeks": 2},
            "holdout",
        ),
        (
            {"region": "northeast", "drop": 0.85, "start": prm.date(2024, 6, 17), "n_weeks": 2},
            "overlap",
        ),
    ],
)
def test_validate_catches_bad_regional_anomaly(value, match):
    with pytest.raises(ValueError, match=match):
        prm.validate_parameters(_replace("anomalies", "regional_drop", value))


def test_effective_noise_note_matches_derived_value():
    eff = prm.effective_weekly_noise()
    assert eff == pytest.approx(0.106, abs=0.0005)
    assert f"~{eff * 100:.1f}%" in prm.PARAMS.volume.weekly_noise_sd.note


def test_incident_status_by_age():
    window = prm.PARAMS.incidents.incident_active_window_weeks.value
    shares = [prm.incident_active_share(age) for age in range(window + 3)]
    assert shares[0] == prm.PARAMS.incidents.incident_active_share_at_end.value
    assert all(a > b for a, b in zip(shares[:window], shares[1:window], strict=False))
    assert all(x == 0 for x in shares[window:])
    assert 0 < prm.expected_active_incidents() < prm.expected_totals()["incidents"]


def test_other_incident_type_has_a_phrasing():
    phr = prm.PARAMS.corpus.incident_type_phrasing.value
    assert phr["other"] == "a problem with the visit"
    assert set(phr) == set(prm.INCIDENT_TYPES)


# --------------------------------------------------------------------------- ADR-039


def test_no_positive_incident_cells_remain():
    cells = prm.expected_cell_counts()
    assert not [c for c in cells if c["sentiment"] == "positive" and c["context"] != "none"]
    for ctx in ("minor", "serious"):
        for st in ("plain", "implicit"):
            assert prm.is_allowed("positive", st, ctx)  # still a valid feedback row
            assert not prm.is_corpus_cell("positive", st, ctx)


@pytest.mark.parametrize(
    ("row", "cell"),
    [
        (("positive", "plain", "repair", "serious", "missed_sla"), "positive|plain|none|repair"),
        (("positive", "implicit", "install", "minor", "other"), "positive|implicit|none|install"),
        (("positive", "plain", "upgrade", "none", None), "positive|plain|none|upgrade"),
        (
            ("negative", "sarcastic", "repair", "serious", "billing_dispute"),
            "negative|sarcastic|serious|billing_dispute",
        ),
        (("mixed", "plain", "inspection", "minor", "missed_sla"), "mixed|plain|minor|missed_sla"),
        (("neutral", "plain", "maintenance", "none", None), "neutral|plain|none|maintenance"),
    ],
)
def test_corpus_cell_for_row(row, cell):
    assert prm.corpus_cell_for_row(*row) == cell
    keys = {
        prm.corpus_cell_key(
            c["sentiment"], c["style"], c["context"], c["service_type"] or c["incident_type"]
        )
        for c in prm.expected_cell_counts()
    }
    assert cell in keys


def test_corpus_cell_for_row_rejects_forbidden_rows():
    with pytest.raises(ValueError):
        prm.corpus_cell_for_row("neutral", "plain", "repair", "minor", "missed_sla")
    with pytest.raises(ValueError):
        prm.corpus_cell_for_row("negative", "plain", "repair", "serious", None)


def test_enlarged_positive_cells_cover_combined_demand():
    t = prm.expected_totals()
    inc_pos = t["feedback_incident"] * prm.incident_row_sentiment()["positive"]
    cells = [c for c in prm.expected_cell_counts() if c["sentiment"] == "positive"]
    assert sum(c["expected_incident_rows"] for c in cells) == pytest.approx(inc_pos)
    for c in cells:
        assert c["expected"] == pytest.approx(
            c["expected_no_incident"] + c["expected_incident_rows"]
        )
        assert c["expected_incident_rows"] > 0
        assert c["required"] >= prm.poisson_ppf(0.99, c["expected"])
    # Every feedback row still has a cell: expected rows across cells equal all feedback.
    assert sum(c["expected"] for c in prm.expected_cell_counts()) == pytest.approx(t["feedback"])


# --------------------------------------------------------------------------- ADR-042/043


def test_incident_rates_by_sla_hold_both_targets():
    r = prm.incident_rates_by_sla()
    m = prm.expected_sla_miss_rate()
    rate = prm.PARAMS.incidents.request_incident_rate.value
    assert m * r["sla_missed"] + (1 - m) * r["sla_met"] == pytest.approx(rate)
    missed_incidents = m * r["sla_missed"]  # one missed_sla per missed request with incidents
    share = missed_incidents / (rate * prm.mean_incidents_per_request())
    assert share == pytest.approx(prm.PARAMS.incidents.incident_type_mix.value["missed_sla"])
    assert r["sla_missed"] == pytest.approx(0.25, abs=0.01)
    assert r["sla_met"] == pytest.approx(0.08, abs=0.01)


def test_pending_share_by_age():
    w = prm.PARAMS.billing.payment_pending_window_weeks.value
    top = prm.PARAMS.billing.payment_pending_share_at_end.value
    assert prm.pending_share_by_age(0) == top
    assert prm.pending_share_by_age(w / 2) == pytest.approx(top / 2)
    assert prm.pending_share_by_age(w) == 0 and prm.pending_share_by_age(100) == 0
    assert 0 < prm.expected_pending_share() < 0.08  # below the old flat 8%


def test_daily_seasonal_factors_match_the_per_day_rule():
    from datetime import date, timedelta

    days = [date(2024, 1, 1) + timedelta(days=i) for i in range(366)]
    raw = prm.daily_seasonal_factors(days, normalized=False)
    assert list(raw) == [prm._raw_daily_season(d, prm.PARAMS) for d in days]
    norm = prm.daily_seasonal_factors(days)
    assert list(norm) == pytest.approx([prm.seasonal_factor(d) for d in days])


def test_season_normalization_is_cached():
    prm._season_norm_cached.cache_clear()
    prm.expected_totals()
    info = prm._season_norm_cached.cache_info()
    assert info.misses == 1 and info.hits > 100


def test_moved_generation_constants_are_parameters():
    rows = {r[0] for r in prm.to_generation_parameters_rows()}
    for key in (
        "window.snapshot_offset_hours",
        "reference.inactive_stop_span",
        "reference.terminated_span",
        "reference.home_region_preference",
        "requests.booking_lead",
        "requests.cancellation_timing",
        "incidents.report_delay",
        "incidents.resolve_delay",
        "feedback.response_delay",
        "billing.archive_delay_hours",
        "incidents.incident_note_slots",
        "derived_incidents.incident_rate_given_sla",
        "derived_billing.expected_pending_share",
    ):
        assert key in rows, key
