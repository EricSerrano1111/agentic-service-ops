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
- [x] `packages/llm` (budget 1.5 days): 429 handling lifted from `build_corpus.py`, separating per-minute (back off, retry after the stated delay) from daily quota (stop cleanly, typed error); free key default; paid only with an explicit flag, its own key and a required request cap; token metering on every call, logged as list-price equivalent; one provider; done = offline tests pass against a fake transport
  Stop rule: budget 1.5 days. Done = the offline tests below pass. If the SDK's error shapes can't distinguish per-minute from daily quota, stop and report rather than guess.
  *Done 2026-09-26 on `feat/llm-package`, inside the budget; stop rule not hit: the SDK's structured `quotaId` separates daily from per-minute. 37 offline tests pass (ADR-048); live free-tier test awaits a local run.*
- [x] Orchestrator classification (reporting, out-of-scope, other domain not yet available, multi-domain per ADR-032), with 20–30 seeded labelled intents as test fixtures
  Stop rule (with the parsing item below): budget 2 days. At most two revisions of each prompt against the seed set; accuracy tuning belongs to the Sprint 3 routing eval. If the checkpoint e2e test isn't passing by 2026-10-07, stop and report.
  *Done 2026-09-26 on `feat/routing-and-parsing`: one routing call on `gemini-3.7-flash` (ADR-049) into `RouteDecision`, prompt `route_v1`, all five routes and error mappings unit-tested; 28-question seed set in `evals/routing/`, live run pending.*
  *2026-09-26: the first checkpoint e2e run failed because `gemini-3.7-flash` rejects thinking level `minimal` (400 INVALID_ARGUMENT), which had been one global setting; thinking level is now per role (orchestrator `low`), rejections are logged with Google's message and map to 500 `internal_error`, and per-role live smoke tests cover the production config. Checkpoint e2e re-run: 6/6 passed (one test on a second run after free-tier 503s, R-15).*
- [x] Reporting agent question parsing per ADR-046; two or three reporting tools covering the FR-06 examples; template-rendered answers; e2e test against independent SQL
  *Parsing done 2026-09-26 on `feat/routing-and-parsing` (ADR-046, ADR-050: as-of date, dateless default), template answers, checkpoint e2e written (live run pending). Left open: the second and third reporting tools for the FR-06 examples; the one tool is still incidents by date range.*
  Stop rule (FR-06 metric tools, 2026-09-26): budget 2 days. If a metric's definition in data dictionary §6 is ambiguous for a case the tools hit (for example, which date filters which side of a ratio), stop and ask; don't choose. §6 exists because an unrecorded choice becomes an agent-vs-QA disagreement later.
  *Done 2026-09-26 on `feat/reporting-metrics`: `get_incident_rate`, `get_sla_compliance`, `get_first_time_fix_rate` (§6, Decimal-string rates, group_by account/region/service_type/technician, top 25), parsing prompt `parse_v2` with `metric` and `group_by`, per-metric templates, integration tests against `app_qa` SQL. The stop rule fired twice, both decided by Eric: region is now stored on `locations` (ADR-051), and a cancelled child request no longer counts against first-time fix (full window 0.9798 excluded against 0.9777 counted). Data dictionary §6 gained the date-filter rules and the cancelled-child sentence (a direct edit; §6 had no date rules). Repeat-visit drivers remain Sprint 3.*
  *2026-09-26, before merge: grouped results sort worst first (incident rate highest first; SLA compliance and first-time fix lowest first), so the top-25 cap keeps the worst groups. The answer text ranks only groups with at least `REPORTING_MIN_GROUP_DENOMINATOR` cases (default 20) and says how many were left out; the data part keeps every group. §6 now says incident rate is per 100 and can exceed 1.*
- [x] Portable Alembic ruff hook (Alembic `module` runner if the installed version supports it); verified locally and in CI
  *Done 2026-09-26: `ruff.type = module` (`<python> -m ruff format`), supported by the installed Alembic 1.20; no path, so it works on the Windows venv, Linux CI and cloud sessions. Verified by generating the ADR-051 migration and a throwaway revision (both reformatted; the throwaway deleted); CI runs `alembic check`.*
- [x] Draft `03-planning-management.md` 2026-10-08 to 10-11, after checking its rubric
  *2026-09-30: drafted early by Eric (with `04`), not submitted. Whether the rubric was checked: Eric to confirm.*
  *2026-09-30: drafted, rubric checked; not submitted.*

R-06 checkpoint: skeleton hop working by 2026-10-02, or hold the scope conversation that day;
LLM-classified question answered end to end in docker-compose by 2026-10-07. Log hours per
layer (MCP, A2A, llm, orchestrator). Work a test can verify runs in Claude Code cloud sessions
and returns as a PR; anything needing a real API key, `gcloud`, or a judgment call runs
locally. The paid key never goes into a cloud environment.

**Shipped:**

**Goal:** met. Checkpoint 1 (the skeleton hop, no LLM) passed 2026-09-25 against a
2026-10-02 deadline. Checkpoint 2 (an LLM-routed, LLM-parsed question answered end to end
in docker-compose) passed 2026-09-26 against a 2026-10-07 deadline. Engineering finished
2026-09-30 (PR #7 merged). The work ran 2026-09-25 to 09-30, so PRs #1 to #5 merged before
the sprint's formal start on 2026-09-28.

- PR #1 (2026-09-25), docs sweep for Sprint 2 planning: no final paper, the Sprint 4 slice deploy, specialists parse their own questions (ADR-044, ADR-045, ADR-046).
- PR #2 (2026-09-25), walking skeleton: orchestrator → A2A → reporting agent → MCP → Postgres in docker-compose, no LLM; SDKs pinned (ADR-047).
- PR #3 (2026-09-26), `packages/llm`: one Gemini client, free by default, per-minute vs daily 429, list-price metering; 429 fixtures rebuilt from real bodies (ADR-048).
- PR #4 (2026-09-26), routing and parsing: `route_v1`, `parse_v1`, as-of date, checkpoint 2 e2e; orchestrator on Flash-Lite after the seed-set comparison (ADR-049, ADR-050).
- PR #5 (2026-09-26), FR-06 metrics: incident rate, SLA compliance, first-time fix with group-by; `parse_v2`; site region stored (ADR-051); limitations log L-01 to L-13.
- PR #6 (2026-09-30), routing_v1 and `route_v2`: 18 owner-written routing questions, both models run; thinking level per model; forecast covers forward-looking questions (ADR-052, ADR-053; L-14 to L-17).
- PR #7 (2026-09-30), `route_v3`: the router is given the as-of date; routing evals run three times (ADR-054; L-18).

**Planned vs done:** every engineering item is done: the walking skeleton, `packages/llm`,
orchestrator classification, reporting parsing and the FR-06 metric tools, and the portable
Alembic hook. The FR-06 item is done except for the deferrals below. The `03` draft is done early,
rubric checked. Not done: hours per layer for R-06 were not logged. Done beyond the plan, from Sprint 3: the labelled routing set (routing_v1) and
two routing prompt revisions.

**Carried over:**
Deferred to Sprint 3:
- Repeat-visit drivers.
- Incident counts by breakdown (L-06: incident counts can't be broken down yet).
- The single-technician filter decision (routing_v1 r15, r17).

**Blockers encountered:**
None blocked the goal. Two provider-side problems each cost a rerun: `gemini-3.7-flash`
rejected thinking level `minimal` (400) on the first checkpoint e2e run, and free-tier
`gemini-3.7-flash` returned "high demand" 503s (R-15). Both are recorded in the Planned notes
above.

**Retro:**
*Written 2026-09-30, before the sprint's formal end (2026-10-11). Anything merged later gets a dated addendum.*

- What went well:
  - Walking skeleton first. The A2A hop was proven with no LLM in the loop, before anything
    depended on it. Both R-06 checkpoints were met ahead of schedule, and the protocol risk
    was settled before the LLM work began.
  - The stop rules worked. They fired twice (what "region" means; whether cancelled
    follow-ups count against first-time fix), and both times produced a recorded definition
    instead of a silent choice. Budgeted items stayed inside their budgets. This was Sprint
    1's change #2, applied.
  - Sourcing discipline held. Price-table entries carry a source and date. Error fixtures are
    labelled observed or assembled. The limitations log captured issues as they were found.
    This was Sprint 1's change #1, applied.
  - Decisions were made on evidence. The orchestrator moved off 3.7 Flash after a
    side-by-side comparison. Total paid spend for the sprint was a few cents.

- What didn't:
  - Tests built from the author's assumptions passed while the code was wrong.
    - The hand-assembled 429 fixtures hid the bug that misread real quota errors as billing
      errors; only a captured real error body exposed it.
    - The first live test used a different model and configuration from production, so it
      missed that 3.7 Flash rejects the thinking level in use.
    - Thinking level had to be fixed twice: from global to per role, then to per model.
  - Instructions asserted repo state without checking it. Assistant-written prompts:
    - edited a dated register entry (charter removal);
    - set the wrong status on R-15;
    - assumed 04 and 05 had content in the repo (they're placeholders);
    - targeted a branch that had already been merged.

    Each cost a correction round.
  - Environment drift. Two reports came from a machine without Docker, `uv` or `gh`. Each
    verified only part of the work: the e2e didn't run, and a PYTHONPATH workaround stood in
    for the CI install.
  - Evaluation evidence is thin. routing_v1 was used to revise the routing prompt, so it's no
    longer a blind test. Model output varies between runs even at temperature 0. Every
    one-question gap so far is within noise.

- What changes next sprint:
  1. Every verification artifact says where it came from: observed from the real system, or
     assembled. Live tests run the production configuration. Anything still assembled is
     listed in the limitations log.
  2. Every Claude Code prompt starts with a state check (branch, environment, and the files
     and content it assumes), and stops if reality differs.
  3. Kept from Sprint 1: every design loop starts with a written stop rule and budget.
     Routing evaluations report three runs.

**Academic deliverable status:**
- `02-requirements-analysis.md` (due 2026-10-04): complete early, in Sprint 1.
- `03-planning-management.md` and `04-design-solution-architecture.md` (due 2026-10-18):
  drafted, not submitted.
- Weekly status report: drafted, not submitted (maintained by Eric).
- Final copies are committed to `docs/academic/` after submission; the repo copies are
  placeholders until then.

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
- ADR-047 — MCP and A2A SDKs pinned (`mcp==2.2.0`, `a2a-sdk==1.1.5`); A2A used as a minimal subset; everything else pinned by `uv.lock`.
- ADR-048 — LLM client policy: free by default, paid opt-in with caps, per-minute vs daily 429s, list-price metering, validated structured output, one provider.
- ADR-049 — per-role runtime models; the orchestrator stays on Flash-Lite on measured evidence (seed set 28/28 against 3.7 Flash 27/28).
- ADR-050 — reporting answers resolve relative dates against a fixed as-of date (the dataset end), stated in every answer.
- ADR-051 — `locations.region`: the customer site's region, stored (FR-06 stop rule, decided by Eric).
- ADR-052 — thinking level follows the model called, not only the role (supersedes ADR-049 in part).
- ADR-053 — routing prompt `route_v2`: forecast covers forward-looking questions, not only request volume.
- ADR-054 — routing prompt `route_v3`: the router is given the as-of date; routing evals report three runs.

*Note: this is the highest-risk sprint in the plan — it proves the entire MCP → A2A → orchestrator path. If it slips, that's schedule signal worth taking seriously, not just noting.*

---

## Sprint 3 (Weeks 5–6, 2026-10-12 to 2026-10-25) — Analytical agents
**Goal (increment):** All three specialists working; forecast beats a naive baseline or the gap is documented.
*2026-10-02: met, pulled forward. Reporting, sentiment and forecast each answer end to
end through the orchestrator, and the forecast beats seasonal naive on the headline
holdout (total MAPE 8.81% against 14.80%; ADR-069).*
*2026-10-04: Sprint 3 closed, 8 days before its formal start (2026-10-12). Everything
shipped below was merged 2026-10-01 to 10-04. Open: FR-03 (carried to Sprint 5) and the
`05` draft (carried to Sprint 4).*
*2026-10-05: Close-out provisional. Sprint 3 is final once the `05` test-scenarios draft is
complete (owner drafting week of 2026-10-05; due 2026-11-01). Sprint 4 planning proceeds in
parallel; Sprint 4 development does not start until Sprint 3 is final.*
*2026-10-05: Sprint 3 final. The `05` draft is complete; the close-out is no longer provisional.*

**Planned:**
- [x] MCP servers #2 and #3 (feedback, volume)
  *2026-10-01: feedback done (ADR-067). `mcp_feedback` answers from stored predictions
  (`sentiment_predictions`, migration `3d7e1a9c5b20`) with `get_sentiment_summary` and
  `get_feedback_examples`, scoring unscored comments on demand (cap 250, batch 8); all
  7,521 comments backfilled. Stored test-split predictions match 3b's on 1,128/1,128.
  Volume still to do.*
  *2026-10-02: volume done (ADR-072). `mcp_volume` serves `volume_v2` through
  `get_volume_forecast` (numbers only for served slice-bands, ADR-071) and
  `get_order_volume_history`, as `app_forecast`; numpy only, image 410 MB.*
- [x] Forecast agent + regression model + seasonal-naive baseline comparison
  *2026-10-02: forecast agent built (ADR-072): one parse call, period rules in code,
  template answers with the held-out error per band, unserved bands named with their
  error, declines for SLA, incidents, sentiment, breakdowns and past periods. Parse set
  parse_v1: 14/14 exact match in each of 3 runs, no flips. End to end: next month,
  install for 10 weeks (weeks 1-4 refused, 5-10 served), December (year-end caveat),
  the next year (served to 26 weeks), and the SLA decline, 1.5-2.5 s each; reporting
  and sentiment unchanged. 56 free-tier calls. Results: `evals/results/forecast_agent/2026-10-02/`.*
  - [x] Rolling-origin folds over the Q4 2024 and Q4 2025 peaks, reported separately alongside the 26-week holdout; backtest threshold set from them (ADR-057, ADR-055).
  *2026-10-02: pulled forward. Regression model and seasonal-naive comparison done; the
  forecast agent is still to build (5b), so the parent item stays open. Protocol
  pre-registered (ADR-069). `volume_v1` failed ADR-069's gate on the total in bands 1-4
  and 14-26 (L-41); the gate was corrected and `volume_v2` added a year-end indicator
  after the fold results and before the holdout, disclosed as post-hoc (ADR-070, L-42).
  Headline holdout (2026-03-02 to 08-30), total MAPE: v1 9.26%, v2 8.81%, seasonal naive
  14.80%: the model beats the baseline under ADR-069's definition. Fold B under the
  corrected gate: the total passes every band; inspection is ineligible, and 6 other
  service-type bands fail (L-44). `volume_v2` exported with its manifest; reload check
  exact. Results: `evals/results/forecast/`.*
- [x] Sentiment agent + confidence scoring
  *2026-10-01: `agent_sentiment` built (ADR-068): one parse call, template answers from
  `mcp_feedback`, the two-proportion trend rule, declines for account, technician and
  service type, at most 3 quoted comments, none sent to an LLM. The orchestrator routes
  sentiment to it; forecast keeps "not available yet". Parse set parse_v1 (14
  questions): 13/14 exact match in each of 3 runs, no flips; the one miss is p14 "in
  August" (L-38). FR-07's example, "Is sentiment trending down in the West?", is now
  answered end to end: 241 comments, March to August 2026 (range assumed), negative
  21.9% in August against 14.4% before, p = 0.27, no clear change; 2.6 s on the first
  question after a cold stack start, 1.8 s warm. 54 free-tier calls. Results: `evals/results/sentiment_agent/2026-10-01/`.*
  *2026-10-01: model and threshold done, agent still to build. Artifact `bert_v1`
  (`lr2e-5_v1` epoch 4, ADR-066) exported with a hashed manifest; reload check matched the
  checkpoint on 1,129/1,129 validation comments. Temperature T = 1.032 and review threshold
  τ = 0.841 (the 99% target set it, not the 20% cap), both fitted on validation. On test:
  ECE 0.0106 raw, 0.0094 calibrated; 1.4% flagged; un-flagged accuracy 98.65%, flagged 50%;
  8 of 23 errors flagged (L-32). Results: `evals/results/sentiment/2026-10-01_bert_v1/`.*
  - [x] Measure BERT CPU inference latency on a realistic feedback batch against the 120 s ceiling.
    *2026-10-01: proxy measured with the untrained model (pinned `bert-base-uncased`,
    random head) in a CPU-limited local container (ADR-065, L-28). Gate slices pass at
    1 CPU / 2 GiB and 2 CPU / 4 GiB: largest account-quarter (107) 10.0 s / 6.1 s, largest
    region-quarter (225) 20.7 s / 12.3 s (max of 3); cold start 13.4 s / 13.1 s (budget
    20 s). Not gates and over 30 s: largest quarter (736) 65 s / 40 s, last 12 months
    (2,666) 239 s / 148 s, full window (7,521) 669 s / 410 s; the last two ran 1 repeat
    (L-29). Peak memory under 0.5 GiB. Stays unticked until measured on the real
    container. Results: `evals/results/sentiment/2026-10-01_latency_proxy/`.*
    *2026-10-01: measured on the real `mcp_feedback` container at 1 CPU / 2 GiB (local
    Docker; L-28 still applies, no Cloud Run measurement). Cold start to ready (hash
    check, no model) 14.9 s, and 29.4 s on the first start after a Windows restart
    (L-36). Largest region-quarter (225) cold, model load and scoring included, 45.0 s;
    stored 0.06 s. Largest quarter (736) before backfill: 300 scored in 43.1 s,
    partial. Warm inference on 300 comments: batch 8 median 31.8 s (9.42/s), batch 16
    35.5 s (8.46/s), below the proxy's 10.74/s (L-35), so the cap is 250 at batch 8
    (ADR-067). Backfill of 6,996 in 856.6 s. With predictions stored, answers take
    0.05–1.0 s. Results: `evals/results/sentiment/2026-10-01_mcp_feedback_live/`.*
  - [x] TF-IDF plus logistic regression baseline, required (ADR-059).
    *2026-10-01: pulled forward. Split v1 committed first (ADR-064). Selected on validation:
    word 1-2-grams, C=10 (validation macro-F1 0.9333; at the grid edge, L-26). Test
    macro-F1 0.9431, scored once and in the ledger. Interpretation rule: neither condition
    fired (TF-IDF below 0.95; length-only diagnostic 0.3331, below 0.60), so BERT is judged
    on overall macro-F1 as well as hard cases and mixed.*
- [x] Sentiment eval reports neutral accuracy by neutral kind (via `corpus_id`; neutral is 73% administrative) and hard-case accuracy with the judge disagreement rates alongside (ADR-040)
  *2026-10-01: `evals/sentiment/score.py` (reads as `app_eval`) reports neutral accuracy by
  kind and hard-case accuracy by type with n and the judge disagreement rate on the same
  rows; run on the baselines. BERT still to run.*
  *2026-10-01: BERT run. Test macro-F1: BERT (`bert_v1`) 0.9713, TF-IDF 0.9431. Paired
  bootstrap difference +0.028, 95% interval [0.012, 0.046]; McNemar full set 36 vs 10
  (p = 0.0002): BERT better overall under ADR-065's rule. Sarcastic (1 vs 2), implicit
  (9 vs 4) and mixed (7 vs 2) are not distinguishable. Ledger lines 4 and 5; caveats beside
  the result: L-26 (TF-IDF at grid edge), L-30 (BERT at epoch cap), L-31.*
- [x] Orchestrator routes across all three
  *2026-10-02: done in 5b (not ticked then). Reporting, sentiment and forecast questions
  each route to their agent over A2A (ADR-068, ADR-072); the "not available yet" path is
  gone, and the out-of-scope decline names all three domains.*
- [x] Golden set (known-correct answers for `05` and the Sprint 5 evals)
  *2026-10-02: golden set v1 (ADR-074): 36 items in `evals/golden/`, 10 owner-written
  (verbatim) and 26 drafted, 4 stretch. Expected figures for 22 items from independent
  oracles (fresh SQL as `app_eval`, scipy, statsmodels; forecast via `forecast_runtime`),
  hashed in a manifest. Built without calling the system; blind until the Sprint 5
  evaluation. Three oracle results hand-checked, one per agent.*
- [ ] FR-03: ambiguous questions are not force-routed (ADR-075)
  *2026-10-03: added after plan close, found during the `04` update. `route_v3`
  best-fit routed unclear questions, against FR-03. Built: the `ambiguous` route with
  candidates, the clarification message, `AskResponse.reason`, relabelled `seed_v2` and
  `routing_v2`, and `golden_v2`. Evaluated against a pre-registered gate: `route_v4`
  failed (a) on r05; revision `route_v5` failed (b), 41 vs a floor of 42 in one run.
  The call budget (343 of 350) ruled out a second revision, so `route_v3` stays the
  default and FR-03 stays open (L-58). Not ticked.*
  *2026-10-04: corrected gate (ADR-076: 3 `route_v3` runs, confirmation on the fresh
  owner-written set `fr03_fresh_v1`). `route_v5` passed (a), (b1) and (b2) but failed
  (c): 3 of 5 fresh ambiguous questions recognised (f03 and f05 missed in all three
  runs). `route_v3` stays the default; FR-03 stays open, with no further attempts
  before Sprint 5. 188 calls. Not ticked.*
- [x] Labelled routing set: ambiguous, multi-domain, out-of-scope and technician-level intents
  *2026-09-30: seed_v1 (clear, ambiguous, out-of-scope, multi-domain) and routing_v1
  (ambiguous, near-miss out-of-scope, technician) together cover all categories. On
  `route_v1`, Flash-Lite 17/18 and 3.7 Flash 16/18 on routing_v1, so ADR-049 stands
  (L-14). `route_v2` is the default (ADR-053), which makes routing_v1 no longer blind (L-16).*
  *2026-09-30: `route_v3` (the as-of date as today) is the default (ADR-054). Three runs
  each on Flash-Lite: seed_v1 27-28/28, routing_v1 16-17/18; flips s16, r02 (L-18).*
  - Includes harder ambiguous items and near-miss out-of-scope items, written by Eric in dispatch phrasing; the seed set was too easy to separate the models (ADR-049).
  - Re-run both `gemini-3.5-flash-lite` and `gemini-3.7-flash` on it (`evals/routing/run_seed.py --model`); a clear Flash advantage reopens ADR-049 in a new ADR.
- [x] Decide whether to add a single-technician filter (routing_v1 r15, r17 need it).
  *2026-10-02: added (ADR-073). `find_technician` (at most 5 matches, whole-word, no
  patterns) and a `technician_id` filter on every reporting tool. One match gives the
  filtered figure "based on n" cases, flagged under 20; none or several end the turn with
  no figures (orchestrator outcome `needs_clarification`). End to end, r15 answers "No
  technician matches Dave." and "Priya" lists both Priyas.*
- [x] Repeat-visit drivers (deferred from Sprint 2).
  *2026-10-02: `get_repeat_visit_drivers(start, end, by)` (ADR-073): repeat rate by
  incident type, service type, region, account or technician; Fisher's exact test with
  Bonferroni, 20-job minimum, worst first. The investigation found every repeat runs
  through a repeat-visit-required incident and the generator ties repeats only to SLA misses
  and incident count, so most answers say no group stands out (L-52 records the 1-in-20
  false standout). parse_v3 k=3: 15/16 x3 after the L-51 fix.*
- [x] `ml/` structure (`ml/sentiment/`, `ml/forecast/`) and the training-role decision (ADR-062).
  *2026-10-01: training-role decision made: `app_train` reads `sentiment_labels` plus exactly
  the columns the runtime models read, no `rating` and no `generation_parameters` (ADR-063).
  The folder structure is still to do.*
  *2026-10-01: `ml/sentiment/` created (split, data access, baselines; ADR-064).
  `ml/forecast/` still to do.*
  *2026-10-02: `ml/forecast/` created (data, model, baseline, metrics, evaluate, ledger,
  export; ADR-069, ADR-070). Both halves done.*
- [x] Evaluation/training read role (with ADR-062's training-role decision); then revoke `sentiment_labels` and `generation_parameters` from `app_qa`. **Required before the QA agent is built in Sprint 4**, so the runtime QA role never ships holding gold labels (ADR-055).
  *2026-10-01: pulled forward from Sprint 3; `app_eval` and `app_train` created, `app_qa`
  revoked (ADR-063). `validate.py` now reads as `app_eval`.*
- [x] Incident counts by breakdown (deferred from Sprint 2; L-06).
  *2026-10-02: `get_incidents_by_date_range` gains `group_by` (account, region, service
  type, technician with an "unattributed" group, incident type, severity), highest first,
  cap 25 (ADR-073; data dictionary §6). Figures match `app_eval` SQL in the integration
  suite. L-06 resolved.*
- [x] Fill `docs/security-model.md` while drafting `04`
  *2026-09-30: seeded from data-dictionary §7: the four access guarantees and the threat-model paragraph. MCP/A2A controls, prompt injection, secrets and logging still to write.*
  *2026-10-04: completed at the Sprint 3 close: MCP controls, A2A and service-to-service, prompt injection, secrets and logging, each control marked built (with its test or file) or planned (with its sprint). The code review found gaps that are recorded in the file rather than fixed: no authentication between services today and the orchestrator published on all host interfaces, a question containing `{{...}}` returning HTTP 500, and the logs carrying the router's `reason`, typed technician names and echoed rejected arguments.*
- [x] Draft `05-test-scenarios.md` in week 2 (2026-10-19 to 10-25)
  *2026-10-04: carried to Sprint 4. Sprint 3 closed early, so this is not late: `05` is due
  2026-11-01.*
  *2026-10-05: stays in Sprint 3 and is not carried to Sprint 4; Sprint 3 is provisional until
  this draft is complete.*
  *2026-10-05: draft complete (owner-authored, committed unchanged). Its claims check against
  the built system was reported to the owner, who decides on edits before submission.*

**Shipped:**

**Goal:** met 2026-10-02 (pulled forward); sprint closed 2026-10-04. The work ran 2026-10-01
to 10-04, so PRs #11 to #23 all merged before the sprint's formal start on 2026-10-12.
Dates are local (US Central).

Offline roles:
- PR #11 (2026-10-01), offline read roles `app_eval` and `app_train`; gold labels leave `app_qa` (ADR-063).

Sentiment:
- PR #12 (2026-10-01), split v1 committed before training; TF-IDF baseline, diagnostic floors and the scorer (ADR-064; L-26).
- PR #13 (2026-10-01), BERT protocol pre-registered; CPU torch, pinned model, latency proxy (ADR-065; L-28, L-29).
- PR #14 (2026-10-01), `bert_v1`: temperature scaling and review threshold fitted on validation; test macro-F1 0.9713 against 0.9431 for TF-IDF (ADR-066; L-30 to L-32).
- PR #15 (2026-10-01), stored predictions: `sentiment_predictions`, `mcp_feedback` (`get_sentiment_summary`, `get_feedback_examples`), on-demand scoring capped at 250, all 7,521 comments backfilled (ADR-067; L-35, L-36).
- PR #16 (2026-10-01), sentiment agent: one parse call, template answers, the two-proportion trend rule; parse set 13/14 in each of 3 runs (ADR-068; L-38).

Forecast:
- PR #17 (2026-10-02), forecast model: protocol pre-registered; `volume_v1` failed the first gate on the total in two bands; the gate was corrected and a year-end indicator added (`volume_v2`) after the fold results and before the holdout; holdout total MAPE 8.81% against 14.80% for seasonal naive; serving requires passing on fold B and the holdout (ADR-069, ADR-070, ADR-071; L-41, L-42, L-44).
- PR #18 (2026-10-02), `mcp_volume` and the forecast agent: numbers only for served slice-bands, track record shown, future periods only; prediction code moved to `packages/forecast_runtime`; parse set 14/14 in each of 3 runs (ADR-072; L-48 to L-50).

Reporting additions:
- PR #19 (2026-10-02), incident counts by six breakdowns, `find_technician` and the single-technician filter, repeat-visit drivers with a significance rule, `parse_v3`; parse set 15/16 in each of 3 runs after the key-order fix (ADR-073; L-06 resolved; L-51 to L-53).

Golden set:
- PR #20 (2026-10-02), golden set v1: 36 questions (10 owner-written), independent oracles, hashed manifest; blind until Sprint 5 (ADR-074; L-54 to L-56).

FR-03 attempt (failed; `route_v3` remains the default):
- PR #22 (2026-10-03), the `ambiguous` route (`route_v4`, `route_v5`), `AskResponse.reason`, relabelled routing sets, `golden_v2`; failed its pre-registered gate (ADR-075; L-57, L-58).
- PR #23 (2026-10-04), corrected gate (3 `route_v3` runs) confirmed on a fresh owner-written set; passed (a), (b1), (b2), failed (c) with 3 of 5 ambiguous questions recognised; FR-03 stays open (ADR-076; L-58).

Academic:
- PR #21 (2026-10-04), `04` design document updated to the Sprint 3 state, with the open FR-03 gap disclosed (no ADR).

Closing PR (2026-10-04): Sprint 3 closed in `sprint-log.md`; `docs/security-model.md` completed, with each control marked built or planned; `docs/requirements-traceability.md` added (27 requirements: 12 met, 5 partly met, 6 not yet built, 4 open; unrecorded gaps listed at the top).

**Carried over:**
- FR-03 (ambiguous questions not force-routed) to Sprint 5: open, with a Sprint 5 item (L-58, ADR-075, ADR-076). Any reattempt needs a new owner-written fresh set, because `fr03_fresh_v1` has been used.
- The `05` draft to Sprint 4. Sprint 3 closed early, so it is not late: `05` is due 2026-11-01. Its scenarios include the FR-03 known-failing scenario.
*2026-10-05: the `05` draft is no longer carried to Sprint 4; it stays in Sprint 3, which is provisional until the draft is complete. FR-03, carried to Sprint 5, is unchanged.*
*2026-10-05: the `05` draft is complete and nothing from Sprint 3 is carried to Sprint 4. FR-03, carried to Sprint 5, is unchanged.*

**Blockers encountered:**
Factual; each is recorded elsewhere in the logs.
- The first forecast gate (ADR-069, pre-registered) failed `volume_v1` on the total in two bands. The flaw was in the gate (a 4-week band cannot separate two forecasters at about 10% weekly noise); it was corrected after the fold results and before the holdout, and the original verdicts are kept (ADR-070; L-41, L-42).
- `parse_v3` lost every date to a key-order clash between the request model and the prompt template. The first k=3 parse run scored 0, 1 and 0 of 16, spent 48 calls, and its results file was lost to a console-encoding crash in the runner; found with a two-item diagnostic (L-51).
- The response contract had no `reason` field, so the golden set's G01 and G16 expected technician codes the API never returned. Fixed in ADR-075 and `golden_v2`.
- Two FR-03 gates failed: ADR-075's (`route_v4` flagged a clear question as ambiguous; `route_v5` dropped below the accuracy floor in one run) and ADR-076's corrected gate (3 of 5 fresh ambiguous questions recognised). ADR-075's gate also broke ADR-054's rule that routing evals report 3 runs.
- One Claude Code session limit was hit mid-evaluation (2026-10-03); no data was lost.

**Retro:**
*Written 2026-10-04, at close.*

- What went well:
  - *(Owner)* All else was mostly fine.
  - *(Assistant-observed)* Pre-registered gates on held-out data caught problems that
    development data hid. The forecast gate and the year-end miss (the 2025 Christmas week,
    52% over) surfaced from the fold results before the holdout was scored. `route_v5` passed
    on the v2 sets it had been revised against, then recognised only 3 of 5 on questions it
    had never seen: it had learned the examples, not the concept.
  - *(Assistant-observed, 2026-10-05)* The close-out's security-model completion and
    traceability check found defects before any deploy: an orchestrator port open on all
    interfaces with no authentication; user text treated as template syntax (a `{{...}}`
    question returned HTTP 500); typed names and rejected values in the logs; and an
    unrecorded NFR-4 gap (circuit breaking). All of them were fixed or recorded (PR #25,
    ADR-077, L-59), and render equality (1,128 renders identical before and after) showed the
    routing results still stand.

- What didn't:
  1. *(Owner)* "The 04 design document drifted from actual development as problems and needed changes arose."
  2. *(Assistant-observed)* FR-03 diverged from a committed MVP requirement in Sprint 2.
     Nothing traced requirements to code, so it surfaced only when the `04` update described
     the system accurately.
  3. *(Assistant-observed)* ADR-075's gate broke ADR-054's k=3 rule, and the golden set's
     expected outputs were written without checking the response contract.
  4. *(Assistant-observed, 2026-10-05)* None of those defects had a test. The suites covered
     intended behaviour but not hostile or malformed input at the service edges.
  - **Final review (owner, 2026-10-05):**
    1. *(Owner)* Drift from creating an academic deliverable before actual development. The
       `04` design was written ahead of the build and strayed from it as problems and needed
       changes arose.
    2. *(Owner)* Repeated memory exhaustion in the local environment (WSL/Docker), which forced
       freeing memory and restarting the machine several times.
       - *(Assistant-observed, from the logs)* The logs record one related event: the first
         container start after a Windows restart took 29.4 s, against 14.9 s otherwise, with a
         cold file cache (L-36; `evals/results/sentiment/2026-10-01_mcp_feedback_live/`). The
         host is an Intel i7-6700HQ (4 cores / 8 threads) running Docker Desktop on WSL2. The
         latency proxy saw no out-of-memory kill inside its containers, peak under 0.5 GiB
         (`evals/results/sentiment/2026-10-01_latency_proxy/summary.md`); that is container
         memory, not the host's.
       - *(Assistant-observed)* The logs record no count or dates of the exhaustion incidents
         or restarts, and none is stated here.

- What changes next sprint:
  1. The requirements traceability matrix (`docs/requirements-traceability.md`) is re-checked
     at every sprint close.
  2. Before any academic deliverable is submitted, check its claims against the built system
     and record any divergence. After submission, divergences are recorded in the sprint log
     and carried to the evaluation report, never silently.
  3. Every gate cites the evaluation rules it must satisfy, and a reviewer checks it against
     them before any run.
  4. *(Assistant-observed, 2026-10-05)* Every new service edge in Sprint 4 (the QA agent, the
     gateway, deployed ingress) gets malformed-input and exposure tests written with it, not
     afterwards.
  5. *(Owner-derived, 2026-10-05)* Academic deliverables describe the built system or say
     plainly what is planned. The claims check before submission (item 2 above) is the control;
     it is not repeated here.
  6. *(Owner-derived, 2026-10-05)* A short local-environment recovery note (in `README.md`,
     "Local environment recovery"), and a memory headroom check before long runs or full-stack
     rebuilds, because Sprint 4 adds the QA agent and the deploy tooling to the local
     footprint. Tracked as R-17.

Retro final.

**Academic deliverable status:**
- `03-planning-management.md` (due 2026-10-18) — submitted before the due date (owner).
- `04-design-solution-architecture.md` (due 2026-10-18) — submitted before the due date (owner).
  *2026-09-30: drafted with Appendix A (security and data-access summary); rubric checked; not submitted.*
  *2026-10-04: the copy in this repo is the Markdown before the Word port. The submitted
  Word version may differ in figures and formatting.*
  *2026-10-04, post-submission divergences between a submitted document and the built system
  (carry to the evaluation report):*
  - *`02`, FR-10 says a model that fails the threshold on held-out weeks is not deployed. The
    built system deploys `volume_v2` and withholds each failing slice-band, with its error
    shown (ADR-071).*
  *2026-10-05, further post-submission divergences from ADR-078 to ADR-080 (carry to the
  evaluation report):*
  - *`04`, TA-16 quotes the stop date 2026-11-04. ADR-078 moves the deploy window to
    2026-10-12 to 10-14, with the stop rule at the end of 10-14.*
  - *`04`, "each component deploys as its own Cloud Run service". ADR-079 runs each MCP server
    as a sidecar of its agent, so the deploy is two services at first and six in the target
    topology, not one per component.*
  - *`04`, the interface "on Node.js LTS". ADR-080 serves a static export from the gateway, so
    no Node.js runs in production (Node is a build tool only).*
  - *`04`, Table 3 says the orchestrator routes on Agent Card skills. In fact `route_v3`
    hard-codes the domain descriptions, and the card supplies only the agent's URL.*
  *2026-10-08, further post-submission divergence from ADR-082 (carry to the evaluation
  report):*
  - *`03` quotes the original sprint calendar (sprint dates, the critical path, the schedule
    rows and the stop rules' dates). ADR-082 re-baselines it: Sprint 4 is 2026-10-06 to 10-25,
    Sprint 5 10-26 to 11-08, Sprint 6 11-09 to 11-22, buffer 11-23 to 12-05. The final date
    is unchanged.*
  - *`03`, the critical path, the task-16 schedule row and the stop rules quote the deploy
    window 11-02 to 11-04. ADR-078 moves it. `03` is Eric's to edit; nothing was changed.*
- `05-test-scenarios.md` (due 2026-11-01) — drafted 2026-10-05, submission pending (owner).
- Weekly status report due (maintained by Eric)

**Decisions made this sprint:**
- ADR-063 — Offline read roles: `app_eval` for validation and evaluation, `app_train` for training; gold labels leave `app_qa` (2026-10-01, pulled forward)
- ADR-064 — Sentiment split and evaluation protocol (2026-10-01, pulled forward)
- ADR-065 — BERT training, comparison and latency protocol, pre-registered (2026-10-01, pulled forward)
- ADR-066 — Sentiment model selection, calibration and review threshold, pre-registered (2026-10-01, pulled forward)
- ADR-067 — Sentiment predictions stored and scored on arrival; the sentiment server gains region access (2026-10-01, pulled forward)
- ADR-068 — Sentiment agent: one parse call, template answers, a significance-based trend rule, explicit declines (2026-10-01, pulled forward)
- ADR-069 — Forecast protocol, pre-registered: folds, holdout, intervals and release gate (2026-10-02, pulled forward)
- ADR-070 — Forecast gate correction and `volume_v2` with a year-end indicator, decided after fold results and before the holdout (2026-10-02, pulled forward)
- ADR-071 — Forecast serving requires passing on both fold B and the holdout (2026-10-02, pulled forward)
- ADR-072 — Forecast agent and `mcp_volume`: served-only numbers, track record shown, future periods only (2026-10-02, pulled forward)
- ADR-073 — Reporting additions: incident counts by breakdown, a single-technician filter, repeat-visit drivers, `parse_v3` (2026-10-02, pulled forward)
- ADR-074 — Golden set v1: blind, independently computed expected answers (2026-10-02, pulled forward)
- ADR-075 — Ambiguous questions are not force-routed: the router returns `ambiguous`, and the orchestrator asks the user to rephrase (FR-03); accepted, not in effect, gate failed (2026-10-03, pulled forward)
- ADR-076 — Corrected FR-03 routing gate (supersedes ADR-075's gate only); also failed (2026-10-04, pulled forward)

---

## Sprint 4 (2026-10-06 to 2026-10-25, three weeks; re-baselined, ADR-082; closed 2026-10-10, day 5, ADR-093) — Verification
**Goal (increment):** QA agent operational with all three verification strategies; measurable catch rate.
*2026-10-04: Sprint 4 pulled forward; planning to follow.*
*2026-10-05, planning decisions taken; the ADRs follow and are not written yet:*
- *ADR-078 (to write): the reporting-slice deploy is pulled forward from its 2026-11-02 to
  11-04 window, superseding ADR-045's dates only. The new dates are fixed in the ADR. The
  3-day timebox and the stop rule stay, and the stop date moves with the window. Cost note:
  about $2 extra if the instance is stopped when idle, about $7 if left running.
  Provisioning: the smallest shared-core instance, the Enterprise edition chosen explicitly,
  automatic storage increase off.*
  - *Post-submission divergence (carry to the evaluation report): the submitted `04` quotes
    the 2026-11-04 stop date (TA-16); ADR-078 moves it.*
- *ADR-079 (to write): service topology. Each MCP server runs as a Cloud Run sidecar of its
  agent. The services are the gateway (the only public one), the orchestrator, and the
  reporting, sentiment, forecast and QA agents, all internal with IAM. Rationale: one fewer
  cold-start hop per domain against the 120-second ceiling, and no service-to-service
  authentication between an agent and its MCP server. Trade-off: an agent and its MCP server
  share one service account; database credentials are mounted only into the MCP container.
  That needs a new limitation, written with the ADR. The early deploy needs only the
  orchestrator and the reporting agent.*
- *ADR-080 (to write): the UI is a Next.js static export served by the FastAPI gateway (same
  origin, no Node runtime in production). Cloud Storage hosting is rejected: it needs a load
  balancer and a separate origin. Next.js is kept over Vite for experience and portfolio
  value; the ADR will say so explicitly, because it is not a requirement at this scale (the
  UI needs nothing beyond React).*
- *Sequencing: the deploy comes first in Sprint 4, then the QA build.*
- *Still to plan: the rest of the Sprint 4 sequence, and L-60 (the router's model-written
  `reason` and unredacted tracebacks in the logs), the last unrecorded gap from the
  traceability matrix; it is recorded with the ADRs.*
*2026-10-05: Sprint 4 starts on 2026-10-06, the day after Sprint 3's final date, pulled forward
from 2026-10-26. The sequence is the deploy first (ADR-078, window 2026-10-12 to 10-14), then
QA. The rest of the sequence is planned separately. ADR-078 to ADR-080 and L-60 and L-61 are
now written; they record the planning decisions above.*

*2026-10-08: ADR-081 (deploy configuration for the reporting slice) and ADR-082 (sprint calendar re-baselined) are written. Sprint 4 is 2026-10-06 to 10-25, Sprint 5 10-26 to 11-08, Sprint 6 11-09 to 11-22, buffer 11-23 to 12-05; the headers above carry the new dates, each marked "re-baselined, ADR-082". Phase 1 readiness gate: the readiness PR (`feat/sprint4-deploy-readiness`) must merge by the end of 2026-10-11 or the deploy window moves by a short ADR.*
*Planned sequence (2026-10-08):*
- *Phase 1, deploy readiness, local only: 10-08 to 10-11.*
- *Deploy window: 10-12 to 10-14 (ADR-078).*
- *Reporting filters (L-62): about 10-15 to 10-18.*
- *QA build: about 10-19 onward.*
- *Fault-injection harness last.*
*2026-10-08, e2e assertion corrected after a result: the checkpoint e2e's figures check compared the whole figures object to the SQL-derived five keys and failed on the first run (2 live calls) because the answer also carries the ADR-073 fields (`group_by`, `groups`, `group_count`, `truncated`, `technician_id`, `technician_name`), which the test predated. The five keys equalled the SQL, so the answer was not wrong; the assertion was stale. It now compares the five keys and requires the six fields to be empty. The first response was not saved, so one fresh attempt was made (2 more calls; 4 of the 4 budgeted were used across the day) and passed against the corrected assertion. Because the assertion was changed after seeing a result, this note records it; it was not tuned to make a wrong answer pass.*

*2026-10-08, deploy window outcome: **the reporting slice is verified serving** (ADR-084), on day one of three. Build 5a181fa1 at commit `1a3f1e3` built, deployed and verified its own revision: `ops-orchestrator-00004-c6f` and `ops-reporting-00004-5kz`, each at 100% traffic, every `verify.py` check passing. The stop rule did not fire. 7 of 8 live calls used, no 503. `ops-db` is stopped and the build trigger is disabled (ADR-083) until Sprint 5 extends the deploy. Details and timings are in `docs/deploy-window-log.md`.*
*Provisioning record, 2026-10-08: Cloud SQL `ops-db`, PostgreSQL 16, Enterprise edition, `db-f1-micro`, 10 GB SSD, zonal, us-central1, public IP with no authorized networks, storage auto-increase off, automated backups and point-in-time recovery off (the data is synthetic and reloadable), `max_connections=60` (raised from 25; L-66), labels `app=agentic-service-ops`, `component=deploy`. Created in 9 min 42 s. **The console cost estimate was not captured** (the CLI cannot read it); the owner adds the actual Cloud SQL cost from Billing, Reports, in a dated note once the billing data settles (about 24 hours).*
*Fix PRs from the window:*
- *#30: the create call must not carry `name` (the v2 API rejects it); found by the first deploy.*
- *#31: tests for both paths of `deploy_service.py` (create omits `name`, update keeps it).*
- *#32: check 2 probes `POST /ask` and `GET /` (401 or 403 only); `/healthz` is reserved by Cloud Run and answers 404, now an INFO line.*
- *#33: caller token from the metadata server (superseded, dead code).*
- *#34: check 6 impersonates `CALLER_SA` in the pipeline (ADR-085); #29 earlier added the labels, account-name defaults and the secrets list.*
*2026-10-08, notes for the owner on the reporting filters (ADR-086):*
- *`05-test-scenarios.md` (yours to edit, not edited here): TS-01-A ("SLA compliance in the west region last month"), TS-02-C ("incident rate for the central region", no period given) and TS-05-B ("SLA compliance in the west region in July 2026") are now answerable as scoped figures. Each can be restated as: routed to reporting, the answer says "the west region" (or "central"), and the counts and rate equal the independent calculation. TS-02-C's assumed range (July 2026) is stated by the agent as before. "Region" means the customer site's region, the same column the by-region breakdown uses; an area that is not one of the four regions is declined, not mapped (L-68).*
- *The golden set was not opened (ADR-074). Golden items about one region or one account may have a different correct answer now that the tools can scope a figure; check them at the Sprint 5 evaluation and, if needed, make a `golden_v3` with disclosure.*
- *The deploy trigger is still disabled (ADR-083); merging this changes `services/**` and deploys nothing.*
*2026-10-09, phase 4 split into three prompts, and phase 4a (this PR, `feat/qa-foundations`) outcome:*
- *Phase 4a (L): ADR-087 (the QA agent's checks and the sentiment rating-check rule, pre-registered) and ADR-088 (retry classes, one 120 s deadline, breaker values, cost cap, degraded result); the Deadline, CircuitBreaker and cost accounting in `packages/common`; the Gemini breaker; agents clamp to the deadline and report cost; the orchestrator's degraded result; the sentiment baseline. **No QA agent yet.***
- *End-to-end (6 of 6 live calls): a normal reporting question answered with `cost_usd` = 0.00095 in the orchestrator log (the routing call plus the agent's parse call, list price); with `agent_reporting` stopped, three asks each returned the degraded result naming reporting (`escalate: true`), the third opened the breaker, and the fourth failed fast in 3.6 s (the routing call only) with no call to the agent; no traceback, error text or internal address in any response.*
- *Phase 4b (M): the QA agent (`agent_qa`) and the orchestrator's verification loop.*
- *Phase 4c (N): the fault-injection harness and the catch rate.*
- *Sentiment baseline (measured once as `app_eval`, 2026-10-09, after the rule was committed in ADR-087): n = 4,715 covered comments, x = 7 contradictions, p̂ = 0.001485, so p0 = max(p̂, 0.01) = 0.01. The 1% floor (the owner's judgement) sets the bar on this data. Per region: central 2/1,198, northeast 1/1,395, southeast 3/1,208, west 1/914.*
*2026-10-09 (owner, GCP Billing): 2026-10-01 to 10-09, $0.29 gross, $0.21 savings, $0.08 net, covering the deploy window and storage since.*
*2026-10-09, phase 4b (this PR, `feat/qa-agent-reporting-forecast`): the QA agent for reporting and forecast, and the verification loop (ADR-089).*
- *Built: `agent_qa` (A2A agent, `app_qa` credentials, its own SQL written from the data dictionary, a compose service on loopback), the verification contract (`packages/schemas/verification.py`), `AskResponse.qa_status`, the orchestrator's loop with QA's own breaker, the reviewer note (`qa_guidance`) the specialists read as untrusted text, declines carrying their `parsed_request`, and routing failures as the degraded result. 221 QA tests, 41 loop tests, an integration suite showing QA's SQL equals the tools' on the loaded database over 100 cases, and an independence test.*
- *Interpretation gate (pre-registered, `6c79e50` at 2026-10-09 09:29 CDT, before any live call): **failed twice**. `qa_interp_v1` run 1: 6 false rejects of 42 (limit 2), 37 of 42 caught (need 34); the one revision `qa_interp_v2` run 1: 7 and 39. Both were stopped after the first failing run (194 of 420 gate calls). The check ships in **advisory mode** (L-74). The early stops and the same-day revision are disclosed in `evals/qa_interp/README.md`.*
- *End to end (13 of 20 live calls): a reporting, a region-filtered and a forecast question came back `qa_status: verified`; sentiment came back `not_checked` with the not-verified line; with `agent_qa` stopped, one ask returned the degraded result with `qa_status: unavailable`. 207 live calls in all (budget 450).*
- *For the owner: seven definition gaps QA hit while checking against §6 were listed in L-72. **Ruled 2026-10-09 and fixed:** all seven are rules in data dictionary §6, the incidents tools changed for the tie order and the name words, and QA enforces one reading of each (no tolerance left).*
- *For the owner, `05-test-scenarios.md` (yours to edit, not edited here): scenarios that expect an HTTP error when an agent is down, or when the model is rate-limited or out of quota, now get the degraded result instead (HTTP 200, `outcome: degraded`, `escalate: true`, a warning naming the capability, and for routing `routing`). They need rewording to that result. A QA-checked answer carries `qa_status`; a sentiment answer says it is not verified.*
*2026-10-09, phase 4c (this PR, `feat/qa-sentiment`): QA checks for sentiment answers (ADR-090), and `not_checked` no longer stands for "no check yet".*
- *Rules first: data dictionary §6 "Sentiment answers" (`276d59a`, 19:48 CDT), then the code. QA's `sentiment.py` is written from it with no import of `mcp_feedback`, `agent_sentiment` or any model code; τ and the model version come from the committed manifest file.*
- *Real data: 15 cases against the real feedback server plus a rolled-back partial-coverage case; the full-window rating cross-check is n = 4,715, x = 7 and passes. End to end: 12 of 12 live calls (a trend, a quotes question, an account decline and a reporting regression, all `verified`).*
- *For the owner: L-77 and L-79 needed rulings. **Ruled and applied 2026-10-09** (see ADR-090's dated note): the flag check has a 0.00005 band, the compared bucket is named and checked, nothing-to-test must read no clear change, and quote selection is a written, enforced rule.*
*2026-10-10, phase 5 (this PR, `feat/qa-fault-injection`): the fault-injection harness and the catch rate (ADR-091).*
- *Freeze: catalogue, generator, seed `20261010`, mutations and report format committed together at `b5ad1f4`, 2026-10-10 12:32 CDT, before any QA verdict. The owner's five faults (owner-selected, AI-co-written) were added first, with the owner's rulings on variants and translations.*
- *Result: 219 of 223 caught (98.2%, 95% Wilson 95.5-99.3%) on 34 assistant-drafted caught-expected faults; 1 false alarm in 62 controls; 4 misses; the pre-registered rating rule agrees with QA in 50 of 50 cases (caught 0/10, 0/10, 1/10, 8/10, 10/10 at 0.5, 1, 2, 4 and 8%); consistent misparse 0 of 71; the owner's forecast fault 0 of 6; the owner's 4a, 4b and 5 known gaps held.*
- *Sprint 4 goal, "QA agent operational with all three verification strategies; measurable catch rate": **met**, with limits stated: the three strategies run on every answer (own SQL, manifest and arithmetic, rating and comment checks), the interpretation call is advisory (L-74), the catalogue is not blind (L-85), and the harness found one defect that would degrade a correct answer (L-81).*
- *Loop demonstration, 5 of 10 live calls: a count off by one through a test-only proxy came back degraded with the failed check named, escalated and not retried; the same question with no fault came back verified.*
*2026-10-10, phase 5b (this PR, `fix/qa-fault-findings`): QA fixes from the fault injection and measurement 2 (ADR-092).*
- *Rules first: data dictionary §6 "Answer text" (`d5c0fbe`, 13:42 CDT), then the code (first code commit `e96daa2`, 13:48).*
- *Measurement 1 (ADR-091): 219 of 223 = 98.2%, one false alarm in 62 controls. **Measurement 2 (same frozen catalogue and seed, after the fixes): 223 of 223 = 100% (95% Wilson 98.3-100%), 0 of 62 controls fail.** Six cases changed verdict, all fail where they passed: the four forecast text figures and owner faults 4a and 4b. Nothing caught in measurement 1 now passes. The fixes were designed after measurement 1's misses, so measurement 2 is not new evidence on unseen faults (L-85).*
- *Unchanged: rating sensitivity (matches the pre-registered rule in 50 of 50), consistent misparse 0 of 71 (L-74), the owner's forecast fault 2 passes 0 of 6 (L-83(a), a Sprint 5 decision).*
- *`qa_status: failed` is new; `not_checked` now means the request ended before any check ran.*
*Planned sequence update (2026-10-08): the deploy window is done. The reporting filters (L-62) start next, from about 2026-10-09; then QA; the fault-injection harness last.*
*For `06` (due 2026-11-08), not written there: the window's failures are material for its production-support write-up: a create-body field the API rejects, a reserved path (`/healthz`) that hides the IAM boundary, identity-token minting in Cloud Build, IAM propagation delay (a new invoker binding took over a minute), and a revision failing its readiness probe while the database was stopped.*

**Planned:**
- [x] Sprint 4 backlog (2026-10-08): dispose engines in the MCP figures tests' fixtures (L-66).
  *2026-10-08: done. A pool-less, disposed engine fixture in `tests/integration/conftest.py`; the integration suite passes (883) at `max_connections=25`, where the two figures files had 11 failures before. L-66 resolved.*
- [ ] Sprint 4 backlog (2026-10-08): the trace-ID-in-access-logs follow-up PR. It needs an access-log middleware in all seven servers and a trace-ID header on the A2A and MCP clients, because the ID only reaches agents and MCP servers in the request body.
  *2026-10-10: carried to Sprint 5 (listed there). Reason: a small design change that deserves its own short ADR, and Sprint 6 observability depends on it.*
- [x] Region and account filters on the reporting tools, with a `parse_v3` update and a parse eval re-run (L-62). Built before QA, so QA's recompute is written against the filtered tools.
  *2026-10-05: added. 05 TS-01-A, TS-02-C and TS-05-B depend on it.*
  *2026-10-08: done (ADR-086, PR `feat/reporting-filters`). `region` and `account_id` filters on the four incident tools, `find_account`, `parse_v4` (the agent's default) and the clarification reasons `account_not_found` and `account_ambiguous`. Evidence: 90 integration tests against raw SQL as `app_eval` (the filtered figure equals its group's row, every metric, every region, all 50 accounts, combinations); the parse gate passed on the first candidate (`parse_v3` 15/16 in each of 3 runs, `parse_v4` 15/16 on the old items and 12/12 on the new in each of 3 runs, both unsupported areas declined in all 3), 134 of 220 calls; one end-to-end filtered question matched SQL. L-62 resolved; L-67 to L-69 recorded.*
- [x] QA agent (ADR-055, ADR-056) — own-SQL re-check (reporting); input history, arithmetic and a per-slice lookup of the stored backtest error, not a per-request backtest run (forecast); star-rating cross-check, comment-set and confidence-flag checks (sentiment); one LLM call checks interpretation
  - [x] Reporting: every figure recomputed with QA's own SQL, declines checked, text checked.
    *2026-10-09: done (ADR-089). `services/agent_qa`, `tests/integration/test_qa_agrees_with_tools.py` (100 cases against the loaded database), `tests/unit/test_qa_independence.py`; one overall and one region-filtered question verified end to end.*
  - [x] Forecast: weeks, arithmetic, the manifest's serving table and shown errors, the year-end caveat, history, text.
    *2026-10-09: done (ADR-089). `services/agent_qa/tests/test_qa_forecast_checks.py`; one forecast question verified end to end.*
  - [x] Sentiment: rating cross-check, comment-set and confidence-flag checks (phase M2).
    *2026-10-09: done (ADR-090). Coverage, counts, shares, buckets, flags, the trend, quotes, declines and text recomputed by QA from the written §6 rules; the rating cross-check at ADR-087's rule on every sentiment verdict; sentiment answers are `verified` and the temporary not-verified line is gone (L-73 resolved). 15 real-data cases equal the real feedback server; one trend, one quotes question, one decline and one reporting regression ran end to end (12 live calls).*
  - [x] The interpretation call and its gate.
    *2026-10-09: built and measured; the gate failed twice and the check ships advisory (L-74, ADR-089).*
  - [x] Sentiment contradiction thresholds set under a stop rule (ADR-055).
    *2026-10-09: the rule was fixed in ADR-087 before the baseline was measured (n = 4,715, x = 7, p0 = 0.01) and is applied unchanged by QA (ADR-090); the full-window check passes.*
- [x] Bounded retry loop (max 2), escalation path on final failure — owned by the orchestrator (ADR-055)
  *2026-10-09: done (ADR-089). Interpretation failures re-ask the specialist with QA's note, up to 2 times; a figures failure is never retried; the deadline and cost cap hold across it. 41 loop tests. With the interpretation check advisory (L-74) no running request is re-asked yet.*
- [x] Circuit breaker, one per outbound dependency (the Gemini provider interface; each A2A client), built with the per-request deadline (ADR-077; NFR-4)
  *2026-10-09: done for the Gemini transport and the reporting, sentiment and forecast clients (ADR-088: 3 failures, 30 s, one trial). QA's own breaker comes with the QA client in phase M. Tests: `tests/unit/test_circuit_breaker.py`, `tests/unit/test_llm_breaker.py` and the orchestrator's `test_resilience.py` (opens after 3, fails fast, one trial, 4xx and declines never count, one dependency does not affect another). End to end (`tests/e2e/test_resilience_e2e.py`, 6 live calls): see the 2026-10-09 phase 4a note. State is per process (L-70).*
  *2026-10-09: QA's own breaker is in (ADR-089): three failures open it, the following requests fail fast to the degraded result with the answer marked not verified, and a task QA rejected as malformed does not count. `test_qa_failures_open_its_own_breaker_and_specialists_keep_answering`.*
- [x] Fault-injection harness for QA catch-rate measurement
  *2026-10-10: done (ADR-091). Catalogue v1 (47 assistant-drafted faults and the owner's 5 in 8 variants), frozen at `b5ad1f4` (12:32 CDT) before the first run; 390 cases over 62 controls, no model called. **Catch rate on the assistant-drafted faults expected to be caught: 219 of 223 = 98.2% (95% Wilson 95.5-99.3%), 34 faults; reporting 104/104, forecast 39/43, sentiment 76/76.** 1 false alarm in 62 controls (L-81); 4 misses (L-82); rating sensitivity as pre-registered in 50 of 50; consistent misparse 0 of 71 (L-74); the owner's forecast fault 0 of 6 (L-83). Loop demonstration 5 of 10 live calls.*
- [x] Sprint 4 backlog (2026-10-10): fix the zero-figure false alarm in QA's reporting text check (L-81) in a separate PR that re-runs the frozen catalogue and seed as a second measurement.
  *2026-10-10: done (ADR-092, PR `fix/qa-fault-findings`). L-81 resolved; control `reporting:f09` passes; 0 of 62 controls fail in measurement 2.*
- [x] Sprint 4 backlog (2026-10-10): make QA's forecast text check positional and drop the neighbour tolerance where the template does not round (L-82); same PR and second measurement. If Sprint 4 has no room, Sprint 5.
  *2026-10-10: done (ADR-092). Positional for all three agents, from data dictionary §6 "Answer text"; F08 9 of 9; the small-sample rule (L-84) and `qa_status: failed` came with it.*
- [ ] Sprint 5 decision item (2026-10-10, owner; L-83 split in ADR-092): build or not an answer-time check that every served forecast number equals the model's own prediction, re-implemented in QA from the manifest's stored coefficients (a check against the model, not a prediction, so consistent with ADR-055). The owner leans towards building it, as the condition for "QA verifies forecasts" meaning more than arithmetic. The model-does-not-know-a-holiday case (L-83(b)) stays an offline-evaluation matter.
- [ ] Sprint 5 option (2026-10-10): owner-written faults added to the catalogue and reported apart (L-85).
  *2026-10-10: the decision item and this option are listed under Sprint 5; not Sprint 4 work.*
- [x] Price a full routing eval run (~300-700 requests, two LLM calls per request per
  ADR-046) on paid Flash-Lite using the official pricing page, and add that cost to the
  budget alongside the ~$20-30 Pro-for-QA test (ADR-029; optional, buffer only, ADR-056). ADR-041 already decided the runs
  use the paid, spend-capped project.
  *2026-10-10: done (architecture §9). Official pricing page read 2026-10-10: paid Flash-Lite $0.30 per 1M input and $2.50 per 1M output tokens. 150 end-to-end requests (50 questions, k=3, routing + parse + advisory interpretation) about $0.24; routing only about $0.04. The Pro-for-QA test keeps its ~$20-30 ceiling. Revised plan: the held-out set is the Sprint 5 routing eval, run once on the paid key.*
- [x] Minimal Cloud Run deploy of the reporting slice (ADR-045, dates moved by ADR-078 and ADR-084):
  *2026-10-08: verified serving, build 5a181fa1 at `1a3f1e3`, revisions 00004, every `verify.py` check passing in the pipeline. See the outcome note above.*
  orchestrator and `agent_reporting` with `mcp_incidents` as its sidecar (ADR-079), with the
  smallest Cloud SQL instance (stopped when idle), 2026-10-12 to 10-14 (was 11-02 to 11-04),
  timeboxed to 3 days. Cloud Build trigger with an explicit deploy
  step; post-deploy check that the serving revision is the one just built at 100% traffic;
  Secret Manager; IAM ID tokens between services; `alembic upgrade head` and the grants suite
  against Cloud SQL. Stop rule: not verified serving by end of 10-14 → stop, record R-03 as
  realised, write it up as the first incident in `06`, leave Sprint 5 unchanged. Carry order
  if Sprint 4 overflows: the fault-injection harness moves to Sprint 5 first.
  - [x] Agent Card cached with a TTL (currently fetched on every request).
    *2026-10-08: cached per target URL for `AGENT_CARD_TTL_S` (default 300 s), dropped after any failed call; the fetch carries the ID token.*
  - [ ] Trace id in web-server access logs.
    *2026-10-10: carried to Sprint 5 with the backlog item above.*
  - [x] A readiness probe alongside `/healthz`.
    *2026-10-08: `/readyz` on every MCP server and agent; compose orders startup on it.*
  - [x] Code for the deploy, built and unit-tested locally, not yet run on GCP: database host by env (TCP or Cloud SQL socket), MCP URL by env, IAM ID tokens on the card fetch and the message call, non-root images with nothing secret baked in.
    *2026-10-08.*
  - [x] Deploy config drafts in `deploy/` (v2 service definitions, `cloudbuild.yaml`, `render.py`, `verify.py`, runbook), validated locally only.
    *2026-10-08.*
  - [x] Cloud SQL major version 16, to match local Postgres (R-14 parity); record it at provisioning.
    *2026-10-08: `ops-db` is PostgreSQL 16 (see the provisioning record above).*
- [x] Wire the per-request cost cap (§9, `MAX_COST_PER_RUN_USD`, unwired today); it matters once the QA revise loop can multiply calls.
  *2026-10-09: wired (ADR-088). Default $0.02, list-price, summed across services from response metadata and checked before each specialist hop; malformed or negative reported costs are rejected. Estimate only (L-71).*
- [x] Decide the service count and UI hosting at Sprint 4 planning. Evaluate each MCP server as a Cloud Run sidecar of its agent, and the UI as a static export served by the gateway or Cloud Storage, so no Node server runs in production.
  *2026-10-05: decided. Each MCP server is a sidecar of its agent (ADR-079); the UI is a Next.js static export served by the gateway (ADR-080).*
- [x] Draft `05-test-scenarios.md` (carried over from Sprint 3; due 2026-11-01). Includes the FR-03 known-failing scenario.
  *2026-10-05: no longer carried over; the `05` draft stays in Sprint 3.*
  *2026-10-05: drafted and ticked under Sprint 3; nothing remains here.*
- [x] Re-check `docs/requirements-traceability.md` at sprint close.
  *2026-10-10: done. Every row's status and evidence re-read; counts unchanged (13 met, 9 partly met, 1 not yet built, 1 open, 3 optional; 27); four stale notes corrected (FR-13, NFR-2, NFR-3, NFR-5). No row's evidence points at anything unmerged: every PR through #41 is merged.*

*Planning note, 2026-10-01 (from 4b):*
- *ADR-034's 120 s ceiling is not enforced as one request deadline today. Each hop has
  its own timeout: routing 30 s, then the specialist's A2A call up to 60 s (reporting) or
  85 s (sentiment), so the bound holds only by adding them up. The Sprint 4 QA loop
  multiplies hops (QA, up to two revisions), so it must add a single per-request deadline,
  set once and passed through every step, and on expiry return the degraded result with a
  warning and an escalation flag that NFR-1 describes (`02`, non-functional requirement 1,
  Performance).*
- *QA's interpretation call (ADR-056) must not receive quoted customer comments (security
  guarantee 9). It gets the sentiment answer with each quote replaced by its feedback ID;
  the quotes are verified mechanically against the database (the IDs exist, are in range
  and region, and the quoted text matches `feedback_text`).*

**Close (2026-10-10, day 5 of a sprint planned as 2026-10-06 to 10-25).**
**Goal: met, with stated limits.** The QA agent is operational for all three agents (reporting, forecast, sentiment), and the catch rate is measured. It is quoted only as follows:
- **Measurement 1 (ADR-091): 219 of 223 cases, 98.2%, an upper bound.** The faults were drafted by the assistant that built QA (L-85), and the five owner-selected faults were co-written with it.
- **Consistent misparses: 0 of 71 caught.** Interpretation is advisory (L-74); `verified` means the figures are correct for the request as parsed.
- **Measurement 2 (ADR-092): 223 of 223.** The same frozen catalogue and seed after fixes designed from measurement 1's misses. It is evidence that the fixes work on the cases they targeted, not a new catch rate.

**Shipped (PRs #28 to #41, 2026-10-08 to 10-10):**
- *Phase 1, deploy readiness:* #28 the readiness change set (deploy config, `/readyz`, card cache, the deploy code and drafts); #29 cost-split labels, account-name defaults and the secrets list.
- *The deploy window (ADR-084, ADR-085):* #30 the create call omits `name`; #31 tests for create and update; #32 check 2 probes `POST /ask` and `GET /`; #33 the caller token from the metadata server (superseded); #34 check 6 impersonates `CALLER_SA` (the pipeline); #35 the window's records.
- *Reporting filters:* #36 `region` and `account_id` filters, `find_account`, `parse_v4` (ADR-086, L-62).
- *Phase 4a, foundations:* #37 ADR-087 and ADR-088: the QA checks and the pre-registered rating rule, the deadline, the breaker, the cost cap and the degraded result.
- *The QA agent for reporting and forecast:* #38 `agent_qa`, the verification contract and the orchestrator's loop; the interpretation gate (failed twice, advisory); the seven L-72 rulings enforced (ADR-089).
- *QA for sentiment:* #39 the sentiment checks, §6 "Sentiment answers", the flag band, the compared bucket and the quote selection rule (ADR-090).
- *Fault injection:* #40 the harness, catalogue v1 and its freeze, measurement 1 and the loop demonstration (ADR-091).
- *The QA fixes and measurement 2:* #41 positional text check, zero denominators, small samples, `qa_status: failed` (ADR-092).

**Carried over or dropped:**
- **Trace ID in web-server access logs: carried to Sprint 5.** It needs an access-log middleware in all seven servers and a trace-ID header on the A2A and MCP clients, which is a small design change with its own short ADR when built. Sprint 6 observability depends on it.
- **Price a full paid routing eval run: done at the close** (architecture §9): about $0.24 for 150 end-to-end requests at paid Flash-Lite list prices, about $0.04 routing only; the Pro-for-QA test keeps its ~$20-30 ceiling.
- **Re-check `docs/requirements-traceability.md`: done at the close.** Statuses and counts unchanged (13 met, 9 partly met, 1 not yet built, 1 open, 3 optional); four stale notes were corrected.
- **Draft `05-test-scenarios.md`: not a Sprint 4 item.** It was drafted and ticked under Sprint 3 (2026-10-05); submission is the owner's.
- **The Sprint 5 decision item and options added to this list during the sprint** (L-83(a), owner-written faults) are listed under Sprint 5.
- Nothing else in the Planned list was left undone: every other item is ticked above with its evidence.

**Blockers encountered:** factual, each recorded elsewhere:
- The Cloud Build token-minting fixes (#33, #34; ADR-085, L-64).
- IAM propagation delay: a new invoker binding took over a minute (the sprint-log note under the deploy window).
- A usage-limit cut-off during M1's interpretation gate left a partial run and an early stop that was not pre-registered (ADR-089's disclosure; L-74).
- The interpretation gate failing twice (L-74).
- The L-72 spec gaps found at the owner's review of #38 (ADR-089's dated note).
- The line-ending hash mismatch found in #41: two of the four frozen files hashed differently in a fresh checkout because git rewrote them as CRLF (ADR-092; pinned in `.gitattributes` at this close).

**Retro (owner-endorsed, assistant-drafted, 2026-10-10):**
- What went well:
  1. **Pre-registration held every time.** In L (phase 4a), M1, parse_v4 and the fault catalogue, every gate or freeze was committed before the first live call or verdict, and the timestamps were checked. No gate was loosened after results.
  2. **The deploy window reached verified serving on day one of three.** R-14 did not happen: the migrations, grants and load ran unchanged on Cloud SQL. Five small fix PRs, each caught by a check before it caused harm.
  3. **The malformed-input and exposure tests (Sprint 3 retro rule 4) found real defects:** a bearer token in the A2A SDK's DEBUG logs (L-63) and an infinite number in metadata crashing protobuf.
  4. **The owner's faults found what the assistant's did not.** Faults 4a and 4b exposed two missing small-sample checks, now closed. Fault 2 turned "QA can't check forecasts" into a measured number with two separate causes (L-83).
  5. **Fault injection found a false alarm on a correct answer** (L-81), which matters more than a miss, and it was fixed and re-measured.
- What didn't:
  1. **QA was first built to accept every possible answer where §6 had no rule (L-72).** That calibrated it to the code it was checking. It was caught at review, not by process: the prompt said "stop and ask", but the owner could not be reached mid-session.
  2. **The interpretation gate failed twice.** The check is advisory and 0 of 71 misparses are caught. This is the largest open quality gap. Gates built on assistant-drafted items keep repeating the same non-blind pattern (L-69, L-74, L-85).
  3. **Rules were written after the code in M1.** The rounding (L-77), the trend and quote rules (L-79) and the quote skew (L-80) all surfaced late.
  4. **The assistant's prompt planning made arithmetic mistakes:** a live-call budget that forgot the advisory call (5 against 4), and day-cap planning in M1.
  5. **Process friction:** a usage-limit cut-off left partial gate runs, and the gate stopped early without that being pre-registered. With up to seven PRs a day, review and the re-upload of docs to the Project can fall behind the build.
- What changes next sprint:
  1. **Spec first, as a standing rule:** every check, metric or display rule goes into data dictionary §6, or the relevant ADR, before its code.
  2. **When a prompt hits a spec gap and the owner cannot be reached:** stop that item, record the gap, and continue with other items. Never implement a tolerant "accept every reading" behaviour.
  3. **Live-call budgets are worked out per path,** including advisory calls and a stated retry margin, and checked before any run.
  4. **Any gate built on drafted items is labelled non-blind** and is not treated as evidence of quality. Sprint 5 schedules owner writing time for the held-out routing set, a fresh FR-03 set and a fresh interpretation set.
  5. **Frozen artifacts are pinned:** `.gitattributes` keeps them at LF line endings, and git blob hashes are recorded alongside file hashes (ADR-092's dated note).

**Academic deliverable status:**
- `05-test-scenarios.md` (due 2026-11-01) and `06-production-support.md` (due 2026-11-08): under ADR-093 both fall in Sprint 6 (`05` in its first week, `06` on its last day, which benefits from the full Sprint 5 deploy). The dates are the course's and did not move. `05` was drafted 2026-10-05; submission is the owner's.
- Weekly status report due (maintained by Eric)
  *2026-10-10, further post-submission divergence from ADR-093 (carry to the evaluation report):*
  - *`03` quotes the original calendar and, after ADR-082, the 2026-10-08 re-baseline. ADR-093 moves Sprint 5 to 2026-10-12 to 10-25 and Sprint 6 to 10-26 to 11-08, with the buffer 11-09 to 12-05; the final date is unchanged. `03` is Eric's to edit; nothing was changed.*

**Decisions made this sprint** (ADR-078 to ADR-080 were written 2026-10-05 as planning-time decisions; the rest as built):
- ADR-078 — The reporting-slice deploy pulled forward to 2026-10-12 (planning-time, 2026-10-05; dates superseded by ADR-084)
- ADR-079 — Each MCP server a Cloud Run sidecar of its agent; the first deploy is two services (planning-time, 2026-10-05)
- ADR-080 — The UI is a Next.js static export served by the FastAPI gateway (planning-time, 2026-10-05)
- ADR-081 — Deploy configuration for the reporting slice (2026-10-08)
- ADR-082 — Sprint calendar re-baselined: Sprint 4 to 10-25, buffer 11-23 to 12-05 (2026-10-08; sprint dates superseded by ADR-093)
- ADR-083 — The deploy runs in the paid project; cost-split labels; trigger disabled between windows (2026-10-08)
- ADR-084 — The deploy window pulled forward to 2026-10-08 to 10-10; verified serving on day one (2026-10-08)
- ADR-085 — Deploy verification and IAM changes found in the window (2026-10-08)
- ADR-086 — Region and account filters on the reporting metrics, `find_account`, the parse gate (2026-10-08)
- ADR-087 — The QA agent's checks; the rating cross-check rule, pre-registered (2026-10-09)
- ADR-088 — The verification loop, one request deadline, breaker values and the cost cap (2026-10-09)
- ADR-089 — The QA agent for reporting and forecast, the verification contract and the loop (2026-10-09)
- ADR-090 — QA checks for sentiment answers; `not_checked` narrowed (2026-10-09)
- ADR-091 — The fault-injection harness, catalogue v1, the freezing rule and measurement 1 (2026-10-10)
- ADR-092 — QA fixes from the fault injection, `qa_status: failed` and measurement 2 (2026-10-10)
- ADR-093 — Sprint calendar re-baselined at the Sprint 4 close (2026-10-10; supersedes ADR-082's sprint dates only)

*Note: scope-expansion decisions (broader capability within the existing three domains) are only appropriate if genuinely ahead of plan at this boundary — see the working agreement in `architecture.md` §13.*

---

## Sprint 5 (2026-10-12 to 2026-10-25; re-baselined, ADR-093) — Interface & evaluation
**Goal (increment):** Deployed system with a working UI; routing accuracy reported with failure analysis.

**Planned:**
- [x] Routing eval harness + failure-case analysis (ambiguous, multi-domain, and out-of-scope intents included)
  *2026-10-13 (Sprint 5 close): done.* Harness `evals/results/sprint5_x/harness.py` and scorers (`score_routing.py`, `score_golden.py`), the pre-registered scoring (`golden_scoring.md`, `evals/sprint5_gates.md`), and the failure analysis `evals/results/sprint5_failure_analysis.md` (ambiguous, multi-domain and out-of-scope intents included; data in `sprint5_failure_data.md`).
- [x] Held-out routing set (never used to revise a prompt), written by Eric
  *2026-10-11: generated under ADR-094, not owner-written (drafts; the owner's skim comes first). Set: `routing_heldout_v1` (`evals/generated/`).*
  *2026-10-11: frozen, commit `8ed47771fa084794fe663506ae489339f5db4459`: `routing_heldout_v1`, 50 items (target 50), 3 owner drops at the skim replaced from skimmed-Y reserve items of the same category. Final sets are append-never; a change is a `_v2` under a new ADR. Hashes: `evals/generated/manifest.json`.*
  *2026-10-12 (Prompt W, ADR-103): **evaluation freeze.** The system Prompt X measures is recorded in `evals/freeze_s5.json` (commit `1d105ea`, every prompt file's SHA-256, models and thinking levels, mode flags, caps, the data dictionary's hash, default router `route_v3`) and checked by `tests/unit/test_eval_freeze.py`; tag `eval-freeze-s5`. Both Sprint 5 gates failed (ADR-101, ADR-102), so the frozen system keeps `route_v3` and the advisory interpretation check. Scoring for X is pre-registered in `evals/sprint5_gates.md` (B3). Not ticked: Prompt X runs the held-out set.*
  *2026-10-13 (Prompt X): **held-out routing run on the deployed, frozen system (images `9607fa72`, paid mode, `route_v3`).** `routing_heldout_v1`, k=3: 38, 38, 38 of 50 correct (range 38 to 38, no flipping items); 38, 38, 38 of 43 without the 7 ambiguous items (labelled as such). All 21 ambiguous item-runs are wrong by construction under `route_v3` ("ambiguous not flagged"); the other wrong item-runs are 15, all "out-of-scope accepted" (5 items: OOS-01, OOS-03, OOS-14, NM-14, NM-20). No wrong area, false ambiguous, multi-domain miss or error. Per-run median latency 3.5 to 3.8 s, p95 5.1 to 17.6 s; none over 120 s. Not ticked (Prompt Y). The set is now spent for blind use. Data: `evals/results/sprint5_x.md`, `evals/results/sprint5_failure_data.md`.*
  *2026-10-13 (Sprint 5 close): done, with the disclosure.* `routing_heldout_v1` (50 items) was run once, k=3, on the deployed frozen system: 38, 38, 38 of 50, no flipping items; 38 of 43 without the 7 ambiguous items. It was generated under ADR-094, not written by Eric, and is now spent for blind use (L-86 update). Summary: `evals/results/sprint5_summary.md`.
- [ ] Run the real-data QA suites on Cloud SQL after the sentiment predictions backfill there (`tests/integration/test_qa_sentiment_agrees.py` and the sentiment figures suites): locally they need the stored predictions, so CI skips them (L-78). *Added 2026-10-09.*
  *2026-10-13 (Sprint 5 close): not done; carried to Sprint 6.* The scoped L-78 run on Cloud SQL needs a reviewed credential plan (Sprint 6 backlog). The sentiment oracle's counts were checked against the deployed system by the golden run instead (G04, G20, G21 equal the oracle), which is not the same suites.
- [ ] A second interpretation-gate attempt for QA's check (L-74), **only on an owner-written set** of question and parsed-request pairs, with a new pre-registered gate; the 84 assistant-drafted pairs have been used to judge `qa_interp_v1` and `v2` and can't confirm a third prompt. Review the 13 rejected correct pairs listed in L-74 first. *Added 2026-10-09.*
  *2026-10-11: generated under ADR-094, not owner-written (drafts; the owner's skim comes first). Set: `interp_fresh_v1`; the pairs are built from `intent` at the freeze, not yet.*
  *2026-10-11: frozen, commit `8ed47771fa084794fe663506ae489339f5db4459`: `interp_fresh_v1`, 23 items (target 24; reporting 10, forecast 7, sentiment 6: one sentiment slot had no eligible reserve item, so the set is one short) and `interp_pairs_v1`, 46 pairs (23 correct, 23 wrong; `pairs_plan.md`, committed before the pairs were built). 3 items had a field with no documented request representation or no applicable mutation and were removed; 2 were refilled from the reserve by plan.md's rule.*
  *2026-10-12 (Prompt W, ADR-102): **gate failed; the check stays advisory with `qa_interp_v2` (L-74 stands, L-92 opened). Not ticked.** The frozen pairs are not owner-written (ADR-094). The check also covers sentiment (ADR-090), so the gate ran on all three domains (23 correct, 23 wrong; reporting 10, forecast 7, sentiment 6 per role) and its cap was raised from 522 to 561 before any call. One revision, `qa_interp_v3` (`07ca35b`). Criteria restated as rates, strict rounding: at most 1 false reject of 23, at least 19 of 23 caught, all 3 runs. Run 1 (46 calls): 3 false rejects (a) FAIL, 19 caught (b) PASS; runs 2 and 3 not made, as pre-registered. Development diagnostic, not held-out: 3 false rejects on 7 decline pairs of the used set (the frozen gate has 1 decline pair, L-92).*
  *2026-10-13 (Sprint 5 close): attempted and failed; stays open.* The attempt ran on generated pairs, not an owner-written set (ADR-094), and failed on (a) (ADR-102). A further attempt needs a decline-heavy interpretation set first (L-92). Not carried as a planned Sprint 6 item: the owner decides whether it is.
- [x] Golden-set items about one region or one account may have a different correct answer after ADR-086: check them at the evaluation and make a `golden_v3` with disclosure if needed (do not open the golden set before then). *Added 2026-10-08.* The tie order for rate breakdowns changed too (L-72 ruling 2: worse rate, then the larger denominator, then the name), so a golden item that expects a particular group in the top 25 of a tied breakdown may differ. *Added 2026-10-09.*
  *2026-10-13 (Prompt X): **first `golden_v2` run, deployed system.** Mechanical score 29 of 36 (`evals/results/sprint5_x/golden_scoring.md`, fixed before the run); `must` / `must_not` are with the owner (`golden_owner_review.csv`). Stretch items: G02, G04, G10 pass the mechanical score; G05 fails (range). G35 fails as expected (L-58). The region, account and tie-order items (G04, G20, G21, G12, G13, G18) equal the oracle; **no expectation looks wrong for those reasons**, so no `golden_v3` is called for by them. Other failures: G03 ("district" read as an unsupported breakdown), G07 (period read as calendar 2027, 8 weeks shown), G08 (routed to forecast, declined there), G21 (p-value shown to 4 places; every other figure equal), G28 (`answered` with no weeks, item accepts `not_available`). Items whose expectation the owner may want to look at: G03, G07, G28 (`golden_assistant_reading.md`). Not ticked (Prompt Y).*
  *2026-10-13 (Sprint 5 close): checked, no `golden_v3` called for by these.* G04, G20, G21 (one region), G12 (one account) and the tie-order items G12, G13, G18 equal the oracle on the deployed system (`golden_assistant_reading.md`, check notes). A `golden_v3` is in the Sprint 6 backlog for a different reason: the G21 scorer comparison (L-95).
- [ ] An owner-written fresh set of region and account questions for the reporting parse (the `parse_v4` set was drafted by its prompt's author, L-69), used for any later prompt change. *Added 2026-10-08.*
  *2026-10-11: generated under ADR-094, not owner-written (drafts; the owner's skim comes first). Set: `parse_filters_v1` (optional, 12 filtered items).*
  *2026-10-11: frozen, commit `8ed47771fa084794fe663506ae489339f5db4459`: `parse_filters_v1`, 12 items (target 12), unchanged by the skim.*
  *2026-10-13 (Sprint 5 close): not used; unticked.* `parse_filters_v1` is frozen (12 items) but no reporting-parse prompt changed in Sprint 5, so nothing was measured on it. It was generated, not owner-written (ADR-094). It stays for any later parse prompt change.
- [x] Every routing eval reports k=3 runs: range and flipping items (L-17).
  *2026-10-13 (Sprint 5 close): done.* The FR-03 gate (ADR-101) and the held-out run (X) both ran k=3 and report range and flipping items (none flipped in X).
- [ ] FR-03 (ambiguous questions not force-routed) is open (L-58, ADR-075, ADR-076). Any
  reattempt needs a new owner-written fresh set: `fr03_fresh_v1` has now been used to
  judge `route_v5` and can't confirm a revision made after seeing its results.
  *Added 2026-10-04.*
  *2026-10-11: generated under ADR-094, not owner-written (drafts; the owner's skim comes first). Set: `fr03_fresh_v2`.*
  *2026-10-11: frozen, commit `8ed47771fa084794fe663506ae489339f5db4459`: `fr03_fresh_v2`, 16 items (target 16), 2 owner drops at the skim replaced from skimmed-Y reserve ambiguous items.*
  *2026-10-12 (Prompt W, ADR-101): **gate failed on (c); FR-03 stays open (L-58). Not ticked.** One revision, `route_v6` (`031426b`, written from used development material only, example-overlap test), run once on the frozen `fr03_fresh_v2` (8 ambiguous, 8 not; k=3 each for `route_v6` and `route_v3`; pre-registered at `458f105`, 2026-10-12 16:24 CDT, before the first gate call). (a) PASS (0 non-ambiguous routed `ambiguous`), (b1) PASS (43.00 against a floor of 42.00), (b2) PASS at the boundary (7.00 against 7.00), (c) **FAIL: 4 of 8** recognised in at least 2 of 3 runs (needed 6; AMB-08, AMB-11, AMB-17, AMB-18 missed in 3 of 3). `route_v3` stays the default; no further attempts in Sprint 5. 288 calls in all (A1 192, C1 96).*
  *Academic note for `05` (2026-10-12): FR-03 is still not met in the running system: on 8 fresh ambiguous questions the best revision (`route_v6`) recognised 4 and failed the pre-registered floor of 6, and the default router (`route_v3`) recognised 0 of 8; this is the same known-failing scenario as the `05` draft, with new evidence (ADR-101), not a change.*
  *2026-10-13 (Sprint 5 close): attempted, failed, stays open.* `route_v6` failed (c), 4 of 8 against 6 (ADR-101). On the held-out set the 7 ambiguous items are wrong in all 21 item-runs under `route_v3`; golden G35 fails as predicted (L-58).
- [ ] Rating cross-check sensitivity: flip a few percent of ratings to mimic real-world rating/text disagreement; report the QA catch rate with and without (L-24).
  *2026-10-10 (owner correction): still open. This item flips **ratings** (real-world rating/text disagreement with a correct classifier) and tests **false alarms** on correct answers, that is, whether the p0 = 1% floor is enough. The fault injection (ADR-091, K05 to K80) flipped **predictions** (classifier errors) and tested the **catch** side only: contradictions at 0.5, 1, 2, 4 and 8% of the covered set were caught 0/10, 0/10, 1/10, 8/10 and 10/10, matching the pre-registered rule in all 50 cases. That is evidence for the catch side; it says nothing about false alarms when the classifier is right and the ratings disagree.*
  *2026-10-13 (Sprint 5 close): not done; unticked, not carried as a planned item.* The false-alarm side (L-24) stays unmeasured; the owner decides whether it goes to Sprint 6.
- [ ] QA model comparison (Flash-Lite vs `gemini-3.1-pro-preview`): optional, buffer only (ADR-056).
  *2026-10-13 (Sprint 5 close): not done.* Optional, buffer only (ADR-056). Left.
- [x] FastAPI gateway + thin React UI
  *2026-10-13 (Sprint 5 close): done and deployed.* PR #46 (ADR-097); the gateway runs as `ops-gateway-00001-8st`, one of the six services (`sprint5_x.md`). Access is by invite link, not IAP (ADR-097).
  - [x] Pin Next.js to the current patched release at build time (security release scheduled 2026-09-30); verify the version then.
    *Source: https://nextjs.org/blog/tag/security. As of 2026-09-30 the patched releases are 16.3.8 (Active LTS) and 15.5.27 (Maintenance LTS).*
    *2026-10-12: built locally (branch `feat/gateway-ui`, PR open, not merged; nothing deployed, no GCP change). `services/api_gateway` (FastAPI: invite-link sign-in, session cookie, limits, `/api/ask` in front of the orchestrator, the static export at `/`), `web/` (a Next.js static export, one screen), `scripts/invites.py`, and a `gateway` compose service on 127.0.0.1:8080. Access control is ADR-097; the display rules are data dictionary §6, "Answer display (UI)". The orchestrator's `/ask` gains `parsed_request` for a decline (validated; no answer changes). Local smoke: three questions verified with the right "Interpreted as:" line; revocation and the logging check passed; the degraded path did not behave as expected (L-89).*
    *2026-10-12: **Next.js pinned to 16.3.8** (exact; `web/scripts/check-next-version.mjs` fails the build below it; `npm audit --omit=dev`: 0 vulnerabilities). Source and date read: the 2026-10-12 read of the GitHub Security Advisories API for vercel/next.js (GHSA-h694-7cp9-m8p3, patched 16.3.8; most of the 2026-09-30 advisories list their patched version only as `16.3.?`), the npm registry (16.3.8 published 2026-09-30; 15.5.27 the Maintenance backport; 16.4.0 published 2026-10-06, `latest`) and the nextjs.org blog index. The tag URL in the prompt, https://nextjs.org/blog/tag/security, returned 404 (Next.js moved it). 16.4.0 is not pinned: no advisory confirms its patch status. **Next.js announced an out-of-band security update for 2026-10-14** (two Critical and one High, in upstream dependencies; versions not yet published): Prompts U and V must re-read the advisories and raise `MIN_NEXT` before the deploy. A static export does not run Next.js's server code, so these do not apply to the deployed gateway (ADR-080); the pin stays anyway.*
    *2026-10-12 (Prompt U): corrected source. The tag URL above (`https://nextjs.org/blog/tag/security`) is dead (404 on 2026-10-12, Next.js moved it) and is not to be used. The sources actually used are the GitHub Security Advisories API for `vercel/next.js` (`https://api.github.com/repos/vercel/next.js/security-advisories`) and the npm registry (`npm view next dist-tags`). The out-of-band release announced for 2026-10-14 is not out yet: the runbook's pre-flight checks both at the window and bumps the pin only if an advisory confirms the patched version, else deploys 16.3.8.*
    *2026-10-12 (against the Sprint 5 plan): **Identity-Aware Proxy was replaced by invite-link access** (ADR-097). IAP was never recorded in an ADR; the grader's Northwestern address is on Microsoft 365, so a Google identity may not be available. Cost: the authentication code is ours (L-88).*
    *2026-10-12 (browser check, no model call): the gateway image and a headless Chromium (Playwright 1.55, Chromium 140) over the real export: a fresh invite link signs in, the fragment is cleared, the `__Host-session` cookie is `Secure`, `HttpOnly`, `SameSite=Strict` on `http://127.0.0.1`, a reload keeps the session, sign-out works, the 404 page renders, no horizontal scroll at 390 px, zero CSP violations; the inline scripts of `/` and `/404.html` are all in the served policy (no `unsafe-inline`). The first run found that a link opened in an already-loaded tab was not read (a same-document hash change); the page now also reads the fragment on `hashchange`. `/api/ask` was not used there; the answer strings were checked through the API.*
  *2026-10-13 (Sprint 5 close): pinned to 16.3.8 on 2026-10-12 (see above).* The out-of-band release announced for 2026-10-14 is a Sprint 6 gateway-only redeploy (backlog); a static export does not run Next.js's server code (ADR-080).
- [x] Extend deployment to all services; complete Cloud SQL migration
  *2026-10-12 (Prompt U, deploy readiness; local only, nothing deployed, no GCP change): ready except the sentiment service. ADR-098 (the `volume_v2` files baked into the forecast and QA images, 171-forecast clean check 0 mismatches) and ADR-099 (the six service definitions, `deploy/plan_full.py`, the connection arithmetic 46 of 60, `cloudbuild.yaml` and `deploy/trigger_full.yaml` extended to six services). The runbook is `deploy/RUNBOOK_V.md` (13 steps, about 3 h 55 min). **Blocked on the owner: `ops-sentiment`** (R-19, L-90), whose image cannot start without the 438 MB weights; it is skipped by `_DEPLOY_SENTIMENT=false`. The pricing pages could not be read, so the costs are estimates. The client-IP rule for Cloud Run is a documented gap (note under ADR-097).*
  *2026-10-12 (Prompt U2, ADR-100; local only, nothing deployed, no GCP change): **sentiment unblocked.** The owner chose option B: deployed sentiment reads stored, offline-scored predictions and the classifier is out of the request path (`MCP_FEEDBACK_SCORING=stored_only`; the `stored` image target has no torch and no weights; a gap in the stored predictions fails closed with `predictions_incomplete`). `_DEPLOY_SENTIMENT` is `true` and `ops-sentiment` deploys with the other five; its `mcp-feedback` container is 512 Mi (measured peak 96 MiB after 20 queries in the built image). R-19's blocker is removed; L-90 is resolved for serving and L-91 records what replaces it. The runbook is split into two sittings (Thu 10-15 about 1.5 h; Fri 10-16 about 2.5 h) and deploys one service at a time (R-20). Branch `feat/sentiment-stored-only`, PR open, not merged.*
  *2026-10-13 (Sprint 5 close): done.* Six services deployed on frozen images tagged `9607fa72` (revisions `ops-forecast-00002-m79`, `ops-gateway-00001-8st`, `ops-orchestrator-00006-bvj`, `ops-qa-00003-hwq`, `ops-reporting-00006-md5`, `ops-sentiment-00002-cxz`; identical at the start and end of the X run). Cloud SQL: the eight tables the oracles read equal the local database in row counts and in per-table and per-column hashes, `sentiment_predictions` included (`evals/results/sprint5_x/data_parity_{local,cloud}.json`). `verify.py` 11 of 11 (3 paid calls, about $0.0015) and the per-step record are in `docs/deploy-window-log.md` (2026-10-12/13).
- [ ] Re-enable the build trigger `deploy-reporting-slice` (disabled 2026-10-08, ADR-083) when the deploy is extended; the command is in `deploy/README.md`.
  *2026-10-12 (Prompt U): `deploy/trigger_full.yaml` (disabled; filters and substitutions for six services, `web/**`, the baked manifests and parameter files included; docs, READMEs and the runbook ignored; prompts still trigger). Apply and enable commands are in `deploy/RUNBOOK_V.md`, steps 5a and 8. The filter is tested offline (`tests/unit/test_deploy_trigger.py`).*
  *2026-10-13 (Sprint 5 close): not done, by decision.* The trigger `deploy-reporting-slice` stays disabled outside deploy windows (ADR-105). Enabling it and the docs-only merge check are Sprint 6 backlog items.
- [x] Backfill `sentiment_predictions` on Cloud SQL before the sentiment service deploys (`test_golden_oracles` skips without stored predictions; the load truncates them).
  *2026-10-12 (Prompt U): plan and check ready, not run. The backfill re-scores 7,521 comments with the local weights through `cloud-sql-proxy` as `app_sentiment` (about 15 min; it is not a row copy). `scripts/predictions_fingerprint.py` prints the count and a content hash (no timestamps); recorded locally: 7,521 rows, SHA-256 `a340b82d8af178173afae34cb17bb7f2a1e3a944baa879321f34c4ac137e259f`. It unblocks `test_golden_oracles` (sentiment oracle), `test_qa_baseline` and `test_qa_sentiment_agrees`. Commands: `deploy/RUNBOOK_V.md`, step 4. The sentiment service itself is blocked on R-19.*
  *2026-10-13 (Sprint 5 close): done.* `sentiment_predictions` on Cloud SQL matches the local table in rows and hashes (`data_parity_cloud.json`), and the deployed sentiment service answered G04, G20, G21 and G22 on stored predictions. The backfill fingerprint (7,521 rows, `a340b82d…e259f`, an exact match to local, twice) is in `docs/deploy-window-log.md` (2026-10-12/13).
- [x] Verify revision promotion immediately after deploy (known failure mode from a prior project — see risk register)
  *2026-10-13 (Sprint 5 close): done.* Traffic verified at 100% on every service (step 5e and the serving-revisions check after the paid-key switch, `docs/deploy-window-log.md` (2026-10-12/13)), and the six revisions were identical at the start and end of the X run (`sprint5_x.md`). R-03 closed.
- [ ] Trace ID in web-server access logs (carried from Sprint 4, 2026-10-10): an access-log middleware in all seven servers and a trace-ID header on the A2A and MCP clients, with its own short ADR when built. Sprint 6 observability depends on it. *Source: the Sprint 4 backlog item of 2026-10-08.*
  *2026-10-13 (Sprint 5 close): not done; carried to Sprint 6.* Nothing changed after the freeze (ADR-103). Sprint 6 observability depends on it.
- [x] Decision: build or not an answer-time check that every served forecast number equals the model's own prediction, re-implemented in QA from the manifest's stored coefficients (L-83(a); a check against the model, not a prediction, so consistent with ADR-055). The owner leans towards building it, as the condition for "QA verifies forecasts" meaning more than arithmetic. *Source: ADR-092, L-83.*
  *2026-10-11: built (ADR-095, branch `feat/qa-forecast-recompute`, PR open, not merged). QA recomputes the weekly point, the 80% range and the period total from the `volume_v2` parameter files in pure Python. Measurement 3: owner fault 2 caught 6 of 6 (0 of 6 before), 223 of 223 overall, 0 false alarms on 171 unmodified forecasts, no regression; consistent misparses still 0 of 71. Evidence the fix works, not a catch rate (ADR-092, L-85). Unchecked: the 95% ends and a total interval (L-87); L-83(b) remains offline. Deployment of QA needs the parameter files mounted.*
  *Academic note for `05` and `06` (2026-10-11): "QA now recomputes forecast numbers independently" from the stored model parameters and requires an exact match after display rounding. Measurement 3 (6 of 6 on the owner's holiday-weeks fault, 223 of 223 overall) is evidence the fix works on the case it was designed from, not a new catch rate; the faults are drafted by the assistant that built QA. It does not catch a model that misses a holiday (judged offline) or a misparse (R-18, the interpretation check stays advisory).*
  *2026-10-13 (Sprint 5 close): built and deployed.* ADR-095, ADR-096; QA recomputes served forecast numbers from the baked parameter files (ADR-098) on the deployed `ops-qa`.
- [x] Schedule owner writing time for three sets: the held-out routing set (above), a fresh FR-03 set and a fresh interpretation set. *Source: the Sprint 4 retro, change 4.*
  *2026-10-11: generated under ADR-094, not owner-written (drafts; the owner's skim comes first). The sets were written by an independent model instead (capacity), so no owner writing time is needed for them; the skim is the owner's part.*
  *2026-10-11: owner approved the brief's design and ruled on the one policy difference before generation; owner read `brief_v2.md` in full after generation and before the skim.*
  *2026-10-11: owner drops at the skim were made on persona grounds: a question a dispatcher or call-centre agent would ask, but not a senior operations leader with an overview of the business unit (the brief's stated asker). Labels were not changed. The owner hadn't seen any system output for these items. Selection effect to disclose: persona drops may remove the more granular, operational questions, which leaves sets weighted toward broad leadership questions. Prompt Y's failure analysis reports the drop count.*
  *2026-10-13 (Sprint 5 close): closed by ADR-094.* The three sets were generated; the owner's part was the brief review and the skim.
- [ ] Option: owner-written faults added to QA's fault catalogue and reported apart from the assistant-drafted ones (L-85). *Source: ADR-091, ADR-092.*
  - *2026-10-10 (Sprint 4 close): the re-enabled trigger excludes `**/*.md`, so a docs-only merge deploys nothing. Source: the Sprint 4 close.*
  *2026-10-13 (Sprint 5 close): dropped.* ADR-094 dropped it for the same capacity reason as the owner-written sets; recorded here as that ADR said it would be.

**Close (2026-10-13, day 2 of a sprint planned as 2026-10-12 to 10-25; owner-endorsed, assistant-drafted).**
**Goal: met, with stated limits.** "A deployed system with a working UI; routing accuracy reported with failure analysis." The system is deployed (six services, a gateway with invite-link access and an "Interpreted as:" line) and routing accuracy is reported with a failure analysis. The limits:
- **FR-03 is open.** `route_v6` failed its gate (4 of 8 against 6, ADR-101); `route_v3` stays and ambiguous questions are best-fit routed (L-58).
- **The interpretation check is advisory.** `qa_interp_v3` failed (a), 3 false rejects against at most 1 (ADR-102); misparses are not caught by QA (L-74, L-92; R-18).
- **The golden owner-item gap.** Owner-written items score lower than drafted ones: mechanical 6 of 10 against 23 of 26, owner judgement 7 of 10 against 24 of 26 (L-54). Ten items is too few to size it.

**Figures (the one page is `evals/results/sprint5_summary.md`; the analysis is `evals/results/sprint5_failure_analysis.md`):**
- **Held-out routing (`routing_heldout_v1`, k=3):** 38, 38, 38 of 50, no flipping items; 38 of 43 without the 7 ambiguous items (labelled as such). 21 ambiguous-not-flagged and 15 out-of-scope-accepted item-runs, nothing else wrong.
- **Golden (`golden_v2`):** **29 of 36 mechanical (pre-registered) and 31 of 36 on the owner's judgement, reported side by side; neither replaces the other.** The owner's N marks: G03, G05, G07, G27, G35. G21 is "30/36 if compared at display precision. A correction made after seeing results; not the pre-registered score" (L-95). G35 fails as predicted (L-58).
- **The gates (W):** FR-03 failed (c), 4 of 8 against 6; interpretation failed (a), 3 false rejects against 1; `qa_interp_v3` not shipped despite better development numbers (pre-registration held).
- **QA (S):** measurement 3 is 223 of 223, owner fault 2 caught 6 of 6: "evidence the fix works, not a catch rate" (ADR-092, L-85).
- **Deploy:** six services, frozen images `9607fa72`, paid key (ADR-104). Per `docs/deploy-window-log.md` (2026-10-12/13): `verify.py` 11 of 11; the cold-start question 55.87 s in the browser (54.47 s at the gateway) against 120 s. X latency: per-run median about 3.7 s, p95 at most 17.6 s.

**The schedule:** closed 2026-10-13, against the plan's 2026-10-25 (ADR-093): 12 days returned to the buffer. The buffer is 2026-11-09 to 12-05; scope expansion is decided at this close under the working agreement; this record proposes none, and the owner decides. The open gaps are quality gaps (FR-03, the interpretation check, the decline-heavy gate), not missing capacity. The divergence from ADR-093's calendar is on the post-submission list below.

**Cost:** paid key spend this sprint, list-price estimates (L-71): Q about $0.16 (owner-reported in the Prompt Y brief) and V3 about $0.0015 (3 paid `verify.py` calls, `docs/deploy-window-log.md` (2026-10-12/13)), W $0.2719 (`evals/results/sprint5_w_ledger.json`), X $0.1727 (`sprint5_x_ledger.json`), plus the smoke questions (not itemised). The prepaid balance is about $2.9 after X (owner-reported, an estimate; R-02). GCP spend for the window: not provided at the close; the owner adds it from Billing.

**Shipped (PRs #43 to #51, 2026-10-11 to 10-13, and the deploy window of 2026-10-13):**
- *The evaluation sets:* #43 generation (ADR-094) and #44 the freeze (`routing_heldout_v1`, `fr03_fresh_v2`, `interp_fresh_v1`, `interp_pairs_v1`, `parse_filters_v1`).
- *QA forecast recompute:* #45 (ADR-095, ADR-096).
- *The gateway and UI:* #46 (ADR-097), Next.js pinned to 16.3.8.
- *Deploy readiness:* #47 the full-system deploy configuration and parameter files (ADR-098, ADR-099); #48 sentiment from stored predictions only (ADR-100).
- *The gates and the freeze:* #49 `route_v6` and `qa_interp_v3` gate results (ADR-101, ADR-102), the evaluation freeze (ADR-103).
- *The paid key:* #50 (ADR-104, L-93).
- *The blind runs:* #51 held-out routing and golden (Prompt X; L-94, L-95).
- *The deploy:* six services on Cloud Run, one at a time, on the frozen images.
- *This close:* the results summary, the failure analysis, ADR-105, the risk review (R-21 added) and these records.

**Carried over or dropped (each with its reason in the item's dated note above):**
- Carried to Sprint 6: the Cloud SQL real-data QA suites (L-78), the trace ID in access logs, enabling the trigger, and the post-freeze fixes listed under Sprint 6.
- Attempted and still open: FR-03; the interpretation gate (needs a decline-heavy set, L-92).
- Not done and not carried as planned items: rating cross-check sensitivity, QA model comparison (optional), the owner-written parse set (the generated `parse_filters_v1` is unused).
- Dropped: owner-written QA faults (ADR-094).
- **`ops-db` stop (ADR-105):** the decision is recorded. The stop command was **not** run in this session: the permission classifier denied it, and it was not retried. The instance read `RUNNABLE ALWAYS` on 2026-10-13 before the attempt. The owner runs the command (in ADR-105) and the state is confirmed as `STOPPED NEVER`.

**Blockers encountered:** factual; the first four are recorded in `docs/deploy-window-log.md` (2026-10-12/13):
- The free tier returned `504 DEADLINE_EXCEEDED` on 2026-10-13 (ADR-104, R-15).
- An unquoted comma list in `--update-env-vars` broke the value; the fail-fast config caught it.
- Cloud Run's front end reserves `/healthz`; the public health route has to be renamed.
- `deploy/plan_full.py` needs `shell=True` on Windows.

**Retro (owner-endorsed, assistant-drafted, 2026-10-13):**
- What went well:
  1. **State checks caught wrong prompt assumptions before damage, five times:** the interpretation-check scope (it covers sentiment too, ADR-102), the response cost fields (L-94), `/healthz`, the deny rules and `plan_full.py`.
  2. **Pre-registration held under a tempting result.** `qa_interp_v3` had better development numbers and was not shipped after it failed the gate (ADR-102).
  3. **The fail-fast config caught the comma bug** before a service ran with a split value.
  4. **Honest degraded results under the free-tier outage** (R-15, ADR-104).
- What went badly:
  1. **The prompt author's assumptions about the environment:** Windows PowerShell 5.1, the Cloud Run reserved path, the response fields.
  2. **Spec-first missed once** (Prompt U; ADR-098 states the order it was written in).
  3. **Budget caps are per process** (L-93): the caps in the services were not a ceiling.
  4. **The runbook lacked commands that work as written** (the Sprint 6 backlog lists the fixes).
- What changes next sprint:
  1. **Example commands in prompts are written for Windows PowerShell 5.1 and quoted.**
  2. **A prompt that depends on a response field or a path names where it was verified.**
  3. **Budget enforcement lives in a harness ledger, never in per-process caps.**
  4. **No "don't ask again" during deploy windows.** Narrow deny rules stay permanently.

**Academic deliverable status:**
- `05-test-scenarios.md` (due 2026-11-01) and `06-production-support.md` (due 2026-11-08) are the owner's and were not edited. What they will need to reflect:
  - **`05` (due 11-01), wording changes:**
    - FR-03: still not met in the running system; on the held-out set, 0 of 21 ambiguous item-runs recognised under `route_v3`, and the best revision recognised 4 of 8 against a floor of 6 (ADR-101).
    - The interpretation check is advisory (ADR-102, L-92); "verified" means the figures are correct for the request as interpreted.
    - The held-out figures (38, 38, 38 of 50; 38 of 43 without the ambiguous items) with their disclosure: the sets were generated, not owner-written (ADR-094), and the persona-drop selection effect (L-86).
    - Deployed, with invite-link access (ADR-097) and "Interpreted as:" shown with every answer.
    - Model calls on the paid key (ADR-104, ADR-105); the system is available in announced windows.
    - The golden figure as two numbers: 29 of 36 mechanical and 31 of 36 owner judgement.
  - **`06` (due 11-08), deploy-window material:** the free-tier outage and its diagnosis (one call per key, ADR-104); the comma-quoting failure caught by the fail-fast config; `/healthz` reserved by Cloud Run; `plan_full.py` on Windows; sequential deploys (R-20); the stored-predictions design (ADR-100, L-91).
- Weekly status report due (maintained by Eric) — the last report covers the week ending 2026-11-22
  *2026-10-13, post-submission divergence list (carry to the evaluation report; nothing in a submitted document was edited):*
  - *`04`'s three sentiment lines differ from the built system (ADR-100: deployed sentiment reads stored predictions only).*
  - *The ADR-093 calendar: Sprint 5 closed on 2026-10-13, 12 days before 2026-10-25, so the Sprint 5 window and the buffer start differ from `03` and ADR-093 again.*
  - *Identity-Aware Proxy was replaced by invite-link access (ADR-097).*

**Decisions made this sprint:**
- ADR-094 — Evaluation sets are written by an independent model (2026-10-11)
- ADR-095 — QA recomputes served forecast numbers independently (2026-10-11)
- ADR-096 — QA also checks the 95% interval ends (2026-10-12; supersedes ADR-095 in part)
- ADR-097 — Invite-link access to the gateway (2026-10-12)
- ADR-098 — The `volume_v2` parameter files are baked into the forecast and QA images (2026-10-12)
- ADR-099 — Deploy configuration for the full system (2026-10-12)
- ADR-100 — Deployed sentiment reads stored predictions only (2026-10-12)
- ADR-101 — The FR-03 gate on `fr03_fresh_v2`: `route_v6` failed (c) (2026-10-12)
- ADR-102 — The interpretation gate: `qa_interp_v3` failed (a) (2026-10-12)
- ADR-103 — Evaluation freeze for Sprint 5 (2026-10-12)
- ADR-104 — Deployed model calls use the paid key for the evaluation and grading window (2026-10-13)
- ADR-105 — Grading availability: `ops-db` stopped by default, started for announced windows (2026-10-13)

### Sprint 5 close: records corrections, 2026-10-14 (Z1)

*Added 2026-10-14, after the Sprint 5 close. Source: the 2026-10-14 gap audit, each finding verified against the file and line it cites. Nothing above is edited; each item below is a dated correction citing both places. Owner-decided 2026-10-14 ("defaults"); assistant-drafted.*

**Decisions recorded:** ADR-106 (the Sprint 6.5 scope decision moves to the Sprint 6 close; supersedes ADR-093 in part) and ADR-107 (grading windows A, 2026-10-31 to 11-09, and B, 2026-12-01 to 12-12; the hourly cap to 30 in Z2). The window procedure is `deploy/RUNBOOK_GRADING.md`.

**Corrections:**
- **`05` status.** `05` is held, not submitted; it will be revised with Sprint 5 evidence before 11-01 (owner, D1). Its "Assignment complete" mark (`05:9`) dates from 2026-10-05. *Contradicts:* `05:9` against the Sprint 5 close's Academic deliverable status above, `architecture.md` §10 and ADR-093, which treat `05` as a Sprint 6 deliverable.
- **G04.** Two descriptions, both right about different things. L-56 (`evaluation-report.md`) describes the question: complaint themes since an app update, a stretch item. The Sprint 4 backlog note above and R-16 describe the deployed answer: a one-region sentiment item whose counts equal the oracle. From `evals/results/sprint5_x/golden_assistant_reading.md`: G04 passes mechanically; the answer is the region's sentiment counts, shares and range, with the range stated as assumed, verbatim quotes and no invented theme or app-update date; it does not say the qualifier was ignored (the stretch gap). The 6.5 candidate "G04 complaint themes" is right that theme extraction does not exist; G04 itself is answered, not declined. (R-16 carries the same line.)
- **The forecast-recompute decision item, ticked and unticked.** The Sprint 4 backlog's "Sprint 5 decision item (2026-10-10, owner; L-83 split in ADR-092): build or not an answer-time check..." is `[ ]`, and the Sprint 5 list's "Decision: build or not an answer-time check..." is `[x]`. They are one decision. **Real status: decided and built** (ADR-095, 2026-10-11), the 95% ends added (ADR-096), and deployed on `ops-qa` (2026-10-13). The `[ ]` copy is stale and is not edited.
- **`ops-db` stop.** `ops-db` stopped by the owner 2026-10-13 after the Sprint 5 close (STOPPED NEVER), per ADR-105; the time is not recorded (evening). A read-only `describe` on 2026-10-14 read `STOPPED NEVER`. This replaces the Sprint 5 close line "the stop command was not run in this session ... the owner runs the command".
- **Client IP.** The 2026-10-13 probe logged a `remoteIp` that was the caller's real address, which is consistent with the rule; the evidence is Cloud Run's logged `remoteIp` only, so it is **observed, not documented**. Recorded under L-88, as a note under ADR-097, and as an addendum to `docs/deploy-window-log.md`. *Contradicts:* L-88 and ADR-097 ("unverified") against the window log ("the rule holds"); both now say observed, not documented.
- **G21 and `golden_v3`.** A `golden_v3` scoring change needs a golden-run prompt with explicit permission to open `evals/golden/`; it is not a Z item. Owner decides in 6.5 (L-95). *Contradicts:* the Sprint 6 backlog's G21 item (a `golden_v3` for the scorer) against L-95 ("only if the owner wants expectations changed. Not done"); the backlog item is no longer a Sprint 6 task.
- **Buffer dates.** The Sprint 6 section's two closing notes disagree: "the buffer is 2026-11-09 to 12-05" (ADR-093, 2026-10-10) and "the buffer is 2026-11-23 to 12-05" (ADR-082, 2026-10-08, not marked superseded). **The log shows otherwise than the "Sprint 5 close to Sprint 6 start" reading:** both lines are the buffer after Sprint 6. ADR-093's later line stands: Sprint 6 runs 2026-10-26 to 11-08 and the buffer 2026-11-09 to 12-05; 11-23 is ADR-082's superseded date. Separately, the interval from the Sprint 5 close (2026-10-13) to the Sprint 6 start (2026-10-26) is unscheduled (the Sprint 5 close counts it as 12 days returned against ADR-093's 2026-10-25 end). Sprint 6.5, if any, is about 11-09 to 11-29 inside the buffer (ADR-106).
- **R-14.** Closed against its stated condition (the Sprint 5 deploy of every service); see the risk register.
- **Grader caps.** ADR-097 sized the caps for the owner's use; ADR-105 relies on graders. Resolved by ADR-107: hourly 15 to 30 in Z2, daily 50. (L-88 update.)
- **Freeze record.** `freeze_s5.json`'s `llm_mode_in_services: free` is superseded for deployed serving by ADR-104 (note under ADR-103); the freeze test does not check the data-dictionary hash (L-97). The record is not changed.
- **Scope-decision timing.** ADR-093, `architecture.md` §10 and R-10 said "at the Sprint 5 close"; the Sprint 5 close above says "this record proposes none, the owner decides"; the 6.5 note says "at or near the Sprint 6 close". Resolved by ADR-106: the Sprint 6 close.
- **Default compute service account holding Editor:** already backlogged (Sprint 6 Planned: "Review the default compute service account's project-level Editor role"). No new item.

**Notes for `05` (due 2026-11-01), the owner's revision checklist.** Every line below is from the audit, checked against the file on 2026-10-14. `05` is not edited by the assistant.
1. `05:9`, "(Assignment complete)": held, not submitted; revise with Sprint 5 evidence (ADR-106 keeps 6.5 out of it).
2. `05:102`, Test Approach: "free tier limited to 500 requests per day". The deployed key is paid (ADR-104). Re-verify the limit or reword as "paid key in deployment (ADR-104)" (R-11).
3. `05:120`, Test Environment table, sentiment classifier "Same artifact": the deployed service reads stored, offline-scored predictions and the classifier is out of the request path (ADR-100, `MCP_FEEDBACK_SCORING=stored_only`).
4. `05:147`, precondition 6, "either the free tier or the capped paid project": deployed on the paid key; the free key stays mounted for a revert (ADR-104).
5. `05:209`, `05:234-236`, Scenario Summary Table and status "as of October 5, 2026 ... 1 known failing, 9 not yet built, 10 not yet run": out of date; the QA agent and revision loop (ADR-089 to ADR-092), the gateway and UI (ADR-097) and the deployment (ADR-099, 2026-10-13) exist.
6. `05:221-224`, TS-09 to TS-12 "Not yet built": built; QA measured (223 of 223 after fixes, ADR-092).
7. `05:226`, `:228-230`, `:232`, TS-14, TS-16, TS-17, TS-18, TS-20 "Not yet built": deployed; they run in Window A (2026-10-31 to 11-09, ADR-107).
8. `05:238-240`, the definition of "Not yet built" lists the QA agent, loop, authentication, gateway, interface and deployment: all exist now.
9. `05:558`, Known Failures, FR-03: "five fresh ambiguous questions, recognized three". The record: held-out under `route_v3`, 0 of 21 ambiguous item-runs recognised; the best revision, `route_v6`, recognised 4 of 8 against a floor of 6 (ADR-101). FR-03 is **unmet**, described so in `05` and `06` (ADR-106).
10. `05:559` and `05:473`, TS-15-D: the router's `reason` and unredacted tracebacks in logs (L-60) are fixed in Z2, and TS-15-D also needs the trace ID on access-log lines (not built; Z2, own ADR). The case fails until Z2 ships.
11. `05:567`, "free-tier model whose limits and availability the project does not control": the deployed system is on the paid key (ADR-104); the availability point stands (R-15 realised on 2026-10-13).
12. The numbers to carry (Sprint 5 close above): held-out 38, 38, 38 of 50 (38 of 43 without the ambiguous items); golden 29 of 36 mechanical and 31 of 36 owner judgement, side by side (L-95); both sets generated, not owner-written (ADR-094, L-86).
13. How `05` reaches the deployed system: by invite, in a window (ADR-107, `RUNBOOK_GRADING.md`), with `ops-db` otherwise stopped (ADR-105).

**Notes for `06` (due 2026-11-08).** Stub; outline waits on the assignment text (owner to supply). Material: the deploy-window log, ADR-104, ADR-105, ADR-107, `RUNBOOK_GRADING.md`, L-88, L-89, R-21.

---

## Sprint 6 (2026-10-15 to 2026-10-25; re-baselined, ADR-109) — Hardening & delivery
*Planning note, 2026-10-15 (Owner-decided 2026-10-15; assistant-drafted.)* Sprint 6 runs 2026-10-15 to 10-25 (11 days) and the buffer is 10-26 to 12-05 (ADR-109, which supersedes ADR-093's Sprint 6 dates and ADR-106 in part). The goal below is unchanged, and its "demo rehearsed" is **not expected inside Sprint 6**: it falls in the buffer. Buffer targets: evaluation report draft (Sprint 5 results plus the divergence list) by 11-08, final by 12-01; presentation draft by 11-22; demo rehearsal by 11-29. `05` (due 11-01) and `06` (due 11-08) keep the course's dates; submitting them is owner work in the buffer if not done by 10-25. No 6.5 change is deployed before `06` is submitted. Owner verification sessions outside the windows are allowed (ADR-110).
**Goal (increment):** Production-grade checklist closed out; demo rehearsed.
*2026-10-18 (S6-C1; owner-decided 2026-10-18; assistant-drafted.)* **Closed 2026-10-18, day 4 of the 10-15 to 10-25 sprint (ADR-113). Goal verdict: partly met.**
- **Checklist half: audited item by item, not closed out.** `docs/production-grade-audit.md` gave verdicts; in `architecture.md` §7, 8 of the 12 boxes are ticked (1, 2, 3, 7, 8, 10, 11, 12). By the audit's verdicts, items 5 and 6 are Met, offline only, and stay unticked; items 4 and 9 are Partly met. The four unticked items need a redeploy or a live fault: item 4 (F1, F2: probes), item 9 (F13: a pipeline run), item 5 (retry and breaker behaviour, never run on Cloud Run) and item 6 (a specialist-unavailable path, not run on the current build). Items 4 and 9 are in ADR-113's hardening bundle; items 5 and 6 are covered only by its "if the window allows" live degraded path.
- **Demo half: not done, by plan.** "Demo rehearsed" was placed in the buffer at planning (ADR-109); the target is 11-29.
- "8 of 12" counts ticked boxes, not "Met": two unticked items are Met offline only.

**Planned:**
- [ ] Observability, CI/CD completion, graceful degradation, load/latency testing (latency for a handful of concurrent users; no throughput target)
- [ ] Option: when a sentiment question asks for example comments without a label, quote one comment per leading label, or the trend's label for a trend question, instead of the top three by confidence (which skew to the majority label, usually positive, L-80); change §6 rule 7 and QA's check together. *Added 2026-10-09.*
- [ ] Option: store the unrounded confidence in `sentiment_predictions` (a new column or a wider type, with its migration and a backfill), so the flag check can be exact instead of banded at 0.00005 (L-77). *Added 2026-10-09.*
- [x] A log-based alert on `outcome=degraded`: a degraded answer is HTTP 200, so Cloud Run's error metrics never count it (ADR-088, ADR-089).
  - *2026-10-16 (S6-A1; owner-decided 2026-10-16; assistant-drafted.)* The specification is ADR-112, tested with a synthetic entry. Part A is built on branch `feat/degraded-alert`: the metric and policy files (`ops/monitoring/`), `scripts/alert_degraded.py` and its offline tests. **Stays unticked until Part B's live test passes.** The filter is on the orchestrator's `ask degraded` line, not on `outcome` (no such field on that line; ADR-112).
  - *2026-10-16 (S6-A2; owner present; assistant-drafted.)* **Ticked: Part B passed.** The metric and policy are applied; the synthetic entry (`alerttest-70b1b5266e5d4a2a`, 22:22:48Z) read back, was counted by the metric within about 1 to 1.5 minutes, opened an incident within about 3 minutes, and the owner received the email at 5:26 PM CDT. Record: `docs/deploy-window-log.md` (2026-10-16 entry) and the result note under ADR-112. The incident's close time is owner-reported with one open inconsistency (see that entry); it does not affect the tick. The metric read-back reported a false FAIL (label order, default `valueType`), tracked in the next item.
- [ ] **Fix `scripts/alert_degraded.py`'s metric read-back:** compare the labels by `key` (not by position) and treat a missing `valueType` as `STRING`, with an offline test for both. Also print a UTC timestamp on each poll line in the `test` subcommand, so stage timings are measured, not estimated. Separate PR, no GCP. *Added 2026-10-16 (S6-A2; owner-decided 2026-10-16; assistant-drafted.) Source: `docs/deploy-window-log.md` (2026-10-16 entry).*
- [ ] Terraform: buffer-only stretch goal, portfolio value (ADR-061).
- [ ] A separate `verify-caller` service account holding the orchestrator invoker, so building and calling are separate identities (ADR-085).
- [ ] Deploy with no traffic, verify the revision's own URL, then move traffic, so a failed verification never serves (L-64).
- [ ] Review the default compute service account's project-level Editor role (nothing in this deploy runs as it).
- [x] Production-grade checklist (`architecture.md` §7) audited item by item
  - *2026-10-16 (S6-P1; owner-decided 2026-10-16; assistant-drafted.)* **Ticked: audited.** `docs/production-grade-audit.md` (criteria committed before the evidence, then evidence, verdicts, the fresh-clone record and the deployed-state appendix). Verdicts: Met, deployed: items 1, 2, 3, 11. Met, offline only: 5, 6, 7, 8, 10. Partly met: 4, 9. Not met: 12. In `architecture.md` §7, items 1, 2, 3, 7, 8, 11 are now ticked (10 was) and items 4, 5, 6, 9, 12 are unticked with a dated reason each. Item 11 was first read as Partly met and moved to Met, deployed the same day on the owner's console readings (F8 below); item 7's tick stands on the owner's ruling that CI skips are allowed for the L-78 suites. The audit made no model call, no GCP write, no `ops-db` start and no code change. Actionable findings are the Planned items at the end of this list, dated 2026-10-16 (S6-P1).
- [ ] Evaluation report (`docs/evaluation-report.md`), presentation, demo rehearsal (ADR-044)
- [ ] Batch-scoring job for new comments (Cloud Run Job, weights from a bucket, ingest-time scoring, coverage disclosure). Portfolio value, not required at this scale (ADR-100). *Added 2026-10-12.*
- [x] `deploy/plan_full.py` lacks `shell=True` for Windows (deploy window). *Added 2026-10-13 (Sprint 5 close; Prompt Z). Source: `docs/deploy-window-log.md` (2026-10-12/13) and the Sprint 5 close (Prompt Y brief, section 6).*
- [x] Runbook (`deploy/RUNBOOK_V.md`) fixes, each from the window: step 3 needs `--skip-deploy`; step 5e should check the tag at the template; steps 5f and 5f-2 should read the Cloud SQL annotation; step 7 needs `POSTGRES_ADMIN_*`; quote the comma lists in `--update-env-vars`; add Windows PowerShell 5.1 notes. *Added 2026-10-13 (Sprint 5 close; Prompt Z). Source: `docs/deploy-window-log.md` (2026-10-12/13) and the Sprint 5 close (Prompt Y brief, section 6).*
- [x] Rename the public `/healthz` route (Cloud Run's front end reserves it), and replace the runbook's step 12 loop. *Added 2026-10-13 (Sprint 5 close; Prompt Z). Source: `docs/deploy-window-log.md` (2026-10-12/13) and the Sprint 5 close (Prompt Y brief, section 6).*
- [ ] Log the error class and status of each retried LLM call (L-93's neighbour; found diagnosing the 504s, ADR-104). *Added 2026-10-13 (Sprint 5 close; Prompt Z). Source: `docs/deploy-window-log.md` (2026-10-12/13) and the Sprint 5 close (Prompt Y brief, section 6).*
- [x] Sync `deploy/cloudrun/*.yaml` to paid mode: the repo says `LLM_MODE: free` and the deployed configuration is paid (ADR-104's drift note). *Added 2026-10-13 (Sprint 5 close; Prompt Z). Source: `docs/deploy-window-log.md` (2026-10-12/13) and the Sprint 5 close (Prompt Y brief, section 6).*
- [x] The Next.js bump for the 2026-10-14 release, as a gateway-only redeploy (ADR-080; the pin is 16.3.8). *Added 2026-10-13 (Sprint 5 close; Prompt Z). Source: `docs/deploy-window-log.md` (2026-10-12/13) and the Sprint 5 close (Prompt Y brief, section 6).*
- [ ] Runbook step 7: a scoped L-78 run on Cloud SQL, with a reviewed credential plan (also the first Sprint 5 item above). *Added 2026-10-13 (Sprint 5 close; Prompt Z). Source: `docs/deploy-window-log.md` (2026-10-12/13) and the Sprint 5 close (Prompt Y brief, section 6).*
- [x] Runbook step 8: enable the build trigger, and add the docs-only merge check (ADR-105 keeps it disabled outside windows). *Added 2026-10-13 (Sprint 5 close; Prompt Z). Source: `docs/deploy-window-log.md` (2026-10-12/13) and the Sprint 5 close (Prompt Y brief, section 6).*
  - *2026-10-15 (Owner-decided 2026-10-15; assistant-drafted.) Ticked.* The docs-only merge did not build: PR #58 (`82501b0`: `deploy/RUNBOOK_V.md`, `deploy/RUNBOOK_GRADING.md` and three files under `docs/`) merged about 22:26 CDT on 2026-10-14 with the trigger enabled, and read-only `gcloud builds list` at 22:27, 22:30 and 22:33 showed the latest build still `0dc5aae1…`. The ignore list gained `deploy/**/*.md` in PR #57 (`9ab7c77`). Source: `docs/deploy-window-log.md`, Z2b addendum (2026-10-14).
- [x] Extend `deploy/verify.py` to the four services it does not cover (forecast, QA, sentiment and gateway). *Added 2026-10-13 (Sprint 5 close; Prompt Z). Source: `docs/deploy-window-log.md` (2026-10-12/13) and the Sprint 5 close (Prompt Y brief, section 6).*
- [ ] **G21:** a scorer comparison at display precision, as a `golden_v3` scoring change, with disclosure (L-95). The pre-registered 29 of 36 is not changed retroactively. *Added 2026-10-13 (Sprint 5 close; Prompt Z). Source: `docs/deploy-window-log.md` (2026-10-12/13) and the Sprint 5 close (Prompt Y brief, section 6).*
- [x] The runbook's step 12 second idle wait (the cold-start measurement's second leg, R-05). *Added 2026-10-13 (Sprint 5 close; Prompt Z). Source: `docs/deploy-window-log.md` (2026-10-12/13) and the Sprint 5 close (Prompt Y brief, section 6).*
  - *2026-10-18 (S6-C1, owner rulings; owner-decided 2026-10-18; assistant-drafted.)* Ticked. The second idle wait was measured in owner verification session 1: sentiment 30.64 s with all four hops cold (`evals/results/session1/2026-10-15/summary.md`; R-05).
- [ ] **The orchestrator response:** consider exposing `cost_usd` and `model_calls` in `AskResponse` (L-94; deviation 1 in `sprint5_x.md`). A redeploy, so after any freeze. *Added 2026-10-13 (Sprint 5 close; Prompt Z). Source: `docs/deploy-window-log.md` (2026-10-12/13) and the Sprint 5 close (Prompt Y brief, section 6).*

- [x] **Z2: the trace ID in web-server access-log lines**, with its own ADR (carried from Sprint 4: the `[ ]` item of 2026-10-08 and the Sprint 5 item above; `security-model.md` §5). Sprint 6 observability and `05`'s TS-15-D depend on it. *Added 2026-10-14 (Z1). Source: audit, section 1; the Sprint 5 close.*
- [x] **Z2: the L-60 redaction** (the router's `reason` and unredacted tracebacks out of the logs; owner decision D3). `evaluation-report.md` L-60: "revisited with the Sprint 6 hardening". `05`'s TS-15-D fails until it is done. *Added 2026-10-14 (Z1). Source: audit, section 1.*
- [x] **Z2, hard ordering: sync `deploy/cloudrun/*.yaml` to paid mode (`LLM_MODE: paid`, `gemini-api-key-paid`) before the build trigger is enabled.** The repo YAML still says `LLM_MODE: free`; the first deploy after an enable would silently revert ADR-104 on five services. This item must be merged and verified before the "enable the build trigger" item above is acted on. *Added 2026-10-14 (Z1). Source: audit, section 1; ADR-104's drift note; the warning in `deploy/RUNBOOK_GRADING.md`.*
- [x] **Z2: the hourly per-invite cap from 15 to 30** (ADR-107): set `GATEWAY_ASKS_PER_SESSION_HOUR` in `deploy/cloudrun/gateway.yaml` (the code default is 15, `services/api_gateway/src/api_gateway/config.py`); the daily cap stays 50. A gateway-only redeploy, no answer change (ADR-103). *Added 2026-10-14 (Z1). Source: ADR-107.*
- [x] **Window A (2026-10-31 to 11-09): run `05`'s deployed scenarios** (TS-14, TS-16, TS-17, TS-18, TS-20, as `05` marks them). Needs the window opened as in `deploy/RUNBOOK_GRADING.md`: paid balance $5 or more, `ops-db` started, an invite. *Added 2026-10-14 (Z1). Source: audit, section 4 (items for `05`); ADR-107.*
  - *2026-10-15 (Owner-decided 2026-10-15; assistant-drafted.)* Moved to the owner verification session (ADR-110); Window A stays as a precaution.
  - *2026-10-15 (S6-W1; owner-decided 2026-10-15; assistant-drafted.)* **TS-17 is not a deployed scenario: `05` classes it Local** ("Environment: Local"; each case stops a service, which on Cloud Run is a configuration change). The item's list above ("TS-14, TS-16, TS-17, TS-18, TS-20, as `05` marks them") is corrected here, not edited: the deployed cases are TS-14, TS-16-D, TS-18-C and D, and TS-20. Source: `docs/session-plan-2026-10-17.md`, "Owner decisions 2026-10-15", decision 6.
  - *2026-10-15 (S6-W2; run by the owner with the assistant; assistant-drafted.)* Run in owner verification session 1, results in `evals/results/session1/2026-10-15/summary.md`. Ticked as run, not as passed: TS-14-A, B (five services; tool servers are sidecars), C, D (images not scanned), TS-18-D and TS-20-A, C, D pass; **TS-18-C's scaling clause failed** (reporting stayed at one instance); **TS-20-B and TS-20-E were not run**. The 05 revision is the owner's.
  - *2026-10-15 (S6-W2; owner-decided 2026-10-15; assistant-drafted.)* Two corrections to the note above. **TS-18-C's scaling-clause fail is classed by the owner as a `05` criterion flaw** (the clause asks for a scale-up that six concurrent requests at concurrency 8 do not require), not a system fault. **TS-20-E was checked by the owner at 20:00 CDT: FAIL, the known fail (`05` §7), no synthetic-data notice on the landing page.** TS-20-B stays not run (owner decision, no trigger).
- [x] **Window A: time the cold start on the sentiment and forecast paths.** Only the reporting path was measured (55.87 s in the browser, 2026-10-13). *Added 2026-10-14 (Z1). Source: audit, section 1.*
  - *2026-10-15 (Owner-decided 2026-10-15; assistant-drafted.)* Moved to the owner verification session (ADR-110), including the second idle wait (R-05).
  - *2026-10-15 (S6-W2; assistant-drafted.)* Done in owner verification session 1 (`evals/results/session1/2026-10-15/summary.md`): sentiment 61 s (gateway hop not cold) then 30.64 s on the second idle wait; forecast 46 s with all four hops cold; reporting at TS-20-A 29 s. All inside 120 s. The R-05 update is not written here.
- [ ] **R-11 / `05` (owner item for the `05` revision): re-verify the free-tier limits wherever `05` states them** (`05:102`, `05:567`), or reword them as "paid key in deployment (ADR-104)". *Added 2026-10-14 (Z1). Source: R-11 (2026-09-30 and 2026-10-10 lines).*
- [ ] **L-92 and L-24: the owner decides at the Sprint 6 close** whether the decline-heavy interpretation set (L-92) and the false-alarm sensitivity work (L-24) are built or dropped (6.5 brainstorm). *Added 2026-10-14 (Z1). Source: the Sprint 4 close ("the owner decides") and audit, section 1.*
- [x] **The divergence list goes into the evaluation report** (Sprint 6 writing): the post-submission list at the Sprint 5 close (`04`'s three sentiment lines against ADR-100; the ADR-093 calendar; Identity-Aware Proxy replaced by invite links, ADR-097). *Added 2026-10-14 (Z1). Source: the Sprint 5 close; ADR-094's note.*
  - *2026-10-15 (Owner-decided 2026-10-15; assistant-drafted.)* Add `03`'s calendar, which ADR-109 moves again (Sprint 6 now 10-15 to 10-25; buffer 10-26 to 12-05).
  - *2026-10-18 (S6-C1; owner-decided 2026-10-18; assistant-drafted.)* `03`'s calendar again: ADR-113 moves it a second time (Sprint 6 closed 10-18, day 4; buffer 10-19 to 12-05). `03` is Eric's to edit and nothing was changed.
  - *2026-10-18 (B-E1; owner-decided 2026-10-18; assistant-drafted.) Ticked: the list is collected in section 7 of the evaluation report skeleton (`docs/evaluation-report.md`).*
- [ ] **6.5 candidates (see that section):** L-89's degraded result, the L-95 rulings ("district", "end of next year") and L-96's router and decline-text fix. They change answers, so they are decided at the Sprint 6 close (ADR-106), not in Sprint 6. *Added 2026-10-14 (Z1). Source: audit, section 1.*
- [ ] **A paid-balance check and top-up before each window** (ADR-105, ADR-107, R-21): in `deploy/RUNBOOK_GRADING.md`; the dates are Window A and Window B. L-93's programmatic budget stop stays an option, not scheduled. *Added 2026-10-14 (Z1). Source: audit, section 1.*
- [x] **A repo-wide test guard:** point `CLOUDSDK_CONFIG` at an empty temp folder in the root `conftest.py`, so no test can reach GCP (a Z2a test touched IAM, 2026-10-14). *Added 2026-10-14 (Z2b). Source: the Z2a incident above.*
  - *2026-10-15 (S6-T1; owner-decided 2026-10-15; assistant-drafted.)* Built on branch `chore/window-day-tooling`: the root `conftest.py` sets `CLOUDSDK_CONFIG` to a fresh empty temp folder for the session and unsets `GOOGLE_APPLICATION_CREDENTIALS` and `CLOUDSDK_CORE_PROJECT`; no existing test failed because of it in the unit and services suites (2645 passed before, 2647 after the guard alone, 0 failures); integration, e2e and live were not run.
- [x] **Window-day tooling for the owner's PC:** IPv6 to `*.run.app` black-holes and `gcloud` calls take minutes, so `verify.py`'s end-to-end call hangs. Give `verify.py` a connect timeout that falls back to IPv4 (or an `--ipv4` flag) and print each line as it completes. The temp wrapper used on 2026-10-14 is in `RUNBOOK_V.md`'s PowerShell notes. *Added 2026-10-14 (Z2b). Source: `docs/deploy-window-log.md`, Z2b.*
  - *2026-10-15 (S6-T1; owner-decided 2026-10-15; assistant-drafted.)* Built on branch `chore/window-day-tooling`: `verify.py` gains `--ipv4` and `--gcloud-timeout`, a 10 s connect timeout per address, a timeout on each `gcloud` call that kills its process tree, and per-line flushed output; spec in `deploy/README.md` ("Window-day options"); the `$env:TEMP` wrapper in `RUNBOOK_V.md` is replaced by `--ipv4`. Never run against real services (live-call budget 0). Merging touches `deploy/verify.py`, a trigger path: the build trigger must be disabled at merge (ADR-105).
- [x] **Failure-path log codes, not seen live:** Z2b confirmed `outcome`, `verdict` and the trace ID on the success path only; `code` on a failed task and `outcome=degraded` are read from the code. Exercise one failure (for example a refused name) in Window A and read its lines. No plain-text-code gap was found. *Added 2026-10-14 (Z2b).*
  - *2026-10-15 (S6-W2; assistant-drafted.)* `code=invalid_range` seen live on the orchestrator's `agent task failed` and the reporting agent's `task failed` lines (an invalid date range, not a refused name, which returns `needs_clarification` first). `outcome=degraded` was **not** exercised. Observation: the reporting agent's line and `mcp_incidents` carry the tool's error text. See the session summary.
  - *2026-10-16 (S6-D2; Owner-decided 2026-10-15; assistant-drafted.)* Moved to owner session 1 (ADR-110) and exercised in step 4 (422 `invalid_range`, trace `2e3dc32a…`). The observation about tool error text in the logs is recorded as L-98. Ticked (already `[x]` from the S6-W2 note above; `outcome=degraded` stays unexercised).
- [ ] **Still not verified deployed:** the logging of each failed model-call attempt (no retry occurred in the Z2b requests). *Added 2026-10-14 (Z2b).*
  - *2026-10-15 (S6-W2; assistant-drafted.)* Left unticked: no retry occurred in session 1 either (a read for `attempt failed` found no lines).
- [ ] **A standing check for the retry log line.** At each session or window close, read the logs for `llm attempt failed` (the message `packages/llm/src/llm/client.py` logs for each failed model-call attempt, ADR-108). Read-only, no model calls; the PowerShell 5.1 command is in `deploy/RUNBOOK_GRADING.md`, "Close the window". The item above, "Still not verified deployed: the logging of each failed model-call attempt", stays open: no retry happened in Z2b or session 1, and forcing one needs fault injection, which means a deploy. If no natural retry has happened by the Sprint 6 close (2026-10-25), carry the item over with that reason; the unit tests are the evidence. *Added 2026-10-16 (S6-A1; owner-decided 2026-10-16; assistant-drafted.)* A read of the last 30 days on 2026-10-16 found no `llm attempt failed` line.
- [x] **Owner verification session 1 (ADR-110):** on a weekend before 10-25, date set by the owner. Runs `05`'s deployed scenarios, times the sentiment and forecast cold starts including the second idle wait, exercises one failure path to read its log codes live, and confirms grader access with a test invite from a browser profile with no owner session. Paid balance $5 or more first; `ops-db` started and stopped in one sitting; an entry in `docs/deploy-window-log.md`. *Added 2026-10-15 (Owner-decided 2026-10-15; assistant-drafted.)*
  - *2026-10-15 (S6-W2; assistant-drafted.)* Run 2026-10-15 instead of the planned 2026-10-17 (owner decision). `ops-db` 17:39 to 19:47 CDT, `STOPPED NEVER`. Summary: `evals/results/session1/2026-10-15/summary.md`; window-log entry dated 2026-10-15. Grader access confirmed; the three `06` confirmations are stated there (scenarios not fully confirmed).
- [x] **Owner decision: L-98 (tool error text in the logs).** Either state it in `06` and decide the fix at the 6.5 brainstorm, or fix it in Sprint 6 (logs only; needs a redeploy of two services). *Added 2026-10-16 (S6-D2; Owner-decided 2026-10-15; assistant-drafted. Source: `evals/results/session1/2026-10-15/summary.md`.)*
  - *2026-10-16 (S6-A1; owner-decided 2026-10-16; assistant-drafted.)* The owner chose option (a) on 2026-10-16: `06` states the limit; the fix is decided at the 6.5 brainstorm and deployed only after `06` is submitted (ADR-109). Option (b), a Sprint 6 fix, is not taken.
- [ ] **For the 6.5 brainstorm:** L-99 (verification line on a clarification) and L-100 (a backwards date range silently reordered; changes answers, ADR-106). *Added 2026-10-16 (S6-D2; Owner-decided 2026-10-15; assistant-drafted.)*
  - *2026-10-16 (S6-A1; owner-decided 2026-10-16; assistant-drafted.)* Add L-98's fix to this list: log the code, length and hash instead of the tool's error text in `agent_reporting`'s `task failed` line and in `mcp_incidents`. Logs only; a redeploy of two services, after `06` is submitted (ADR-109).
- [x] **Fix the Windows lock race in `scripts/session_driver.py`** (`_file_lock`, line 77): `os.open` with `O_CREAT|O_EXCL` raises `PermissionError`, not `FileExistsError`, while another thread deletes the lock. Bounded retry on `PermissionError`, then re-raise. Evidence: `test_parallel_never_passes_the_cap` failed 2 of 3 isolated runs on `main` `06ab581`; CI on Linux does not reproduce it. The failure is closed (an exception, never a cap breach). Separate PR, before the driver's next use (Window A or any 6.5 evaluation run). *Added 2026-10-16 (S6-A1; owner-decided 2026-10-16; assistant-drafted.)*
  - *2026-10-16 (S6-L1; owner-decided 2026-10-16; assistant-drafted.)* Fixed on branch `fix/session-driver-lock`: `_file_lock` treats `PermissionError` like "held" and retries (50 tries in a row, 50 ms apart, about 2.5 s), then re-raises the error, so a real permission problem still surfaces; the wait for a held lock (30 s) is unchanged. It was the only `O_CREAT|O_EXCL` in the repo. Offline tests monkeypatch `os.open` (acquire after 7 denials; re-raise after the bound; a held lock still times out). `test_parallel_never_passes_the_cap` passed 20 of 20 isolated runs on this machine (2 of 3 failed before). CI (Linux) cannot reproduce the race, so it never saw the failure. Tick holds once the PR merges.
- [ ] **Renew the owner invite `owner-laptop-2`** before Window A (it expires about 10-27; ADR-107). *Added 2026-10-16 (S6-D2; Owner-decided 2026-10-15; assistant-drafted.)*
- [ ] **Submit `05`** (due 2026-11-01; owner). *Added 2026-10-15 (Owner-decided 2026-10-15; assistant-drafted.)*
- [ ] **Submit `06`** (due 2026-11-08; owner) after the three confirmations of session 1 (scenarios, cold starts, grader access). *Added 2026-10-15 (Owner-decided 2026-10-15; assistant-drafted.)*
  - *2026-10-18 (S6-D3; owner-decided 2026-10-18; assistant-drafted.)* `06` is drafted in Word as version 1.3, dated 2026-10-18, about 29 pages; not submitted (due 2026-11-08). The Markdown copy is committed to `docs/academic/` only after submission. Its claims were checked against the deployed system before submission (Sprint 3 retro, rule 2), using owner verification session 1 (2026-10-15) and `docs/production-grade-audit.md`. `06` states these as limits:
    - tool error text in two services' logs (L-98), and the model provider's error sentence, logged shortened (the L-60 remainder);
    - logging of failed model-call attempts is deployed but not yet observed;
    - the forced restart is not yet rehearsed;
    - no backups and no point-in-time recovery, with a single-zone database;
    - the QA startup probe is on `/healthz` (F1);
    - no liveness probes (F2);
    - the pipeline's verify step has not yet run on all six services (F13);
    - scaling across services is not demonstrated;
    - there is no automated dependency scanning;
    - a degraded result has not occurred on the current build;
    - the degraded-answer alert is the only alert on system behaviour.
    - Stays unticked until the owner submits.

*Findings from the production-grade audit (S6-P1), added 2026-10-16 (owner-decided 2026-10-16; assistant-drafted). Source for each: `docs/production-grade-audit.md`, Findings. The label on each is a suggestion from whether the fix touches a deployed service (ADR-109: no deploy before `06` is submitted); the owner decides which are fixed.*
- [ ] **F1: point the `ops-qa` startup probe at `/readyz`** (`deploy/cloudrun/qa.yaml:79-82`; the endpoint checks the database). A config change that needs a redeploy. *Carry to 6.5 / close.*
  - *2026-10-22 (ADR-113 item 1; assistant-drafted.)* Built in the repo, not deployed: the `ops-qa` startup probe is on `/readyz`. It deploys in the hardening window after `06` is submitted.
- [ ] **F2, probes: add a Cloud Run `livenessProbe` (`/healthz`) to the nine containers.** A config change that needs a redeploy; bundle it with F1. *Carry to 6.5 / close.*
  - *2026-10-22 (ADR-113 item 1; assistant-drafted.)* Built in the repo, not deployed: a `livenessProbe` on `/healthz` on all nine containers. It deploys in the hardening window after `06` is submitted.
- [x] **F2, wording: a dated note on §7 item 4** so "liveness on every service" is read as the endpoints only, until the probes exist. Docs only. *Sprint 6 if capacity.*
  - *2026-10-18 (S6-R1; owner-decided 2026-10-16; assistant-drafted.)* Done: a dated wording note on `architecture.md` §7 item 4. The probes themselves (F2, probes) stay a 6.5 candidate with F1.
- [ ] **F13: one Cloud Build run with `_RUN_VERIFY=true` against the six-service system** that passes `verify.py` in the pipeline (needs a deploy window: `ops-db` running, the trigger enabled for the run, the build account's invoker bindings in place). Holds item 9 at Partly met until done. A deploy action. *Carry to 6.5 / close.*
  - *2026-10-22 (ADR-113 item 1; assistant-drafted.)* A deploy-window action, not built here.
- [x] **F3: a dated correction to §7 item 9's deploy history.** The services' images were built and deployed by Cloud Build trigger runs (`3e63cdc4`, `0dc5aae1`); `plan_full.py` created accounts, secrets and IAM bindings by hand-run commands. Docs only; also check where else the "by hand through `plan_full.py`" wording appears (for example `deploy/RUNBOOK_GRADING.md`, `06`). *Sprint 6 if capacity.*
  - *2026-10-18 (S6-R1; owner-decided 2026-10-16; assistant-drafted.)* Checked by search (`plan_full`, "deployed by hand", `*.md`). The only line that says `plan_full.py` deployed the services is `architecture.md` §7 item 9, which already carries the audit's correction. The other hits are pre-deploy plans (ADR-099, `decisions-log.md:3216`, `:3246`, `:3248`; `risk-register.md:360`; `sprint-log.md:906`), usage lines (`deploy/RUNBOOK_V.md`, `deploy/README.md:7`) and records of what `plan_full.py` did create (`deploy-window-log.md:246`), none of which claim it deployed the images. No `06` text and no `deploy/RUNBOOK_GRADING.md` line carries the wording. No further correction was needed.
- [x] **F4 and F5: README fixes.** Say at step 2 that `docker compose up -d postgres` needs `GOOGLE_AI_API_KEY` set to any value (or split the compose file so postgres alone does not need it); update the three stale lines (Sprint 6 dates per ADR-109; the trigger sentence; "five" roles against ADR-063). Optionally note that Windows needs a short clone path. Docs, and possibly compose; re-run the fresh-clone check afterwards. *Sprint 6 if capacity.*
  - *2026-10-18 (S6-R1; owner-decided 2026-10-16; assistant-drafted.)* Done in the README, with no compose change: the three stale lines are fixed; a stage table says what each stage needs; the key note sits at the `.env` step; a line on short clone paths covers F10. The README also states that without the sentiment weights no end-to-end answer is possible, because of the compose `depends_on` chain. The fresh-clone re-run on the fixed README passed every step before the key-and-weights step (`docs/production-grade-audit.md`, "Fresh-clone record, re-run 2026-10-18").
- [x] **F6: the README architecture diagram** (owner draws it; placeholder at `README.md:39`). Item 12 stays unticked until it exists and the clean-clone steps pass. *Sprint 6 if capacity.*
  - *2026-10-18 (S6-R1; owner-decided 2026-10-16; assistant-drafted.)* **Drafted, awaiting the owner's check; not ticked.** A Mermaid flowchart is in the README. It could not be validated locally (no Node on this machine, so `mermaid-cli` could not run), so its syntax was reviewed by hand only. The owner checks the render on the PR page.
  - *2026-10-18 (S6-R1 follow-up; owner-decided 2026-10-18; assistant-drafted.)* **Done.** The owner saw it render on GitHub, and it validated with mermaid-cli 11.4.2 in headless Chromium with no errors (commit `8b55192`). Item 12 is ticked in `architecture.md` §7.
- [x] **F7 and F9: two dated qualifiers in `security-model.md`.** §4's "LLM callers get only the free key; no service gets the paid key" holds for compose only (the deployed containers mount both keys, ADR-104). §4's secret-scanning row should record that GitHub secret scanning and push protection are enabled on the repository (read 2026-10-16), while GitGuardian remains visible on pull requests only. Append-only: add dated lines, do not edit the rows. *Sprint 6 if capacity.*
  - *2026-10-18 (S6-R1; owner-decided 2026-10-16; assistant-drafted.)* Done as two dated notes directly after the §4 table in `security-model.md`, each naming the row it qualifies (a line inside the table would split it). The rows are unedited.
- [x] **F8: the owner reads the Billing console** and records the budget alerts ($10 project at 50%, 90%, 100%; $50 and $80 account) and the paid prepaid balance and auto-reload state, because the Cloud Billing Budget API is not enabled and the CLI cannot read them. Read-only in the console; no GCP write. Item 11 stays unticked until the readings are recorded. *Sprint 6 if capacity (before `06`).*
  - *2026-10-16 (S6-P1; owner-decided 2026-10-16; assistant-drafted.)* **Resolved by owner observation** in the consoles: GCP budget alerts at $10, $50 and $80 exist; the AI Studio prepaid balance is $7.85; GCP cost for 2026-10-01 to 10-16 is $3.15. Recorded in `docs/production-grade-audit.md`, item 11, as owner-reported. Item 11 is ticked in `architecture.md` §7.
- [x] **TS-14-D: a credential scan of the repository history and the nine deployed images.**
  - *2026-10-18 (S6-S1; owner-decided 2026-10-18; assistant-drafted.)* **Run. Verdict: Passed.** Trivy 0.76.0 (secret scanner) over the nine images at the digests the serving revisions are pinned to (tag `9ab7c77…`): 0 hits in each. Gitleaks v8.30.1 over all 333 non-merge commits of a fresh full clone at `3f342c3`: 2 hits, both false positives (SHA-256 file digests for `tokenizer.json` and `tokenizer_config.json` in `ml/sentiment/artifacts/bert_v1.manifest.json`, commit `ff004c7d4e`, lines 23 and 24). By class: 0 real credentials, 0 test fixtures, 2 false positives, 0 third-party package hits. Image history showed no `ARG` or secret mount, and baked `Env` holds no secret. The `secretKeyRef` table read from the live revisions matches the audit's Appendix A; the one addition is the gateway's literal `GATEWAY_INVITES_SECRET`, which holds a Secret Manager resource name, not a value. Trivy read the images from Artifact Registry with a short-lived access token (local `docker save` archives were unreadable to it; summary, "How Trivy read them"). No model call, no GCP write, no `ops-db`. Evidence: `evals/results/ts14d/2026-10-18/summary.md`.
  - *For `05` (the owner's to edit):* TS-14-D's result is **Passed** (it was "images not scanned" in owner session 1), so TS-14 can move from Partly run to Passed if its other cases stand as recorded in `evals/results/session1/2026-10-15/summary.md`. This is a secret scan, not a CVE scan.

*Backlog correction, 2026-10-14 (Z1):* the **G21 item** above (a scorer comparison "as a `golden_v3` scoring change") needs a golden-run prompt with explicit permission to open `evals/golden/`. It is not a Z item. Owner decides in 6.5 (L-95).

**Z2a status, 2026-10-14 (post-freeze fixes, code PR, local only; owner-decided 2026-10-14; assistant-drafted).** Built in Z2a (PR `fix/z2-post-freeze`), deploy in Z2b. **None is ticked until Z2b verifies it deployed.** Each is one of the changes ADR-103 allows after the freeze (logging, the trace ID, deploy config and tooling); none changes an answer, a route, a parse, a QA verdict or §6's answer wording, and no prompt file changed.
- **Built in Z2a, deploy in Z2b:**
  - the trace ID end to end (ADR-108): the gateway mints or keeps a valid `X-Trace-Id`, one `request` access line per request in all nine HTTP servers, the header on A2A and MCP calls;
  - the L-60 redaction (ADR-108): the router's `reason` and agent failure sentences as length and hash, exceptions as classes and frames, `mcp` SDK logger held at INFO;
  - the YAML sync to paid mode for the five model-calling containers (ADR-104 note); **the trigger may be enabled only after it is merged**;
  - the hourly cap of 30 (ADR-107), daily cap 50;
  - logging of each failed model-call attempt (class, status, wait, elapsed);
  - the public `GET /health` and the cold-start measure that no longer uses `/healthz`;
  - `plan_full.py` without a shell (`shutil.which`), `verify.py` over all six services, and the runbook fixes (template tag, Cloud SQL annotation, step 7 scope, Windows PowerShell 5.1 notes).
- **Not done in Z2a, by rule:** the Next.js bump. The 2026-10-14 out-of-band release was announced for that day (https://nextjs.org/blog/upcoming-nextjs-security-update-october-2026, read 2026-10-14) but no advisory or release note naming a fixed version was published at the time of reading (https://github.com/vercel/next.js/security/advisories: newest 2026-09-30). The pin stays 16.3.8. Re-check before Z2b; pin only to a version an advisory names.
- **Still open for Z2b or later:** enabling the build trigger and its docs-only merge check (runbook step 8); the scoped Cloud SQL suites below.
- **Step 7, planned scope for Z2b (read from the fixtures, 2026-10-14).** Only `tests/integration/test_qa_sentiment_agrees.py` and `tests/integration/test_agent_sentiment_figures.py` (L-78). **Both need `POSTGRES_ADMIN_*`:** the shared `live_database` fixture (`tests/integration/conftest.py`) connects as the admin role to check that the database is migrated, `test_agent_sentiment_figures.py` writes and deletes throwaway predictions as admin, and two tests in `test_qa_sentiment_agrees.py` open admin connections (one skips under `stored_only`). Running them on Cloud SQL would put the superuser's credentials in the test shell, which was refused on 2026-10-13. **So the run stays deferred**, and L-78's status is recorded as: met locally; Cloud SQL parity proven by fingerprint and table hashes (`evals/results/sprint5_x/data_parity_cloud.json`, `sprint5_x.md`); suites not run on Cloud SQL because their fixtures need superuser.
- **Incident in Z2a, recorded for honesty.** A new unit test of `plan_full.py` (`test_a_real_run_that_deploys_needs_an_image_tag_or_skip_deploy`) selected phase 5 instead of phase 6, which has no deploy step, and so ran the real plan: four `gcloud iam service-accounts add-iam-policy-binding` calls granting `build-deploy` `roles/iam.serviceAccountUser` on `run-sentiment`, `run-forecast`, `run-qa` and `run-gateway`. Those bindings already existed (ADR-099, deployed 2026-10-12/13), so the policies are unchanged in content (read back with `get-iam-policy` the same hour; only the policy version and etag can have moved). It was a project change the prompt did not allow. Fixed: the test selects phase 6 and a fixture in `tests/unit/test_deploy_full.py` makes any test that starts a real process fail. Reported to the owner.
- **`05` note:** TS-15-D (hostile and malformed input, logs) is now testable after Z2b's deploy: the trace ID is on every log line of a request, and a typed name is in none (ADR-108, `services/agent_reporting/tests/test_log_redaction.py`). Until Z2b deploys, the deployed services log as before and TS-15-D still fails as `05:559` says.
- **Proof of no answer change, Z2a section 9 (local stack, paid mode, 2026-10-14).** Containers capped at 12 requests and $0.01 each, 12 requests and $0.05 in total; used 12 requests (3 before, 9 after) and $0.0042 on the 9 after-run calls (from the `llm call` lines). **Conflict recorded:** the prompt asks for the three questions before and after (18 calls) under a 12-request cap, so the before run asked only question 1 (3 calls) and the after run asked all three (9 calls); the cap was kept.
  - *Q1, "What was SLA compliance in the Northeast last month?", main against `fix/z2-post-freeze`:* route `reporting`, `prompt_version` `route_v3`, parsed request (`sla_compliance`, region `northeast`, 2026-07-01 to 07-31), outcome `answered`, `qa_status` `verified`, figures (141 of 160, rate 0.8813) and answer text **identical**. The only difference is the router's model-written `reason` ("...falls under operational reporting." against "...which fall under reporting."): model wording variance, and not logged any more (ADR-108).
  - *Q2, sentiment trend by month, after only:* route `sentiment`, `answered`, `verified`, range 2026-04-01 to 06-30, 723 comments (positive 366, neutral 176, negative 128, mixed 53).
  - *Q3, weekly volume for the next 8 weeks, after only:* route `forecast`, `answered`, `verified`, 8 weeks from 2026-08-31 to 10-25.
  - *Trace ID, Q1 after-run `bf0c6a86ff474177aa2a5cd0a5c51437`:* the `X-Trace-Id` response header equals the body's `trace_id`, and the same ID is on 6 lines of the orchestrator (including the `request` access line), 6 of `agent_reporting`, 3 of `mcp_incidents` (its tool call and its two `/mcp` access lines) and 6 of `agent_qa`. Lines with no ID are server start-up lines only.
  - *Not covered live:* sentiment and forecast before/after (the cap). Their answers are covered by the unchanged answer-text tests (the whole suite passes with only three log-field assertions changed, listed in the PR), and QA marked both `verified`.
- **Suites at the end of Z2a:** unit and services, integration (`REQUIRE_INTEGRATION_DB=1`, local Postgres, 1127 passed), ruff clean; `test_eval_freeze.py` and `test_eval_set_manifest.py` pass; no file under `services/*/prompts/` changed.

**Next.js 16.4.1 bump, 2026-10-14 (PR `fix/nextjs-16.4.1`, local only, no live calls, no GCP; assistant-drafted).** Supersedes the "not done in Z2a" line above: an advisory now names a fixed version.
- **Advisories, read 2026-10-14** on `github.com/vercel/next.js/security/advisories/<id>` (not yet in the global advisory database or OSV at the time of reading); all published 2026-10-14; `next@16.4.1` is on the npm registry (published 2026-10-14T17:43:55Z, `latest`):
  - GHSA-2464-fhr4-w9xw, critical (CVSS v4 9.5): remote code execution in the Image Optimization API when SVG files are used (via `sharp`); patched 16.4.1 (and 15.5.28).
  - GHSA-673q-mjm6-r5xr, critical (9.5): remote code execution in `use cache` functions returning typed arrays (App Router with Cache Components); patched 16.4.1.
  - GHSA-p3m5-59mp-jv5r, high (8.2): denial of service in the App Router with at least one Server Action; patched 16.4.1 (and 15.5.28).
- **Exposure finding: none of the three is reachable in the deployed gateway.** `web/next.config.mjs:4` sets `output: "export"`; `:5` sets `images: { unoptimized: true }`; `web/app/` contains no `"use server"`, no `"use cache"`, no `next/image` import and no `cacheComponents` setting (searched, no match); the gateway image has no Node runtime (final stage of `services/api_gateway/Dockerfile` is `python:3.12-slim` serving `/app/static`). All three are server-runtime paths, and there is no Next.js server in production (ADR-080).
- **Bumped as defence in depth**, not because anything was exploitable: `next` pinned to exactly 16.4.1 in `web/package.json` and `web/package-lock.json` (only `next` and its platform packages changed; there is no `eslint-config-next`); `MIN_NEXT` in `web/scripts/check-next-version.mjs` raised to 16.4.1. `web/out` rebuilt; `npm audit --omit=dev --audit-level=high` reports 0 vulnerabilities. The UI is unchanged: gateway suite (114) passes, including the CSP hash check on the real export and the section 6 wording tests; no file under `services/*/prompts/` changed.
- Deploy of the new image is Z2b's, with the rest of Z2a.

**Z2b status, 2026-10-14 (deployed and verified; owner present; assistant-drafted).** Build `0dc5aae1-2a6c-498e-bbca-f709c2c91149` from `9ab7c775964bd0aae491ca72082e95229c994129`, `SUCCESS` in about 7 min; six revisions serving at 100%; `verify.py` all `PASS` (paid mode on the five containers, so the YAML sync held); the gateway revision carries `GATEWAY_ASKS_PER_SESSION_HOUR=30`; the trace ID is on the orchestrator, reporting, `mcp_incidents` and QA lines of one request, with no question or router-reason text. The ticks above are those Z2b verified deployed. Not ticked: the build-trigger item under Planned (its proof is recorded in the next dated window-log entry) and the model-call-attempt logging. Record: `docs/deploy-window-log.md`.

**Shipped:**
*2026-10-18 (S6-C1; owner-decided 2026-10-18; assistant-drafted.)* The PRs merged from 2026-10-15 to the close, #60 to #73, from `git log --merges` (PRs #58 and #59 merged 10-14, before the sprint, and are Z2b records).
- **Sprint set-up and tooling** (not among the close prompt's themes; listed so none is dropped):
  - #60 `docs/sprint6-calendar` (merge `89f9140`): the Sprint 6 calendar (ADR-109, ADR-110).
  - #61 `docs/05-revision` (merge `e1baec3`): `05` latest revision in `docs/academic/` (the owner's).
  - #62 `chore/window-day-tooling` (merge `6dd8ba8`): `verify.py --ipv4`, timeouts and per-line output; the `CLOUDSDK_CONFIG` test guard.
  - #63 `docs/session-plan-1` (merge `60027c1`): the plan for owner verification session 1.
  - #64 `chore/session-driver` (merge `ad6e556`): `scripts/session_driver.py`, the ledger-capped session driver.
- **Session 1 records:**
  - #65 `docs/session1-results` (merge `379ec6c`): results of owner verification session 1 (2026-10-15), window log and sprint log.
  - #66 `docs/session1-followup` (merge `06ab581`): ADR-111, L-98 to L-101, R-05, R-21 and the calendar table.
- **The alert:**
  - #67 `feat/degraded-alert` (merge `fdcd470`): Part A, the metric, policy and `scripts/alert_degraded.py` as code (ADR-112).
  - #69 `docs/alert-part-b` (merge `fa2c7cd`): Part B, the live apply and the synthetic-entry test, which passed.
- **The lock fix:** #68 `fix/session-driver-lock` (merge `36932d5`): `_file_lock` retries on `PermissionError`, bounded, then re-raises.
- **The audit:** #70 `docs/production-grade-audit` (merge `1da8374`): `docs/production-grade-audit.md` (criteria before evidence), the §7 ticks and notes, the findings.
- **README and diagram, and the docs findings:** #71 `docs/readme-and-audit-fixes` (merge `3f342c3`): the README setup stages and the Mermaid architecture diagram (validated with mermaid-cli 11.4.2); dated corrections for F2, F3, F7, F9, F12; the fresh-clone re-run.
- **TS-14-D:** #72 `evals/ts14d-scan` (merge `030bf81`): Trivy over the nine images and gitleaks over the history; Passed.
- **`06` status records:** #73 `docs/06-production-support-status` (merge `e1537c1`): `06` drafting status, rubric and weights backup location (S6-D3).
- No code in these PRs changed a deployed service: the nine deployed images were read on 2026-10-18 at the digests the serving revisions are pinned to, tag `9ab7c77…` (`evals/results/ts14d/2026-10-18/summary.md`), and the trigger is disabled.

**Planned vs done:**
*2026-10-18 (S6-C1; owner-decided 2026-10-18; assistant-drafted.)* Status as the list stands at the close; no box is changed here.
- Observability, CI/CD completion, graceful degradation, load/latency: unticked. Observability done (trace ID and redaction deployed in Z2b, the alert); CI/CD completion waits on F13; graceful degradation has the alert but no live path on the current build; load testing was not done (cold starts were timed in session 1).
- The L-80 and L-77 options: not done; roadmap, portfolio value, not built (owner ruling 2026-10-18, ADR-113).
- The alert: done (ticked, #67 and #69). The alert script's comparator and timestamp fix: not done; carried as housekeeping (ADR-113).
- Terraform; the `verify-caller` account; deploy with no traffic (L-64); the batch-scoring job: not done; roadmap, portfolio value, not built (owner ruling 2026-10-18, ADR-113). The default compute account's Editor-role review: not done; 6.5 housekeeping (IAM only, no service redeploy; ADR-113).
- The production-grade audit: done (ticked, #70).
- The evaluation report, presentation and demo rehearsal: not started; buffer by plan (ADR-109, ADR-113).
- The deploy-window and runbook items (`plan_full.py`, runbook fixes, the route rename, the YAML sync, the Next.js bump, the build-trigger step, `verify.py` coverage), the Z2 items, the window-day tooling, the test guard, the failure-path log codes: done (ticked).
- Logging of failed model-call attempts and the standing check: unticked. Built and deployed, never observed (the read below found 0).
- Runbook step 7 (the L-78 Cloud SQL suites): unticked, carried.
- G21 (a `golden_v3` scorer change, L-95), the `cost_usd` and `model_calls` response fields (L-94): unticked; roadmap (ADR-113).
- The runbook's step 12 second idle wait: ticked at the owner's ruling later the same day (dated note on the item); it was measured in session 1 (sentiment 30.64 s).
- Window A's scenarios and the cold-start timing: done in session 1 (ticked).
- The `05` free-tier wording (R-11): unticked; the owner's, in `05`.
- L-92 and L-24, "the owner decides at the Sprint 6 close": decided by ADR-113 as roadmap; the box stays unticked because neither is built.
- The 6.5 candidates item (L-89, the L-95 rulings, L-96): decided by ADR-113 as roadmap.
- The paid-balance check before each window: unticked, carried.
- The divergence list: unticked; evaluation report writing, buffer.
- L-99 and L-100: L-99 is in the hardening bundle, L-100 is roadmap (ADR-113).
- The renewal of `owner-laptop-2`, submitting `05`, submitting `06`: unticked, carried (below).
- Audit findings: F1, F2 (probes) and F13 unticked, in the hardening bundle (ADR-113). F2 wording, F3, F4 and F5, F6, F7 and F9, F8: done (ticked). TS-14-D: done (ticked).

**Carried over:**
*2026-10-18 (S6-C1; owner-decided 2026-10-18; assistant-drafted.)*
- **Submitting `05` (due 11-01) and `06` (due 11-08):** owner; both are complete and held, not submitted (owner decision).
  *2026-10-22 (owner-reported 2026-10-22; assistant-drafted.)* `05` is submitted. `06` is still held, not submitted, so ADR-109's rule (kept by ADR-113) still holds: no 6.5 change deploys until `06` is submitted. ADR-106 still holds too: nothing from 6.5 is counted in `05`. Under the academic-documents rule, `05`'s Markdown copy may now be committed; that is a separate change, made when the owner provides the file.
- **The retry-log check.** Read 2026-10-19 00:13:34 UTC (2026-10-18 19:13 CDT): `jsonPayload.msg="llm attempt failed"` on the Cloud Run `stdout` log (`log_id("run.googleapis.com/stdout")`), `--freshness 30d`: **0 entries**. The line is a `log.warning` (`packages/llm/src/llm/client.py:278`) and the JSON handler writes to stdout (`packages/common/src/common/logging.py:166`), so the filter could have matched it. A control read of `ask answered` over the same form returned an entry (2026-10-16T00:38:28Z). Carried with the reason: no natural retry has occurred; forcing one needs fault injection, which means a deploy; the unit tests (`tests/unit/test_llm_client.py`) are the evidence.
- **The 6.5 scope items (ADR-113):** the hardening bundle and the UI polish, deployed in one window after `06` is submitted; the FR-03 attempt, ending by 11-08, with its own ADR before any model call.
  *2026-10-22 (owner-accepted 2026-10-22; assistant-drafted.)* FR-03's third and final attempt is done: no-go at development selection (ADR-114 result note, ADR-115), and FR-03 is recorded as unmet with no further attempt. It finished 17 days inside its 11-08 timebox, at $1.641 of the $2.50 budget. Nothing from it deploys; the hardening bundle and the UI polish are unaffected and still deploy after `06` is submitted.
  *2026-10-22 (ADR-116; owner-decided 2026-10-22; assistant-drafted.)* `route_v6` becomes the default router. It was merged with the trigger disabled and deploys with the hardening bundle after `06` is submitted. The window's verification adds one live ambiguous question (expect `needs_clarification`, `intent_ambiguous`) and one clear question.
  *2026-10-22 (ADR-117; owner-decided 2026-10-22; assistant-drafted.)* The 6.5 presentation scope widens to six items: example questions, a "How it works" page, an FAQ, an evaluation results page, the answer journey (moved from roadmap; an API contract change), and a demonstration runbook with a backup recording. A CI job will build the UI. The final package is code, a documentation packet with optional revisions, and a live demonstration, with no slide file. The deploy window moves to after Window A (about 11-10 onward, unless the owner chooses otherwise). Done so far: the hardening bundle merged (PR #82), not deployed.
  *2026-10-22 (TS-20-E; assistant-drafted.)* Notice text revised to cover the sentiment model's synthetic training data, as TS-20-E requires (§6 rule 6, dated block). Built and checked locally; not deployed. `05`'s recorded result stands (ADR-106).
- **The L-78 Cloud SQL suites:** their fixtures need the superuser's credentials, which was refused (Z2a, step 7 note above); housekeeping.
- **Renewing the `owner-laptop-2` invite about 10-30,** because a renewal tonight would expire before Window A (it expires about 10-27 and Window A opens 10-31, ADR-107).
- **The paid-balance check before Window A** (10-31; ADR-105, R-21).

**Blockers encountered:**
*2026-10-18 (S6-C1; owner-decided 2026-10-18; assistant-drafted.)* The first is owner-reported in S6-C1; the second is recorded in part (the audit, F12); the third is recorded in the S6-R1 note on F6 and in `architecture.md` §7 item 12.
- The Project files ran two days behind the repo (found 2026-10-18, refreshed the same day). Owner-reported in S6-C1; no earlier record in the repo.
- The permission layer refused to delete temporary folders three times: `C:\fc-audit` (recorded in the audit, F12, and since removed), and `C:\fc2` and `C:\ts14d` (owner-reported in S6-C1; the repo records `C:\fc2` and `C:\ts14d` only as clone locations).
- No Node on the owner's machine, so the README diagram could not be validated locally on 2026-10-18 (S6-R1). Resolved the same day: it validated with mermaid-cli 11.4.2 in headless Chromium (commit `8b55192`).

**Retro:**
*2026-10-18 (S6-C1; owner-decided 2026-10-18; assistant-drafted.)* A draft for the owner to edit in the PR. Where a line rests only on the owner's word, it says so.
- What went well:
  - Criteria committed before evidence in the audit (commit `5271dea`, "criteria before evidence", ahead of the evidence commit).
  - A synthetic log entry proved the alert path (filter, metric, policy, email) without waiting for a real fault (ADR-112).
  - State checks caught a stale Project (owner-reported), an overclaiming prompt from another chat (owner-reported), and wrong premises in the assistant's own prompts: the `outcome == "degraded"` filter that the orchestrator's line does not carry (ADR-112); the "never exercised live" wording (owner-reported); and a validation claim made before the validation ran, which was caught and then run (the diagram, F6; the catch is owner-reported).
  - The fresh-clone check found a setup failure the README hid (F4, `docker compose up -d postgres` needs a key the README did not mention).
- What didn't:
  - *2026-10-14 (Z2b):* A prompt's "no GCP change" rule doesn't bind test code; the guard above does.
  - Project-file drift across chats (owner-reported).
  - Prompts from dedicated chats bypassing the state checks; now routed through the main chat (owner-reported).
  - Temporary folders created outside the scratch area (recorded: audit F12).
  - Assistant-written prompts that asserted facts before checking them (recorded: ADR-112).
- What changes next sprint: *(n/a — final sprint.)* What I'd do differently on a future project:
  - Refresh shared context after every merge batch.
  - One chat owns the repo prompts.
  - Temporary work goes under a gitignored folder inside the repo.
  - A claim in a prompt names where it was verified.

**Academic deliverable status:**
- Final product due 2026-12-05 (end of Module 10) — *2026-10-18 (S6-C1; owner-decided 2026-10-18; assistant-drafted.)* In progress: the evaluation report draft by 11-08 and final by 12-01, the presentation draft by 11-22 and rehearsal by 11-29 (ADR-113). `05` and `06` are complete and held, not submitted (owner decision); due 11-01 and 11-08.
- *2026-10-16 (S6-A1; owner-decided 2026-10-16; assistant-drafted.)* **Notes for `06`** (written by the owner; this records what the evidence supports):
  - `06` must not claim that retry logging is verified on the deployed system. It is built and unit-tested (ADR-108); no retry has happened on the deployed system, so no line has been read.
  - `06` must not claim that the degraded outcome is verified on the deployed system by the alert test: that test proves the monitoring path only (ADR-112). What is true: degraded results were observed live on 2026-10-13 on the previous build (two `ask degraded` lines, `trigger=dependency`, `capability=routing`, the free-tier 504 window of ADR-104); the current build has the same line shape (`degraded_response()` is unchanged between `9607fa72` and `9ab7c77`) and has not been exercised.
  - `06`'s logging section must say all of the following, consistent with L-98 and `security-model.md` §5: (1) tool error text, including dates parsed from the question, can appear in two services' logs (`agent_reporting`'s `task failed` line and `mcp_incidents`); (2) question wording was not seen in the logs; (3) only one failure path was checked.
- *2026-10-16 (S6-A2; owner present; assistant-drafted.)* **Notes for `06`, addition** (what the evidence supports):
  - `06` may say the alert path (filter, metric, policy, email) is verified live on 2026-10-16, with a synthetic entry (`trace_id` `alerttest-...`, `synthetic_alert_test: true`, which adds one `trigger=dependency`, `capability=routing` count to the metric's history).
  - `06` may say the degraded log line was observed live on 2026-10-13, on the previous build (`ops-orchestrator-00005-pzc`, routing dependency), with the same line shape in the current build.
  - `06` must not say the current build has produced a real degraded answer: it has not.
- *2026-10-18 (S6-D3; owner-decided 2026-10-18; assistant-drafted.)* **Notes for `06`, status:** the original line "**Notes for `06` (due 2026-11-08).** Stub; outline waits on the assignment text" is superseded. The assignment text is the four required parts (application description, standard operating procedures, troubleshooting, disaster recovery and clean restart), and `06` is drafted (Word version 1.3, 2026-10-18). The original line is unchanged.

**Decisions made this sprint:**

- ADR-106 (Sprint 6.5 scope at the Sprint 6 close), ADR-107 (grading windows and grader access) and ADR-108 (trace ID, log redaction, retry error logging): decided 2026-10-14, before this sprint's start.
- ADR-109 (Sprint 6 runs 2026-10-15 to 10-25; the buffer starts 10-26) and ADR-110 (owner verification sessions outside grading windows): decided 2026-10-15.
- ADR-111 (owner verification session 1 ran on a weekday; supersedes ADR-110's weekend clause only): owner-decided 2026-10-15, written 2026-10-16.
- ADR-112 (a log-based alert on degraded answers, tested with a synthetic entry): owner-decided and written 2026-10-16.
- ADR-113 (Sprint 6 closes 2026-10-18; the buffer starts 10-19; the Sprint 6.5 scope; supersedes ADR-109's sprint dates and ADR-106 in part): owner-decided and written 2026-10-18.

*Re-baselined 2026-10-10 (ADR-093): this sprint now runs 2026-10-26 to 11-08 and the buffer is 2026-11-09 to 12-05; scope expansion is decided at the Sprint 5 close.*
*Note (ADR-082, 2026-10-08): this sprint is planned hardening and delivery work. The buffer is 2026-11-23 to 12-05. If Sprints 1–5 ran clean, use the slack for polish and rehearsal — not for starting anything new.*
*2026-10-16 (S6-A1; owner-decided 2026-10-16; assistant-drafted.)* Correction: both lines above are superseded by ADR-109. Sprint 6 runs 2026-10-15 to 10-25 and the buffer runs 2026-10-26 to 12-05.

---

## Sprint 6.5 candidates (brainstorm, not committed) — recorded 2026-10-14

Owner's note: a possible Sprint 6.5 (about 2026-11-09 to 11-29, inside the
buffer before the 12-05 final) to expand scope where it adds value. Nothing
here is committed: scope is decided at a brainstorming session at or near the
Sprint 6 close, as an ADR-093 buffer-and-scope decision. Each candidate notes
whether it changes answers (and so needs a fresh blind evaluation or a
disclosed difference from the evaluated system).

*2026-10-16 (S6-A1; owner-decided 2026-10-16; assistant-drafted.)* Under ADR-109, 6.5 work can start 2026-10-26 (the header's "about 2026-11-09 to 11-29" is superseded), and nothing from it deploys before `06` is submitted.

*2026-10-18 (S6-C1; owner-decided 2026-10-18; assistant-drafted.)* **Scope decided by ADR-113** (the Sprint 6 close; 6.5 work starts 10-19, and the 6.5 deploy waits for `06` to be submitted). No line below is deleted; each candidate is marked here, and nothing is dropped:
- Response transparency, split in three: **committed**, the live elapsed timer, in the UI polish item (client-side only: the browser times the request; no API change, no answer change); **roadmap**, the after-answer timeline (needs per-hop durations in the orchestrator's response, an API contract change and an orchestrator redeploy); **roadmap**, the estimated cost per answer (needs `cost_usd` and `model_calls`, L-94, the same contract change).
- Cost framing: **roadmap**; it needs a measured baseline, and cost figures are list-price estimates only (L-71).
- UI appearance upgrade scoped to the presentation: **committed** (ADR-113 item 2; §6 answer wording kept exactly).
- Executive-style analysis: **roadmap**.
- Expanded agent abilities (L-68, L-67, G04 and L-56, L-47): **roadmap**.
- FR-03 third attempt on a freshly generated blind set: **committed**, one attempt, its method decided in its own ADR before any model call (ADR-113 item 3).
- L-89 (a stopped database gives the degraded result): **roadmap**.
- The L-95 rulings ("district", "end of next year"): **roadmap**.
- L-96 (the router and decline-text fix): **roadmap**.
- Also decided at this close, though not candidate lines: L-92 (the decline-heavy interpretation set) and L-24 (the false-alarm sensitivity check) are **roadmap**; L-99 (verification line on a clarification) and L-98 (tool error text) are **committed** in the hardening bundle; L-100 (backwards date ranges) is **roadmap**; `golden_v3` and the G21 scorer comparison (L-95) are **roadmap**.
- Also placed by the owner's rulings of 2026-10-18 (not candidate lines): the default compute service account's Editor-role review is **committed** as 6.5 housekeeping (IAM only, no service redeploy); the `verify-caller` account, the no-traffic deploy (L-64), Terraform (ADR-061), the batch-scoring job (ADR-100), and the L-80 and L-77 options are **roadmap**, portfolio value, not built.

- [ ] Response transparency: live elapsed timer; after-answer timeline (route,
  per-hop durations, QA); estimated cost per answer (list price, L-71). No
  answer change; one ADR. Optional stretch: live stage streaming via A2A
  status updates.
- [ ] Cost framing: cost per answer, and "savings" only against a measured
  baseline (ADR-049 Flash vs Flash-Lite; ADR-100 stored vs query-time scoring).
- [ ] UI appearance upgrade scoped to the presentation. No answer change if
  §6 answer wording is kept.
- [ ] Executive-style analysis: option 1 deterministic "what changed" lines
  (QA-verifiable); option 2 model narrative constrained to verified facts with
  new QA checks (roadmap unless time allows). Changes answers.
- [ ] Expanded agent abilities (from the limitations log: L-68 districts/cities,
  L-67 repeat drivers by region, G04 complaint themes, L-47 monthly forecasts).
  Changes answers; likely roadmap.
- [ ] FR-03 third attempt on a freshly generated blind set (the Q/R pipeline).
  Closes the one unmet MVP requirement. Changes answers.


*Added 2026-10-14 (Z1; owner-decided 2026-10-14, "defaults"; assistant-drafted). Scope is decided at the Sprint 6 close (ADR-106); nothing here is counted in `05` or `06`.*
- [ ] **L-89: a stopped database gives the degraded result, not an error** (map the agent's `tool_error` to `DegradedResult("dependency", ...)`; a new ADR superseding the relevant part of ADR-088). Changes behaviour; it is what a grader sees outside a window.
- [ ] **The L-95 rulings:** "district" (G03) and "end of next year" (G07), as product questions. They change answers.
- [ ] **L-96: the router and decline-text fix** (a router revision stating the owner's out-of-scope rule, gated on a new set, or a decline text naming all three domains). Changes answers.

---

## Cumulative Summary
*(fill in progressively — one line per sprint, for a fast look-back when writing the evaluation report and final presentation)*

| Sprint | Goal met? | Key learning | Scope change? |
|---|---|---|---|
| 1 | Yes, 2026-09-25, two days inside the sprint | Iteration with pass bars but no stop rule consumed most of the sprint; it ended by redefining the criterion (ADR-040), an option available from the start | Yes: corpus design reshaped (ADR-036 to 041); paid, spend-capped project added (~$1.40); human review cut from 200 to 30; deliverable plan rebuilt from the course calendar |
| 2 | Yes; checkpoint 2 met 2026-09-26 (deadline 10-07); engineering complete 2026-09-30 | Tests built from the author's assumptions passed while the code was wrong; real error captures and production-config runs found both bugs | Yes: all agents on Flash-Lite after comparison (ADR-049); site region stored (ADR-051); routing prompt revised twice (ADR-053, ADR-054); repeat-visit drivers and incident-count breakdowns deferred to Sprint 3 |
| 3 | Yes, 2026-10-02, pulled forward; closed 2026-10-04 (final 2026-10-05) | Pre-registered gates on unseen data caught failures that development data hid; requirements drifted from code unnoticed until a document pass | Yes: stored predictions replaced per-request scoring; the forecast gate was corrected and disclosed; the reporting additions arrived from Sprint 2; FR-03 was attempted, failed, and carried to Sprint 5 |
| 4 | Yes, with stated limits, 2026-10-10 (day 5 of a sprint planned to 10-25) | Pre-registration held and fault injection found what the checks' author did not think of (a false alarm on a correct answer, missing small-sample checks); a check that accepts every reading where the spec is silent checks nothing (L-72); 219 of 223 caught (98.2%, an upper bound), consistent misparses 0 of 71, and 223 of 223 after fixes designed from the misses | Yes: the deploy pulled forward and finished in one day (ADR-084); the interpretation check ships advisory (L-74); QA fixes and a second measurement added (ADR-092); Sprints 5 and 6 pulled forward and the buffer kept whole (ADR-093) |
| 5 | Yes, with stated limits, 2026-10-13 (day 2 of a sprint planned to 10-25) | Both pre-registered gates failed and the frozen system shipped as it stood; the held-out run (38, 38, 38 of 50) and the golden run (29 of 36 mechanical, 31 of 36 owner) put numbers on FR-03 and the owner/drafted gap; state checks caught wrong prompt assumptions five times; budget caps per process are not a ceiling (L-93) | Yes: IAP replaced by invite links (ADR-097); sentiment served from stored predictions (ADR-100); the paid key for the deployed services (ADR-104); `ops-db` stopped between announced windows (ADR-105) |
| 6 | Partly met, closed 2026-10-18 (day 4 of a sprint planned to 10-25): the checklist is audited, 8 of 12 boxes ticked, the other four need a redeploy or a live fault; the demo rehearsal is in the buffer by plan (ADR-109) | Criteria committed before evidence and a synthetic entry to prove the alert path worked; what failed was shared context, with stale Project files and prompts that asserted facts before checking them | Yes: the 6.5 scope (ADR-113): one hardening redeploy and UI polish after `06` is submitted, and a third and final FR-03 attempt; the rest is roadmap |
