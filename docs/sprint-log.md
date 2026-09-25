# Sprint Log — Agentic Service Operations Intelligence Platform

**Purpose:** The record of what was planned, what shipped, and what changed — updated at the start and end of every sprint. This is the primary evidence for the Agile-methodology requirement: a filled-in log across six sprints is what distinguishes a graded Agile project from a plan that happened to work out. Solo projects lose peer review as a check on drift; a consistently updated log is the substitute.

**Cadence:** Update the "Planned" section at sprint start, "Shipped" and "Retro" at sprint end. Update `risk-register.md` at every sprint boundary — do it in the same sitting as the retro so it actually happens.

---

## How to fill in each sprint

- **Goal (increment):** one sentence — what will be demoable at sprint end. Fixed at planning; don't rewrite it after the fact to match what shipped.
- **Planned:** the backlog items committed to at sprint start.
- **Shipped:** what actually got done. Cross-reference against Planned — gaps are data, not failures.
- **Carried over:** anything from Planned not done, moved to a future sprint (or explicitly dropped, with a one-line reason).
- **Blockers encountered:** anything that cost meaningful time — a library issue, a design decision that needed rework, an external dependency.
- **Retro:**
  - *What went well* — worth repeating deliberately, not just noticing in passing.
  - *What didn't* — specific, not "time management." What decision or estimate was wrong, and why.
  - *What changes next sprint* — one or two concrete adjustments, not a general resolution.
- **Academic deliverable status:** what's due this sprint per the milestone plan, and whether it's done, drafted, or slipped.
- **Decisions made this sprint:** cross-reference to new `decisions-log.md` entries, if any.

---

## Sprint 1 (Weeks 1–2) — Foundation
**Goal (increment):** Synthetic data generator producing validated, signal-bearing data; queryable locally.

**Planned:**
- [x] Repo scaffold, docker-compose, local Postgres — *Postgres running in Docker; both migrations applied and `alembic check` clean (2026-09-22)*
- [ ] CI skeleton
- [x] Schema finalized in `data-dictionary.md` (done ahead of Sprint 1 — see decisions log)
- [ ] Data generator + ground-truth tables (`sentiment_labels`, `generation_parameters`)
- [x] `data/generator/build_corpus.py` — one-off script that generates `feedback_text` through Google's API (ADR-030) — *built 2026-09-23, full run 2026-09-23 to 09-25*
  - [x] Model choice (ADR-030 open item) — *decided 2026-09-23: Flash-Lite 3.5 generates, Gemma 4 31B judges labels; ADR-036 to record it. Bake-off: `experiments/bakeoff/2026-09-23/` (blind review 13/20 vs 15/20, a draw)*
  - [ ] Prompt v1 + Gemma judge trial — *ran 2026-09-23 (`experiments/bakeoff/2026-09-23-v1/`): opener repetition fixed, judge agrees 54/80 but only 2/20 on neutral. Blind review scored: human–judge 32/40, both 2/10 vs intended on neutral — the generator, not the judge, misses neutral; believability fell to 2.10, sounds-AI 20/40*
  - [ ] Prompt v2 targeted rerun — *ran 2026-09-23 (`experiments/bakeoff/2026-09-23-v2/`): judge vs intended neutral 8/20 (FAIL, bar 14), positive + serious incident 9/10 (PASS), mixed + incident 2/8 (FAIL, bar 6); all opener checks PASS; blind review not done (superseded by v3)*
  - [ ] Prompt v3, final iteration — *ran 2026-09-23 (`experiments/bakeoff/2026-09-23-v3/`): judge neutral 10/20 (FAIL, bar 14; minimal 1/7), positive + serious incident 10/10 (PASS), mixed + minor incident 4/8 (FAIL, bar 6); opener checks PASS. Blind review: human neutral 6/10 (FAIL, bar 7), sounds-AI 10/24 (FAIL, bar 25%); human labels positive + serious incident as mixed 5/6, judge says positive 6/6*
- [x] Committed corpus: `data/generator/corpus/feedback_text.jsonl` plus `provenance.json` (model ID, date, prompt, settings) — *13,184 accepted comments in 91 cells, complete under the q99 rule (2026-09-25)*
- [ ] Corpus label validation in `validate.py` — sample comments against their requested sentiment, reject exact and near duplicates — before the corpus is accepted
- [x] Validate signal is actually recoverable — plot seasonality, confirm sentiment/severity coupling shows up in the data — *`validate.py`, 66/66 checks pass (2026-09-25)*
- [x] GCP budget alerts configured ($50, $80) — *$50/$80 alerts on the billing account (2026-09-24); dedicated paid project `A2A-agentic-service-ops-gcp` with a $10 alert (50/90/100%) and a $5 prepaid balance, auto-reload off (2026-09-24) (ADR-041)*
- [x] Confirm Google AI student credit coverage and expiry (open item from ADR-006) — *confirmed not available; free tier adopted (ADR-029, 2026-09-22)*

**Shipped:**
- Python packaging foundation: root `pyproject.toml` (uv-workspace-shaped, pip-installable today) and `packages/db_models` as the first workspace package.
- `packages/db_models/` — SQLAlchemy 2.0 models for all 12 tables, the 21 controlled vocabularies as `StrEnum`, and the §7 access matrix as an importable data structure.
- Alembic under `data/migrations/`, building its connection string from `POSTGRES_*` environment variables so the Sprint 5 Cloud SQL switch is a config change (ADR-007).
- Two migrations: initial schema (tables, FKs, CHECK constraints, the §9 indexes) and the five least-privilege roles with the §7 grants.
- `docker-compose.yml` with Postgres 16.
- 34 contract tests covering the schema, the access matrix, and the roles migration's credential handling, running without a database.
- `alembic upgrade head` run against local Postgres (both migrations applied); `alembic check` reports "No new upgrade operations detected." The hand-written initial migration now matches the models, including column types and server defaults.
- Grants integration test (`tests/integration/test_access_matrix_grants.py`, 401 cases): logs in as each of the five roles with its `.env` credentials and checks reads on every table, plus every column of `service_feedback` and `service_requests`, and INSERT/UPDATE/DELETE on every table (the generator can write everywhere, no agent role anywhere), all against `db_models.access_matrix`. Write probes touch zero rows. Checked by drifting the matrix in memory both ways (an extra grant, a missing grant) and confirming exactly the right cases fail. Skips when no database is reachable.
- `app_sentiment` tightened to a column-level grant on `service_feedback` (`feedback_id`, `request_id`, `submitted_at`, `feedback_text`), so `rating` stays an independent QA cross-check (R-04). Applied by a new migration, `1ee8342c81a7`.
- Roles-and-grants migration frozen to a literal snapshot of its original matrix instead of importing the live one (ADR-027). Verified by upgrading a fresh database to that revision (sentiment still had its original table-level grant) and then to head, with `alembic check` and both test suites green.
- `app_forecast` narrowed to a column-level grant on `service_requests` (`request_id`, `scheduled_datetime`, `service_type`), with SELECT on `accounts`, `locations` and `archived_requests` revoked (ADR-035). Applied by a new migration, `fae4b8c9814c`. Verified: `alembic check` clean at head, grants integration test green, and a one-revision downgrade restored the original four table-level grants with no leftover column ACLs, then re-upgraded green.
- `sentiment_labels`: `hard_case_type` (`none`/`sarcastic`/`implicit`, the 22nd vocabulary) replaces `is_sarcastic`, and `corpus_id` (NOT NULL, UNIQUE) is added (ADR-037). Applied by a new migration, `4c6589542b27`. Verified: `alembic upgrade head` then `alembic check` clean, unit (105) and grants integration (401) suites green; a one-revision downgrade restored `is_sarcastic` (BOOLEAN NOT NULL DEFAULT false) and removed both new columns and their constraints, then re-upgrade, `alembic check` and both suites green again.
- `data/generator/parameters.py`: ground truth of the synthetic world — every generation parameter with a note, seed derivation (`derive_seed`, SHA-256 stage keys), analytic expected totals, the solved no-incident sentiment mix, the ADR-036 cell rules, corpus sizing (119 cells, 11,990 comments), and `validate_parameters()`; 35 offline tests. numpy pinned in the `generator` extra. Anomaly strength and several chosen values await owner review.
- `generation_parameters.param_group` gains `world` and `feedback` (ADR-038). Applied by a new migration, `9135d8de9f27`. Verified: `alembic upgrade head` then `alembic check` clean, unit (157) and grants integration (401) suites green; a one-revision downgrade restored the five-value CHECK, then re-upgrade, `alembic check` and both suites green again. A downgrade with a `world` row present fails with a CheckViolation, as intended. `parameters.py` updated to match: regions, a regional anomaly (z = 3.3), effective noise, age-dependent incident status, Poisson-quantile corpus sizing (13,307 comments).
- `data/generator/build_corpus.py`: resumable generate -> checks -> judge -> select -> top-up pipeline over append-only stage files, versioned prompts (`prompts/generator_v4.txt`, `judge_v4.txt`), corpus_id at spec creation, Pacific-day request cap (480 Flash-Lite), clean stop on daily-quota 429. Near-duplicates are checked across the WHOLE corpus (MinHash LSH, 5-gram character Jaccard > 0.6), not within a cell. Test batch only (60 specs, `experiments/corpus_test/2026-09-23/`); full run not started. 41 offline tests.
- Test-batch fixes in `build_corpus.py`: Flash-Lite returned JSON with unquoted keys for one batch (20 of 60 comments lost), so the parser now repairs bare keys after strict parsing fails and re-requests a batch that still parses to zero; a crash-truncated stage-file line no longer swallows the next append (the partial line is terminated first). ADR-039 applied: 91 corpus cells, 13,091 comments, 655 Flash-Lite requests; scipy pinned.
- Feedback corpus complete (ADR-030, ADR-036 to ADR-041): 13,184 accepted comments in 91 cells, complete under the q99 rule — every cell's accepted count covers its Poisson q99 demand (minimum 1.2x); 5 plain-neutral cells sit below their 2x build target, which was headroom for judge rejections, not a requirement. Generated 2026-09-23 to 09-25 on 429 free-tier and 570 paid Flash-Lite batches (~$1.40 estimated at list prices, plus free-tier quota) with 2,232 free-tier Gemma judge requests.
- Fixes found during the corpus run: weekday names allowed by the date check, and by the name-like check too (capitalised weekdays had been tripping it; 152 comments reinstated); persistent Gemma 500/503 errors stop the run cleanly and resumably instead of crashing past `finalize`; billing or balance errors on the paid key stop cleanly without retries; `--finalize` rebuilds the outputs from the stage files, and completion follows the q99 rule.
- Generator and loader: `generate.py` (pure, deterministic: explicit IDs, per-state timezones, committed name lists) and `load.py` (one-transaction reload as `app_generator`), with every world rule and constant in `parameters.py` (ADR-042, ADR-043). Loaded into local Postgres on 2026-09-25: 20,230 requests, 18,063 archived, 2,067 incidents, 7,521 feedback rows with labels, 140 generation_parameters rows (plus 50 accounts, 198 contacts, 197 locations, 32 technicians, 63 skills, 15 users); about 10 s of inserts, 14 s end to end. Read-back invariants hold; the grants suite passes with data (401); two generations hash identically.
- `data/generator/validate.py` run against local Postgres on 2026-09-25: **66 of 66 checks pass** — 22 invariants plus 6 SQL cross-checks (all 0), distributions, signal recovery (growth 8.5% vs 8%, seasonal range 0.39 vs 0.42 designed in the same K=3 basis, residual sd 11.7%), anomalies (regional z 3.53, account drop 93%, billing 150/0), couplings (all p >= 0.07), and corpus integrity. Read as `app_forecast` (three columns, ADR-035) and `app_qa`; truth from `generation_parameters`. Output: `data/generator/validation/2026-09-25/`.
- Docs: ADR-025 added; three corrections to `data-dictionary.md` that writing the DDL exposed.

**Carried over:**
- CI skeleton.
- The broken Alembic ruff post-write hook (`Could not find entrypoint console_scripts.ruff`).
- Corpus label sanity spot-check, ~30 comments (ADR-040).

**The Sprint 1 goal was not met.** The increment was a validated, signal-bearing synthetic
dataset, queryable locally; the schema, roles, parameters, and the frozen feedback corpus
shipped, but the generator itself did not. Label design for the corpus took the sprint: a
model bake-off, four prompt rounds (v0 to v3), and a test batch, followed by the multi-day
corpus run.

**Blockers encountered:**
- ~~**Docker Desktop is not installed on the development machine**, so no Postgres is reachable. Consequences: the initial migration had to be hand-written rather than autogenerated, and `alembic upgrade head` has not been run. The models-vs-migration risk this creates is covered by offline contract tests, but the authoritative check — `alembic upgrade head` followed by `alembic check` — is still outstanding and should be the first thing done once Docker is installed. Installing it is now the gate on the data generator too.~~ **Resolved 2026-09-22:** Docker Desktop installed, Postgres 16 running, `alembic upgrade head` applied both migrations and `alembic check` reported no pending operations.

**Retro:**
- What went well:
- What didn't:
- What changes next sprint:

**Academic deliverable status:** Problem statement, project charter, initial risk register — *(status)*

**Decisions made this sprint:**
- ADR-025 — grant enforcement details: column-level `service_feedback` grant for reporting, `PUBLIC` defaults revoked, the cross-table `completed_at` invariant left to QA rather than a trigger.
- ADR-027 — sentiment's `service_feedback` grant made column-level with `rating` withheld (supersedes ADR-025 in part); migrations are immutable snapshots that never import the live matrix, and each grant change gets its own migration.
- ADR-028 — role names are required, never defaulted: a blank `DB_ROLE_*_USER` fails the roles migration just like a blank password.
- ADR-029 — runtime inference on the Gemini API free tier, Flash-Lite default for all agents (supersedes ADR-006 in part); Pro-for-QA deferred to a spend-capped Sprint 5 test.
- ADR-030 — `feedback_text` is LLM-generated once by `build_corpus.py` and frozen as a committed corpus with a provenance record; `generate.py` never calls an API.
- ADR-031 — single-shot interaction is the committed scope; multi-turn only as a scope expansion decided at the Sprint 4 boundary, never built in Sprint 6.
- ADR-032 — compound (multi-specialist) routing out of scope; the orchestrator detects multi-domain questions and tells the user to submit each part separately.
- ADR-033 — reporting may break metrics out by individual technician, framed as decision support, with every rate shown alongside its completed-job count.
- ADR-034 — 120-second end-to-end timeout ceiling, reusing ADR-022's degraded-result path; latency is measured, not targeted.
- ADR-035 — `app_forecast` narrowed to a column-level grant on `service_requests` (`request_id`, `scheduled_datetime`, `service_type`); SELECT on `accounts`, `locations` and `archived_requests` revoked.
- ADR-036 — feedback corpus design: Flash-Lite writes, Gemma 4 judges; hard cases are sarcastic and implicit; content-type label definitions and cell rules; plain labels judge-confirmed, hard cases unfiltered; ~200-comment blind human review (supersedes ADR-019, ADR-021 and ADR-030 in part).
- ADR-037 — `sentiment_labels.hard_case_type` (`none`, `sarcastic`, `implicit`) replaces `is_sarcastic`; `corpus_id` (UNIQUE) links each label to its corpus comment and enforces no reuse in the database.
- ADR-038 — generator parameters: text on every feedback row; account, regional and billing anomalies scored as z against effective noise; coherence rules; Poisson-quantile corpus sizing; `param_group` gains `world` and `feedback`.
- ADR-039 — positive feedback on incident rows draws its comment from the no-incident positive cell for the same service type and style; the 28 positive-with-incident cells are removed (supersedes ADR-036 in part).
- ADR-040 — sentiment labels are defined by the ADR-036 written specification (plain: judge-confirmed intent; hard cases: intent, judge disagreement reported); the human review becomes a ~30-comment sanity check with no agreement gate (supersedes ADR-036 in part).
- ADR-041 — remaining Flash-Lite corpus generation runs on a separate paid, spend-capped project (own key, $10 budget alert, per-session request cap in code); the Gemma judge stays on the free tier (supersedes ADR-029 in part).
- ADR-042 — the generator writes explicit deterministic IDs (OVERRIDING SYSTEM VALUE), uses one timezone per state and committed name lists, and loads as `app_generator` in one transaction.
- ADR-043 — generator world rules: incidents conditioned on SLA outcome (~0.25 vs ~0.08), a snapshot at window end + 12h, age-dependent incident and payment statuses, templated incident notes.

---

## Sprint 2 (Weeks 3–4) — First vertical slice
**Goal (increment):** Ask a natural-language question about incidents, get a verified answer, end to end.

**Planned:**
- [ ] MCP server #1 (incidents) with scoped tools + dedicated DB role
- [ ] Reporting agent + A2A Agent Card
- [ ] Minimal orchestrator routing to a single agent

**Shipped:**
*(fill in at sprint end)*

**Carried over:**
*(fill in at sprint end)*

**Blockers encountered:**
*(fill in at sprint end)*

**Retro:**
- What went well:
- What didn't:
- What changes next sprint:

**Academic deliverable status:** Literature review, architecture documentation — *(status)*

**Decisions made this sprint:**

*Note: this is the highest-risk sprint in the plan — it proves the entire MCP → A2A → orchestrator path. If it slips, that's schedule signal worth taking seriously, not just noting.*

---

## Sprint 3 (Weeks 5–6) — Analytical agents
**Goal (increment):** All three specialists working; forecast beats a naive baseline or the gap is documented.

**Planned:**
- [ ] MCP servers #2 and #3 (feedback, volume)
- [ ] Forecast agent + regression model + seasonal-naive baseline comparison
- [ ] Sentiment agent + confidence scoring
- [ ] Sentiment eval reports neutral accuracy by neutral kind (via `corpus_id`; neutral is 73% administrative) and hard-case accuracy with the judge disagreement rates alongside (ADR-040)
- [ ] Orchestrator routes across all three

**Shipped:**
*(fill in at sprint end)*

**Carried over:**
*(fill in at sprint end)*

**Blockers encountered:**
*(fill in at sprint end)*

**Retro:**
- What went well:
- What didn't:
- What changes next sprint:

**Academic deliverable status:** Methodology section, mid-point status deliverable — *(status)*

**Decisions made this sprint:**

---

## Sprint 4 (Weeks 7–8) — Verification
**Goal (increment):** QA agent operational with all three verification strategies; measurable catch rate.

**Planned:**
- [ ] QA agent — deterministic re-check (reporting), backtest threshold (forecast), labeled-holdout scoring (sentiment)
- [ ] Bounded retry loop (max 2), escalation path on final failure
- [ ] Fault-injection harness for QA catch-rate measurement
- [ ] Decide the eval-run approach before Sprint 5: split runs across
  days on the free tier vs. a paid, spend-capped eval project. Price a
  full routing eval run (~300-700 requests) on paid Flash-Lite using the
  official pricing page, and add that cost to the budget alongside the
  ~$20-30 Pro-for-QA test (ADR-029).

**Shipped:**
*(fill in at sprint end)*

**Carried over:**
*(fill in at sprint end)*

**Blockers encountered:**
*(fill in at sprint end)*

**Retro:**
- What went well:
- What didn't:
- What changes next sprint:

**Academic deliverable status:** Ethics & responsible-AI section, security design documentation — *(status)*

**Decisions made this sprint:**

*Note: scope-expansion decisions (broader capability within the existing three domains) are only appropriate if genuinely ahead of plan at this boundary — see the working agreement in `architecture.md` §13.*

---

## Sprint 5 (Weeks 9–10) — Interface & evaluation
**Goal (increment):** Deployed system with a working UI; routing accuracy reported with failure analysis.

**Planned:**
- [ ] Routing eval harness + failure-case analysis (ambiguous, multi-domain, and out-of-scope intents included)
- [ ] FastAPI gateway + thin React UI
- [ ] Migrate Postgres to Cloud SQL; first Cloud Run deployment
- [ ] Verify revision promotion immediately after deploy (known failure mode from a prior project — see risk register)

**Shipped:**
*(fill in at sprint end)*

**Carried over:**
*(fill in at sprint end)*

**Blockers encountered:**
*(fill in at sprint end)*

**Retro:**
- What went well:
- What didn't:
- What changes next sprint:

**Academic deliverable status:** Results/evaluation writeup begins, draft final paper — *(status)*

**Decisions made this sprint:**

---

## Sprint 6 (Weeks 11–12) — Hardening & delivery
**Goal (increment):** Production-grade checklist closed out; demo rehearsed.

**Planned:**
- [ ] Observability, CI/CD completion, graceful degradation, load/latency testing
- [ ] Production-grade checklist (`architecture.md` §7) audited item by item
- [ ] Final paper, presentation, demo rehearsal

**Shipped:**
*(fill in at sprint end)*

**Carried over:**
*(fill in at sprint end)*

**Blockers encountered:**
*(fill in at sprint end)*

**Retro:**
- What went well:
- What didn't:
- What changes next sprint: *(n/a — final sprint; note instead what you'd do differently on a future project)*

**Academic deliverable status:** Final paper, presentation, demo — *(status)*

**Decisions made this sprint:**

*Note: this sprint is protected buffer, not planned work with a buffer label. If Sprints 1–5 ran clean, use the slack for polish and rehearsal — not for starting anything new.*

---

## Cumulative Summary
*(fill in progressively — one line per sprint, for a fast look-back when writing the final paper)*

| Sprint | Goal met? | Key learning | Scope change? |
|---|---|---|---|
| 1 | | | |
| 2 | | | |
| 3 | | | |
| 4 | | | |
| 5 | | | |
| 6 | | | |
