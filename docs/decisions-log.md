# Decisions Log — Agentic Service Operations Intelligence Platform

**Purpose:** The permanent record of *why*, kept separate from `architecture.md` (the current *what*). When a decision changes, don't edit its entry here — add a new one marked "Supersedes ADR-XXX." The trail of reasoning is the point.

**Format:** Decision → Context → Alternatives considered → Consequences.

**Note on dates:** entries below were compiled retroactively from planning conversations rather than logged in real time, so per-entry dates aren't tracked. New entries from this point forward should include one. Numbering reflects the order decisions were actually made.

---

## Index

| # | Decision | Status |
|---|---|---|
| 001 | A2A + MCP two-protocol architecture | Accepted |
| 002 | Cut the research/scraping agent | Accepted |
| 003 | QA agent as a verification stage, not a formality | Accepted |
| 004 | Solo / Agile / Python project parameters | Accepted (course-selected) |
| 005 | GCP over Azure | Accepted |
| 006 | Claude Pro for development; Gemini credits for runtime inference | Accepted |
| 007 | Cloud SQL deferred to Sprint 5; local Docker Postgres before | Accepted |
| 008 | Three MCP servers, one per specialist domain | Accepted |
| 009 | React over Streamlit for the UI | Accepted |
| 010 | Reporting agent built first, in Sprint 2 | Accepted |
| 011 | Monorepo, separate service processes | Accepted |
| 012 | Domain: field service dispatch (network/hardware technicians) | Accepted |
| 013 | Schema built from general domain principles, not employer's system | Accepted |
| 014 | `incidents` and `service_feedback` split into separate tables | Accepted |
| 015 | BIGINT identity surrogate keys, not UUID | Accepted |
| 016 | `technician_skills` join table, not a delimited string | Accepted |
| 017 | SLA window snapshotted onto the request, not looked up live | Accepted |
| 018 | Forecast: weekly, univariate, all statuses, 36-month history | Accepted |
| 019 | Sentiment distribution: 50/22/20/8, 15% deliberately hard | Accepted |
| 020 | Enums as VARCHAR + CHECK; `upgrade` added to `service_type` | Accepted |
| 021 | Incident severity influences sentiment, with noise | Accepted |
| 022 | QA retries bounded at 2, then escalate | Accepted |
| 023 | Per-agent least-privilege DB roles + narrow MCP tools | Accepted |
| 024 | Trained models behind sentiment and forecast tools; training is offline | Accepted |
| 025 | Grant enforcement details: column-level feedback grant, PUBLIC revoked, cross-table invariant left to QA | Accepted |
| 026 | SQLAlchemy models separate from Pydantic schemas | Accepted |
| 027 | Sentiment reads `service_feedback` by column, `rating` withheld; migrations are frozen snapshots | Accepted — supersedes ADR-025 in part |
| 028 | Role names required, never defaulted: a blank `DB_ROLE_*_USER` fails like a blank password | Accepted |
| 029 | Runtime inference on the Gemini API free tier; Flash-Lite default for all agents | Accepted — supersedes ADR-006 in part |
| 030 | `feedback_text` LLM-generated once and frozen as a committed corpus | Accepted |
| 031 | Single-shot interaction committed; multi-turn is conditional stretch | Accepted |
| 032 | Compound routing out of scope; multi-domain questions detected and split by the user | Accepted |
| 033 | Metrics reportable per individual technician, framed as decision support | Accepted |
| 034 | 120-second end-to-end timeout ceiling; latency measured, not targeted | Accepted |
| 035 | Forecast agent narrowed to three columns of `service_requests` | Accepted |
| 036 | Feedback corpus design: models, label definitions, cell rules, judge-confirmed plain labels | Accepted — supersedes ADR-019, ADR-021 and ADR-030 in part |
| 037 | `sentiment_labels`: `hard_case_type` replaces `is_sarcastic`; `corpus_id` added | Accepted |
| 038 | Generator parameters: text on every feedback row, anomalies, coherence rules, corpus sizing, param_group values | Accepted |
| 039 | Positive feedback on incident rows uses no-incident positive comments | Accepted — supersedes ADR-036 in part |
| 040 | Sentiment labels defined by the written specification; human review becomes a sanity check | Accepted — supersedes ADR-036 in part |

---

### ADR-001 — A2A for agent coordination, MCP for tool calling
**Decision:** Use both protocols, layered — A2A for orchestrator-to-specialist delegation, MCP for each specialist's own tool calls. Not MCP alone for everything.
**Context:** MCP is a client-tool model — one caller, a known schema, call-and-wait. A2A is peer-to-peer between autonomous agents — capability contracts via Agent Cards, a task lifecycle, no assumption of shared framework or internal visibility.
**Alternatives considered:** MCP-only, wrapping each sub-agent as a callable tool (rejected — flattens autonomous agents into stateless functions, loses the ability to stream progress or ask clarifying questions, tangles the tool-permission model together with the agent-trust model). In-process orchestration with no protocol at all (rejected as the primary design, but acknowledged as honestly sufficient at this scale — see consequences).
**Consequences:** At 5 agents in one codebase, A2A's overhead isn't strictly necessary — this is a deliberate choice to demonstrate protocol fluency and keep the orchestration contract swappable, not a claim of necessity. State it that way in interviews and the writeup, not as "A2A was required."

### ADR-002 — Cut the research/scraping agent
**Decision:** No web-scraping/research agent in the initial build.
**Context:** Originally proposed alongside the QA agent as a "nice to have." Reviewed against the actual task set (reporting, forecasting, sentiment) and found to have no defined job — nothing in scope needs external web data.
**Alternatives considered:** Keep it scoped narrowly to one purpose, e.g. pulling an external industry SLA benchmark to contextualize the forecast (left open as a possible late addition, not committed).
**Consequences:** Time redirected to QA rigor instead. May be revisited only if the core system is complete and stable with sprint time remaining — not before.

### ADR-003 — QA agent as a genuine verification stage
**Decision:** Build a QA agent that reviews every specialist's draft output before it reaches the orchestrator, with the authority to reject and trigger revision — not just log a result.
**Context:** Most multi-agent demos stop at "delegate → respond → done." A rejection-capable verification stage is what demonstrates the verifiability principle in practice rather than just asserting outputs are correct.
**Alternatives considered:** No QA stage (rejected — the single biggest missed differentiator in typical agent portfolio projects). QA that only logs/flags without blocking (rejected — doesn't meaningfully change what the user receives).
**Consequences:** Verification strategy differs by task, since the three tasks aren't equally verifiable (deterministic query re-run for reporting, backtest error threshold for forecasting, labeled-holdout scoring for sentiment — see ADR-019). This asymmetry has to be designed for explicitly, not treated as one generic "QA check."

### ADR-004 — Solo, Agile, Python (course-selected parameters)
**Decision:** Solo project, Agile methodology (six two-week sprints), Python throughout.
**Context:** Course-level choices, not derived from the architecture — but each has downstream implications: solo means no peer review, so CI/tests/AI-assisted review substitute; Agile means sprint reviews and retros are graded deliverables, not overhead; Python rules out the Microsoft Agent Framework (.NET-oriented) as a serious option.
**Alternatives considered:** N/A — course-level selection.
**Consequences:** Solo + Agile only has value if the ceremony is real. A documented "planned X, shipped Y, got Z wrong and adjusted" each sprint is what separates a graded Agile project from a Waterfall plan wearing a costume.

### ADR-005 — GCP over Azure
**Decision:** Build and deploy on GCP.
**Context:** Azure has stronger enterprise/agent-tooling alignment in some circles, and the "check industry standard" question was raised deliberately, not casually.
**Alternatives considered:** Azure (rejected — existing GCP account and credits are worth real money against a ~$100 budget; prior Cloud Run experience is worth real weeks against a 12-week timeline; Microsoft's agent framework is .NET-aligned, which conflicts with the Python decision anyway).
**Consequences:** Neutralize the "industry standard" concern architecturally instead of by cloud choice — containerize everything, define infrastructure in Terraform. The claim becomes "deployed on GCP, portable by design," which is a stronger Solutions Architecture answer than having picked whichever cloud an interviewer happens to use.

### ADR-006 — Claude Pro for development; Gemini via Google AI credits for runtime
**Decision:** Development assistance runs on the existing Claude Pro subscription. Runtime inference for all five agents runs on Gemini, billed against existing Google AI (student) credits.
**Context:** Claude Pro does not include API access — API usage bills separately with no subscriber discount. Conflating the two would have silently consumed the ~$100 budget through runtime inference, the cost center a solo Agile QA-loop system generates fastest.
**Alternatives considered:** Claude API for runtime (rejected on cost grounds given the budget ceiling — revisit only if credits run out or a specific comparison, e.g. QA catch-rate by model, justifies it).
**Consequences:** Every agent is built behind a provider-agnostic interface (`packages/llm/`), converting the budget constraint into an architectural talking point — "swap providers without touching orchestration." Confirm what the Google AI student credits actually cover and when they expire; this assumption underwrites the entire runtime budget (open item).

### ADR-007 — Local Docker Postgres through Sprint 4; Cloud SQL from Sprint 5
**Decision:** Don't provision Cloud SQL until deployment work actually begins.
**Context:** An always-on managed Postgres instance running the full 12 weeks would consume roughly a third of the total budget for no benefit during local development.
**Alternatives considered:** Cloud SQL from day one (rejected — pure cost with no corresponding benefit before Sprint 5).
**Consequences:** Schema migrations (Alembic) must be written identically for both environments from the start, so the Sprint 5 switch is a config change, not a rewrite.

### ADR-008 — Three MCP servers, one per specialist domain
**Decision:** Reporting, sentiment, and forecasting each get their own MCP server with their own database credentials, rather than one server exposing all tools.
**Context:** A single shared server means every agent's tool-access boundary is enforced only by which functions it happens to call — not by what it's actually capable of reaching.
**Alternatives considered:** One MCP server, multiple tools, permission-gated by tool definition (rejected — a compromised or injection-manipulated agent could still reach other tools on the same server; the boundary would be a convention, not a structural fact).
**Consequences:** More scaffolding (three small servers instead of one), for a materially stronger claim: "a compromised sentiment agent has no path to the forecasting tools, because the connection doesn't exist."

### ADR-009 — React/Next.js over Streamlit
**Decision:** Thin React front end over a FastAPI gateway, not a Streamlit app.
**Context:** The capstone commits to a "production-grade" claim; Streamlit is faster to build but reads as a prototype rather than a deployed product.
**Alternatives considered:** Streamlit (rejected on the production-grade claim specifically — would otherwise have been the pragmatic choice for a solo 12-week build).
**Consequences:** UI scope is deliberately kept minimal — intent input, response display, QA status, escalation flag — to keep this decision from expanding into a second major workstream.

### ADR-010 — Reporting agent built first (Sprint 2)
**Decision:** The least analytically interesting agent goes first, not last.
**Context:** The reporting agent's task is fully deterministic, making it the cheapest way to prove the entire MCP → A2A → orchestrator path end to end.
**Alternatives considered:** Build forecasting or sentiment first as the "harder, more impressive" pieces (rejected — proving the architecture matters more early than proving the hardest model, and doing the hardest agent first risks discovering a stack-level problem with no runway left to fix it).
**Consequences:** Sprint 2 is treated as the highest-risk, highest-value sprint in the plan — everything after it is repetition and refinement of an already-proven path.

### ADR-011 — Monorepo, separate service processes
**Decision:** One repository, but each agent and MCP server runs as its own process/container — not a single monolithic process, not separate repos per service.
**Context:** A2A implies separate endpoints and Agent Cards per agent; fully separate repos would add coordination overhead disproportionate to a solo project.
**Alternatives considered:** Single process, in-memory calls between agents (rejected — undermines the A2A demonstration entirely). Separate repos per service (rejected — solo-project overhead with no real benefit at this scale).
**Consequences:** docker-compose locally, Cloud Run services in deployment, one CI pipeline covering all services.

### ADR-012 — Domain: field service dispatch, network/hardware technicians
**Decision:** Model the system around field service dispatch for network/hardware technicians, not ground transportation.
**Context:** Ground transportation is the owner's actual professional domain. Diversifying was considered for "growth," but the operational logic (dispatch, SLA windows, incident escalation, customer feedback) is what's actually valuable and transferable — the specific vertical label is not.
**Alternatives considered:** Ground transportation (rejected — too close to the owner's employer, both as a provenance concern and as a "this is just my job" narrative risk). Retail/e-commerce products (rejected — an incidents-and-feedback table stops making sense without the SLA/dispatch mechanics that make the forecasting story interesting). IT helpdesk/managed services (viable alternative, not chosen but noted as a near-equal option).
**Consequences:** Field service dispatch is recognizable across enterprise software broadly (ServiceNow, Salesforce Field Service, Jira Service Management category), which is a stronger interview reference point than a narrower transportation-specific frame.

### ADR-013 — Schema built from general principles, not the owner's employer's system
**Decision:** Rebuild field names, status vocabulary, and workflow states from general service-dispatch domain knowledge, not from the specifics of any real production system the owner has access to.
**Context:** An early schema draft showed signs of being modeled directly on a real system — over-specific field naming conventions, real contact information present in sample data.
**Alternatives considered:** N/A — this is a constraint, not a design tradeoff.
**Consequences:** Every subsequent schema decision (ADR-014 onward) was made by asking "what would a field-service dispatch system need," not "what does the reference system have."

### ADR-014 — Split `incidents` and `service_feedback` into separate tables
**Decision:** Quality incidents and customer feedback are two tables, not one combined `incidents_feedback` table.
**Context:** A combined table means feedback can only exist where an incident exists — so essentially all feedback would be negative. This makes the sentiment classification task degenerate (always predict negative, score ~90%, learn nothing) and makes QA scoring against the label holdout meaningless with no class balance to measure.
**Alternatives considered:** One table, accept the class imbalance as a documented limitation (rejected — the imbalance isn't realistic and would undermine the sentiment agent's entire reason for existing).
**Consequences:** Requires updating `architecture.md` §4 to match (done). Produces a structural security benefit as a side effect: the sentiment MCP server can be granted access to `service_feedback` only, with no path to `incidents` at all, so internal staff notes can never leak into the sentiment pipeline.

### ADR-015 — BIGINT identity surrogate keys, not UUID
**Decision:** All surrogate primary keys are `BIGINT GENERATED ALWAYS AS IDENTITY`.
**Context:** UUIDs solve distributed-write and enumeration-privacy problems that don't apply here — single generator script, one process, ~20k rows.
**Alternatives considered:** UUID (rejected as unnecessary overhead for a single-writer synthetic dataset; noted as the correct choice if distributed generation or public-facing ID exposure were ever in scope).
**Consequences:** `reservation_number` remains the separate human-facing business identifier, so the internal key choice doesn't affect what the system displays to a user.

### ADR-016 — `technician_skills` join table, not a delimited string
**Decision:** Technician skills live in their own join table (`technician_id`, `skill`, `proficiency`), not a comma-delimited column on `technicians`.
**Context:** A delimited string forces substring matching to query ("find all network techs"), which is both awkward and subtly wrong (`LIKE '%network%'` also matches `network_admin`).
**Alternatives considered:** Delimited string (rejected — canonical first-normal-form violation, and a capstone reviewer would flag it immediately; the fix costs about ten lines of DDL).
**Consequences:** Enables future skill-based capacity modeling in the forecast agent, if pursued as a scope expansion.

### ADR-017 — SLA window snapshotted onto the request, not looked up live
**Decision:** `service_requests.sla_window_minutes` is populated from the account's contract tier at request-creation time and stored, not derived by joining to `accounts` at query time.
**Context:** A live lookup means that if an account changes contract tier, every one of its *past* requests would retroactively be judged against the new tier's SLA — changing historical compliance reports every time a tier changes.
**Alternatives considered:** Live join to `accounts.contract_tier` (rejected — non-reproducible reporting, a live number changes the meaning of past reports).
**Consequences:** Deliberate denormalization, documented as such. Defaults locked: standard tier 480/240/120 min (standard/urgent/critical priority), priority tier 240/120/60, enterprise tier 120/60/30.

### ADR-018 — Forecast: weekly, univariate, all statuses, 36-month history
**Decision:** The forecast target is the weekly count of `service_requests` by `scheduled_datetime`, across all request statuses, using a univariate model (date in, volume out), over a 36-month synthetic history.
**Context:** Daily grain is too noisy at realistic volumes; monthly grain leaves too few points to model. Filtering to completed-only requests would confound customer demand with the system's own cancellation behavior. Univariate keeps the model's inputs auditable and avoids any risk of it learning from incident/sentiment signals it shouldn't have access to.
**Alternatives considered:** Daily grain (rejected — noise). Monthly grain (rejected — too few points over the window). Completions-only target (rejected — conflates demand with internal cancellation patterns). Multivariate model incorporating incident/sentiment data (rejected — see ADR-021 for why this isn't needed and could complicate the leakage story).
**Consequences:** ~156 weekly points; ~130 for training, ~26 held out for backtesting against a seasonal-naive baseline.

### ADR-019 — Sentiment distribution: 50/22/20/8, 15% deliberately hard
**Decision:** Generated feedback sentiment targets 50% positive, 22% neutral, 20% negative, 8% mixed, with ~15% of all feedback flagged as deliberately hard (`is_sarcastic` or genuinely ambiguous).
**Context:** A realistic field-service feedback distribution is not incident-skewed — most completed jobs go fine. An unrealistic distribution (e.g. majority negative) would make every downstream sentiment accuracy figure meaningless.
**Alternatives considered:** Incident-driven distribution (rejected — see ADR-014, this is the same underlying problem the table split was meant to fix). No deliberately hard cases (rejected — a dataset with only easy cases can't produce a credible failure analysis, and failure analysis is one of the strongest artifacts this project can produce).
**Consequences:** Enables reporting subgroup accuracy separately (e.g. "92% overall, 64% on hard cases") rather than one aggregate number — validate the actual generated distribution in Sprint 1 before building anything on top of it.

### ADR-020 — Enums as VARCHAR + CHECK; `upgrade` added to `service_type`
**Decision:** All controlled-vocabulary fields are implemented as `VARCHAR` with a `CHECK` constraint, not native Postgres `ENUM` types. `service_type` includes `upgrade` alongside install/repair/maintenance/inspection.
**Context:** Native Postgres enums require a migration to add a value and are worse to remove one — a real cost on a 12-week solo timeline where a missing enum value discovered mid-sprint is likely.
**Alternatives considered:** Native `ENUM` type (rejected — migration friction outweighs the marginal type-safety benefit at this scale). Broader enum expansion generally (rejected as a default — more categories thin out the per-category row counts in a ~20k-row dataset and make aggregations noisier).
**Consequences:** Enum value sets should still be locked before data generation begins — a `CHECK` constraint is cheaper to alter than a native enum, but changing values after data exists still means regenerating.

### ADR-021 — Incident severity influences sentiment, with noise
**Decision:** `incident_notes` severity is coupled to the sentiment of associated `service_feedback`, via an explicit parameter in `generation_parameters` (`incident_severity_sentiment_coupling`) — not deterministically.
**Context:** Without some coupling, incidents and feedback would be three unrelated random streams rather than a coherent synthetic business, which undermines the realism the whole project depends on. The earlier concern that this could let the forecast model "cheat" doesn't apply once the forecast is locked as univariate (ADR-018) — it never sees incident or sentiment data at all.
**Alternatives considered:** No coupling (rejected — produces an incoherent synthetic world). Deterministic coupling, i.e. severity always maps to a fixed sentiment (rejected — makes the feedback text redundant with the severity field, which would undercut the sentiment agent's entire reason for existing).
**Consequences:** Generator must include genuine exceptions — e.g. a high-severity incident handled well yielding neutral or positive feedback — both for realism and as useful hard cases for QA scoring (ADR-019).

### ADR-022 — QA retries bounded at 2, then escalate
**Decision:** The QA agent allows a maximum of two revision cycles per request. On final failure, the system returns a degraded result with an explicit warning and a human-escalation flag — never an unbounded retry loop, never a silent pass-through of unverified output.
**Context:** Multi-agent systems with QA loops fan out token usage and cost quickly; an unbounded loop is both a latency and a budget risk (see ADR-006's cost constraints).
**Alternatives considered:** Unbounded retries until success (rejected — cost and latency risk with no guaranteed termination). Single-attempt QA with no revision (rejected — discards the main value of having a QA stage at all).
**Consequences:** The cap should be presented as a deliberate cost/latency control in the writeup, not discovered as a limitation during a demo.

### ADR-023 — Per-agent least-privilege DB roles + narrow MCP tools (defense in depth)
**Decision:** Two independent security layers: MCP tools are narrow, purpose-built functions (never raw SQL execution), and each agent additionally connects with its own least-privilege database role.
**Context:** MCP's rapid adoption has made it a heavily targeted surface (tool poisoning, rug pulls, supply-chain exposure), with formal NSA/CISA guidance issued. A generic `run_query`-style tool, even read-only, is vulnerable to prompt injection via customer-supplied text crafting a query that reaches data it shouldn't.
**Alternatives considered:** Tool-level scoping only, shared database credentials across agents (rejected — the boundary would exist only in the tool schema, not at the database level; see also ADR-008 for the related MCP-server-per-domain decision).
**Consequences:** A concrete outcome fell out of building the full access matrix: no agent holds any grant on `contacts` at all, so customer PII never enters an LLM context window under any code path — a specific, defensible claim for both the security writeup and interviews.

### ADR-024 — Trained models behind sentiment and forecast tools; training is offline
**Decision:** The sentiment and forecast MCP tools wrap real trained models, not further LLM calls. Sentiment: a fine-tuned transformer classifier (BERT), trained on `sentiment_labels`. Forecast: a scikit-learn/statsmodels regression, trained on the weekly volume series. Reporting and QA tools remain deterministic code — no model behind either. Model training is a separate, offline step that a developer or a scheduled job runs; no agent triggers or performs training as part of handling a request.
**Context:** The architecture had left this implicit. "The agent calls an MCP tool" is true at the orchestration layer for all four specialists, but at the tool layer only sentiment and forecast actually need a model — and that model is classical/deep ML the project trains itself, not a further call out to Gemini. Left unstated, this was at risk of being quietly implemented as an LLM-prompting shortcut for both, which would understate the project's ML content relative to what a DS/AI capstone should demonstrate.
**Alternatives considered:** LLM-prompted sentiment with self-reported confidence (rejected as the primary approach — faster to build, but weaker academically and offers a less reliable confidence signal than a softmax output from a trained classifier; the owner's existing CIS361 BERT-based text-classification pipeline, already validated CPU-only, removes most of the setup risk that would otherwise justify the shortcut). Agent-triggered or on-demand retraining (rejected — introduces unbounded cost/latency into request handling and blurs a boundary a reviewer would specifically ask about; training stays a deliberate, human-or-scheduler-triggered offline step).
**Consequences:** Each of `agent_sentiment` and `agent_forecast` needs its own training script and a place to store the resulting artifact — see the repo layout update below. Trained artifacts must never be committed to git (transformer checkpoints in particular can exceed 100MB) — add exclusions to `.gitignore`. The forecast model invites a deliberate choice between extending the approach from the owner's existing Mobility-Demand-Forecaster portfolio project or trying a different technique this time, to avoid the two portfolio pieces reading as duplicates.

### ADR-025 — Grant enforcement details settled while writing the DDL
*Date: 2026-09-20. Extends ADR-023; supersedes nothing.*

**Decision:** Three implementation choices that §7 of `data-dictionary.md` left underspecified, settled now that the access matrix is executable code:

1. **`service_feedback` for `app_reporting` is a column-level GRANT that omits `feedback_text`**, covering every other column. This is how §7's "SELECT (aggregate)" is enforced.
2. **Default privileges are revoked from `PUBLIC`** — `REVOKE CONNECT ON DATABASE`, `REVOKE ALL ON SCHEMA public` — and `CONNECT` / `USAGE` are then granted explicitly to the five agent roles.
3. **The cross-table invariant `archived_requests.completed_at >= service_requests.scheduled_datetime` is not enforced by a database trigger.** It becomes a generator-validation check and a QA-agent invariant instead.

**Context:** §7 is a table of privileges; turning it into GRANT statements forced three questions it didn't answer. Postgres has no aggregate-only privilege, so "SELECT (aggregate)" had to become something concrete. A `CHECK` cannot span two tables, so §8's phrasing ("enforce via trigger or app layer") had to resolve one way. And the matrix says nothing about `PUBLIC`, whose Postgres defaults quietly undercut the least-privilege claim.

**Alternatives considered:**

- *Feedback grant:* plain table-level `SELECT`, with "aggregate" enforced only by the MCP tool layer (rejected — the documented boundary and the actual boundary would differ, and the tool layer is Layer 1; the point of ADR-023's Layer 2 is that it holds when Layer 1 is compromised). A dedicated aggregate view with no grant on the base table (rejected — strongest boundary, but it adds an object the data dictionary doesn't define and pre-commits to which aggregations reporting may ever ask for).
- *`PUBLIC`:* leave the defaults alone (rejected — on Postgres < 15 any role can create objects in schema `public`, and any role can connect to the database; "least privilege" would be partly aspirational). Note the downgrade path restores the Postgres 15/16 defaults, not the older ones.
- *Cross-table invariant:* a row-level trigger on `archived_requests` (rejected — invisible behaviour, awkward under the generator's bulk inserts, and it duplicates a check the QA agent already owns; a failed insert deep inside a generation run is also far harder to diagnose than a named validation failure afterwards).

**Consequences:** The reporting agent cannot read a customer's raw words under any code path, which extends the §7 PII claim beyond `contacts` — worth stating in the security writeup alongside it. The privilege sets now live in `packages/db_models/access_matrix.py` rather than in prose, and `tests/unit/test_access_matrix.py` asserts each of §7's three structural properties, so a later edit that reopens one fails CI. §7's own wording should be read against that module, which is the authority for what is actually granted.

### ADR-026 — SQLAlchemy models separate from Pydantic schemas
*Logged retroactively — decided during planning, before this repo's decisions-log.md existed as the live document; recorded now so the history is complete.*
 
**Decision:** DB table definitions live in `packages/db_models/`, used as the source of truth for Alembic autogenerate. `packages/schemas/` remains Pydantic-only — request/response contracts for MCP tools and the API gateway.
**Context:** The repo layout didn't originally specify where ORM table definitions should live. Putting them in `packages/schemas/` alongside the Pydantic contracts would conflate two things that change for different reasons — a tool's input/output shape versus a table's column structure.
**Alternatives considered:** Defining models inline per-service, duplicated wherever needed (rejected — multiple MCP servers need to reference the same tables; duplication risks drift from the canonical structure in `data-dictionary.md`). Folding ORM models into `packages/schemas/` (rejected — see context).
**Consequences:** Confirmed implemented — `packages/db_models/src/db_models/` now holds `base.py`, `enums.py`, `reference.py`, `operational.py`, `ground_truth.py`, and `access_matrix.py`, matching this decision.

### ADR-027 — Sentiment reads `service_feedback` by column, `rating` withheld; migrations are frozen snapshots
*Date: 2026-09-22. Supersedes ADR-025 in part: the table-level `service_feedback` grant to `app_sentiment` that ADR-025 left in place. ADR-025's other decisions stand.*

**Decision:** Two linked decisions.

1. **`app_sentiment` gets a column-level `GRANT SELECT` on `service_feedback`** covering exactly `feedback_id`, `request_id`, `submitted_at` and `feedback_text`, replacing its table-level SELECT. `rating` is withheld. `submitted_at` stays because `get_feedback_batch(date_range, …)` filters on it.
2. **Migrations are immutable snapshots of what they did.** A migration carries its roles, tables and columns as literal data. It never imports live application code such as `db_models.access_matrix`, and every future grant change gets its own new migration. The already-applied roles-and-grants migration (`7d54e0c9a318`) was frozen in place to comply. The sentiment change is migration `1ee8342c81a7`.

**Context:** R-04's mitigation depends on `rating` being an *independent* cross-check on sentiment classification: a "positive" label on a 1-star review is a contradiction the QA agent can catch. If the sentiment agent can read the rating, a classifier (or an LLM step) can lean on the stars, and the check stops being independent without anything visibly breaking. ADR-025 closed the equivalent gap for reporting but left sentiment's table-level grant alone.

Planning the change exposed the second problem. `7d54e0c9a318` imported the live matrix, so its effect silently changed whenever the matrix did. On a fresh database it would already have applied the new sentiment grant, so history was no longer reproducible. Its downgrade could not know the prior state. And the first migration to add a table would have broken a fresh `upgrade head`, because `7d54e0c9a318` would try to grant on a table that doesn't exist yet at that revision.

**Alternatives considered:**

- *Sentiment grant:* keep table-level SELECT and have the sentiment MCP tool simply not select `rating` (rejected — the same argument as ADR-025: the tool is Layer 1, and ADR-023's Layer 2 exists so the boundary holds when Layer 1 doesn't). A view exposing only the four columns (rejected — same as ADR-025: an object the data dictionary doesn't define, for no stronger guarantee than a column grant).
- *Migrations:* keep importing the matrix and treat later grant migrations as convergent deltas (rejected — it leaves all three problems in place and makes each migration's meaning depend on the date it's read). Freeze `7d54e0c9a318` later, just before the first table-adding migration (rejected — a deferred fix that's cheap now and only gets riskier once more environments exist).

**Consequences:**

- The sentiment agent cannot read `rating` under any code path, so R-04's second signal is independent by construction. As a side effect it also loses `submitted_by_contact_id` (a PII foreign key) and `incident_id` (a pointer into staff-written data), consistent with §7 points 2–3.
- Freezing `7d54e0c9a318` in place was an edit to an applied migration. It was acceptable once, and only because that migration had run against nothing but the local development database, and the frozen literals reproduce its original effect exactly (verified against the matrix as committed, and by upgrading a fresh database to that revision). **After Sprint 5, once migrations have run against Cloud SQL, editing an applied migration is never acceptable:** fix forward with a new one.
- Because migrations no longer import the matrix, nothing *structurally* ties the two together. `tests/integration/test_access_matrix_grants.py` is what does: it compares the fully migrated database with the live matrix, reads and writes both, so a matrix edit with no matching migration (or the reverse) fails there. That makes the integration suite load-bearing, and it belongs in CI once a database is available there.
- Order matters in any migration that narrows a table grant to columns: in Postgres, `REVOKE … ON TABLE` also revokes that privilege on every column, so the table-level REVOKE must come before the column GRANT.

### ADR-028 — Role names are required, never defaulted: a blank `DB_ROLE_*_USER` fails like a blank password
*Date: 2026-09-22. Extends ADR-023 and ADR-025; supersedes nothing. Logged retroactively — the behaviour was decided and implemented while writing the roles migration, and is recorded here now because it is a security decision that the code alone does not explain.*

**Decision:** Every role's login name comes from its `DB_ROLE_*_USER` environment variable, which is **required**. An unset or empty value is a hard failure, reported exactly like an unset or empty `DB_ROLE_*_PASSWORD`, and the migration aborts before touching the database. The canonical role keys in `db_models.access_matrix` (`app_reporting`, `app_sentiment`, …) are identifiers for the matrix and the documentation — they are never used as a fallback login name. `_resolve_credentials()` in the roles migration collects every missing variable and raises once, so a fresh checkout gets one actionable error rather than five sequential ones.

**Context:** The canonical key is sitting right there in the same data structure as the environment variable pair, which makes `os.environ.get(user_var, role_key)` the obvious convenience. It is the wrong default. A role created under a name nothing connects as does not fail where the mistake was made: the migration succeeds, the grants are applied to a role that exists, and the failure surfaces much later and somewhere else as an opaque "permission denied" from an agent — or, worse, the intended role already exists from an earlier run with different privileges, and the mismatch is never noticed at all. Silence is the expensive outcome here, and the cost of the alternative is one clear error message at setup time.

**Alternatives considered:** Defaulting the name to the canonical role key (rejected — see context; it converts a setup error into a runtime mystery). Defaulting the name but requiring the password (rejected — inconsistent: both halves of a credential are equally load-bearing, and a half-defaulted credential is harder to reason about than either rule applied uniformly). Validating names in application code at startup instead of in the migration (rejected — the migration is what creates the roles, so it is the only place that can fail before the wrong thing is created).

**Consequences:** `.env.example` has to carry every `DB_ROLE_*_USER`, and a fresh checkout cannot run `alembic upgrade head` until they are filled in — deliberate friction, at the one moment when the person setting it up has the context to get it right. The same applies to deployment, though the two halves are not handled alike: role names are not secrets and travel as plain Cloud Run environment variables, while only the `DB_ROLE_*_PASSWORD` values need GCP Secret Manager (ADR-007). `tests/unit/test_roles_migration.py` covers each failure mode, including that all problems are reported together, and `tests/integration/test_access_matrix_grants.py` checks the other end of the contract — each role actually logs in under the name its `DB_ROLE_*_USER` specifies, so a role created under a name nothing connects as fails there too.

### ADR-029 — Runtime inference on the Gemini API free tier; model tiering revised
*Date: 2026-09-22. Supersedes ADR-006 in part (runtime funding: student credits
→ free tier) and resolves its open item. Replaces the model-tiering guidance in
`architecture.md` §9. ADR-007 (Cloud SQL from Sprint 5) is unchanged.*

**Decision:** Development-time inference runs on the Gemini API free tier via a
Google AI Studio key. Student credits: confirmed not available. Default model
for all agents during development is Gemini 3.5 Flash-Lite
(`gemini-3.5-flash-lite`). Flash-class models are used only where Flash-Lite
measurably underperforms. Pro-class models are not used during development.
Before the Sprint 5 evaluation runs, decide whether to move eval workloads to
a paid-tier project with a spend cap.

**Context:** Per the official Gemini API pricing page (checked 2026-09-22),
all Gemini 3.x Flash and Flash-Lite text models are free on the free tier
(image and Omni variants are not); Gemini 3.1 Pro (gemini-3.1-pro-preview) is
paid-only. Free-tier usage may be used by Google to improve its products;
acceptable here because all data is synthetic. Rate limits, verified in AI
Studio on 2026-09-22 (from a free-tier project on the same account; free-tier
defaults apply per project):

- `gemini-3.5-flash-lite`: 15 RPM, 250K TPM, 500 RPD.
- All Gemini Flash models (3, 3.5, 3.6, 3.7, 3.8): 5 RPM, 250K TPM, 20 RPD.
- `gemini-2.5-pro` and `gemini-3.1-pro-preview`: 0 RPM / 0 TPM / 0 RPD — no
  free-tier quota.
- Gemma 4 26B and Gemma 4 31B (open-weight, not Gemini): 30 RPM, 16K TPM,
  14.4K RPD. Recorded for reference only — not adopted for any agent.

Limits change without notice; the live values in AI Studio are authoritative,
not this entry. A project upgraded to paid is billed for all usage, so any paid
workloads would need a separate project.

**Alternatives considered:** Keep the `architecture.md` §9 tiering — a
stronger model for orchestrator routing and QA — with Gemini 3.1 Pro for QA
(rejected for development — it has no free tier). Gemini 2.5 Pro for QA (free
tier) — not adopted for development, kept as a Sprint 5 candidate. It is
Pro-class and free, so it is tested alongside Flash-Lite and
gemini-3.1-pro-preview in the Sprint 5 QA comparison rather than ruled out.
Its free-tier limits for Pro-class models may be too tight for eval volume;
check this project's limits in AI Studio before the comparison. No shutdown
date announced per Google's deprecations page, checked 2026-09-22.
*Revised 2026-09-22 after quota check:* despite the pricing page listing it as
free-tier, `gemini-2.5-pro` has zero free-tier quota on this account (0 RPM /
0 TPM / 0 RPD), so it is not a free QA candidate and is dropped from the
Sprint 5 QA comparison; `gemini-3.1-pro-preview` remains the paid,
spend-capped Pro-class candidate. Move to paid now
(deferred — no workload yet needs it, and Flash-Lite costs are low enough to
decide on real usage data later). Self-hosted Postgres on an Always Free
e2-micro instead of Cloud SQL (not adopted — would supersede ADR-007 and
weaken the production-grade claim; revisit only in a separate ADR if budget
forces it).

**Consequences:** Update GEMINI_MODEL_* in .env.example to Flash-Lite
defaults. packages/llm must handle 429 rate-limit responses with backoff,
since free-tier limits will be hit during evals. Moving any agent from
Flash-Lite to Flash on the free tier is impractical at 20 RPD, so any such move
implies the paid tier. A full routing eval run may need 300-700 requests
(orchestrator, specialist, QA, and up to 2 retries per case), which can exceed
the 500 RPD Flash-Lite cap; Sprint 5 must either split eval runs across days or
run evals on a paid, spend-capped project. Any LLM-generated synthetic data on
Flash-Lite must batch many rows per request to fit the daily quota. Gemma 4's
14.4K RPD makes it a candidate for generating synthetic `feedback_text`, since
the ~7,200 `service_feedback` rows would fit in one day even at one row per
request. Its 16K TPM limits how many tokens can be generated per minute (about
530 tokens per request at the full 30 RPM; 7,200 requests take at least four
hours). Decision deferred to the data generator session; not a runtime model
for any agent. The QA-model
comparison noted in `architecture.md` §9 and §12 becomes a Sprint 5 decision,
made with a spend cap in place. Pro for QA is estimated at roughly $20-30 for
the evaluation phase including thinking tokens (floor of ~$10-15 without them),
within the ~$40 buffer; the spend cap enforces the ceiling. Basis for the
floor: roughly 500 QA calls x ~5,000 input tokens x $2.00/M = ~$5, plus
500 x ~1,000 output tokens x $12.00/M = ~$6 (gemini-3.1-pro-preview standard
paid rates for prompts up to 200k tokens, per the official pricing page,
checked 2026-09-22). Output is billed including thinking tokens, which can
multiply output volume for Pro models. Test it in
Sprint 5 under a spend cap rather than ruling it out. The correct identifier
for the Pro model is `gemini-3.1-pro-preview` (not `gemini-3.1-pro`); it is a
preview model, with tighter limits and no stability guarantee. Update R-02 in
the risk register from Open to Mitigating.

### ADR-030 — `feedback_text` is LLM-generated once and frozen as a committed corpus
*Date: 2026-09-22. Applies the frozen-snapshot principle of ADR-027 to generated
data; uses the API and limits recorded in ADR-029. Supersedes nothing.*

**Decision:** `feedback_text` is written by an AI model through Google's API,
not assembled from templates. A dedicated corpus script,
`data/generator/build_corpus.py`, calls the API once and writes every feedback
comment to a committed file, `data/generator/corpus/feedback_text.jsonl`. Each
comment carries the sentiment it was requested to have, whether it was
requested as a hard case, and if so which kind (sarcastic or genuinely
ambiguous). A provenance record alongside it,
`data/generator/corpus/provenance.json`, captures the model ID, date, exact
prompt, and generation settings. `generate.py` reads the frozen corpus and
never calls an API; it assigns comments to `service_feedback` rows using the
persisted random seed, so the same seed and corpus reproduce the same dataset.
Regenerating the corpus is a deliberate, documented act, not something that
happens on a normal run.

**Context:** LLM output isn't deterministic, hosted models change or are
retired, and free-tier limits change without notice (ADR-029), so calling the
API on every generation run would make the dataset irreproducible and
downstream accuracy numbers incomparable across runs. This is the same
principle as the frozen migrations in ADR-027: an artifact that later results
depend on is captured once as a literal snapshot, not re-derived from
something that can drift.

**Alternatives considered:** Templates (rejected — risk a sentiment model that
learns template patterns rather than sentiment). Claude-written raw material
assembled by the script (rejected — assembling fragments recreates the
template problem at a finer grain; whole generated comments read more
naturally). Calling the API on every `generate.py` run (rejected —
irreproducible, for the reasons above).

**Consequences:**
- The requested sentiment is intent, not ground truth. `validate.py` must
  check a sample of comments against their intended labels before the corpus
  is accepted.
- The corpus must hold at least as many unique comments in each (sentiment,
  hard-case) cell as the locked distribution needs (`data-dictionary.md` §6:
  ~3,600 positive, ~1,580 neutral, ~1,440 negative, ~580 mixed; ~1,080 hard),
  so `generate.py` never reuses a comment. `validate.py` also rejects exact and
  near duplicates: a comment that lands in both the sentiment model's training
  split and the holdout (ADR-024) inflates accuracy, and LLM batches do repeat
  phrasing. Generate 15-20% more than the target in each cell, so comments
  rejected by label validation or duplicate checks are replaced from spares
  rather than requiring another API run.
- The corpus records each hard case's type (sarcastic or genuinely
  ambiguous). `sentiment_labels.is_sarcastic` can only represent the sarcastic
  kind, so genuinely ambiguous hard cases would be stored the same as easy
  ones and become indistinguishable in failure analysis.
- Requests should generate many comments per call so the prompt is paid once
  per batch, not once per comment (see ADR-029 rate limits).
- Generator scripts print progress and summaries only, never generated rows,
  to keep tool output small.
- Open for the generator session: which model (Gemma 4 vs Flash-Lite, per
  ADR-029), batch size, prompt design, how label validation is done (sample
  size and method), and whether comments are also requested per
  `service_type` or incident presence, so a comment about a failed printer
  doesn't land on a clean network install; and whether `sentiment_labels`
  needs a `hard_case_type` column (a schema change and new migration) so the
  distinction survives into the database.

### ADR-031 — Single-shot interaction is the committed scope; multi-turn is conditional stretch
*Date: 2026-09-22. Resolves the open item in `architecture.md` §12. Supersedes nothing.*

**Decision:** The system accepts one natural-language question and returns
one verified answer per exchange. No conversation state, no follow-up
handling, in the committed build. Multi-turn/conversational follow-up is
considered only as a scope expansion, decided at the Sprint 4 boundary and
only if genuinely ahead of plan per the §13 working agreement. It is never
built in Sprint 6, which is protected buffer.

**Context:** `architecture.md` §12 left this open: *"Whether the UI supports
conversational follow-up or single-shot intents (affects orchestrator state
management)."* Left unresolved, it was ambiguous whether the orchestrator
needed a session/state layer at all — a load-bearing design question, not a
UI detail, since it affects how the orchestrator is built from Sprint 2
onward.

**Alternatives considered:** Building conversational support from the start
(rejected — adds orchestrator state-management complexity with no
corresponding rubric requirement or portfolio value strong enough to justify
displacing solo dev time from the routing eval and QA loop, which are the
higher-value places to spend it).

**Consequences:** The orchestrator has no session/state layer to design,
build, or test in the committed scope. Resolves the conversational-vs-single-shot
open item in `architecture.md` §12. If multi-turn is pursued later, it is a
scope expansion under the terms above, not a reopened architectural question.

### ADR-032 — Compound (multi-specialist) routing is out of scope; multi-domain questions are detected and split by the user
*Date: 2026-09-22. Resolves an implied commitment in `architecture.md` §3 and §8 that no ADR had decided. Supersedes nothing.*

**Decision:** The orchestrator routes each question to exactly one specialist.
It does not send one question to several specialists or merge their answers.
When a question spans more than one domain (e.g., "are incidents and
sentiment both getting worse in the Northeast?"), the orchestrator detects
it and responds by telling the user which domains the question covers and
asking them to submit each part separately. It does not silently answer only
one part.

**Context:** `architecture.md` §8 lists "multi-agent intents requiring more
than one specialist" as a routing eval category, and §3 says the orchestrator
"assembles the final response." Read together, they imply compound routing as
a committed capability. But no ADR decided it, no sprint plans to build it,
and the Sprint 5 eval item in `sprint-log.md` lists only ambiguous and
out-of-scope intents. The architecture was testing for a behavior the plan
never builds. Surfaced while writing the Detailed Requirements Analysis,
where leaving it unresolved would have let a frozen requirements contract be
read as committing to it.

**Alternatives considered:**

- *Build compound routing* (rejected). The cost sits in three places:
  merging outputs of different types (a metric table, a sentiment breakdown,
  a forecast) into one coherent answer; QA across multiple outputs per
  request, including partial failure where one specialist passes and another
  doesn't; and multiplying API calls per request, including retries, under
  the 500 RPD Flash-Lite free-tier cap (ADR-029). None of this is needed to
  answer the Business Case's three question types, each of which maps to a
  single specialist.
- *Answer only the primary domain of a compound question* (rejected). A
  partial answer presented as a complete one is the failure the QA stage
  exists to prevent.
- *Remove the multi-agent category from the routing eval* (rejected). Users
  will still ask compound questions. Dropping the category would leave the
  orchestrator's handling of them untested.

**Consequences:**

- Detecting and splitting multi-domain questions is requirement FR-04.
  Compound routing is listed as excluded (FR-21) in the Detailed
  Requirements Analysis.
- The QA agent verifies one specialist output per request. No partial-failure
  handling is needed.
- Since interaction is single-shot (ADR-031), the orchestrator cannot ask a
  follow-up. Its response must itself name the domains detected and tell
  the user to resubmit each part.
- The routing eval keeps the multi-agent category, with a changed expected
  outcome: a case is scored correct when the orchestrator detects the
  multi-domain question and returns the split instruction, not when it
  routes to multiple specialists.
- Required edits:
  - `architecture.md` §3, Orchestrator description: replace "assembles the
    final response" with "returns the specialist's verified response to the
    user."
  - `architecture.md` §8, Routing eval harness: change the bullet to
    "**Multi-domain intents** spanning more than one specialist, expected to
    be detected and returned with a split instruction rather than routed
    (ADR-032)."
  - `sprint-log.md` Sprint 5: change the eval item to "Routing eval harness
    + failure-case analysis (ambiguous, multi-domain, and out-of-scope
    intents included)."

### ADR-033 — Metrics may be reported for individual technicians, as decision support
*Date: 2026-09-22. Extends FR-06 and the Ethical Considerations requirement in the Detailed Requirements Analysis. Supersedes nothing.*

**Decision:** The reporting agent may answer questions at the level of an
individual technician (e.g., "which technicians have the most incidents this
quarter?"), alongside account, region, and service-type breakdowns.
Technician-level figures are presented as decision support for operations
leaders, not as automated performance judgments, and pass the same QA
verification as every other answer. Every technician-level rate is shown
with the number of completed jobs behind it.

**Context:** `incidents.attributed_technician_id` records which technician an
incident is attributed to, and `app_reporting` already holds SELECT on
`technicians` and `incidents` (`data-dictionary.md` §7), so technician-level
reporting was technically possible but undecided. Surfaced while writing the
Ethical Considerations requirement: a system that ranks individual employees
from automated output is making a choice with consequences for those
employees, and that choice should be stated rather than left as a side
effect of the schema.

**Alternatives considered:**

- *Restrict reporting to team, region, or account level* (rejected).
  Operations leaders need technician-level information for coaching,
  training, and dispatch decisions; the attribution field exists for that
  purpose. Hiding it would push leaders back to analysts for the question,
  which is the gap the project exists to close.
- *Allow it with no stated framing* (rejected). Leaves the ethical position
  implicit, which the Ethical Considerations requirement doesn't permit.

**Consequences:**

- FR-06 lists individual technician as a reportable dimension. The Ethical
  Considerations requirement states the decision-support framing.
- Rates are shown with their completed-job count, because a technician with
  few jobs can look far worse than peers after a single incident. A rate
  without its sample size is misleading, and misleading figures about named
  people are the most harmful kind this system can produce.
- `attributed_technician_id` is nullable: not every incident is
  attributable (e.g., dispatch errors). Technician-level incident counts
  cover attributable incidents only, and answers say so.
- Technician names are employee personal data. Acceptable here because all
  data is synthetic; a real deployment would need a data-handling review
  before technician names enter model context.
- The Sprint 4 ethics section cites this ADR. The routing eval should
  include technician-level questions so this path is tested.

### ADR-034 — 120-second end-to-end timeout ceiling; latency measured, not targeted
*Date: 2026-09-22. Extends ADR-022. Supersedes nothing.*

**Decision:** No request runs longer than 120 seconds end to end. When the
ceiling is reached, the system stops waiting and returns a degraded result
with a warning and an escalation flag, reusing ADR-022's final-failure path.
No response-time target is committed. Response time and token cost are
measured per request type (reporting, sentiment, forecast, declined,
escalated) and reported in the final evaluation, including the effect of QA
revision cycles and cold starts.

**Context:** Set while writing the Performance requirement in the Detailed
Requirements Analysis, which becomes a frozen contract. The template's
example target (0.5 seconds) is not achievable for a multi-agent system
with LLM calls and a QA stage, and no latency measurements exist yet. A
committed target would be a guess. The ceiling is enforced by a timeout in
the system's own code, so it is met by construction.

**Alternatives considered:**

- *A fixed response-time target* (rejected). Unverifiable before measurement,
  and largely dependent on the external model's response time.
- *60-second ceiling* (rejected). A cold start plus up to two QA revision
  cycles could reach it on legitimate requests, returning degraded results
  for answers that would have finished.
- *5-minute ceiling* (rejected). Nothing in the pipeline should legitimately
  take minutes; a request running that long is almost certainly stuck, and a
  long ceiling hides it from the user instead of escalating it. It also
  equals Cloud Run's default 300-second request timeout, so Cloud Run would
  cut the request off before the system's own ceiling fired, and the user
  would get a generic error instead of the degraded result.

**Consequences:**

- Inner timeouts must fit inside the ceiling: orchestrator-to-specialist
  calls, MCP calls, and each QA cycle get their own shorter timeouts that
  together stay under 120 seconds.
- Everything in front of the orchestrator must wait longer than 120 seconds:
  the FastAPI gateway and the UI's HTTP requests need timeouts above the
  ceiling, and Cloud Run's 300-second default must not be lowered below it.
- Latency measurement belongs to Sprint 6 load and latency testing
  (`architecture.md` §8).
- Revisit only with evidence: if Sprint 5 deploy measurements show
  legitimate requests approaching the ceiling, raising it is a new ADR.

### ADR-035 — Forecast agent narrowed to three columns of `service_requests`
*Date: 2026-09-22. Extends ADR-023. Supersedes the forecast column of the original `data-dictionary.md` §7 access matrix.*

**Decision:** `app_forecast` gets a column-level `GRANT SELECT` on
`service_requests` covering exactly `request_id`, `scheduled_datetime`, and
`service_type`, replacing its table-level SELECT. Its SELECT on `accounts`,
`locations`, and `archived_requests` is revoked. Applied by a new migration.

**Context:** Found while writing the per-agent data access maps for the
Detailed Requirements Analysis. The forecast is univariate (ADR-018): a
weekly count of requests by `scheduled_datetime`, with an optional breakout
by `service_type`. The original matrix granted it four tables, including
completed-job billing records, none of which that forecast uses. The
least-privilege claim (ADR-023) did not hold for this role, and a reader
comparing the access map with FR-08 could see it.

**Alternatives considered:**

- *Keep the original grants* (rejected). Leaves billing data reachable by an
  agent that never needs it, and overstates the least-privilege claim.
- *Table-level SELECT on `service_requests` only* (rejected). Still exposes
  payment method, cancellation reasons, and account, contact, and technician
  IDs. Same reasoning as ADR-025 and ADR-027: where a table-level grant
  over-grants, use a column-level one.
- *A pre-aggregated weekly-volume view* (rejected). Same as ADR-025: an
  object the data dictionary doesn't define, for no stronger guarantee than
  a column grant.

**Consequences:**

- The forecast agent cannot read billing, accounts, locations, customer
  feedback, incidents, or any customer or technician identifier.
  `request_id` stays as an identifier to count and report against.
- Any forecast breakout beyond `service_type` (e.g., by region or account)
  requires a new grant, migration, and ADR. That friction is deliberate.
- Per ADR-027, the migration carries its grants as frozen literals, revokes
  the table-level SELECT before granting columns, and its downgrade restores
  the original grants exactly.
- `data-dictionary.md` §7 and `db_models.access_matrix` are updated to
  match. The live grants integration test enforces the match.

### ADR-036 — Feedback corpus design: models, label definitions, cell rules, judge-confirmed plain labels
*Date: 2026-09-23. Supersedes ADR-019 and ADR-030 in part (the second hard-case type:
"genuinely ambiguous" becomes "implicit"), ADR-021 in part (how a handled-well serious
incident appears in the text), and ADR-030's validation approach for plain comments.
Resolves ADR-030's open items except the `hard_case_type` schema question, which is
ADR-037.*

**Decision:**

1. **Models.** `gemini-3.5-flash-lite` writes the corpus (temperature 1.0,
   `thinking_level=minimal`, JSON mode). `gemma-4-31b-it` is the label judge
   (temperature 0, `thinking_level=minimal`) and sees comment text only.
2. **Hard-case types are `sarcastic` and `implicit`.** Implicit: the sentiment is real
   but carried by facts or understatement, and a careful reader reaches it with
   confidence. Genuinely ambiguous comments are excluded: their label would be noise.
3. **Label definitions**, used verbatim in both generator and judge prompts:
   - *positive*: the writer's overall verdict is satisfied. On an incident row, the
     text praises the handling without naming the failure.
   - *negative*: the writer's overall verdict is dissatisfied.
   - *mixed*: the writer praises at least one aspect and criticizes at least one other,
     neither dominating; or names a serious problem and praises how it was handled.
   - *neutral*: one of three kinds only: minimal or indifferent; administrative
     (a request or information, never a dispute); status without a verdict. A visit
     described as having gone well is positive, however flatly worded.
4. **Cell rules:** neutral only on rows without an incident, plain style only. Mixed
   plain only, any incident level. Sarcastic only negative. Implicit only positive and
   negative. `parameters.py` enforces these as zero-probability combinations.
5. **Conditioning:** comments without an incident are keyed on (sentiment, style,
   service_type); incident comments on (sentiment, style, incident level, incident
   type), with minor = low severity and serious = medium or high. Every possible cell
   gets at least 6 comments plus 20% spares; plain neutral and plain mixed cells get
   2x, since the judge filter rejects more of them.
6. **Spec fields:** focus and opening are drawn per spec, except for minimal neutrals,
   which get neither. Openings: problem first, time reference, sentence fragment,
   question (question only for negative and administrative neutral). SMS comments are
   2-12 words in a loose style; minimal neutrals are 1-8 words on any channel.
7. **Validation:**
   - The judge labels every comment. A plain comment whose judge label differs from
     its intended label is rejected and replaced from spares.
   - Sarcastic and implicit comments are never rejected on judge disagreement;
     disagreements go to human review.
   - Automated checks reject money, times, dates, name-like tokens, greetings, and
     near-duplicates (5-gram character Jaccard > 0.6 within a cell).
   - A blind, stratified human review of about 200 comments follows, with a
     calibration pass first and anchored believability ratings. It reports agreement
     per cell. A cell below 50% human-intended agreement is regenerated once. Other
     results are reported, not gating.
8. **`build_corpus.py`** batches 20 comments per request, retries server errors with
   a higher cap than the bake-off's 5, and resumes from the last completed batch.

**Context:** ADR-030's model question was settled by a bake-off and three prompt
iterations on 2026-09-23 (evidence in `data/generator/experiments/bakeoff/`, scored
blind by the owner).

| Round | What it showed |
|---|---|
| v0 | Quality tied (human agreement 13/20 Flash-Lite, 15/20 Gemma); about half of all comments opened with "The" |
| v1 | Openers fixed. Judge agreed on neutral 2/20, but the human and judge agreed 32/40, so the generator was the weak link |
| v2 | Content-type neutral definition; neutral 8/20. The minimal kind conflicted with the length bands |
| v3 | Final iteration under a pre-committed stop rule: neutral 10/20, mixed + minor incident 4/8, both below target. The human review showed the human reading 5 of 6 "positive after a serious incident" comments as mixed, while the judge read all 6 as positive |

Three findings drove the design. Defining neutral by tone produced label noise, because
a flat report of a working fix reads as satisfied. The judge applies whatever definition
it is given, so its agreement proves consistency with the specification, not that the
specification matches a human reader. And the system's users are operations leaders
reading these comments, so ground truth has to match how a person reads them; otherwise
the sentiment agent is marked wrong for reading like one (R-13).

**Alternatives considered:**
- *More prompt iterations* (rejected). Four rounds were run, and the stop rule was set in advance.
- *Dropping neutral, or changing the 50/22/20/8 mix* (rejected). Neutral is real, and
  ADR-019's mix stands.
- *Judge filter on every cell* (rejected). It removes the hardest sarcastic and implicit
  cases, inflating the hard-case accuracy that subgroup exists to measure.
- *No judge filter* (rejected). The generator writes neutral as intended only about half
  the time, and unfiltered, that becomes label noise.
- *Problem plus recovery labeled positive* (rejected). The human reader disagreed on 5 of 6.
- *Gemma as generator* (rejected). Quality tied, and it was 11x slower with frequent
  server errors.

**Consequences:**
- Plain labels are judge-confirmed, not only generator-intended. Hard-case labels
  remain intent verified by sampling. The final paper states both.
- Judge filtering biases plain cells toward comments Gemma reads clearly, so the plain
  subgroup is easier than real plain feedback. This is stated as a limitation.
- The human evidence so far is one annotator (the owner) on 20-24 comments per round.
  The full-corpus human review is the real acceptance evidence, and the single-annotator
  limitation is stated in the paper.
- Believability was not achieved in the bake-off (10 of 24 v3 comments sounded
  AI-written). The SMS and opening changes target its two measured sources but are
  untested until the corpus review. If unresolved, it is reported as a limitation.
- The corpus grows to roughly 10-11K comments: about 550 Flash-Lite requests over two
  days, plus a judge pass of several hours.
- `parameters.py` allocates the 15% hard-case share across positive (implicit) and
  negative (implicit, sarcastic) only.
- `sentiment_labels.is_sarcastic` cannot represent implicit hard cases. ADR-037 decides
  the schema change.

### ADR-037 — `sentiment_labels`: `hard_case_type` replaces `is_sarcastic`; `corpus_id` added
*Date: 2026-09-23. Resolves the schema question left open by ADR-030 and ADR-036.
Supersedes nothing.*

**Decision:**
1. `sentiment_labels.is_sarcastic` is replaced by `hard_case_type`: VARCHAR + CHECK
   (`none`, `sarcastic`, `implicit`), NOT NULL. It becomes the 22nd controlled
   vocabulary, `HardCaseType` in `enums.py`.
2. `sentiment_labels.corpus_id` is added: VARCHAR(32), NOT NULL, UNIQUE. It holds the
   ID of the corpus comment (`data/generator/corpus/feedback_text.jsonl`) that supplied
   the row's `feedback_text`.
3. A new migration applies both, carrying its definitions as frozen literals (ADR-027).
   Its upgrade maps existing rows (`is_sarcastic` true → `sarcastic`, false → `none`),
   although the table is empty today. Its downgrade restores `is_sarcastic`, mapping
   `sarcastic` → true and everything else → false. That mapping is lossy for
   `implicit`, which is documented in the migration.

**Context:** ADR-036 defines two hard-case types. A boolean can represent only one, so
implicit hard cases would be stored as easy ones and disappear from the failure
analysis. That analysis also needs the corpus metadata behind each label (neutral kind,
incident level, focus, channel), which lives in the committed corpus, not the database.
Without a stored key, the eval harness could join a label to its corpus record only by
matching the text, which is fragile.

**Alternatives considered:**
- *Keep `is_sarcastic` and add a separate implicit flag* (rejected). Two booleans can
  contradict each other; one vocabulary column cannot.
- *Keep the hard-case type only in the corpus* (rejected). Without `corpus_id` there is
  no reliable join, and with it the type would still be one extra join away for every
  subgroup query.
- *Store the full corpus metadata in the database* (rejected). It adds columns the
  schema doesn't otherwise need. The corpus file is committed and authoritative, and
  `corpus_id` is enough to reach it.

**Consequences:**
- `UNIQUE (corpus_id)` enforces ADR-030's no-reuse rule in the database: a generator
  bug that assigns one comment to two feedback rows fails at insert time.
- `sentiment_labels` grants are table-level (`app_qa` SELECT, `app_generator` ALL), so
  both new columns are covered without a grant change. No agent role gains anything.
- `data-dictionary.md` §4, §5 and §10 are updated; the vocabulary count goes from 21
  to 22.

### ADR-038 — Generator parameters: text on every feedback row, anomalies, coherence rules, corpus sizing, `param_group` values
*Date: 2026-09-23. Extends ADR-018, ADR-021 and ADR-036. Supersedes nothing.*

**Decision:**
1. **Every `service_feedback` row has `feedback_text`.** Only `rating` may be null
   (10%). A sentiment label on a row with no text would be meaningless.
2. **Three anomalies, all inside the forecast training span:**
   - *Account drop:* the largest account (12% of volume) falls 90% for weeks 40-41
     (from 2024-06-10). It is invisible in weekly totals (z ≈ 1.4 over the window)
     and obvious at account level, so it tests the reporting agent's drill-down.
   - *Regional drop:* every site in the largest region (~30% of volume) falls 85% for
     two weeks from 2025-02-17. It is visible in weekly totals (z >= 3 over the
     window) and tests forecast robustness. Placed away from the Q4 peak and the
     December trough so it isn't confounded with seasonality.
   - *Billing:* direct-bill invoices carry a 0.10 surcharge instead of 0 for weeks
     95-97 (from 2025-06-30), about 130 invoices, detectable per invoice.
3. **Noise:** the weekly multiplicative noise parameter is 6%. The effective
   week-to-week noise, including Poisson counting noise, is about 10.6%. Reports cite
   the effective figure.
4. **Coherence rules:**
   - `missed_sla` incidents occur only on requests that missed their SLA.
   - A `repeat_visit_required` incident creates exactly one child request (same
     account, site and type, 2-10 days later).
   - Feedback links to the most severe incident, with ties going to the earliest.
   - Incident status depends on age: only recent incidents are open or investigating.
5. **Corpus cells are sized from the Poisson 99th percentile of their expected count**
   (then x1.2, or x2 for plain neutral and plain mixed, with a floor of 6), not from a
   seeded dry run. That keeps the corpus independent of the seed. `generate.py` fails
   if a cell runs out; it never reuses or borrows across cells.
6. **`param_group` gains `world`** (seed, window, reference counts, regions, request
   lifecycle) **and `feedback`** (response rates, channels, corpus sizing), via a new
   frozen migration.
7. **numpy is pinned exactly**, because seeded draws are reproducible only within one
   numpy version. `parameters.py` is the authority for the SLA matrix at generation
   time. A unit test, not the generator, checks it against `data-dictionary.md` §2.

**Context:** Reviewing `parameters.py`'s analytic output showed that the account drop
was statistically invisible in weekly totals, that Poisson noise exceeded the 6%
parameter, that sizing corpus cells from their expectation would starve small cells,
and that five of the seven parameter prefixes had no fitting `param_group`.

**Alternatives considered:**
- *A larger top account* (rejected). An account at ~25% of volume is needed for the
  drop to be visible, which distorts account-level reporting.
- *Replacing the account drop with the regional one* (rejected). The account drop is
  the better drill-down test for the reporting agent.
- *Sizing the corpus from a seeded dry run* (rejected). It ties the corpus to one seed,
  which ADR-030's design avoids.
- *Mapping global parameters into existing groups* (rejected). It mislabels
  ground-truth rows the paper cites.

**Consequences:** The corpus grows to roughly 12-13K comments, still two days of
Flash-Lite quota. `generate.py` must assign location states to hit the regional
shares. The final paper reports anomaly strength as z-scores against the effective
noise.

### ADR-039 — Positive feedback on incident rows uses no-incident positive comments
*Date: 2026-09-23. Supersedes ADR-036 in part: the positive-on-incident-row clause of
decision 3, and the positive-with-incident cells of decisions 4 and 5. ADR-021's
severity-sentiment coupling is unchanged.*

**Decision:** The corpus has no positive-with-incident cells. When `generate.py`
assigns positive sentiment to a feedback row on a request with an incident, it draws
the comment from the no-incident positive cell with the same service type and style
(plain or implicit). Those cells are enlarged to cover the combined expected demand,
using the same Poisson q99 sizing (ADR-038). The comment does not mention the incident.

**Context:** In the `build_corpus.py` test batch (2026-09-23), the judge labelled all
14 judged positive-with-incident comments as mixed, across both styles and both
severity levels. That includes 8 where a keyword heuristic found no mention of the
problem. Writing a positive comment that is shaped by an incident without naming it
proved unreliable: either the generator names the failure anyway, or any praised
recovery reads as mixed. At a 0% plain acceptance rate, the 28 cells (487 comments)
could not be filled even with three top-up rounds (~900 extra requests). Their implicit
comments would also have entered the corpus labelled positive while the judge read them
as mixed. The prompt route was already closed by ADR-036's stop rule.

**Alternatives considered:**
- *More prompt work* (rejected). The stop rule is closed, and the failure was total
  rather than marginal.
- *Positive-with-incident labelled mixed, i.e. no positive sentiment on incident rows*
  (rejected). It is feasible for the overall mix, but it removes ADR-021's
  handled-well exception entirely and makes an incident a near-certain signal of
  "not positive."
- *Keeping the cells without the judge filter* (rejected). It admits labels the judge
  and, per the earlier human review, a human would dispute.

**Consequences:**
- ADR-021's exception survives at the label level: incident rows can still carry
  positive sentiment. The text of those rows carries no incident-specific signal,
  which is a realism cost stated in the paper.
- The corpus loses 28 cells. The no-incident positive cells grow by the incident-row
  positive demand (about 21% of incident-row feedback is positive).
- The generator and judge prompts are unchanged (still v4). The positive-incident spec
  note is removed from the code.
- Failure analysis cannot report "positive despite an incident" as a text subgroup,
  only as a label-level slice.

### ADR-040 — Sentiment labels are defined by the written specification; human review becomes a sanity check
*Date: 2026-09-23. Supersedes ADR-036 in part: decision 7's human review and its
regeneration gate. ADR-036's label definitions and ADR-039 stand unchanged.*

**Decision:**
1. The ground truth for sentiment is the ADR-036 written label definitions. Plain labels
   are the generator's intent confirmed by the Gemma judge. Sarcastic and implicit
   labels are the generator's intent; the judge's disagreement rate on them is reported,
   not used as a filter. Human reading is not the reference standard.
2. The ~200-comment human review is replaced by a ~30-comment sanity spot-check that
   flags only unusable comments: broken or off-domain text, prohibited content, or a
   label plainly wrong under the written definitions. There is no agreement scoring, no
   believability rating, and no regeneration gate based on human agreement.
3. Reported validation evidence: judge acceptance rate per cell before filtering, judge
   agreement on hard cases, automated check rejection rates by reason, and the achieved
   class distribution against the 50/22/20/8 target.
4. The problem-plus-recovery boundary stays as ADR-036 defines it and is not reopened.

**Context:** The owner's blind reviews (bake-off v0-v3 and the corpus test batch) were a
single non-specialist annotator, and they were unstable on the ambiguous boundary. The
owner read problem-plus-recovery comments as mixed 5 of 6 times in v3, and as positive
13 of 17 times in the test batch. Human-judge agreement ranged from 32/40 (v1) to 14/30
(test batch). Sentiment in customer feedback is inherently ambiguous and annotators
disagree, so a single annotator's reading is not a reliable reference. The disputed
boundary affects about 1.6% of feedback rows (mixed on medium- or high-severity incident
rows, ~125 of ~7,600). Sentiment is one of three specialists, and label design had
already consumed Sprint 1.

**Alternatives considered:**
- *Revert to a verdict-based boundary* (rejected). It reopens ADR-036 and ADR-039 for
  ~1.6% of rows, on the evidence of one reader who has read the category both ways.
- *A second annotator* (rejected on schedule). Recorded as future work; it is the right
  method for a real deployment.
- *Keep the ~200-comment review* (rejected). It would measure one reader's variability,
  not label quality.

**Consequences:**
- The paper states that labels are specification-defined and that sentiment accuracy is
  measured against the specification. The owner's review results are reported as
  evidence of the category's ambiguity.
- Hard-case labels remain generator intent and are never filtered by the judge, so
  hard-case accuracy is not inflated (R-13). Their judge disagreement rate is reported
  alongside.
- No believability claim is made for the corpus.
