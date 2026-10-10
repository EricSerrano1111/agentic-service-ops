# Data Dictionary — Field Service Operations Schema

**Domain:** Network/hardware technician field service dispatch (installs, repairs, maintenance visits)

**Status:** Implemented — schema and vocabularies locked (ADR-020) and implemented in `packages/db_models/` through Alembic head `3d7e1a9c5b20` (§10). Where this document and the models disagree, the models are right.

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

**Structural change on review — feedback split from incidents.** The previous single `incidents_feedback` table meant customer feedback could only exist where an incident existed. That would have produced a dataset where essentially all feedback is negative, which breaks the sentiment agent in two ways: the classification task becomes degenerate (predict "negative" always, score ~90%), and evaluation against `sentiment_labels` becomes meaningless because there's no class balance to measure. Gold labels are used only offline: to train the sentiment model (`app_train`) and in evaluation (holdout scoring and QA catch rate, `app_eval`); runtime QA cross-checks against `rating` instead (ADR-055, ADR-063). Real field service collects post-visit feedback on *every* completed job — most of it neutral or positive. Two tables now: `incidents` for quality events, `service_feedback` for survey responses, with an optional link between them when a complaint accompanies a low rating.

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
| `region` | ENUM (`northeast`, `southeast`, `central`, `west`) | Yes | **Added by ADR-051.** The customer site's region, where the work happened: the region whose state list in `data/generator/parameters.py` (`Regions.states`) contains `state`. That mapping is the only copy. The generator writes it on every row and `validate.py` checks it (A23); the column is nullable only because it was added to an already-loaded table and no migration may fill it (ADR-027). Not the technician's `home_region` |

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

**Why `rating` and `feedback_text` both exist:** the numeric rating is a partial cross-check on sentiment classification — a "positive" classification on a 1-star review is a detectable contradiction. That gives the runtime QA agent an independent signal at answer time, which meaningfully strengthens the verification story for the one task that's otherwise hardest to verify. Deliberately generate some mismatches (sarcasm, mixed feedback) so this check has something real to catch. As generated, star ratings were drawn from the label alone, so there are no clear rating/text contradictions (L-24). The `sentiment_labels` gold labels are not a QA signal: they are used only offline: to train the sentiment model (`app_train`) and in evaluation (holdout scoring and QA catch rate, `app_eval`), and runtime QA cannot read them (ADR-055, ADR-063).

**Important distinction preserved from the earlier draft:** internal staff notes (`incidents.incident_notes`) and the customer's own words (`service_feedback.feedback_text`) are different kinds of text with different authors. Feeding staff-written notes into the sentiment agent would quietly corrupt that pipeline. The table split now makes this structurally enforceable rather than a convention to remember — the sentiment MCP server simply has no grant on `incidents`.

---

### `sentiment_predictions` (derived — ADR-067)
**Operational and derived, not ground truth.** What the deployed sentiment model said about each comment, stored so answers come from a table rather than per-request inference. One row per comment per model version. Written only by `mcp_feedback` as `app_sentiment` (INSERT, never UPDATE or DELETE): scored on arrival when a question first covers a comment, or by the one-off backfill.

How it differs from `sentiment_labels` (§4): a label is the generator's answer key, assigned before any model saw the text and read only offline; a prediction is the model's opinion, read at runtime to answer questions and by QA to recompute them. The two are never joined at runtime, and `app_train` cannot read predictions, so the model never trains on its own output.

| Column | Type | Description |
|---|---|---|
| `feedback_id` | BIGINT, FK → service_feedback, ON DELETE CASCADE; PK part | The comment. A regeneration clears this table in the same TRUNCATE as `service_feedback` (`load.py`) |
| `model_version` | VARCHAR(64); PK part | SHA-256 of the committed artifact manifest (`ml/sentiment/artifacts/bert_v1.manifest.json`), so a new model or a new T or τ is a new version, never an overwrite |
| `predicted_label` | ENUM (`positive`, `neutral`, `negative`, `mixed`) | The same vocabulary as `sentiment_labels.true_sentiment` |
| `confidence` | NUMERIC(5,4), CHECK 0–1 | Calibrated probability of the predicted class, softmax(logits / T) (ADR-066), rounded to 4 places |
| `flagged` | BOOLEAN | `confidence < τ` for this version, decided before rounding: routed to human review (ADR-066) |
| `scored_at` | TIMESTAMPTZ, default now() | When the prediction was stored |

Primary key (`feedback_id`, `model_version`).

---

## 4. Ground-Truth Tables (generator/eval only — not part of the operational schema)

### `generation_parameters`
The true parameters used to generate the synthetic dataset. Written once by the data generator, read only by the validation scripts and the eval harness, as `app_eval` (ADR-063). No agent ever queries this table, and no runtime role can. **Given a key-value shape on review** — the original prose description wasn't specific enough to implement against.

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

**The sentiment agent's MCP tool must never have a code path that reads this table.** It exists solely for the validation scripts and eval harness (`app_eval`) and for training (`app_train`), all offline (ADR-063). No runtime role reads it, QA included: answers in a real deployment have no gold labels (ADR-055). Enforce this with a database grant, not a code convention — see §7.

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
| `region` | `northeast`, `southeast`, `central`, `west` (added by ADR-051) | `locations` |

All 23 vocabularies are implemented once, as `StrEnum` classes in `packages/db_models/src/db_models/enums.py`, and reused by the models, the generator, and the eval harness. That module is the authority; this table is the documentation of it.

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
- **First-time fix rate** = requests completed with no child request where `parent_request_id` points back to them, over all completed requests. A cancelled child request does not count against its parent; a child in any other status (including en route) does.
- **Incident rate** = incidents per 100 completed requests, by period. Being per 100, it can exceed 1 (11.4433 over the full window); the `DECIMAL(5,4)` rate convention above covers stored rates such as `surcharge_rate`, not derived per-100 figures.

**Date filters** (added 2026-09-26 with the FR-06 metric tools; each range applies to the event the definition is about, inclusive UTC days):
- Incident rate: incidents whose `reported_at` is in the range, over requests whose `archived_requests.completed_at` is in the range.
- SLA compliance: requests whose `dispatched_at` is in the range. Requests never dispatched, or with a null `sla_met`, are excluded from the denominator.
- First-time fix rate: requests whose `completed_at` is in the range; a child request counts whatever its own date.

**Incident counts by breakdown** (added 2026-10-02, ADR-073): incidents whose `reported_at` is in the range, as for the total. `account`, `region` (the site's) and `service_type` come from the incident's request; `incident_type` and `severity` are the incident's own; `technician` is `attributed_technician_id`, and incidents attributed to no technician form their own "unattributed" group, so the groups always sum to the total. Highest count first, ties by name; at most 25 groups, with the full count reported.

**Single-technician filter** (ADR-073): each metric restricted to the column its technician breakdown uses, so a filtered figure equals that technician's group: incident count, `attributed_technician_id`; incident rate, attributed incidents over completed requests with `archived_requests.technician_id`; SLA compliance and first-time fix rate, `archived_requests.technician_id`. Not combined with a breakdown.

**Region and account filters** (added 2026-10-08, ADR-086): each metric restricted on the same entity and dates its breakdown uses, so **a filtered figure equals that group's row in the matching unfiltered breakdown**.
- *`region`* is one of `northeast`, `southeast`, `central`, `west`: the **site's** region, `locations.region` reached through the request's `location_id`, the column `group_by=region` uses. *`account_id`* is the request's `account_id`, the column `group_by=account` uses. Incident count: incidents (by `reported_at`) whose request is at a site in the region and/or belongs to the account. Incident rate: that numerator over completed requests (by `archived_requests.completed_at`) with the same site/account. SLA compliance: dispatched requests (by `dispatched_at`) with the same site/account, a null `sla_met` excluded as before. First-time fix: completed requests with the same site/account, a child request counting whatever its own region, account or date.
- *Combinations:* `region` and `account_id` together are an AND. A filter with a breakdown by a **different** dimension is allowed (the West by account: each account's row is that account's figure in the West). A filter with a breakdown by the **same** dimension is declined. A filter with `technician_id` is an AND, on the technician columns of ADR-073; a technician filter with any breakdown stays declined.
- *Repeat-visit drivers take neither filter in this phase;* a filtered repeat-driver question is declined, because the significance rule compares a group with "the rest" and a filter changes what the rest is.
- *Accounts by name:* `find_account(name)` uses `find_technician`'s rules over the 50 account names: every word of the query must be a whole word of the name, case-insensitive; at most 5 matches plus the total count; pattern and wildcard characters rejected. A partial word ("Blue") matches nothing; a first word ("Bluewater") matches every account that has it.
- *Regions are exactly the four values.* A state, a city or any other area is not mapped to a region (no synonyms).

**Repeat-visit drivers** (ADR-073):
- *Jobs* are requests completed in the range (`archived_requests.completed_at`, as for first-time fix). A job *repeated* if it has a non-cancelled child request, whatever the child's date. Repeat rate = repeated jobs / jobs. Every repeat is recorded through a `repeat_visit_required` incident on the original job (an invariant of the generated data, checked by the integration suite).
- By `service_type`, `region` (the site's), `account` or `technician` (the original job's `assigned_technician_id`; jobs with none are "unassigned"): each group's jobs against every other job in range.
- By `incident_type`: for each type except `repeat_visit_required`, jobs with at least one incident of that type against jobs without one; a job can be in several groups. Plus jobs with any incident other than `repeat_visit_required` against jobs with none other, a single comparison: with at least 20 jobs on each side, Fisher's exact p < 0.05 and the any-other rate higher means the association is stated; otherwise the answer says the two didn't differ clearly. No Bonferroni.
- A group *stands out* only if it has at least 20 jobs, its repeat rate is above the rest's, and a two-sided Fisher's exact test of its 2×2 table (repeated / not, group / rest) gives p < 0.05 after Bonferroni correction (p × the number of groups with at least 20 jobs, capped at 1). Groups are listed by repeat rate, highest first, then more jobs, then name; at most 25.

**Rules fixed by the owner on 2026-10-09 (L-72)** — the cases above left open, each now one reading, enforced by the reporting tools and by the QA agent alike:
1. *Fisher's exact test, two-sided.* The p-value is the sum of the probabilities, under the hypergeometric distribution with the table's margins, of every 2×2 table whose probability is no greater than the observed table's (a relative tolerance of 1e-7 for ties). This is the definition of `scipy.stats.fisher_exact` with `alternative='two-sided'`.
2. *Order of a rate breakdown (incident rate, SLA compliance, first-time fix rate).* Worst rate first (highest for the incident rate, lowest for the other two); groups with the same rate: the larger denominator first, then the name; a group with no rate (zero denominator) last, in the same order. The cap of 25 applies after this order, so a tie at the cap keeps the groups resting on more cases. (Incident counts keep their own order: highest count, then name.)
3. *Incident types with no job.* In repeat-visit drivers by incident type, a type with no completed job in the range is not listed; `group_count` counts the groups listed.
4. *A group equal to all jobs.* A repeat-driver group that contains every job in the range has no "rest" to compare with. It is listed with its rate, is not compared, is left out of the Bonferroni count, has a null p-value and never stands out.
5. *Words of a name.* In `find_technician` and `find_account`, a word is a whitespace-separated token with every leading and trailing character that is not a letter or a digit removed, case-folded; a token with nothing left is not a word. "Co" and "Co." are the same word, so "Summit Distribution Co" finds "Summit Distribution Co."; punctuation inside a word ("O'Neil", "Mary-Ann") stays. The pattern and wildcard characters are rejected as before.
6. *Order of decline reasons.* A request is declined for the first rule that applies, in this order: the metric is unsupported; the breakdown is unsupported; the breakdown is not offered for the metric; the region is an unsupported area; repeat-visit drivers with a region or an account; a region filter with a breakdown by region; an account filter with a breakdown by account; repeat-visit drivers with a technician; a technician with any breakdown. The decline states that reason and carries no figures. Only a request that no rule declines is looked up by name, the technician before the account.
7. *Technician filter on repeat-visit drivers.* Repeat-visit drivers take no technician filter, as they take neither a region nor an account filter (ADR-073, ADR-086). A repeat-drivers question that names a technician is declined, with the reply to ask for repeat drivers by technician instead.

Define these once, here. If the reporting agent and the QA agent each compute them independently from prose, they will disagree, and you'll spend a sprint debugging a discrepancy that's actually a specification gap.

### Sentiment answers (rules written 2026-10-09 from ADR-066, ADR-067, ADR-068 and ADR-087, so the sentiment agent and the QA agent share one written spec)

Where an ADR is silent and the agent's code is the only implementation, the code's behaviour is written down here as the rule; those points are marked *(code)*. Nothing below is new behaviour.

1. **The comment set.** A comment is a `service_feedback` row with text (`feedback_text` not null). The set is the comments whose `submitted_at` falls in the inclusive UTC days of the range, restricted to the site's region (`locations.region` through the request's `location_id`) when one is given. A comment is *scored* when `sentiment_predictions` holds a row for it with the **current `model_version`** only: the SHA-256 of the committed `ml/sentiment/artifacts/bert_v1.manifest.json`.
2. **Coverage (ADR-067).** `n_comments` = comments in the set; `n_scored` = those that are scored; `complete` = (`n_scored` == `n_comments`). Every figure is computed over the scored comments only. A partial answer opens with its coverage line.
3. **The range and the bucket.** With dates named, those dates and the requested bucket (`month` by default). With none named: for a trend question the six calendar months ending at the as-of date's month, from the first day of the first of them through the as-of date, in monthly buckets whatever bucket was asked (ADR-068); otherwise the previous calendar month (ADR-050) with the requested bucket.
4. **Counts, shares and buckets.** Counts are scored comments by predicted label. A share is a count over `n_scored`, half-up to 4 places as a string, null when `n_scored` is 0. A bucket is a calendar month (`YYYY-MM`) or quarter (`YYYY-Qn`) of `submitted_at` in UTC. Only buckets holding at least one scored comment are listed *(code)*, sorted by name; each lists its scored count, label counts and flagged count, and the buckets sum to the totals.
5. **Flags (ADR-066).** A prediction is flagged when its calibrated top-class probability is below τ, the `calibration.threshold` of the manifest. The stored `confidence` is that probability rounded to 4 places, and the rule QA enforces for every prediction in the set is `flagged == (confidence < τ)` on the stored values, strictly, **except** when `|confidence − τ| ≤ 0.00005` (half a rounding step of the stored 4-place value): inside that band either flag is accepted, because the decision was made before rounding (owner's ruling 2026-10-09, L-77). The answer's flagged count is the number of flagged predictions in the set; each bucket's is the number in that bucket.
6. **The trend (ADR-068).** Over the listed buckets sorted by name: the latest listed bucket *(code)* against the pooled earlier listed buckets. With fewer than two buckets the verdict is "needs two periods" and no other trend field is set. The answer names the buckets it compared (`latest_bucket` and `earlier_buckets` in the data, and "Latest month, 2026-08: …" and "Earlier months, 2026-03 to 2026-07: …" in the text) and QA checks both. Otherwise, with `n1`, `x1` the latest bucket's scored and negative counts and `n2`, `x2` the earlier buckets' summed: the sides are *small* when `n1` or `n2` is under 20. The test is the two-sided two-proportion z-test with a pooled standard error: `pooled = (x1 + x2) / (n1 + n2)`, `se = sqrt(pooled × (1 − pooled) × (1/n1 + 1/n2))`, `z = (x1/n1 − x2/n2) / se`, `p = erfc(|z| / √2)`. When `se` is 0 *(code)*, or either side is empty, `z = 0` and `p = 1`, and the verdict must then be "no clear change" (owner's ruling 2026-10-09). The verdict is "rose" when the sides are not small, `p < 0.05` and `x1/n1 > x2/n2`; "fell" when not small, `p < 0.05` and not higher; otherwise "no clear change". The answer reports `z` and `p` rounded to 4 places, both counts on each side and `small_sample`.
7. **Quotes (at most 3).** Each quoted `feedback_id` exists, is in the set (in range and region, and scored), has the predicted label the question asked for when it asked for one, and its quoted text equals `feedback_text` exactly. The label, confidence (4 places), flag, region and `submitted_at` shown with a quote equal the stored ones. `quoted_feedback_ids` lists the quotes in order. **Which comments are quoted is fixed** (owner's ruling 2026-10-09, from the agent's one rule): among the comments in the set, of the asked label when the question asked for one, the three with the highest stored `confidence`, ties by the lowest `feedback_id`, in that order; fewer when fewer match; none when the question did not ask for comments. QA recomputes that list and the quoted ids must equal it. The question can ask for a label but not for flagged-only comments.
8. **Declines.** A sentiment question that asks for a breakdown by account, technician, service type or anything else other than time and region is declined, with no figures and no query. The parse reports one reason (`account`, `technician`, `service_type` or `other`) and the decline states it: there is no ordering among several reasons because the parse never reports more than one *(code)*. A decline is not otherwise checked for what the question "really" asked: that is the interpretation check's job, which is advisory (L-74).
9. **The rating cross-check (ADR-087, unchanged).** *Covered* comments: in the set, with a rating, predicted `positive` or `negative`. A *contradiction*: `positive` on 1 to 2 stars, or `negative` on 4 to 5. With `n` covered and `x` contradictions, `p0 = max(p̂, 0.01)` where `p̂ = 0.001485` is the baseline measured once over the full window (n = 4,715, x = 7), so `p0 = 0.01`. The answer fails if `n ≥ 20` and the one-sided exact binomial `P(X ≥ x | n, p0) < 0.01`; below 20 covered it is reported as `insufficient_coverage` and does not fail. `n`, `x`, `p0` and the result are reported on every sentiment verdict.

### Answer text: slots, rounding, zero denominators and small samples (rules written 2026-10-10 from ADR-033, ADR-046, ADR-068, ADR-072, ADR-073 and ADR-086 and the three renderers' behaviour, for L-81, L-82 and L-84)

Nothing below is new behaviour: it is what the template renderers do, written down so QA can check the text by position instead of by set. The renderers are `agent_reporting/render.py`, `agent_forecast/render.py` and `agent_sentiment/render.py`; no model writes any of this text.

1. **Slots.** The *numbers* an answer's text states are read left to right, after removing ISO dates (`YYYY-MM-DD`), bucket names (`YYYY-MM`, `YYYY-Qn`), `ADR-nnn` references, names (technician, account and group names) and quoted comment text. Each number is a *slot*: it stands for one named field of the data part, in the order below. The text is correct when its numbers, in order, are exactly the slots the data part calls for, each equal to its field formatted by rule 2. A number the data part has no slot for, a missing slot, and a slot whose number differs are three different failures. Set membership ("some other figure in the answer has this value") is not accepted. In every list, "min" is 20 (rule 4), and a number marked "template" is printed by the template, not taken from the data.
   - **Incident count:** `incident_count`, `by_severity.high`, `.medium`, `.low`. With a breakdown: the first 5 groups' `count` in listed order; then `group_count - 5` when that is above 0; then, when `truncated`, `group_count` and the number of groups listed.
   - **Incident rate, overall:** `rate`, 100 (template), `numerator`, `denominator`. When `rate` is null (no completed requests): only `numerator`.
   - **SLA compliance and first-time fix, overall:** the percentage of `rate`, `numerator`, `denominator`. When `rate` is null: no slot.
   - **A single filtered figure** (technician, account and/or region): incident rate: `rate`, 100, `numerator`, `denominator`; SLA and first-time fix: the percentage, `denominator`, `numerator`. When `rate` is null: no slot. A breakdown by a different dimension follows as below.
   - **A rate breakdown** (after the overall or filtered figure): for the first 5 groups whose `denominator` is at least min, in listed order: incident rate: `rate`, 100, `numerator`, `denominator`; SLA and first-time fix: the percentage, `numerator`, `denominator`. Then, when no group reaches min, the number min; otherwise, when `k` groups are below min, `k` and min. Then, when `truncated`, `group_count` and the number of groups listed. A group below min is not listed (rule 4), so its zero-denominator wording (rule 3) never appears in a ranked list.
   - **Repeat-visit drivers:** with no jobs, no slot. Otherwise `overall.repeated`, `overall.jobs`, the percentage of `overall.rate`; then for each group that stands out, in listed order: the percentage of `this.rate`, `this.repeated`, `this.jobs`, the percentage of `rest.rate`; or, when none stands out, the number 20 (template); then for the first 5 groups with `this.jobs` at least min: the percentage of `this.rate`, `this.repeated`, `this.jobs`; then, when `k` groups are below min, `k` and min; then, when `truncated`, `group_count` and the number listed; then, for `incident_type`, the any-other group (the percentage, `repeated`, `jobs`; none when it has no rate), the none group likewise, and the two percentages of the closing sentence (none for a side with no rate).
   - **Forecast:** the number of weeks requested (weeks shown plus `beyond_horizon_weeks`); when no week is shown, 26; for each served week in order: `point`, 80 (template), `lo80`, `hi80`; when `period_total` is present: the number of weeks shown, then `period_total`; for each band present, in the order 1-4, 5-13, 14-26: the band's two numbers (template, for example 5 and 13) then `shown_error`; when `beyond_horizon_weeks` is above 0 and weeks are shown: `beyond_horizon_weeks`, 26 (template); for each history week: `count`.
   - **Sentiment:** when partial: `n_scored`, `n_comments`; when `n_scored` is above 0: `n_scored`, then each label's count and share in the order positive, neutral, negative, mixed, then `flagged_count` and its share; for a trend with two periods: `latest_negative`, `latest_n`, its share, `earlier_negative`, `earlier_n`, its share, `p_value`; and, when `small_sample`, 20 (template); for each quote: `confidence`, `feedback_id`.
2. **Rounding, per quantity** (what the renderers do today; each quantity is rounded one way everywhere it appears):
   - *Counts* (incidents, severities, group counts, numerators, denominators, jobs, comments, flagged, history counts): the exact integer, thousands separators ignored.
   - *Incident rate and the per-group incident rates:* the stored 4-place string, as it is (`0.3871`).
   - *SLA, first-time fix and repeat-visit shares:* the stored 4-place fraction times 100, exactly, 2 places (`0.8881` is `88.81%`); no rounding occurs.
   - *Forecast weekly points, ranges and the period total:* the nearest whole number, a tie to the even number (Python's `round`); the total is rounded from the exact sum, not summed from rounded weeks.
   - *Forecast shown error:* one decimal place (Python's `.1f`).
   - *Sentiment shares:* the stored 4-place share times 100 to 1 place, half up (`0.4978` is `49.8%`); the flagged share and each trend side's share are the 4-place half-up fraction of the two counts, then 1 place half up.
   - *Sentiment p-value:* 4 decimal places (Python's `.4f`).
   - *Quote confidence:* the stored 4-place string.

   No slot is compared with a looser tolerance than its rule: a number that is one more than its field, or its field's ceiling where the rule rounds to nearest, is wrong.
3. **Zero denominators (L-81).** When a rate's denominator is 0 the rate is null and no rate is stated. The text states that there were no cases of the denominator's kind, and a numerator is **not** required in the text, except where the template prints it. The metrics word it differently, and the rule is the list:
   - *Incident rate, overall:* "No requests were completed [range], so there is no incident rate (N incidents reported)." The count of incidents is stated (slot `numerator`).
   - *SLA compliance, overall:* "No dispatched requests were completed [range], so there is no SLA compliance figure." No number.
   - *First-time fix, overall:* "No requests were completed [range], so there is no first-time fix rate figure." No number.
   - *A filtered figure:* "[Subject] completed no requests [range], so there is no incident rate." / "... completed no dispatched requests ..., so there is no SLA figure." / "... completed no requests ..., so there is no first-time fix rate." No number, and no small-sample marking.
   - *A group with no rate:* below min, so it is left out of a ranked list and counted in the left-out number (rule 4); in a text that lists it (none does today), incident rate: "[group]: no completed jobs (N incidents)"; SLA and first-time fix: "[group]: no qualifying requests".
   - *Repeat-visit drivers:* "No jobs were completed [range], so there are no repeat visits to compare." No number.
4. **Small samples (ADR-033, ADR-073, ADR-086).** The minimum is **20 cases**, the value of this rule, not a configuration: QA uses 20 whatever `REPORTING_MIN_GROUP_DENOMINATOR` says, and a deployment that sets another value is a deployment QA fails. A case is a completed request or a dispatched request (the denominator), or a completed job for repeat drivers.
   - (a) A single filtered rate (technician, account and/or region) whose `denominator` is below 20 and whose rate is not null carries the sentence "That is too few to compare reliably."; a filtered rate at or above 20 does not. An incident count, a repeat-driver answer and an unfiltered overall figure carry no such sentence.
   - (b) A breakdown's text ranks only groups at or above 20 cases, worst first, at most 5; says how many groups were left out ("N [dimension]s left out of the ranking for fewer than 20 cases; all are in the data" and, for repeat drivers, "N with fewer than 20 jobs left out of the list") exactly when that number is above 0, the number being QA's own count of groups below 20; and, when no group reaches 20, says "no [dimension] has at least 20 cases to rank". The data part keeps every group.

### Forecast target — **locked**

- **Target:** count of `service_requests` by `scheduled_datetime`
- **Grain:** weekly, ISO weeks (Monday start, UTC), 156 complete weeks from 2023-09-04 to 2026-08-30. Three windows, each fitted only on weeks before its origin (ADR-069): fold A tests 2024-09-02 to 2025-03-02 on one year of history (reported, not gated); fold B tests 2025-09-01 to 2026-03-01 on two years (sets the release gate); the headline holdout tests the final 26 weeks, 2026-03-02 to 2026-08-30, on 130 (ADR-018). The folds end before the holdout begins. The production model refits on all 156. Daily is too noisy at these volumes; monthly gives too few points to model
- **Filter:** all requests regardless of final status — you're forecasting *demand*, not completions. Forecasting only completions confounds customer demand with your own cancellation behavior
- **Segmentation:** total, with optional breakout by `service_type`. A slice and horizon band is served only if it passed the fold B gate and stayed within 20% MAPE on the holdout (ADR-071): today the total at every band, and install and repair at 5–13 weeks. QA reads `served` and `shown_error` from the `volume_v2` manifest
- **Model form:** **univariate** — date in, volume out. It never sees incidents or sentiment. This matters for the coupling decision in §4. `volume_v2`'s year-end indicator (ADR-070) is a function of the date alone, so the model stays univariate

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
| History window | **36 months** | Three full seasonal cycles. The final 26 weeks are the headline holdout, which misses the Q4 peak, so rolling-origin folds test Q4 2024 (about one cycle of history) and Q4 2025 (about two) (ADR-018, ADR-057) |
| `accounts` | 40–60 | Enough for account-level aggregation to be meaningful |
| `locations` | 150–250 | ~3–4 sites per account |
| `contacts` | 150–300 | |
| `technicians` | 25–40 | |
| `service_requests` | 15,000–25,000 | ~100–160/week — enough signal for weekly regression, small enough to stay inside free-tier Postgres |
| `archived_requests` | ~90% of requests | Remainder cancelled |
| `incidents` | 8–12% of completed requests | Realistic field service incident rate |
| `service_feedback` | 35–50% of completed requests (~7,200 rows) | Realistic survey response rate. Every row has `feedback_text`; only `rating` may be null (ADR-038) |

**Realised (loaded 2026-09-25, seed 20260923):** 20,230 requests, 18,063 completed, 2,067 incidents (10.2% of completed requests have one; missed_sla is 24.4% of incidents), 7,521 feedback rows (41.6% of completed). Sentiment mix 50.2% positive / 22.4% neutral / 19.6% negative / 7.8% mixed; hard cases 14.9%. Payment status: 94.8% paid, 4.1% disputed, 1.1% pending (pending only within six weeks of the snapshot, ADR-043). Cancellation rate 10.2%. Reference tables: 50 accounts, 198 contacts, 197 locations, 32 technicians (63 skill rows), 15 internal users; 140 `generation_parameters` rows.

**Signal as recovered by `validate.py` (2026-09-25, 66/66 checks pass, `data/generator/validation/2026-09-25/report.json`):** annual growth 8.5% (designed 8%); seasonal peak-to-trough 0.39 against 0.42 designed in the same K=3 basis; residual sd of log weekly volume 11.7% (designed effective ~10.6%); regional drop z 3.53; account drop 93% at account level; 150 direct-bill invoices at the 0.10 surcharge inside the billing window and 0 outside. Note: the account drop's dip in *weekly totals* measured z 3.92 (report-only check), against the ~1.4 designed, so it is not invisible in weekly totals as the anomaly row above describes. Closed 2026-09-25: realised z reported, no reseed.

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

| Table | `app_reporting` | `app_sentiment` | `app_forecast` | `app_qa` | `app_generator` | `app_eval` | `app_train` |
|---|---|---|---|---|---|---|---|
| `accounts` | SELECT | — | — | SELECT | ALL | SELECT | — |
| `contacts` | — | — | — | — | ALL | — | — |
| `locations` | SELECT | SELECT (columns)⁶ | — | SELECT | ALL | SELECT | — |
| `technicians` | SELECT | — | — | SELECT | ALL | SELECT | — |
| `technician_skills` | SELECT | — | — | SELECT | ALL | SELECT | — |
| `internal_users` | — | — | — | — | ALL | — | — |
| `service_requests` | SELECT | SELECT (columns)⁶ | SELECT (columns)³ | SELECT | ALL | SELECT | SELECT (columns)⁵ |
| `archived_requests` | SELECT | — | — | SELECT | ALL | SELECT | — |
| `incidents` | SELECT | **—** | — | SELECT | ALL | SELECT | **—** |
| `service_feedback` | SELECT (aggregate)¹ | SELECT (columns)² | — | SELECT | ALL | SELECT | SELECT (columns)⁴ |
| `sentiment_labels` | — | **—** | — | **—** | ALL | SELECT | SELECT |
| `generation_parameters` | — | — | — | **—** | ALL | SELECT | **—** |
| `sentiment_predictions` | — | SELECT, INSERT⁷ | — | SELECT | ALL | SELECT | **—** |

¹ Postgres has no aggregate-only privilege. This is implemented as a **column-level** `GRANT SELECT` covering every column of `service_feedback` **except `feedback_text`**, so the reporting agent can count and average ratings but is structurally unable to read a customer's raw words. See ADR-025.

² A **column-level** `GRANT SELECT` on exactly `feedback_id`, `request_id`, `submitted_at` and `feedback_text`: the text to classify, an identifier to report against, and the timestamp the sentiment tools filter on (`get_sentiment_summary` and `get_feedback_examples`, which replaced `get_feedback_batch`; ADR-067). **`rating` is withheld** because it is the QA agent's independent cross-check on sentiment classification (R-04); a sentiment agent that can see the stars is no longer being checked independently. See ADR-027, which supersedes ADR-025's table-level grant here.

³ A **column-level** `GRANT SELECT` on exactly `request_id`, `scheduled_datetime` and `service_type`. That is all the univariate forecast needs (ADR-018): a weekly count by `scheduled_datetime`, optionally broken out by `service_type`, with an identifier to count against. Billing and payment fields, cancellation detail, and every account, contact and technician identifier are withheld, and the forecast role has no access to `accounts`, `locations` or `archived_requests`. A breakout beyond `service_type` needs a new grant, migration and ADR. See ADR-035.

⁴ The same four columns as `app_sentiment` (²): `feedback_id`, `request_id`, `submitted_at`, `feedback_text`. **`rating` is withheld**: a sentiment model trained with the stars would undermine QA's independent rating cross-check (R-04, ADR-027). See ADR-063.

⁵ The same three columns as `app_forecast` (³): `request_id`, `scheduled_datetime`, `service_type`. Training reads exactly what inference reads; with no grant on `generation_parameters`, forecast training can't read the generator's answer key (ADR-058, ADR-063).

⁶ **Column-level** `GRANT SELECT` on `service_requests` (`request_id`, `location_id`) and `locations` (`location_id`, `region`): exactly the join from a comment to its site's region, which FR-07's regional questions need. No `account_id`, no `state`, no `accounts`; region carries no personal information and no staff-written text (ADR-067).

⁷ The only write any runtime role holds: `app_sentiment` may INSERT its own predictions (with `ON CONFLICT DO NOTHING`) and read them back, but holds no UPDATE or DELETE, so the server can't rewrite a stored prediction. `app_qa` and `app_eval` read it; `app_train` can't (ADR-067).

**Offline roles.** `app_eval` (validation and evaluation) and `app_train` (training) are read-only roles used only by offline scripts on the developer machine. No deployed service, compose service or Dockerfile ever holds their credentials; `tests/unit/test_offline_roles_isolation.py` fails if one references `DB_ROLE_EVAL_*` or `DB_ROLE_TRAIN_*`. `app_eval` holds what `app_qa` held before ADR-063, gold labels and generator parameters included; `app_qa` no longer reads either (ADR-055, ADR-063). Grants control tables and columns, not rows, so `app_train` could still read the test split's labels: split integrity rests on a split fixed and committed before training, and on review (L-25).

**Implementation:** this matrix is executable, not prose — `packages/db_models/src/db_models/access_matrix.py` is the authority for what is granted. `tests/unit/test_access_matrix.py` asserts it says what this table says, and `tests/integration/test_access_matrix_grants.py` asserts the migrated database grants exactly that, reads and writes both. Migrations carry frozen literal copies of the grants they applied rather than importing the module (ADR-027), so every grant change is a new migration. The roles migration additionally revokes the Postgres `PUBLIC` defaults (ADR-025), which this table does not cover.

Nine things this matrix enforces that a code convention wouldn't:

1. **The sentiment agent cannot read `sentiment_labels`.** Circular self-verification becomes structurally impossible, not just discouraged.
2. **The sentiment agent cannot read `incidents`.** Staff-written notes can never leak into the sentiment pipeline.
3. **No agent reads `contacts`.** Customer PII never enters an LLM context window — a strong, concrete point for the security writeup, and exactly the kind of deliberate scoping decision worth calling out in an interview.
4. **The sentiment agent cannot read `service_feedback.rating`.** The rating stays a genuinely independent signal for the QA agent to check sentiment against (R-04, ADR-027).
5. **The forecast agent cannot read billing or any customer or technician identifier.** It sees three columns of `service_requests` and nothing else (ADR-035).
6. **The runtime QA role cannot read gold labels or generator parameters.** `app_qa` has no grant on `sentiment_labels` or `generation_parameters`; answers in a real deployment have no gold labels, so QA never checks against them (ADR-055, ADR-063).
7. **Training cannot read `rating` or `generation_parameters`.** `app_train` reads the labels and exactly the columns the runtime models read, so neither leakage rule rests on convention (ADR-027, ADR-058, ADR-063).
8. **Training cannot read `sentiment_predictions`.** The model never trains on its own output (ADR-067).
9. **The only runtime write is `app_sentiment`'s INSERT into `sentiment_predictions`.** No UPDATE or DELETE, and no other table; every other runtime role is read-only (ADR-067).

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
- Every `incidents.request_id` and `service_feedback.request_id` resolves to a real request
- `archived_requests.completed_at >= service_requests.scheduled_datetime` — moved here from the check-constraint list, since it spans two tables

**Generator-validation check, run as `app_eval`** (moved from the QA list by ADR-063: it concerns how the data was generated, not any answer, and the runtime QA role can't read `sentiment_labels`):
- Every `service_feedback` row has a corresponding `sentiment_labels` row

**Derived-table invariants (`sentiment_predictions`, ADR-067):**
- At most one prediction per comment per model version: the primary key (`feedback_id`, `model_version`) enforces it
- `flagged` equals `confidence < τ` for that version's τ (from its manifest). The flag is decided on the unrounded probability, so a stored `confidence` within 0.00005 of τ can sit on the other side of τ after rounding; QA checks the rule with that tolerance
- `predicted_label` is the class with the highest calibrated probability, and `confidence` is that probability (CHECK 0–1)

The QA-agent invariants double as your data-generator validation suite (`validate.py` runs them all, as `app_eval`). Run it immediately after generation in Sprint 1 — finding a broken invariant in Sprint 4 means regenerating and redoing every downstream measurement.

---

## 9. Design Notes

- **Sensitive fields:** `payment_reference` holds last-4 or a transaction reference only, never a full card or account number — good practice regardless of the data being synthetic, and it keeps the habit correct. `contacts.phone`/`email` are PII-shaped even when generated; use reserved-for-documentation formats (e.g. `555-01xx` numbers, `example.com` domains) so nothing resembles a real person.
- **Indexing considerations for the MCP tools:** index `service_requests(scheduled_datetime)` for the forecast series, `(account_id, scheduled_datetime)` and `(request_status)` for reporting date-range and status queries, and `(parent_request_id)` for first-time-fix calculation; index `incidents(request_id)` and `(incident_type, reported_at)` for aggregation; index `service_feedback(request_id)` and `(submitted_at)` for sentiment batch pulls; index `archived_requests(completed_at)` for billing-period reporting.
- **Why `equipment_unit_count` instead of `NumOfStops`:** your original field assumed a transportation multi-stop model. In field service, the equivalent scaling factor is how many devices/units get serviced in one visit — same purpose (a request can be "bigger" than a single unit), correct domain.
- **The `payment_method` vs `payment_method_final` split is intentional, not redundant:** a request can be logged with one intended payment method and settled differently (e.g., a disputed credit card charge that gets rebilled as direct-bill). If that distinction doesn't matter for your use case, collapsing them is a fine simplification — but make that a documented decision, not a default.

---

## 10. Decisions Log

All seven open questions resolved. Recorded here so the reasoning survives into the ADRs and the evaluation report (ADR-044).

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

### DDL status — **implemented** (2026-09-20; current through Alembic head `3d7e1a9c5b20`, 2026-10-01)

The schema in this document is now implemented in code. Migration chain: `0f3c81a47b21` → `7d54e0c9a318` → `1ee8342c81a7` → `fae4b8c9814c` → `4c6589542b27` → `9135d8de9f27` → `ab53ceceeffe` → `95a2f308a9cd` → `3d7e1a9c5b20` (head).

| Artifact | Location |
|---|---|
| SQLAlchemy models (all 13 tables) | `packages/db_models/src/db_models/` |
| Controlled vocabularies | `packages/db_models/src/db_models/enums.py` |
| §7 access matrix, as data | `packages/db_models/src/db_models/access_matrix.py` |
| Initial migration — tables, constraints, §9 indexes (`0f3c81a47b21`) | `data/migrations/versions/*_initial_schema.py` |
| Roles and grants migration (frozen, ADR-027; `7d54e0c9a318`) | `data/migrations/versions/*_roles_and_grants.py` |
| Sentiment column-level feedback grant (ADR-027, `1ee8342c81a7`) | `data/migrations/versions/*_sentiment_feedback_column_grant.py` |
| Forecast column-level `service_requests` grant (ADR-035, `fae4b8c9814c`) | `data/migrations/versions/*_forecast_service_requests_column_grant.py` |
| `sentiment_labels`: `hard_case_type` replaces `is_sarcastic`, `corpus_id` added (ADR-037, `4c6589542b27`) | `data/migrations/versions/*_sentiment_labels_hard_case_type_and_.py` |
| `generation_parameters.param_group` gains `world` and `feedback` (ADR-038, `9135d8de9f27`) | `data/migrations/versions/*_param_group_world_and_feedback.py` |
| `locations.region`, the customer site's region (ADR-051, `ab53ceceeffe`) | `data/migrations/versions/*_locations_region.py` |
| Offline read roles `app_eval` and `app_train`; `sentiment_labels` and `generation_parameters` revoked from `app_qa` (ADR-063, `95a2f308a9cd`) | `data/migrations/versions/*_offline_read_roles.py` |
| `sentiment_predictions`; `app_sentiment` INSERT on it plus region column grants; SELECT for `app_qa` and `app_eval` (ADR-067, `3d7e1a9c5b20`) | `data/migrations/versions/*_sentiment_predictions_and_region_access.py` |
| Contract tests | `tests/unit/` |
| Live grant tests (reads and writes, per role; run in CI) | `tests/integration/` |
| Generator, loader and validation (ADR-042, ADR-043); dataset loaded 2026-09-25 | `data/generator/` |

**The models are the source of truth from here.** When this document and `db_models` disagree, the code is right and this file needs correcting — `alembic check` enforces that the migrations match the models, but nothing enforces that either matches this prose.

Three points where implementation required a decision this document had left open are recorded in ADR-025. Three corrections to this document itself are marked inline above (two `TIMESTAMP` → `TIMESTAMPTZ` fixes, five vocabularies missing from §5, and the `role_*` → `app_*` relabel in §7).
