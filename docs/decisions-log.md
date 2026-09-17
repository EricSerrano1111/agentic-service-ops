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
 