"""Validate the loaded dataset against its own recorded ground truth (R-07).

    python data/generator/validate.py              # against local Postgres
    python data/generator/validate.py --offline    # against a fresh generate.py run (no DB)

The check functions are pure: they take in-memory tables ({table: [row dicts]}) and a
`Truth` built from `generation_parameters` rows, so they run against the database and,
offline, against generate.py output in unit tests.

Database access uses agent roles only, never a superuser (ADR-023):
  - app_forecast reads the weekly volume series from exactly request_id,
    scheduled_datetime and service_type -- showing its ADR-035 grant is sufficient;
  - app_qa reads everything else, including generation_parameters.
Truth values come from generation_parameters, not from parameters.py: the database alone
describes its own ground truth. (A unit test confirms the two agree.)

Tolerances are fixed in CHECK_TOLERANCES below and were set before any result was seen.
Output: data/generator/validation/<date>/report.json, PNG plots, spot_check.csv.
Exits non-zero if any hard check fails. Prints a summary table only, never comment text.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT_ROOT = HERE / "validation"
YEAR_WEEKS = 365.25 / 7
FOURIER_K = 3
SPOT_CHECK_SEED = 20260925
SPOT_CHECK_ROWS = 30
ALPHA = 0.01
CENT = Decimal("0.01")

#: Fixed before any result was seen (validate.py task, 2026-09-25). Do not tune.
CHECK_TOLERANCES = {
    "sentiment_pp": 0.015,
    "hard_case_share": (0.13, 0.17),
    "incident_request_rate": (0.08, 0.12),
    "missed_sla_share": (0.20, 0.30),
    "feedback_per_completed": (0.35, 0.50),
    "cancel_rate": (0.08, 0.12),
    "sla_met_pp": 0.03,
    "service_mix_pp": 0.02,
    "disputed_share": (0.03, 0.05),
    "pending_pp": 0.01,
    "trend_growth_pp": 0.03,
    "season_range_pp": 0.06,
    "residual_sd": (0.08, 0.13),
    "regional_z_min": 3.0,
    "account_drop_min": 0.80,
    "alpha": ALPHA,
}


# --------------------------------------------------------------------------- results


@dataclass
class Check:
    id: str
    group: str
    name: str
    value: object
    tolerance: str
    passed: bool
    hard: bool = True
    detail: dict = field(default_factory=dict)

    def __post_init__(self):
        self.passed = bool(self.passed)

    @property
    def status(self) -> str:
        if self.passed:
            return "PASS"
        return "FAIL" if self.hard else "NOTE"


def _band(x: float, lo: float, hi: float) -> bool:
    return lo <= x <= hi


# --------------------------------------------------------------------------- truth


class Truth:
    """Ground truth read from generation_parameters rows (param_key -> param_value)."""

    def __init__(self, gp_rows: list[dict]):
        self.v = {r["param_key"]: r["param_value"] for r in gp_rows}

    def __getitem__(self, key: str):
        if key not in self.v:
            raise KeyError(f"generation_parameters has no {key!r}")
        return self.v[key]

    @property
    def start(self) -> date:
        return date.fromisoformat(self["window.start_monday"])

    @property
    def n_weeks(self) -> int:
        return int(self["window.n_weeks"])

    @property
    def holdout_start(self) -> int:
        return self.n_weeks - int(self["window.holdout_weeks"])

    @property
    def window_end(self) -> datetime:
        return datetime.combine(self.start, time(), tzinfo=UTC) + timedelta(weeks=self.n_weeks)

    @property
    def as_of(self) -> datetime:
        return self.window_end + timedelta(hours=float(self["window.snapshot_offset_hours"]))

    def week_of(self, t: datetime) -> int:
        return (t.astimezone(UTC).date() - self.start).days // 7

    def anomaly_weeks(self) -> dict[str, list[int]]:
        acct = self["anomalies.volume_drop"]
        reg = self["anomalies.regional_drop"]
        bill = self["anomalies.billing_surcharge"]
        reg_start = (date.fromisoformat(reg["start"]) - self.start).days // 7
        return {
            "account": list(range(acct["start_week"], acct["start_week"] + acct["n_weeks"])),
            "regional": list(range(reg_start, reg_start + reg["n_weeks"])),
            "billing": list(range(bill["start_week"], bill["start_week"] + bill["n_weeks"])),
        }

    def allowed_hard_types(self) -> dict[str, set[str]]:
        """Hard-case types each sentiment may carry (ADR-036), from the stored style mix."""
        by_style = {"plain": "none", "implicit": "implicit", "sarcastic": "sarcastic"}
        styles = self["derived_sentiment.style_given_sentiment"]
        return {se: {by_style[st] for st, p in d.items() if p > 0} for se, d in styles.items()}

    def raw_daily_season(self, d: date) -> float:
        trough = self["volume.late_december_trough"]
        monthly = self["volume.seasonality_monthly_raw"]
        if (d.month == 12 and d.day >= int(trough["from"][3:])) or (d.month == 1 and d.day == 1):
            return float(trough["factor"])
        return float(monthly[str(d.month)])


# --------------------------------------------------------------------------- helpers


def total_invoice(a: dict) -> Decimal:
    return ((a["labor_charge"] + a["parts_charge"]) * (1 + a["surcharge_rate"])).quantize(
        CENT, ROUND_HALF_UP
    )


def sla_met(req: dict, arch: dict) -> bool:
    return arch["completed_at"] <= req["dispatched_at"] + timedelta(
        minutes=req["sla_window_minutes"]
    )


class Index:
    """Lookups shared by several checks."""

    def __init__(self, t: Mapping[str, list[dict]]):
        self.req = {r["request_id"]: r for r in t["service_requests"]}
        self.arch = {a["request_id"]: a for a in t["archived_requests"]}
        self.inc = {i["incident_id"]: i for i in t["incidents"]}
        self.inc_by_req: dict[int, list[dict]] = defaultdict(list)
        for i in t["incidents"]:
            self.inc_by_req[i["request_id"]].append(i)
        self.label = {x["feedback_id"]: x for x in t["sentiment_labels"]}
        self.completed = [r for r in t["service_requests"] if r["request_status"] == "completed"]


# --------------------------------------------------------------------------- A. invariants


def check_invariants(t: Mapping[str, list[dict]], truth: Truth) -> list[Check]:
    """§8 QA invariants and ADR-038/043 coherence rules: violation counts that must be 0."""
    ix = Index(t)
    sr, ar, inc, fb = (
        t["service_requests"],
        t["archived_requests"],
        t["incidents"],
        t["service_feedback"],
    )
    completed_ids = {r["request_id"] for r in ix.completed}
    rank = {"low": 0, "medium": 1, "high": 2}
    active_weeks = int(truth["incidents.incident_active_window_weeks"])
    active_edge = truth.window_end - timedelta(weeks=active_weeks)
    pend_weeks = int(truth["billing.payment_pending_window_weeks"])
    open_weeks = int(truth["window.open_status_weeks"])
    open_edge = truth.window_end - timedelta(weeks=open_weeks)

    counts: dict[str, int] = {}
    counts["completed request without exactly one archive row"] = sum(
        1 for r in completed_ids if r not in ix.arch
    )
    counts["archive row on a cancelled or non-completed request"] = sum(
        1 for a in ar if a["request_id"] not in completed_ids
    )
    counts["archived completed_at before scheduled_datetime"] = sum(
        1
        for a in ar
        if a["request_id"] not in ix.req
        or a["completed_at"] < ix.req[a["request_id"]]["scheduled_datetime"]
    )
    credits: dict[int, Decimal] = defaultdict(Decimal)
    for i in inc:
        if i["credit_issued_amount"] is not None:
            credits[i["request_id"]] += i["credit_issued_amount"]
    counts["credits exceed total_invoice"] = sum(
        1 for rid, c in credits.items() if rid not in ix.arch or c > total_invoice(ix.arch[rid])
    )
    counts["feedback row without a sentiment_labels row"] = sum(
        1 for f in fb if f["feedback_id"] not in ix.label
    )
    counts["incident or feedback on an unknown request"] = sum(
        1 for x in inc + fb if x["request_id"] not in ix.req
    )
    counts["cancelled_at set iff cancelled (violations)"] = sum(
        1 for r in sr if (r["cancelled_at"] is not None) != (r["request_status"] == "cancelled")
    )
    counts["cancellation_reason on a non-cancelled request"] = sum(
        1 for r in sr if r["cancellation_reason"] and r["request_status"] != "cancelled"
    )
    counts["feedback or incident on a non-completed request"] = sum(
        1 for x in inc + fb if x["request_id"] not in completed_ids
    )
    counts["request with two feedback rows"] = len(fb) - len({f["request_id"] for f in fb})

    # ADR-038 / ADR-043 coherence.
    missed_bad = one_missed_bad = 0
    for rid, incs in ix.inc_by_req.items():
        req, arch = ix.req.get(rid), ix.arch.get(rid)
        if req is None:
            continue
        n_missed = sum(i["incident_type"] == "missed_sla" for i in incs)
        missed = arch is not None and not sla_met(req, arch)
        if n_missed and not missed:
            missed_bad += 1
        if missed and n_missed != 1:
            one_missed_bad += 1
    counts["missed_sla incident on a request that met its SLA"] = missed_bad
    counts["missed request with incidents lacking exactly one missed_sla"] = one_missed_bad

    children: dict[int, list[dict]] = defaultdict(list)
    for r in sr:
        if r["parent_request_id"] is not None:
            children[r["parent_request_id"]].append(r)
    repeat = {
        rid
        for rid, incs in ix.inc_by_req.items()
        if any(i["incident_type"] == "repeat_visit_required" for i in incs)
    }
    counts["repeat-visit parent without exactly one child, or child without one"] = len(
        repeat ^ set(children)
    ) + sum(1 for k in children.values() if len(k) != 1)
    counts["child differs from parent in account, site or service type"] = sum(
        1
        for pid, kids in children.items()
        for c in kids
        if pid not in ix.req
        or any(c[k] != ix.req[pid][k] for k in ("account_id", "location_id", "service_type"))
    )

    link_bad = 0
    for f in fb:
        incs = ix.inc_by_req.get(f["request_id"], [])
        best = (
            min(incs, key=lambda i: (-rank[i["severity"]], i["reported_at"], i["incident_id"]))
            if incs
            else None
        )
        if (best["incident_id"] if best else None) != f["incident_id"]:
            link_bad += 1
    counts["feedback not linked to the most severe (then earliest) incident"] = link_bad

    counts["incident active outside the active window, or resolved_at mismatch"] = sum(
        1
        for i in inc
        if (i["incident_status"] in ("open", "investigating")) != (i["resolved_at"] is None)
        or (i["incident_status"] in ("open", "investigating") and i["reported_at"] <= active_edge)
    )
    counts["incident_notes null on a non-open incident"] = sum(
        1 for i in inc if i["incident_notes"] is None and i["incident_status"] != "open"
    )
    counts["pending invoice outside the pending window"] = sum(
        1
        for a in ar
        if a["payment_status"] == "pending"
        and (truth.as_of - a["completed_at"]) >= timedelta(weeks=pend_weeks)
    )
    counts["payment_reference null iff pending (violations)"] = sum(
        1 for a in ar if (a["payment_reference"] is None) != (a["payment_status"] == "pending")
    )
    counts["non-terminal request outside the final weeks"] = sum(
        1
        for r in sr
        if r["request_status"] not in ("completed", "cancelled")
        and r["scheduled_datetime"] < open_edge - timedelta(days=1)
    )
    stamps = [
        (r, k) for r in sr for k in ("created_at", "dispatched_at", "cancelled_at", "updated_at")
    ] + [(a, k) for a in ar for k in ("completed_at", "archived_at", "updated_at")]
    stamps += [(i, k) for i in inc for k in ("reported_at", "created_at", "resolved_at")]
    stamps += [(f, "submitted_at") for f in fb]
    counts["event after the snapshot"] = sum(
        1 for row, k in stamps if row[k] is not None and row[k] > truth.as_of
    )
    prospects = {a["account_id"] for a in t["accounts"] if a["account_status"] == "prospect"}
    counts["request on a prospect account"] = sum(1 for r in sr if r["account_id"] in prospects)

    return [
        Check(f"A{n:02d}", "A invariants", name, v, "= 0", v == 0)
        for n, (name, v) in enumerate(counts.items(), 1)
    ]


#: The §8 invariants as SQL, run as app_qa against the database (cross-check of group A).
SQL_INVARIANTS = {
    "completed request without an archive row": """
        SELECT count(*) FROM service_requests r LEFT JOIN archived_requests a USING (request_id)
        WHERE r.request_status = 'completed' AND a.request_id IS NULL""",
    "archive row on a non-completed request": """
        SELECT count(*) FROM archived_requests a JOIN service_requests r USING (request_id)
        WHERE r.request_status <> 'completed'""",
    "credits exceed total_invoice": """
        SELECT count(*) FROM (
          SELECT request_id, sum(credit_issued_amount) AS c FROM incidents
          WHERE credit_issued_amount IS NOT NULL GROUP BY request_id) x
        JOIN archived_requests a USING (request_id)
        WHERE x.c > round((a.labor_charge + a.parts_charge) * (1 + a.surcharge_rate), 2)""",
    "feedback without a sentiment_labels row": """
        SELECT count(*) FROM service_feedback f LEFT JOIN sentiment_labels s USING (feedback_id)
        WHERE s.feedback_id IS NULL""",
    "incident or feedback on an unknown request": """
        SELECT (SELECT count(*) FROM incidents i LEFT JOIN service_requests r USING (request_id)
                WHERE r.request_id IS NULL)
             + (SELECT count(*) FROM service_feedback f LEFT JOIN service_requests r
                USING (request_id) WHERE r.request_id IS NULL)""",
    "archived completed_at before scheduled_datetime": """
        SELECT count(*) FROM archived_requests a JOIN service_requests r USING (request_id)
        WHERE a.completed_at < r.scheduled_datetime""",
}


# --------------------------------------------------------------------------- B. distributions


def target_service_mix(weekly: Mapping[int, int], truth: Truth) -> dict[str, float]:
    """Window-average designed service mix (upgrade x Q4 multiplier), weighted by the
    observed weekly volume."""
    base = truth["volume.service_type_mix"]
    mult = float(truth["volume.upgrade_q4_multiplier"])
    out: dict[str, float] = defaultdict(float)
    total = sum(weekly.values())
    for w, n in weekly.items():
        mix = dict(base)
        if (truth.start + timedelta(weeks=w)).month in (10, 11, 12):
            mix["upgrade"] *= mult
        s = sum(mix.values())
        for k, v in mix.items():
            out[k] += n / total * v / s
    return dict(out)


def check_distributions(t: Mapping[str, list[dict]], truth: Truth) -> list[Check]:
    ix = Index(t)
    tol = CHECK_TOLERANCES
    out: list[Check] = []
    sl, fb, sr, ar, inc = (
        t["sentiment_labels"],
        t["service_feedback"],
        t["service_requests"],
        t["archived_requests"],
        t["incidents"],
    )
    n = len(sl)
    mix = Counter(x["true_sentiment"] for x in sl)
    for se, target in truth["sentiment.target_mix"].items():
        v = mix[se] / n
        out.append(
            Check(
                f"B-sent-{se}",
                "B distributions",
                f"sentiment share: {se}",
                round(v, 4),
                f"{target:.2f} ± {tol['sentiment_pp'] * 100:.1f} pp",
                abs(v - target) <= tol["sentiment_pp"],
            )
        )
    hard = sum(x["hard_case_type"] != "none" for x in sl) / n
    lo, hi = tol["hard_case_share"]
    out.append(
        Check(
            "B-hard",
            "B distributions",
            "hard-case share of feedback",
            round(hard, 4),
            f"{lo:.2f}-{hi:.2f}",
            _band(hard, lo, hi),
        )
    )
    comp = len(ix.completed)
    with_inc = len({i["request_id"] for i in inc}) / comp
    lo, hi = tol["incident_request_rate"]
    out.append(
        Check(
            "B-inc",
            "B distributions",
            "completed requests with an incident",
            round(with_inc, 4),
            f"{lo:.2f}-{hi:.2f}",
            _band(with_inc, lo, hi),
        )
    )
    missed = sum(i["incident_type"] == "missed_sla" for i in inc) / len(inc)
    lo, hi = tol["missed_sla_share"]
    out.append(
        Check(
            "B-missed",
            "B distributions",
            "missed_sla share of incidents",
            round(missed, 4),
            f"{lo:.2f}-{hi:.2f}",
            _band(missed, lo, hi),
        )
    )
    fbr = len(fb) / comp
    lo, hi = tol["feedback_per_completed"]
    out.append(
        Check(
            "B-fb",
            "B distributions",
            "feedback rows per completed request",
            round(fbr, 4),
            f"{lo:.2f}-{hi:.2f}",
            _band(fbr, lo, hi),
        )
    )
    cancel = sum(r["request_status"] == "cancelled" for r in sr) / len(sr)
    lo, hi = tol["cancel_rate"]
    out.append(
        Check(
            "B-cancel",
            "B distributions",
            "cancellation rate",
            round(cancel, 4),
            f"{lo:.2f}-{hi:.2f}",
            _band(cancel, lo, hi),
        )
    )
    by_pri: dict[str, list[bool]] = defaultdict(list)
    for r in ix.completed:
        if r["request_id"] in ix.arch:
            by_pri[r["priority_tier"]].append(sla_met(r, ix.arch[r["request_id"]]))
    for pri, target in truth["requests.sla_met_target"].items():
        v = float(np.mean(by_pri[pri]))
        out.append(
            Check(
                f"B-sla-{pri}",
                "B distributions",
                f"sla_met rate: {pri}",
                round(v, 4),
                f"{target:.2f} ± {tol['sla_met_pp'] * 100:.0f} pp",
                abs(v - target) <= tol["sla_met_pp"],
                detail={"n": len(by_pri[pri])},
            )
        )
    weekly = Counter(truth.week_of(r["scheduled_datetime"]) for r in sr)
    target_mix = target_service_mix(weekly, truth)
    obs = Counter(r["service_type"] for r in sr)
    for st, target in sorted(target_mix.items()):
        v = obs[st] / len(sr)
        out.append(
            Check(
                f"B-svc-{st}",
                "B distributions",
                f"service mix: {st}",
                round(v, 4),
                f"{target:.3f} ± {tol['service_mix_pp'] * 100:.0f} pp",
                abs(v - target) <= tol["service_mix_pp"],
            )
        )
    status = Counter(a["payment_status"] for a in ar)
    disputed = status["disputed"] / len(ar)
    lo, hi = tol["disputed_share"]
    out.append(
        Check(
            "B-disputed",
            "B distributions",
            "disputed invoices",
            round(disputed, 4),
            f"{lo:.2f}-{hi:.2f}",
            _band(disputed, lo, hi),
        )
    )
    pending = status["pending"] / len(ar)
    exp_pending = float(truth["derived_billing.expected_pending_share"])
    out.append(
        Check(
            "B-pending",
            "B distributions",
            "pending invoices",
            round(pending, 4),
            f"{exp_pending:.4f} (recorded) ± {tol['pending_pp'] * 100:.0f} pp",
            abs(pending - exp_pending) <= tol["pending_pp"],
        )
    )
    return out


# --------------------------------------------------------------------------- C/D. signal


def weekly_counts(requests: list[dict], truth: Truth) -> np.ndarray:
    """Weekly request counts over the window from scheduled_datetime alone (all statuses)."""
    counts = np.zeros(truth.n_weeks)
    for r in requests:
        w = truth.week_of(r["scheduled_datetime"])
        if 0 <= w < truth.n_weeks:
            counts[w] += 1
    return counts


def design_matrix(weeks: np.ndarray, k: int = FOURIER_K) -> np.ndarray:
    t = weeks + 0.5
    cols = [np.ones_like(t), t]
    for j in range(1, k + 1):
        ang = 2 * np.pi * j * t / YEAR_WEEKS
        cols += [np.cos(ang), np.sin(ang)]
    return np.column_stack(cols)


def seasonal_range(coefs: np.ndarray, k: int = FOURIER_K) -> tuple[float, np.ndarray]:
    """Peak-to-trough of exp(seasonal component) over one year (centred)."""
    grid = np.linspace(0, YEAR_WEEKS, 2000, endpoint=False)
    s = design_matrix(grid - 0.5, k)[:, 2:] @ coefs
    s -= s.mean()
    f = np.exp(s)
    return float(f.max() - f.min()), f


def designed_weekly_season(truth: Truth) -> np.ndarray:
    """Designed weekly seasonal factor for every window week (mean of daily raw factors,
    normalized to mean 1 over a year)."""
    year = [date(2025, 1, 1) + timedelta(days=i) for i in range(365)]
    norm = sum(truth.raw_daily_season(d) for d in year) / 365
    out = []
    for w in range(truth.n_weeks):
        start = truth.start + timedelta(weeks=w)
        out.append(sum(truth.raw_daily_season(start + timedelta(days=i)) for i in range(7)) / 7)
    return np.array(out) / norm


def fit_signal(counts: np.ndarray, truth: Truth) -> dict:
    """log(count) = a + b t + Fourier(K=3), on training weeks with anomaly windows masked."""
    masked = {w for ws in truth.anomaly_weeks().values() for w in ws}
    weeks = np.array([w for w in range(truth.holdout_start) if w not in masked and counts[w] > 0])
    x = design_matrix(weeks.astype(float))
    y = np.log(counts[weeks])
    coefs, *_ = np.linalg.lstsq(x, y, rcond=None)
    resid = y - x @ coefs
    sd = float(np.sqrt(resid @ resid / (len(y) - x.shape[1])))

    # The designed profile seen through the same basis: project log(designed weekly season)
    # onto intercept + trend + Fourier(K=3) over the same weeks.
    design = designed_weekly_season(truth)
    dcoefs, *_ = np.linalg.lstsq(x, np.log(design[weeks]), rcond=None)
    return {
        "weeks": weeks,
        "coefs": coefs,
        "resid_sd": sd,
        "growth": float(math.exp(coefs[1] * YEAR_WEEKS) - 1),
        "season_range": seasonal_range(coefs[2:])[0],
        "design_range_k3": seasonal_range(dcoefs[2:])[0],
        "design_range_raw": float(design.max() - design.min()),
        "design": design,
        "dcoefs": dcoefs,
    }


def check_signal(counts: np.ndarray, truth: Truth) -> tuple[list[Check], dict]:
    fit = fit_signal(counts, truth)
    tol = CHECK_TOLERANCES
    growth_true = float(truth["volume.trend_annual_growth"])
    lo, hi = tol["residual_sd"]
    checks = [
        Check(
            "C-trend",
            "C signal recovery",
            "recovered annual growth",
            round(fit["growth"], 4),
            f"{growth_true:.2f} ± {tol['trend_growth_pp'] * 100:.0f} pp",
            abs(fit["growth"] - growth_true) <= tol["trend_growth_pp"],
            detail={"true": growth_true, "weeks_fitted": len(fit["weeks"])},
        ),
        Check(
            "C-season",
            "C signal recovery",
            "recovered seasonal peak-to-trough",
            round(fit["season_range"], 4),
            f"{fit['design_range_k3']:.3f} (designed, same K=3 basis) ± "
            f"{tol['season_range_pp'] * 100:.0f} pp",
            abs(fit["season_range"] - fit["design_range_k3"]) <= tol["season_range_pp"],
            detail={
                "designed_k3": round(fit["design_range_k3"], 4),
                "designed_raw_weekly": round(fit["design_range_raw"], 4),
                "nominal": "±25% amplitude, peak-to-trough ~0.50 before weekly and K=3 smoothing",
            },
        ),
        Check(
            "C-noise",
            "C signal recovery",
            "residual sd of log weekly volume",
            round(fit["resid_sd"], 4),
            f"{lo:.2f}-{hi:.2f}",
            _band(fit["resid_sd"], lo, hi),
            detail={"designed_effective": truth["derived_volume.effective_weekly_noise"]},
        ),
    ]
    return checks, fit


def _window_z(counts: np.ndarray, weeks: list[int], fit: dict) -> float:
    x = design_matrix(np.array(weeks, dtype=float))
    resid = np.log(np.maximum(counts[weeks], 1)) - x @ fit["coefs"]
    return float(resid.sum() / (fit["resid_sd"] * math.sqrt(len(weeks))))


def check_anomalies(
    t: Mapping[str, list[dict]], counts: np.ndarray, fit: dict, truth: Truth
) -> list[Check]:
    tol = CHECK_TOLERANCES
    aw = truth.anomaly_weeks()
    out = []
    reg_z = -_window_z(counts, aw["regional"], fit)
    out.append(
        Check(
            "D-regional",
            "D anomalies",
            "regional drop: z over its window",
            round(reg_z, 2),
            f">= {tol['regional_z_min']:.0f}",
            reg_z >= tol["regional_z_min"],
            detail={"weeks": aw["regional"]},
        )
    )

    # Account drop: the largest account by volume outside the anomaly weeks.
    sr = t["service_requests"]
    masked = {w for ws in aw.values() for w in ws}
    by_acct = Counter(
        r["account_id"] for r in sr if truth.week_of(r["scheduled_datetime"]) not in masked
    )
    top = by_acct.most_common(1)[0][0]
    acct_weekly = Counter(
        truth.week_of(r["scheduled_datetime"]) for r in sr if r["account_id"] == top
    )
    first, last = aw["account"][0], aw["account"][-1]
    around = [w for w in range(first - 8, last + 9) if w not in masked and 0 <= w < truth.n_weeks]
    base = float(np.mean([acct_weekly[w] for w in around]))
    during = float(np.mean([acct_weekly[w] for w in aw["account"]]))
    drop = 1 - during / base
    out.append(
        Check(
            "D-account",
            "D anomalies",
            "account drop at account level",
            round(drop, 4),
            f">= {tol['account_drop_min']:.2f}",
            drop >= tol["account_drop_min"],
            detail={"account_id": top, "weekly_during": during, "weekly_around": base},
        )
    )
    acct_z = -_window_z(counts, aw["account"], fit)
    out.append(
        Check(
            "D-account-total",
            "D anomalies",
            "account drop: weekly-total dip z (designed ~1.4)",
            round(acct_z, 2),
            "report only",
            True,
            hard=False,
        )
    )

    bill = truth["anomalies.billing_surcharge"]
    rate = Decimal(repr(bill["surcharge_rate"])).quantize(Decimal("0.0001"))
    inside = outside = inside_other = 0
    for a in t["archived_requests"]:
        if a["payment_method_final"] != bill["payment_method"]:
            continue
        in_win = truth.week_of(a["completed_at"]) in aw["billing"]
        if a["surcharge_rate"] == rate:
            inside += in_win
            outside += not in_win
        elif in_win:
            inside_other += 1
    out.append(
        Check(
            "D-billing",
            "D anomalies",
            "billing: direct-bill invoices at 0.10 inside / outside the window",
            f"{inside} / {outside}",
            "> 0 inside, 0 outside, none missed inside",
            inside > 0 and outside == 0 and inside_other == 0,
            detail={"inside": inside, "outside": outside, "inside_at_other_rate": inside_other},
        )
    )
    return out


# --------------------------------------------------------------------------- E. couplings


def check_couplings(t: Mapping[str, list[dict]], truth: Truth) -> tuple[list[Check], dict]:
    from scipy import stats

    ix = Index(t)
    out: list[Check] = []
    plots: dict = {}

    table = truth["sentiment.incident_sentiment_by_severity"]
    obs_sev: dict[str, Counter] = defaultdict(Counter)
    for f in t["service_feedback"]:
        if f["incident_id"] is not None:
            inc, lab = ix.inc.get(f["incident_id"]), ix.label.get(f["feedback_id"])
            if inc is not None and lab is not None:
                obs_sev[inc["severity"]][lab["true_sentiment"]] += 1
    plots["severity"] = {"observed": obs_sev, "designed": table}
    for sev, design in table.items():
        out.append(
            _chisq(f"E-sev-{sev}", f"severity -> sentiment: {sev}", obs_sev[sev], design, stats)
        )

    rates = truth["derived_incidents.incident_rate_given_sla"]
    k = {"sla_missed": 0, "sla_met": 0}
    n = {"sla_missed": 0, "sla_met": 0}
    for r in ix.completed:
        if r["request_id"] not in ix.arch:
            continue
        key = "sla_met" if sla_met(r, ix.arch[r["request_id"]]) else "sla_missed"
        n[key] += 1
        k[key] += bool(ix.inc_by_req.get(r["request_id"]))
    plots["sla"] = {"k": k, "n": n, "derived": rates}
    for key in ("sla_missed", "sla_met"):
        p = stats.binomtest(k[key], n[key], rates[key]).pvalue
        out.append(
            Check(
                f"E-{key}",
                "E couplings",
                f"P(incident | {key.replace('_', ' ')})",
                round(k[key] / n[key], 4),
                f"binomial vs derived {rates[key]:.3f}, p >= {ALPHA}",
                p >= ALPHA,
                detail={"p": p, "k": k[key], "n": n[key], "derived": rates[key]},
            )
        )

    ratings = truth["sentiment.rating_given_sentiment"]
    obs_rating: dict[str, Counter] = defaultdict(Counter)
    for f in t["service_feedback"]:
        if f["rating"] is not None:
            lab = ix.label.get(f["feedback_id"])
            if lab is not None:
                obs_rating[lab["true_sentiment"]][str(f["rating"])] += 1
    plots["rating"] = {"observed": obs_rating, "designed": ratings}
    for se, design in ratings.items():
        out.append(
            _chisq(f"E-rating-{se}", f"rating given sentiment: {se}", obs_rating[se], design, stats)
        )
    return out, plots


def _chisq(cid: str, name: str, observed: Counter, design: Mapping, stats) -> Check:
    """Chi-square goodness of fit; any observation in a zero-probability category fails."""
    cats = [c for c, p in design.items() if p > 0]
    impossible = sum(v for c, v in observed.items() if design.get(c, 0) == 0)
    n = sum(observed[c] for c in cats)
    obs = np.array([observed[c] for c in cats], dtype=float)
    exp = np.array([design[c] for c in cats], dtype=float)
    exp = exp / exp.sum() * n
    p = float(stats.chisquare(obs, exp).pvalue) if n else 0.0
    shares = {c: round(observed[c] / n, 3) if n else None for c in cats}
    return Check(
        cid,
        "E couplings",
        name,
        shares,
        f"chi-square vs designed {dict(design)}, p >= {ALPHA}; none impossible",
        p >= ALPHA and impossible == 0,
        detail={"p": p, "n": n, "impossible": impossible},
    )


# --------------------------------------------------------------------------- F. corpus


def check_corpus(t: Mapping[str, list[dict]], truth: Truth) -> list[Check]:
    fb, sl = t["service_feedback"], t["sentiment_labels"]
    dup_text = len(fb) - len({f["feedback_text"] for f in fb})
    dup_id = len(sl) - len({x["corpus_id"] for x in sl})
    allowed = truth.allowed_hard_types()
    on_incident = {f["feedback_id"] for f in fb if f["incident_id"] is not None}
    bad = sum(
        1
        for x in sl
        if x["hard_case_type"] not in allowed[x["true_sentiment"]]
        or (x["true_sentiment"] == "neutral" and x["feedback_id"] in on_incident)
    )
    return [
        Check(
            "F-text",
            "F corpus",
            "duplicate feedback_text across rows",
            dup_text,
            "= 0",
            dup_text == 0,
        ),
        Check("F-id", "F corpus", "duplicate corpus_id", dup_id, "= 0", dup_id == 0),
        Check(
            "F-cells", "F corpus", "labels breaking the ADR-036 cell rules", bad, "= 0", bad == 0
        ),
    ]


# --------------------------------------------------------------------------- orchestration


def run_checks(t: Mapping[str, list[dict]], weekly_rows: list[dict], truth: Truth):
    """All check groups. `weekly_rows` holds only request_id, scheduled_datetime and
    service_type (what app_forecast may read)."""
    checks = check_invariants(t, truth)
    checks += check_distributions(t, truth)
    counts = weekly_counts(weekly_rows, truth)
    sig, fit = check_signal(counts, truth)
    checks += sig
    checks += check_anomalies(t, counts, fit, truth)
    cpl, plot_data = check_couplings(t, truth)
    checks += cpl
    checks += check_corpus(t, truth)
    return checks, {"counts": counts, "fit": fit, **plot_data}


def spot_check_rows(t: Mapping[str, list[dict]], n: int = SPOT_CHECK_ROWS) -> list[dict]:
    ix = Index(t)
    fb = sorted(t["service_feedback"], key=lambda f: f["feedback_id"])
    rng = np.random.default_rng(SPOT_CHECK_SEED)
    rows = []
    for i in sorted(rng.choice(len(fb), size=min(n, len(fb)), replace=False)):
        f = fb[int(i)]
        lab = ix.label[f["feedback_id"]]
        inc = ix.inc.get(f["incident_id"]) if f["incident_id"] else None
        rows.append(
            {
                "corpus_id": lab["corpus_id"],
                "feedback_text": f["feedback_text"],
                "true_sentiment": lab["true_sentiment"],
                "hard_case_type": lab["hard_case_type"],
                "incident_type": inc["incident_type"] if inc else "",
                "incident_severity": inc["severity"] if inc else "",
                "unusable_yn": "",
                "notes": "",
            }
        )
    return rows


def write_outputs(out: Path, checks: list[Check], data: dict, t, truth: Truth, meta: dict):
    out.mkdir(parents=True, exist_ok=True)
    report = {
        "meta": meta,
        "tolerances_fixed_before_results": CHECK_TOLERANCES,
        "summary": dict(Counter(c.status for c in checks)),
        "checks": [{**{k: v for k, v in asdict(c).items()}, "status": c.status} for c in checks],
    }
    (out / "report.json").write_text(
        json.dumps(report, indent=2, default=_json_default), encoding="utf-8"
    )
    with (out / "spot_check.csv").open("w", newline="", encoding="utf-8") as fh:
        rows = spot_check_rows(t)
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    write_plots(out, data, t, truth)


def _json_default(o):
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (Decimal, datetime, date)):
        return str(o)
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    raise TypeError(type(o))


def write_plots(out: Path, data: dict, t, truth: Truth) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    counts, fit = data["counts"], data["fit"]
    weeks = np.arange(truth.n_weeks)
    dates = [truth.start + timedelta(weeks=int(w)) for w in weeks]
    fitted = np.exp(design_matrix(weeks.astype(float)) @ fit["coefs"])

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(dates, counts, lw=1, color="#444", label="weekly requests (all statuses)")
    ax.plot(dates, fitted, lw=2, color="#1f77b4", label="fitted trend + season (K=3)")
    ho = dates[truth.holdout_start]
    ax.axvline(ho, color="k", ls="--", lw=1)
    ax.text(ho, ax.get_ylim()[1] * 0.97, " holdout (26 wk)", va="top")
    colors = {"account": "#ff7f0e", "regional": "#d62728", "billing": "#2ca02c"}
    for name, ws in truth.anomaly_weeks().items():
        ax.axvspan(
            dates[ws[0]],
            dates[ws[-1]] + timedelta(days=7),
            color=colors[name],
            alpha=0.25,
            label=f"{name} anomaly",
        )
    ax.set_title("Weekly request volume with fitted trend and seasonality")
    ax.set_xlabel("week")
    ax.set_ylabel("requests per week")
    ax.legend(loc="lower right", fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "weekly_volume_fit.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 4.5))
    grid = np.linspace(0, YEAR_WEEKS, 2000, endpoint=False)
    _, rec = seasonal_range(fit["coefs"][2:])
    _, des = seasonal_range(fit["dcoefs"][2:])
    raw = fit["design"][:53]
    ax.plot(
        np.arange(len(raw)) + 0.5, raw, color="#999", lw=1, label="designed weekly factor (raw)"
    )
    ax.plot(grid, des, color="#2ca02c", lw=2, label="designed, K=3 basis")
    ax.plot(grid, rec, color="#1f77b4", lw=2, ls="--", label="recovered from data, K=3")
    ax.set_title("Seasonal profile: recovered vs designed (weeks from window start, early Sept)")
    ax.set_xlabel("week of year from window start")
    ax.set_ylabel("multiplicative factor")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "seasonal_profile.png", dpi=150)
    plt.close(fig)

    sl = t["sentiment_labels"]
    mix = Counter(x["true_sentiment"] for x in sl)
    target = truth["sentiment.target_mix"]
    cats = list(target)
    fig, ax = plt.subplots(figsize=(7, 4))
    x = np.arange(len(cats))
    ax.bar(x - 0.2, [target[c] for c in cats], 0.4, label="target", color="#bbb")
    ax.bar(x + 0.2, [mix[c] / len(sl) for c in cats], 0.4, label="achieved", color="#1f77b4")
    ax.set_xticks(x, cats)
    ax.set_ylabel("share of feedback")
    ax.set_title(f"Sentiment mix: achieved vs target (n={len(sl)})")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "sentiment_mix.png", dpi=150)
    plt.close(fig)

    sev = data["severity"]
    sevs = list(sev["designed"])
    sents = ["positive", "neutral", "negative", "mixed"]
    des_m = np.array([[sev["designed"][s][c] for c in sents] for s in sevs])
    obs_m = np.array(
        [
            [sev["observed"][s][c] / max(1, sum(sev["observed"][s].values())) for c in sents]
            for s in sevs
        ]
    )
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
    for ax, m, title in ((axes[0], obs_m, "observed"), (axes[1], des_m, "designed")):
        im = ax.imshow(m, vmin=0, vmax=0.8, cmap="Blues")
        ax.set_xticks(range(len(sents)), sents)
        ax.set_yticks(range(len(sevs)), sevs)
        for i in range(len(sevs)):
            for j in range(len(sents)):
                ax.text(j, i, f"{m[i, j]:.2f}", ha="center", va="center", fontsize=9)
        ax.set_title(f"Sentiment by incident severity: {title}")
    fig.colorbar(im, ax=axes, shrink=0.8)
    fig.savefig(out / "severity_sentiment_heatmap.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    s = data["sla"]
    keys = ["sla_missed", "sla_met"]
    obs = [s["k"][k] / s["n"][k] for k in keys]
    err = [1.96 * math.sqrt(p * (1 - p) / s["n"][k]) for p, k in zip(obs, keys, strict=True)]
    fig, ax = plt.subplots(figsize=(6, 4))
    x = np.arange(2)
    ax.bar(x - 0.2, [s["derived"][k] for k in keys], 0.4, label="derived", color="#bbb")
    ax.bar(x + 0.2, obs, 0.4, yerr=err, capsize=4, label="observed (95% CI)", color="#1f77b4")
    ax.set_xticks(x, ["SLA missed", "SLA met"])
    ax.set_ylabel("P(incident)")
    ax.set_title("Incident rate by SLA outcome")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "incident_rate_by_sla.png", dpi=150)
    plt.close(fig)


def print_summary(checks: list[Check]) -> None:
    w = max(len(c.name) for c in checks)
    print(f"{'id':16} {'check':{w}}  {'value':>22}  {'tolerance':44}  status")
    for c in checks:
        v = c.value if not isinstance(c.value, dict) else json.dumps(c.value)
        print(f"{c.id:16} {c.name:{w}}  {str(v):>22}  {c.tolerance[:44]:44}  {c.status}")
    s = Counter(c.status for c in checks)
    print(f"\n{s['PASS']} pass, {s['FAIL']} fail, {s['NOTE']} report-only")


# --------------------------------------------------------------------------- database


def _conn(user_var: str, password_var: str):
    import psycopg
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
    need = ("POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", user_var, password_var)
    missing = [v for v in need if not os.environ.get(v)]
    if missing:
        raise SystemExit(f"Missing environment variables: {', '.join(missing)}")
    return psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ[user_var],
        password=os.environ[password_var],
        options="-c timezone=UTC",
    )


QA_TABLES = (
    "accounts",
    "service_requests",
    "archived_requests",
    "incidents",
    "service_feedback",
    "sentiment_labels",
    "generation_parameters",
)


def read_database() -> tuple[dict, list[dict], dict]:
    """Tables as app_qa, the weekly series as app_forecast, and the §8 SQL cross-check."""
    from psycopg.rows import dict_row

    with _conn("DB_ROLE_FORECAST_USER", "DB_ROLE_FORECAST_PASSWORD") as conn:
        cur = conn.cursor(row_factory=dict_row)
        cur.execute("SELECT request_id, scheduled_datetime, service_type FROM service_requests")
        weekly_rows = cur.fetchall()
    tables = {}
    sql_counts = {}
    with _conn("DB_ROLE_QA_USER", "DB_ROLE_QA_PASSWORD") as conn:
        cur = conn.cursor(row_factory=dict_row)
        for tname in QA_TABLES:
            cur.execute(f'SELECT * FROM "{tname}"')  # noqa: S608 - fixed table names
            tables[tname] = cur.fetchall()
        for name, q in SQL_INVARIANTS.items():
            cur.execute(q)
            sql_counts[name] = next(iter(cur.fetchone().values()))
    return tables, weekly_rows, sql_counts


def sql_checks(sql_counts: Mapping[str, int]) -> list[Check]:
    return [
        Check(f"A-sql{n:02d}", "A invariants (SQL, app_qa)", name, v, "= 0", v == 0)
        for n, (name, v) in enumerate(sql_counts.items(), 1)
    ]


# --------------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--offline", action="store_true", help="validate a fresh generate.py run")
    ap.add_argument("--out-date", default=date.today().isoformat())
    args = ap.parse_args(argv)

    if args.offline:
        sys.path.insert(0, str(HERE))
        import generate as gen

        tables = gen.generate(HERE / "corpus" / "feedback_text.jsonl")
        weekly_rows = [
            {k: r[k] for k in ("request_id", "scheduled_datetime", "service_type")}
            for r in tables["service_requests"]
        ]
        sql_counts = {}
        source = "offline: generate.py output (no database)"
    else:
        tables, weekly_rows, sql_counts = read_database()
        source = "local Postgres: weekly series as app_forecast, all else as app_qa"
    truth = Truth(tables["generation_parameters"])
    checks, data = run_checks(tables, weekly_rows, truth)
    n_inv = sum(c.group == "A invariants" for c in checks)
    checks = checks[:n_inv] + sql_checks(sql_counts) + checks[n_inv:]
    out = OUT_ROOT / args.out_date
    meta = {
        "source": source,
        "run_date": args.out_date,
        "corpus_sha256": truth["seed.corpus_sha256"],
        "master_seed": truth["seed.master_seed"],
        "rows": {k: len(v) for k, v in tables.items()},
    }
    write_outputs(out, checks, data, tables, truth, meta)
    print_summary(checks)
    print(f"wrote {out}")
    return 0 if all(c.passed or not c.hard for c in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
