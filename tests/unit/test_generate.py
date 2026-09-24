"""Offline tests for data/generator/generate.py and load.py (no database).

The corpus is a synthetic fixture with feedback_text.jsonl's schema. The full-scale
fixture holds exactly the per-cell counts parameters.py sizes the real corpus to
(Poisson q99 sizing, ADR-038), so the full-scale run doubles as a check that a corpus of
that size is enough.
"""

from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pytest
from sqlalchemy import String

_GEN = Path(__file__).resolve().parents[2] / "data" / "generator"
sys.path.insert(0, str(_GEN))
import db_models  # noqa: E402
import generate as gen  # noqa: E402
import load  # noqa: E402
import parameters as prm  # noqa: E402
import reference_data as ref  # noqa: E402

P = prm.PARAMS
SMALL_SCALE = 0.1
CHANNELS = list(P.feedback.channel_mix.value)
WINDOW_START = datetime.combine(P.window.start_monday.value, datetime.min.time(), tzinfo=UTC)
WINDOW_END = WINDOW_START + timedelta(weeks=P.window.n_weeks.value)

# --------------------------------------------------------------------------- fixtures


def corpus_cells() -> list[dict]:
    return prm.expected_cell_counts(P)


def cell_key(c: dict) -> str:
    return prm.corpus_cell_key(
        c["sentiment"], c["style"], c["context"], c["service_type"] or c["incident_type"]
    )


def write_corpus(path: Path, counts: dict[str, int]) -> Path:
    """A synthetic corpus in feedback_text.jsonl's schema (build_corpus.finalize)."""
    by_key = {cell_key(c): c for c in corpus_cells()}
    rng = np.random.default_rng(0)
    n = 0
    with open(path, "w", encoding="utf-8") as fh:
        for key in sorted(counts):
            c = by_key[key]
            for _ in range(counts[key]):
                n += 1
                row = {
                    "corpus_id": f"fb-{n:06d}",
                    "text": f"synthetic comment {n}",
                    "intended_sentiment": c["sentiment"],
                    "style": c["style"],
                    "hard_case_type": prm.HARD_CASE_BY_STYLE[c["style"]],
                    "cell": key,
                    "context": c["context"],
                    "service_type": c["service_type"],
                    "incident_type": c["incident_type"],
                    "focus": None,
                    "opening": None,
                    "channel": CHANNELS[int(rng.integers(len(CHANNELS)))],
                    "min_words": 1,
                    "max_words": 60,
                    "writer": "site contact",
                    "neutral_kind": None,
                    "judge_label": c["sentiment"],
                    "judge_disagreement": False,
                    "model": "fixture",
                    "judge_model": "fixture",
                }
                fh.write(json.dumps(row) + "\n")
    return path


@pytest.fixture(scope="session")
def full_corpus(tmp_path_factory) -> Path:
    counts = {cell_key(c): c["required"] for c in corpus_cells()}
    return write_corpus(tmp_path_factory.mktemp("corpus") / "full.jsonl", counts)


@pytest.fixture(scope="session")
def small_corpus(tmp_path_factory) -> Path:
    counts = {cell_key(c): math.ceil(c["required"] * SMALL_SCALE * 1.5) + 4 for c in corpus_cells()}
    return write_corpus(tmp_path_factory.mktemp("corpus") / "small.jsonl", counts)


@pytest.fixture(scope="session")
def full_state(full_corpus):
    """The generator after a full run: `.dataset` plus state for rules whose dates
    (account stops, technician changes) are not stored in any column."""
    g = gen._Generator(gen.load_corpus(full_corpus), gen.file_sha256(full_corpus), P, 1.0)
    g.dataset = g.run()
    return g


@pytest.fixture(scope="session")
def full(full_state) -> dict[str, list[dict]]:
    return full_state.dataset


@pytest.fixture(scope="session")
def small(small_corpus) -> dict[str, list[dict]]:
    return gen.generate(small_corpus, scale=SMALL_SCALE)


def by_id(rows, key):
    return {r[key]: r for r in rows}


def local(dt: datetime, lid: int, locations) -> datetime:
    return dt.astimezone(ZoneInfo(ref.STATE_TIMEZONE[locations[lid]["state"]]))


# --------------------------------------------------------------------------- determinism


def test_full_scale_is_deterministic(full, full_corpus):
    # scale=1.0 passed explicitly: the test argument must not change full-scale output.
    assert gen.generate(full_corpus, scale=1.0) == full


def test_reduced_scale_is_deterministic(small, small_corpus):
    assert gen.generate(small_corpus, scale=SMALL_SCALE) == small


def test_corpus_file_order_does_not_matter(small, small_corpus, tmp_path):
    lines = small_corpus.read_text(encoding="utf-8").splitlines()
    shuffled = tmp_path / "shuffled.jsonl"
    shuffled.write_text("\n".join(reversed(lines)) + "\n", encoding="utf-8")
    other = gen.generate(shuffled, scale=SMALL_SCALE)
    for t in gen.TABLES:
        if t != "generation_parameters":  # carries the corpus file's sha256
            assert other[t] == small[t], t


def test_stages_draw_only_from_their_own_seeds(full_state):
    assert set(full_state.rngs) <= set(prm.STAGES)
    for stage, rng in full_state.rngs.items():
        fresh = np.random.default_rng(prm.derive_seed(stage))
        assert rng.bit_generator.seed_seq.entropy == fresh.bit_generator.seed_seq.entropy


# --------------------------------------------------------------------------- schema shape


def test_rows_have_exactly_the_model_columns(full):
    for table in gen.TABLES:
        cols = {c.name for c in db_models.metadata.tables[table].columns}
        cols -= set(load.SERVER_DEFAULT_COLUMNS.get(table, ()))
        for row in full[table][:50]:
            assert set(row) == cols, table


def _vocab_checks() -> dict[tuple[str, str], set[str]]:
    out = {}
    for table in db_models.metadata.tables.values():
        for ck in table.constraints:
            m = re.fullmatch(r"(\w+) IN \((.*)\)", str(getattr(ck, "sqltext", "")))
            if m:
                out[(table.name, m.group(1))] = set(re.findall(r"'([^']*)'", m.group(2)))
    return out


def test_not_null_lengths_and_vocabularies(full):
    vocab = _vocab_checks()
    assert len(vocab) >= 22
    for table in gen.TABLES:
        t = db_models.metadata.tables[table]
        for col in t.columns:
            if col.name in load.SERVER_DEFAULT_COLUMNS.get(table, ()):
                continue
            values = [r[col.name] for r in full[table]]
            if not col.nullable:
                assert all(v is not None for v in values), f"{table}.{col.name} null"
            if isinstance(col.type, String) and col.type.length:
                assert all(v is None or len(v) <= col.type.length for v in values), col
            allowed = vocab.get((table, col.name))
            if allowed:
                assert {v for v in values if v is not None} <= allowed, f"{table}.{col.name}"


def test_surrogate_keys_are_explicit_and_sequential(full):
    for table, key in [
        ("accounts", "account_id"),
        ("contacts", "contact_id"),
        ("locations", "location_id"),
        ("technicians", "technician_id"),
        ("internal_users", "user_id"),
        ("service_requests", "request_id"),
        ("incidents", "incident_id"),
        ("service_feedback", "feedback_id"),
    ]:
        assert [r[key] for r in full[table]] == list(range(1, len(full[table]) + 1)), table


def test_unique_constraints(full):
    for table, cols in [
        ("accounts", ("account_code",)),
        ("service_requests", ("reservation_number",)),
        ("service_feedback", ("request_id",)),
        ("sentiment_labels", ("corpus_id",)),
        ("technician_skills", ("technician_id", "skill")),
        ("generation_parameters", ("param_key",)),
        ("archived_requests", ("request_id",)),
    ]:
        keys = [tuple(r[c] for c in cols) for r in full[table]]
        assert len(keys) == len(set(keys)), (table, cols)


def test_every_foreign_key_resolves(full):
    for table in gen.TABLES:
        for fk in db_models.metadata.tables[table].foreign_keys:
            target = {r[fk.column.name] for r in full[fk.column.table.name]}
            col = fk.parent.name
            missing = [r[col] for r in full[table] if r[col] is not None and r[col] not in target]
            assert not missing, f"{table}.{col} -> {fk.column}"


# --------------------------------------------------------------------------- §8 invariants


@pytest.mark.parametrize("which", ["full", "small"])
def test_validate_dataset_clean(which, request):
    assert gen.validate_dataset(request.getfixturevalue(which)) == []


def test_validate_dataset_catches_violations(small):
    broken = {t: [dict(r) for r in rows] for t, rows in small.items()}
    broken["service_requests"][0]["cancelled_at"] = None
    broken["service_requests"][0]["request_status"] = "cancelled"
    broken["service_feedback"][0]["rating"] = 6
    problems = gen.validate_dataset(broken)
    assert any("cancelled_at" in p for p in problems)
    assert any("rating" in p for p in problems)


def test_check_constraints_row_by_row(full):
    for r in full["service_requests"]:
        assert (r["cancelled_at"] is not None) == (r["request_status"] == "cancelled")
        assert r["cancellation_reason"] is None or r["request_status"] == "cancelled"
        assert r["equipment_unit_count"] > 0 and r["sla_window_minutes"] > 0
        assert r["parent_request_id"] != r["request_id"]
    for a in full["archived_requests"]:
        assert a["labor_charge"] >= 0 and a["parts_charge"] >= 0
        assert 0 <= a["surcharge_rate"] <= 1
        for c in ("labor_charge", "parts_charge"):
            assert a[c] == a[c].quantize(Decimal("0.01"))
    for i in full["incidents"]:
        assert i["credit_issued_amount"] is None or i["credit_issued_amount"] >= 0
    for f in full["service_feedback"]:
        assert f["rating"] is None or 1 <= f["rating"] <= 5
        assert f["feedback_text"]


def test_qa_invariants(full):
    reqs = by_id(full["service_requests"], "request_id")
    arch = by_id(full["archived_requests"], "request_id")
    completed = {k for k, r in reqs.items() if r["request_status"] == "completed"}
    assert set(arch) == completed
    assert not any(reqs[k]["request_status"] == "cancelled" for k in arch)
    for k, a in arch.items():
        assert a["completed_at"] >= reqs[k]["scheduled_datetime"]
        assert a["technician_id"] == reqs[k]["assigned_technician_id"]
    credits = defaultdict(Decimal)
    for i in full["incidents"]:
        credits[i["request_id"]] += i["credit_issued_amount"] or Decimal(0)
    for k, c in credits.items():
        a = arch[k]
        assert c <= gen.total_invoice(a["labor_charge"], a["parts_charge"], a["surcharge_rate"])
    fb_ids = {f["feedback_id"] for f in full["service_feedback"]}
    assert {x["feedback_id"] for x in full["sentiment_labels"]} == fb_ids


# --------------------------------------------------------------------------- counts


def test_full_scale_counts_within_dictionary_ranges(full):
    n = gen.row_counts(full)
    completed = n["archived_requests"]
    assert 40 <= n["accounts"] <= 60
    assert 150 <= n["locations"] <= 250
    assert 150 <= n["contacts"] <= 300
    assert 25 <= n["technicians"] <= 40
    assert 15_000 <= n["service_requests"] <= 25_000
    assert 0.08 <= n["incidents"] / completed <= 0.12
    assert 0.35 <= n["service_feedback"] / completed <= 0.50
    exp = prm.expected_totals(P)
    assert n["service_requests"] == pytest.approx(exp["requests"], rel=0.04)
    assert completed == pytest.approx(exp["completed"], rel=0.04)
    assert n["incidents"] == pytest.approx(exp["incidents"], rel=0.08)
    assert n["service_feedback"] == pytest.approx(exp["feedback"], rel=0.05)


def test_reduced_scale_counts(small, full):
    n = gen.row_counts(small)
    exp = prm.expected_totals(P)
    assert n["service_requests"] == pytest.approx(exp["requests"] * SMALL_SCALE, rel=0.10)
    assert n["archived_requests"] == pytest.approx(exp["completed"] * SMALL_SCALE, rel=0.10)
    assert n["service_feedback"] == pytest.approx(exp["feedback"] * SMALL_SCALE, rel=0.15)
    # Scale touches volume only; reference tables are the full-scale ones.
    for t in ("accounts", "contacts", "locations", "technicians", "internal_users"):
        assert small[t] == full[t]


def test_reference_counts_follow_parameters(full):
    r = P.reference
    assert Counter(a["contract_tier"] for a in full["accounts"]) == r.contract_tier_counts.value
    assert Counter(a["account_status"] for a in full["accounts"]) == r.account_status_counts.value
    assert (
        Counter(t["technician_status"] for t in full["technicians"])
        == r.technician_status_counts.value
    )
    assert Counter(u["user_role"] for u in full["internal_users"]) == (
        r.internal_user_role_counts.value
    )
    per_tech = Counter(s["technician_id"] for s in full["technician_skills"])
    lo, hi = r.skills_per_technician.value
    assert set(per_tech) == {t["technician_id"] for t in full["technicians"]}
    assert all(lo <= k <= hi for k in per_tech.values())


def test_prospects_have_no_requests(full):
    prospects = {a["account_id"] for a in full["accounts"] if a["account_status"] == "prospect"}
    assert prospects
    assert not any(r["account_id"] in prospects for r in full["service_requests"])


# --------------------------------------------------------------------------- lifecycle


def test_cancellations(full):
    reqs = full["service_requests"]
    cancelled = [r for r in reqs if r["request_status"] == "cancelled"]
    assert len(cancelled) / len(reqs) == pytest.approx(P.requests.cancel_rate.value, abs=0.01)
    reasons = Counter(r["cancellation_reason"] for r in cancelled)
    for reason, share in P.requests.cancellation_reason_mix.value.items():
        assert reasons[reason] / len(cancelled) == pytest.approx(share, abs=0.03)
    for r in cancelled:
        assert r["cancellation_reason"] is not None
        assert r["cancelled_at"] >= r["created_at"]
        if r["cancellation_reason"] == "client_no_show":
            assert r["assigned_technician_id"] is not None and r["dispatched_at"] is not None
        else:
            assert r["assigned_technician_id"] is None and r["dispatched_at"] is None


def test_non_terminal_statuses_only_in_final_two_weeks(full):
    cutoff = WINDOW_END - timedelta(weeks=P.window.open_status_weeks.value)
    open_ = [
        r for r in full["service_requests"] if r["request_status"] not in ("completed", "cancelled")
    ]
    assert open_
    assert all(r["scheduled_datetime"] >= cutoff for r in open_)
    for r in open_:
        dispatched = r["request_status"] != "open"
        assert (r["dispatched_at"] is not None) == dispatched
        assert (r["assigned_technician_id"] is not None) == dispatched


def test_every_request_is_in_the_window_and_timestamps_ordered(full):
    as_of = WINDOW_END + gen.AS_OF_AFTER_WINDOW_END
    for r in full["service_requests"]:
        assert WINDOW_START <= r["scheduled_datetime"] < WINDOW_END
        assert r["created_at"] <= r["scheduled_datetime"]
        assert r["created_at"] <= r["updated_at"] <= as_of
        if r["dispatched_at"]:
            assert r["dispatched_at"] >= r["scheduled_datetime"]
    for a in full["archived_requests"]:
        assert a["completed_at"] <= a["archived_at"] <= a["updated_at"] <= as_of
    for i in full["incidents"]:
        assert i["reported_at"] <= i["created_at"] <= i["updated_at"] <= as_of
        assert i["resolved_at"] is None or i["resolved_at"] >= i["created_at"]
    for f in full["service_feedback"]:
        assert f["submitted_at"] <= as_of


def test_sla_snapshot_and_completion_model(full):
    tiers = {a["account_id"]: a["contract_tier"] for a in full["accounts"]}
    matrix = P.requests.sla_window_minutes.value
    for r in full["service_requests"]:
        assert r["sla_window_minutes"] == matrix[tiers[r["account_id"]]][r["priority_tier"]]
    reqs = by_id(full["service_requests"], "request_id")
    met = defaultdict(list)
    for a in full["archived_requests"]:
        r = reqs[a["request_id"]]
        window = timedelta(minutes=r["sla_window_minutes"])
        met[r["priority_tier"]].append(a["completed_at"] <= r["dispatched_at"] + window)
    for pr, target in P.requests.sla_met_target.value.items():
        assert np.mean(met[pr]) == pytest.approx(target, abs=0.03), pr


def test_inactive_accounts_stop_partway(full_state, full):
    reqs = full["service_requests"]
    for aid, acc in full_state.accounts.items():
        if acc["row"]["account_status"] != "inactive":
            continue
        stop = acc["stop_at"]
        mine = [r for r in reqs if r["account_id"] == aid]
        assert mine, aid
        # Nothing scheduled from the stop week on (local Sunday evenings can spill a few
        # hours past the UTC week boundary).
        assert max(r["scheduled_datetime"] for r in mine) < stop + timedelta(hours=12)
        lo, hi = gen.INACTIVE_STOP_SPAN
        assert WINDOW_START + (WINDOW_END - WINDOW_START) * lo <= stop
        assert stop <= WINDOW_START + (WINDOW_END - WINDOW_START) * hi


def test_technicians_not_assigned_after_status_change(full_state, full):
    until = {t["id"]: t["until"] for t in full_state.technicians}
    status = {t["technician_id"]: t["technician_status"] for t in full["technicians"]}
    changed = {k for k, v in status.items() if v != "active"}
    assert changed and all(until[k] is not None for k in changed)
    assert all(until[k] is None for k in status if k not in changed)
    for r in full["service_requests"]:
        t = r["assigned_technician_id"]
        if t in changed:
            assert r["dispatched_at"] < until[t]


def test_region_shares(full):
    shares = P.regions.share.value
    region_of_state = {s: g for g, states in P.regions.states.value.items() for s in states}
    loc_region = {loc["location_id"]: region_of_state[loc["state"]] for loc in full["locations"]}
    reqs = [r for r in full["service_requests"] if r["parent_request_id"] is None]
    vol = Counter(loc_region[r["location_id"]] for r in reqs)
    sites = Counter(loc_region.values())
    for g, s in shares.items():
        assert vol[g] / len(reqs) == pytest.approx(s, abs=0.03), g
        assert sites[g] / len(loc_region) == pytest.approx(s, abs=0.03), g


# --------------------------------------------------------------------------- anomalies


def _weekly(rows, pred=lambda r: True) -> Counter:
    return Counter(
        (r["scheduled_datetime"] - WINDOW_START) // timedelta(weeks=1) for r in rows if pred(r)
    )


def test_account_volume_anomaly(full_state, full):
    a = P.anomalies.volume_drop.value
    top = full_state.top_account
    weeks = _weekly(full["service_requests"], lambda r: r["account_id"] == top)
    total = len([r for r in full["service_requests"] if r["account_id"] == top])
    assert total / len(full["service_requests"]) == pytest.approx(
        P.reference.largest_account_volume_share.value, abs=0.015
    )
    dip = [weeks[w] for w in range(a["start_week"], a["start_week"] + a["n_weeks"])]
    around = [weeks[w] for w in range(a["start_week"] - 6, a["start_week"])]
    assert max(dip) <= 0.3 * np.mean(around)


def test_regional_volume_anomaly(full):
    a = P.anomalies.regional_drop.value
    start = prm.week_index(a["start"], P)
    region_states = set(P.regions.states.value[a["region"]])
    in_region = {loc["location_id"] for loc in full["locations"] if loc["state"] in region_states}
    weeks = _weekly(
        full["service_requests"],
        lambda r: r["location_id"] in in_region and r["parent_request_id"] is None,
    )
    dip = [weeks[w] for w in range(start, start + a["n_weeks"])]
    around = [weeks[w] for w in range(start - 6, start)]
    assert max(dip) <= 0.3 * np.mean(around)


def test_billing_surcharge_anomaly(full):
    a = P.anomalies.billing_surcharge.value
    weeks = range(a["start_week"], a["start_week"] + a["n_weeks"])
    rates = P.billing.surcharge_rate_by_method.value
    hit = 0
    for r in full["archived_requests"]:
        week = (r["completed_at"].date() - P.window.start_monday.value).days // 7
        method = r["payment_method_final"]
        expected = rates[method]
        if method == a["payment_method"] and week in weeks:
            expected = a["surcharge_rate"]
            hit += 1
        assert r["surcharge_rate"] == Decimal(repr(expected)).quantize(Decimal("0.0001"))
    assert hit > 50


def test_billing_distributions(full):
    arch = full["archived_requests"]
    status = Counter(a["payment_status"] for a in arch)
    for s, share in P.billing.payment_status_mix.value.items():
        assert status[s] / len(arch) == pytest.approx(share, abs=0.01), s
    reqs = by_id(full["service_requests"], "request_id")
    changed = np.mean(
        [a["payment_method_final"] != reqs[a["request_id"]]["payment_method"] for a in arch]
    )
    assert changed == pytest.approx(P.billing.payment_method_change_rate.value, abs=0.01)
    for a in arch:
        ref_ = a["payment_reference"]
        assert (ref_ is None) == (a["payment_status"] == "pending")
        # Last-4 or a transaction reference, never a card-length number (§9).
        assert ref_ is None or not re.search(r"\d{11,}", ref_)


# --------------------------------------------------------------------------- coherence (ADR-038)


def test_missed_sla_incidents_only_on_sla_misses(full):
    reqs = by_id(full["service_requests"], "request_id")
    arch = by_id(full["archived_requests"], "request_id")
    missed = [i for i in full["incidents"] if i["incident_type"] == "missed_sla"]
    assert missed
    for i in missed:
        r, a = reqs[i["request_id"]], arch[i["request_id"]]
        assert a["completed_at"] > r["dispatched_at"] + timedelta(minutes=r["sla_window_minutes"])
    per_req = Counter(i["request_id"] for i in missed)
    assert max(per_req.values()) == 1
    share = len(missed) / len(full["incidents"])
    assert share == pytest.approx(P.incidents.incident_type_mix.value["missed_sla"], abs=0.03)


def test_incident_rates_and_mixes(full):
    incs = full["incidents"]
    completed = len(full["archived_requests"])
    with_any = len({i["request_id"] for i in incs})
    assert with_any / completed == pytest.approx(P.incidents.request_incident_rate.value, abs=0.01)
    types = Counter(i["incident_type"] for i in incs)
    for t, share in P.incidents.incident_type_mix.value.items():
        assert types[t] / len(incs) == pytest.approx(share, abs=0.03), t
    sev = Counter(i["severity"] for i in incs)
    for s, share in P.incidents.severity_mix.value.items():
        assert sev[s] / len(incs) == pytest.approx(share, abs=0.03), s
    for i in incs:
        assert i["incident_status"] in ("open", "investigating", "resolved", "closed")
        assert (i["root_cause_category"] is None) == (i["incident_status"] == "open")
        if P.incidents.attribution_prob_by_type.value[i["incident_type"]] == 0:
            assert i["attributed_technician_id"] is None


def test_exactly_one_child_per_repeat_visit_request(full):
    reqs = by_id(full["service_requests"], "request_id")
    arch = by_id(full["archived_requests"], "request_id")
    locs = by_id(full["locations"], "location_id")
    repeat_parents = {
        i["request_id"] for i in full["incidents"] if i["incident_type"] == "repeat_visit_required"
    }
    assert repeat_parents
    per_req = Counter(
        i["request_id"] for i in full["incidents"] if i["incident_type"] == "repeat_visit_required"
    )
    assert max(per_req.values()) == 1  # so "per incident" and "per request" coincide
    children = defaultdict(list)
    for r in full["service_requests"]:
        if r["parent_request_id"] is not None:
            children[r["parent_request_id"]].append(r)
    assert set(children) == repeat_parents
    lo, hi = P.requests.child_schedule_days.value
    for pid, kids in children.items():
        assert len(kids) == 1
        child, parent = kids[0], reqs[pid]
        for c in ("account_id", "location_id", "service_type", "contact_id"):
            assert child[c] == parent[c]
        done = local(arch[pid]["completed_at"], parent["location_id"], locs).date()
        sched = local(child["scheduled_datetime"], child["location_id"], locs).date()
        assert lo <= (sched - done).days <= hi
        assert child["created_at"] >= arch[pid]["completed_at"]


def test_feedback_links_most_severe_then_earliest(full):
    rank = {"low": 0, "medium": 1, "high": 2}
    by_req = defaultdict(list)
    for i in full["incidents"]:
        by_req[i["request_id"]].append(i)
    for f in full["service_feedback"]:
        incs = by_req.get(f["request_id"], [])
        if not incs:
            assert f["incident_id"] is None
            continue
        best = min(incs, key=lambda i: (-rank[i["severity"]], i["reported_at"], i["incident_id"]))
        assert f["incident_id"] == best["incident_id"]
    tied = [v for v in by_req.values() if len(v) > 1]
    assert tied, "fixture has no multi-incident requests to exercise the tie rule"


def test_incident_status_depends_on_age(full):
    window = P.incidents.incident_active_window_weeks.value
    edge = WINDOW_END - timedelta(weeks=window)
    active = [i for i in full["incidents"] if i["incident_status"] in ("open", "investigating")]
    assert active
    for i in full["incidents"]:
        if i["incident_status"] in ("open", "investigating"):
            assert i["resolved_at"] is None
            assert i["reported_at"] > edge
        else:
            assert i["resolved_at"] is not None
        if i["reported_at"] <= edge:
            assert i["incident_status"] in ("resolved", "closed")


def test_feedback_only_on_completed_requests_with_response_rates(full):
    reqs = by_id(full["service_requests"], "request_id")
    assert all(
        reqs[f["request_id"]]["request_status"] == "completed" for f in full["service_feedback"]
    )
    inc_reqs = {i["request_id"] for i in full["incidents"]}
    completed = [a["request_id"] for a in full["archived_requests"]]
    fb = {f["request_id"] for f in full["service_feedback"]}
    with_inc = [k for k in completed if k in inc_reqs]
    without = [k for k in completed if k not in inc_reqs]
    fb_rate = P.feedback
    assert np.mean([k in fb for k in with_inc]) == pytest.approx(
        fb_rate.response_rate_incident.value, abs=0.04
    )
    assert np.mean([k in fb for k in without]) == pytest.approx(
        fb_rate.response_rate_no_incident.value, abs=0.02
    )
    for f in full["service_feedback"]:
        assert f["submitted_by_contact_id"] == reqs[f["request_id"]]["contact_id"]


# --------------------------------------------------------------------------- sentiment and corpus


def test_class_mix_matches_target(full):
    labels = full["sentiment_labels"]
    mix = Counter(x["true_sentiment"] for x in labels)
    for se, share in P.sentiment.target_mix.value.items():
        assert mix[se] / len(labels) == pytest.approx(share, abs=0.015), se
    hard = sum(x["hard_case_type"] != "none" for x in labels) / len(labels)
    assert hard == pytest.approx(0.15, abs=0.01)
    pairs = Counter((x["true_sentiment"], x["hard_case_type"]) for x in labels)
    for (se, st), share in P.sentiment.hard_case_shares.value.items():
        assert pairs[(se, prm.HARD_CASE_BY_STYLE[st])] / len(labels) == pytest.approx(
            share, abs=0.01
        )


def test_cell_rules_and_labels(full, full_corpus):
    corpus = {r["corpus_id"]: r for rs in gen.load_corpus(full_corpus).values() for r in rs}
    fb = by_id(full["service_feedback"], "feedback_id")
    reqs = by_id(full["service_requests"], "request_id")
    incs = by_id(full["incidents"], "incident_id")
    level = P.corpus.incident_context_by_severity.value
    for lab in full["sentiment_labels"]:
        f = fb[lab["feedback_id"]]
        rec = corpus[lab["corpus_id"]]
        se, hard = lab["true_sentiment"], lab["hard_case_type"]
        assert lab["label_confidence"] is None
        assert f["feedback_text"] == rec["text"]
        assert f["response_channel"] == rec["channel"]
        assert rec["intended_sentiment"] == se and rec["hard_case_type"] == hard
        inc = incs.get(f["incident_id"])
        ctx = level[inc["severity"]] if inc else "none"
        style = {v: k for k, v in prm.HARD_CASE_BY_STYLE.items()}[hard]
        assert prm.is_allowed(se, style, ctx)
        expected_cell = prm.corpus_cell_for_row(
            se,
            style,
            reqs[f["request_id"]]["service_type"],
            ctx,
            inc["incident_type"] if inc else None,
        )
        assert rec["cell"] == expected_cell
    assert not any(
        lab["true_sentiment"] == "neutral" and fb[lab["feedback_id"]]["incident_id"]
        for lab in full["sentiment_labels"]
    )


def test_ratings(full):
    labels = by_id(full["sentiment_labels"], "feedback_id")
    fb = full["service_feedback"]
    nulls = np.mean([f["rating"] is None for f in fb])
    assert nulls == pytest.approx(P.feedback.rating_null_rate.value, abs=0.015)
    table = P.sentiment.rating_given_sentiment.value
    for f in fb:
        if f["rating"] is not None:
            assert f["rating"] in table[labels[f["feedback_id"]]["true_sentiment"]]


def test_corpus_exhaustion_raises(small_corpus, tmp_path):
    """A cell left with one comment runs out; nothing is reused or borrowed."""
    victim = "neutral|plain|none|repair"
    kept, seen = [], 0
    for line in small_corpus.read_text(encoding="utf-8").splitlines():
        if json.loads(line)["cell"] == victim:
            seen += 1
            if seen > 1:
                continue
        kept.append(line)
    short = tmp_path / "short.jsonl"
    short.write_text("\n".join(kept) + "\n", encoding="utf-8")
    with pytest.raises(gen.CorpusExhaustedError, match=re.escape(victim)):
        gen.generate(short, scale=SMALL_SCALE)


def test_missing_cell_raises(small_corpus, tmp_path):
    victim = "negative|sarcastic|none|install"
    lines = [
        ln
        for ln in small_corpus.read_text(encoding="utf-8").splitlines()
        if json.loads(ln)["cell"] != victim
    ]
    path = tmp_path / "missing.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(gen.CorpusExhaustedError, match=re.escape(victim)):
        gen.generate(path, scale=SMALL_SCALE)


@pytest.mark.parametrize(
    ("edit", "match"),
    [
        (lambda r: r.update(cell="mixed|plain|none|repair"), "does not match"),
        (lambda r: r.update(style="sarcastic", intended_sentiment="positive"), "not a corpus cell"),
        (lambda r: r.update(hard_case_type="sarcastic"), "hard_case_type"),
        (lambda r: r.update(channel="fax"), "channel"),
        (lambda r: r.pop("text"), "missing"),
    ],
)
def test_load_corpus_rejects_bad_records(small_corpus, tmp_path, edit, match):
    lines = small_corpus.read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[0])
    edit(rec)
    path = tmp_path / "bad.jsonl"
    path.write_text(json.dumps(rec) + "\n", encoding="utf-8")
    with pytest.raises(gen.CorpusError, match=match):
        gen.load_corpus(path)


def test_load_corpus_rejects_duplicate_ids(small_corpus, tmp_path):
    line = small_corpus.read_text(encoding="utf-8").splitlines()[0]
    path = tmp_path / "dup.jsonl"
    path.write_text(line + "\n" + line + "\n", encoding="utf-8")
    with pytest.raises(gen.CorpusError, match="duplicate"):
        gen.load_corpus(path)


# --------------------------------------------------------------------------- timestamps


def test_all_timestamps_are_utc_aware(full):
    for table in gen.TABLES:
        for row in full[table]:
            for v in row.values():
                if isinstance(v, datetime):
                    assert v.tzinfo is not None and v.utcoffset() == timedelta(0)


def test_local_hour_of_day_matches_weights(full):
    locs = by_id(full["locations"], "location_id")
    hours, minutes = Counter(), Counter()
    reqs = full["service_requests"]
    for r in reqs:
        t = local(r["scheduled_datetime"], r["location_id"], locs)
        hours[t.hour] += 1
        minutes[t.minute] += 1
    weights = P.volume.hour_of_day_weights.value
    assert set(hours) <= set(weights)
    for h, w in weights.items():
        assert hours[h] / len(reqs) == pytest.approx(w, abs=0.01), h
    assert set(minutes) <= set(gen.SCHEDULE_MINUTES)
    # Not hour-of-day in UTC: the West's share alone shifts that by hours.
    utc_hours = Counter(r["scheduled_datetime"].hour for r in reqs)
    assert utc_hours != hours


def test_weekday_concentration(full):
    locs = by_id(full["locations"], "location_id")
    days = Counter(
        local(r["scheduled_datetime"], r["location_id"], locs).weekday()
        for r in full["service_requests"]
        if r["parent_request_id"] is None
    )
    n = sum(days.values())
    for i, (_, w) in enumerate(P.volume.day_of_week_weights.value.items()):
        assert days[i] / n == pytest.approx(w, abs=0.015), i


def test_every_state_has_a_timezone_and_city():
    states = {s for sts in P.regions.states.value.values() for s in sts}
    assert len(states) == 51
    assert set(ref.STATE_TIMEZONE) == states == set(ref.STATE_CITY)
    for tz in ref.STATE_TIMEZONE.values():
        ZoneInfo(tz)


# --------------------------------------------------------------------------- PII shape, parameters


def test_contact_and_name_formats(full):
    for c in full["contacts"]:
        assert re.fullmatch(r"\d{3}-555-01\d{2}", c["phone"])
        assert c["email"].endswith("@example.com")
        assert c["first_name"] in ref.FIRST_NAMES and c["last_name"] in ref.LAST_NAMES
    names = [t["full_name"] for t in full["technicians"]] + [
        u["full_name"] for u in full["internal_users"]
    ]
    assert len(names) == len(set(names))


def test_generation_parameters_rows(full, full_corpus):
    rows = full["generation_parameters"]
    expected = prm.to_generation_parameters_rows(P)
    assert [
        (r["param_key"], r["param_value"], r["param_group"], r["notes"]) for r in rows[:-1]
    ] == [tuple(e) for e in expected]
    by_key = by_id(rows, "param_key")
    assert by_key["seed.master_seed"]["param_value"] == prm.MASTER_SEED
    assert by_key["seed.corpus_sha256"]["param_value"] == gen.file_sha256(full_corpus)
    json.dumps([r["param_value"] for r in rows])  # JSONB-safe


# --------------------------------------------------------------------------- load.py (offline)


def test_load_dry_run(full_corpus, capsys):
    assert load.main(["--corpus", str(full_corpus), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "service_requests:" in out and "invariants hold" in out
    assert "synthetic comment" not in out  # counts only, never rows (ADR-030)


def test_load_dry_run_reports_exhaustion(tmp_path, small_corpus, capsys):
    lines = small_corpus.read_text(encoding="utf-8").splitlines()[:50]
    path = tmp_path / "tiny.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert load.main(["--corpus", str(path), "--dry-run"]) == 2
    assert "ran out" in capsys.readouterr().err


def test_insert_statements_override_identity_only_where_needed():
    for table in gen.TABLES:
        cols = [c.name for c in db_models.metadata.tables[table].columns]
        stmt = load.insert_statement(table, cols).as_string(None)
        identity = any(c.identity is not None for c in db_models.metadata.tables[table].columns)
        assert ("OVERRIDING SYSTEM VALUE" in stmt) == identity, table
        assert (table in load.IDENTITY_TABLES) == identity
