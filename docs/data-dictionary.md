# Data Dictionary — Field Service Operations Schema

**Domain:** Network/hardware technician field service dispatch (installs, repairs, maintenance visits)

**Status:** Implemented — schema and vocabularies locked (ADR-020) and implemented in `packages/db_models/` through Alembic head `9135d8de9f27` (§10). Where this document and the models disagree, the models are right.

**Companion to:** `architecture.md`

---

## 1. Entity Overview

```
accounts ──┬── contacts
           └── locations

technicians        internal_users        (reference)

service_requests ──► archived_requests   (0..1, only for completed requests)
       │
       ├──► incidents          (1:many)  — quality events, mostly negative
       │         │
       │         └── optional link
       │                 │
       └──► service_feedback  (0..1)     — post-visit survey, full sentiment range

generation_parameters  — synthetic-data ground truth, generator/eval only
sentiment_labels       — sentiment ground truth, keyed to service_feedback,
                         never in the sentiment agent's MCP scope
```

Four tables were pulled out as proper reference entities instead of being repeated inline on every request row: **accounts**, **contacts**, **locations**, **technicians**. This fixes the update-anomaly problem from your draft, where an account's name or a contact's phone number lived on every row that mentioned them.

**Structural change on review — feedback split from incidents.** The previous single `incidents_feedback` table meant customer feedback could only exist where an incident existed. That would have produced a dataset where essentially all feedback is negative, which breaks the sentiment agent in two ways: the classification task becomes degenerate (predict "negative" always, score ~90%), and the QA agent's scoring against `sentiment_labels` becomes meaningless because there's no class balance to measure. Real field service collects post-visit feedback on *every* completed job — most of it neutral or positive. Two tables now: `incidents` for quality events, `service_feedback` for survey responses, with an optional link between them when a complaint accompanies a low rating.

> **Decided:** accepted. `architecture.md` §4 has been updated to reflect the four-table operational model.

---

## 2. Reference Tables

### `accounts`
The client companies being served.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `account_id` | BIGINT IDENTITY, PK | No | Internal surrogate key |
| `account_code` | VARCHAR(20), UNIQUE | No | External/business-facing account identifier |
| `account_name` | VARCHAR(255) | No | Client company name |
| `account_status` | ENUM (`active`, `inactive`, `prospect`) | No | Current relationship status |
| `contract_tier` | ENUM (`standard`, `priority`, `enterprise`) | No | Drives default SLA window — see below |
| `created_at` | TIMESTAMPTZ | No | Account onboarding date |

**SLA defaults by tier (minutes) — snapshotted onto the request, not looked up.** The generator reads this matrix at request-creation time and writes the resulting value into `service_requests.sla_window_minutes`.

| Contract tier | `standard` priority | `urgent` | `critical` |
|---|---|---|---|
| `standard` | 480 (8h) | 240 | 120 |
| `priority` | 240 (4h) | 120 | 60 |
| `enterprise` | 120 (2h) | 60 | 30 |

*Why snapshot rather than join at query time: if an account upgrades tier in month 20, a live lookup would retroactively re-judge all of their past requests against the stricter new SLA, and every historical compliance report would change. This is deliberate denormalization to preserve historical accuracy — a standard production pattern worth being able to explain.*

### `contacts`
People associated with an account — the person who calls in a request or reports an incident.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `contact_id` | BIGINT IDENTITY, PK | No | Internal surrogate key |
| `account_id` | FK → accounts | No | Which account this contact belongs to |
| `first_name` | VARCHAR(100) | No | |
| `last_name` | VARCHAR(100) | No | |
| `phone` | VARCHAR(20) | Yes | |
| `email` | VARCHAR(255) | Yes | |
| `contact_role` | ENUM (`site_contact`, `billing_contact`, `account_admin`, `other`) | Yes | |

*Replaces the previously inconsistent `CallerName`/`CallerFirstName`/`CallerLastName`/`CallerNumber`/`ContactEmail` fields scattered across tables. Every "who called this in" reference across the schema now points here.*

### `locations`
Client sites where a technician is dispatched. One account can have many sites.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `location_id` | BIGINT IDENTITY, PK | No | Internal surrogate key |
| `account_id` | FK → accounts | No | Which account this site belongs to |
| `site_name` | VARCHAR(100) | Yes | e.g. "HQ", "Branch 3", "Data Center West" |
| `street_address` | VARCHAR(255) | No | |
| `city` | VARCHAR(100) | No | |
| `state` | VARCHAR(2) | No | |
| `zip_code` | VARCHAR(10) | No | |

*Replaces the pickup/dropoff address pattern — field service has one service site per visit, not a pickup and a dropoff. If a single engagement ever needs to span multiple sites, model that as a `request_sites` join table rather than duplicating address columns onto every request row.*

### `technicians`
Internal dispatch resources.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `technician_id` | BIGINT IDENTITY, PK | No | Internal surrogate key |
| `full_name` | VARCHAR(200) | No | |
| `technician_status` | ENUM (`active`, `on_leave`, `terminated`) | No | |
| `skill_tags` | *(removed — see `technician_skills`)* | — | Delimited strings violate first normal form; split into a join table |
| `home_region` | VARCHAR(100) | Yes | Base region — useful later for travel-time/SLA modeling |

### `technician_skills`
Join table — one row per technician-skill pair. **Decided on review.**

| Column | Type | Nullable | Description |
|---|---|---|---|
| `technician_id` | FK → technicians, composite PK | No | |
| `skill` | VARCHAR + CHECK (`network`, `hardware`, `cabling`, `security_systems`, `power_systems`) | No | Composite PK with `technician_id` |
| `proficiency` | VARCHAR + CHECK (`certified`, `experienced`, `trainee`) | No | Optional dimension for later capacity modeling |

*Why: `skill_tags = "network,hardware"` forces substring matching to answer "find all network techs" — and `LIKE '%network%'` would also match `network_admin`, which is quietly wrong. A delimited list in a column is the canonical first-normal-form violation and a capstone reviewer will spot it immediately.*

### `internal_users`
Dispatch and back-office staff who create records. **Added on review** — the original draft had `created_by_user_id` on multiple tables referencing nothing, which is a dangling foreign key waiting to happen.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `user_id` | BIGINT IDENTITY, PK | No | Internal surrogate key |
| `full_name` | VARCHAR(200) | No | |
| `user_role` | ENUM (`dispatcher`, `supervisor`, `billing_clerk`, `qa_analyst`) | No | |
| `user_status` | ENUM (`active`, `inactive`) | No | |

---

## 3. Core Operational Tables

### `service_requests`
Active/open service engagements. This is your "records" table.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `request_id` | BIGINT IDENTITY, PK | No | Internal surrogate key |
| `reservation_number` | VARCHAR(20), UNIQUE | No | Human-facing business identifier, e.g. `RES-100234` |
| `account_id` | FK → accounts | No | |
| `location_id` | FK → locations | No | Service site |
| `contact_id` | FK → contacts | No | Client contact for this request |
| `service_type` | ENUM (`install`, `repair`, `maintenance`, `inspection`, `upgrade`) | No | |
| `priority_tier` | ENUM (`standard`, `urgent`, `critical`) | No | |
| `equipment_unit_count` | INT | No | Number of devices/units in scope for this visit |
| `scheduled_datetime` | TIMESTAMPTZ | No | Single combined timestamp — replaces split date/time fields. *Corrected from `TIMESTAMP` when the DDL was written: §6 forbids naive timestamps outright* |
| `sla_window_minutes` | INT | No | Target response/resolution window for this request |
| `assigned_technician_id` | FK → technicians | Yes | Null until dispatched |
| `payment_method` | ENUM (`credit_card`, `direct_bill`, `ach`, `check`) | No | *Requested* method — may differ from what's actually used at billing (see `archived_requests`) |
| `request_status` | ENUM (`open`, `dispatched`, `en_route`, `in_progress`, `completed`, `cancelled`) | No | Controlled vocabulary — replaces free-text `ResStatus` |
| `parent_request_id` | FK → service_requests | Yes | **Added on review** — self-reference for repeat visits. The `repeat_visit_required` incident type implies a follow-up job; without this link there's no way to measure first-time-fix rate, which is the single most-watched KPI in field service |
| `dispatched_at` | TIMESTAMPTZ | Yes | When a technician was actually assigned — the true SLA clock start (see §6) |
| `cancelled_at` | TIMESTAMPTZ | Yes | Null unless `request_status` = `cancelled` |
| `cancellation_reason` | ENUM (`client_cancelled`, `client_no_show`, `resource_unavailable`, `duplicate`, `other`) | Yes | **Added on review** — cancellations need to be distinguishable from completions in the forecast, and client-driven vs. capacity-driven cancellations mean very different things operationally |
| `created_at` | TIMESTAMPTZ | No | |
| `updated_at` | TIMESTAMPTZ | No | **Added on review** — required for the audit-trail element of the production-grade checklist |
| `created_by_user_id` | FK → internal_users | No | Dispatch user who logged the request |

### `archived_requests`
Completed requests with final billing. 0..1 with `service_requests` (see the cardinality note below), created when `request_status` reaches `completed`.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `request_id` | FK → service_requests, PK | No | Same key as the originating request |
| `completed_at` | TIMESTAMPTZ | No | Actual resolution time — needed for SLA-compliance calculation. *Corrected from `TIMESTAMP` when the DDL was written, per §6* |
| `technician_id` | FK → technicians | No | Who ultimately performed the work |
| `labor_charge` | DECIMAL(10,2) | No | |
| `parts_charge` | DECIMAL(10,2) | No | |
| `surcharge_rate` | DECIMAL(5,4) | No | e.g. `0.0300` for 3% |
| `payment_method_final` | ENUM (same as above) | No | Method actually used — can differ from the request's stated method |
| `payment_status` | ENUM (`pending`, `paid`, `disputed`) | No | Replaces the mixed free-text `"Billing Complete or Final Billing Pending or Disputed"` |
| `payment_reference` | VARCHAR(50) | Yes | Last-4 or transaction reference only — never a full card/account number |
| `archived_at` | TIMESTAMPTZ | No | When the archive record was written |
| `updated_at` | TIMESTAMPTZ | No | Billing records get corrected — track it |

**Cardinality correction:** this is **0..1** with `service_requests`, not 1:1. Cancelled requests never produce an archive row. Your reporting and forecast tools must use the correct join type or they will silently undercount — and a QA check that asserts `count(completed requests) == count(archived rows)` is a good cheap invariant to build in.

**Derived, not stored:** `total_invoice` = `(labor_charge + parts_charge) * (1 + surcharge_rate)`. Compute this in a view or at query time, not as a stored column — storing it invites drift if any input changes after the fact, and your reporting agent's MCP tool is the right place to compute it consistently.

**Also derivable, not stored:** `sla_met`. See §6 for the precise definition — the original phrasing left the SLA clock start ambiguous, which would have made this metric unreproducible.

### `incidents`
Quality events requiring investigation. Not every request has one; some have several.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `incident_id` | BIGINT IDENTITY, PK | No | |
| `request_id` | FK → service_requests | No | Consistent name — no more `ReservationNumber` vs `ReservationNo` |
| `incident_type` | ENUM (`missed_sla`, `wrong_dispatch_info`, `repeat_visit_required`, `technician_conduct`, `equipment_damage`, `billing_dispute`, `other`) | No | |
| `incident_status` | ENUM (`open`, `investigating`, `resolved`, `closed`) | No | |
| `severity` | ENUM (`low`, `medium`, `high`) | No | **Added on review** — gives the reporting agent a weighting dimension beyond raw counts |
| `root_cause_category` | ENUM (`dispatch_error`, `technician_error`, `equipment_failure`, `client_site_issue`, `communication_breakdown`, `other`) | Yes | Filled in once investigated |
| `attributed_technician_id` | FK → technicians | Yes | **Added on review** — the entity overview implied this link but no column existed. Nullable because not every incident is technician-attributable (dispatch errors, for instance) |
| `reported_at` | TIMESTAMPTZ | No | When the customer reported it |
| `reported_by_contact_id` | FK → contacts | No | Reuses the contacts table — no duplicate caller fields |
| `resolved_at` | TIMESTAMPTZ | Yes | **Added on review** — without this there's no incident-resolution-time metric, and time-to-resolve is a core quality KPI |
| `incident_notes` | TEXT | Yes | Internal staff account of what happened. **Never fed to the sentiment agent.** Generated as short templated staff notes (2-3 sentences: incident type, root cause when known, status) from committed phrase lists in `data/generator/reference_data.py`, with no names or contact details; null only for some still-open incidents (ADR-043) |
| `credit_issued_amount` | DECIMAL(10,2) | Yes | Explicit — replaces the ambiguous `IncidentCost` |
| `created_by_user_id` | FK → internal_users | No | |
| `created_at` | TIMESTAMPTZ | No | When the record was logged (can differ from `reported_at`) |
| `updated_at` | TIMESTAMPTZ | No | |

**Not stored here, on purpose:** original invoice amount. It's derivable via `request_id → archived_requests` when that record exists, and duplicating it here is exactly the redundancy we flagged in your draft — two copies of the same number that can drift apart.

### `service_feedback`
Post-visit customer survey responses. **New on review.** This is the sentiment agent's sole data source.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `feedback_id` | BIGINT IDENTITY, PK | No | |
| `request_id` | FK → service_requests, UNIQUE | No | At most one survey per completed request |
| `incident_id` | FK → incidents | Yes | Optional link when the feedback accompanies a logged complaint |
| `submitted_by_contact_id` | FK → contacts | No | |
| `submitted_at` | TIMESTAMPTZ | No | |
| `rating` | SMALLINT (1–5) | Yes | Structured satisfaction score. Nullable — some respondents leave text only |
| `feedback_text` | TEXT | Yes | The customer's own words — **this is what the sentiment agent reads**. Generated text, drawn from the frozen corpus in `data/generator/corpus/` (ADR-030) |
| `response_channel` | ENUM (`email_survey`, `sms_survey`, `phone_followup`, `portal`) | No | |
| `created_at` | TIMESTAMPTZ | No | |

**Why `rating` and `feedback_text` both exist:** the numeric rating is a partial cross-check on sentiment classification — a "positive" classification on a 1-star review is a detectable contradiction. That gives your QA agent a second, independent signal beyond the `sentiment_labels` holdout, which meaningfully strengthens the verification story for the one task that's otherwise hardest to verify. Deliberately generate some mismatches (sarcasm, mixed feedback) so this check has something real to catch.

**Important distinction preserved from the earlier draft:** internal staff notes (`incidents.incident_notes`) and the customer's own words (`service_feedback.feedback_text`) are different kinds of text with different authors. Feeding staff-written notes into the sentiment agent would quietly corrupt that pipeline. The table split now makes this structurally enforceable rather than a convention to remember — the sentiment MCP server simply has no grant on `incidents`.

---

## 4. Ground-Truth Tables (generator/eval only — not part of the operational schema)

### `generation_parameters`
The true parameters used to generate the synthetic dataset. Written once by the data generator, read only by validation scripts and the eval harness. No agent ever queries this table. **Given a key-value shape on review** — the original prose description wasn't specific enough to implement against.

| Column | Type | Description |
|---|---|---|
| `param_key` | VARCHAR(100), PK | e.g. `seasonality_amplitude`, `trend_slope_monthly`, `incident_rate_baseline`, `incident_sentiment_corr`, `anomaly_window_start` |
| `param_value` | JSONB | Value. Implemented as JSONB throughout (scalars as well as windowed/array cases), so callers have one decode path |
| `param_group` | ENUM (`volume`, `incidents`, `sentiment`, `billing`, `anomalies`, `world`, `feedback`) | Groups params by which model they govern. Seven values (ADR-038): `world` holds the seed, window, reference counts, regions and request lifecycle; `feedback` holds response rates, channels and corpus sizing |
| `notes` | TEXT | Human explanation of what this parameter controls |
| `generated_at` | TIMESTAMPTZ | Generation run timestamp — lets you regenerate reproducibly |

Also persist the **random seed** here. Without it your dataset isn't reproducible, and a capstone reviewer asking "can you regenerate this?" should get a yes.

As generated (ADR-042, ADR-043): `seed.master_seed` and `seed.stage_keys` persist the seed, and `seed.corpus_sha256` records the SHA-256 of the corpus file the dataset was drawn from, so seed plus corpus reproduce it. Derived values are stored too, including `derived_incidents.incident_rate_given_sla` — P(incident | SLA missed) ≈ 0.252 and P(incident | SLA met) ≈ 0.081, solved so the overall incident rate is 10% of completed requests and missed_sla is 25% of incidents — and `derived_billing.expected_pending_share`.

**Severity → sentiment coupling — decided: yes, with noise.** Incident severity influences the sentiment of the associated feedback. The earlier concern about leakage doesn't apply now that the forecast is locked as univariate — it never sees incidents or sentiment, so there's no path for it to learn a shortcut. And this correlation is precisely one of the ground-truth relationships the synthetic world needs; without it you have three unrelated random streams rather than a coherent business.

Store the coupling strength as an explicit parameter (`incident_severity_sentiment_coupling`) rather than a magic number in generator code.

**Guard: do not make it deterministic.** If severity perfectly predicts sentiment, the text becomes redundant — an analyst could skip reading it entirely, and your sentiment agent's reason for existing evaporates. Build in genuine exceptions: a serious incident handled well can yield mixed feedback that names the problem and praises the recovery, or positive feedback that praises the handling without naming the failure (ADR-036). Neutral feedback never occurs on incident rows.

### `sentiment_labels`
**Repointed on review** — now keyed to `service_feedback`, not incidents, following the table split.

| Column | Type | Description |
|---|---|---|
| `feedback_id` | FK → service_feedback, PK | One label per feedback record |
| `true_sentiment` | ENUM (`positive`, `neutral`, `negative`, `mixed`) | Assigned at generation time, before any model sees the text. It is the sentiment the corpus model was asked to write (ADR-030). Plain comments are confirmed by the judge (ADR-036); sarcastic and implicit comments are intent; their judge disagreement rate is reported (ADR-040). |
| `label_confidence` | NUMERIC(4,3), nullable | Null on every generated row: genuinely ambiguous comments are excluded from the corpus (ADR-036), so labels carry no graded confidence |
| `hard_case_type` | ENUM (`none`, `sarcastic`, `implicit`), NOT NULL | Which kind of deliberately hard case the comment is, or `none` (ADR-037; replaces `is_sarcastic`). There are two hard-case types (ADR-036), and failure analysis reports subgroup accuracy per type. |
| `corpus_id` | VARCHAR(32), NOT NULL, UNIQUE | ID of the corpus comment (`data/generator/corpus/feedback_text.jsonl`) that supplied the row's `feedback_text`, so the eval harness can join a label to its corpus metadata. UNIQUE enforces ADR-030's no-reuse rule (ADR-037). |

**The sentiment agent's MCP tool must never have a code path that reads this table.** It exists solely for the QA agent and the eval harness. Enforce this with a database grant, not a code convention — see §7.

---

## 5. Controlled Vocabularies — Consolidated

Defining these once here, referenced by every table above, keeps them from drifting into inconsistent free text.

| Enum | Values |
|---|---|
| `service_type` | `install`, `repair`, `maintenance`, `inspection`, `upgrade` |
| `priority_tier` | `standard`, `urgent`, `critical` |
| `request_status` | `open`, `dispatched`, `en_route`, `in_progress`, `completed`, `cancelled` |
| `payment_method` | `credit_card`, `direct_bill`, `ach`, `check` |
| `payment_status` | `pending`, `paid`, `disputed` |
| `incident_type` | `missed_sla`, `wrong_dispatch_info`, `repeat_visit_required`, `technician_conduct`, `equipment_damage`, `billing_dispute`, `other` |
| `incident_status` | `open`, `investigating`, `resolved`, `closed` |
| `root_cause_category` | `dispatch_error`, `technician_error`, `equipment_failure`, `client_site_issue`, `communication_breakdown`, `other` |
| `contract_tier` | `standard`, `priority`, `enterprise` |
| `account_status` | `active`, `inactive`, `prospect` |
| `technician_status` | `active`, `on_leave`, `terminated` |
| `severity` | `low`, `medium`, `high` |
| `cancellation_reason` | `client_cancelled`, `client_no_show`, `resource_unavailable`, `duplicate`, `other` |
| `response_channel` | `email_survey`, `sms_survey`, `phone_followup`, `portal` |
| `user_role` | `dispatcher`, `supervisor`, `billing_clerk`, `qa_analyst` |
| `true_sentiment` | `positive`, `neutral`, `negative`, `mixed` |

**Added when the DDL was written.** These are used by the table definitions in §2–§4 but were missing from this consolidated list, which is exactly the drift this section exists to prevent. `hard_case_type` was added later, by ADR-037.

| Enum | Values | Used by |
|---|---|---|
| `contact_role` | `site_contact`, `billing_contact`, `account_admin`, `other` | `contacts` |
| `user_status` | `active`, `inactive` | `internal_users` |
| `skill` | `network`, `hardware`, `cabling`, `security_systems`, `power_systems` | `technician_skills` |
| `proficiency` | `certified`, `experienced`, `trainee` | `technician_skills` |
| `param_group` | `volume`, `incidents`, `sentiment`, `billing`, `anomalies`, `world`, `feedback` (the last two added by ADR-038) | `generation_parameters` |
| `hard_case_type` | `none`, `sarcastic`, `implicit` | `sentiment_labels` |

All 22 vocabularies are implemented once, as `StrEnum` classes in `packages/db_models/src/db_models/enums.py`, and reused by the models, the generator, and the eval harness. That module is the authority; this table is the documentation of it.

---

## 6. Conventions & Metric Definitions

**Added on review** — these were implicit, and implicit conventions are where reproducibility quietly dies.

### Storage conventions

| Concern | Decision |
|---|---|
| Surrogate keys | `BIGINT GENERATED ALWAYS AS IDENTITY`. Single-writer generator, so UUIDs buy nothing; integers debug and index better. `reservation_number` remains the human-facing identifier |
| Enum implementation | `VARCHAR` + `CHECK` constraint, **not** Postgres native `ENUM`. Native enums require a migration to add a value and are worse to remove one — a CHECK gives identical validation with a one-line change when you find a missing value mid-sprint. The tables above say "ENUM" as shorthand for the allowed value set |
| Timestamps | `TIMESTAMPTZ`, stored UTC. Never naive `TIMESTAMP` — a multi-region field service dataset with naive timestamps will produce wrong SLA math and wrong hour-of-day seasonality |
| Display timezone | Convert at the presentation layer only |
| Currency | USD throughout. No multi-currency support — documented simplification |
| Money type | `DECIMAL(10,2)` always, never `FLOAT` |
| Rates | `DECIMAL(5,4)` — `surcharge_rate` stored as `0.0300`, not `3` |
| Soft deletes | None. Records are corrected, not deleted |

### Metric definitions (canonical — the reporting agent's MCP tool implements exactly these)

- **SLA clock start** = `dispatched_at`, *not* `scheduled_datetime`. The original draft left this ambiguous, which would have made `sla_met` unreproducible between the agent and the QA check. Requests never dispatched have no SLA outcome.
- **`sla_met`** = `completed_at <= dispatched_at + (sla_window_minutes × interval '1 minute')`. Null when either timestamp is null.
- **`total_invoice`** = `(labor_charge + parts_charge) × (1 + surcharge_rate)`, rounded half-up to 2 decimals. Rounding rule matters — the agent and the QA verifier must round identically or every check fails on pennies.
- **`net_revenue`** = `total_invoice − credit_issued_amount` (summed across the request's incidents).
- **First-time fix rate** = requests completed with no child request where `parent_request_id` points back to them, over all completed requests.
- **Incident rate** = incidents per 100 completed requests, by period.

Define these once, here. If the reporting agent and the QA agent each compute them independently from prose, they will disagree, and you'll spend a sprint debugging a discrepancy that's actually a specification gap.

### Forecast target — **locked**

- **Target:** count of `service_requests` by `scheduled_datetime`
- **Grain:** weekly. ~156 points across 36 months — roughly 130 to train, 26 held out for backtest. Daily is too noisy at these volumes; monthly gives too few points to model
- **Filter:** all requests regardless of final status — you're forecasting *demand*, not completions. Forecasting only completions confounds customer demand with your own cancellation behavior
- **Segmentation:** total, with optional breakout by `service_type`
- **Model form:** **univariate** — date in, volume out. It never sees incidents or sentiment. This matters for the coupling decision in §4

### Signal shape the generator must produce

The forecast can only recover what you deliberately put in. Pin these in `generation_parameters`:

| Component | Specification |
|---|---|
| Annual seasonality | Q4 budget-flush peak (Oct–Nov high), late-December trough. Amplitude ~±25% of baseline |
| Growth trend | ~+8% per year, so the model must separate trend from season |
| Weekly pattern | Weekday-concentrated; minimal weekend volume |
| Noise | Enough that a seasonal-naive baseline is imperfect, not so much that the pattern is unrecoverable. 6% weekly multiplicative noise; ~10.6% effective week-to-week once Poisson counting noise is included (ADR-038) |
| Anomalies | Three, all in the training span (ADR-038): the largest account drops 90% for weeks 40–41 (from 2024-06-10; invisible in weekly totals, obvious per account); every site in the largest region drops 85% for two weeks from 2025-02-17 (z ≥ 3 in weekly totals); direct-bill invoices carry a 0.10 surcharge for weeks 95–97 (from 2025-06-30). These are what make the reporting and QA agents interesting |
| Random seed | Persisted, so the whole dataset is reproducible |

### Dataset scale targets

| Entity | Target volume | Rationale |
|---|---|---|
| History window | **36 months** | Three full seasonal cycles — two to learn from, one to hold out |
| `accounts` | 40–60 | Enough for account-level aggregation to be meaningful |
| `locations` | 150–250 | ~3–4 sites per account |
| `contacts` | 150–300 | |
| `technicians` | 25–40 | |
| `service_requests` | 15,000–25,000 | ~100–160/week — enough signal for weekly regression, small enough to stay inside free-tier Postgres |
| `archived_requests` | ~90% of requests | Remainder cancelled |
| `incidents` | 8–12% of completed requests | Realistic field service incident rate |
| `service_feedback` | 35–50% of completed requests (~7,200 rows) | Realistic survey response rate. Every row has `feedback_text`; only `rating` may be null (ADR-038) |

**Realised (loaded 2026-09-25, seed 20260923):** 20,230 requests, 18,063 completed, 2,067 incidents (10.2% of completed requests have one; missed_sla is 24.4% of incidents), 7,521 feedback rows (41.6% of completed). Sentiment mix 50.2% positive / 22.4% neutral / 19.6% negative / 7.8% mixed; hard cases 14.9%. Payment status: 94.8% paid, 4.1% disputed, 1.1% pending (pending only within six weeks of the snapshot, ADR-043). Cancellation rate 10.2%. Reference tables: 50 accounts, 198 contacts, 197 locations, 32 technicians (63 skill rows), 15 internal users; 140 `generation_parameters` rows.

**Signal as recovered by `validate.py` (2026-09-25, 66/66 checks pass, `data/generator/validation/2026-09-25/report.json`):** annual growth 8.5% (designed 8%); seasonal peak-to-trough 0.39 against 0.42 designed in the same K=3 basis; residual sd of log weekly volume 11.7% (designed effective ~10.6%); regional drop z 3.53; account drop 93% at account level; 150 direct-bill invoices at the 0.10 surcharge inside the billing window and 0 outside. Note: the account drop's dip in *weekly totals* measured z 3.92 (report-only check), against the ~1.4 designed, so it is not invisible in weekly totals as the anomaly row above describes.

### Sentiment distribution — **locked**

| Label | Share | Approx. rows |
|---|---|---|
| `positive` | 50% | ~3,600 |
| `neutral` | 22% | ~1,580 |
| `negative` | 20% | ~1,440 |
| `mixed` | 8% | ~580 |

**Hard cases: ~15% of all feedback** (~1,080 rows) sarcastic or implicit (ADR-036). Enough to report subgroup accuracy credibly — "92% overall, 64% on hard cases, here's the failure analysis" — without making the dataset look artificially adversarial.

Cell rules (ADR-036): no neutral on incident rows; sarcastic is negative only; implicit is positive and negative only.

Positive feedback on an incident row draws its comment from the no-incident positive corpus cell with the same service type and style; the corpus has no positive-with-incident cells, so such comments never mention the incident (ADR-039).

**Feedback corpus (final, 2026-09-25).** 13,184 accepted comments in 91 cells (`data/generator/corpus/feedback_text.jsonl`). The corpus is complete when every cell's accepted count is at least its Poisson q99 demand estimate (ADR-038); the 2x plain-neutral / plain-mixed build factor is generation headroom for judge rejections, not a requirement. Minimum coverage is 1.2x q99. Accepted neutrals are 73% administrative, 19% status and 8% minimal: most minimal comments were rejected as corpus-wide duplicates, and the judge accepted administrative notes (78%) far more often than status (27%) or minimal (52%) ones. The text checks allow weekday names but reject calendar dates and times.

If your generated feedback ends up overwhelmingly negative, every accuracy number you report downstream is noise. Validate this distribution in Sprint 1 before building anything on top of it. *(Done 2026-09-25: the realised mix above is within ±1.5 pp of every target.)*

---

## 7. Table → Agent → Database Role Access Matrix

**Added on review.** The context doc commits to per-agent database roles as a defense-in-depth layer; this is where that gets specified concretely enough to write the GRANT statements against.

Role names are `app_*` (the `role_*` labels used in earlier drafts of this table were never the actual role names). The names below are the values `.env` ships with; the actual names come from `DB_ROLE_*_USER`, which is **required** — the migration fails rather than assuming a name, since a role created under a name nothing connects as surfaces much later as an opaque "permission denied".

| Table | `app_reporting` | `app_sentiment` | `app_forecast` | `app_qa` | `app_generator` |
|---|---|---|---|---|---|
| `accounts` | SELECT | — | — | SELECT | ALL |
| `contacts` | — | — | — | — | ALL |
| `locations` | SELECT | — | — | SELECT | ALL |
| `technicians` | SELECT | — | — | SELECT | ALL |
| `technician_skills` | SELECT | — | — | SELECT | ALL |
| `internal_users` | — | — | — | — | ALL |
| `service_requests` | SELECT | — | SELECT (columns)³ | SELECT | ALL |
| `archived_requests` | SELECT | — | — | SELECT | ALL |
| `incidents` | SELECT | **—** | — | SELECT | ALL |
| `service_feedback` | SELECT (aggregate)¹ | SELECT (columns)² | — | SELECT | ALL |
| `sentiment_labels` | — | **—** | — | SELECT | ALL |
| `generation_parameters` | — | — | — | SELECT | ALL |

¹ Postgres has no aggregate-only privilege. This is implemented as a **column-level** `GRANT SELECT` covering every column of `service_feedback` **except `feedback_text`**, so the reporting agent can count and average ratings but is structurally unable to read a customer's raw words. See ADR-025.

² A **column-level** `GRANT SELECT` on exactly `feedback_id`, `request_id`, `submitted_at` and `feedback_text`: the text to classify, an identifier to report against, and the timestamp `get_feedback_batch(date_range, …)` filters on. **`rating` is withheld** because it is the QA agent's independent cross-check on sentiment classification (R-04); a sentiment agent that can see the stars is no longer being checked independently. See ADR-027, which supersedes ADR-025's table-level grant here.

³ A **column-level** `GRANT SELECT` on exactly `request_id`, `scheduled_datetime` and `service_type`. That is all the univariate forecast needs (ADR-018): a weekly count by `scheduled_datetime`, optionally broken out by `service_type`, with an identifier to count against. Billing and payment fields, cancellation detail, and every account, contact and technician identifier are withheld, and the forecast role has no access to `accounts`, `locations` or `archived_requests`. A breakout beyond `service_type` needs a new grant, migration and ADR. See ADR-035.

**Implementation:** this matrix is executable, not prose — `packages/db_models/src/db_models/access_matrix.py` is the authority for what is granted. `tests/unit/test_access_matrix.py` asserts it says what this table says, and `tests/integration/test_access_matrix_grants.py` asserts the migrated database grants exactly that, reads and writes both. Migrations carry frozen literal copies of the grants they applied rather than importing the module (ADR-027), so every grant change is a new migration. The roles migration additionally revokes the Postgres `PUBLIC` defaults (ADR-025), which this table does not cover.

Five things this matrix enforces that a code convention wouldn't:

1. **The sentiment agent cannot read `sentiment_labels`.** Circular self-verification becomes structurally impossible, not just discouraged.
2. **The sentiment agent cannot read `incidents`.** Staff-written notes can never leak into the sentiment pipeline.
3. **No agent reads `contacts`.** Customer PII never enters an LLM context window — a strong, concrete point for the security writeup, and exactly the kind of deliberate scoping decision worth calling out in an interview.
4. **The sentiment agent cannot read `service_feedback.rating`.** The rating stays a genuinely independent signal for the QA agent to check sentiment against (R-04, ADR-027).
5. **The forecast agent cannot read billing or any customer or technician identifier.** It sees three columns of `service_requests` and nothing else (ADR-035).

Note that `app_qa` is deliberately broad: verification requires cross-checking sources the specialists can't see. That's the point — but it also makes the QA agent the highest-value target in the system, which is worth one paragraph in the threat model.

---

## 8. Constraints & Invariants

Worth writing as actual DB constraints where possible, and as QA-agent checks where not.

**Check constraints:**
- `service_requests.cancelled_at IS NOT NULL` ⟺ `request_status = 'cancelled'` — implemented as `ck_service_requests_cancelled_at_matches_status`
- `service_feedback.rating BETWEEN 1 AND 5` — `ck_service_feedback_rating_range`. A NULL rating passes, which is correct: some respondents leave text only
- `labor_charge >= 0`, `parts_charge >= 0`, `credit_issued_amount >= 0`
- `surcharge_rate BETWEEN 0 AND 1`
- `equipment_unit_count > 0`
- `parent_request_id <> request_id` (no self-reference) — implemented as `parent_request_id IS DISTINCT FROM request_id`, so a NULL parent passes rather than evaluating to NULL

**Added when the DDL was written** (not in the original list; see ADR-025):
- `cancellation_reason IS NULL OR request_status = 'cancelled'` — `ck_service_requests_cancellation_reason_requires_cancelled`. The list above constrains `cancelled_at` but was silent on the reason column; a cancellation reason on a non-cancelled request is meaningless
- `sla_window_minutes > 0` — `ck_service_requests_sla_window_minutes_positive`. The SLA matrix in §2 only ever yields 30–480, so a non-positive window is always a generator bug and should fail at insert time rather than surface later as a nonsense compliance figure

**Not a check constraint, deliberately:**
- `archived_requests.completed_at >= service_requests.scheduled_datetime`. This spans two tables, so it cannot be a `CHECK`. The earlier phrasing offered "trigger or app layer"; it is enforced as a generator-validation check and a QA-agent invariant instead, not a trigger — see ADR-025 for why

**Data invariants for the QA agent to verify:**
- Every `completed` request has exactly one `archived_requests` row
- No `cancelled` request has an archive row
- `credit_issued_amount` never exceeds the request's `total_invoice`
- Every `service_feedback` row has a corresponding `sentiment_labels` row
- Every `incidents.request_id` and `service_feedback.request_id` resolves to a real request
- `archived_requests.completed_at >= service_requests.scheduled_datetime` — moved here from the check-constraint list, since it spans two tables

That last set doubles as your data-generator validation suite. Run it immediately after generation in Sprint 1 — finding a broken invariant in Sprint 4 means regenerating and redoing every downstream measurement.

---

## 9. Design Notes

- **Sensitive fields:** `payment_reference` holds last-4 or a transaction reference only, never a full card or account number — good practice regardless of the data being synthetic, and it keeps the habit correct. `contacts.phone`/`email` are PII-shaped even when generated; use reserved-for-documentation formats (e.g. `555-01xx` numbers, `example.com` domains) so nothing resembles a real person.
- **Indexing considerations for the MCP tools:** index `service_requests(scheduled_datetime)` for the forecast series, `(account_id, scheduled_datetime)` and `(request_status)` for reporting date-range and status queries, and `(parent_request_id)` for first-time-fix calculation; index `incidents(request_id)` and `(incident_type, reported_at)` for aggregation; index `service_feedback(request_id)` and `(submitted_at)` for sentiment batch pulls; index `archived_requests(completed_at)` for billing-period reporting.
- **Why `equipment_unit_count` instead of `NumOfStops`:** your original field assumed a transportation multi-stop model. In field service, the equivalent scaling factor is how many devices/units get serviced in one visit — same purpose (a request can be "bigger" than a single unit), correct domain.
- **The `payment_method` vs `payment_method_final` split is intentional, not redundant:** a request can be logged with one intended payment method and settled differently (e.g., a disputed credit card charge that gets rebilled as direct-bill). If that distinction doesn't matter for your use case, collapsing them is a fine simplification — but make that a documented decision, not a default.

---

## 10. Decisions Log

All seven open questions resolved. Recorded here so the reasoning survives into the ADRs and the final paper.

| # | Decision | Rationale |
|---|---|---|
| 1 | **Accept the `incidents` / `service_feedback` split** | Feedback tied only to incidents makes the sentiment task degenerate and the QA scoring meaningless. `architecture.md` §4 updated to match |
| 2 | **BIGINT identity keys, not UUID** | Single-writer generator; integers debug and index better. `reservation_number` carries the business-facing identity |
| 3 | **`technician_skills` join table** | Delimited strings break 1NF and force wrong substring matching |
| 4 | **Snapshot `sla_window_minutes` onto the request** | Live tier lookup would retroactively change historical compliance reports |
| 5 | **Weekly volume, all statuses, 36 months, univariate** | ~156 points; forecasts demand rather than confounding it with cancellation behavior |
| 6 | **50/22/20/8 sentiment split, 15% hard cases** | Realistic class balance; enough hard cases for credible subgroup reporting. Hard-case types later set to sarcastic and implicit (ADR-036, ADR-037) |
| 7 | **Enums locked; `upgrade` added to `service_type`; VARCHAR+CHECK implementation** | Hardware refresh is a real category with its own seasonality; CHECK constraints avoid painful enum migrations |
| 8 | **Severity influences sentiment, with noise** | No leakage path given a univariate forecast; the correlation is what makes the synthetic world coherent |

### DDL status — **implemented** (2026-09-20; current through Alembic head `9135d8de9f27`, 2026-09-23)

The schema in this document is now implemented in code. Migration chain: `0f3c81a47b21` → `7d54e0c9a318` → `1ee8342c81a7` → `fae4b8c9814c` → `4c6589542b27` → `9135d8de9f27` (head).

| Artifact | Location |
|---|---|
| SQLAlchemy models (all 12 tables) | `packages/db_models/src/db_models/` |
| Controlled vocabularies | `packages/db_models/src/db_models/enums.py` |
| §7 access matrix, as data | `packages/db_models/src/db_models/access_matrix.py` |
| Initial migration — tables, constraints, §9 indexes (`0f3c81a47b21`) | `data/migrations/versions/*_initial_schema.py` |
| Roles and grants migration (frozen, ADR-027; `7d54e0c9a318`) | `data/migrations/versions/*_roles_and_grants.py` |
| Sentiment column-level feedback grant (ADR-027, `1ee8342c81a7`) | `data/migrations/versions/*_sentiment_feedback_column_grant.py` |
| Forecast column-level `service_requests` grant (ADR-035, `fae4b8c9814c`) | `data/migrations/versions/*_forecast_service_requests_column_grant.py` |
| `sentiment_labels`: `hard_case_type` replaces `is_sarcastic`, `corpus_id` added (ADR-037, `4c6589542b27`) | `data/migrations/versions/*_sentiment_labels_hard_case_type_and_.py` |
| `generation_parameters.param_group` gains `world` and `feedback` (ADR-038, `9135d8de9f27`) | `data/migrations/versions/*_param_group_world_and_feedback.py` |
| Contract tests | `tests/unit/` |
| Live grant tests (reads and writes, per role; run in CI) | `tests/integration/` |
| Generator, loader and validation (ADR-042, ADR-043); dataset loaded 2026-09-25 | `data/generator/` |

**The models are the source of truth from here.** When this document and `db_models` disagree, the code is right and this file needs correcting — `alembic check` enforces that the migrations match the models, but nothing enforces that either matches this prose.

Three points where implementation required a decision this document had left open are recorded in ADR-025. Three corrections to this document itself are marked inline above (two `TIMESTAMP` → `TIMESTAMPTZ` fixes, five vocabularies missing from §5, and the `role_*` → `app_*` relabel in §7).
