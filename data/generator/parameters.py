"""Ground truth of the synthetic world: every generation parameter, its derivations, and
their self-validation.

Pure data and arithmetic. No database access and no random draws: the only randomness
here is *seed derivation* (`derive_seed`), which build_corpus.py and generate.py use to
seed their own stages. Everything a later stage needs to know about the world — volume
shape, SLA targets, incident rules, the severity -> sentiment coupling, the ADR-036 cell
rules, corpus sizing, anomalies — is defined once here and persisted to
`generation_parameters` via `to_generation_parameters_rows()`.

Every parameter is a `P(value, note, chosen, kind)`:
- `note` becomes `generation_parameters.notes`;
- `chosen=True` marks a value picked while writing this file rather than specified by the
  project owner — the ones to review;
- `kind` tells `validate_parameters()` which values are distributions that must sum to 1.

Names and categories are generic field service (R-08).

Run as a script to print the derived summary (totals, solved sentiment, corpus sizing,
anomaly strength). It prints numbers only.

Docs: data-dictionary.md §2-§6; ADR-018, -019, -021, -030, -036, -037.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from datetime import date, timedelta
from pathlib import Path
from statistics import NormalDist
from types import MappingProxyType
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
DICTIONARY = REPO_ROOT / "docs" / "data-dictionary.md"


def fz(d: Mapping) -> Mapping:
    """Recursively read-only mapping, so frozen dataclasses are frozen all the way down."""
    return MappingProxyType({k: fz(v) if isinstance(v, Mapping) else v for k, v in d.items()})


@dataclass(frozen=True)
class P[T]:
    """One parameter: its value, a one-line note, and whether the value was chosen here."""

    value: T
    note: str
    chosen: bool = False
    #: "value", "dist" (a mapping whose values sum to 1) or "dist_by" (a mapping of dists).
    kind: str = "value"


def D(value: Mapping, note: str, chosen: bool = False) -> P:  # noqa: N802 — reads as a type
    return P(fz(value), note, chosen, "dist")


def DB(value: Mapping, note: str, chosen: bool = False) -> P:  # noqa: N802
    return P(fz(value), note, chosen, "dist_by")


def V(value: Any, note: str, chosen: bool = False) -> P:  # noqa: N802
    return P(fz(value) if isinstance(value, Mapping) else value, note, chosen, "value")


# --------------------------------------------------------------------------- seeds

MASTER_SEED = 20260923

STAGE_REFERENCE = "reference"
STAGE_VOLUME = "volume"
STAGE_REQUESTS = "requests"
STAGE_INCIDENTS = "incidents"
STAGE_BILLING = "billing"
STAGE_FEEDBACK = "feedback"
STAGE_SENTIMENT = "sentiment"
STAGE_CORPUS_ASSIGNMENT = "corpus_assignment"
STAGE_ANOMALIES = "anomalies"
STAGES: tuple[str, ...] = (
    STAGE_REFERENCE,
    STAGE_VOLUME,
    STAGE_REQUESTS,
    STAGE_INCIDENTS,
    STAGE_BILLING,
    STAGE_FEEDBACK,
    STAGE_SENTIMENT,
    STAGE_CORPUS_ASSIGNMENT,
    STAGE_ANOMALIES,
)


def stage_key(stage: str) -> int:
    """Stable 64-bit key for a stage name: first 8 bytes of SHA-256, big-endian.

    Never Python's `hash()`, which is salted per process (PYTHONHASHSEED).
    """
    if not stage:
        raise ValueError("stage name must be non-empty")
    return int.from_bytes(hashlib.sha256(stage.encode("utf-8")).digest()[:8], "big")


def derive_seed(stage: str, master_seed: int = MASTER_SEED) -> np.random.SeedSequence:
    """Independent, reproducible SeedSequence for one generation stage.

    Each stage's entropy depends only on (master seed, its own name), so adding a stage
    never shifts another stage's stream.
    """
    return np.random.SeedSequence([master_seed, stage_key(stage)])


# --------------------------------------------------------------------------- vocab
# Literal value sets. validate_parameters() checks each against db_models.enums, so a
# vocabulary change can't silently leave the generator behind.

SERVICE_TYPES = ("install", "repair", "maintenance", "inspection", "upgrade")
PRIORITIES = ("standard", "urgent", "critical")
CONTRACT_TIERS = ("standard", "priority", "enterprise")
INCIDENT_TYPES = (
    "missed_sla",
    "wrong_dispatch_info",
    "repeat_visit_required",
    "technician_conduct",
    "equipment_damage",
    "billing_dispute",
    "other",
)
SEVERITIES = ("low", "medium", "high")
SENTIMENTS = ("positive", "neutral", "negative", "mixed")
STYLES = ("plain", "implicit", "sarcastic")  # ADR-036; stored as hard_case_type (ADR-037)
INCIDENT_CONTEXTS = ("none", "minor", "serious")  # ADR-036 §5: minor=low, serious=med/high
HARD_CASE_BY_STYLE = {"plain": "none", "implicit": "implicit", "sarcastic": "sarcastic"}


# --------------------------------------------------------------------------- domains


@dataclass(frozen=True)
class Window:
    start_monday: P = V(date(2023, 9, 4), "First week of the history window (a Monday).")
    n_weeks: P = V(156, "History length in weeks: three full seasonal cycles (ADR-018).")
    holdout_weeks: P = V(26, "Final weeks held out for the forecast backtest (ADR-018).")
    open_status_weeks: P = V(
        2, "Only requests scheduled in the final N weeks may still be in a non-terminal status."
    )
    open_status_share_by_week_from_end: P = V(
        {1: 0.60, 2: 0.25},
        "Share of non-cancelled requests still non-terminal, by week counted from the end.",
        chosen=True,
    )
    open_status_mix: P = D(
        {"open": 0.30, "dispatched": 0.25, "en_route": 0.15, "in_progress": 0.30},
        "Status mix among non-terminal requests in the final weeks.",
        chosen=True,
    )


@dataclass(frozen=True)
class Reference:
    n_accounts: P = V(50, "Client accounts (§6: 40-60).")
    contract_tier_mix: P = D(
        {"standard": 0.50, "priority": 0.35, "enterprise": 0.15}, "Account contract tier mix."
    )
    contract_tier_counts: P = V(
        {"standard": 25, "priority": 17, "enterprise": 8},
        "Exact tier counts for 50 accounts (mix rounded; priority 17.5 -> 17).",
        chosen=True,
    )
    account_status_mix: P = D(
        {"active": 0.85, "inactive": 0.10, "prospect": 0.05}, "Account status mix."
    )
    account_status_counts: P = V(
        {"active": 43, "inactive": 5, "prospect": 2},
        "Exact status counts for 50 accounts (mix rounded).",
        chosen=True,
    )
    prospects_get_requests: P = V(False, "Prospect accounts have no service history.")
    inactive_accounts_get_requests: P = V(
        True,
        "Inactive accounts have history; generate.py decides when in the window they stop.",
        chosen=True,
    )
    locations_per_account: P = V((3, 5), "Sites per account, uniform inclusive (§6: 150-250).")
    contacts_per_account: P = V(
        (3, 5), "Contacts per account, uniform inclusive (~4; §6: 150-300).", chosen=True
    )
    contact_role_mix: P = D(
        {"site_contact": 0.55, "billing_contact": 0.20, "account_admin": 0.15, "other": 0.10},
        "Contact role mix.",
        chosen=True,
    )
    n_technicians: P = V(32, "Technicians (§6: 25-40).")
    technician_status_mix: P = D(
        {"active": 0.85, "on_leave": 0.05, "terminated": 0.10}, "Technician status mix."
    )
    technician_status_counts: P = V(
        {"active": 27, "on_leave": 2, "terminated": 3},
        "Exact status counts for 32 technicians (mix rounded).",
        chosen=True,
    )
    skills_per_technician: P = V((1, 3), "Distinct skills per technician, uniform inclusive.")
    skill_mix: P = D(
        {
            "network": 0.30,
            "hardware": 0.25,
            "cabling": 0.20,
            "security_systems": 0.15,
            "power_systems": 0.10,
        },
        "Skill draw weights.",
        chosen=True,
    )
    proficiency_mix: P = D(
        {"certified": 0.30, "experienced": 0.50, "trainee": 0.20},
        "Proficiency per technician-skill pair.",
        chosen=True,
    )
    n_internal_users: P = V(15, "Dispatch and back-office users.")
    internal_user_role_counts: P = V(
        {"dispatcher": 8, "supervisor": 3, "billing_clerk": 3, "qa_analyst": 1},
        "Exact internal user role counts.",
        chosen=True,
    )
    internal_user_status_counts: P = V(
        {"active": 13, "inactive": 2}, "Exact internal user status counts.", chosen=True
    )
    largest_account_volume_share: P = V(
        0.12, "Largest account's share of request volume; shares are Zipf over accounts."
    )


@dataclass(frozen=True)
class Volume:
    expected_new_requests: P = V(
        20_000,
        "Expected first-visit requests over the window (target 18-22K); repeat-visit "
        "children come on top.",
        chosen=True,
    )
    trend_annual_growth: P = V(0.08, "Multiplicative volume growth per year (§6).")
    seasonality_monthly_raw: P = V(
        {
            1: 0.88,
            2: 0.92,
            3: 0.98,
            4: 1.00,
            5: 1.00,
            6: 0.96,
            7: 0.92,
            8: 0.95,
            9: 1.04,
            10: 1.22,
            11: 1.25,
            12: 1.00,
        },
        "Raw daily seasonal factor by month before normalization to mean 1 (Oct-Nov peak).",
        chosen=True,
    )
    late_december_trough: P = V(
        {"from": "12-20", "to": "01-01", "factor": 0.75},
        "Raw factor for Dec 20 - Jan 1 inclusive (late-December trough).",
        chosen=True,
    )
    seasonality_amplitude_target: P = V(0.25, "Intended seasonal swing, about +/-25% (§6).")
    day_of_week_weights: P = D(
        {
            "mon": 0.21,
            "tue": 0.21,
            "wed": 0.21,
            "thu": 0.20,
            "fri": 0.15,
            "sat": 0.015,
            "sun": 0.005,
        },
        "Share of a week's requests scheduled on each weekday.",
        chosen=True,
    )
    hour_of_day_weights: P = D(
        {
            7: 0.04,
            8: 0.10,
            9: 0.13,
            10: 0.13,
            11: 0.11,
            12: 0.07,
            13: 0.11,
            14: 0.11,
            15: 0.09,
            16: 0.07,
            17: 0.04,
        },
        "Scheduled hour, site-local business hours. Timezone handling is generate.py's call.",
        chosen=True,
    )
    weekly_noise_sd: P = V(0.06, "SD of weekly multiplicative noise on expected volume.")
    service_type_mix: P = D(
        {"repair": 0.35, "maintenance": 0.25, "install": 0.18, "inspection": 0.12, "upgrade": 0.10},
        "Base service type mix.",
    )
    upgrade_q4_multiplier: P = V(
        1.5,
        "Upgrade weight multiplier in Oct-Dec, mix renormalized (hardware refresh).",
        chosen=True,
    )


@dataclass(frozen=True)
class Requests:
    priority_mix: P = D({"standard": 0.70, "urgent": 0.22, "critical": 0.08}, "Priority mix.")
    cancel_rate: P = V(0.10, "Share of requests cancelled.")
    cancellation_reason_mix: P = D(
        {
            "client_cancelled": 0.45,
            "client_no_show": 0.20,
            "resource_unavailable": 0.15,
            "duplicate": 0.10,
            "other": 0.10,
        },
        "Cancellation reasons; client-driven most common.",
        chosen=True,
    )
    sla_window_minutes: P = V(
        {
            "standard": {"standard": 480, "urgent": 240, "critical": 120},
            "priority": {"standard": 240, "urgent": 120, "critical": 60},
            "enterprise": {"standard": 120, "urgent": 60, "critical": 30},
        },
        "SLA window by contract tier then priority (§2), snapshotted onto each request.",
    )
    sla_met_target: P = V(
        {"standard": 0.90, "urgent": 0.87, "critical": 0.82},
        "Target P(completed_at <= dispatched_at + window) by priority.",
    )
    completion_ratio_sigma: P = V(
        0.35,
        "Lognormal sigma of (completed_at - dispatched_at) / sla_window; mu is solved per "
        "priority so P(ratio <= 1) equals the SLA target.",
        chosen=True,
    )
    dispatch_lag_median_minutes: P = V(
        {"standard": 90, "urgent": 30, "critical": 10},
        "Median minutes from scheduled time to dispatch; does not affect sla_met (§6).",
        chosen=True,
    )
    dispatch_lag_sigma: P = V(0.6, "Lognormal sigma of dispatch lag.", chosen=True)
    equipment_unit_count_bins: P = V(
        (
            (1, 1, 0.30),
            (2, 2, 0.22),
            (3, 3, 0.15),
            (4, 4, 0.10),
            (5, 5, 0.08),
            (6, 10, 0.10),
            (11, 25, 0.04),
            (26, 60, 0.01),
        ),
        "(lo, hi, prob) bins, uniform within a bin: mostly 1-5 with a long tail.",
        chosen=True,
    )
    repeat_child_rule: P = V(
        "A completed request with at least one repeat_visit_required incident gets exactly "
        "one child request (parent_request_id set), same account, location and service type.",
        "Repeat-visit coherence rule; children follow every other rule like any request.",
    )
    child_schedule_days: P = V(
        (2, 10), "Child scheduled this many days after the parent's completion.", chosen=True
    )


@dataclass(frozen=True)
class Billing:
    labor_charge: P = V(
        {
            "install": {"median": 650.0, "sigma": 0.45},
            "repair": {"median": 320.0, "sigma": 0.50},
            "maintenance": {"median": 240.0, "sigma": 0.35},
            "inspection": {"median": 180.0, "sigma": 0.30},
            "upgrade": {"median": 900.0, "sigma": 0.50},
        },
        "Lognormal labor charge (USD) for one unit, by service type.",
        chosen=True,
    )
    labor_unit_exponent: P = V(
        0.4, "Labor scales with equipment_unit_count ** exponent.", chosen=True
    )
    parts_charge: P = V(
        {
            "install": {"p_nonzero": 0.90, "median": 1200.0, "sigma": 0.70},
            "repair": {"p_nonzero": 0.70, "median": 250.0, "sigma": 0.80},
            "maintenance": {"p_nonzero": 0.30, "median": 80.0, "sigma": 0.60},
            "inspection": {"p_nonzero": 0.10, "median": 40.0, "sigma": 0.50},
            "upgrade": {"p_nonzero": 0.95, "median": 1800.0, "sigma": 0.70},
        },
        "Parts charge (USD) for one unit: zero with prob 1 - p_nonzero, else lognormal.",
        chosen=True,
    )
    parts_unit_exponent: P = V(
        0.8, "Parts scale with equipment_unit_count ** exponent.", chosen=True
    )
    payment_method_mix: P = D(
        {"direct_bill": 0.40, "credit_card": 0.30, "ach": 0.20, "check": 0.10},
        "Requested payment method mix.",
        chosen=True,
    )
    surcharge_rate_by_method: P = V(
        {"credit_card": 0.03, "direct_bill": 0.0, "ach": 0.0, "check": 0.0},
        "surcharge_rate by payment_method_final.",
    )
    payment_method_change_rate: P = V(
        0.05,
        "P(payment_method_final differs from requested); the new method is uniform over "
        "the others.",
    )
    payment_status_mix: P = D(
        {"paid": 0.88, "pending": 0.08, "disputed": 0.04}, "Final payment status mix."
    )
    billing_dispute_to_disputed: P = V(
        0.60,
        "P(payment_status = disputed | request has a billing_dispute incident); counts "
        "toward the 4% disputed.",
        chosen=True,
    )


@dataclass(frozen=True)
class Incidents:
    request_incident_rate: P = V(0.10, "Share of completed requests with at least one incident.")
    incidents_per_request_mix: P = D(
        {1: 0.88, 2: 0.10, 3: 0.02},
        "Number of incidents on a request that has any.",
        chosen=True,
    )
    incident_type_mix: P = D(
        {
            "missed_sla": 0.25,
            "repeat_visit_required": 0.20,
            "wrong_dispatch_info": 0.15,
            "billing_dispute": 0.12,
            "equipment_damage": 0.10,
            "technician_conduct": 0.08,
            "other": 0.10,
        },
        "Incident type mix (marginal over all incidents).",
    )
    missed_sla_requires_sla_miss: P = V(
        True,
        "Coherence rule: missed_sla incidents are drawn only from requests whose sla_met is false.",
    )
    severity_mix: P = D(
        {"low": 0.50, "medium": 0.35, "high": 0.15},
        "Severity per incident, independent of type.",
    )
    root_cause_by_type: P = DB(
        {
            "missed_sla": {
                "dispatch_error": 0.45,
                "technician_error": 0.25,
                "client_site_issue": 0.15,
                "communication_breakdown": 0.10,
                "other": 0.05,
            },
            "wrong_dispatch_info": {
                "dispatch_error": 0.60,
                "communication_breakdown": 0.35,
                "other": 0.05,
            },
            "repeat_visit_required": {
                "equipment_failure": 0.40,
                "technician_error": 0.30,
                "client_site_issue": 0.20,
                "other": 0.10,
            },
            "technician_conduct": {"technician_error": 0.90, "communication_breakdown": 0.10},
            "equipment_damage": {
                "technician_error": 0.55,
                "equipment_failure": 0.30,
                "client_site_issue": 0.15,
            },
            "billing_dispute": {
                "communication_breakdown": 0.50,
                "dispatch_error": 0.20,
                "other": 0.30,
            },
            "other": {"other": 0.50, "communication_breakdown": 0.20, "client_site_issue": 0.30},
        },
        "Root cause given type; null while the incident is still open (§3).",
        chosen=True,
    )
    attribution_prob_by_type: P = V(
        {
            "missed_sla": 0.60,
            "wrong_dispatch_info": 0.0,
            "repeat_visit_required": 0.70,
            "technician_conduct": 1.0,
            "equipment_damage": 0.80,
            "billing_dispute": 0.0,
            "other": 0.20,
        },
        "P(attributed_technician_id is set) by type; never for billing or dispatch errors.",
        chosen=True,
    )
    credit_by_type: P = V(
        {
            "missed_sla": {"p": 0.40, "frac_lo": 0.05, "frac_hi": 0.20},
            "wrong_dispatch_info": {"p": 0.30, "frac_lo": 0.05, "frac_hi": 0.15},
            "repeat_visit_required": {"p": 0.35, "frac_lo": 0.10, "frac_hi": 0.25},
            "technician_conduct": {"p": 0.25, "frac_lo": 0.05, "frac_hi": 0.20},
            "equipment_damage": {"p": 0.60, "frac_lo": 0.20, "frac_hi": 1.00},
            "billing_dispute": {"p": 0.50, "frac_lo": 0.10, "frac_hi": 0.40},
            "other": {"p": 0.10, "frac_lo": 0.02, "frac_hi": 0.10},
        },
        "P(credit issued) and credit as a uniform fraction of total_invoice; the sum of "
        "credits on one request is capped at its total_invoice.",
        chosen=True,
    )
    incident_status_mix: P = D(
        {"closed": 0.35, "resolved": 0.55, "investigating": 0.07, "open": 0.03},
        "Incident status; generate.py should skew recent incidents toward open.",
        chosen=True,
    )


@dataclass(frozen=True)
class Feedback:
    response_rate_no_incident: P = V(0.40, "Survey response rate, completed without incident.")
    response_rate_incident: P = V(0.55, "Survey response rate, completed with an incident.")
    feedback_text_always: P = V(True, "Every feedback row has feedback_text (from the corpus).")
    rating_null_rate: P = V(0.10, "Share of feedback rows with no numeric rating.")
    channel_mix: P = D(
        {"email_survey": 0.45, "sms_survey": 0.25, "portal": 0.20, "phone_followup": 0.10},
        "Response channel mix.",
    )
    incident_link_rule: P = V(
        "most_severe_then_earliest",
        "With several incidents, feedback links to the most severe; ties go to the "
        "earliest reported.",
        chosen=True,
    )


@dataclass(frozen=True)
class Sentiment:
    target_mix: P = D(
        {"positive": 0.50, "neutral": 0.22, "negative": 0.20, "mixed": 0.08},
        "Overall true_sentiment target (ADR-019).",
    )
    incident_sentiment_by_severity: P = DB(
        {
            "low": {"positive": 0.30, "neutral": 0.0, "negative": 0.45, "mixed": 0.25},
            "medium": {"positive": 0.15, "neutral": 0.0, "negative": 0.60, "mixed": 0.25},
            "high": {"positive": 0.10, "neutral": 0.0, "negative": 0.70, "mixed": 0.20},
        },
        "incident_severity_sentiment_coupling: sentiment given the linked incident's "
        "severity (ADR-021); neutral is 0 on incident rows (ADR-036).",
    )
    hard_case_shares: P = V(
        {
            ("positive", "implicit"): 0.08,
            ("negative", "implicit"): 0.03,
            ("negative", "sarcastic"): 0.04,
        },
        "Hard cases as shares of all feedback (total 0.15, ADR-019/-036).",
    )
    hard_case_independent_of_incident: P = V(
        True,
        "Within a sentiment, the hard-case style share is the same on incident and "
        "no-incident rows.",
        chosen=True,
    )
    rating_given_sentiment: P = DB(
        {
            "positive": {5: 0.60, 4: 0.35, 3: 0.05},
            "neutral": {4: 0.30, 3: 0.50, 2: 0.20},
            "negative": {1: 0.50, 2: 0.35, 3: 0.15},
            "mixed": {4: 0.30, 3: 0.50, 2: 0.20},
        },
        "Rating given true sentiment (when not null).",
    )


@dataclass(frozen=True)
class Corpus:
    cell_floor: P = V(6, "Minimum comments per possible corpus cell (ADR-036 §5).")
    spare_rate: P = V(0.20, "Spares on top of each cell's requirement (ADR-036 §5).")
    double_cells: P = V(
        (("neutral", "plain"), ("mixed", "plain")),
        "(sentiment, style) cells sized 2x: the judge filter rejects more of them.",
    )
    double_multiplier: P = V(2.0, "Size multiplier for double_cells.")
    incident_context_by_severity: P = V(
        {"low": "minor", "medium": "serious", "high": "serious"},
        "Corpus incident level from the linked incident's severity (ADR-036 §5).",
    )
    batch_size: P = V(20, "Comments per Flash-Lite request (ADR-036 §8).")


@dataclass(frozen=True)
class Anomalies:
    volume_drop: P = V(
        {"account_rank": 1, "drop": 0.90, "start_week": 40, "n_weeks": 2},
        "Largest account's requests drop 90% for 2 weeks (a site closure); week index "
        "from window start, inside the training span.",
        chosen=True,
    )
    billing_surcharge: P = V(
        {"payment_method": "direct_bill", "surcharge_rate": 0.10, "start_week": 95, "n_weeks": 3},
        "direct_bill invoices carry surcharge_rate 0.10 instead of 0 for 3 weeks "
        "(a billing error); inside the training span.",
        chosen=True,
    )


@dataclass(frozen=True)
class Parameters:
    window: Window = field(default_factory=Window)
    reference: Reference = field(default_factory=Reference)
    volume: Volume = field(default_factory=Volume)
    requests: Requests = field(default_factory=Requests)
    billing: Billing = field(default_factory=Billing)
    incidents: Incidents = field(default_factory=Incidents)
    feedback: Feedback = field(default_factory=Feedback)
    sentiment: Sentiment = field(default_factory=Sentiment)
    corpus: Corpus = field(default_factory=Corpus)
    anomalies: Anomalies = field(default_factory=Anomalies)


PARAMS = Parameters()


def iter_params(params: Parameters = PARAMS):
    """Yield (domain, name, P) for every parameter."""
    for dom in fields(params):
        domain = getattr(params, dom.name)
        for f in fields(domain):
            yield dom.name, f.name, getattr(domain, f.name)


# --------------------------------------------------------------------------- cell rules
# ADR-036 §4: neutral only without incident and plain; mixed plain only (any incident
# level); sarcastic negative only; implicit positive and negative only. Imported by
# build_corpus.py and generate.py alike.

ALLOWED_STYLES: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "positive": ("plain", "implicit"),
        "neutral": ("plain",),
        "negative": ("plain", "implicit", "sarcastic"),
        "mixed": ("plain",),
    }
)
ALLOWED_CONTEXTS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "positive": INCIDENT_CONTEXTS,
        "neutral": ("none",),
        "negative": INCIDENT_CONTEXTS,
        "mixed": INCIDENT_CONTEXTS,
    }
)
ALLOWED_CELLS: frozenset[tuple[str, str, str]] = frozenset(
    (se, st, ctx) for se in SENTIMENTS for st in ALLOWED_STYLES[se] for ctx in ALLOWED_CONTEXTS[se]
)


def is_allowed(sentiment: str, style: str, context: str) -> bool:
    """True if (sentiment, style, incident context) is a possible cell under ADR-036."""
    return (sentiment, style, context) in ALLOWED_CELLS


# --------------------------------------------------------------------------- derivations


def week_start(w: int, params: Parameters = PARAMS) -> date:
    return params.window.start_monday.value + timedelta(weeks=w)


def holdout_start_week(params: Parameters = PARAMS) -> int:
    return params.window.n_weeks.value - params.window.holdout_weeks.value


def _raw_daily_season(d: date, params: Parameters) -> float:
    trough = params.volume.late_december_trough.value
    if (d.month == 12 and d.day >= int(trough["from"][3:])) or (d.month == 1 and d.day == 1):
        return trough["factor"]
    return params.volume.seasonality_monthly_raw.value[d.month]


def _season_norm(params: Parameters) -> float:
    days = [date(2025, 1, 1) + timedelta(days=i) for i in range(365)]
    return sum(_raw_daily_season(d, params) for d in days) / len(days)


def seasonal_factor(d: date, params: Parameters = PARAMS) -> float:
    """Daily seasonal multiplier, normalized to mean 1 over a year."""
    return _raw_daily_season(d, params) / _season_norm(params)


def seasonal_range(params: Parameters = PARAMS) -> dict:
    days = [date(2025, 1, 1) + timedelta(days=i) for i in range(365)]
    vals = [seasonal_factor(d, params) for d in days]
    return {"peak": max(vals), "trough": min(vals)}


def _weekly_season(w: int, params: Parameters) -> float:
    start = week_start(w, params)
    norm = _season_norm(params)
    return sum(_raw_daily_season(start + timedelta(days=i), params) for i in range(7)) / 7 / norm


def _weekly_growth(w: int, params: Parameters) -> float:
    days = w * 7 + 3.5  # mid-week
    return (1 + params.volume.trend_annual_growth.value) ** (days / 365.25)


def base_weekly_requests(params: Parameters = PARAMS) -> float:
    """First-week expected volume (before season) that makes the window total hit target."""
    shape = sum(
        _weekly_growth(w, params) * _weekly_season(w, params)
        for w in range(params.window.n_weeks.value)
    )
    return params.volume.expected_new_requests.value / shape


def weekly_expected_new(params: Parameters = PARAMS) -> list[float]:
    """Expected first-visit requests per week (no noise, no anomalies, no children)."""
    base = base_weekly_requests(params)
    return [
        base * _weekly_growth(w, params) * _weekly_season(w, params)
        for w in range(params.window.n_weeks.value)
    ]


def service_mix_for_week(w: int, params: Parameters = PARAMS) -> dict[str, float]:
    mix = dict(params.volume.service_type_mix.value)
    start = week_start(w, params)
    if start.month in (10, 11, 12):
        mix["upgrade"] *= params.volume.upgrade_q4_multiplier.value
    total = sum(mix.values())
    return {k: v / total for k, v in mix.items()}


def expected_service_mix(params: Parameters = PARAMS) -> dict[str, float]:
    """Volume-weighted service mix over the window (includes the Q4 upgrade lift)."""
    weekly = weekly_expected_new(params)
    out = dict.fromkeys(SERVICE_TYPES, 0.0)
    for w, vol in enumerate(weekly):
        for k, v in service_mix_for_week(w, params).items():
            out[k] += vol * v
    total = sum(out.values())
    return {k: v / total for k, v in out.items()}


def zipf_exponent(params: Parameters = PARAMS) -> float:
    """Zipf exponent s over requesting accounts so the rank-1 share hits the target."""
    counts = params.reference.account_status_counts.value
    n = counts["active"] + counts["inactive"]
    target = params.reference.largest_account_volume_share.value

    def top_share(s: float) -> float:
        return 1.0 / sum(k ** (-s) for k in range(1, n + 1))

    lo, hi = 0.0, 3.0
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if top_share(mid) < target else (lo, mid)
    return (lo + hi) / 2


def account_volume_shares(params: Parameters = PARAMS) -> list[float]:
    """Volume share by account rank (rank 1 = largest) over requesting accounts."""
    counts = params.reference.account_status_counts.value
    n = counts["active"] + counts["inactive"]
    s = zipf_exponent(params)
    raw = [k ** (-s) for k in range(1, n + 1)]
    total = sum(raw)
    return [r / total for r in raw]


def completion_ratio_mu(params: Parameters = PARAMS) -> dict[str, float]:
    """Lognormal mu of duration/window per priority so P(ratio <= 1) = SLA target."""
    sigma = params.requests.completion_ratio_sigma.value
    return {
        pr: -sigma * NormalDist().inv_cdf(t)
        for pr, t in params.requests.sla_met_target.value.items()
    }


def expected_sla_miss_rate(params: Parameters = PARAMS) -> float:
    mix = params.requests.priority_mix.value
    return sum(mix[p] * (1 - params.requests.sla_met_target.value[p]) for p in mix)


def max_severity_dist(params: Parameters = PARAMS) -> dict[str, float]:
    """P(most severe incident on a request = s | request has incidents)."""
    sev = params.incidents.severity_mix.value
    cum = {"low": sev["low"], "medium": sev["low"] + sev["medium"], "high": 1.0}
    out = dict.fromkeys(SEVERITIES, 0.0)
    for k, pk in params.incidents.incidents_per_request_mix.value.items():
        prev = 0.0
        for s in SEVERITIES:
            out[s] += pk * (cum[s] ** k - prev)
            prev = cum[s] ** k
    return out


def mean_incidents_per_request(params: Parameters = PARAMS) -> float:
    return sum(k * p for k, p in params.incidents.incidents_per_request_mix.value.items())


def child_prob_given_incident(params: Parameters = PARAMS) -> float:
    """P(at least one repeat_visit_required among a request's incidents | any incident)."""
    q = params.incidents.incident_type_mix.value["repeat_visit_required"]
    return sum(
        pk * (1 - (1 - q) ** k)
        for k, pk in params.incidents.incidents_per_request_mix.value.items()
    )


def expected_totals(params: Parameters = PARAMS) -> dict[str, float]:
    """Analytic expected counts for the whole window."""
    weekly_new = weekly_expected_new(params)
    new = sum(weekly_new)
    cancel = params.requests.cancel_rate.value
    inc_rate = params.incidents.request_incident_rate.value
    # Children (repeat visits) are requests too, and can themselves spawn children.
    child_rate = (1 - cancel) * inc_rate * child_prob_given_incident(params)
    scale = 1 / (1 - child_rate)
    total = new * scale
    cancelled = total * cancel
    shares = params.window.open_status_share_by_week_from_end.value
    n = params.window.n_weeks.value
    non_terminal = sum(weekly_new[n - k] * scale * (1 - cancel) * shares[k] for k in shares)
    completed = total - cancelled - non_terminal
    incident_requests = completed * inc_rate
    incidents = incident_requests * mean_incidents_per_request(params)
    fb_inc = incident_requests * params.feedback.response_rate_incident.value
    fb_none = (completed - incident_requests) * params.feedback.response_rate_no_incident.value
    feedback = fb_inc + fb_none
    miss = expected_sla_miss_rate(params)
    missed_sla_incidents = incidents * params.incidents.incident_type_mix.value["missed_sla"]
    return {
        "new_requests": new,
        "child_requests": total - new,
        "requests": total,
        "cancelled": cancelled,
        "non_terminal_final_weeks": non_terminal,
        "completed": completed,
        "incident_requests": incident_requests,
        "incidents": incidents,
        "incidents_per_completed": incidents / completed,
        "feedback": feedback,
        "feedback_per_completed": feedback / completed,
        "feedback_incident": fb_inc,
        "feedback_no_incident": fb_none,
        "feedback_incident_share": fb_inc / feedback,
        "sla_misses": completed * miss,
        "missed_sla_incidents": missed_sla_incidents,
        "missed_sla_incident_share_of_misses": missed_sla_incidents / (completed * miss),
    }


def incident_row_sentiment(params: Parameters = PARAMS) -> dict[str, float]:
    """Sentiment distribution on incident rows, mixing the coupling table by max severity."""
    table = params.sentiment.incident_sentiment_by_severity.value
    msd = max_severity_dist(params)
    return {se: sum(msd[s] * table[s][se] for s in SEVERITIES) for se in SENTIMENTS}


def solve_no_incident_distribution(
    target: Mapping[str, float], incident_dist: Mapping[str, float], incident_share: float
) -> dict[str, float]:
    """No-incident sentiment mix so that the overall mix equals `target`.

    target = f * incident + (1 - f) * no_incident  =>  no_incident = (target - f*inc)/(1 - f).
    Raises ValueError if any solved value falls outside [0, 1].
    """
    f = incident_share
    if not 0 <= f < 1:
        raise ValueError(f"incident share {f} must be in [0, 1)")
    solved = {se: (target[se] - f * incident_dist[se]) / (1 - f) for se in SENTIMENTS}
    bad = {k: v for k, v in solved.items() if not -1e-12 <= v <= 1 + 1e-12}
    if bad:
        raise ValueError(f"infeasible no-incident sentiment values: {bad}")
    return solved


def no_incident_sentiment(params: Parameters = PARAMS) -> dict[str, float]:
    return solve_no_incident_distribution(
        params.sentiment.target_mix.value,
        incident_row_sentiment(params),
        expected_totals(params)["feedback_incident_share"],
    )


def style_given_sentiment(params: Parameters = PARAMS) -> dict[str, dict[str, float]]:
    """P(style | sentiment) from the hard-case shares of all feedback."""
    target = params.sentiment.target_mix.value
    hard = params.sentiment.hard_case_shares.value
    out = {}
    for se in SENTIMENTS:
        d = {st: hard.get((se, st), 0.0) / target[se] for st in ALLOWED_STYLES[se] if st != "plain"}
        d["plain"] = 1 - sum(d.values())
        out[se] = d
    return out


def expected_cell_counts(params: Parameters = PARAMS) -> list[dict]:
    """Expected feedback rows per ADR-036 corpus cell, and the corpus size each needs.

    No-incident cells key on (sentiment, style, service_type); incident cells on
    (sentiment, style, incident level, incident type) using the linked incident.
    """
    tot = expected_totals(params)
    p0 = no_incident_sentiment(params)
    styles = style_given_sentiment(params)
    svc = expected_service_mix(params)
    msd = max_severity_dist(params)
    coupling = params.sentiment.incident_sentiment_by_severity.value
    level_of = params.corpus.incident_context_by_severity.value
    types = params.incidents.incident_type_mix.value

    level_p = dict.fromkeys(("minor", "serious"), 0.0)
    level_sent = {lv: dict.fromkeys(SENTIMENTS, 0.0) for lv in level_p}
    for s in SEVERITIES:
        lv = level_of[s]
        level_p[lv] += msd[s]
        for se in SENTIMENTS:
            level_sent[lv][se] += msd[s] * coupling[s][se]
    for lv in level_sent:
        level_sent[lv] = {se: v / level_p[lv] for se, v in level_sent[lv].items()}

    cells = []
    for se in SENTIMENTS:
        for st in ALLOWED_STYLES[se]:
            for sv in SERVICE_TYPES:
                exp = tot["feedback_no_incident"] * p0[se] * styles[se][st] * svc[sv]
                cells.append(
                    {
                        "sentiment": se,
                        "style": st,
                        "context": "none",
                        "service_type": sv,
                        "incident_type": None,
                        "expected": exp,
                    }
                )
            for lv in ("minor", "serious"):
                if not is_allowed(se, st, lv):
                    continue
                for it in INCIDENT_TYPES:
                    exp = (
                        tot["feedback_incident"]
                        * level_p[lv]
                        * level_sent[lv][se]
                        * styles[se][st]
                        * types[it]
                    )
                    cells.append(
                        {
                            "sentiment": se,
                            "style": st,
                            "context": lv,
                            "service_type": None,
                            "incident_type": it,
                            "expected": exp,
                        }
                    )

    floor = params.corpus.cell_floor.value
    spare = params.corpus.spare_rate.value
    doubles = set(params.corpus.double_cells.value)
    for c in cells:
        mult = (
            params.corpus.double_multiplier.value if (c["sentiment"], c["style"]) in doubles else 1
        )
        c["floor_binds"] = c["expected"] < floor
        c["required"] = math.ceil(max(floor, c["expected"]) * (1 + spare) * mult)
    return cells


def corpus_summary(params: Parameters = PARAMS) -> dict:
    cells = expected_cell_counts(params)
    total = sum(c["required"] for c in cells)
    return {
        "cells": len(cells),
        "cells_no_incident": sum(c["context"] == "none" for c in cells),
        "cells_incident": sum(c["context"] != "none" for c in cells),
        "cells_floor_binds": sum(c["floor_binds"] for c in cells),
        "expected_rows": sum(c["expected"] for c in cells),
        "required_comments": total,
        "flash_lite_requests": math.ceil(total / params.corpus.batch_size.value),
    }


def anomaly_volume_dip(params: Parameters = PARAMS) -> dict:
    """How visible the volume anomaly is in weekly totals, against noise."""
    a = params.anomalies.volume_drop.value
    weekly = weekly_expected_new(params)
    tot = expected_totals(params)
    scale = tot["requests"] / tot["new_requests"]
    share = account_volume_shares(params)[a["account_rank"] - 1]
    out = []
    for w in range(a["start_week"], a["start_week"] + a["n_weeks"]):
        expected = weekly[w] * scale
        dip = expected * share * a["drop"]
        noise_sd = expected * params.volume.weekly_noise_sd.value
        poisson_sd = math.sqrt(expected)
        combined = math.hypot(noise_sd, poisson_sd)
        out.append(
            {
                "week": w,
                "week_start": week_start(w, params).isoformat(),
                "expected_total": expected,
                "expected_dip": dip,
                "dip_fraction": share * a["drop"],
                "noise_sd": noise_sd,
                "poisson_sd": poisson_sd,
                "combined_sd": combined,
                "z": dip / combined,
            }
        )
    z_two = sum(o["expected_dip"] for o in out) / math.sqrt(sum(o["combined_sd"] ** 2 for o in out))
    return {"weeks": out, "z_combined_window": z_two}


# --------------------------------------------------------------------------- persistence

#: param_group by domain. Only the five existing values are used; "*" marks a
#: provisional mapping where no group really fits (reported, not silently accepted).
GROUP_BY_DOMAIN: Mapping[str, tuple[str, bool]] = MappingProxyType(
    {
        "seed": ("volume", True),
        "window": ("volume", True),
        "reference": ("volume", True),
        "volume": ("volume", False),
        "requests": ("volume", True),
        "billing": ("billing", False),
        "incidents": ("incidents", False),
        "feedback": ("sentiment", True),
        "sentiment": ("sentiment", False),
        "corpus": ("sentiment", True),
        "anomalies": ("anomalies", False),
        "derived_volume": ("volume", False),
        "derived_sentiment": ("sentiment", False),
        "derived_requests": ("volume", True),
    }
)


def json_safe(v: Any) -> Any:
    if isinstance(v, Mapping):
        return {
            (",".join(map(str, k)) if isinstance(k, tuple) else str(k)): json_safe(x)
            for k, x in v.items()
        }
    if isinstance(v, tuple | list):
        return [json_safe(x) for x in v]
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float) and not math.isfinite(v):
        raise ValueError(f"non-finite value {v}")
    return v


def provisional_group_mappings() -> list[str]:
    return sorted(d for d, (_, prov) in GROUP_BY_DOMAIN.items() if prov)


def to_generation_parameters_rows(params: Parameters = PARAMS) -> list[tuple[str, Any, str, str]]:
    """(param_key, JSON-safe value, param_group, notes) for generation_parameters.

    Includes the seed, every parameter, and the key derived values (solved sentiment,
    Zipf exponent, SLA mu, base volume), so the table alone reproduces the world.
    """
    rows = [
        (
            "seed.master_seed",
            MASTER_SEED,
            GROUP_BY_DOMAIN["seed"][0],
            "Master seed; each stage derives its own SeedSequence from it and the stage name.",
        ),
        (
            "seed.stage_keys",
            {s: str(stage_key(s)) for s in STAGES},
            GROUP_BY_DOMAIN["seed"][0],
            "Per-stage entropy: first 8 bytes of sha256(stage name), as decimal strings.",
        ),
    ]
    for domain, name, p in iter_params(params):
        note = p.note + (" [value chosen in parameters.py]" if p.chosen else "")
        rows.append((f"{domain}.{name}", json_safe(p.value), GROUP_BY_DOMAIN[domain][0], note))
    derived = [
        (
            "derived_volume",
            "base_weekly_requests",
            base_weekly_requests(params),
            "Expected first-week volume before season, solved from expected_new_requests.",
        ),
        (
            "derived_volume",
            "seasonal_range",
            seasonal_range(params),
            "Normalized daily seasonal factor extremes.",
        ),
        (
            "derived_volume",
            "account_zipf_exponent",
            zipf_exponent(params),
            "Zipf exponent over requesting accounts giving the largest-account share.",
        ),
        (
            "derived_requests",
            "completion_ratio_mu",
            completion_ratio_mu(params),
            "Lognormal mu of duration/window per priority, solved from sla_met_target.",
        ),
        (
            "derived_sentiment",
            "incident_row_sentiment",
            incident_row_sentiment(params),
            "Sentiment on incident rows after mixing the coupling by max severity.",
        ),
        (
            "derived_sentiment",
            "no_incident_sentiment",
            no_incident_sentiment(params),
            "Solved no-incident sentiment so the overall mix hits target_mix.",
        ),
        (
            "derived_sentiment",
            "style_given_sentiment",
            style_given_sentiment(params),
            "P(style | sentiment) implied by hard_case_shares.",
        ),
    ]
    for domain, name, value, note in derived:
        rows.append((f"{domain}.{name}", json_safe(value), GROUP_BY_DOMAIN[domain][0], note))
    return rows


# --------------------------------------------------------------------------- validation


def _parse_sla_matrix_from_dictionary(path: Path = DICTIONARY) -> dict[str, dict[str, int]]:
    text = path.read_text(encoding="utf-8")
    block = text.split("**SLA defaults by tier (minutes)", 1)[1].split("\n\n", 2)[1]
    out = {}
    for line in block.splitlines():
        m = re.match(r"\|\s*`(\w+)`\s*\|(.*)\|\s*$", line)
        if m:
            cells = [c.strip() for c in m.group(2).split("|")]
            nums = [int(re.match(r"\d+", c).group()) for c in cells]
            out[m.group(1)] = dict(zip(PRIORITIES, nums, strict=True))
    return out


def _vocab_checks(params: Parameters) -> list[str]:
    """Categorical keys must match db_models.enums exactly."""
    import db_models.enums as e  # lazy: parameters.py itself needs no database package

    def vals(enum):
        return set(e.values(enum))

    r, b, i, f, s, ref = (
        params.requests,
        params.billing,
        params.incidents,
        params.feedback,
        params.sentiment,
        params.reference,
    )
    checks = [
        ("service_type_mix", set(params.volume.service_type_mix.value), vals(e.ServiceType)),
        ("priority_mix", set(r.priority_mix.value), vals(e.PriorityTier)),
        (
            "cancellation_reason_mix",
            set(r.cancellation_reason_mix.value),
            vals(e.CancellationReason),
        ),
        ("sla tiers", set(r.sla_window_minutes.value), vals(e.ContractTier)),
        ("payment_method_mix", set(b.payment_method_mix.value), vals(e.PaymentMethod)),
        ("surcharge_rate_by_method", set(b.surcharge_rate_by_method.value), vals(e.PaymentMethod)),
        ("payment_status_mix", set(b.payment_status_mix.value), vals(e.PaymentStatus)),
        ("incident_type_mix", set(i.incident_type_mix.value), vals(e.IncidentType)),
        ("severity_mix", set(i.severity_mix.value), vals(e.Severity)),
        ("incident_status_mix", set(i.incident_status_mix.value), vals(e.IncidentStatus)),
        ("root_cause_by_type keys", set(i.root_cause_by_type.value), vals(e.IncidentType)),
        ("attribution_prob_by_type", set(i.attribution_prob_by_type.value), vals(e.IncidentType)),
        ("credit_by_type", set(i.credit_by_type.value), vals(e.IncidentType)),
        ("channel_mix", set(f.channel_mix.value), vals(e.ResponseChannel)),
        ("target_mix", set(s.target_mix.value), vals(e.TrueSentiment)),
        ("contract_tier_mix", set(ref.contract_tier_mix.value), vals(e.ContractTier)),
        ("account_status_mix", set(ref.account_status_mix.value), vals(e.AccountStatus)),
        ("technician_status_mix", set(ref.technician_status_mix.value), vals(e.TechnicianStatus)),
        ("skill_mix", set(ref.skill_mix.value), vals(e.Skill)),
        ("proficiency_mix", set(ref.proficiency_mix.value), vals(e.Proficiency)),
        ("contact_role_mix", set(ref.contact_role_mix.value), vals(e.ContactRole)),
        ("internal_user_role_counts", set(ref.internal_user_role_counts.value), vals(e.UserRole)),
        (
            "internal_user_status_counts",
            set(ref.internal_user_status_counts.value),
            vals(e.UserStatus),
        ),
    ]
    problems = [
        f"{name}: keys {sorted(got)} != enum {sorted(want)}"
        for name, got, want in checks
        if got != want
    ]
    for t, d in i.root_cause_by_type.value.items():
        if not set(d) <= vals(e.RootCauseCategory):
            problems.append(f"root_cause_by_type[{t}] has unknown causes {set(d)}")
    if not set(params.window.open_status_mix.value) <= vals(e.RequestStatus) - {
        "completed",
        "cancelled",
    }:
        problems.append("open_status_mix must hold non-terminal request statuses only")
    if set(HARD_CASE_BY_STYLE.values()) != vals(e.HardCaseType):
        problems.append("HARD_CASE_BY_STYLE does not cover HardCaseType")
    return problems


def validate_parameters(params: Parameters = PARAMS) -> None:
    """Raise ValueError listing every problem. Called by tests, not at import."""
    problems: list[str] = []

    # 1. Distributions sum to 1.
    for domain, name, p in iter_params(params):
        dists = (
            {name: p.value}
            if p.kind == "dist"
            else ({f"{name}[{k}]": v for k, v in p.value.items()} if p.kind == "dist_by" else {})
        )
        for label, d in dists.items():
            total = sum(d.values())
            if abs(total - 1) > 1e-9:
                problems.append(f"{domain}.{label} sums to {total!r}")
            if any(v < 0 for v in d.values()):
                problems.append(f"{domain}.{label} has a negative probability")
    bins = params.requests.equipment_unit_count_bins.value
    if abs(sum(b[2] for b in bins) - 1) > 1e-9:
        problems.append("equipment_unit_count_bins probabilities do not sum to 1")

    # Exact counts agree with their totals.
    ref = params.reference
    for name, counts, n in (
        ("contract_tier_counts", ref.contract_tier_counts.value, ref.n_accounts.value),
        ("account_status_counts", ref.account_status_counts.value, ref.n_accounts.value),
        ("technician_status_counts", ref.technician_status_counts.value, ref.n_technicians.value),
        (
            "internal_user_role_counts",
            ref.internal_user_role_counts.value,
            ref.n_internal_users.value,
        ),
        (
            "internal_user_status_counts",
            ref.internal_user_status_counts.value,
            ref.n_internal_users.value,
        ),
    ):
        if sum(counts.values()) != n:
            problems.append(f"{name} sums to {sum(counts.values())}, expected {n}")

    # 2. Totals within data-dictionary §6 ranges.
    t = expected_totals(params)
    if not 15_000 <= t["requests"] <= 25_000:
        problems.append(f"expected requests {t['requests']:.0f} outside 15,000-25,000")
    if not 18_000 <= t["new_requests"] <= 22_000:
        problems.append(f"expected new requests {t['new_requests']:.0f} outside 18,000-22,000")
    if not 0.35 <= t["feedback_per_completed"] <= 0.50:
        problems.append(f"feedback {t['feedback_per_completed']:.3f} of completed outside 35-50%")
    if not 0.08 <= t["incidents_per_completed"] <= 0.12:
        problems.append(f"incidents {t['incidents_per_completed']:.3f} of completed outside 8-12%")
    if t["missed_sla_incidents"] > t["sla_misses"]:
        problems.append("more missed_sla incidents expected than SLA misses")
    loc_lo, loc_hi = ref.locations_per_account.value
    if not 150 <= ref.n_accounts.value * (loc_lo + loc_hi) / 2 <= 250:
        problems.append("expected locations outside 150-250")

    # 3. Sentiment solve feasible and reproducing the targets.
    try:
        p0 = no_incident_sentiment(params)
        inc = incident_row_sentiment(params)
        f = t["feedback_incident_share"]
        for se, target in params.sentiment.target_mix.value.items():
            got = f * inc[se] + (1 - f) * p0[se]
            if abs(got - target) > 1e-9:
                problems.append(f"sentiment {se}: overall {got} != target {target}")
    except ValueError as exc:
        problems.append(str(exc))
    for sev, d in params.sentiment.incident_sentiment_by_severity.value.items():
        if d["neutral"] != 0:
            problems.append(f"neutral must be 0 on incident rows (severity {sev}, ADR-036)")

    # 4. Hard cases feasible and allowed by the cell rules.
    target = params.sentiment.target_mix.value
    for se, st in params.sentiment.hard_case_shares.value:
        if st not in ALLOWED_STYLES[se]:
            problems.append(f"hard case ({se}, {st}) forbidden by ADR-036 cell rules")
    for se in SENTIMENTS:
        hard = sum(v for (s, _), v in params.sentiment.hard_case_shares.value.items() if s == se)
        if hard > target[se]:
            problems.append(f"hard cases for {se} ({hard}) exceed its share ({target[se]})")
    if abs(sum(params.sentiment.hard_case_shares.value.values()) - 0.15) > 1e-9:
        problems.append("hard_case_shares must total 0.15 (ADR-019)")

    # 5. Anomalies inside the window and outside the holdout.
    hs = holdout_start_week(params)
    for name, a in (
        ("volume_drop", params.anomalies.volume_drop.value),
        ("billing_surcharge", params.anomalies.billing_surcharge.value),
    ):
        if a["start_week"] < 0 or a["start_week"] + a["n_weeks"] > hs:
            problems.append(f"anomaly {name} weeks overlap the holdout or leave the window")
    if params.anomalies.billing_surcharge.value["payment_method"] not in (
        params.billing.surcharge_rate_by_method.value
    ):
        problems.append("billing anomaly payment_method unknown")

    # 6. SLA matrix matches §2, and the Zipf solve hit its target.
    try:
        documented = _parse_sla_matrix_from_dictionary()
        encoded = {k: dict(v) for k, v in params.requests.sla_window_minutes.value.items()}
        if documented != encoded:
            problems.append(f"SLA matrix {encoded} != data-dictionary §2 {documented}")
    except (OSError, IndexError, AttributeError) as exc:
        problems.append(f"could not read the §2 SLA matrix: {exc!r}")
    if abs(account_volume_shares(params)[0] - ref.largest_account_volume_share.value) > 1e-6:
        problems.append("Zipf solve missed the largest-account share")

    # 7. Vocabularies match the schema.
    problems += _vocab_checks(params)

    if problems:
        raise ValueError("invalid parameters:\n  " + "\n  ".join(problems))


# --------------------------------------------------------------------------- summary


def summary(params: Parameters = PARAMS) -> dict:
    return {
        "totals": expected_totals(params),
        "seasonal_range": seasonal_range(params),
        "base_weekly_requests": base_weekly_requests(params),
        "zipf_exponent": zipf_exponent(params),
        "expected_service_mix": expected_service_mix(params),
        "completion_ratio_mu": completion_ratio_mu(params),
        "max_severity_dist": max_severity_dist(params),
        "incident_row_sentiment": incident_row_sentiment(params),
        "no_incident_sentiment": no_incident_sentiment(params),
        "style_given_sentiment": style_given_sentiment(params),
        "corpus": corpus_summary(params),
        "anomaly_volume_dip": anomaly_volume_dip(params),
        "holdout_start": week_start(holdout_start_week(params), params).isoformat(),
        "provisional_groups": provisional_group_mappings(),
        "n_rows": len(to_generation_parameters_rows(params)),
    }


if __name__ == "__main__":
    validate_parameters()
    print(json.dumps(json_safe(summary()), indent=2, default=str))
