"""evals/generated/generate_sets.py: filters, ranking and set selection, on synthetic items."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

GEN = Path(__file__).resolve().parents[2] / "evals" / "generated"
spec = importlib.util.spec_from_file_location("evalgen_generate_sets", GEN / "generate_sets.py")
gs = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gs
spec.loader.exec_module(gs)


def _intent(area="reporting", **kw):
    base = {
        "area": area,
        "measure": "incident_count",
        "period_stated": False,
        "period_text": None,
        "period_start": None,
        "period_end": None,
        "horizon_weeks": None,
        "region": None,
        "account_name": None,
        "technician_name": None,
        "breakdown": None,
        "work_type": None,
        "sentiment_label": None,
        "examples_requested": False,
    }
    return base | kw


def _raw(cat, n, route, intent, cands=()):
    return {
        "id": f"{cat[:3].upper()}-{n:02d}",
        "category": cat,
        "question": f"q {cat} {n}",
        "expected_route": route,
        "candidate_areas": list(cands),
        "intent": intent,
        "rationale": "r",
    }


def _entry(cat, n, area, eligible=True, **intent_kw):
    null_intent = cat in gs.schema.NULL_INTENT_CATEGORIES
    route = area if not null_intent else cat if cat != "near_miss" else "out_of_scope"
    raw = _raw(
        cat,
        n,
        route,
        None if null_intent else _intent(area, **intent_kw),
        ["reporting", "sentiment"] if cat in ("ambiguous", "multi_domain") else [],
    )
    item = gs.schema.Item.model_validate(raw)
    uid = f"{cat}/{raw['id']}"
    return {
        "uid": uid,
        "rank": gs.rank(f"item:{uid}"),
        "category": cat,
        "area": area,
        "brief_route": route,
        "system_route": route,
        "interp_eligible": eligible and not null_intent,
        "ineligible_reasons": [],
        "item": raw,
    }, item


def test_rank_is_deterministic_and_seeded():
    assert gs.rank("item:a/b") == gs.rank("item:a/b")
    assert gs.rank("item:a/b") != gs.rank("item:a/c")
    assert gs.SEED == 20261012


def test_label_problems():
    ok = _entry("clear_reporting", 1, "reporting")[1]
    assert gs.label_problem(ok, "clear_reporting") is None
    assert gs.label_problem(ok, "clear_sentiment") == "category_mismatch"
    wrong = gs.schema.Item.model_validate(_raw("clear_reporting", 2, "sentiment", _intent()))
    assert gs.label_problem(wrong, "clear_reporting") == "route_contradicts_category"
    mismatch = gs.schema.Item.model_validate(_raw("filtered", 3, "sentiment", _intent("reporting")))
    assert gs.label_problem(mismatch, "filtered") == "area_contradicts_route"
    plain = gs.schema.Item.model_validate(_raw("unsupported_in_area", 4, "reporting", _intent()))
    assert gs.label_problem(plain, "unsupported_in_area") == "no_unsupported_element"
    other = gs.schema.Item.model_validate(
        _raw("unsupported_in_area", 5, "reporting", _intent(measure="other"))
    )
    assert gs.label_problem(other, "unsupported_in_area") is None


def test_unsupported_elements():
    assert gs.has_unsupported_element(_intent(region="unsupported"))
    assert gs.has_unsupported_element(_intent("sentiment", breakdown="technician"))
    assert gs.has_unsupported_element(_intent("forecast", breakdown="region"))
    assert gs.has_unsupported_element(_intent(breakdown="month"))
    assert not gs.has_unsupported_element(_intent(breakdown="region"))


def test_duplicate_measures():
    assert gs.normalise_exact("How many, incidents?") == gs.normalise_exact("how  many incidents")
    a, b = (
        gs.shingles("how many incidents last month"),
        gs.shingles("how many incidents last month?"),
    )
    assert gs.jaccard(a, b) > gs.NEAR_DUP_THRESHOLD
    assert gs.jaccard(a, gs.shingles("forecast of weekly volume")) < gs.NEAR_DUP_THRESHOLD


def test_selection_is_disjoint_stratified_and_ordered():
    pool, n = [], 0
    spec_pool = {
        "clear_reporting": ("reporting", 12),
        "clear_sentiment": ("sentiment", 12),
        "clear_forecast": ("forecast", 12),
        "underspecified": ("reporting", 25),
        "ambiguous": ("reporting", 30),
        "multi_domain": ("reporting", 20),
        "out_of_scope": ("reporting", 10),
        "near_miss": ("reporting", 10),
        "technician": ("reporting", 10),
        "filtered": ("reporting", 20),
        "unsupported_in_area": ("reporting", 5),
    }
    for cat, (area, count) in spec_pool.items():
        for i in range(count):
            kw = {"measure": "incident_count"} if area == "reporting" else {}
            if area == "sentiment":
                kw = {"measure": "sentiment_mix"}
            if area == "forecast":
                kw = {"measure": "weekly_volume"}
            if cat == "filtered" and i % 5 == 0:
                kw["region"] = "unsupported"
            pool.append(_entry(cat, i, area, **kw)[0])
            n += 1
    pool.sort(key=lambda r: r["rank"])
    sets, reserve, notes = gs.select_sets(pool)
    uids = [r["uid"] for rows in sets.values() for r in rows] + [r["uid"] for r in reserve]
    assert len(uids) == len(set(uids)) == n
    assert {k: len(v) for k, v in sets.items()} == {
        "interp_fresh_v1": 24,
        "fr03_fresh_v2": 16,
        "routing_heldout_v1": 50,
        "parse_filters_v1": 12,
    }
    interp = sets["interp_fresh_v1"]
    assert sum(r["area"] == "reporting" for r in interp) == 10
    assert sum(r["area"] == "sentiment" for r in interp) == 7
    assert sum(r["area"] == "forecast" for r in interp) == 7
    assert sum(r["category"] == "filtered" for r in interp) >= 2
    assert sum(r["category"] == "technician" for r in interp) >= 2
    assert any(r["item"]["intent"]["region"] == "unsupported" for r in interp)
    assert all(r["interp_eligible"] for r in interp)
    routing = sets["routing_heldout_v1"]
    assert sum(r["category"] == "ambiguous" for r in routing) == 7
    assert sum(r["category"] == "clear_forecast" for r in routing) == 5
    assert notes["interp_unsupported_region_eligible"]
