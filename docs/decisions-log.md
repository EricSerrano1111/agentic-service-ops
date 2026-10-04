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
| 003 | QA agent as a verification stage, not a formality | Accepted — superseded in part by ADR-055 |
| 004 | Solo / Agile / Python project parameters | Accepted (course-selected) |
| 005 | GCP over Azure | Accepted — superseded in part by ADR-061 |
| 006 | Claude Pro for development; Gemini credits for runtime inference | Accepted — superseded in part by ADR-029 |
| 007 | Cloud SQL deferred to Sprint 5; local Docker Postgres before | Accepted — superseded in part by ADR-045 |
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
| 019 | Sentiment distribution: 50/22/20/8, 15% deliberately hard | Accepted — superseded in part by ADR-036; `is_sarcastic` replaced by ADR-037 |
| 020 | Enums as VARCHAR + CHECK; `upgrade` added to `service_type` | Accepted |
| 021 | Incident severity influences sentiment, with noise | Accepted — superseded in part by ADR-036 |
| 022 | QA retries bounded at 2, then escalate | Accepted — superseded in part by ADR-055 |
| 023 | Per-agent least-privilege DB roles + narrow MCP tools | Accepted |
| 024 | Trained models behind sentiment and forecast tools; training is offline | Accepted — consequence amended by ADR-062 |
| 025 | Grant enforcement details: column-level feedback grant, PUBLIC revoked, cross-table invariant left to QA | Accepted — superseded in part by ADR-027 |
| 026 | SQLAlchemy models separate from Pydantic schemas | Accepted |
| 027 | Sentiment reads `service_feedback` by column, `rating` withheld; migrations are frozen snapshots | Accepted — supersedes ADR-025 in part |
| 028 | Role names required, never defaulted: a blank `DB_ROLE_*_USER` fails like a blank password | Accepted |
| 029 | Runtime inference on the Gemini API free tier; Flash-Lite default for all agents | Accepted — supersedes ADR-006 in part; superseded in part by ADR-041 |
| 030 | `feedback_text` LLM-generated once and frozen as a committed corpus | Accepted — superseded in part by ADR-036; corpus sizing replaced by ADR-038 |
| 031 | Single-shot interaction committed; multi-turn is conditional stretch | Accepted |
| 032 | Compound routing out of scope; multi-domain questions detected and split by the user | Accepted |
| 033 | Metrics reportable per individual technician, framed as decision support | Accepted |
| 034 | 120-second end-to-end timeout ceiling; latency measured, not targeted | Accepted |
| 035 | Forecast agent narrowed to three columns of `service_requests` | Accepted |
| 036 | Feedback corpus design: models, label definitions, cell rules, judge-confirmed plain labels | Accepted — supersedes ADR-019, ADR-021 and ADR-030 in part; superseded in part by ADR-039, ADR-040 |
| 037 | `sentiment_labels`: `hard_case_type` replaces `is_sarcastic`; `corpus_id` added | Accepted |
| 038 | Generator parameters: text on every feedback row, anomalies, coherence rules, corpus sizing, param_group values | Accepted |
| 039 | Positive feedback on incident rows uses no-incident positive comments | Accepted — supersedes ADR-036 in part |
| 040 | Sentiment labels defined by the written specification; human review becomes a sanity check | Accepted — supersedes ADR-036 in part |
| 041 | Remaining corpus generation on a separate paid, spend-capped project | Accepted — supersedes ADR-029 in part |
| 042 | Generator: explicit deterministic IDs, per-state timezones, committed name lists, loads as app_generator | Accepted |
| 043 | Generator world rules: SLA-conditioned incidents, snapshot semantics, age-dependent statuses, templated incident notes | Accepted |
| 044 | No final paper: limitations and results go in the evaluation report | Accepted |
| 045 | Minimal Cloud Run deploy of the reporting slice in Sprint 4 | Accepted — supersedes ADR-007 in part |
| 046 | Specialists parse their own questions; figures stay deterministic | Accepted |
| 047 | Protocol SDKs pinned (`mcp==2.2.0`, `a2a-sdk==1.1.5`); A2A used as a minimal subset | Accepted |
| 048 | LLM client policy: free by default, paid opt-in with caps, per-minute vs daily 429, list-price metering, validated structured output, one provider | Accepted |
| 049 | Per-role runtime models and thinking levels; the orchestrator stays on `gemini-3.5-flash-lite` (seed set: 28/28 vs 3.7 Flash 27/28) | Accepted — superseded in part by ADR-052 |
| 050 | Reporting answers resolve relative dates against a fixed as-of date (the dataset end), stated in every answer | Accepted |
| 051 | `locations.region`: the customer site's region, stored, written by the generator from the one state-to-region mapping | Accepted — superseded in part by ADR-067 |
| 052 | Thinking level follows the model called: each model's supported levels in `prices.toml`, default the lowest, a per-role override only if supported | Accepted — supersedes ADR-049 in part |
| 053 | Routing prompt `route_v2`: forecast covers forward-looking questions about the operation, not only request volume | Accepted |
| 054 | Routing prompt `route_v3`: the as-of date is given to the router as today's date; every routing eval reports k=3 runs | Accepted |
| 055 | The orchestrator owns the QA loop; QA verifies with its own SQL, per-agent answer-time scope | Accepted — supersedes ADR-003 and ADR-022 in part; superseded in part by ADR-069 |
| 056 | QA checks numbers without a model and interpretation with one LLM call; Pro QA comparison optional | Accepted |
| 057 | Forecast evaluation: 26-week headline holdout plus rolling-origin folds over the Q4 peaks | Accepted — superseded in part by ADR-069 |
| 058 | Forecast model form: log-linear trend plus K annual harmonics chosen from data, robust down-weighting, 26-week horizon | Accepted — superseded in part by ADR-070 |
| 059 | Sentiment training: pinned `bert-base-uncased`, stratified split, class weights, calibrated threshold, required TF-IDF baseline | Accepted |
| 060 | No agent framework; LangGraph removed from the stack | Accepted |
| 061 | Portability without Terraform; Terraform a buffer-only stretch goal | Accepted — supersedes ADR-005 in part |
| 062 | Inference inside the MCP servers; artifacts versioned in Cloud Storage; training code in `ml/` | Accepted |
| 063 | Offline read roles: `app_eval` for validation and evaluation, `app_train` for training; gold labels leave `app_qa` | Accepted |
| 064 | Sentiment split and evaluation protocol: near-duplicate groups, committed hashed split, test scored once, interpretation rule fixed in advance | Accepted |
| 065 | BERT training, comparison and latency protocol (pre-registered): fixed recipe, learning-rate budget, paired bootstrap and McNemar comparison, latency budget | Accepted — superseded in part by ADR-067 |
| 066 | Sentiment model selection, calibration and review threshold (pre-registered): `lr2e-5_v1` epoch 4 as `bert_v1`, temperature scaling, 99% / 20% review threshold | Accepted |
| 067 | Sentiment predictions stored and scored on arrival (250-comment on-demand cap); two `mcp_feedback` tools; `app_sentiment` gains region access and INSERT on its predictions table | Accepted |
| 068 | Sentiment agent: one parse call, template answers, a significance-based trend rule, explicit declines | Accepted |
| 069 | Forecast protocol (pre-registered): folds A and B, headline holdout, intervals, release gate on fold B (MAPE ≤ 30% and no worse than seasonal naive) | Accepted — superseded in part by ADR-070 |
| 070 | Forecast gate correction (26-week eligibility, 20% band ceiling) and `volume_v2` with a year-end indicator; decided after fold results, before the holdout | Accepted — superseded in part by ADR-071 |
| 071 | Forecast serving requires passing on both fold B (ADR-070 gate) and the holdout (MAPE ≤ 20%); shown error is the larger of the two | Accepted |
| 072 | Forecast agent and `mcp_volume`: served-only numbers, track record shown, future periods only; prediction code in `packages/forecast_runtime` | Accepted |
| 073 | Reporting additions: incident counts by breakdown, a single-technician filter with `find_technician`, repeat-visit drivers with a significance rule, parse prompt `parse_v3` | Accepted |
| 074 | Golden set v1: blind, independently computed expected answers | Accepted |
| 075 | Ambiguous questions are not force-routed: the router returns `ambiguous` and the orchestrator asks the user to rephrase (FR-03); `AskResponse` gains `reason` | Accepted; not in effect. Gate failed (see Results); route_v3 remains the default. FR-03 open (L-58). |
| 076 | Corrected FR-03 routing gate (supersedes ADR-075's gate only), confirmed on a fresh owner-written set | Accepted |

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

### ADR-041 — Remaining corpus generation runs on a separate paid, spend-capped project
*Date: 2026-09-24. Supersedes ADR-029 in part: its rule that development inference
stays on the free tier. The runtime model choices in ADR-029 and ADR-036 are unchanged.*

**Decision:** Flash-Lite corpus generation after round-0 batch 429 runs on a separate
Google Cloud project with billing enabled, using its own API key. The Gemma judge stays
on the free tier. The paid project has a $10 budget alert, and `build_corpus.py`
enforces a hard per-session request cap in code. The same project is reused for the
Sprint 5 paid evaluation runs that ADR-029 anticipated.

**Context:** At 480 free-tier requests per day, the remaining ~800 generation requests
(round 0 plus top-ups) would take about two more days, with Sprint 1 already over. At
list prices ($0.30/M input, $2.50/M output) the remaining generation costs about $2, and
under $5 even if top-ups run long. ADR-029 already planned a separate spend-capped paid
project for Sprint 5 evaluations, so this sets it up earlier rather than adding new
infrastructure.

**Alternatives considered:**
- *Stay on the free tier* (rejected). Free, but about two more days on a schedule
  already past its sprint boundary.
- *Upgrade the existing project* (rejected). ADR-029 notes that a project upgraded to
  paid is billed for all of its usage.

**Consequences:**
- The model ID is unchanged, and `provenance.json` records which batches ran on which
  tier. Output quality is unaffected.
- Cost is logged per request and summarized in provenance, as an estimate from list
  prices.
- The GCP budget alerts at $50/$80 (a Sprint 1 item) are set before billing is linked.
- R-02 and R-11: paid spend now exists; the budget alerts and the code cap bound it.

### ADR-042 — Generator writes explicit deterministic IDs, uses per-state timezones and committed name lists, and loads as `app_generator`
*Date: 2026-09-25. Extends ADR-015, ADR-018, ADR-030 and ADR-038. Supersedes nothing.*

**Decision:**
1. Every surrogate key is assigned by `generate.py` in generation order and inserted
   with `OVERRIDING SYSTEM VALUE`. The columns stay `GENERATED ALWAYS AS IDENTITY`
   (ADR-015).
2. Each location's state maps to one IANA timezone (`reference_data.STATE_TIMEZONE`),
   the zone where most of the state's population lives. Hour-of-day weights apply in
   site-local time, and all timestamps are stored as UTC.
3. Names, companies, streets, and cities come from short committed lists in
   `reference_data.py`. Phones use 555-01XX and emails use example.com
   (`data-dictionary.md` §9).
4. `load.py` connects as `app_generator`, never as a superuser. It validates the
   dataset, then truncates and reloads every generated table in one transaction.
5. `generate.py` is pure: no database access, no clock reads, no network. All
   generation constants live in `parameters.py` and are recorded in
   `generation_parameters`, together with the corpus file's SHA-256.

**Context:** ADR-030 requires that the same seed and corpus reproduce the same dataset.
If the database assigned IDs, they would depend on insert order and sequence state, so
foreign keys built in memory couldn't be trusted, and a partial reload would silently
renumber rows. Generating hour-of-day patterns in UTC would shift western sites'
business hours by 3-10 hours, which is the naive-timezone error §6 forbids. A faker
library would add a dependency whose output can change between versions. The §7 access
matrix already gives `app_generator` everything a load needs.

**Alternatives considered:**
- *Database-assigned IDs with a lookup pass after insert* (rejected). Not reproducible,
  and more complex.
- *Deriving the timezone from the ZIP code* (rejected). More precision than a synthetic
  dataset needs.
- *Faker* (rejected). A source of drift unless pinned, and still opaque.
- *Loading as the admin role* (rejected). It breaks ADR-023's least-privilege model.

**Consequences:**
- Identity sequences are left behind the loaded IDs, and `app_generator` has no sequence
  privileges to advance them. Any future writer that relies on auto-generated IDs must
  reset the sequences first. No current writer does.
- States that span two timezones are simplified to one.
- Every load replaces the whole dataset; there are no incremental loads.
- A dataset can be traced to both its seed and its corpus through `generation_parameters`.

### ADR-043 — Generator world rules: SLA-conditioned incidents, snapshot semantics, age-dependent statuses, templated incident notes
*Date: 2026-09-25. Extends ADR-021 and ADR-038. Supersedes nothing.*

**Decision:**
1. **Incidents depend on SLA outcome.** A request that missed its SLA gets an incident
   with a higher probability than one that met it (about 0.25 vs 0.08, derived so the
   overall rate is 10% and missed_sla is 25% of incidents). A missed request with
   incidents carries exactly one missed_sla. Both rates are derived parameters in
   `generation_parameters`.
2. **The dataset is a snapshot at the window end plus 12 hours.** Events after the
   snapshot don't exist, and statuses reflect it: an unfinished job is in progress, an
   undispatched one is open, and a survey not yet received has no row.
3. **Statuses depend on age.** Only recent incidents are open or investigating
   (ADR-038). Only invoices completed within the last 6 weeks can be pending, with a
   probability that falls with age. Disputed stays at 4% overall.
4. **Incident notes are short templated staff notes**, built from committed phrase lists
   by incident type and root cause, with no names or contact details. They are never
   readable by the sentiment role (§7).
5. The other rules `parameters.py` had left open (inactive-account stop dates, technician
   status dates and regional assignment, cancellation timing, the anomaly account's
   identity, repeat-visit scheduling) are implemented as `generate.py` does, with their
   constants recorded in `generation_parameters`.

**Context:** Building `generate.py` exposed rules that `parameters.py` had left open. An
independent incident draw cannot hold both the 10% incident rate and the 25% missed_sla
share, because only about 11% of requests miss their SLA. A flat 8% pending rate
produced invoices still pending after two years. And leaving `incident_notes` null made
the staff-notes/customer-text boundary (ADR-014, §7) a boundary around an empty column.

**Alternatives considered:**
- *Independent incident draws* (rejected). They cannot satisfy both targets without
  dropping the missed_sla coherence rule (ADR-038).
- *A flat pending rate* (rejected). It is unrealistic at any age beyond a few weeks.
- *Null incident notes* (rejected). They make the §7 boundary claim vacuous, and they
  give the reporting agent no staff text to handle.
- *LLM-generated notes* (rejected). Nothing trains on notes, so templates are enough,
  and they cost nothing and are fully deterministic.

**Consequences:**
- The SLA-incident relationship is planted. When the reporting agent surfaces it, that
  is recovery of a known signal, useful for evaluation, and the paper says so.
- The overall pending share falls below the old flat 8%; the realised figure is
  recorded.
- Templated notes are repetitive by design. They are internal staff shorthand, not a
  modelled text source.

### ADR-044 — There is no final paper; limitations and results go in the evaluation report
*Date: 2026-09-25. Supersedes nothing formally; re-points the "final paper" references in
ADR-036, ADR-038, ADR-039, ADR-040 and ADR-043.*

**Decision:** The final submission (due 2026-12-05) is a presentation plus the completed
project: the code and the deployed system. The limitations and evaluation results that
ADR-036, ADR-038, ADR-039, ADR-040 and ADR-043 assign to "the final paper" or "the paper" are
published in `docs/evaluation-report.md`, written in Sprint 6 from the Sprint 5 eval runs, and
summarized in the final presentation.

**Context:** Confirmed from the course materials: there is no final paper deliverable. The
paper was a planning assumption, repeated across `architecture.md`, the sprint log, the risk
register and five ADRs until it read as a requirement.

Clarification, recorded here because those entries cannot be edited: ADR-037 replaced
ADR-019's `is_sarcastic` flag, and ADR-038 replaced ADR-030's corpus sizing rule (15-20%
spares per cell, replaced by Poisson q99 sizing), although both headers said "supersedes
nothing". The index Status column records both.

**Alternatives considered:**
- *Write a paper anyway* (rejected). No deliverable asks for one, and it would compete with
  Sprint 6's protected buffer.
- *Scatter the limitations across `04` to `06`* (rejected). Those documents are due before
  the Sprint 5 eval runs exist, so the results and several limitations cannot be stated in
  them yet.

**Consequences:**
- Every commitment of the form "the paper states X" in ADR-036 to ADR-043 is a commitment for
  `docs/evaluation-report.md`.
- Sprint 6 plans the evaluation report, presentation and demo rehearsal in place of a final
  paper.
- `evals/results/` is the evidence the report cites.

### ADR-045 — Minimal Cloud Run deploy of the reporting slice in Sprint 4
*Date: 2026-09-25. Supersedes ADR-007 in part: Cloud SQL is provisioned in Sprint 4 for the
reporting slice rather than from Sprint 5. ADR-007's reasoning (no managed database during
local development) stands.*

**Decision:** Deploy three services, the orchestrator, `agent_reporting` and
`mcp_incidents`, to Cloud Run in Sprint 4 week 2 (2026-11-02 to 11-04), timeboxed to 3 days.
Provision the smallest Cloud SQL instance then and stop it when not in use. The full Cloud SQL
migration and the remaining services stay in Sprint 5.

- In scope: a Cloud Build trigger with an explicit deploy step; a post-deploy check that the
  serving revision is the one just built and holds 100% of traffic; secrets in Secret Manager;
  service-to-service calls authenticated with IAM ID tokens; `alembic upgrade head` and the
  grants suite run against Cloud SQL.
- Out of scope: Terraform, the API gateway, the UI, the QA agent.
- Stop rule: if the revision is not verified serving by the end of 2026-11-04, stop. Record
  R-03 as realised, write it up as the first incident in `06-production-support.md`, and leave
  the Sprint 5 plan unchanged.

**Context:** R-03 (build/deploy decoupling, which recurred on a prior project) would
otherwise surface in Sprint 5, alongside Cloud SQL, the gateway, the UI and the routing eval.
R-14: every migration, grant and load so far has run against local Docker Postgres with a true
superuser, while Cloud SQL provides `cloudsqlsuperuser`, not SUPERUSER. And
`06-production-support.md` is due 2026-11-08; with this deploy it can describe a real deployed
system.

**Alternatives considered:**
- *Keep the first deploy in Sprint 5* (rejected). It stacks the riskiest work into the most
  loaded sprint.
- *Deploy in Sprint 3* (rejected). `03` and `04` are due 10-18, alongside two new agents.
- *Deploy against Postgres on a VM or container* (rejected). Not the production path, and it
  does not test R-14.

**Consequences:**
- Sprint 4 carries one more engineering item. If Sprint 4 overflows, the fault-injection
  harness carries to Sprint 5 first, accepting that the Sprint 4 goal's "measurable catch
  rate" may slip.
- `05-test-scenarios.md` is drafted in Sprint 3 week 2 (2026-10-19 to 10-25).
- Cloud SQL instance-hours start in Sprint 4; storage bills while the instance is stopped.

### ADR-046 — Specialists parse their own questions; figures stay deterministic
*Date: 2026-09-25. Supersedes nothing.*

**Decision:** The orchestrator classifies and routes, sending the question text over A2A.
Each specialist makes one LLM call through `packages/llm` to map the question to a typed,
enum-constrained Pydantic request (`packages/schemas`), then computes its answer without a
model. The parsed request is returned alongside the answer. Answers are rendered from
templates; no LLM-written prose surrounds the figures.

**Context:** No document specified where natural language becomes tool arguments.
`architecture.md` §11 marked `agent_reporting` "deterministic — no model", which would have
left extraction to the orchestrator.

**Alternatives considered:**
- *The orchestrator extracts all parameters* (rejected). The orchestrator would have to know
  every specialist's schema, the coupling ADR-001 cites against collapsing agents into MCP
  tools. It would save one LLM call per request.

**Consequences:**
- Two LLM calls per request (classification, then parsing). The Sprint 4 eval-run pricing
  counts both.
- "Deterministic" means the figures, not the parsing.
- Because the parsed request is returned, the Sprint 4 QA agent can check it against the
  question.
- The same pattern applies to the sentiment and forecast agents.

### ADR-047 — Protocol SDKs pinned (`mcp==2.2.0`, `a2a-sdk==1.1.5`); A2A used as a minimal subset
*Date: 2026-09-25. Supersedes nothing. Fires R-12.*

**Decision:** Pin the official SDKs exactly (`==`) in each service's `pyproject.toml`:
`mcp==2.2.0` (which pins `mcp-types==2.2.0` itself) and `a2a-sdk==1.1.5`, the current
releases on PyPI on 2026-09-25. Use A2A as a minimal subset: Agent Card discovery at
`/.well-known/agent-card.json`, plus blocking `SendMessage` over the JSON-RPC binding,
returning a Task that is already `completed` or `failed`. The card declares
`streaming: false` and `push_notifications: false`. No `input-required`, no cancel, no
task polling. MCP runs over streamable HTTP in stateless mode with JSON responses, and
the client pins protocol `2026-07-28` rather than probing for it.

**Evidence the SDKs meet the spec targets (architecture §3, A-10):**
- *MCP 2026-07-28.* In the installed package, `mcp_types.version` lists
  `MODERN_PROTOCOL_VERSIONS = ("2026-07-28",)` and
  `LATEST_PROTOCOL_VERSION = "2026-07-28"`. The SDK's v2.0.0 release notes say it
  implements the 2026-07-28 revision (stateless requests with no handshake, `MCPServer`
  replacing `FastMCP`), and the v2.1.0 and v2.2.0 notes restate support for it. Observed
  locally: a client against the stateless server negotiated `protocol_version ==
  "2026-07-28"`.
- *A2A v1.0.* In the installed package, `a2a.utils.constants` sets
  `PROTOCOL_VERSION_CURRENT = "1.0"`, and the client sends `A2A-Version: 1.0` on every
  request. The changelog for 1.0.0 (2026-04-20) says "Upgraded to A2A 1.0 spec with
  proto-based types", and 1.0.3 aligns error mappings and JSON-RPC details with the 1.0
  spec. The Agent Card advertises `protocolVersion: "1.0"`.
- *Naming.* In A2A v1.0 the JSON-RPC method is `SendMessage`. `message/send` is the v0.3
  name, which this SDK serves only with `enable_v0_3_compat`, left off here. Planning
  documents that say `message/send` mean this operation.

**Context:** R-12 asked for exact pins and confirmed spec targets before any service
code. R-06 made the Sprint 2 walking skeleton the test of whether A2A costs too much
solo time, with hand-rolling the used protocol surface as the fallback. The SDKs worked
on the first attempt for both hops, so the fallback was not needed.

**Why only a subset:** ADR-031 makes every exchange single-shot, so nothing ever asks a
clarifying question (`input-required`) or continues a conversation. ADR-034 caps a
request at 120 seconds, and the skeleton answers in well under a second locally, so no
task runs long enough to need streamed progress or push notifications. Those features
would never be exercised. Declaring them in the card would advertise capabilities that
nothing tests.

**A2A's justification stays as `architecture.md` §3 states it:** portfolio value and a
swappable orchestration contract, not necessity. At this scale in-process calls would
work. The subset makes this plainer: what is left is one card fetch and one RPC call.
That is exactly the surface the R-06 fallback would have hand-rolled.

**Alternatives considered:**
- *Hand-roll the Agent Card endpoint and `SendMessage` on FastAPI/httpx* (the R-06
  fallback). Rejected: the SDKs worked, and hand-rolling would mean owning conformance.
- *`a2a-sdk` 0.3.x.* Rejected: it implements the v0.3 protocol, not v1.0.
- *`mcp` 1.x.* Rejected: it predates the 2026-07-28 revision and speaks only the
  handshake-era protocols.
- *Enable the SDK's v0.3 compatibility layer.* Rejected: there are no v0.3 peers.

**Consequences:**
- Upgrading either SDK is a deliberate act that needs a new ADR. It never happens as a
  side effect of a dependency refresh (R-12).
- A2A data parts are protobuf `Value`s, which carry every number as a double. A receiver
  validates a data part against its `packages/schemas` contract, which restores the
  integers and rejects a mismatched shape. The orchestrator does this.
- Tutorials for `mcp` 1.x (`FastMCP`, `ClientSession` plus transport) do not apply to 2.x.
- The MCP server keeps DNS-rebinding protection on, with explicit allowed hosts.
- The task store is in memory. A task finishes inside the call that created it, so no
  task outlives its request or needs sharing across replicas.
- The protocol SDKs are pinned exactly in `pyproject.toml`. Every other dependency is
  pinned by `uv.lock`, which covers the whole uv workspace: 89 packages, resolved with
  uv 0.12.19. A lock file is required before the Sprint 4 slice deploy (ADR-045), and it
  was added now rather than scheduled. CI (`uv sync --locked`) and the service images
  (`uv sync --locked --package <service>`) install from it, so CI, local and images get
  identical versions. `--locked` fails the build if the lock is stale against any
  `pyproject.toml`, so a dependency change must come with `uv lock` in the same commit.

### ADR-048 — LLM client policy: free by default, per-minute vs daily 429s, list-price metering
*Date: 2026-09-26. Supersedes nothing.*

**Decision:** Every agent calls models through one client, `packages/llm`
(`LLMClient.generate(prompt, *, model=None, response_model=None, trace_id)`), with
these policies:

1. **Free by default; paid only by explicit opt-in with caps.** The free key
   (`GOOGLE_AI_API_KEY`, the name `build_corpus.py` uses) is the default. Paid mode
   needs `LLM_MODE=paid`, the separate `GOOGLE_AI_API_KEY_PAID`, a request cap
   (`LLM_MAX_REQUESTS`) and a spend cap (`LLM_MAX_SPEND_USD`). The client refuses to
   start if any is missing, and it never falls back to the other key. The spend cap is a
   per-process list-price total. A call whose estimated cost would cross it raises
   `LLMBudgetExceeded` before it is sent. A per-process request cap, counting retries,
   applies in both modes; the free-mode default is 1,000.
2. **Per-minute and daily quota 429s are told apart.** The decision reads the
   `quotaId` in the error's `google.rpc.QuotaFailure` detail (`...PerDay...` means
   daily), from the SDK's structured `APIError.details`. A structured quota 429 is
   classified before any billing text check, because the real quota message says
   "please check your plan and billing details". A body listing both per-minute and
   per-day violations counts as daily. A per-minute 429 waits the
   `RetryInfo.retryDelay` the error states, or 30 s if it states none (as
   `build_corpus.py` did). It then retries, within `LLM_MAX_RETRY_WAIT_S` of total
   waiting (default 30 s, well inside ADR-034's 120 s), and raises `LLMRateLimited`
   past that. A daily 429 raises `LLMDailyQuotaExhausted`, naming the model, with no
   retry. Billing and permission errors raise `LLMAuthError` with no retry. Transient
   5xx errors and timeouts get two short jittered retries, then raise `LLMUnavailable`.
   Every error inherits from `LLMError`.
3. **Metering at list-price equivalent.** Every call logs one JSON line through
   `packages/common`: trace id, model, mode, tokens in and out (thinking tokens count
   as output), cost, latency, attempts and outcome. Costs come from `llm/prices.toml`,
   where each entry records its source URL and an `as_of` date, or
   `source = "UNCONFIRMED"`. Free-tier calls are costed too, and `mode` says they were
   not billed. The client keeps running per-process totals for the Sprint 4 eval
   pricing.
4. **Structured output is validated, with no repair loop.** With a `response_model`,
   the request asks for JSON matching the model's schema, and the reply is validated
   with Pydantic. On failure the client raises `LLMOutputInvalid` carrying the raw
   text. It does not retry or ask the model to repair its output.
5. **A single provider behind a narrow interface.** Gemini, through `google-genai`
   (pinned `==2.25.0`, the version `build_corpus.py` and the corpus provenance use).
   The transport is the only code that touches the SDK. There is no provider
   abstraction beyond it and no second adapter.

**Context:** Sprint 2 needs LLM calls for classification and question parsing
(ADR-046), and every later agent will make them too. `build_corpus.py` had already met
the free tier's failure modes and handled them: per-minute 429s, the daily cap, 5xx
bursts on Gemma, and billing stops on the paid project. Its policy is lifted here
rather than reinvented. It detected the daily quota by matching the quota identifier
in the error's string. That string is rendered from the structured error body, so this
client reads the same identifier from the structured field. Text matching remains only
as a fallback for a body without that detail. The corpus build's local caps always
stopped it before Gemini sent a 429, so no real 429 body existed in the repo when the
client was first written.

*Observed error shapes (updated 2026-09-26, before merge):* `scripts/capture_gemini_429.py`
captured real bodies on the free key into `tests/fixtures/gemini_errors/`, and the tests
now build on them.
- **Observed:** a 429 from `gemini-3.1-pro-preview`, which has no free-tier quota:
  `RESOURCE_EXHAUSTED` with `google.rpc.Help`, a `QuotaFailure` listing four violations
  at once (requests and input tokens, per minute and per day, all "limit: 0"), and
  `RetryInfo` `"36s"`. Its message contains "billing details", which exposed an
  ordering bug: billing text was checked before the quota detail, so every real quota
  429 would have raised `LLMAuthError`. `build_corpus.py` has the same order but never
  received a 429. The client now checks the structured quota detail first. The real
  per-minute `quotaId` carries a `-FreeTier` suffix.
- **Observed:** a 503 `UNAVAILABLE` ("high demand") with no details, from
  `gemini-3.7-flash`.
- **Still assembled:** a pure per-minute 429, because the burst hit a 503 before any
  429. A daily quota used up after normal traffic is also still assembled: the Pro call
  returned the zero-limit shape, with per-minute and per-day violations together, not
  a per-day violation on its own. Both are built from the observed 429 by keeping only
  the matching violations. Billing error bodies are assembled from `build_corpus.py`'s
  test messages, and the 500 body reuses the observed 503 envelope.

**Alternatives considered:**
- *Retry every 429 with backoff, as the SDK's own retry option would* (rejected). A
  daily 429 would be retried for up to the 120 s ceiling and then fail anyway, burning
  the request budget. A daily quota clears at Pacific midnight, not in seconds.
- *A provider abstraction with a second adapter (e.g. Anthropic)* (rejected for now).
  `architecture.md` §9 asks for model-agnosticism. A narrow transport seam gives that
  without a second adapter nothing exercises.
- *A repair loop that asks the model to fix invalid JSON* (rejected). It hides parsing
  failures that the Sprint 5 evals should count, and it adds calls that the budget and
  the 120 s ceiling must absorb.
- *Enforce the spend cap in free mode too* (rejected). Free calls cost nothing, and
  the request cap already bounds a runaway loop.

**Consequences:**
- A new dependency, `service-ops-llm`, in any service that calls a model. The key is
  held in a `Secret` and scrubbed from error messages, and a unit test proves it never
  reaches a log line, an exception, a traceback or a `repr`.
- The retry policy lives in one place. The SDK's own retries are off (`attempts=1`),
  so every wait counts once against `LLM_MAX_RETRY_WAIT_S`.
- `QuotaFailure` and `RetryInfo` are now observed. A pure per-minute 429, a daily
  quota used up after normal traffic, and a billing error remain assembled. Capture
  each when it first occurs (`scripts/capture_gemini_429.py` for the first).
- `generate` is async, since every caller runs inside an async A2A server.

### ADR-049 — Per-role runtime models: the orchestrator stays on Flash-Lite, on measured evidence
*Date: 2026-09-26. Supersedes nothing. Confirms ADR-029's Flash-Lite default for the
orchestrator with a measurement, and makes model and thinking level per-role settings.
Edited in place before merge: the first version chose `gemini-3.7-flash` for the
orchestrator, and the seed-set comparison below reversed that.*

**Decision:** Runtime models and thinking levels are set per caller role:

| Role | Model (`GEMINI_MODEL_<ROLE>`) | Thinking level (`LLM_THINKING_LEVEL_<ROLE>`) |
|---|---|---|
| Orchestrator (routing) | `gemini-3.5-flash-lite` | `minimal` |
| Specialists (question parsing, ADR-046) | `gemini-3.5-flash-lite` | `minimal` |
| QA | `gemini-3.5-flash-lite` (the value in `.env.example`) | `minimal` |

**Evidence:** The routing seed set (`evals/routing/seed_v1.jsonl`, 28 questions) ran
through the orchestrator's own `Router` and prompt `route_v1` (sha `d2b285c19d9e`) on
both candidates. There were no errors on either run. Results are in `evals/results/`:
- `gemini-3.5-flash-lite`: 28/28, on the free key, $0.0075 list-price equivalent
  (`routing_seed_v1_gemini-3.5-flash-lite_route_v1_20260926T201614Z.json`).
- `gemini-3.7-flash`: 27/28, on the paid key, $0.0201
  (`routing_seed_v1_gemini-3.7-flash_route_v1_20260926T202518Z.json`). The one miss
  was s16, "Are complaints going up?", labelled reporting and routed to sentiment.
  That label is the seed set's most contestable (`evals/routing/README.md`), so the
  miss says little either way.

**Context:** The first version of this entry put the orchestrator on
`gemini-3.7-flash`, reasoning that a misroute costs more than the price difference.
That choice was made before any routing measurement existed.

**Why Flash-Lite:**
- 3.7 Flash showed no accuracy advantage on the seed set.
- 3.7 Flash has a twentieth of Flash-Lite's free daily quota (20 against 500 requests
  per day; 5 against 15 per minute, ADR-029). The orchestrator is the first hop of every
  request, so on the free key the whole system would answer about 20 questions a day.
- The free-tier 3.7 Flash produced the R-15 "high demand" 503s: in the 2026-09-26
  capture run, and three times in a row during the checkpoint e2e.

**Caveat:** The seed set is small and mostly easy: 14 of 28 questions are clear, and
both models got every one of those right. It cannot separate two strong routers. The
Sprint 3 routing set adds harder ambiguous items and near-miss out-of-scope items,
written by the owner in dispatch phrasing, and re-tests both models. A clear accuracy
advantage for Flash there reopens this decision in a new ADR.

**Thinking level is per role because support differs by model.** `gemini-3.7-flash`
rejects thinking level `minimal` with a 400 `INVALID_ARGUMENT` ("Thinking level MINIMAL
is not supported for this model"). With one global setting inherited from
`build_corpus.py`, that failed every routing call in the first checkpoint e2e run
(2026-09-26). The level is now set per role (`llm.config.ROLE_THINKING_LEVELS`,
overridable with `LLM_THINKING_LEVEL_<ROLE>`). A role that moves to another model must
check that model's supported levels. The per-role live smoke tests (`tests/live/`)
exercise each role's real model and settings.

**Alternatives considered:**
- *`gemini-3.7-flash` for the orchestrator* (the first version of this entry;
  rejected on the evidence above).
- *Flash for every role* (rejected). Parsing a date range and the deterministic QA
  checks don't need it, and Flash's free-tier limits are far tighter.

**Consequences:**
- Every role runs on the free tier's most generous Flash-Lite quota. Eval volume still
  exceeds 500 requests a day on some runs; ADR-029's split-across-days or paid-key rule
  still applies.
- R-15's likelihood drops, since Flash-Lite had no 503s in either seed run, but it is
  not closed: Flash-Lite can also return 503s.
- `llm/prices.toml` keeps its 3.7 Flash entry for the Sprint 3 comparison.

### ADR-050 — Reporting answers resolve relative dates against a fixed as-of date
*Date: 2026-09-26. Supersedes nothing. Implements the date handling ADR-046 left open.*

**Decision:** The reporting agent resolves every relative date ("last month", "this
quarter", "the past 30 days") against an as-of date, `REPORTING_AS_OF_DATE`. It never
uses the wall clock. The as-of date defaults to the dataset window end, 2026-08-30, the
same value the incidents MCP server validates against. Every answer states the as-of
date. A question with no date at all is answered for the last full calendar month
before the as-of date (July 2026 by default), and the answer says that range was
assumed. There is no clarification turn (ADR-031). The parsing model returns no dates
for such a question, and code applies the default deterministically; the model never
guesses one.

**Context:** The synthetic dataset ends 2026-08-30 (ADR-018, ADR-043). Resolved against
the wall clock, "last month" would drift past the data and return an empty or rejected
range, and a result would change with the day it was asked. A fixed as-of date makes
answers reproducible, which the Sprint 4 QA re-check and the Sprint 5 evals need.

**Definitions** (given to the parsing prompt, `services/agent_reporting/prompts/`):
- "Last month" is the calendar month before the as-of date's month. With the default,
  that is July 2026: August is not complete on 2026-08-30.
- "This month" runs from the first of the as-of month to the as-of date. "Last quarter"
  is the previous full calendar quarter. "The past N days" ends on the as-of date.
- An explicit date or month is taken as stated.
- A range outside the dataset window fails with a clear message from the MCP tool's
  validation. It is not clipped, since clipping would answer a question that wasn't
  asked.

**Alternatives considered:**
- *Wall-clock "today"* (rejected). Answers would drift out of the data and never be
  reproducible.
- *Let the model pick a default range when the question has none* (rejected). A guessed
  range presented as an answer is what ADR-046's typed request exists to prevent.
- *Ask a clarifying question* (rejected). Interaction is single-shot (ADR-031).

**Consequences:**
- The as-of date is user-visible: it appears in every reporting answer and in the
  artifact's data part, next to the parsed request and the figures.
- Moving to a live data feed means changing `REPORTING_AS_OF_DATE` to "today". That
  change would be a new ADR.
- The walking-skeleton checkpoint question, "How many incidents were reported last
  month?", resolves to July 2026, not August.

### ADR-051 — `locations.region`: the customer site's region, stored
*Date: 2026-09-26. Supersedes nothing. Schema change.*

**Decision:** `locations` gains `region`, the customer site's region, where the work
happened. It has a CHECK constraint on the four values `northeast`, `southeast`,
`central` and `west` (a new vocabulary, `Region`, the 23rd in §5). The value is the
region whose state list in `data/generator/parameters.py` (`Regions.states`) contains
the site's `state`. That mapping is the only copy of it anywhere.

**How it is filled: the generator emits it.** The generator already draws each site's
region before its state, so it writes that region onto the row. It adds no random draw,
so nothing else in the dataset changes. The migration (`ab53ceceeffe`) only adds the
column and the CHECK. It cannot fill existing rows. A literal state list in the
migration would be a second copy of the mapping. Reading `generation_parameters` would
make the migration's result depend on live data, which ADR-027 forbids for frozen
migrations. So the column is nullable at the database level: it was added to an
already-loaded table and nothing in the migration can fill it. Completeness is enforced
twice instead. The generator's invariants refuse to load a location with a missing or
wrong region, and `validate.py` check A23 verifies every loaded location against the
recorded mapping. A database loaded before this migration needs `load.py` rerun.

**Context:** FR-06 lists region as a reporting dimension, and the first SLA-by-region
question found no region stored for a site. `locations` held only `state`, and the one
stored region, `technicians.home_region`, is where a technician is based, not where the
work happened. The site mapping existed only in the generator's parameters, which
`app_reporting` cannot read. Any region grouping would have rested on an unrecorded
mapping, the agent-against-QA disagreement data dictionary §6 exists to prevent. Raised
under the FR-06 stop rule, decided by the owner.

**Evidence nothing else changed:** the generated dataset's canonical SHA-256 went from
`4a96210afe63692671ac4ea8814b677efa0a8e674a19a63d64d3804973e99221` to
`429c49ee9ad268172da1b0c7838f835c9be32519c29b5f68a92faebac30be0a3`. Only `locations`
changed, and `locations` with `region` removed hashes identically before and after
(`4b089ff1…aca62f2`). `validate.py`: 67/67, the previous 66 plus A23; the
regional-drop check is unchanged (z 3.53).

**Alternatives considered:**
- *`technicians.home_region`* (rejected). Where the technician is based, not where the
  work happened.
- *Group by `state`* (rejected). No mapping needed, but not the dimension FR-06 names.
- *A migration backfill* (rejected). It would need either a second copy of the mapping
  or a live-data read (ADR-027).
- *A `regions` reference table* (rejected for now). More schema for four fixed names.

**Consequences:**
- `app_reporting` and `app_qa` read `region` through their existing table-level SELECT
  on `locations`; §7 is unchanged. `app_forecast` and `app_sentiment` have no grant on
  `locations`.
- The MCP metric tools offer `region` as a breakdown. Technician `home_region` stays
  out of `group_by` for now.
- Future regeneration keeps the column filled automatically. A change to the mapping is
  a parameter change, reloaded like any other.

### ADR-052 — Thinking level follows the model called, not only the role
*Date: 2026-09-30. Supersedes ADR-049 in part: its per-role thinking-level defaults
(`llm.config.ROLE_THINKING_LEVELS`). ADR-049's per-role models, and the orchestrator on
Flash-Lite, stand.*

**Decision:** Each model's supported thinking levels are recorded in
`packages/llm/src/llm/prices.toml` (`thinking_levels`, from Google's thinking docs,
checked 2026-09-30): `gemini-3.5-flash-lite` minimal, low, medium, high;
`gemini-3.7-flash` and `gemini-3.1-pro-preview` low, medium, high. The client resolves
the level for the model each call actually goes to, defaulting to that model's lowest
supported level. `LLM_THINKING_LEVEL_<ROLE>` stays as an override, but a level the model
doesn't support is refused with `LLMConfigError` before anything is sent: at startup
for the role's own model, per call for a `model=` override. A model with no recorded
levels is refused rather than guessed.

**Context:** Under ADR-049 the level was a per-role setting that ignored which model the
call went to. A `model=` override bypassed it entirely. On 2026-09-30 the routing_v1 run
of `gemini-3.7-flash` (`run_seed.py --model`) sent the orchestrator default `minimal` and
failed all 18 calls with a 400 "Thinking level MINIMAL is not supported for this model",
the same failure as 2026-09-26. The comparison only ran after a manual
`LLM_THINKING_LEVEL_ORCHESTRATOR=low`.

**Alternatives considered:**
- *Keep per-role levels and document the override* (rejected). It failed twice, and
  nothing stops a third time.
- *Silently replace an unsupported override with a supported level* (rejected). It hides
  a configuration error, and it would mean the level that ran is not the one configured.
- *Allow models with no recorded levels and send the override, or nothing* (rejected).
  Every model the project calls is in the table already, and the table is where a new
  model's price must be added anyway.

**Consequences:**
- `gemini-3.7-flash` can't be sent `minimal` (unit test
  `test_flash_37_can_never_be_sent_minimal`).
- Calling a model that isn't in `prices.toml` now fails in free mode too. Before, it was
  metered with no cost.
- `run_seed.py` records the thinking level in each result file.
- `build_corpus.py` and the generator experiments keep their own constant (`minimal`, on
  Flash-Lite and Gemma); they don't use `packages/llm`.

### ADR-053 — Routing prompt `route_v2`: forecast covers forward-looking questions
*Date: 2026-09-30. Supersedes nothing. `route_v1` stays in the repo; `route_v2` is the
orchestrator default.*

**Decision:** In `services/orchestrator/prompts/route_v2.md`, forecast covers
forward-looking questions about the operation: expected volumes, SLA outlook, trends
ahead. The forecast agent declines what it cannot project. The rule "Only future volume
is forecast" becomes "Questions about what will happen are forecast". Nothing else
changes from `route_v1`.

**Context:** The routing_v1 labelling rule, written before any run: "A question routes
to the agent whose domain it falls in, even when that agent can't answer it yet;
out_of_scope means no agent's domain covers it." `route_v1` defined forecast as future
request volume only, so a forward-looking SLA question (r04, "Are we going to hit our
SLA targets next month?") fell outside every domain. 3.7 Flash, following that
definition, routed it to out_of_scope. The forecast model itself is unchanged: weekly
request volume, univariate (data dictionary §10, decision 5). Only what is routed to the
forecast agent widens; it declines what that model can't project.

**Results** (Flash-Lite, free key, thinking `minimal`, against `route_v1`):

| Set | `route_v1` | `route_v2` |
|---|---|---|
| seed_v1 | 28/28 | 27/28 |
| routing_v1 | 17/18 | 17/18 |

The one seed_v1 change is s05 (clear, reporting), routed to forecast on the grounds that
"July 2026" is a future period. Three immediate repeats on each prompt all returned
reporting, so this is run-to-run variance, not a stable regression (L-17).

**Alternatives considered:**
- *Relabel r04 as out_of_scope* (rejected). It would change a label after seeing results,
  and it contradicts the labelling rule.
- *Keep `route_v1`* (rejected). The forecast agent's domain would be defined by what its
  first model can do, not by the questions it owns.

**Consequences:**
- routing_v1 is no longer a blind set (L-16). The Sprint 5 evaluation needs a fresh
  held-out routing set.
- A forward-looking question the forecast model can't project gets the forecast agent's
  decline, not the out-of-scope message. Until the forecast agent exists, it gets the
  orchestrator's "not available yet" text, which still says "service request volume
  forecasting" (`DOMAIN_LABELS` in `routing.py`).
- The route prompt still carries no current date (L-17).

### ADR-054 — Routing prompt `route_v3`: the router is given the as-of date; routing evals run k=3
*Date: 2026-09-30. Supersedes nothing. `route_v1` and `route_v2` stay in the repo;
`route_v3` is the orchestrator default.*

**Decision:** `services/orchestrator/prompts/route_v3.md` is `route_v2` plus one paragraph:
today's date is the as-of date (`REPORTING_AS_OF_DATE`, ADR-050), and every date in the
question is read against it, past or current on or before it, future only after it. The
orchestrator reads the same variable, with the same default (2026-08-30), as the
reporting agent, so the router and the parser share one "today". `Router` fills the date
only when the prompt has the placeholder, so `route_v1` and `route_v2` still render
unchanged. Every routing eval is run three times and reports the per-run accuracy, the
range, and every question whose route changes between runs.

In the same change, the orchestrator's forecast label (`DOMAIN_LABELS` in `routing.py`)
and the out-of-scope text say "operational forecasts (volumes, SLA outlook)", matching
`route_v2`'s forecast definition, instead of "service request volume forecasting".

**Context:** The parsing prompt has carried the as-of date since ADR-050; the routing
prompt had none. In the seed_v1 run on `route_v2`, s05 ("Which incident type was most
common in July 2026 ...") was routed to forecast because "July 2026" looked like the
future to the model (L-17). Without a date, the model's sense of "now" is whatever it
assumes on that call. Single-run comparisons also turned out to sit inside run-to-run
variance, so one run per prompt can't show whether a change helped (L-17).

**Results** (Flash-Lite, free key, thinking `minimal`, `route_v3`, as-of 2026-08-30,
three runs each):

| Set | Run 1 | Run 2 | Run 3 | Range | `route_v2` (single run) |
|---|---|---|---|---|---|
| seed_v1 | 27/28 | 28/28 | 28/28 | 27-28 | 27/28 |
| routing_v1 | 17/18 | 17/18 | 16/18 | 16-17 | 17/18 |

No errors and no retries in any run. s05 routed to reporting in all three runs. Questions
whose route changed between runs:
- s16 (ambiguous, reporting), "Are complaints going up?": forecast, reporting, reporting.
  The forecast run's reason was "future trends in complaints". The question has no date,
  so the as-of date can't settle it.
- r02 (ambiguous, reporting), "Did the route reorganization actually help the North
  zone?": reporting, reporting, out_of_scope.

r11 (near-miss, out_of_scope) was routed to sentiment in all three runs, as on every
earlier prompt (L-15).

**What this does and does not show:** The fix is justified by consistency (the router
and the parser should read dates against the same day), not by a measured gain. s05 was
right in all three `route_v3` runs, but `route_v2` also returned reporting on three
immediate repeats, so s05 alone can't separate the prompts. Both ranges overlap the
`route_v2` single runs. At this set size, a one-question difference is noise.

**Alternatives considered:**
- *Keep `route_v2` and accept the variance* (rejected). The router would still read dates
  against an unstated "now" while the parser uses the as-of date, so the two LLM calls in
  one request could disagree about what is past.
- *Use the wall-clock date* (rejected for the same reasons as in ADR-050: the data ends
  2026-08-30, and results would change with the day).
- *Report a single run, or the best of several* (rejected). A single run hides variance,
  and best-of-k overstates accuracy.

**Consequences:**
- Moving to a live data feed changes the router's "today" along with the parser's, since
  both read `REPORTING_AS_OF_DATE`.
- Each routing eval costs three times the calls: 3 x 46 = 138 Flash-Lite requests for
  both current sets, inside the free tier's 500 a day (ADR-029).
- Undated trend questions (s16) remain ambiguous between reporting and forecast. That is
  a labelling question for the held-out set, not something a date fixes.
- routing_v1 stays non-blind (L-16). The held-out set is still the source of final
  routing numbers.

### ADR-055 — The orchestrator owns the QA loop; QA verifies with its own SQL
*Date: 2026-09-30. Supersedes ADR-003 in part (QA reviewing output "before it reaches the
orchestrator") and ADR-022 in part (which agent owns the loop). Keeps ADR-022's bound of
two revisions and its escalation. ADR-027 and R-04 stay valid.*

**Decision:**
- Specialists return drafts to the orchestrator. The orchestrator sends each draft to the
  QA agent over A2A and owns the revision loop. On rejection it re-delegates to the
  specialist with QA's guidance, at most twice, inside the 120 s ceiling (ADR-034).
  Specialists never call QA.
- QA runs its own SQL as `app_qa`. It never calls the specialists' MCP tools.
- QA's scope per agent:
  - **Reporting:** recompute the figures and compare.
  - **Sentiment:**
    - At answer time, cross-check the labels in the answer against star ratings, which QA
      reads and the sentiment agent can't (ADR-027, FR-11, R-04). Only clear
      contradictions count: positive on 1-2 stars, negative on 4-5. Neutral, mixed,
      3-star and unrated comments are excluded, and coverage is reported. Reject only
      when the answer's contradiction rate is clearly above the normal rate measured on
      labelled data. Thresholds are set in Sprint 4 under a stop rule.
    - Gold labels (`sentiment_labels`) are used only in evaluation (holdout scoring and
      QA catch rate), never as an answer-time check, because new comments in a real
      deployment have no gold labels.
    - Verify the comment set, the counts, and that cited comments exist.
    - The sentiment model flags low-confidence results for human review against the
      threshold calibrated in ADR-059. QA re-applies that threshold to the confidences in
      the answer and checks that the flags match. QA doesn't set the threshold or decide
      the flags; a mismatch means the answer misreports its own confidence, and fails.
    - QA can't recompute a label, and the sentiment model is never re-run as its own
      verification.
  - **Forecast:** no one can verify a future value; QA verifies the method's track record
    on held-out weeks for the slice requested.
    - Release gate: the backtest threshold (RMSE/MAPE, set in Sprint 3 from the folds)
      is applied at model evaluation and release over the ADR-057 folds. A model that
      fails is not deployed. The backtest error per slice (`service_type`, and horizon
      bands up to 26 weeks) is stored with the model artifact (ADR-062).
    - At answer time, QA verifies the input history against its own SQL; verifies the
      arithmetic (intervals contain the point forecast; horizon at most 26 weeks); and
      looks up the stored backtest error for the requested slice and horizon, failing the
      answer if that slice is above threshold, with the error shown to the user.

**Context:**
- The topology diagram and ADR-003 placed QA differently: the diagram had QA between the
  specialists and the orchestrator, ADR-003 had it reviewing drafts "before [they reach]
  the orchestrator", and ADR-022's text made the QA agent the owner of the retry count.
- The retry counter and the time budget belong in one place, next to the 120 s ceiling.
- A specialist's own tool can't independently check that tool's defects, so QA computes
  from the database itself.
- ADR-003's per-task strategies ("backtest error threshold for forecasting,
  labeled-holdout scoring for sentiment") assumed checks that can't run on a real answer:
  a forecast can't be scored before the future arrives, and new comments have no gold
  labels. The scopes above say what QA can actually check at answer time.

**Alternatives considered:**
- *Specialists call QA* (rejected). Retry and timeout logic would be spread across three
  agents.
- *QA reuses the MCP tools* (rejected). Not independent: a defect in the tool would pass
  its own check.
- *A per-request backtest run for forecasts* (rejected). It re-measures the same model
  on every request; the stored per-slice error answers the same question.

**Consequences:**
- The orchestrator becomes a loop controller as well as a router.
- QA is the broadest-access role, as `docs/security-model.md` already states. Runtime QA
  no longer needs `sentiment_labels` or `generation_parameters`, which today's `app_qa`
  grants include because `validate.py` and the evals read as `app_qa`. An evaluation and
  training read role is decided in Sprint 3 with ADR-062's training role, and both grants
  are then revoked from `app_qa`, before the QA agent is built in Sprint 4, so the
  runtime QA role never ships holding gold labels.
- On this synthetic data, star ratings are drawn from the same label the text was written
  to, so the normal clear-contradiction rate on labelled data is zero (L-24). The rating
  cross-check will look stronger here than on real customers.
- Update the `architecture.md` agent topology diagram and QA section; FR-10 and FR-11 in
  the `02` reference copy; the Sprint 4 QA item.

### ADR-056 — QA checks numbers without a model, and interpretation with one LLM call
*Date: 2026-09-30. Supersedes nothing. Narrows the "QA: deterministic, no model"
statements; ADR-024 (QA tools are deterministic code) still holds for the tools.*

**Decision:**
- Figures are verified by deterministic SQL, which alone decides pass or fail on numbers.
- One LLM call (Flash-Lite, per ADR-049 and ADR-052) checks interpretation: does the
  specialist's parsed request (metric, range, breakdown) match the question asked?
- The Sprint 5 Flash-Lite vs Pro QA comparison becomes optional, buffer only, and is
  labelled portfolio value.

**Context:** ADR-046 put an LLM in question parsing, which makes interpretation the
riskiest unverified step: a figure can be computed correctly for the wrong question, and no
SQL query can detect that. The QA tools stay deterministic code; the interpretation check
is a call the QA agent makes, not a tool.

**Alternatives considered:**
- *No interpretation check* (rejected). The parse is the one LLM step in a reporting
  answer, and a misparse passes every figure check.
- *A stronger model for the interpretation check by default* (rejected for now).
  Flash-Lite is the measured default (ADR-049); the Pro comparison stays available as a
  buffer-only measurement.

**Consequences:**
- FR-09 and the `architecture.md` repo layout ("deterministic — no model") change to
  "figures verified without a model; one model call checks interpretation".
- The QA prompt ingests specialist output, so it is a prompt-injection surface. Added to
  `docs/security-model.md`'s still-to-write list.

### ADR-057 — Forecast evaluation: 26-week holdout plus rolling-origin folds
*Date: 2026-09-30. Extends ADR-018.*

**Decision:**
- The final 26 weeks (about March to August 2026) remain the headline holdout (ADR-018).
- Rolling-origin folds are added, with test windows that include the Q4 2024 and Q4 2025
  peaks.
- Each fold is reported separately; the folds are not averaged.

**Context:** The headline holdout excludes the Q4 budget-flush peak, the strongest
seasonal feature in the data, so on its own it would never test the peak.

**Alternatives considered:**
- *Headline holdout only* (rejected). It never tests a Q4 peak.
- *Averaging the folds* (rejected). An average hides whether the model handles the peak.

**Consequences:**
- The fold before Q4 2024 has about one year of history, so only one seasonal cycle.
- `data-dictionary.md` §6's "two to learn from, one to hold out" is reconciled with this
  entry and ADR-018.
- The backtest threshold in ADR-055's release gate is set from these folds.

### ADR-058 — Forecast model form
*Date: 2026-09-30. Supersedes nothing.*

**Decision:**
- Linear regression on log weekly volume, with a linear trend plus annual sine/cosine
  pairs.
- The number of pairs, K, is chosen on training data by an information criterion. It is
  never fixed at 3, the generator's own basis.
- Disruptions are down-weighted by a residual-based robust method, using only information
  an operator would have. Knowledge of the planted anomalies from `parameters.py` is not
  used: that is answer-key leakage, like fixing K at 3.
- The horizon is capped at 26 weeks, and prediction ranges are returned.
- The baseline is seasonal naive: each week is predicted by the same week 52 weeks
  earlier.

**Context:** The generator builds seasonality from three harmonics and plants three
anomalies (ADR-038). A model told either fact would recover the answer key, not show that
the method works.

**Alternatives considered:**
- *Fix K at 3* (rejected). Answer-key leakage.
- *Mask the planted anomaly weeks* (rejected). Uses knowledge no operator would have.

**Consequences:**
- K and the down-weighting are reported with the results, and limitations L-20 and L-21
  record both choices.

### ADR-059 — Sentiment model training
*Date: 2026-09-30. Supersedes nothing. Implements ADR-024's BERT classifier.*

**Decision:**
- Model: `bert-base-uncased`, pinned to a specific Hugging Face revision hash, fine-tuned
  for 4 classes. DistilBERT is a fallback only if the CPU latency test fails.
- Split: stratified roughly 70/15/15 by class and hard-case type, with near-duplicates
  kept on one side.
- Class-weighted loss for the mixed class (about 8%).
- A confidence threshold calibrated on the validation set; low-confidence results are
  flagged for human review (and QA checks the flags, ADR-055).
- A TF-IDF plus logistic regression baseline is required.

**Context:** On LLM-written text, a bag-of-words model may score close to BERT. If it
does, that is a finding about the corpus, reported as such, not a reason to drop the
baseline.

**Alternatives considered:**
- *DistilBERT from the start* (rejected). Only worth its accuracy cost if BERT's CPU
  latency fails against the 120 s ceiling.
- *No classical baseline* (rejected). Without it, BERT's score can't be read.

**Consequences:**
- The test split is about 1,128 comments, with 168 hard cases (L-22). Per-type scores
  are noisy, so counts are reported with them.

### ADR-060 — No agent framework
*Date: 2026-09-30. Supersedes nothing. Removes "LangGraph per agent" from the stack
(`architecture.md` §6), which no ADR had recorded.*

**Decision:** No agent framework. The agents are plain, tested Python services.

**Context:**
- The reporting agent is one parse call plus deterministic tools.
- The ADR-055 loop is bounded (at most two revisions, with a deadline), so it is plain,
  tested code.
- LangGraph would be fashion, not need.

**Alternatives considered:**
- *LangGraph per agent* (rejected). Adds a dependency and an abstraction layer for
  control flow a few lines of code express directly.

**Consequences:**
- A2A still makes an agent's internals swappable, so a framework can be adopted later
  inside one agent without changing the others.

### ADR-061 — Portability without Terraform
*Date: 2026-09-30. Supersedes ADR-005 in part (Terraform).*

**Decision:**
- Portability rests on containers, standard protocols (A2A, MCP) and Postgres.
- The deploy is scripted in Cloud Build and versioned in the repo.
- Terraform becomes a buffer-only Sprint 6 stretch goal, labelled portfolio value.

**Context:** ADR-005 named Terraform as how the project stays portable. The portability
claim actually rests on what runs, not on how the infrastructure is declared, and the
Sprint 4 deploy (ADR-045) is already scripted in Cloud Build.

**Alternatives considered:**
- *Terraform from Sprint 4* (rejected). Infrastructure-as-code work competes with the
  timeboxed slice deploy for no change in what is deployed.

**Consequences:**
- `infra/terraform/` is marked as a stretch goal in the repo layout.

### ADR-062 — Where models run and how artifacts ship
*Date: 2026-09-30. Amends a consequence of ADR-024 (training-script location); ADR-024's
decision stands.*

**Decision:**
- Inference runs inside the MCP servers (`mcp_feedback`, `mcp_volume`), which keeps
  ADR-024 intact: the tools wrap the models.
- Model artifacts are versioned in Cloud Storage. Cloud Build pulls a pinned version into
  the image at build time. Locally, compose mounts `models/`.
- Training code lives in `ml/sentiment/` and `ml/forecast/`, not in the agent folders.
  Training is offline and never deployed.
- Training needs `sentiment_labels`, which `app_sentiment` correctly can't read. The
  read-only role training uses is decided in Sprint 3 (candidate: a dedicated training
  role); never a runtime role.

**Context:** ADR-024 put training scripts in each agent's folder, which would ship
training code and its dependencies in deployed images and tempt a runtime role to hold
training grants.

**Alternatives considered:**
- *Training scripts in the agent folders* (rejected, as above).
- *Artifacts committed to git* (rejected). Checkpoints can exceed 100 MB (ADR-024).

**Consequences:**
- The forecast artifact carries the per-slice backtest error that QA looks up (ADR-055).
- The training-role decision is made together with the evaluation read role that takes
  `sentiment_labels` and `generation_parameters` from `app_qa` (ADR-055).

### ADR-063 — Offline read roles: `app_eval` for validation and evaluation, `app_train` for training; gold labels leave `app_qa`
*Date: 2026-10-01. Decides the training role ADR-062 left open and carries out ADR-055's revocation. Supersedes nothing.*

**Decision:**
- Two read-only login roles, used only by offline scripts on the developer machine and never held by a deployed service:
  - `app_eval`: SELECT on the ten tables `app_qa` held before this change. Used by the validation scripts, the eval harnesses and the Sprint 5 rating-sensitivity check.
  - `app_train`: SELECT on `sentiment_labels`, plus exactly the columns the runtime models read: `app_sentiment`'s four `service_feedback` columns and `app_forecast`'s three `service_requests` columns.
- `app_qa` loses SELECT on `sentiment_labels` and `generation_parameters`.
- Names and passwords come from required `DB_ROLE_EVAL_*` and `DB_ROLE_TRAIN_*` variables (ADR-028). A unit test fails if any service, compose file or Dockerfile references them.

**Context:**
- ADR-055: the runtime QA role must not ship holding gold labels. ADR-062: training needs `sentiment_labels`, and never through a runtime role.
- Giving training exactly what inference reads, plus the labels, enforces two existing rules by grant instead of convention: a sentiment model trained with `rating` would undermine QA's independent rating cross-check (R-04, ADR-027), and reading `generation_parameters` during forecast training is the answer-key leakage ADR-058 rules out.
- The check that every feedback row has a label is a generator check, not an answer-time check, so it moves to the validation suite.

**Alternatives considered:**
- *One combined evaluation and training role* (rejected). One fewer role, but nothing would stop a training script from reading `rating` or `generation_parameters`. Both leakage rules would be convention only, against ADR-023's grant-over-convention stance.
- *Training or validation as `app_qa`, or as any runtime role* (rejected). ADR-055 and ADR-062.
- *Scripts as the admin role* (rejected). Breaks least privilege, as ADR-042 found for the loader.

**Consequences:**
- Seven roles: four runtime roles (`app_reporting`, `app_sentiment`, `app_forecast`, `app_qa`) and three offline roles (`app_generator`, `app_eval`, `app_train`). `data-dictionary.md` §4, §7, §8 and §10 updated.
- Grants control tables and columns, not rows: training could still read the test split's labels. Split integrity rests on a split fixed and committed before training, and on review (L-25).
- Both credentials stay on the developer machine. Training on a hosted notebook reads an exported file, never the database.
- `alembic upgrade head` now needs the four variables wherever it runs, including the Sprint 4 Cloud SQL deploy (ADR-045), even though no deployed service uses them. Their passwords go in Secret Manager like the others.
- The `02` reference copy (FR-11, ground-truth tables "used by the QA agent") was already queued for correction by ADR-055.

### ADR-064 — Sentiment split and evaluation protocol
*Date: 2026-10-01. Extends ADR-059 (split, baseline) and ADR-040 (what the sentiment eval reports). Supersedes nothing.*

**Decision:**
- Near-duplicates are grouped before splitting: character 5-gram Jaccard > 0.6 on lowercased, whitespace-normalised text, across all rows (ADR-036 applied the same rule only within a corpus cell). Connected components are groups; a group never spans two splits.
- Whole groups are split about 70/15/15, stratified by `true_sentiment` × `hard_case_type`, with seed 20261001. The split file (`feedback_id`, `corpus_id`, `split`; no labels, no text) and a manifest carrying its SHA-256 are committed before any training code exists. Loaders verify the hash.
- Settings are chosen on validation only. Each model is scored on test once; every test scoring is recorded in an append-only ledger.
- Headline metric: macro-F1. Also reported: per-class P/R/F1, the confusion matrix, hard-case accuracy by type with n and the judge's disagreement rate on the same subset, neutral accuracy by kind with n, and mixed-class recall.
- Baselines: TF-IDF plus logistic regression over a fixed six-config grid (required, ADR-059), plus two diagnostics: majority class, and length-only logistic regression.
- Interpretation rule, fixed before any test result: if TF-IDF test macro-F1 is at least 0.95, BERT is judged only on hard-case accuracy and mixed-class F1. If the length-only diagnostic reaches macro-F1 0.60, length is reported as carrying class signal.

**Context:**
- ADR-059 required near-duplicates on one side but didn't define them. The corpus was deduplicated only within cells, and minimal neutrals in different service-type cells can be near-identical.
- Labels are attached to corpus comments drawn at random, so time order carries no drift; a random split doesn't lose the realism a time-based split would add.
- Grants can't enforce row-level separation (L-25). A committed, hashed split and a test ledger make split integrity checkable after the fact.
- Fixing the interpretation rule before the results stops the bar for BERT moving to fit them.
- Measured: 7,500 groups; largest group 2 rows; 0.56% of rows (42) in groups larger than 1; 1 mixed-label group (2 rows); test split 1,128 rows, 42 sarcastic, 126 implicit.

**Alternatives considered:**
- *Row-level stratified split* (rejected). Near-identical texts on both sides inflate test scores.
- *Time-based split* (rejected). The corpus has no temporal signal to protect.
- *Cross-validation instead of a fixed test split* (rejected). BERT on CPU makes repeated fine-tuning costly, and one fixed test split keeps every model comparable.
- *Choosing the bar for BERT after seeing TF-IDF* (rejected). It invites moving the goalposts.

**Consequences:**
- BERT, its calibration, and any fallback model use split_v1 and the same scorer.
- A change to the split is a new version (split_v2) and a new ADR, never an edit.
- Per-type hard-case scores are noisy at these counts (L-22); n is always shown.

### ADR-065 — BERT training, comparison and latency protocol (pre-registered)
*Date: 2026-10-01. Extends ADR-059 and ADR-064. Committed before any BERT code or result exists. Supersedes nothing.*

**Decision:**
- Training: pinned `bert-base-uncased` revision; class-balanced cross-entropy; AdamW (weight decay 0.01), 10% warmup then linear decay; batch 16; at most 4 epochs with early stopping on validation macro-F1 (patience 1); seed 20261001; train split only. `max_length` is the smallest of 32/64/96/128 covering 99.5% of train comments.
- Search budget: learning rates {2e-5, 3e-5} if a 4-epoch run is projected at 3 hours or less, otherwise 2e-5 only. The run and epoch with the best validation macro-F1 is the model; nothing else is tuned.
- Confidence threshold: calibrated on validation (method fixed in the 3b prompt before calibration runs); low-confidence results are flagged for review.
- Test: the selected model is scored once and recorded in the ledger, like the baselines.
- Comparison with TF-IDF, on the same test comments:
  - Macro-F1 difference with a paired bootstrap 95% interval (10,000 resamples, seed 20261001).
  - Per-comment correctness compared with McNemar's exact test on the full test set and on the sarcastic, implicit and mixed subsets, reporting the discordant counts (comments one model gets right and the other wrong) every time.
  - BERT is called better on a metric only if the interval excludes zero (macro-F1) or the McNemar p-value is below 0.05 (subsets). Every subset is reported, whatever its result.
  - ADR-064's interpretation rule did not fire, but TF-IDF's margin was 0.007 with its selected configuration at the grid edge (L-26). The comparison reports this beside the overall result.
- Latency budget (Cloud Run proxy, ADR-034's 120 s ceiling):
  - warm inference on the realistic worst slice is at most 30 s, and cold start at most 20 s.
  - The realistic worst slice is the largest single-account or single-region quarter. Whole-window and 12-month slices are reported but are not the gate, because a whole-window question needs a different design (sampling or stored predictions), decided separately if needed.
  - If BERT fails on the configuration chosen for deployment, DistilBERT is evaluated under this same protocol (ADR-059).

**Context:**
- On test, TF-IDF scored macro-F1 0.943, with sarcastic 36/42 and mixed F1 0.883. Differences of a few comments are within noise at these sizes, so an unpaired comparison of two accuracies can't support a claim.
- The orchestrator allows up to 2 revision cycles (ADR-055). If each re-runs inference, 3 × 30 s plus a 20 s cold start plus about 6–8 LLM calls approaches 120 s. The sentiment MCP server should therefore reuse a request's inference across revisions (decided with `mcp_feedback`).
- Latency doesn't depend on fine-tuned weights, so it is measured with the untrained model before any training is spent.

**Alternatives considered:**
- *Comparing headline scores only* (rejected). It can't distinguish a gain from noise on 42 sarcastic comments.
- *A wider hyperparameter search* (rejected). CPU-only training makes each run cost hours, and validation selection over a large grid overfits a 1,129-comment validation set.
- *Measuring latency after training* (rejected). A failure would waste the training time.

**Consequences:**
- The likely honest outcome is that BERT is indistinguishable from TF-IDF overall and differs, if at all, on hard cases. That is reported as the finding.
- 3b fixes the calibration method before running it.

### ADR-066 — Sentiment model selection, calibration and review threshold (pre-registered)
*Date: 2026-10-01. Extends ADR-059 and ADR-065. Committed before calibration runs and before any BERT test result exists. Supersedes nothing.*

**Decision:**
- Selected model: `lr2e-5_v1` at epoch 4 (validation macro-F1 0.9767), by ADR-065's rule. It is exported as artifact `bert_v1` (weights, tokenizer, label map), with a committed manifest of file hashes and calibration values.
- Calibration: temperature scaling. One scalar T is fitted on the validation logits by minimising negative log-likelihood, and calibrated probabilities are softmax(logits / T). Expected calibration error (15 equal-width bins) is reported before and after.
- Review threshold: τ is the smallest calibrated top-class probability at which predictions at or above τ reach at least 99% accuracy on validation. If that would flag more than 20% of validation comments, τ is set where 20% are flagged, and the accuracy reached is reported. Comments below τ are flagged for human review; QA checks the flags (ADR-055).
- Test reporting adds ECE, flag rate, accuracy on flagged and un-flagged predictions, and the share of errors flagged, overall and for the sarcastic, implicit and mixed subsets.

**Context:**
- Raw transformer confidence is usually overconfident. Temperature scaling corrects it with a single parameter and never changes which class wins, so it cannot affect the comparison with TF-IDF.
- The 99% target and the 20% cap balance the reliability of answers that aren't flagged against the size of the human-review queue. 20% is the owner's estimate of what an operations team would review.
- Both runs peaked at the epoch cap (L-30). The cap was fixed in advance, so it is not extended.

**Alternatives considered:**
- *Isotonic or Platt scaling per class* (rejected). These need more parameters than about 1,129 validation comments support for a 4-class model.
- *A fixed threshold such as 0.5* (rejected). Without calibration the number has no meaning.
- *Fitting T and τ on test* (rejected). That would turn the test set into training data.

**Consequences:**
- T and τ are fitted on the same validation split used for selection, so validation calibration figures are optimistic. Only test figures are reported as results.
- `mcp_feedback` loads `bert_v1` with its manifest's T and τ, and checks the file hashes at start-up.

### ADR-067 — Sentiment predictions are stored and scored on arrival; the sentiment server gains region access
*Date: 2026-10-01. Supersedes ADR-051 in part (app_sentiment's lack of a locations grant) and ADR-065 in part (the latency gate's slice definition). Extends ADR-062. Replaces the `get_feedback_batch` tool contract defined in `architecture.md`.*

**Decision:**
- New table `sentiment_predictions` (`feedback_id`, `model_version`, `predicted_label`, `confidence`, `flagged`, `scored_at`), keyed on (`feedback_id`, `model_version`). `model_version` is the SHA-256 of the committed artifact manifest.
- `mcp_feedback` answers only from stored predictions. Before answering, it scores any comments in the requested range that have no prediction for the current version, at most 250 per request (newest first), stores them, and reports coverage (`n_comments`, `n_scored`, `complete`). Newest first because in a live system the unscored comments are the most recent, and the latest period is what an operations question most needs; a partial answer therefore leaves out the oldest buckets instead. A one-off backfill scores the existing data; a new model version requires a fresh backfill.
- The cap of 250 is the largest multiple of 50 that fits the unchanged 30 s warm-inference budget (ADR-065) at the slowest observed throughput of the real `mcp_feedback` image at 1 CPU / 2 GiB: 300 real comments, 3 repeats per batch size, batch 8 median 31.8 s (9.42 comments/s), slowest 9.28/s, so 250 takes at most 26.9 s; batch 16 median 35.5 s (8.46/s). Batch 8 is used. The latency proxy had measured 10.7/s at batch 16 (ADR-065, L-28); the comments here match the proxy's train-split texts in length and padding (24.6 against 24.4 mean tokens; 41.5 padded tokens per comment at batch 16 in both), so the texts don't explain the gap. The proxy ran a separate image on a Docker VM since rebuilt; the cause isn't isolated. Batch 8 wins on padding: 38.2 padded tokens per comment against 41.5.
- Two tools: `get_sentiment_summary` returns counts, shares, buckets and flag counts with no text; `get_feedback_examples` returns at most 5 comments with text, for citation. Neither tool writes or accepts free-form query input.
- Grants: `app_sentiment` gets SELECT and INSERT on `sentiment_predictions` (no UPDATE or DELETE), plus column SELECT on `service_requests` (`request_id`, `location_id`) and `locations` (`location_id`, `region`). `app_qa` and `app_eval` get SELECT; `app_generator` gets ALL. `app_train` gets nothing, so the model can never train on its own output.
- The model loads on first need; artifact hashes are verified at start-up.

**Context:**
- FR-07's own example, "is sentiment trending down in a region?", needs region, which `app_sentiment` could not resolve, and it spans months. At about 9 comments per second on 1 CPU, a multi-month regional question (400–800 comments) takes 45–90 s per pass, and an all-accounts quarter took 65 s in the proxy (L-29). Per-request inference cannot meet the 120 s ceiling with revision cycles (ADR-055); stored predictions answer in about a second at any range.
- Scoring on arrival is how production systems handle recurring sentiment reporting. QA can then recompute counts directly from stored predictions.
- Region and `location_id` carry no personal information and no staff-written text; `rating` stays withheld (ADR-027).

**Alternatives considered:**
- *Per-request inference with a cap and an offer to narrow* (rejected). The cap would refuse FR-07's central question.
- *Classifying a random sample above the cap* (rejected). Monthly trend buckets become too noisy to read.
- *A separate offline scoring role and job* (rejected for now). It adds a role and a deployment; scoring inside the server reuses the deployed model and its hash checks. A scheduled scorer is future work.
- *Granting `account_id` and account names too* (rejected). No requirement needs account-level sentiment; it can be added later with its own ADR.

**Consequences:**
- `mcp_feedback` gains write access to exactly one table, through internal code only; the security model records it.
- Answers can be partial when more than 300 comments in range are unscored. The agent must state the coverage (4b).
- The latency gate of ADR-065 now applies only to on-demand scoring of at most 250 comments. The first scoring pass after the container starts is about twice as slow as a warm one (68.8 s for 300 comments, model load 1.25 s included), so the 30 s budget holds for warm requests only.
- Sprint 4 QA verifies sentiment answers by recomputing them from `sentiment_predictions` and cross-checking ratings. A sentiment answer fails only on errors the agent can fix (wrong comment set, miscounts, a summary that misstates the numbers), never on disagreement with a label.

### ADR-068 — Sentiment agent: one parse call, template answers, a significance-based trend rule, explicit declines
*Date: 2026-10-01. Applies ADR-046 and ADR-047 to sentiment; builds on ADR-067. Supersedes nothing.*

**Decision:**
- The agent makes one LLM call to parse the question into `SentimentRequest` (time range, optional region, bucket, whether a trend or examples are wanted, or an unsupported dimension). Every figure comes from `mcp_feedback`; answers are rendered from templates.
- Customer comments are never sent to an LLM by the agent. Quoted examples (at most 3) go straight into the template.
- Every answer states the range, the as-of date, the region if any, counts and shares by label, and the flagged count. When coverage is incomplete, the answer opens with the coverage line.
- A question that names no period gets a range applied by code, never by the model: for a trend question, the six whole calendar months ending at the as-of month (2026-03-01 to 2026-08-30 by default), in monthly buckets; otherwise ADR-050's default, the previous calendar month. The answer says the range was assumed.
- Trend rule: compare the negative share in the latest bucket with the pooled negative share of all earlier buckets in range. Report "rose" or "fell" only if both sides have at least 20 comments and a two-proportion z-test gives p < 0.05; otherwise "no clear change". Both shares and counts are always shown.
- Account, technician and service-type breakdowns are declined with a message naming what is supported. No MCP call is made for a decline.

**Context:**
- FR-07 asks whether sentiment is trending down in a region. A monthly regional bucket holds about 40 comments, where the negative share's sampling error is about 6 points, so "trending" has to mean more than a visible change.
- Negative share is the measure because FR-07's purpose is surfacing dissatisfaction.
- Template-only answers keep every figure checkable and remove the agent as a prompt-injection target: customer text has nothing to instruct.
- FR-07's own question names no period. ADR-050's one-month default, which is scoped to the reporting agent, would give a trend question a single bucket, so trend questions get a six-month default instead.

**Alternatives considered:**
- *A fixed percentage-point threshold* (rejected). At these sample sizes it reports noise as trends.
- *An LLM-written summary* (rejected). It would put customer text in a model's context and make figures uncheckable (ADR-046).
- *Answering account-level questions from region data* (rejected). It misstates what was asked.

**Consequences:**
- Many short-range regional questions will honestly return "no clear change". That is the correct answer at these sample sizes.
- Sprint 4 QA verifies the trend claim by recomputing the test from `sentiment_predictions`.
- An account breakdown needs a new grant and its own ADR (ADR-067's alternatives).

### ADR-069 — Forecast protocol (pre-registered): folds, holdout, intervals and release gate
*Date: 2026-10-02. Extends ADR-057 and ADR-058. Supersedes ADR-055 in part: the release gate is applied on fold B only, not over both folds; and ADR-057 in part: its consequence that the gate threshold is set from both folds. Committed before any forecast code or result exists.*

**Decision:**
- Series: weekly counts of `service_requests` by `scheduled_datetime`, all statuses, ISO weeks (Monday start, UTC), complete weeks only: 156 weeks from 2023-09-04 to 2026-08-30. Slices: the total and each of the 5 service types, each modelled separately.
- Model (ADR-058): OLS on log weekly count with an intercept, a linear trend and K sine/cosine pairs (period 52.1775 weeks). K ∈ {0, …, 6} is chosen by AICc on the OLS fit, then refitted at that K with robust regression (Tukey biweight, c = 4.685, MAD scale). The point forecast is the exponentiated fitted log (the median). 80% and 95% intervals come from the robust scale and leverage, on the log scale, then exponentiated. Horizon capped at 26 weeks.
- Baseline: seasonal naive (the same week 52 weeks earlier).
- Evaluation windows, each fitted only on weeks before its origin:
  - Fold A: test 2024-09-02 to 2025-03-02 (26 weeks, over the Q4 2024 peak); about one year of history. Reported, not gated.
  - Fold B: test 2025-09-01 to 2026-03-01 (26 weeks, over the Q4 2025 peak); about two years of history. Sets the release gate.
  - Headline holdout: test 2026-03-02 to 2026-08-30 (26 weeks). Scored once per model, recorded in an append-only ledger.
  The folds end before the holdout begins, so no fold result uses holdout weeks.
- Metrics: MAPE (primary) and RMSE, overall and by horizon band (1–4, 5–13, 14–26 weeks); interval coverage at 80% and 95%.
- Release gate (ADR-055): a slice and band passes if, on fold B, the model's MAPE is at most 30% and no higher than seasonal naive's. Failing slice-bands are stored as failing; QA refuses forecast answers for them and shows the error.
- "Beats the baseline" (the Sprint 3 goal): lower MAPE than seasonal naive on the headline holdout, total slice.
- Production model `volume_v1`: refitted on all complete weeks for every slice. Its manifest carries the fold B error table and the gate verdicts.

**Context:**
- Fold A's single year of history barely separates trend from season, and the deployed model trains on three years. Gating on fold A would block deployment over a condition the deployed model never faces, so fold A is reported as a stress test.
- The headline holdout misses the Q4 peak (ADR-057); the folds cover it.
- Weekly noise is about 10.6% effective (ADR-038), so about 8–9% MAPE is the floor on the total. Service-type slices have fewer requests a week and noisier counts. The 30% ceiling is the owner's operational judgment: a forecast whose average weekly error is within 30% is still usable for coarse, service-type-level staffing on messy operational data. MAPE is an average error, not a confidence level; how often the true value falls inside the forecast range is measured separately, by interval coverage. The ceiling is deliberately loose, so the binding condition for most slices is expected to be beating seasonal naive.
- Robust down-weighting uses only residuals, never the generator's anomaly list (ADR-058).

**Alternatives considered:**
- *Gating on both folds* (rejected). Fold A's history is unrepresentative of deployment.
- *Fold windows reaching into the holdout* (rejected). They would let fold results use holdout weeks.
- *Choosing K on holdout or fold error* (rejected). The information criterion keeps selection inside each training window.
- *A mean forecast with a smearing correction* (rejected for now). The median is the natural point for a log model, and operators read it as "typical week".

**Consequences:**
- Some service-type slices may fail the gate; their forecasts are not served.
- Interval coverage is reported, not gated.
- Changing any choice above after results means a new ADR and a new model version.

### ADR-070 — Forecast gate correction and `volume_v2` with a year-end indicator (decided after fold results, before the holdout)
*Date: 2026-10-02. Supersedes ADR-069 in part: the release-gate rule, and the production model becomes `volume_v2`. Supersedes ADR-058 in part (the model form gains a calendar year-end indicator; ADR-058's leakage rules — K chosen from data, no planted-anomaly knowledge — still hold). Decided after the ADR-069 fold results were seen and before any holdout result existed; disclosed as post-hoc.*

**Decision:**
- The ADR-069 gate result stands on the record: `volume_v1` failed on the total slice in bands 1–4 (model 11.9% vs naive 4.3% MAPE) and 14–26 (11.9% vs 10.9%), and in several service-type bands.
- Corrected gate, applied to fold B: a slice is eligible only if its model MAPE over the full 26-week window is no higher than seasonal naive's. Each horizon band of an eligible slice passes if its band MAPE is at most 20%. Ineligible slices and failing bands are not served.
- `volume_v2` = the ADR-069 model plus one regressor: a year-end indicator for ISO weeks containing December 25 or January 1, included in both K selection and the robust fit. `volume_v2` is the production model whatever the holdout shows; the holdout reports v1 and v2 side by side.
- The holdout is scored once each for v1, v2 and seasonal naive.

**Context:**
- ADR-069 compared model with baseline inside each band. The 1–4 band holds 4 weeks; with about 10% weekly noise, that comparison cannot separate two forecasters. The flaw does not depend on the direction of the result: the comparison would have been equally uninformative had the model won. Over 26 weeks the comparison carries information. The per-band 20% ceiling, which judges usefulness rather than relative skill, is kept.
- Disclosure: `volume_v1`'s total slice passes the corrected gate as well, so the correction, not v2, is what changes the total's verdict. The corrected gate still rejects most service-type bands.
- v1 overpredicted the Christmas 2025 week by 52%, while seasonal naive was 1% off. The evidence for a year-end effect was available before that test window: v1's robust fit down-weighted the year-end weeks of 2023 and 2024 in training. An operator inspecting their own history would see a recurring year-end dip. The indicator is defined from the calendar (Dec 25, Jan 1), not from the generator's trough dates, which would be answer-key leakage (ADR-058).
- The production forecast's 26 weeks from 2026-08-31 include Christmas 2026, so v1 would overstate holiday-week volume.

**Alternatives considered:**
- *Accept ADR-069's verdicts and serve nothing failing* (rejected). It would refuse the total's near-term forecast on the strength of a 4-week comparison that measures noise.
- *Lower the bar on service-type slices* (rejected). Nothing in the fold results justifies it.
- *Indicators for every US federal holiday* (rejected). Only the year-end shows a recurring residual in training; adding the rest would be fishing for fit.
- *Choosing v1 or v2 after the holdout* (rejected). That would turn the holdout into a selection set.

**Consequences:**
- Nothing in this dataset tests the year-end fix blindly: the holdout (March to August) contains no December. The fold evidence for it is not blind.
- `gate_v1` remains in the code to reproduce the pre-registered verdicts.
- Sprint 4 QA reads the corrected-gate verdicts from the `volume_v2` manifest.

### ADR-071 — Forecast serving requires passing on both fold B and the holdout
*Date: 2026-10-02. Supersedes ADR-070 in part: which slice-bands are served. Decided after the holdout was scored. It only removes slice-bands from service; no reported evaluation figure changes.*

**Decision:**
- A forecast slice-band is served only if it passes ADR-070's gate on fold B and its `volume_v2` holdout MAPE is at most 20%.
- The error shown with a served forecast, and used by QA (ADR-055), is the larger of the fold B and holdout MAPE for that slice-band.
- The manifest records both errors, the ADR-070 verdict and the served flag.

**Context:**
- Four slice-bands passed fold B and then missed on the blind holdout: install 14–26 weeks (18.5% → 29.4%), upgrade 5–13 (17.3% → 26.9%), upgrade 14–26 (14.6% → 21.2%) and repair 1–4 (7.7% → 27.9%). With about 20–40 requests a week per service type, a single 26-week window cannot certify a slice-band on its own.
- Once the holdout has been scored and reported, it is part of the model's track record. The production model already trains on those weeks, and QA's per-slice track record should include them.
- The rule can only tighten what is served, so it cannot flatter any result.

**Alternatives considered:**
- *Serve on fold B alone* (rejected). It knowingly serves forecasts that missed by 20–30% on blind data, while showing a smaller error.
- *Raise the ceiling for service types* (rejected). Nothing justifies it, and it would be decided after the results.
- *Monthly service-type forecasts* (deferred). Aggregation would reduce the noise, but it is new scope.

**Consequences:**
- Served: the total at every horizon band; install 5–13 weeks; repair 5–13 weeks. Every other service-type slice-band is refused, with its error shown.
- No later holdout exists in this dataset, so the served set has no further blind test.

### ADR-072 — Forecast agent and `mcp_volume`: served-only numbers, track record shown, future periods only
*Date: 2026-10-02. Applies ADR-046, ADR-047 and ADR-055 to forecasting; serves `volume_v2` under ADR-071. Supersedes nothing. Extends ADR-035: `get_order_volume_history` reads only `app_forecast`'s three columns, and its contract `(slice, weeks ≤ 52)` replaces the `(granularity, window)` sketch in `architecture.md`. Extends ADR-062: the prediction path moves, unchanged, into the workspace package `packages/forecast_runtime`, which both `ml/forecast` and `mcp_volume` import, so no training code is deployed.*

**Decision:**
- `mcp_volume` serves the stored `volume_v2` artifact through two tools: `get_volume_forecast(slice, horizon_weeks ≤ 26)` and `get_order_volume_history(slice, weeks ≤ 52)`. It never returns forecast numbers for a slice-band the manifest marks unserved; it returns only the flag and the shown error.
- The forecast agent makes one parse call into `ForecastRequest`, then renders from templates. Every served forecast shows the held-out error for its horizon band; every unserved band is named with its error; weekly figures carry 80% ranges; a period total is the sum of weekly forecasts and carries no range.
- Period rules: forecasts cover future weeks only. A period maps to the ISO weeks whose Monday falls inside it. A bare month name or quarter means its next occurrence after the as-of date (2026-08-30). "Next month" is September 2026. Requests past 26 weeks are served to the cap; past periods are declined.
- Forecasts covering weeks the year-end indicator marks carry a caveat that the adjustment is unvalidated (ADR-070).
- Declined: SLA outlook, incident or sentiment forecasts, and region, account or technician breakdowns. Each decline names what is supported.

**Context:**
- ADR-055 requires the error to be shown with every forecast. ADR-071 decides which slice-bands are reliable enough to show at all. Withholding numbers at the server keeps an unreliable figure from ever reaching the agent or the user.
- Summing per-week intervals would overstate a total's uncertainty, and a correct total interval needs simulation, which isn't worth building at this scale.
- Forecast questions are about the future, so a bare month means its next occurrence. This avoids the reporting-style rule's August ambiguity (L-38).
- ADR-053 routes every forward-looking question here; the model projects request volume only.
- ADR-062 keeps training code out of deployed images. The prediction functions (week indexing, the year-end indicator, the design matrix, the forecast from saved coefficients, the hash-checked artifact load) are pure numpy and are what serving needs; moving them into a package keeps one code path for evaluation and serving.

**Alternatives considered:**
- *Return all numbers and let QA refuse* (rejected). Defence in depth is cheaper at the source, and QA still checks in Sprint 4.
- *A simulated interval for period totals* (deferred). Correct, but new scope.
- *Forecasting SLA compliance or incidents* (rejected). No model or evaluation exists for them.
- *Copying `ml/forecast` into the `mcp_volume` image* (rejected). It would deploy training and evaluation code (ADR-062).

**Consequences:**
- Most service-type questions get partial or refused answers, with the reason shown. That is the honest result of ADR-071.
- Sprint 4 QA verifies forecast answers against the manifest (served flags and shown errors), the history against its own SQL, and the arithmetic (intervals contain the point; the total equals the sum).

### ADR-073 — Reporting additions: incident counts by breakdown, a single-technician filter, repeat-visit drivers, `parse_v3`
*Date: 2026-10-02. Extends ADR-033 (technician-level reporting), ADR-046 (one parse call, template answers) and ADR-050 (dates are resolved as before). Resolves L-06. Supersedes nothing.*

**Decision:**
- **Incident counts by breakdown.** `get_incidents_by_date_range` gains an optional `group_by`: `account`, `region`, `service_type`, `technician`, `incident_type` or `severity`. Incidents are dated by `reported_at`, as for the ungrouped count. `technician` means `incidents.attributed_technician_id`; incidents with none are reported as their own "unattributed" group. Groups are ranked highest count first and capped at 25, like the other metrics; the answer text names the top groups and the data part keeps every group the tool returns.
- **Single-technician filter.** A new tool, `find_technician(name)`, matches a name against technicians' display names, case-insensitively: the whole name, or every word of the query against whole words of the name (so "Priya" finds every Priya). It returns at most 5 matches (`technician_id`, display name) and the total match count. It rejects wildcard and pattern characters and never builds SQL from the name; the matching runs over the fixed list of technicians. The four metric tools and the incident-count tool gain an optional `technician_id` filter, applied to the same column each uses for `group_by=technician`: incident count, `attributed_technician_id`; incident rate, `attributed_technician_id` for incidents over `archived_requests.technician_id` for completed requests; SLA compliance and first-time fix, `archived_requests.technician_id`.
  - No match: the answer is "No technician matches {name}", with no figures.
  - More than one match: the answer lists them and asks the user to ask again with the full name, with no figures. The turn ends there and no state is kept, so this is a single-shot answer (ADR-031), not a clarification turn.
  - One match: the filtered answer, stating "based on {n} completed requests" (incident rate, first-time fix) or "{n} dispatched requests" (SLA compliance), and adding "too few to compare reliably" when n is under 20, the existing group rule. An incident count has no denominator, so it states only the count attributed to the technician.
  - A technician filter combined with a breakdown is declined.
- **Repeat-visit drivers.** One tool, `get_repeat_visit_drivers(start, end, by)`, with `by` one of `incident_type`, `service_type`, `region`, `account` or `technician` (the original job's assigned technician). Original jobs are requests completed in the range; a repeat visit is a non-cancelled child, counted whatever its own date (the §6 first-time-fix rule).
  1. Every answer opens with the repeat count and rate, and states that every repeat visit is recorded through a repeat-visit-required incident on the original job.
  2. A group is called out as higher only if it has at least 20 jobs and Fisher's exact test (two-sided) of its jobs against all other jobs gives p < 0.05 after Bonferroni correction across the groups compared (those with at least 20 jobs), and its repeat rate is above the rest's. Otherwise the answer says no group stands out. Figures are always listed worst first.
  3. `by=incident_type` excludes `repeat_visit_required`, which defines a repeat. Each type's jobs are compared with jobs without it. The answer also states the repeat rate on jobs with any other incident against jobs with no incident other than `repeat_visit_required`. That comparison uses rule 2's test as a single comparison, so without Bonferroni: at least 20 jobs on each side and Fisher's exact p < 0.05. If it is significant and the any-other rate is higher, the answer says: "In this period, jobs with another incident needed a repeat visit more often ({x}% vs {y}%); this shows association, not cause." Otherwise: "In this period, jobs with another incident and jobs without didn't differ clearly ({x}% vs {y}%)."
- **Parse prompt `parse_v3`.** Adds the incident-count breakdowns, a technician name (`technician_name`), and the `repeat_visit_drivers` metric with its `by`. `parse_v2` stays in the repo. Date rules are unchanged (ADR-050; L-38 still applies to bare month names).

**Context:**
- L-06 left incident counts without breakdowns, repeat-visit drivers deferred, and no way to ask about one technician. routing_v1 r15 and r17 ask about a single technician by first name.
- 32 technicians; no two share a full name, but six first names are shared by two people, so a first-name question can be ambiguous.
- 1,103 of 2,067 incidents have no attributed technician (dispatch errors and site issues), so a technician breakdown of incident counts needs an explicit "unattributed" group, or about half the incidents would vanish from it.
- The repeat-visit investigation (2026-10-02, as `app_eval`) found that every repeat visit's original job has a `repeat_visit_required` incident and every such incident produced a child, so the literal question "which incident types drive repeat visits" has one answer by construction. In the generator, `repeat_visit_required` depends only on whether the job missed its SLA (which depends on priority) and on how many incidents the job drew, with timing exclusions near the window end; it doesn't depend on service type, region, account, technician or any other incident type. No type or group is therefore expected to stand out, and the observed spreads (service type 1.8–2.3% over the full window; 2026 Q2 rests on 22 repeats) are what chance produces. The significance rule keeps the answers from reporting that noise as drivers; the incident-type comparison does show every other type elevated (about 5–7% against 2%), because jobs with several incidents are more likely to include a repeat-visit-required one, which is why that answer states the association, as association, when its own test finds it. Over a short range the comparison can go the other way: for 2026-07-01 to 2026-08-30, jobs with another incident repeated at 1.12% (1 of 89) against 1.21% (10 of 827), so a fixed sentence asserting the association would contradict the figures beside it.
- Fisher's exact test runs in plain Python in `mcp_incidents`, which doesn't depend on scipy; a unit test checks it against scipy.

**Alternatives considered:**
- *Repeat drivers as co-occurring types only, or as attributes only* (rejected). Questions ask both "which types" and "where"; one tool with `by` serves both without two near-copies.
- *Ranking groups by raw rate with no significance rule* (rejected). At these counts it names a "driver" every time, from noise.
- *Substring or pattern matching for technician names* (rejected). Patterns invite enumeration and injection; whole-word matching finds first and last names, which is how people ask.
- *A clarification dialogue for ambiguous names* (rejected). Out of scope under ADR-031; listing the matches and ending the turn gives the user what they need.
- *Dropping unattributed incidents from the technician breakdown* (rejected). It would hide half the incidents.

**Consequences:**
- Most repeat-driver answers will say no group stands out. That is the honest finding in this data.
- The incident-type breakdown of repeat drivers will flag every common type over long ranges, and the any-other comparison will usually be significant there; the answer then states it is association, not cause. Over short ranges it usually says the two didn't differ clearly.
- QA (Sprint 4) recomputes the counts, rates and Fisher p-values from its own SQL.
- Technician-name questions that name nobody in the data ("Dave", "Sarah") get "No technician matches", with no guessed person.

### ADR-074 — Golden set v1: blind, independently computed expected answers
*Date: 2026-10-02. Supports the Sprint 5 evaluation and `05`. Supersedes nothing.*

**Decision:**
- `evals/golden/golden_v1.jsonl` holds 36 questions: 10 written by the owner in dispatch phrasing (verbatim) and 26 drafted to cover each agent's main paths, every decline type, splits, clarify and no-match replies, and known weak spots. Each records acceptable routes, the expected behaviour, the resolved intent, what the answer must and must not do, and a stretch flag.
- Expected figures are computed by oracles that do not share code with the system: fresh SQL as `app_eval` (reporting, and sentiment over stored predictions), and scipy/statsmodels for statistical tests. Exception: forecast expectations use `packages/forecast_runtime` with the `volume_v2` manifest, because the golden set tests that the agent presents the model's served numbers and errors correctly; model accuracy is judged by the holdout (ADR-069 to ADR-071).
- The golden set is blind: built without calling the system, and first run in the Sprint 5 evaluation. Prompt tuning uses the routing and parse sets only. If the golden set is ever used to revise a prompt, it becomes v2 and that use is disclosed.
- Stretch items record behaviour a correct system should show but the current design may not (unsupported qualifiers such as a city, a cause, or a product line). Their failures are reported as known limitations, not hidden.

**Context:**
- Sentiment expectations check answers against stored predictions, not gold labels: model quality is measured separately (ADR-064 to ADR-066).
- Owner phrasing tests realistic input; the drafted items guarantee coverage.

**Alternatives considered:**
- *Expected answers taken from the system's own output* (rejected). It would test the system against itself.
- *Running the golden set now to check it* (rejected). That would end its blindness before the evaluation it exists for.
- *An LLM-written question set* (rejected for the owner subset). Realistic phrasing has to come from someone who has asked these questions.

**Consequences:**
- Sprint 5 defines how `must_not` criteria are scored (owner review or a rubric).
- A later data or model change means re-running `build_expected.py` and recording the new hashes.

### ADR-075 — Ambiguous questions are not force-routed: the router returns `ambiguous`, and the orchestrator asks the user to rephrase (FR-03)
*Date: 2026-10-03. Supersedes nothing. Corrects a gap between the routing prompt and FR-03, which no ADR decided. Found while updating the `04` reference copy.*
*Status: Accepted; not in effect. Gate failed (see Results); route_v3 remains the default. FR-03 open (L-58).*

**Decision:**
- **Definition, written into the prompt.** A question is *ambiguous* when it could reasonably mean different measurable things to different specialists, so the answers would differ in kind. Examples: "How's the Southeast doing?" names no measure; "Are complaints going up?" could mean incident counts (reporting), negative feedback share (sentiment) or a projection (forecast).
- **What is not ambiguous.** A question that clearly fits one domain but leaves out a detail, such as the period, region or bucket, is *underspecified*, not ambiguous. It is routed, and the specialist applies its stated defaults (ADR-050, ADR-068, ADR-072).
  - Multi-domain (ADR-032) asks for two things.
  - Ambiguous asks for one thing, but which thing is unclear.
- **Router output.**
  - `route_v4` = `route_v3` plus the definition and a new route value `ambiguous`, with `candidates`: the two or three domains the question could mean.
  - `RouteDecision.candidates` only ever holds values from {reporting, sentiment, forecast}: invalid or repeated entries are dropped during validation, each drop logged with the trace ID, rather than failing the whole routing call. With fewer than two valid candidates, the message lists all three domains.
  - `route_v3` stays in the repo.
  - The removed `route_v3` sentence: "If the question is unclear but fits one domain best, choose that domain."
- **Orchestrator behaviour.**
  - `ambiguous` maps to outcome `needs_clarification`, reason `intent_ambiguous`.
  - The answer is template text: the question could mean several things; for each candidate, what that agent answers, plus one example rephrasing.
  - No specialist call and no QA.
  - The turn ends and no state is kept, so this is single-shot (ADR-031), the same pattern as `technician_ambiguous` (ADR-073).
- **`reason` on the response.** `AskResponse` gains `reason`: `technician_not_found`, `technician_ambiguous` or `intent_ambiguous` for `needs_clarification`, and null for every other outcome. Until now the technician codes were logged but never returned.
- **No confidence threshold.** The router reports no self-assessed confidence score. That alternative is rejected because LLM self-reported confidence is not calibrated.

**Evaluation (pre-registered, recorded before any `route_v4` run):**
- Sets: `seed_v2` (31) and `routing_v2` (18), relabelled under this definition and committed before any run. 5 items are ambiguous (s15, s16, s20, s29, r02); 44 are not.
- Runs: `route_v4` k=3 on both sets, Flash-Lite, free key, thinking `minimal`, as-of 2026-08-30; `route_v3` once on the same sets for comparison.
- Gate:
  - (a) Across all `route_v4` runs, at most 1 non-ambiguous item-run (clear, underspecified, out-of-scope, multi-domain, near-miss, technician) is routed `ambiguous`.
  - (b) Non-ambiguous accuracy in every `route_v4` run is no lower than the `route_v3` run on the same items, minus 1.
  - (c) At least two-thirds of ambiguous items (4 of 5) return `ambiguous` in at least 2 of 3 runs.
- Budget: at most 2 prompt revisions after the first `route_v4` run and at most 350 live calls in total; every run saved to `evals/results/`, failed iterations included. If the gate still fails after 2 revisions, `route_v3` is restored as the default, the code and labels stay, and the gate is not loosened. A daily-quota 429 stops the evaluation.
- Results (observed, 2026-10-03; 343 of the 350 calls, no errors, no 429):

  | Run | Prompt | Non-ambiguous correct (of 44) | Non-ambiguous routed `ambiguous` | Ambiguous returned `ambiguous` (of 5) |
  |---|---|---|---|---|
  | comparison | `route_v3` | 43 | 0 | 0 |
  | 1 | `route_v4` | 43 | 1 (r05) | 5 |
  | 2 | `route_v4` | 44 | 0 | 5 |
  | 3 | `route_v4` | 43 | 1 (r05) | 5 |
  | 1 | `route_v5` (revision 1) | 44 | 0 | 5 |
  | 2 | `route_v5` | 41 | 0 | 4 (s20 routed forecast) |
  | 3 | `route_v5` | 43 | 0 | 5 |

  - `route_v4`: (a) FAIL, r05 "Did customer satisfaction dip after the software rollout?" (labelled sentiment) routed `ambiguous` in 2 of 3 runs; (b) PASS; (c) PASS, 5 of 5 in 3 of 3 runs.
  - Revision 1, `route_v5` = `route_v4` plus one rule: words for how customers feel point to sentiment, not star ratings, and are not ambiguous on that account. It targets r05, which is disclosed. (a) PASS, no flags; (c) PASS, 5 of 5 in at least 2 of 3 runs; (b) FAIL, run 2 scored 41 against a floor of 42 (r06 to forecast, near-misses r10 to reporting and r11 to sentiment; `route_v3` also routes r11 to sentiment).
  - **Verdict: the gate failed.** A second revision would need 147 more calls against 7 left in the budget, so the stop rule applies: `route_v3` is the default again, the gate is not loosened, and the code, prompts (`route_v4`, `route_v5`) and labels stay. FR-03 is not yet met in the running system (L-58).
  - Per-item results for every run are in `evals/results/routing_{seed,routing}_v2_gemini-3.5-flash-lite_route_v{3,4,5}_20261003T*.json`. In the three `route_v4` files, each row's `candidates` field holds the model's predicted candidates, not the label's (a runner field collision, fixed before the `route_v5` runs as `predicted_candidates`); the gate scores routes only, and the labels are in the jsonl sets.

**Context:**
- FR-03 is an MVP "Yes" in the submitted Requirements Analysis.
- `route_v3` best-fit routed unclear questions, and the golden set accepted either route for "How's the Southeast doing?". Both contradict FR-03's stated reason (not answering a question the user didn't ask).

**Alternatives considered:**
- *Keep best-fit routing and reinterpret FR-03* (rejected). It reinterprets a frozen requirement to match the code, and makes the ambiguous eval category impossible to fail.
- *A confidence threshold* (rejected, above).
- *Clarifying underspecified questions too* (rejected). Defaults already exist and are stated in the answer; bouncing every undated question harms usability.
- *Rejecting a decision with an invalid candidate* (rejected). It would fail the whole routing call, which is worse than asking with all three domains listed.

**Consequences:**
- The main risk is over-flagging clear questions as ambiguous. The gate measures this.
- Labels for ambiguous items are owner judgment (L-57).
- Golden set v1's G01 and G16 expected error codes that the API never returned, and G35 accepted either route. `golden_v2` fixes both: G35 expects `needs_clarification` + `intent_ambiguous`, and G01/G16 are scored on `reason`.
- `05` gains an ambiguous-question scenario.
- `02` needs no correction.

### ADR-076 — Corrected FR-03 routing gate (supersedes ADR-075's gate only)
*Date: 2026-10-04. Supersedes ADR-075, §Gate only. ADR-075's decision and its recorded results stand.*

**The flaw, disclosed:**
- ADR-075's criterion (b) compared each candidate run with a single `route_v3` run, contrary to ADR-054, which requires every routing eval to report k=3 runs.
- With known run-to-run variance of 1–2 items, a single baseline run with a 1-item tolerance can fail on noise.
- The flaw was identified after the results were seen. The original verdict (fail) is preserved.

**Why confirmation needs fresh data:** `route_v5` was revised against r05 in the v2 sets, so the v2 sets cannot confirm it. `fr03_fresh_v1` (15 items, owner-written on 2026-10-03 without viewing the v2 sets or any route prompt, committed before any run) is the confirmation set.

**Corrected gate:** `route_v5` frozen, k=3 for each prompt, Flash-Lite, free key, thinking `minimal`, as-of 2026-08-30.
- (a) On the fresh set, at most 1 non-ambiguous item is routed `ambiguous` across all 3 `route_v5` runs.
- (b1) On the v2 sets, `route_v5`'s mean non-ambiguous correct count is at least `route_v3`'s 3-run mean minus 1. The 3 `route_v3` runs are the existing comparison run plus 2 new runs; the `route_v5` runs are the 3 already recorded under ADR-075.
- (b2) The same rule holds on the fresh set's 10 non-ambiguous items (3 `route_v3` runs and 3 `route_v5` runs).
- (c) On the fresh set, at least 4 of 5 ambiguous items return `ambiguous` in at least 2 of 3 runs.

**No revisions.** If any criterion fails, `route_v3` stays the default, FR-03 stays open (L-58), and there are no further attempts before Sprint 5.

**If the gate passes:** ADR-075 takes effect with `route_v5` as the default, and L-58 is closed with a reference to this ADR.

**Results** (observed, 2026-10-04; 188 calls, 196 requests with retries, of a 200 budget; no daily-quota 429; one `LLMUnavailable` on `route_v3` run 3, f15, scored as wrong):

| Criterion | `route_v3` (3 runs) | `route_v5` (3 runs) | Rule | Verdict |
|---|---|---|---|---|
| (a) fresh non-ambiguous routed `ambiguous` | — | 0 item-runs | at most 1 | PASS |
| (b1) v2 non-ambiguous correct, of 44 | 43, 43, 43 (mean 43.00) | 44, 41, 43 (mean 42.67) | `route_v5` mean ≥ 42.00 | PASS |
| (b2) fresh non-ambiguous correct, of 10 | 10, 10, 9 (mean 9.67) | 10, 10, 10 (mean 10.00) | `route_v5` mean ≥ 8.67 | PASS |
| (c) fresh ambiguous items `ambiguous` in ≥2 of 3 runs | — | 3 of 5 | at least 4 of 5 | FAIL |

- **Verdict: the gate failed on (c).** f01, f02 and f04 returned `ambiguous` in 3 of 3 runs. f03 ("Are we on track going into Q4?", candidates forecast and reporting) was routed to forecast in all three runs, and f05 ("Where are we losing customer goodwill?", candidates sentiment and reporting) to sentiment in all three. On the v2 sets `route_v5` recognised all 5 ambiguous items; on fresh questions it missed two of five, both times choosing one plausible reading, which is the best-fit behaviour FR-03 rules out.
- Per this ADR, there are no revisions: `route_v3` stays the default, FR-03 stays open (L-58), and there are no further attempts before Sprint 5. ADR-075 remains not in effect.
- The route_v3 v2 runs are the ADR-075 comparison run (20261003T175314Z / T175445Z) plus two new runs; the route_v5 v2 runs are the three recorded under ADR-075. Per-item results for every run are in `evals/results/routing_{seed_v2,routing_v2,fr03_fresh_v1}_gemini-3.5-flash-lite_route_v{3,5}_*.json`; expected candidates are intact in every new file (the `predicted_candidates` fix holds).
