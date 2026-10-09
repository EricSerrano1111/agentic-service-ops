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

## Sprint 4 (2026-10-06 to 2026-10-25, three weeks; re-baselined, ADR-082) — Verification
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
*Planned sequence update (2026-10-08): the deploy window is done. The reporting filters (L-62) start next, from about 2026-10-09; then QA; the fault-injection harness last.*
*For `06` (due 2026-11-08), not written there: the window's failures are material for its production-support write-up: a create-body field the API rejects, a reserved path (`/healthz`) that hides the IAM boundary, identity-token minting in Cloud Build, IAM propagation delay (a new invoker binding took over a minute), and a revision failing its readiness probe while the database was stopped.*

**Planned:**
- [x] Sprint 4 backlog (2026-10-08): dispose engines in the MCP figures tests' fixtures (L-66).
  *2026-10-08: done. A pool-less, disposed engine fixture in `tests/integration/conftest.py`; the integration suite passes (883) at `max_connections=25`, where the two figures files had 11 failures before. L-66 resolved.*
- [ ] Sprint 4 backlog (2026-10-08): the trace-ID-in-access-logs follow-up PR. It needs an access-log middleware in all seven servers and a trace-ID header on the A2A and MCP clients, because the ID only reaches agents and MCP servers in the request body.
- [x] Region and account filters on the reporting tools, with a `parse_v3` update and a parse eval re-run (L-62). Built before QA, so QA's recompute is written against the filtered tools.
  *2026-10-05: added. 05 TS-01-A, TS-02-C and TS-05-B depend on it.*
  *2026-10-08: done (ADR-086, PR `feat/reporting-filters`). `region` and `account_id` filters on the four incident tools, `find_account`, `parse_v4` (the agent's default) and the clarification reasons `account_not_found` and `account_ambiguous`. Evidence: 90 integration tests against raw SQL as `app_eval` (the filtered figure equals its group's row, every metric, every region, all 50 accounts, combinations); the parse gate passed on the first candidate (`parse_v3` 15/16 in each of 3 runs, `parse_v4` 15/16 on the old items and 12/12 on the new in each of 3 runs, both unsupported areas declined in all 3), 134 of 220 calls; one end-to-end filtered question matched SQL. L-62 resolved; L-67 to L-69 recorded.*
- [ ] QA agent (ADR-055, ADR-056) — own-SQL re-check (reporting); input history, arithmetic and a per-slice lookup of the stored backtest error, not a per-request backtest run (forecast); star-rating cross-check, comment-set and confidence-flag checks (sentiment); one LLM call checks interpretation
  - [ ] Sentiment contradiction thresholds set under a stop rule (ADR-055).
- [ ] Bounded retry loop (max 2), escalation path on final failure — owned by the orchestrator (ADR-055)
- [ ] Circuit breaker, one per outbound dependency (the Gemini provider interface; each A2A client), built with the per-request deadline (ADR-077; NFR-4)
- [ ] Fault-injection harness for QA catch-rate measurement
- [ ] Price a full routing eval run (~300-700 requests, two LLM calls per request per
  ADR-046) on paid Flash-Lite using the official pricing page, and add that cost to the
  budget alongside the ~$20-30 Pro-for-QA test (ADR-029; optional, buffer only, ADR-056). ADR-041 already decided the runs
  use the paid, spend-capped project.
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
  - [x] A readiness probe alongside `/healthz`.
    *2026-10-08: `/readyz` on every MCP server and agent; compose orders startup on it.*
  - [x] Code for the deploy, built and unit-tested locally, not yet run on GCP: database host by env (TCP or Cloud SQL socket), MCP URL by env, IAM ID tokens on the card fetch and the message call, non-root images with nothing secret baked in.
    *2026-10-08.*
  - [x] Deploy config drafts in `deploy/` (v2 service definitions, `cloudbuild.yaml`, `render.py`, `verify.py`, runbook), validated locally only.
    *2026-10-08.*
  - [x] Cloud SQL major version 16, to match local Postgres (R-14 parity); record it at provisioning.
    *2026-10-08: `ops-db` is PostgreSQL 16 (see the provisioning record above).*
- [ ] Wire the per-request cost cap (§9, `MAX_COST_PER_RUN_USD`, unwired today); it matters once the QA revise loop can multiply calls.
- [x] Decide the service count and UI hosting at Sprint 4 planning. Evaluate each MCP server as a Cloud Run sidecar of its agent, and the UI as a static export served by the gateway or Cloud Storage, so no Node server runs in production.
  *2026-10-05: decided. Each MCP server is a sidecar of its agent (ADR-079); the UI is a Next.js static export served by the gateway (ADR-080).*
- [ ] Draft `05-test-scenarios.md` (carried over from Sprint 3; due 2026-11-01). Includes the FR-03 known-failing scenario.
  *2026-10-05: no longer carried over; the `05` draft stays in Sprint 3.*
  *2026-10-05: drafted and ticked under Sprint 3; nothing remains here.*
- [ ] Re-check `docs/requirements-traceability.md` at sprint close.

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
- `05-test-scenarios.md` (due 2026-11-01) and `06-production-support.md` (due 2026-11-08) now fall in Sprint 5 (ADR-082) — *(status)*
- Weekly status report due (maintained by Eric)

**Decisions made this sprint:**

*Note: scope-expansion decisions (broader capability within the existing three domains) are only appropriate if genuinely ahead of plan at this boundary — see the working agreement in `architecture.md` §13.*

---

## Sprint 5 (2026-10-26 to 2026-11-08; re-baselined, ADR-082) — Interface & evaluation
**Goal (increment):** Deployed system with a working UI; routing accuracy reported with failure analysis.

**Planned:**
- [ ] Routing eval harness + failure-case analysis (ambiguous, multi-domain, and out-of-scope intents included)
- [ ] Held-out routing set (never used to revise a prompt), written by Eric
- [ ] Golden-set items about one region or one account may have a different correct answer after ADR-086: check them at the evaluation and make a `golden_v3` with disclosure if needed (do not open the golden set before then). *Added 2026-10-08.*
- [ ] An owner-written fresh set of region and account questions for the reporting parse (the `parse_v4` set was drafted by its prompt's author, L-69), used for any later prompt change. *Added 2026-10-08.*
- [ ] Every routing eval reports k=3 runs: range and flipping items (L-17).
- [ ] FR-03 (ambiguous questions not force-routed) is open (L-58, ADR-075, ADR-076). Any
  reattempt needs a new owner-written fresh set: `fr03_fresh_v1` has now been used to
  judge `route_v5` and can't confirm a revision made after seeing its results.
  *Added 2026-10-04.*
- [ ] Rating cross-check sensitivity: flip a few percent of ratings to mimic real-world rating/text disagreement; report the QA catch rate with and without (L-24).
- [ ] QA model comparison (Flash-Lite vs `gemini-3.1-pro-preview`): optional, buffer only (ADR-056).
- [ ] FastAPI gateway + thin React UI
  - [ ] Pin Next.js to the current patched release at build time (security release scheduled 2026-09-30); verify the version then.
    *Source: https://nextjs.org/blog/tag/security. As of 2026-09-30 the patched releases are 16.3.8 (Active LTS) and 15.5.27 (Maintenance LTS).*
- [ ] Extend deployment to all services; complete Cloud SQL migration
- [ ] Re-enable the build trigger `deploy-reporting-slice` (disabled 2026-10-08, ADR-083) when the deploy is extended; the command is in `deploy/README.md`.
- [ ] Backfill `sentiment_predictions` on Cloud SQL before the sentiment service deploys (`test_golden_oracles` skips without stored predictions; the load truncates them).
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

## Sprint 6 (2026-11-09 to 2026-11-22; re-baselined, ADR-082) — Hardening & delivery
**Goal (increment):** Production-grade checklist closed out; demo rehearsed.

**Planned:**
- [ ] Observability, CI/CD completion, graceful degradation, load/latency testing (latency for a handful of concurrent users; no throughput target)
- [ ] Terraform: buffer-only stretch goal, portfolio value (ADR-061).
- [ ] A separate `verify-caller` service account holding the orchestrator invoker, so building and calling are separate identities (ADR-085).
- [ ] Deploy with no traffic, verify the revision's own URL, then move traffic, so a failed verification never serves (L-64).
- [ ] Review the default compute service account's project-level Editor role (nothing in this deploy runs as it).
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

*Note (ADR-082, 2026-10-08): this sprint is planned hardening and delivery work. The buffer is 2026-11-23 to 12-05. If Sprints 1–5 ran clean, use the slack for polish and rehearsal — not for starting anything new.*

---

## Cumulative Summary
*(fill in progressively — one line per sprint, for a fast look-back when writing the evaluation report and final presentation)*

| Sprint | Goal met? | Key learning | Scope change? |
|---|---|---|---|
| 1 | Yes, 2026-09-25, two days inside the sprint | Iteration with pass bars but no stop rule consumed most of the sprint; it ended by redefining the criterion (ADR-040), an option available from the start | Yes: corpus design reshaped (ADR-036 to 041); paid, spend-capped project added (~$1.40); human review cut from 200 to 30; deliverable plan rebuilt from the course calendar |
| 2 | Yes; checkpoint 2 met 2026-09-26 (deadline 10-07); engineering complete 2026-09-30 | Tests built from the author's assumptions passed while the code was wrong; real error captures and production-config runs found both bugs | Yes: all agents on Flash-Lite after comparison (ADR-049); site region stored (ADR-051); routing prompt revised twice (ADR-053, ADR-054); repeat-visit drivers and incident-count breakdowns deferred to Sprint 3 |
| 3 | Yes, 2026-10-02, pulled forward; closed 2026-10-04 (final 2026-10-05) | Pre-registered gates on unseen data caught failures that development data hid; requirements drifted from code unnoticed until a document pass | Yes: stored predictions replaced per-request scoring; the forecast gate was corrected and disclosed; the reporting additions arrived from Sprint 2; FR-03 was attempted, failed, and carried to Sprint 5 |
| 4 | | | |
| 5 | | | |
| 6 | | | |
