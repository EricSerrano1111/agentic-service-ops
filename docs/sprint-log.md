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
- [ ] Validate signal is actually recoverable — plot seasonality, confirm sentiment/severity coupling shows up in the data
- [ ] GCP budget alerts configured ($50, $80)
- [x] Confirm Google AI student credit coverage and expiry (open item from ADR-006) — *confirmed not available; free tier adopted (ADR-029, 2026-09-22)*

**Shipped:**
- Python packaging foundation: root `pyproject.toml` (uv-workspace-shaped, pip-installable today) and `packages/db_models` as the first workspace package.
- `packages/db_models/` — SQLAlchemy 2.0 models for all 12 tables, the 21 controlled vocabularies as `StrEnum`, and the §7 access matrix as an importable data structure.
- Alembic under `data/migrations/`, building its connection string from `POSTGRES_*` environment variables so the Sprint 5 Cloud SQL switch is a config change (ADR-007).
- Two migrations: initial schema (tables, FKs, CHECK constraints, the §9 indexes) and the five least-privilege roles with the §7 grants.
- `docker-compose.yml` with Postgres 16.
- 34 contract tests covering the schema, the access matrix, and the roles migration's credential handling, running without a database.
- `alembic upgrade head` run against local Postgres (both migrations applied); `alembic check` reports "No new upgrade operations detected." The hand-written initial migration now matches the models, including column types and server defaults.
- Grants integration test (`tests/integration/test_access_matrix_grants.py`, 301 cases): logs in as each of the five roles with its `.env` credentials and checks reads on every table, plus every column of `service_feedback`, and INSERT/UPDATE/DELETE on every table (the generator can write everywhere, no agent role anywhere), all against `db_models.access_matrix`. Write probes touch zero rows. Checked by drifting the matrix in memory both ways (an extra grant, a missing grant) and confirming exactly the right cases fail. Skips when no database is reachable.
- `app_sentiment` tightened to a column-level grant on `service_feedback` (`feedback_id`, `request_id`, `submitted_at`, `feedback_text`), so `rating` stays an independent QA cross-check (R-04). Applied by a new migration, `1ee8342c81a7`.
- Roles-and-grants migration frozen to a literal snapshot of its original matrix instead of importing the live one (ADR-027). Verified by upgrading a fresh database to that revision (sentiment still had its original table-level grant) and then to head, with `alembic check` and both test suites green.
- Docs: ADR-025 added; three corrections to `data-dictionary.md` that writing the DDL exposed.

**Carried over:**
*(fill in at sprint end)*

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
- ADR-029 — runtime inference on the Gemini API free tier, Flash-Lite default for all agents (supersedes ADR-006 in part); Pro-for-QA deferred to a spend-capped Sprint 5 test.

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
- [ ] Routing eval harness + failure-case analysis (ambiguous + out-of-scope intents included)
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
