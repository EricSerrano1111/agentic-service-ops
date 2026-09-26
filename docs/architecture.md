# Architecture — Agentic Service Operations Intelligence Platform

> **Purpose of this document:** This is the standing context file for the Claude Project supporting this capstone. It defines the project, the architecture, the constraints, the decisions already locked, and the decisions still open. Read this first in any new conversation.

---

## 1. Project Identity

- **Working title:** Agentic Service Operations Intelligence Platform

- **Repo name:** `agentic-service-ops`

- **Type:** Northwestern University capstone — final project of a B.S. in Information Systems (Data Science & AI concentration)

- **Timeline:** six two-week sprints, 2026-09-14 to 2026-12-05; the final product is due 2026-12-05, the end of Module 10 (§10)

- **Target quality bar:** Enterprise/production-grade system, despite operating on synthetic data

### Owner context

Eric Serrano — Enterprise Director of Program Strategy & Operations, managing a large enterprise portfolio for a Fortune 50 aerospace client. Pivoting toward AI/ML Solutions Architecture and adjacent bridge roles (Solutions Engineer, Technical CSM). Positions himself as a bridge between complex technical systems and executive strategy, not as a pure ML engineer.

**Why this matters for the build:** This project has two audiences. The capstone rubric is one. Hiring managers for Solutions Architect roles are the other. Design decisions should serve both — which generally means favoring *defensible architectural reasoning* over raw feature count.

### Dual objectives

1. **Academic:** Satisfy the capstone rubric, including several non-engineering deliverables.
2. **Professional:** Produce a portfolio artifact that demonstrates current-practice agentic architecture — multi-agent orchestration, protocol fluency, and security-by-design — at a level that survives technical interview scrutiny.

### Project parameters (locked, course-selected)

| Parameter | Choice | Implication |
|---|---|---|
| Team structure | **Solo** | No peer review — CI, tests, and AI-assisted review must substitute. Single point of failure is a named project risk. |
| Methodology | **Agile** | Six two-week sprints, each ending in a demoable increment. Sprint artifacts are graded deliverables, not overhead. |
| Language | **Python** | Confirms the stack below; also rules out Microsoft Agent Framework as a serious option (.NET/Azure-aligned). |
| Cloud | **GCP** | Existing account, existing credits, prior Cloud Run experience. See §6 for the Azure question. |
| Budget | **~$100 target, hard ceiling low three figures** | Drives the cost architecture in §9. Non-trivial constraint — treat it as a design input. |
| Dev tooling | **Claude Pro** (development assistance) | Distinct from runtime model spend — see §9. |

**Solo + Agile is a real combination, not a formality.** Solo Agile that skips ceremony becomes undisciplined solo work with sprint labels on it. The sprint review and retrospective are where the rubric value lives: a documented "here's what I planned, here's what shipped, here's what I got wrong and adjusted" is precisely what distinguishes a graded Agile project from a Waterfall plan wearing a costume.

---

## 2. Domain & Problem Statement

A simulated enterprise service operations environment: an organization fulfilling service/product requests for customers, tracking billing on completed work, and capturing quality incidents and customer feedback.

**The problem the system solves:** Operations leaders need answers from this data — quality reporting, sentiment on customer feedback, and forward volume forecasts — without writing SQL or waiting on an analyst. The system accepts natural-language intent and routes it to specialist agents that produce verified answers.

**Why this domain:** It mirrors real enterprise service operations data models, and reflects genuine subject-matter expertise on the owner's part. This is a deliberate differentiator from generic agent demos.

---

## 3. Architecture

### Protocol stack (locked)

Three layers, following current industry practice as of late 2026:

| Layer | Protocol | Role |
|---|---|---|
| Agent coordination | **A2A** (Agent-to-Agent, v1.0) | Orchestrator delegates tasks to peer agents via Agent Cards and task lifecycle messages |
| Tool access | **MCP** (Model Context Protocol, 2026-07-28 spec) | Each agent calls its own narrowly scoped tools |
| Transport | Streamable HTTP | Backbone for both |

**Rationale for using both rather than MCP alone:** MCP is a client-tool model — call, wait, single response, caller must know the schema. A2A is peer-to-peer between autonomous agents — capability-level contracts via Agent Cards, task lifecycle (submitted / working / input-required / completed), tolerant of long-running or clarification-seeking sub-agents, and indifferent to the sub-agent's internal framework. Collapsing sub-agents into MCP "tools" would flatten them into stateless functions and tangle the tool-permission model together with the agent-trust model.

**Honest caveat to carry into interviews and the writeup:** At this scale (5 agents, one codebase, one owner), in-process orchestration would technically suffice. A2A is a *deliberate* choice to demonstrate protocol fluency and to keep the orchestration contract swappable for third-party agents later. State it that way. Do not claim it was strictly necessary — an informed interviewer will ask, and the deliberate answer is stronger than the defensive one.

### Agent topology

```
                     ┌─────────────┐
   User intent ──►   │ ORCHESTRATOR│  (intent classification + routing)
                     └──────┬──────┘
                            │ A2A
            ┌───────────────┼───────────────┐
            ▼               ▼               ▼
      ┌──────────┐   ┌──────────┐   ┌──────────┐
      │ REPORTING│   │ SENTIMENT│   │FORECAST  │
      │  AGENT   │   │  AGENT   │   │  AGENT   │
      └────┬─────┘   └────┬─────┘   └────┬─────┘
           │ MCP          │ MCP          │ MCP
           ▼              ▼              ▼
     ┌───────────┐  ┌───────────┐  ┌───────────┐
     │ MCP srv:  │  │ MCP srv:  │  │ MCP srv:  │
     │ incidents │  │ feedback  │  │ volume +  │
     │           │  │           │  │ regression│
     └───────────┘  └───────────┘  └───────────┘
      (own DB role) (own DB role)  (own DB role)

            All draft outputs ──► ┌──────────┐
                                  │ QA AGENT │ ──► pass / reject+revise
                                  └──────────┘
                                        │
                                  back to orchestrator ──► user
```

**Agents:**

- **Orchestrator** — Classifies end-user intent, routes to the appropriate specialist via A2A, and returns the specialist's verified response to the user. Handles ambiguous and out-of-scope intents gracefully, and detects questions spanning more than one domain, telling the user to ask each part separately (ADR-032).
- **Reporting/Metrics Agent** — Incident and quality metrics reporting. Figures are computed deterministically; one LLM call parses the question into a typed request (ADR-046).
- **Sentiment Agent** — Sentiment classification on freeform customer feedback text.
- **Forecast Agent** — Regression-based forward volume forecasting.
- **QA Agent** — Reviews specialist output before it returns to the user. Can accept, or reject with revision guidance.

**Explicitly out of scope:** A research/web-scraping agent. Considered and cut — no clear job to do, and scope creep at the expense of QA rigor. May be revisited only if the core system is complete and stable with time remaining.

### The QA agent — the architectural centerpiece

Most multi-agent demos stop at "delegate → respond → done." A verification stage that can reject and loop is what distinguishes a trustworthy system from an impressive-looking one, and it's a direct application of the verifiability principle: don't hope the agent got it right, architect a check.

**Critical design constraint — verification must not be circular.** The three tasks have very different verifiability profiles, and the QA agent must be built differently for each:

| Task | Verifiability | QA strategy |
|---|---|---|
| Incident metrics report | Deterministic | Re-run the query independently; assert figures match |
| Volume forecast | Standard ML | Backtest against holdout; assert error metric (RMSE/MAPE) within threshold |
| Sentiment analysis | **Weak — no natural ground truth** | Score against a labeled holdout set; flag low-confidence classifications for human review rather than asserting correctness |

The sentiment path is the trap. Do **not** have the QA agent re-run the same sentiment model and call the result verified.

### QA loop semantics (locked)

- **Bounded retries:** Maximum 2 revision cycles per request.
- **End-to-end ceiling:** No request runs longer than 120 seconds. At the ceiling, the system returns the same degraded result and escalation flag as a final QA failure (ADR-034).
- **On final failure:** Return a degraded result with an explicit warning plus a human-escalation flag. Never silently return unverified output; never loop unbounded.
- **Granularity:** QA annotates specific failed checks rather than rejecting wholesale, so revision guidance is actionable.
- This cap is a deliberate cost and latency control — document it as such.

---

## 4. Data Model

### Core tables

1. **`service_requests`** — Active/open field service engagements (installs, repairs, maintenance, inspections, upgrades).
2. **`archived_requests`** — Completed requests with final billing. 0..1 with requests — cancelled requests never archive.
3. **`incidents`** — Quality events requiring investigation, with severity and root-cause categorization.
4. **`service_feedback`** — Post-visit customer survey responses. **The sentiment agent's sole data source.**

Plus reference tables: `accounts`, `contacts`, `locations`, `technicians`, `technician_skills`, `internal_users`.

**Why incidents and feedback are separate tables.** An earlier draft combined them. That would have meant customer feedback existed only where an incident existed — so effectively all feedback would be negative. This breaks the sentiment agent twice over: the classification task becomes degenerate (always predict negative, score ~90%, learn nothing), and QA scoring against the label holdout becomes meaningless with no class balance to measure. Real field service surveys every completed job, most of which go fine. The split also makes the security boundary structural: the sentiment MCP server holds no grant on `incidents`, so internal staff-written notes can never leak into the sentiment pipeline.

**Full column-level detail lives in `data-dictionary.md`** — schema, enums, constraints, metric definitions, dataset scale, and the table-to-role access matrix.

### Ground-truth tables (critical)

5. **`sentiment_labels`** — The intended sentiment for each generated feedback record, written at generation time, keyed to `service_feedback`. **The sentiment agent never reads this table** — enforced by database grant, not code convention.
6. **`generation_parameters`** — The known true parameters used to generate the data (seasonality, trend, incident/sentiment coupling, injected anomalies, random seed). Enables forecast validation against known truth and full dataset reproducibility.

### Locked generation targets

- **History:** 36 months; ~15,000–25,000 requests
- **Forecast series:** weekly request count, all statuses, **univariate** (date → volume)
- **Signal:** Q4 peak seasonality (±25%), ~+8%/yr trend, three anomalies in the training span — account drop, regional drop, billing surcharge (ADR-038)
- **Sentiment mix:** 50% positive / 22% neutral / 20% negative / 8% mixed, with ~15% deliberately hard cases, sarcastic or implicit (ADR-036)
- **Feedback text:** drawn from the frozen, committed corpus (ADR-030); labels are specification-defined — the ADR-036 written definitions, judge-confirmed for plain comments (ADR-040)

### Synthetic data generation — the biggest technical trap

**Random data means the forecast has nothing to learn and QA has nothing to validate.** Before writing agent code, define what is *true* in this synthetic world:

- A seasonality pattern in request volume (e.g., quarterly cycle, month-end spikes)
- An underlying trend (growth/decline over the historical window)
- A plausible relationship between incident rate and negative feedback sentiment
- Injected billing and volume anomalies worth catching (three: account, regional, billing — ADR-038)
- Realistic noise on top — enough that recovery is non-trivial but achievable

Generate records *from* those parameters, persist the parameters, and validate against them. Everything downstream depends on getting this right first.

**Data provenance constraint:** All data is synthetic. Nothing derived from, resembling, or reverse-engineered from the owner's actual employer or client data. Schema structure is generic enterprise service operations; records are generated.

---

## 5. Security Model

Security is a first-class design requirement, not a section in the writeup. MCP's rapid growth has made it one of the most actively targeted surfaces in agentic AI — tool poisoning, rug pulls, and supply-chain exposure across 10,000+ public servers, with formal NSA/CISA guidance issued. This project demonstrates deliberate mitigation.

### Defense in depth — two independent layers

**Layer 1 — No raw SQL as an MCP tool.** Never expose a generic `run_query` tool, even read-only. Prompt injection via a malicious string in customer feedback text could craft a query reaching into the billing archive. Expose narrow, purpose-built functions only:

- `get_incidents_by_date_range(start, end, filters)` — reads `incidents` + `service_requests`
- `get_feedback_batch(date_range, limit)` — reads four columns of `service_feedback` only, `rating` withheld (ADR-027); no grant on `incidents` or `sentiment_labels`
- `get_order_volume_history(granularity, window)` — weekly request counts for the univariate forecast series, from three columns of `service_requests` (ADR-035)

Each scoped to exactly the tables and fields it needs. This is also a better MCP demonstration — authoring a server with a real capability boundary, not "database access."

**Refinement: three MCP servers, not one.** Rather than a single server exposing all tools, run one small MCP server per specialist domain. Each agent connects only to its own server, which holds only its own database credentials. A compromised or injection-manipulated sentiment agent has no path to the forecasting tools — not because the tool schema discourages it, but because the connection doesn't exist. Slightly more scaffolding, substantially stronger boundary, and a much better story in the security writeup.

**Layer 2 — Per-agent database roles.** Each agent gets its own least-privilege Postgres credentials. The forecast agent should be *unable* to read the feedback table at the database permission level, not merely disinclined by convention. Cheap in Postgres; makes the security narrative concrete rather than aspirational. The full table-to-role grant matrix is in `data-dictionary.md` §7.

**Notable outcome of that matrix:** no agent holds a grant on `contacts`. Customer PII never enters an LLM context window at all. That's a concrete, defensible design decision rather than a generic "we scoped permissions" claim — worth calling out explicitly in both the security writeup and interviews.

### Additional controls

- Prompt injection hardening on any path that ingests freeform customer text
- Secrets via GCP Secret Manager — no credentials in code or images
- Agent identity and scoped credentials per A2A peer
- Audit logging of every tool invocation with trace correlation

---

## 6. Technology Stack

**Decisions (revise only with reason):**

| Concern | Choice | Notes |
|---|---|---|
| Database | PostgreSQL (Cloud SQL) | Per-role permissions required; SQLite can't support the security model |
| Language | Python | Matches existing portfolio and coursework |
| MCP | Official Python SDK, 2026-07-28 spec — **`mcp==2.2.0`** (pinned 2026-09-25, ADR-047) | Stateless core, HTTP-native transport. **Three servers, one per specialist domain** |
| A2A | A2A v1.0 SDK — **`a2a-sdk==1.1.5`** (pinned 2026-09-25, ADR-047) | Agent Card discovery + blocking `SendMessage` only; no streaming, push or `input-required` (ADR-047) |
| Agent runtime | LangGraph per agent | Internal to each agent; A2A makes this swappable |
| Runtime LLM | **Gemini API free tier** (primary); Flash-Lite default | Model-agnostic by design — see §9 and ADR-029. A separate paid, spend-capped project runs corpus generation and the Sprint 5 eval runs (ADR-041) |
| Forecasting | scikit-learn / statsmodels | Lean regression — deliberately simple and explainable |
| Feedback corpus (offline, one-off) | `gemini-3.5-flash-lite` writes, `gemma-4-31b-it` judges plain labels | Frozen, committed corpus; `generate.py` never calls an API (ADR-030, ADR-036, ADR-041) |
| ORM + migrations | SQLAlchemy 2.0 + Alembic, psycopg 3 | Models in `packages/db_models/` (ADR-026); migrations are frozen snapshots (ADR-027) |
| CI | GitHub Actions | Lint (ruff), offline unit tests, and integration against a Postgres 16 service container (live since 2026-09-25) |
| Sentiment | Fine-tuned transformer classifier (BERT), trained on `sentiment_labels` (ADR-024) | Softmax confidence for QA thresholding |
| API layer | FastAPI | |
| UI | Thin React/Next.js front end | See note below |
| Containers | Docker + docker-compose (local), Cloud Run (deployed) | |
| Cloud | GCP — Cloud Run, Cloud SQL, Secret Manager, Artifact Registry, Cloud Build | |

**Topology (locked):** Monorepo, separate service processes per agent, orchestrated locally by docker-compose and deployed as distinct Cloud Run services. A2A implies separate processes with their own endpoints and Agent Cards — honor that. Switching topology mid-project is painful; decide once.

**UI note:** Streamlit is faster to build but reads as a prototype. A thin React/Next.js front end over the FastAPI layer better supports the production-grade claim and the Solutions Architect narrative. Keep it deliberately minimal — intent input, response display, QA status indicator, escalation flag. The UI is a window into the architecture, not the project.

**GCP vs Azure — decided: GCP.** Azure has a larger enterprise footprint and its agent tooling is well-aligned to Microsoft-stack shops, so the question was fair. But: the existing account and credits are worth real money against a $100 budget, prior Cloud Run experience is worth real weeks against a 12-week timeline, and the Microsoft-aligned agent framework is .NET-oriented, which conflicts with the locked Python choice anyway. The concern about "industry standard" is better neutralized architecturally than by cloud selection — containerize everything and define infrastructure in Terraform, then the honest claim is *"deployed on GCP, portable by design,"* which is a stronger Solutions Architect answer than having picked whichever cloud the interviewer happens to use. Revisit only if targeting a specifically Microsoft-stack employer.

**Deployment note:** A prior Cloud Run project hit a decoupled build/deploy pipeline — successful Cloud Builds not producing active revisions. Wire continuous deployment explicitly this time (Cloud Build trigger → deploy step, not just image push) and verify revision promotion early rather than at submission.

---

## 7. Definition of "Production-Grade"

"Production-grade" is the phrase most likely to be hand-waved at submission. It is pinned here to a concrete artifact checklist. Deliver these, or explicitly scope one out with a documented reason — a defensible "deferred because X" reads better than a vague claim.

- [ ] Containerized services, reproducible builds *(in progress: the three skeleton services have Dockerfiles and run in docker-compose; dependencies other than the protocol SDKs are not yet locked, ADR-047)*
- [ ] Config and secrets management — no hardcoded credentials
- [ ] Structured logging with trace IDs correlated across agent hops *(in progress: JSON lines with one trace id across orchestrator → A2A → agent → MCP, `packages/common`; asserted by the e2e test)*
- [ ] Health checks and readiness probes on every service *(in progress: `/healthz` liveness on the skeleton services, used by compose; no readiness probe yet)*
- [ ] Bounded retries, timeouts, and circuit-breaking on all inter-agent calls, within a 120-second end-to-end ceiling (ADR-034)
- [ ] Graceful degradation — defined behavior when any specialist agent is unavailable
- [ ] Test suite — unit and integration *(in progress: offline unit suite and the live grants integration suite exist, both in CI)*
- [ ] Eval harness (see below)
- [ ] CI pipeline *(CI skeleton live 2026-09-25: lint, unit, integration; CD first for the reporting slice in Sprint 4 (ADR-045), completed in Sprints 5–6)*
- [x] Least-privilege database roles per agent *(Sprint 1: five roles, grants asserted by the integration suite in CI — ADR-023, ADR-027, ADR-035)*
- [ ] API cost guardrails and per-run caps
- [ ] README with architecture diagram and local setup that actually works from clean

---

## 8. Evaluation Strategy

Unit tests are not enough. The orchestrator's job is intent classification — the component most likely to silently degrade.

### Routing eval harness (highest-value artifact)

Build a labeled set of test intents with expected routing outcomes, deliberately including:

- Clear single-agent intents
- **Ambiguous intents** ("how are we doing on quality?")
- **Multi-domain intents** spanning more than one specialist, expected to be detected and returned with a split instruction rather than routed (ADR-032)
- **Out-of-scope intents** that should be declined rather than force-routed

Report routing accuracy across N test intents with a documented failure-case analysis. *"Routing accuracy is X% across N intents, here are the failure modes and what I changed"* is the single most interview-ready sentence this project can produce.

### Other evals

- **Forecast:** RMSE/MAPE against holdout, compared to a naive baseline (seasonal naive). A model that doesn't beat the baseline is a finding worth reporting honestly.
- **Sentiment:** Precision/recall/F1 against the `sentiment_labels` holdout, scored against specification-defined labels (ADR-040); neutral reported per kind (minimal, administrative, status) and hard cases per type (sarcastic, implicit) with the judge disagreement rates alongside; calibration of the confidence threshold used for human-review flagging.
- **QA agent:** Catch rate on deliberately injected faulty outputs. Inject known-bad results and measure detection.
- **End-to-end:** Latency and token cost per request type.

---

## 9. Budget & Cost Architecture

**Target: ~$100 total. Treat this as a design constraint, not an afterthought.**

### Critical clarification: Claude Pro ≠ runtime model access

Claude Pro covers the development assistance side — chat, and Claude Code via subscription. It does **not** include API access; API usage is billed separately through the Console and a Pro subscription provides no discount on it. So:

- **Development assistance** (design, code, review, writing): Claude Pro — already paid for, $0 marginal.
- **Runtime inference** (what the five agents actually consume in production): a separate, metered cost that must be budgeted.

This distinction is easy to miss and would blow the budget if discovered in week 9.

### Runtime model strategy

Use **Gemini on the free API tier** (Google AI Studio key) as the primary runtime model for all five agents — student credits are confirmed not available (ADR-029). Every agent defaults to Gemini 3.5 Flash-Lite (`gemini-3.5-flash-lite`) during development and moves to a Flash-class model only where Flash-Lite measurably underperforms. Keep every agent **model-agnostic behind a provider interface** — the A2A/MCP layering already makes this natural, and it converts a budget constraint into an architectural selling point ("swap providers without touching orchestration"). In Sprint 5, compare QA catch rate across two candidates: Flash-Lite (the baseline) and `gemini-3.1-pro-preview` (paid, preview, run in a separate spend-capped project) — that comparison is itself a good results-section finding.

**Paid project (ADR-041).** A separate paid project, `A2A-agentic-service-ops-gcp`, with its own API key, holds all paid inference: it finished the feedback corpus generation (~$1.40 estimated) and will run the Sprint 5 Pro-for-QA test and paid eval runs. It is capped by a $5 prepaid balance with auto-reload off, a $10 project budget alert, and a per-session request cap enforced in code; the existing project stays on the free tier, since a project upgraded to paid is billed for all of its usage (ADR-029).

### Infrastructure cost plan

| Item | Approach | Est. |
|---|---|---|
| Postgres | **Local Docker through Sprint 3.** Cloud SQL from Sprint 4 for the reporting slice, smallest instance, stopped when idle; all services from Sprint 5 (ADR-045) | ~$10–15 total |
| Cloud Run (7 services) | Scale-to-zero, min-instances=0; free tier absorbs demo traffic | ~$0–5 |
| Artifact Registry / Cloud Build / Secret Manager | Free tier | ~$0–3 |
| Runtime LLM | Gemini API free tier; separate spend-capped paid project (ADR-041) for corpus generation (done, ~$1.40), the Sprint 5 Pro-for-QA test and paid eval runs | ~$1.40 spent; Pro test ~$20–30 incl. thinking tokens, drawn from buffer |
| Buffer | Overruns, a stronger QA model, demo-day headroom | ~$40 |

**The Cloud SQL timing is the key move.** An always-on managed Postgres instance running all 12 weeks would consume roughly a third of the budget for no benefit during local development. Develop against Docker Postgres, migrate to Cloud SQL when deployment work actually begins (the Sprint 4 reporting slice, ADR-045; storage bills while the instance is stopped), and keep the schema migration path (Alembic) identical for both so the switch is trivial.

### Runaway-cost guardrails

- Hard per-run token/cost cap, enforced in code — QA loops fan out usage fast
- **Model tiering, only where measured:** every agent starts on Flash-Lite and moves up (Flash; Pro for QA as a Sprint 5 test) only when an eval shows Flash-Lite underperforming (ADR-029)
- Aggressive caching of static context (schemas, tool definitions, system prompts) separate from dynamic context
- Cost logging per request, surfaced in the eval harness
- Development-mode circuit breaker on cumulative spend
- GCP budget alert at $50 and $80 — set in Sprint 1 (2026-09-24), plus a $10 alert and a $5 prepaid cap on the paid project (ADR-041)

**Context engineering note:** Model correctness degrades well before context limits are reached — meaningful degradation appears around 32k tokens, with information buried mid-context getting ignored. Curate minimum high-signal context per agent. Place critical instructions at the beginning or end, never the middle. Use just-in-time retrieval rather than pre-loading.

---

## 10. Sprint Plan (6 × 2-week sprints)

Every sprint ends with a **demoable increment** and a **sprint review + retro entry** in `sprint-log.md`. Academic deliverables are interleaved, not bolted on at the end. Risk register is reviewed and updated every sprint boundary.

**Calendar.** Sprint 1 started Monday 2026-09-14. **The final product is due 2026-12-05, the end of Module 10.** Academic deliverables are the numbered files in `docs/academic/`, with due dates taken from each file; a weekly status report (`00-Weekly-Status-Reports.md`) is also due every week through 2026-11-22.

| Sprint | Dates | Academic deliverables due |
|---|---|---|
| 1 | 2026-09-14 to 09-27 | `01-proposal-business-case.md` (09-27) — complete; weekly status report |
| 2 | 2026-09-28 to 10-11 | `02-requirements-analysis.md` (10-04) — completed early, in Sprint 1; weekly status reports |
| 3 | 2026-10-12 to 10-25 | `03-planning-management.md` (10-18); `04-design-solution-architecture.md` (10-18); weekly status reports |
| 4 | 2026-10-26 to 11-08 | `05-test-scenarios.md` (11-01); `06-production-support.md` (11-08); weekly status reports |
| 5 | 2026-11-09 to 11-22 | Weekly status reports (the last covers the week ending 11-22) |
| 6 | 2026-11-23 to 12-05 | Final submission (12-05): presentation plus the completed project (ADR-044) |

### Sprint 1 (weeks 1–2, 2026-09-14 to 09-27) — Foundation
**Increment:** Synthetic data generator producing validated, signal-bearing data; queryable locally.
- Repo scaffold, CI skeleton, docker-compose, local Postgres
- Schema + generation parameters defined and documented
- Data generator + ground-truth tables (`sentiment_labels`, `generation_parameters`)
- Validate the signal actually exists — plot it, confirm seasonality and correlation are recoverable
- GCP budget alerts configured
- **Academic:** `01-proposal-business-case.md` (due 09-27); weekly status report

### Sprint 2 (weeks 3–4, 2026-09-28 to 10-11) — First vertical slice
**Increment:** Ask a natural-language incident question; the orchestrator routes it over A2A to the reporting agent, which answers through the incidents MCP server; an e2e test confirms the figures match an independent SQL computation. *(Reworded at planning, 2026-09-25: the QA agent is Sprint 4.)*
- MCP server #1 (incidents) with scoped tools + dedicated DB role
- Reporting agent + A2A Agent Card; question parsing per ADR-046
- `packages/llm` (429 handling, token metering)
- Minimal orchestrator: classification and routing to a single agent
- **Academic:** `02-requirements-analysis.md` (due 10-04; completed in Sprint 1); weekly status reports

*This is the most important sprint. It proves the entire MCP → A2A → orchestrator path on the simplest possible task, while there's still time to be wrong about the stack. Everything after is repetition and refinement.*

### Sprint 3 (weeks 5–6, 2026-10-12 to 10-25) — Analytical agents
**Increment:** All three specialists working; forecast beats a naive baseline or the gap is documented.
- MCP servers #2 and #3, forecast agent + regression, sentiment agent + confidence scoring
- Orchestrator routes across all three
- Golden set and labelled routing set (ambiguous, multi-domain, out-of-scope, technician-level), feeding `05`
- Fill `security-model.md` while drafting `04`; draft `05` in week 2 (10-19 to 10-25)
- **Academic:** `03-planning-management.md` and `04-design-solution-architecture.md` (both due 10-18); weekly status reports

### Sprint 4 (weeks 7–8, 2026-10-26 to 11-08) — Verification
**Increment:** QA agent operational with all three verification strategies; measurable catch rate.
- QA agent, bounded retry loop, escalation path
- Fault injection harness for QA catch-rate measurement
- Minimal Cloud Run deploy of the reporting slice (orchestrator, `agent_reporting`, `mcp_incidents`) with Cloud SQL, 2026-11-02 to 11-04, timeboxed to 3 days; revision-serving check; stop rule per ADR-045
- **Academic:** `05-test-scenarios.md` (due 11-01); `06-production-support.md` (due 11-08); weekly status reports

### Sprint 5 (weeks 9–10, 2026-11-09 to 11-22) — Interface & evaluation
**Increment:** Deployed system with a working UI; routing accuracy reported with failure analysis.
- Routing eval harness + failure-case analysis
- FastAPI gateway + thin React UI
- Extend deployment to all services; complete Cloud SQL migration; **verify revision promotion on every deploy**
- **Academic:** weekly status reports (last one covers the week ending 11-22)

### Sprint 6 (weeks 11–12, 2026-11-23 to 12-05) — Hardening & delivery
**Increment:** Production-grade checklist closed out; demo rehearsed.
- Observability, CI/CD completion, graceful degradation, load/latency testing
- Production-grade checklist (§7) audited item by item
- Evaluation report (`docs/evaluation-report.md`) from the Sprint 5 eval runs, presentation, demo rehearsal (ADR-044)
- **Academic:** final submission due 2026-12-05 (end of Module 10): presentation plus the completed project (ADR-044)

**Protect Sprint 6.** It is genuine buffer, not planned work with a buffer label. Scope expansion (broader capability within the existing three domains — not new agents, not the research agent) requires being genuinely ahead at the Sprint 4 boundary.

---

## 11. Repository Layout

Monorepo, separate service processes. Installed with pip today (editable installs, as CI does); the root `pyproject.toml` is already shaped as a uv workspace.

```
agentic-service-ops/
├── README.md                      # architecture diagram, clean-machine setup
├── pyproject.toml                 # workspace root
├── docker-compose.yml             # full local stack incl. Postgres
├── Makefile                       # make dev / test / eval / deploy
├── .env.example
├── .github/workflows/ci.yml
│
├── docs/
│   ├── architecture.md
│   ├── security-model.md           # placeholder — filled while drafting `04` in Sprint 3
│   ├── evaluation-report.md        # Sprint 6: results and limitations (ADR-044)
│   ├── data-dictionary.md
│   ├── risk-register.md            # updated every sprint boundary
│   ├── sprint-log.md               # planning, review, retro per sprint
│   ├── decisions-log.md            # ADR — single running file for architectural decisions
│   └── academic/                   # course deliverables (numbered, due dates in §10)
│       ├── 00-Weekly-Status-Reports.md        # rolling weekly report, maintained by Eric only
│       ├── 01-proposal-business-case.md       # submitted; reference copy kept factually in sync
│       ├── 02-requirements-analysis.md        # submitted; reference copy kept factually in sync
│       ├── 03-planning-management.md
│       ├── 04-design-solution-architecture.md
│       ├── 05-test-scenarios.md
│       └── 06-production-support.md
│
├── infra/
│   ├── terraform/                  # Cloud Run, Cloud SQL, IAM, Secret Manager
│   └── cloudbuild/                 # build + deploy triggers (not just image push)
│
├── data/
│   ├── generator/                  # synthetic data generation from known params
│   │   ├── parameters.py           # the ground truth of this synthetic world
│   │   ├── build_corpus.py         # one-off: LLM writes feedback_text (ADR-030)
│   │   ├── prompts/                # versioned generator + judge prompts (generator_v4.txt, judge_v4.txt)
│   │   ├── experiments/            # model bake-off, prompt rounds, corpus test batch (evidence)
│   │   ├── corpus/                 # committed: feedback_text.jsonl, provenance.json, rejected.jsonl
│   │   │   └── work/               # gitignored: stage files, raw responses, request counts
│   │   ├── reference_data.py       # committed name, place, timezone and note-phrase lists (ADR-042)
│   │   ├── generate.py             # reads the frozen corpus; never calls an API
│   │   ├── load.py                 # one-transaction reload into Postgres as app_generator (ADR-042)
│   │   ├── validate.py             # confirms signal is recoverable; rechecks corpus integrity
│   │   └── validation/<date>/      # committed validate.py output: report.json, plots, spot_check.csv
│   └── migrations/                 # Alembic — identical local ↔ Cloud SQL
│
├── packages/                       # shared libraries
│   ├── db_models/                  # SQLAlchemy models, 22 vocabularies, §7 access matrix (ADR-026)
│   ├── common/                     # config, structured logging, trace IDs, errors
│   ├── a2a_core/                   # Agent Card helpers, task lifecycle client/server
│   ├── llm/                        # provider-agnostic model interface + cost metering
│   └── schemas/                    # Pydantic contracts shared across services
│
├── services/
│   ├── orchestrator/ # intent classification + A2A routing
│   │
│   ├── agent_reporting/ # deterministic figures; one LLM call parses the question (ADR-046)
│   │
│   ├── agent_sentiment/
│   │   ├── training/
│   │   │   └── train.py # fine-tunes BERT model on sentiment_labels
│   │   └── models/ # trained artifact — gitignored, not committed
│   │
│   ├── agent_forecast/
│   │   ├── training/
│   │   │   └── train.py # fits the regression on weekly volume history
│   │   └── models/ # trained artifact — gitignored, not committed
│   │
│   ├── agent_qa/ # deterministic — no model
│   │
│   ├── mcp_incidents/ # scoped tools + own DB role
│   ├── mcp_feedback/
│   ├── mcp_volume/
│   └── api_gateway/ # FastAPI BFF for the UI
│       └── (each service: Dockerfile, pyproject.toml, src/, tests/)
│
├── web/                            # thin React/Next.js UI
│
├── evals/
│   ├── routing/
│   │   ├── intents.yaml            # labeled test intents incl. ambiguous + OOS
│   │   └── run.py
│   ├── forecast/                   # backtest vs. seasonal-naive baseline
│   ├── sentiment/                  # scored against sentiment_labels holdout
│   ├── qa/                         # fault injection + catch rate
│   └── results/                    # dated eval runs — evidence for the evaluation report (ADR-044)
│
└── tests/
    ├── unit/                       # offline contract, generator and corpus tests
    ├── integration/                # live grants suite (needs a migrated Postgres)
    └── e2e/
```

**Notes on the layout:**

- `agent_sentiment/models/` and `agent_forecast/models/` hold trained artifacts, not source — gitignored (`**/models/*.bin`, `**/models/*.pt`, `**/models/*.joblib` or equivalent). A transformer checkpoint can exceed 100MB; it has no business in git history. `training/train.py` in each is what produces the artifact — run deliberately, not something any agent triggers.
- `data/generator/corpus/` is committed, unlike trained-model artifacts: it is the frozen `feedback_text` corpus and its provenance record, written once by `build_corpus.py`. `generate.py` reads it and never calls an API, so a normal generation run is reproducible from the seed alone (ADR-030).
- `packages/llm/` exists specifically to keep the provider swap cheap and to centralize cost metering — both budget requirements from §9.
- `evals/results/` being version-controlled and dated matters: the evaluation report's results section (ADR-044) should cite real dated runs, not numbers retyped from memory.
- `docs/decisions-log.md` is where the "why" lives. Given that a large share of this project's interview value is architectural reasoning rather than code, this is arguably the highest-value file in the repo.
- Each service owns its Dockerfile and tests. Resist the urge to centralize — it undermines the "these are independently deployable peers" claim.
- Per-ADR files were deliberately collapsed into one running `decisions-log.md` — a folder-per-decision only pays for itself with multiple contributors, and this is a solo project.

### Companion files for the Claude Project

This document is the standing context. Alongside it:

| File | Purpose |
|---|---|
| `architecture.md` | This file — architecture, constraints, decisions |
| `sprint-log.md` | Sprint planning, review, retro entries |
| `risk-register.md` | Risks, likelihood/impact, mitigations, status |
| `decisions-log.md` | Running ADR summary — single file, `docs/decisions-log.md` |
| `data-dictionary.md` | Schema, fields, generation parameters |

Keep this context file updated as decisions change. A stale context document is worse than none — it will confidently mislead.

---

## 12. Open Decisions

**Schema decisions are now settled** — see the decisions log in `data-dictionary.md` §10 (table split, BIGINT keys, skills join table, SLA snapshotting, forecast target, sentiment distribution, enum lock, severity coupling).

Remaining:

- [x] Reconcile the milestone plan against the course calendar — done 2026-09-25: actual deliverables and due dates mapped to sprints in §10 (R-09)
- [ ] Check each deliverable's rubric content when drafting starts (R-09)
- [x] Final repo/project name — `agentic-service-ops` (closed 2026-09-25)
- [x] Sentiment approach — fine-tuned transformer classifier (BERT) trained on `sentiment_labels` (ADR-024)
- [x] Specific model/provider selection per agent tier — Flash-Lite for all agents during development (ADR-029)
- [x] Historical data window and granularity for the forecast — 36 months, weekly, univariate (ADR-018)
- [x] Whether the UI supports conversational follow-up or single-shot intents — single-shot committed; multi-turn only as a scope expansion decided at the Sprint 4 boundary (ADR-031)
- [x] Confirm what the Google AI student credits actually cover and their expiry — confirmed not available; runtime moved to the free tier (ADR-029)
- [ ] Whether to route the QA agent to a stronger model late in the project as a measured comparison — scheduled as a Sprint 5 QA comparison of Flash-Lite (baseline) and `gemini-3.1-pro-preview` on the paid, spend-capped project (ADR-029, ADR-041); decided by that measurement
- [ ] Sprint ceremony cadence and whether the instructor expects to see sprint artifacts at specific checkpoints *(partly known: a weekly status report is due every week through 2026-11-22)*

---

## 13. Working Agreement for This Project

- **Frank, direct feedback over encouragement.** Flag weak reasoning, scope creep, and hand-waving explicitly.
- Push back on architectural decisions that are fashionable rather than justified.
- When something is deferred or cut, document *why* — the reasoning is a deliverable.
- Distinguish what's genuinely required at this scale from what's demonstrated deliberately for portfolio value. Never let the two blur in the writeup.
- Protect the schedule buffer. Scope expansion requires being genuinely ahead, not optimistic.
