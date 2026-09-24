"""Build the synthetic dataset in memory: pure and deterministic.

`generate(corpus_path)` builds every generated table from parameters.py and a frozen
corpus file and returns the rows keyed by table name, in foreign-key order. There is no
database access, no network call and no wall-clock read, so the same seed and the same
corpus give identical output. load.py writes the result to Postgres.

Each stage draws only from its own `derive_seed(<stage>)` generator:

    reference          accounts, contacts, locations, technicians, skills, internal users
    volume             weekly noise and Poisson request counts per site
    requests           request attributes, lifecycle timestamps, repeat-visit children
    incidents          incident counts, types, severity, status and timing
    billing            charges, payment method and status, incident credits
    feedback           survey responses and their timing
    sentiment          true sentiment, style (hard case) and rating
    corpus_assignment  which corpus comment each feedback row receives

The three anomalies are fixed multipliers inside the volume and billing stages, so the
`anomalies` stage makes no draws.

Surrogate keys are explicit and assigned in generation order (load.py inserts them with
OVERRIDING SYSTEM VALUE). Timestamps are UTC-aware; scheduled hours follow the hour-of-day
weights in each site's local time (reference_data.STATE_TIMEZONE).

Rules that parameters.py leaves open are the constants under "Rules chosen here".

Docs: data-dictionary.md §2-§8; ADR-018, -021, -030, -036 to -039.
"""

from __future__ import annotations

import bisect
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parameters as prm  # noqa: E402
import reference_data as ref  # noqa: E402

#: Every generated table, in foreign-key (insert) order.
TABLES: tuple[str, ...] = (
    "accounts",
    "contacts",
    "locations",
    "technicians",
    "technician_skills",
    "internal_users",
    "service_requests",
    "archived_requests",
    "incidents",
    "service_feedback",
    "sentiment_labels",
    "generation_parameters",
)

# --------------------------------------------------------------------------- rules chosen here
# parameters.py leaves these open. They are candidates to move into parameters.py so they
# are persisted to generation_parameters (see the feat/generate report).

#: The dataset is a snapshot taken this long after the window end (Monday 00:00 UTC).
AS_OF_AFTER_WINDOW_END = timedelta(hours=12)
#: Requesting accounts were onboarded this many years before the window start (uniform).
ONBOARDED_YEARS_BEFORE = (0.5, 6.0)
#: Prospect accounts were created within this many final weeks of the window.
PROSPECT_RECENT_WEEKS = 26
#: An inactive account's requests stop from a week drawn uniformly from this span of the
#: window (fractions of n_weeks); its volume share passes to the remaining accounts.
INACTIVE_STOP_SPAN = (0.25, 0.85)
#: A terminated technician's change date is drawn from this span of the window.
TERMINATED_SPAN = (0.15, 0.95)
#: An on-leave technician's leave began this many weeks before the window end (uniform).
ON_LEAVE_WEEKS_BEFORE_END = (1, 12)
#: An inactive internal user was deactivated at a point drawn from this span of the window.
INACTIVE_USER_SPAN = (0.25, 0.90)
#: P(a request's technician comes from the site's region, when one is available there).
HOME_REGION_PREFERENCE = 0.80
#: Weight of site contacts when choosing a request's contact; other roles weigh 1.
SITE_CONTACT_WEIGHT = 3.0
REQUEST_CREATOR_ROLES = ("dispatcher",)
INCIDENT_CREATOR_ROLES = ("supervisor", "qa_analyst")
#: Scheduled minutes are quarter-hour slots.
SCHEDULE_MINUTES = (0, 15, 30, 45)
#: Booking lead time before the scheduled slot: lognormal, median hours by priority.
LEAD_MEDIAN_HOURS = {"standard": 72.0, "urgent": 12.0, "critical": 2.0}
LEAD_SIGMA = 0.8
#: A no-show is cancelled this many hours after dispatch; other cancellations fall at a
#: uniform point between booking and the scheduled slot.
NO_SHOW_CANCEL_HOURS = (0.5, 3.0)
INCIDENT_REPORT_MEDIAN_HOURS, INCIDENT_REPORT_SIGMA = 18.0, 1.0
INCIDENT_LOG_HOURS = (0.0, 4.0)
INCIDENT_RESOLVE_MEDIAN_DAYS, INCIDENT_RESOLVE_SIGMA = 5.0, 0.8
FEEDBACK_MEDIAN_HOURS, FEEDBACK_SIGMA = 20.0, 0.9
ARCHIVE_HOURS = (1.0, 48.0)
DISPUTE_UPDATE_DAYS = (1.0, 30.0)
#: Region location counts may exceed their share by this many while balancing volume.
REGION_COUNT_SLACK = 2
SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2}

CENT = Decimal("0.01")
RATE = Decimal("0.0001")

# --------------------------------------------------------------------------- corpus

#: Fields generate.py needs from each feedback_text.jsonl record (build_corpus.finalize).
CORPUS_FIELDS = (
    "corpus_id",
    "text",
    "intended_sentiment",
    "style",
    "hard_case_type",
    "cell",
    "context",
    "service_type",
    "incident_type",
    "channel",
)


class CorpusError(ValueError):
    """The corpus file is malformed or inconsistent with the cell rules."""


class CorpusExhaustedError(RuntimeError):
    """A corpus cell holds fewer comments than the dataset needs (ADR-038: never reuse or
    borrow across cells)."""


def load_corpus(path: str | Path, params: prm.Parameters = prm.PARAMS) -> dict[str, list[dict]]:
    """Read a feedback_text.jsonl corpus into {cell: records sorted by corpus_id}.

    Every record is checked against the cell rules: its cell key must match its own
    sentiment, style, context and detail, be a corpus cell (ADR-036, ADR-039), and carry
    the hard-case type and a channel the parameters know.
    """
    channels = set(params.feedback.channel_mix.value)
    by_cell: dict[str, list[dict]] = defaultdict(list)
    seen: set[str] = set()
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if not line.strip():
                continue
            rec = json.loads(line)
            missing = [k for k in CORPUS_FIELDS if k not in rec]
            if missing:
                raise CorpusError(f"{path} line {n}: missing fields {missing}")
            cid = rec["corpus_id"]
            if cid in seen:
                raise CorpusError(f"{path} line {n}: duplicate corpus_id {cid}")
            seen.add(cid)
            se, st, ctx = rec["intended_sentiment"], rec["style"], rec["context"]
            if not prm.is_corpus_cell(se, st, ctx):
                raise CorpusError(f"{cid}: ({se}, {st}, {ctx}) is not a corpus cell")
            detail = rec["service_type"] if ctx == "none" else rec["incident_type"]
            key = prm.corpus_cell_key(se, st, ctx, detail)
            if key != rec["cell"]:
                raise CorpusError(f"{cid}: cell {rec['cell']!r} does not match its fields ({key})")
            if rec["hard_case_type"] != prm.HARD_CASE_BY_STYLE[st]:
                raise CorpusError(f"{cid}: hard_case_type does not match style {st}")
            if rec["channel"] not in channels:
                raise CorpusError(f"{cid}: unknown channel {rec['channel']!r}")
            if not rec["text"]:
                raise CorpusError(f"{cid}: empty text")
            by_cell[key].append(rec)
    for recs in by_cell.values():
        recs.sort(key=lambda r: r["corpus_id"])
    return dict(by_cell)


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# --------------------------------------------------------------------------- helpers


class _Dist:
    """A categorical distribution drawn with one uniform: keys[bisect(cdf, u)]."""

    __slots__ = ("keys", "cdf", "_excl")

    def __init__(self, mapping: Mapping):
        keys = list(mapping)
        w = [float(mapping[k]) for k in keys]
        total = sum(w)
        if total <= 0 or any(x < 0 for x in w):
            raise ValueError(f"not a distribution: {dict(mapping)}")
        cdf, acc = [], 0.0
        for x in w:
            acc += x / total
            cdf.append(acc)
        cdf[-1] = 1.0
        self.keys, self.cdf = keys, cdf
        self._excl: dict[frozenset, _Dist] = {}

    def draw(self, rng: np.random.Generator):
        return self.keys[bisect.bisect_right(self.cdf, rng.random())]

    def excluding(self, keys: frozenset) -> _Dist:
        """The same distribution renormalized without `keys` (cached)."""
        if not keys:
            return self
        if keys not in self._excl:
            prev = 0.0
            weights = {}
            for k, c in zip(self.keys, self.cdf, strict=True):
                if k not in keys:
                    weights[k] = c - prev
                prev = c
            self._excl[keys] = _Dist(weights)
        return self._excl[keys]


def _lognormal(rng: np.random.Generator, median: float, sigma: float) -> float:
    return float(rng.lognormal(math.log(median), sigma))


def _uniform(rng: np.random.Generator, lo: float, hi: float) -> float:
    return float(rng.uniform(lo, hi))


def money(x: float | Decimal) -> Decimal:
    """DECIMAL(10,2), rounded half-up (§6)."""
    return Decimal(repr(float(x))).quantize(CENT, ROUND_HALF_UP)


def total_invoice(labor: Decimal, parts: Decimal, rate: Decimal) -> Decimal:
    """§6: (labor + parts) * (1 + surcharge_rate), rounded half-up to 2 decimals."""
    return ((labor + parts) * (1 + rate)).quantize(CENT, ROUND_HALF_UP)


def _minute(t: datetime) -> datetime:
    return t.replace(second=0, microsecond=0)


@dataclass(slots=True)
class _Incident:
    incident_id: int
    request: _Request
    incident_type: str
    severity: str
    status: str
    root_cause: str | None
    attributed_technician_id: int | None
    reported_at: datetime
    created_at: datetime
    resolved_at: datetime | None
    created_by_user_id: int
    credit: Decimal | None = None


@dataclass(slots=True)
class _Request:
    request_id: int
    account_id: int
    location_id: int
    contact_id: int
    service_type: str
    priority: str
    units: int
    scheduled: datetime
    week: int
    sla_window: int
    payment_method: str
    created_at: datetime
    created_by_user_id: int
    parent_id: int | None = None
    status: str = "open"
    technician_id: int | None = None
    dispatched_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancellation_reason: str | None = None
    completed_at: datetime | None = None
    incidents: list[_Incident] = field(default_factory=list)
    total_invoice: Decimal | None = None

    @property
    def sla_met(self) -> bool | None:
        if self.completed_at is None or self.dispatched_at is None:
            return None
        return self.completed_at <= self.dispatched_at + timedelta(minutes=self.sla_window)

    def updated_at(self) -> datetime:
        return self.completed_at or self.cancelled_at or self.dispatched_at or self.created_at


# --------------------------------------------------------------------------- generator


class _Generator:
    def __init__(self, corpus: dict[str, list[dict]], corpus_sha: str, params, scale: float):
        if not scale > 0:
            raise ValueError("scale must be positive")
        self.p = params
        self.corpus = corpus
        self.corpus_sha = corpus_sha
        self.scale = scale
        w = params.window
        self.start_day: date = w.start_monday.value
        self.n_weeks: int = w.n_weeks.value
        self.window_start = datetime.combine(self.start_day, time(), tzinfo=UTC)
        self.window_end = self.window_start + timedelta(weeks=self.n_weeks)
        self.as_of = self.window_end + AS_OF_AFTER_WINDOW_END
        self.weekly_expected = prm.weekly_expected_new(params)
        self.rngs: dict[str, np.random.Generator] = {}
        self.tables: dict[str, list[dict]] = {t: [] for t in TABLES}
        self.requests: list[_Request] = []
        self.incidents: list[_Incident] = []

    def rng(self, stage: str) -> np.random.Generator:
        if stage not in self.rngs:
            self.rngs[stage] = np.random.default_rng(prm.derive_seed(stage))
        return self.rngs[stage]

    # ----------------------------------------------------------------- small utilities

    def week_of(self, t: datetime) -> int:
        return (t.astimezone(UTC).date() - self.start_day).days // 7

    def before_as_of(self, rng, start: datetime, t: datetime) -> datetime:
        """`t`, or a uniform point between `start` and the snapshot if `t` is after it."""
        if t <= self.as_of:
            return t
        return start + (self.as_of - start) * _uniform(rng, 0.0, 1.0)

    def window_point(self, rng, span: tuple[float, float]) -> datetime:
        frac = _uniform(rng, *span)
        return _minute(self.window_start + (self.window_end - self.window_start) * frac)

    # ----------------------------------------------------------------- reference

    def build_reference(self) -> None:
        rng = self.rng(prm.STAGE_REFERENCE)
        r = self.p.reference
        n_acc = r.n_accounts.value

        def exact(counts: Mapping[str, int]) -> list[str]:
            items = [k for k, c in counts.items() for _ in range(c)]
            return [items[i] for i in rng.permutation(len(items))]

        tiers = exact(r.contract_tier_counts.value)
        statuses = exact(r.account_status_counts.value)
        combos = [
            f"{a} {b} {c}"
            for a in ref.COMPANY_PREFIXES
            for b in ref.COMPANY_INDUSTRIES
            for c in ref.COMPANY_SUFFIXES
        ]
        names = [combos[i] for i in rng.choice(len(combos), n_acc, replace=False)]

        self.accounts: dict[int, dict] = {}
        for i in range(n_acc):
            aid = i + 1
            status = statuses[i]
            if status == "prospect":
                created = self.window_end - timedelta(weeks=PROSPECT_RECENT_WEEKS) * _uniform(
                    rng, 0.0, 1.0
                )
            else:
                years = _uniform(rng, *ONBOARDED_YEARS_BEFORE)
                created = self.window_start - timedelta(days=365.25 * years)
            stop_at = None
            if status == "inactive":
                lo, hi = (math.floor(f * self.n_weeks) for f in INACTIVE_STOP_SPAN)
                stop_week = int(rng.integers(lo, hi + 1))
                stop_at = self.window_start + timedelta(weeks=stop_week)
            self.accounts[aid] = {
                "row": {
                    "account_id": aid,
                    "account_code": f"ACC-{aid:04d}",
                    "account_name": names[i],
                    "account_status": status,
                    "contract_tier": tiers[i],
                    "created_at": _minute(created),
                },
                "stop_at": stop_at,
                "requesting": status != "prospect" or r.prospects_get_requests.value,
            }
            if status == "inactive" and not r.inactive_accounts_get_requests.value:
                self.accounts[aid]["requesting"] = False
        self._rank_accounts(rng)
        self._build_contacts(rng)
        self._build_locations(rng)
        self._build_people(rng)

    def _rank_accounts(self, rng) -> None:
        """Zipf volume rank per requesting account. Rank 1 (the largest, and the account
        anomaly's target) is the lowest-id active enterprise account, so it never churns;
        the other ranks are a random permutation."""
        req = [a for a, v in self.accounts.items() if v["requesting"]]
        active = [a for a in req if self.accounts[a]["row"]["account_status"] == "active"]
        enterprise = [a for a in active if self.accounts[a]["row"]["contract_tier"] == "enterprise"]
        top = (enterprise or active)[0]
        rest = [a for a in req if a != top]
        order = [top] + [rest[i] for i in rng.permutation(len(rest))]
        shares = prm.account_volume_shares(self.p)
        if len(shares) != len(order):
            raise ValueError("requesting accounts do not match account_volume_shares()")
        self.base_share = dict(zip(order, shares, strict=True))
        self.top_account = top

        # Weekly shares, renormalized over the accounts still requesting that week.
        self.week_shares: list[dict[int, float]] = []
        for w in range(self.n_weeks):
            start = self.window_start + timedelta(weeks=w)
            live = {
                a: s
                for a, s in self.base_share.items()
                if self.accounts[a]["stop_at"] is None or start < self.accounts[a]["stop_at"]
            }
            tot = sum(live.values())
            self.week_shares.append({a: s / tot for a, s in live.items()})

    def _build_contacts(self, rng) -> None:
        r = self.p.reference
        role = _Dist(r.contact_role_mix.value)
        lo, hi = r.contacts_per_account.value
        self.contacts_by_account: dict[int, list[tuple[int, float]]] = {}
        cid = 0
        for aid in self.accounts:
            self.contacts_by_account[aid] = []
            for _ in range(int(rng.integers(lo, hi + 1))):
                cid += 1
                first = ref.FIRST_NAMES[int(rng.integers(len(ref.FIRST_NAMES)))]
                last = ref.LAST_NAMES[int(rng.integers(len(ref.LAST_NAMES)))]
                area = ref.PHONE_AREA_CODES[int(rng.integers(len(ref.PHONE_AREA_CODES)))]
                crole = role.draw(rng)
                self.tables["contacts"].append(
                    {
                        "contact_id": cid,
                        "account_id": aid,
                        "first_name": first,
                        "last_name": last,
                        "phone": f"{area}-555-01{int(rng.integers(100)):02d}",
                        "email": f"{first}.{last}.{cid}@{ref.EMAIL_DOMAIN}".lower(),
                        "contact_role": crole,
                    }
                )
                weight = SITE_CONTACT_WEIGHT if crole == "site_contact" else 1.0
                self.contacts_by_account[aid].append((cid, weight))

    def _build_locations(self, rng) -> None:
        """Site counts, then regions balanced so each region's share of expected request
        volume (and, within a small slack, of sites) matches regions.share."""
        r = self.p.reference
        lo, hi = r.locations_per_account.value
        n_sites = {aid: int(rng.integers(lo, hi + 1)) for aid in self.accounts}
        weekly = self.weekly_expected
        tot_w = sum(weekly)
        avg_share = defaultdict(float)
        for w, shares in enumerate(self.week_shares):
            for a, s in shares.items():
                avg_share[a] += s * weekly[w] / tot_w

        sites = [(aid, k) for aid in self.accounts for k in range(n_sites[aid])]
        weight = [avg_share[aid] / n_sites[aid] for aid, _ in sites]
        order = [int(i) for i in rng.permutation(len(sites))]
        order.sort(key=lambda i: -weight[i])  # stable: ties keep the shuffled order

        shares = self.p.regions.share.value
        regions = list(shares)
        cap = {g: round(shares[g] * len(sites)) + REGION_COUNT_SLACK for g in regions}
        vol = dict.fromkeys(regions, 0.0)
        cnt = dict.fromkeys(regions, 0)
        region_of: dict[int, str] = {}
        for i in order:
            open_ = [g for g in regions if cnt[g] < cap[g]]
            if weight[i] > 0:
                g = max(open_, key=lambda g: shares[g] - vol[g])
            else:
                g = max(open_, key=lambda g: shares[g] * len(sites) - cnt[g])
            region_of[i] = g
            vol[g] += weight[i]
            cnt[g] += 1

        states = self.p.regions.states.value
        self.locations: dict[int, dict] = {}
        self.sites_by_account: dict[int, list[int]] = defaultdict(list)
        for i, (aid, k) in enumerate(sites):
            lid = i + 1
            g = region_of[i]
            state = states[g][int(rng.integers(len(states[g])))]
            city, zip3 = ref.STATE_CITY[state]
            street = (
                f"{int(rng.integers(100, 9900))} "
                f"{ref.STREET_NAMES[int(rng.integers(len(ref.STREET_NAMES)))]} "
                f"{ref.STREET_SUFFIXES[int(rng.integers(len(ref.STREET_SUFFIXES)))]}"
            )
            self.tables["locations"].append(
                {
                    "location_id": lid,
                    "account_id": aid,
                    "site_name": ref.SITE_NAMES[k],
                    "street_address": street,
                    "city": city,
                    "state": state,
                    "zip_code": f"{zip3}{int(rng.integers(100)):02d}",
                }
            )
            self.locations[lid] = {
                "account_id": aid,
                "region": g,
                "tz": ZoneInfo(ref.STATE_TIMEZONE[state]),
                "frac": 1.0 / n_sites[aid],
            }
            self.sites_by_account[aid].append(lid)

    def _build_people(self, rng) -> None:
        r = self.p.reference
        n_tech, n_user = r.n_technicians.value, r.n_internal_users.value
        combos = [f"{f} {last}" for f in ref.FIRST_NAMES for last in ref.LAST_NAMES]
        picks = rng.choice(len(combos), n_tech + n_user, replace=False)
        names = [combos[int(i)] for i in picks]

        def exact(counts: Mapping[str, int]) -> list[str]:
            items = [k for k, c in counts.items() for _ in range(c)]
            return [items[i] for i in rng.permutation(len(items))]

        # Technicians: home regions by largest remainder over the region shares.
        shares = self.p.regions.share.value
        raw = {g: shares[g] * n_tech for g in shares}
        counts = {g: math.floor(v) for g, v in raw.items()}
        for g in sorted(raw, key=lambda g: raw[g] - counts[g], reverse=True)[
            : n_tech - sum(counts.values())
        ]:
            counts[g] += 1
        home = exact(counts)
        status = exact(r.technician_status_counts.value)
        skill = r.skill_mix.value
        skill_keys = list(skill)
        skill_p = np.array([skill[k] for k in skill_keys])
        prof = _Dist(r.proficiency_mix.value)
        s_lo, s_hi = r.skills_per_technician.value
        self.technicians: list[dict] = []
        for i in range(n_tech):
            tid = i + 1
            change_at = None
            if status[i] == "terminated":
                change_at = self.window_point(rng, TERMINATED_SPAN)
            elif status[i] == "on_leave":
                weeks = _uniform(rng, *ON_LEAVE_WEEKS_BEFORE_END)
                change_at = _minute(self.window_end - timedelta(weeks=weeks))
            self.tables["technicians"].append(
                {
                    "technician_id": tid,
                    "full_name": names[i],
                    "technician_status": status[i],
                    "home_region": home[i],
                }
            )
            self.technicians.append({"id": tid, "region": home[i], "until": change_at})
            k = int(rng.integers(s_lo, s_hi + 1))
            drawn = rng.choice(len(skill_keys), k, replace=False, p=skill_p)
            for s in sorted(skill_keys[int(j)] for j in drawn):
                self.tables["technician_skills"].append(
                    {"technician_id": tid, "skill": s, "proficiency": prof.draw(rng)}
                )

        roles = exact(r.internal_user_role_counts.value)
        ustatus = exact(r.internal_user_status_counts.value)
        self.users: list[dict] = []
        for i in range(n_user):
            uid = i + 1
            until = self.window_point(rng, INACTIVE_USER_SPAN) if ustatus[i] == "inactive" else None
            self.tables["internal_users"].append(
                {
                    "user_id": uid,
                    "full_name": names[n_tech + i],
                    "user_role": roles[i],
                    "user_status": ustatus[i],
                }
            )
            self.users.append({"id": uid, "role": roles[i], "until": until})

    def pick_technician(self, rng, region: str, at: datetime) -> int:
        avail = [t for t in self.technicians if t["until"] is None or at < t["until"]]
        if not avail:
            raise RuntimeError(f"no technician available at {at}")
        local = [t for t in avail if t["region"] == region]
        pool = local if local and rng.random() < HOME_REGION_PREFERENCE else avail
        return pool[int(rng.integers(len(pool)))]["id"]

    def pick_user(self, rng, roles: tuple[str, ...], at: datetime) -> int:
        pool = [
            u for u in self.users if u["role"] in roles and (u["until"] is None or at < u["until"])
        ]
        if not pool:
            raise RuntimeError(f"no active {roles} user at {at}")
        return pool[int(rng.integers(len(pool)))]["id"]

    # ----------------------------------------------------------------- volume

    def build_volume(self) -> list[np.ndarray]:
        """Poisson request counts per (week, location), before any request exists."""
        rng = self.rng(prm.STAGE_VOLUME)
        weekly = self.weekly_expected
        sd = self.p.volume.weekly_noise_sd.value
        acct = self.p.anomalies.volume_drop.value
        reg = self.p.anomalies.regional_drop.value
        acct_weeks = range(acct["start_week"], acct["start_week"] + acct["n_weeks"])
        reg_start = prm.week_index(reg["start"], self.p)
        reg_weeks = range(reg_start, reg_start + reg["n_weeks"])
        lids = sorted(self.locations)
        counts = []
        for w in range(self.n_weeks):
            noise = math.exp(sd * float(rng.standard_normal()) - sd * sd / 2)
            lam = np.zeros(len(lids))
            for j, lid in enumerate(lids):
                loc = self.locations[lid]
                share = self.week_shares[w].get(loc["account_id"], 0.0)
                mult = 1.0
                if w in acct_weeks and loc["account_id"] == self.top_account:
                    mult *= 1 - acct["drop"]
                if w in reg_weeks and loc["region"] == reg["region"]:
                    mult *= 1 - reg["drop"]
                lam[j] = weekly[w] * noise * share * loc["frac"] * mult * self.scale
            counts.append(rng.poisson(lam))
        self.volume_lids = lids
        return counts

    # ----------------------------------------------------------------- requests

    def _schedule(self, rng, day_dist: _Dist | None, day: date | None, lid: int, limit):
        """A scheduled UTC instant at a local business hour; redrawn if not before `limit`."""
        tz = self.locations[lid]["tz"]
        for _ in range(1000):
            d = day_dist.draw(rng) if day_dist is not None else day
            hour = self.hour_dist.draw(rng)
            minute = SCHEDULE_MINUTES[int(rng.integers(len(SCHEDULE_MINUTES)))]
            t = datetime.combine(d, time(hour, minute), tzinfo=tz).astimezone(UTC)
            if t < limit:
                return t
        raise RuntimeError(f"could not schedule a request at location {lid} before {limit}")

    def build_requests(self, counts: list[np.ndarray]) -> None:
        rng = self.rng(prm.STAGE_REQUESTS)
        v = self.p.volume
        rq = self.p.requests
        self.hour_dist = _Dist(v.hour_of_day_weights.value)
        self.priority = _Dist(rq.priority_mix.value)
        self.units = _Dist({i: b[2] for i, b in enumerate(rq.equipment_unit_count_bins.value)})
        self.pay = _Dist(self.p.billing.payment_method_mix.value)
        self.cancel_reason = _Dist(rq.cancellation_reason_mix.value)
        self.open_mix = _Dist(self.p.window.open_status_mix.value)
        self.mu = prm.completion_ratio_mu(self.p)
        inc = self.p.incidents
        self.inc_rates = self.incident_rates()
        self.inc_k = _Dist(inc.incidents_per_request_mix.value)
        self.inc_types = _Dist(inc.incident_type_mix.value)
        self.inc_sev = _Dist(inc.severity_mix.value)
        self.inc_active = _Dist(inc.incident_active_mix.value)
        self.inc_terminal = _Dist(inc.incident_terminal_mix.value)
        self.inc_cause = {t: _Dist(d) for t, d in inc.root_cause_by_type.value.items()}
        dow = list(v.day_of_week_weights.value.values())

        gen: list[_Request] = []
        for w in range(self.n_weeks):
            monday = self.start_day + timedelta(weeks=w)
            days = [monday + timedelta(days=i) for i in range(7)]
            # Within a week, seasonal_factor's normalization cancels, so the raw daily
            # factor gives the same day weights (seasonal_factor recomputes it per call).
            day_dist = _Dist(
                {d: dow[i] * prm._raw_daily_season(d, self.p) for i, d in enumerate(days)}
            )
            svc = _Dist(prm.service_mix_for_week(w, self.p))
            slots = []
            for j, lid in enumerate(self.volume_lids):
                for _ in range(int(counts[w][j])):
                    slots.append((self._schedule(rng, day_dist, None, lid, self.window_end), lid))
            slots.sort(key=lambda s: (s[0], s[1]))
            for scheduled, lid in slots:
                req = self.new_request(rng, lid, scheduled, w, svc.draw(rng))
                gen.append(req)

        # Repeat-visit children are requests too, and can have children of their own.
        while gen:
            self.build_incidents(gen)
            gen = self.build_children(rng, gen)

    def new_request(
        self,
        rng,
        lid: int,
        scheduled: datetime,
        week: int,
        service_type: str,
        parent: _Request | None = None,
    ) -> _Request:
        rq = self.p.requests
        loc = self.locations[lid]
        aid = loc["account_id"]
        acc = self.accounts[aid]["row"]
        priority = self.priority.draw(rng)
        lo, hi, _ = rq.equipment_unit_count_bins.value[self.units.draw(rng)]
        units = int(rng.integers(lo, hi + 1))
        payment = self.pay.draw(rng)
        if parent is not None:
            contact = parent.contact_id
            span = scheduled - parent.completed_at
            created = parent.completed_at + span * _uniform(rng, 0.1, 0.9)
        else:
            cands = self.contacts_by_account[aid]
            contact = cands[_Dist({i: c[1] for i, c in enumerate(cands)}).draw(rng)][0]
            created = scheduled - timedelta(
                hours=_lognormal(rng, LEAD_MEDIAN_HOURS[priority], LEAD_SIGMA)
            )
        created = _minute(created)
        req = _Request(
            request_id=len(self.requests) + 1,
            account_id=aid,
            location_id=lid,
            contact_id=contact,
            service_type=service_type,
            priority=priority,
            units=units,
            scheduled=scheduled,
            week=week,
            sla_window=rq.sla_window_minutes.value[acc["contract_tier"]][priority],
            payment_method=payment,
            created_at=created,
            created_by_user_id=self.pick_user(rng, REQUEST_CREATOR_ROLES, created),
            parent_id=parent.request_id if parent else None,
        )
        self.requests.append(req)

        lag = timedelta(
            minutes=_lognormal(
                rng, rq.dispatch_lag_median_minutes.value[priority], rq.dispatch_lag_sigma.value
            )
        )
        dispatched = scheduled + lag
        if rng.random() < rq.cancel_rate.value:
            req.status = "cancelled"
            req.cancellation_reason = self.cancel_reason.draw(rng)
            if req.cancellation_reason == "client_no_show":
                # The technician went; the client was not there.
                req.dispatched_at = min(dispatched, self.as_of)
                req.technician_id = self.pick_technician(rng, loc["region"], req.dispatched_at)
                wait = timedelta(hours=_uniform(rng, *NO_SHOW_CANCEL_HOURS))
                req.cancelled_at = min(req.dispatched_at + wait, self.as_of)
            else:
                req.cancelled_at = created + (scheduled - created) * _uniform(rng, 0.0, 1.0)
            return req

        ratio = float(rng.lognormal(self.mu[priority], rq.completion_ratio_sigma.value))
        completed = dispatched + timedelta(minutes=ratio * req.sla_window)
        from_end = self.n_weeks - week
        shares = self.p.window.open_status_share_by_week_from_end.value
        if from_end in shares and rng.random() < shares[from_end]:
            status = self.open_mix.draw(rng)
        elif completed > self.as_of:
            status = "in_progress"  # would finish after the snapshot
        else:
            status = "completed"
        if status != "open" and dispatched > self.as_of:
            status = "open"
        req.status = status
        if status != "open":
            req.dispatched_at = dispatched
            req.technician_id = self.pick_technician(rng, loc["region"], dispatched)
        if status == "completed":
            req.completed_at = completed
        return req

    def build_children(self, rng, gen: list[_Request]) -> list[_Request]:
        """One child per request with a repeat_visit_required incident (parameters
        repeat_child_rule): same account, site and service type, 2-10 days later."""
        lo, hi = self.p.requests.child_schedule_days.value
        children = []
        for parent in gen:
            if not any(i.incident_type == "repeat_visit_required" for i in parent.incidents):
                continue
            tz = self.locations[parent.location_id]["tz"]
            day = parent.completed_at.astimezone(tz).date() + timedelta(
                days=int(rng.integers(lo, hi + 1))
            )
            scheduled = self._schedule(rng, None, day, parent.location_id, self.window_end)
            week = (day - self.start_day).days // 7
            children.append(
                self.new_request(
                    rng, parent.location_id, scheduled, week, parent.service_type, parent
                )
            )
        return children

    # ----------------------------------------------------------------- incidents

    def incident_rates(self) -> tuple[float, float]:
        """P(incident | SLA missed) and P(incident | SLA met).

        A request that missed its SLA and has incidents carries exactly one missed_sla
        incident, so missed_sla incidents occur only on SLA misses (ADR-038). The two
        rates are solved so the overall request incident rate and the missed_sla share of
        incident_type_mix both hold at the parameters' expected SLA miss rate.
        """
        inc = self.p.incidents
        m = prm.expected_sla_miss_rate(self.p)
        rate = inc.request_incident_rate.value
        missed_per_completed = (
            inc.incident_type_mix.value["missed_sla"]
            * rate
            * prm.mean_incidents_per_request(self.p)
        )
        p_miss = missed_per_completed / m
        p_met = (rate - missed_per_completed) / (1 - m)
        if not (0 <= p_miss <= 1 and 0 <= p_met <= 1):
            raise ValueError(f"infeasible incident rates: miss {p_miss:.3f}, met {p_met:.3f}")
        return p_miss, p_met

    def build_incidents(self, gen: list[_Request]) -> None:
        rng = self.rng(prm.STAGE_INCIDENTS)
        p_miss, p_met = self.inc_rates
        child_margin = timedelta(days=self.p.requests.child_schedule_days.value[1] + 1)
        for req in gen:
            if req.status != "completed":
                continue
            missed = not req.sla_met
            if rng.random() >= (p_miss if missed else p_met):
                continue
            k = self.inc_k.draw(rng)
            stop = self.accounts[req.account_id]["stop_at"] or self.window_end
            # A child must fit before the window end and the account's stop (see report).
            repeat_ok = req.completed_at + child_margin <= min(stop, self.window_end)
            types = ["missed_sla"] if missed else []
            while len(types) < k:
                excl = {"missed_sla"}
                if not repeat_ok or "repeat_visit_required" in types:
                    excl.add("repeat_visit_required")
                types.append(self.inc_types.excluding(frozenset(excl)).draw(rng))
            for t in types:
                self.new_incident(rng, req, t)

    def new_incident(self, rng, req: _Request, itype: str) -> None:
        inc = self.p.incidents
        severity = self.inc_sev.draw(rng)
        delay = timedelta(
            hours=_lognormal(rng, INCIDENT_REPORT_MEDIAN_HOURS, INCIDENT_REPORT_SIGMA)
        )
        reported = _minute(self.before_as_of(rng, req.completed_at, req.completed_at + delay))
        logged = reported + timedelta(hours=_uniform(rng, *INCIDENT_LOG_HOURS))
        created = _minute(self.before_as_of(rng, reported, logged))
        age = max(0, (self.window_end - reported) // timedelta(weeks=1))
        resolved = None
        if rng.random() < prm.incident_active_share(age, self.p):
            status = self.inc_active.draw(rng)
        else:
            status = self.inc_terminal.draw(rng)
            took = timedelta(
                days=_lognormal(rng, INCIDENT_RESOLVE_MEDIAN_DAYS, INCIDENT_RESOLVE_SIGMA)
            )
            resolved = _minute(self.before_as_of(rng, created, created + took))
        cause = None if status == "open" else self.inc_cause[itype].draw(rng)
        attributed = (
            req.technician_id if rng.random() < inc.attribution_prob_by_type.value[itype] else None
        )
        incident = _Incident(
            incident_id=len(self.incidents) + 1,
            request=req,
            incident_type=itype,
            severity=severity,
            status=status,
            root_cause=cause,
            attributed_technician_id=attributed,
            reported_at=reported,
            created_at=created,
            resolved_at=resolved,
            created_by_user_id=self.pick_user(rng, INCIDENT_CREATOR_ROLES, created),
        )
        req.incidents.append(incident)
        self.incidents.append(incident)

    # ----------------------------------------------------------------- billing

    def build_billing(self) -> None:
        rng = self.rng(prm.STAGE_BILLING)
        b = self.p.billing
        methods = list(b.payment_method_mix.value)
        rates = b.surcharge_rate_by_method.value
        anomaly = self.p.anomalies.billing_surcharge.value
        anomaly_weeks = range(anomaly["start_week"], anomaly["start_week"] + anomaly["n_weeks"])
        status_mix = b.payment_status_mix.value
        completed = [r for r in self.requests if r.status == "completed"]
        disputed_req = {
            r.request_id
            for r in completed
            if any(i.incident_type == "billing_dispute" for i in r.incidents)
        }
        # P(disputed) on requests without a billing_dispute incident, so the overall
        # disputed share still matches payment_status_mix.
        f = len(disputed_req) / len(completed) if completed else 0.0
        to_disputed = b.billing_dispute_to_disputed.value
        p_other = max(0.0, (status_mix["disputed"] - f * to_disputed) / (1 - f))
        undisputed = {k: v for k, v in status_mix.items() if k != "disputed"}
        u_tot = sum(undisputed.values())
        status_plain = _Dist(
            {"disputed": p_other, **{k: v / u_tot * (1 - p_other) for k, v in undisputed.items()}}
        )
        status_after = _Dist(undisputed)

        for req in completed:
            lab = b.labor_charge.value[req.service_type]
            labor = money(
                _lognormal(rng, lab["median"], lab["sigma"])
                * req.units**b.labor_unit_exponent.value
            )
            pc = b.parts_charge.value[req.service_type]
            parts = Decimal("0.00")
            if rng.random() < pc["p_nonzero"]:
                parts = money(
                    _lognormal(rng, pc["median"], pc["sigma"])
                    * req.units**b.parts_unit_exponent.value
                )
            final = req.payment_method
            if rng.random() < b.payment_method_change_rate.value:
                others = [m for m in methods if m != final]
                final = others[int(rng.integers(len(others)))]
            rate = Decimal(repr(rates[final]))
            if (
                final == anomaly["payment_method"]
                and self.week_of(req.completed_at) in anomaly_weeks
            ):
                rate = Decimal(repr(anomaly["surcharge_rate"]))
            rate = rate.quantize(RATE)
            has_dispute = req.request_id in disputed_req
            if has_dispute and rng.random() < to_disputed:
                pay_status = "disputed"
            else:
                pay_status = (status_after if has_dispute else status_plain).draw(rng)
            reference = None
            if pay_status != "pending":
                reference = self.payment_reference(rng, final, req)
            archived = self.before_as_of(
                rng,
                req.completed_at,
                req.completed_at + timedelta(hours=_uniform(rng, *ARCHIVE_HOURS)),
            )
            archived = max(_minute(archived), req.completed_at)
            updated = archived
            if pay_status == "disputed":
                later = archived + timedelta(days=_uniform(rng, *DISPUTE_UPDATE_DAYS))
                updated = max(_minute(self.before_as_of(rng, archived, later)), archived)
            req.total_invoice = total_invoice(labor, parts, rate)
            self.tables["archived_requests"].append(
                {
                    "request_id": req.request_id,
                    "completed_at": req.completed_at,
                    "technician_id": req.technician_id,
                    "labor_charge": labor,
                    "parts_charge": parts,
                    "surcharge_rate": rate,
                    "payment_method_final": final,
                    "payment_status": pay_status,
                    "payment_reference": reference,
                    "archived_at": archived,
                    "updated_at": updated,
                }
            )

        # Credits: a uniform fraction of total_invoice; a request's credits never sum
        # past its total_invoice (§8).
        credit = self.p.incidents.credit_by_type.value
        remaining = {r.request_id: r.total_invoice for r in completed}
        for i in self.incidents:
            c = credit[i.incident_type]
            if rng.random() < c["p"]:
                amt = (
                    i.request.total_invoice
                    * Decimal(repr(_uniform(rng, c["frac_lo"], c["frac_hi"])))
                ).quantize(CENT, ROUND_DOWN)
                amt = min(amt, remaining[i.request.request_id])
                remaining[i.request.request_id] -= amt
                i.credit = amt

    @staticmethod
    def payment_reference(rng, method: str, req: _Request) -> str:
        """Last-4 or a transaction-style reference only, never a full number (§9)."""
        if method == "credit_card":
            return f"CARD-{int(rng.integers(10_000)):04d}"
        if method == "ach":
            return f"ACH-{int(rng.integers(10**9, 10**10))}"
        if method == "check":
            return f"CHK-{int(rng.integers(1_000, 100_000))}"
        return f"INV-{100_000 + req.request_id}"

    # ----------------------------------------------------------------- feedback

    @staticmethod
    def linked_incident(req: _Request) -> _Incident | None:
        """Most severe incident; ties go to the earliest reported (then lowest id)."""
        if not req.incidents:
            return None
        return min(
            req.incidents,
            key=lambda i: (-SEVERITY_RANK[i.severity], i.reported_at, i.incident_id),
        )

    def build_feedback(self) -> list[dict]:
        rng = self.rng(prm.STAGE_FEEDBACK)
        fb = self.p.feedback
        rows = []
        for req in self.requests:
            if req.status != "completed":
                continue
            link = self.linked_incident(req)
            rate = fb.response_rate_incident.value if link else fb.response_rate_no_incident.value
            if rng.random() >= rate:
                continue
            delay = timedelta(hours=_lognormal(rng, FEEDBACK_MEDIAN_HOURS, FEEDBACK_SIGMA))
            submitted = req.completed_at + delay
            if link is not None:
                submitted = max(submitted, link.created_at)
            if submitted > self.as_of:
                continue  # the survey had not come back by the snapshot
            rows.append({"req": req, "link": link, "submitted_at": _minute(submitted)})
        return rows

    def build_sentiment(self, rows: list[dict]) -> None:
        rng = self.rng(prm.STAGE_SENTIMENT)
        s = self.p.sentiment
        no_inc = _Dist(prm.no_incident_sentiment(self.p))
        by_sev = {sev: _Dist(d) for sev, d in s.incident_sentiment_by_severity.value.items()}
        styles = {se: _Dist(d) for se, d in prm.style_given_sentiment(self.p).items()}
        ratings = {se: _Dist(d) for se, d in s.rating_given_sentiment.value.items()}
        level = self.p.corpus.incident_context_by_severity.value
        null_rate = self.p.feedback.rating_null_rate.value
        for row in rows:
            link = row["link"]
            sentiment = (by_sev[link.severity] if link else no_inc).draw(rng)
            row["sentiment"] = sentiment
            row["style"] = styles[sentiment].draw(rng)
            row["context"] = level[link.severity] if link else "none"
            row["rating"] = None if rng.random() < null_rate else int(ratings[sentiment].draw(rng))
            row["cell"] = prm.corpus_cell_for_row(
                sentiment,
                row["style"],
                row["req"].service_type,
                row["context"],
                link.incident_type if link else None,
            )

    def assign_corpus(self, rows: list[dict]) -> None:
        """Draw each row's comment without replacement from its own cell (ADR-038)."""
        rng = self.rng(prm.STAGE_CORPUS_ASSIGNMENT)
        need = Counter(r["cell"] for r in rows)
        short = {
            c: (n, len(self.corpus.get(c, ())))
            for c, n in need.items()
            if n > len(self.corpus.get(c, ()))
        }
        if short:
            detail = "; ".join(f"{c} needs {n}, has {h}" for c, (n, h) in sorted(short.items()))
            first = min(short)
            raise CorpusExhaustedError(
                f"corpus cell {first} ran out ({len(short)} cell(s) short): {detail}"
            )
        # Every cell is shuffled in sorted order, so a cell's order never depends on demand.
        queues = {
            c: [recs[int(i)] for i in rng.permutation(len(recs))]
            for c, recs in sorted(self.corpus.items())
        }
        used: Counter = Counter()
        for fid, row in enumerate(rows, 1):
            rec = queues[row["cell"]][used[row["cell"]]]
            used[row["cell"]] += 1
            req, link = row["req"], row["link"]
            self.tables["service_feedback"].append(
                {
                    "feedback_id": fid,
                    "request_id": req.request_id,
                    "incident_id": link.incident_id if link else None,
                    "submitted_by_contact_id": req.contact_id,
                    "submitted_at": row["submitted_at"],
                    "rating": row["rating"],
                    "feedback_text": rec["text"],
                    "response_channel": rec["channel"],
                    "created_at": row["submitted_at"],
                }
            )
            self.tables["sentiment_labels"].append(
                {
                    "feedback_id": fid,
                    "true_sentiment": row["sentiment"],
                    "label_confidence": None,
                    "hard_case_type": prm.HARD_CASE_BY_STYLE[row["style"]],
                    "corpus_id": rec["corpus_id"],
                }
            )

    # ----------------------------------------------------------------- output

    def emit(self) -> dict[str, list[dict]]:
        t = self.tables
        t["accounts"] = [a["row"] for a in self.accounts.values()]
        for r in self.requests:
            t["service_requests"].append(
                {
                    "request_id": r.request_id,
                    "reservation_number": f"RES-{100_000 + r.request_id}",
                    "account_id": r.account_id,
                    "location_id": r.location_id,
                    "contact_id": r.contact_id,
                    "service_type": r.service_type,
                    "priority_tier": r.priority,
                    "equipment_unit_count": r.units,
                    "scheduled_datetime": r.scheduled,
                    "sla_window_minutes": r.sla_window,
                    "assigned_technician_id": r.technician_id,
                    "payment_method": r.payment_method,
                    "request_status": r.status,
                    "parent_request_id": r.parent_id,
                    "dispatched_at": r.dispatched_at,
                    "cancelled_at": r.cancelled_at,
                    "cancellation_reason": r.cancellation_reason,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at(),
                    "created_by_user_id": r.created_by_user_id,
                }
            )
        for i in self.incidents:
            t["incidents"].append(
                {
                    "incident_id": i.incident_id,
                    "request_id": i.request.request_id,
                    "incident_type": i.incident_type,
                    "incident_status": i.status,
                    "severity": i.severity,
                    "root_cause_category": i.root_cause,
                    "attributed_technician_id": i.attributed_technician_id,
                    "reported_at": i.reported_at,
                    "reported_by_contact_id": i.request.contact_id,
                    "resolved_at": i.resolved_at,
                    "incident_notes": None,
                    "credit_issued_amount": i.credit,
                    "created_by_user_id": i.created_by_user_id,
                    "created_at": i.created_at,
                    "updated_at": i.resolved_at or i.created_at,
                }
            )
        # generated_at is left to the column's server default (one now() per load
        # transaction), so generation itself never reads the clock.
        for key, value, group, notes in prm.to_generation_parameters_rows(self.p):
            t["generation_parameters"].append(
                {"param_key": key, "param_value": value, "param_group": group, "notes": notes}
            )
        t["generation_parameters"].append(
            {
                "param_key": "seed.corpus_sha256",
                "param_value": self.corpus_sha,
                "param_group": prm.GROUP_BY_DOMAIN["seed"],
                "notes": "SHA-256 of the corpus file generate.py read; with the master seed it "
                "reproduces the dataset (ADR-030).",
            }
        )
        return {name: t[name] for name in TABLES}

    def run(self) -> dict[str, list[dict]]:
        self.build_reference()
        counts = self.build_volume()
        self.build_requests(counts)
        self.build_billing()
        rows = self.build_feedback()
        self.build_sentiment(rows)
        self.assign_corpus(rows)
        return self.emit()


def generate(
    corpus_path: str | Path,
    *,
    params: prm.Parameters = prm.PARAMS,
    scale: float = 1.0,
) -> dict[str, list[dict]]:
    """Build the full dataset: {table name: rows}, tables in foreign-key order.

    `scale` multiplies expected request volume only (reference tables keep their sizes);
    it exists for fast tests. At the default 1.0 every volume rate is multiplied by
    exactly 1.0, so the full-scale output is unaffected by the argument's existence.
    """
    corpus = load_corpus(corpus_path, params)
    return _Generator(corpus, file_sha256(corpus_path), params, scale).run()


def row_counts(dataset: Mapping[str, list]) -> dict[str, int]:
    return {name: len(rows) for name, rows in dataset.items()}


# --------------------------------------------------------------------------- validation


def validate_dataset(dataset: Mapping[str, list[dict]]) -> list[str]:
    """§8 check constraints and QA invariants over generated rows; [] when all hold.

    load.py refuses to write a dataset with any problem, so a violated constraint is a
    named failure here rather than an opaque insert error inside the transaction.
    """
    problems: list[str] = []

    def bad(name: str, rows) -> None:
        rows = list(rows)
        if rows:
            problems.append(f"{name}: {len(rows)} row(s)")

    sr = dataset["service_requests"]
    ar = dataset["archived_requests"]
    inc = dataset["incidents"]
    fb = dataset["service_feedback"]
    sl = dataset["sentiment_labels"]
    req_by_id = {r["request_id"]: r for r in sr}
    arch_by_id = {a["request_id"]: a for a in ar}

    bad(
        "cancelled_at set iff cancelled",
        (r for r in sr if (r["cancelled_at"] is not None) != (r["request_status"] == "cancelled")),
    )
    bad(
        "cancellation_reason on a non-cancelled request",
        (r for r in sr if r["cancellation_reason"] and r["request_status"] != "cancelled"),
    )
    bad("equipment_unit_count <= 0", (r for r in sr if r["equipment_unit_count"] <= 0))
    bad("sla_window_minutes <= 0", (r for r in sr if r["sla_window_minutes"] <= 0))
    bad(
        "parent_request_id = request_id",
        (r for r in sr if r["parent_request_id"] == r["request_id"]),
    )
    bad(
        "rating outside 1-5",
        (f for f in fb if f["rating"] is not None and not 1 <= f["rating"] <= 5),
    )
    bad(
        "negative labor or parts", (a for a in ar if a["labor_charge"] < 0 or a["parts_charge"] < 0)
    )
    bad("surcharge_rate outside 0-1", (a for a in ar if not 0 <= a["surcharge_rate"] <= 1))
    bad(
        "negative credit",
        (i for i in inc if i["credit_issued_amount"] is not None and i["credit_issued_amount"] < 0),
    )

    completed = {r["request_id"] for r in sr if r["request_status"] == "completed"}
    if set(arch_by_id) != completed:
        problems.append("archive rows are not exactly the completed requests")
    bad(
        "completed_at before scheduled_datetime",
        (a for a in ar if a["completed_at"] < req_by_id[a["request_id"]]["scheduled_datetime"]),
    )
    credits: dict[int, Decimal] = defaultdict(Decimal)
    for i in inc:
        if i["credit_issued_amount"] is not None:
            credits[i["request_id"]] += i["credit_issued_amount"]
    over = []
    for rid, c in credits.items():
        a = arch_by_id.get(rid)
        if a is None or c > total_invoice(
            a["labor_charge"], a["parts_charge"], a["surcharge_rate"]
        ):
            over.append(rid)
    bad("credits exceed total_invoice", over)
    if {x["feedback_id"] for x in sl} != {f["feedback_id"] for f in fb}:
        problems.append("feedback rows and sentiment_labels rows do not match one-to-one")
    bad("incident on an unknown request", (i for i in inc if i["request_id"] not in req_by_id))
    bad("feedback on an unknown request", (f for f in fb if f["request_id"] not in req_by_id))
    if len({x["corpus_id"] for x in sl}) != len(sl):
        problems.append("a corpus_id is used twice")
    if len({f["request_id"] for f in fb}) != len(fb):
        problems.append("a request has two feedback rows")
    return problems


__all__ = [
    "TABLES",
    "CorpusError",
    "CorpusExhaustedError",
    "generate",
    "load_corpus",
    "money",
    "row_counts",
    "total_invoice",
    "validate_dataset",
]
