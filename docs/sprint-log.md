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

## Sprint 1 (Weeks 1–2, 2026-09-14 to 2026-09-27) — Foundation
**Goal (increment):** Synthetic data generator producing validated, signal-bearing data; queryable locally.

**Planned:**
- [x] Repo scaffold, docker-compose, local Postgres — *Postgres running in Docker; both migrations applied and `alembic check` clean (2026-09-22)*
- [x] CI skeleton — *`.github/workflows/ci.yml`: lint, unit and integration jobs; green on first run 2026-09-25*
- [x] Schema finalized in `data-dictionary.md` (done ahead of Sprint 1 — see decisions log)
- [x] Data generator + ground-truth tables (`sentiment_labels`, `generation_parameters`) — *`generate.py` and `load.py` shipped; dataset loaded into local Postgres 2026-09-25*
- [x] `data/generator/build_corpus.py` — one-off script that generates `feedback_text` through Google's API (ADR-030) — *built 2026-09-23, full run 2026-09-23 to 09-25*
  - [x] Model choice (ADR-030 open item) — *decided 2026-09-23: Flash-Lite 3.5 generates, Gemma 4 31B judges labels; ADR-036 to record it. Bake-off: `experiments/bakeoff/2026-09-23/` (blind review 13/20 vs 15/20, a draw)*
  - [x] Prompt v1 + Gemma judge trial — *ran 2026-09-23 (`experiments/bakeoff/2026-09-23-v1/`): opener repetition fixed, judge agrees 54/80 but only 2/20 on neutral. Blind review scored: human–judge 32/40, both 2/10 vs intended on neutral — the generator, not the judge, misses neutral; believability fell to 2.10, sounds-AI 20/40*
  - [x] Prompt v2 targeted rerun — *ran 2026-09-23 (`experiments/bakeoff/2026-09-23-v2/`): judge vs intended neutral 8/20 (FAIL, bar 14), positive + serious incident 9/10 (PASS), mixed + incident 2/8 (FAIL, bar 6); all opener checks PASS; blind review not done (superseded by v3)*
  - [x] Prompt v3, final iteration — *ran 2026-09-23 (`experiments/bakeoff/2026-09-23-v3/`): judge neutral 10/20 (FAIL, bar 14; minimal 1/7), positive + serious incident 10/10 (PASS), mixed + minor incident 4/8 (FAIL, bar 6); opener checks PASS. Blind review: human neutral 6/10 (FAIL, bar 7), sounds-AI 10/24 (FAIL, bar 25%); human labels positive + serious incident as mixed 5/6, judge says positive 6/6*
- [x] Committed corpus: `data/generator/corpus/feedback_text.jsonl` plus `provenance.json` (model ID, date, prompt, settings) — *13,184 accepted comments in 91 cells, complete under the q99 rule (2026-09-25)*
- [x] Corpus label validation in `validate.py` — sample comments against their requested sentiment, reject exact and near duplicates — before the corpus is accepted — *delivered in the form ADR-040 set: plain labels judge-confirmed, exact and near duplicates rejected corpus-wide in `build_corpus.py` and rechecked by `validate.py` (group F), and a 30-comment sanity spot-check (30/30 usable, 2026-09-25)*
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
- ADR-040 sanity spot-check: 30/30 comments usable (no broken, off-domain, prohibited, contradictory, or plainly mislabelled comments), 2026-09-25 (`data/generator/validation/2026-09-25/spot_check.csv`).
- CI skeleton (2026-09-25): `.github/workflows/ci.yml` runs on every push and on PRs to main, Python 3.12 with pip caching, installing exactly as local development does. Jobs: lint (ruff check and format --check), unit (the offline suite), and integration (a Postgres 16 service container, `alembic upgrade head`, `alembic check`, then the grants suite). CI-only ephemeral role credentials in the workflow; `REQUIRE_INTEGRATION_DB=1` turns any integration skip into a failure. ruff pinned to 0.16.8 so local and CI format identically. Green on the first run (lint 29 s, unit 44 s, integration 46 s).
- Alembic ruff post-write hook fixed (2026-09-25): the `console_scripts` runner failed because ruff ships as a binary with no Python entry point; it now uses the `exec` runner on the venv's ruff. Verified with a throwaway revision that the hook reformatted, then deleted; `alembic heads` unchanged.
- Docs: ADR-025 added; three corrections to `data-dictionary.md` that writing the DDL exposed.

**Carried over:**

Sprint goal met 2026-09-25, inside the sprint (ends 2026-09-27). Label design for the
corpus consumed most of the sprint (four prompt rounds plus a test batch); see the retro.

**Blockers encountered:**
- ~~**Docker Desktop is not installed on the development machine**, so no Postgres is reachable. Consequences: the initial migration had to be hand-written rather than autogenerated, and `alembic upgrade head` has not been run. The models-vs-migration risk this creates is covered by offline contract tests, but the authoritative check — `alembic upgrade head` followed by `alembic check` — is still outstanding and should be the first thing done once Docker is installed. Installing it is now the gate on the data generator too.~~ **Resolved 2026-09-22:** Docker Desktop installed, Postgres 16 running, `alembic upgrade head` applied both migrations and `alembic check` reported no pending operations.

**Retro:**
- What went well:
  -  Claims enforced, then tested against the live system. Least privilege is enforced by grants and asserted by a 401-case integration suite, which was itself checked by drifting the matrix both ways. Migrations are frozen snapshots verified by up/down/up cycles. Repeat: every security or data claim gets a test that fails when the claim is false, and the test is broken on purpose once to prove it.
  - Pipelines built to be interrupted. build_corpus.py's append-only stage files and clean stops (daily-quota 429, Gemma 500/503, billing errors) absorbed a free-to-paid switch mid-run, a crash-truncated line, and malformed JSON without losing work. This is the pattern for packages/llm.
  - Truth read from the database, not constants: validate.py reads generation_parameters as app_qa and the forecast columns as app_forecast (66/66 passed). Two generations hash identically.
  - Spending money was decided on a written comparison (ADR-041): about $1.40 bought back about two days.

- What didn't:
  - The label-design loop had pass bars but no stop rule. It ran four prompt rounds plus a test batch and produced three superseding ADRs in three days (036, 039, 040). Neutral never met its bar (8/20, then 10/20, against 14). The loop ended by changing the criterion (specification-defined labels, and the review cut from 200 comments to 30, ADR-040), not by passing it. That option existed before round one. It cost most of the sprint: the goal was met 09-25, the same day the register had logged it as missed.
  - Assumptions became requirements by repetition. The project charter began as a planning guess. It was then copied into the sprint log, the week-2 status report, and the risk review, and carried into Sprint 2 planning as an open conflict. The course materials have no charter. "The final paper" followed the same path: five ADRs name it as where limitations get stated, and there is no final paper. Neither was checked against the source it claimed to come from, and each repetition made it look more checked. R-09 was the same failure at the scale of the whole plan.
  - ADR-037 and ADR-038 replaced decisions from ADR-019 and ADR-030 while their headers said "supersedes nothing." The index caught it; the entries didn't. This is the answer to R-01's question, "what would a reviewer have flagged?"

- What changes next sprint:
  1. Any fact about an external requirement (deliverable, rubric, quota, price, SDK capability) is written with its source the first time, or marked UNCONFIRMED. Nothing marked UNCONFIRMED is planned against or copied into a second file.
  2. Every design loop starts with a written stop rule and budget: maximum rounds or dates, and what happens at the limit (accept, change the criterion, or cut). Write it in the sprint log before round one. First uses: packages/llm and the R-06 A2A checkpoint.

**Academic deliverable status:**
- `01-proposal-business-case.md` (due 2026-09-27): complete.
- `02-requirements-analysis.md` (due 2026-10-04, in Sprint 2): complete early, in Sprint 1.
- Weekly status report (week 2, 09-21 to 09-27): complete, submitted; in
  `docs/academic/00-Weekly-Status-Reports.md` (maintained by Eric).
- `docs/academic/` also holds placeholders for `03` to `06`, due in Sprints 3 and 4
  (`architecture.md` §10).

The deliverables originally listed here (problem statement, project charter, initial risk
register) were planning assumptions that did not match the course (R-09). The milestone plan
was reconciled against the course calendar on 2026-09-25 (`architecture.md` §10). Confirmed
from the course materials that no charter is due.

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
- Account-drop anomaly (ADR-038 designed it invisible in weekly totals, z ≈ 1.4; `validate.py` measured a weekly-total dip of z 3.92): closed; realised z reported, no reseed.

---

## Sprint 2 (Weeks 3–4, 2026-09-28 to 2026-10-11) — First vertical slice
**Goal (increment):** Ask a natural-language incident question; the orchestrator routes it over A2A to the reporting agent, which answers through the incidents MCP server; an e2e test confirms the figures match an independent SQL computation.

*Reworded at planning (2026-09-25) because the QA agent is Sprint 4.*

**Planned:**
- [x] Walking skeleton by 2026-10-02: pin MCP and A2A SDKs and confirm spec targets (R-12); one MCP tool (`get_incidents_by_date_range`) as `app_reporting`; reporting agent calls it over streamable HTTP and serves an Agent Card; orchestrator fetches the card and sends one blocking `SendMessage` with a hardcoded route; all in docker-compose; no LLM
  *Done 2026-09-25, on `feat/walking-skeleton`: `mcp==2.2.0` and `a2a-sdk==1.1.5` (ADR-047); all hops real in docker-compose; e2e figures match `app_qa` SQL; one trace id spans all three services.*
- [ ] `packages/llm` (budget 1.5 days): 429 handling lifted from `build_corpus.py`, separating per-minute (back off, retry after the stated delay) from daily quota (stop cleanly, typed error); free key default; paid only with an explicit flag, its own key and a required request cap; token metering on every call, logged as list-price equivalent; one provider; done = offline tests pass against a fake transport
- [ ] Orchestrator classification (reporting, out-of-scope, other domain not yet available, multi-domain per ADR-032), with 20–30 seeded labelled intents as test fixtures
- [ ] Reporting agent question parsing per ADR-046; two or three reporting tools covering the FR-06 examples; template-rendered answers; e2e test against independent SQL
- [ ] Portable Alembic ruff hook (Alembic `module` runner if the installed version supports it); verified locally and in CI
- [ ] Draft `03-planning-management.md` 2026-10-08 to 10-11, after checking its rubric

R-06 checkpoint: skeleton hop working by 2026-10-02, or hold the scope conversation that day;
LLM-classified question answered end to end in docker-compose by 2026-10-07. Log hours per
layer (MCP, A2A, llm, orchestrator). Work a test can verify runs in Claude Code cloud sessions
and returns as a PR; anything needing a real API key, `gcloud`, or a judgment call runs
locally. The paid key never goes into a cloud environment.

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

**Academic deliverable status:**
- `02-requirements-analysis.md` (due 2026-10-04): complete early, in Sprint 1.
- Weekly status report due (maintained by Eric)

**For Sprint 2 planning** *(resolved 2026-09-25)*:
- `06-production-support.md` (due 11-08) is supported by the Sprint 4 slice deploy (ADR-045).
- The golden set and labelled routing set are Sprint 3 deliverables feeding
  `05-test-scenarios.md` (due 11-01), drafted in Sprint 3 week 2.
- `03` is drafted late in Sprint 2; `04` early in Sprint 3, after the R-06 checkpoint.
- No charter is due (confirmed from the course materials).
- No final paper (ADR-044).
- The Sprint 4 eval-run item is reduced to pricing a full routing eval run (ADR-041 decided
  the rest), counting two LLM calls per request (ADR-046).

**Decisions made this sprint:**
- ADR-044 — there is no final paper; limitations and results go in `docs/evaluation-report.md` (Sprint 6) and the final presentation.
- ADR-045 — minimal Cloud Run deploy of the reporting slice with Cloud SQL in Sprint 4, 2026-11-02 to 11-04, with a stop rule (supersedes ADR-007 in part).
- ADR-046 — specialists parse their own questions with one LLM call into a typed request; figures stay deterministic and answers are template-rendered.

*Note: this is the highest-risk sprint in the plan — it proves the entire MCP → A2A → orchestrator path. If it slips, that's schedule signal worth taking seriously, not just noting.*

---

## Sprint 3 (Weeks 5–6, 2026-10-12 to 2026-10-25) — Analytical agents
**Goal (increment):** All three specialists working; forecast beats a naive baseline or the gap is documented.

**Planned:**
- [ ] MCP servers #2 and #3 (feedback, volume)
- [ ] Forecast agent + regression model + seasonal-naive baseline comparison
- [ ] Sentiment agent + confidence scoring
- [ ] Sentiment eval reports neutral accuracy by neutral kind (via `corpus_id`; neutral is 73% administrative) and hard-case accuracy with the judge disagreement rates alongside (ADR-040)
- [ ] Orchestrator routes across all three
- [ ] Golden set (known-correct answers for `05` and the Sprint 5 evals)
- [ ] Labelled routing set: ambiguous, multi-domain, out-of-scope and technician-level intents
- [ ] Fill `docs/security-model.md` while drafting `04`
- [ ] Draft `05-test-scenarios.md` in week 2 (2026-10-19 to 10-25)

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

**Academic deliverable status:**
- `03-planning-management.md` (due 2026-10-18) — *(status)*
- `04-design-solution-architecture.md` (due 2026-10-18) — *(status)*
- Weekly status report due (maintained by Eric)

**Decisions made this sprint:**

---

## Sprint 4 (Weeks 7–8, 2026-10-26 to 2026-11-08) — Verification
**Goal (increment):** QA agent operational with all three verification strategies; measurable catch rate.

**Planned:**
- [ ] QA agent — deterministic re-check (reporting), backtest threshold (forecast), labeled-holdout scoring (sentiment)
- [ ] Bounded retry loop (max 2), escalation path on final failure
- [ ] Fault-injection harness for QA catch-rate measurement
- [ ] Price a full routing eval run (~300-700 requests, two LLM calls per request per
  ADR-046) on paid Flash-Lite using the official pricing page, and add that cost to the
  budget alongside the ~$20-30 Pro-for-QA test (ADR-029). ADR-041 already decided the runs
  use the paid, spend-capped project.
- [ ] Minimal Cloud Run deploy of the reporting slice (ADR-045): orchestrator,
  `agent_reporting` and `mcp_incidents` with the smallest Cloud SQL instance (stopped when
  idle), 2026-11-02 to 11-04, timeboxed to 3 days. Cloud Build trigger with an explicit deploy
  step; post-deploy check that the serving revision is the one just built at 100% traffic;
  Secret Manager; IAM ID tokens between services; `alembic upgrade head` and the grants suite
  against Cloud SQL. Stop rule: not verified serving by end of 11-04 → stop, record R-03 as
  realised, write it up as the first incident in `06`, leave Sprint 5 unchanged. Carry order
  if Sprint 4 overflows: the fault-injection harness moves to Sprint 5 first.
  - [ ] Agent Card cached with a TTL (currently fetched on every request).
  - [ ] Trace id in web-server access logs.
  - [ ] A readiness probe alongside `/healthz`.

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

**Academic deliverable status:**
- `05-test-scenarios.md` (due 2026-11-01) — *(status)*
- `06-production-support.md` (due 2026-11-08) — *(status)*
- Weekly status report due (maintained by Eric)

**Decisions made this sprint:**

*Note: scope-expansion decisions (broader capability within the existing three domains) are only appropriate if genuinely ahead of plan at this boundary — see the working agreement in `architecture.md` §13.*

---

## Sprint 5 (Weeks 9–10, 2026-11-09 to 2026-11-22) — Interface & evaluation
**Goal (increment):** Deployed system with a working UI; routing accuracy reported with failure analysis.

**Planned:**
- [ ] Routing eval harness + failure-case analysis (ambiguous, multi-domain, and out-of-scope intents included)
- [ ] FastAPI gateway + thin React UI
- [ ] Extend deployment to all services; complete Cloud SQL migration
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

**Academic deliverable status:**
- No numbered deliverable due.
- Weekly status report due (maintained by Eric) — the last report covers the week ending 2026-11-22

**Decisions made this sprint:**

---

## Sprint 6 (Weeks 11–12, 2026-11-23 to 2026-12-05) — Hardening & delivery
**Goal (increment):** Production-grade checklist closed out; demo rehearsed.

**Planned:**
- [ ] Observability, CI/CD completion, graceful degradation, load/latency testing
- [ ] Production-grade checklist (`architecture.md` §7) audited item by item
- [ ] Evaluation report (`docs/evaluation-report.md`), presentation, demo rehearsal (ADR-044)

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

**Academic deliverable status:**
- Final product due 2026-12-05 (end of Module 10) — *(status)*

**Decisions made this sprint:**

*Note: this sprint is protected buffer, not planned work with a buffer label. If Sprints 1–5 ran clean, use the slack for polish and rehearsal — not for starting anything new.*

---

## Cumulative Summary
*(fill in progressively — one line per sprint, for a fast look-back when writing the evaluation report and final presentation)*

| Sprint | Goal met? | Key learning | Scope change? |
|---|---|---|---|
| 1 | Yes, 2026-09-25, two days inside the sprint | Iteration with pass bars but no stop rule consumed most of the sprint; it ended by redefining the criterion (ADR-040), an option available from the start | Yes: corpus design reshaped (ADR-036 to 041); paid, spend-capped project added (~$1.40); human review cut from 200 to 30; deliverable plan rebuilt from the course calendar |
| 2 | | | |
| 3 | | | |
| 4 | | | |
| 5 | | | |
| 6 | | | |
