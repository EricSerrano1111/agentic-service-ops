# **Agentic Service Operations Intelligence Platform**

## **Project Design and Solution Architecture**

**Document Information**
Author(s): Eric Serrano 
Keywords: Agentic, AI, Multi-Agent, Field Service, Operations, Business Intelligence, Multi Context Protocol (MCP), Agent to Agent (A2A), Capstone

Due Date: October 18 **(Assignment incomplete)**


**Contents**

[**Agentic Service Operations Intelligence Platform** 1](#_Toc241675387)

[**Project Design & Solution Architecture** 1](#_Toc241675388)

[**Introduction** 3](#_Toc241675389)

[**Purpose** 4](#_Toc241675390)

[**Scope** 4](#_Toc241675391)

[**Acronyms & Abbreviations - Primary: Table 1** 5](#_Toc241675392)

[**Acronyms & Abbreviations – Database & Data-Types: Table 2** 8](#_Toc241675393)

[**Acronyms & Abbreviations – Project & Domain Terms: Table 3** 9](#_Toc241675394)

[**Solution Assumptions** 12](#_Toc241675395)

[**Software & Technology** 15](#_Toc241675396)

[**Solution Blueprint(s)** 16](#_Toc241675397)

[**ER Diagrams or Equivalent** 20](#_Toc241675398)

[**Appendices: Security & Data Access Summary** 26](#_Toc241675399)

## **Introduction**

The Agentic Service Operations Intelligence Platform is a multi-agent AI system that lets an operations leader ask questions about incident and quality metrics, customer sentiment, and future service volume in plain English and receive a verified answer, without writing SQL or waiting on an analyst. It is built over a synthetic dispatch database representing Meridian Field Services, a fictional field service organization with 36 months of history (roughly 15,000 to 25,000 service requests).

A question enters through a web interface and a FastAPI gateway. An orchestrator classifies the intent and routes it over the Agent-to-Agent (A2A) protocol to one of three specialist agents: reporting, sentiment, or forecast. Each specialist reaches data only through its own Model Context Protocol (MCP) server, which exposes narrow, purpose-built tools and connects with its own least-privilege PostgreSQL role. Before any result reaches the user, a QA agent verifies it with a strategy matched to the task: for reporting it recomputes the figures with its own SQL, for forecasts it verifies the input history and arithmetic and checks the model's stored back test error against a threshold, for sentiment it cross-checks labels against star ratings and re-applies the confidence threshold. One language-model call also checks that the question was interpreted correctly. After that, the user receives a degraded result with an explicit warning and a human escalation flag, never unverified output presented as verified.

The platform is built by one developer in six two-week Agile sprints (September 14 to December 5, 2026), written in Python, and deployed as containerized services on Google Cloud Platform.

### **Purpose**

This document is the design of record for the platform. It describes what is being built, how the components connect, how data and control flow from user question to verified answer, and how the work is planned and sequenced.

It has three audiences:

- **Course Reviewers:** to evaluate the design decisions and the project plan.
- **The Developer:** as the build reference against which each sprint's increment is checked.
- **The Test & Support Deliverables:** the test scenarios and production-support documents trace back to the components and interfaces defined here.

### **Scope**

In scope: the end-to-end solution architecture (the backend services, the web front end, and the shared libraries), the technology stack, the agent and protocol design, the security model (scoped MCP tools, per-agent database roles, secrets handling), the data model and the algorithms behind the forecast, sentiment, and QA components, and the deployment topology on GCP.

Out of scope:

- Test scenarios and production support, which are separate deliverables.
- A research or web-scraping agent, which was considered and cut.
- Multi-turn conversation.
- User accounts and per-user permissions.
- Write access to any data.
- Integration with a live operational data source.

### **Acronyms & Abbreviations - Primary: Table 1**

| **Acronym**  | **Expansion**                                           | **Meaning**                                                                                                                                                                               |
| ------------ | ------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A2A          | Agent-to-Agent (protocol, v1.0)                         | Open protocol for communication between autonomous agents. The orchestrator uses it to delegate to the specialist agents, using only Agent Card discovery and blocking SendMessage calls. |
| ADR          | Architecture Decision Record                            | A numbered, dated entry in decisions-log.md recording a design decision, its rationale, and the alternatives rejected. Cited here as ADR-0NN.                                             |
| AI           | Artificial Intelligence                                 |                                                                                                                                                                                           |
| API          | Application Programming Interface                       |                                                                                                                                                                                           |
| BERT         | Bidirectional Encoder Representations from Transformers | Pretrained transformer language model, fine-tuned on sentiment_labels to classify feedback sentiment.                                                                                     |
| BFF          | Backend for Frontend                                    | The FastAPI api_gateway service, which shapes backend responses for the web UI.                                                                                                           |
| BI           | Business Intelligence                                   | Reporting and analysis of operational data to support management decisions.                                                                                                               |
| CD           | Continuous Deployment                                   | Automated build-and-deploy pipeline (Cloud Build trigger - deploy step) that promotes a new revision without manual steps.                                                                |
| CI           | Continuous Integration                                  | GitHub Actions pipeline that runs lint, offline unit tests, and integration tests on every push.                                                                                          |
| DB           | Database                                                |                                                                                                                                                                                           |
| DDL          | Data Definition Language                                | SQL statements that create or alter schema objects. Here, generated and versioned through Alembic migrations.                                                                             |
| E2E          | End-to-End                                              | A test that exercises the full path from question to response.                                                                                                                            |
| ER / ERD     | Entity-Relationship (Diagram)                           | Diagram of tables and the relationships between them.                                                                                                                                     |
| F1           | F1 score                                                | Harmonic mean of precision and recall. Used to score the sentiment classifier.                                                                                                            |
| FK           | Foreign Key                                             | Column referencing the primary key of another table.                                                                                                                                      |
| FR           | Functional Requirement                                  | Numbered requirement defined in the Requirements Analysis.                                                                                                                                |
| GCP          | Google Cloud Platform                                   | Deployment platform: Cloud Run, Cloud SQL, Secret Manager, Artifact Registry, Cloud Build.                                                                                                |
| HTTP         | Hypertext Transfer Protocol                             | See Streamable HTTP (Table 3).                                                                                                                                                            |
| IAM          | Identity and Access Management                          | GCP service controlling which identities may call which resources.                                                                                                                        |
| ID           | Identifier                                              |                                                                                                                                                                                           |
| JSON / JSONB | JavaScript Object Notation / binary JSON                | Text data-interchange format. JSONB is PostgreSQL's binary column type for JSON, which can be indexed and queried.                                                                        |
| KPI          | Key Performance Indicator                               |                                                                                                                                                                                           |
| LLM          | Large Language Model                                    | Runtime model behind the agents that need one (Gemini Flash-Lite) routing, question interpretation, and QA's interpretation check. It never produces a reported figure.                   |
| MAPE         | Mean Absolute Percentage Error                          | Forecast error as an average percentage of the actual value.                                                                                                                              |
| MCP          | Model Context Protocol (spec 2026-07-28)                | Protocol by which an agent calls tools. Each specialist agent connects to its own MCP server.                                                                                             |
| ML           | Machine Learning                                        |                                                                                                                                                                                           |
| MVP          | Minimum Viable Product                                  | In the Requirements Analysis, "Yes" marks a requirement that is a committed deliverable. "No" marks an optional addition.                                                                 |
| ORM          | Object-Relational Mapper                                | SQLAlchemy 2.0, which maps Python classes to database tables.                                                                                                                             |
| PII          | Personally Identifiable Information                     | Customer personal data, held in contacts. No agent role has a grant on it, so PII never enters an LLM context.                                                                            |
| PK           | Primary Key                                             | Column uniquely identifying a row.                                                                                                                                                        |
| QA           | Quality Assurance                                       | Figures are checked by deterministic code; one language-model call checks that the question was interpreted correctly.                                                                    |
| RMSE         | Root Mean Squared Error                                 | Forecast error in the units of the series (requests per week), penalising large misses.                                                                                                   |
| SDK          | Software Development Kit                                |                                                                                                                                                                                           |
| SHA-256      | Secure Hash Algorithm, 256-bit                          | Fingerprint of the frozen feedback corpus, stored so that seed plus corpus reproduce the dataset.                                                                                         |
| SLA          | Service Level Agreement                                 | The target response/resolution window for a request, set by contract tier and priority and snapshotted onto the request (sla_window_minutes).                                             |
| SQL          | Structured Query Language                               |                                                                                                                                                                                           |
| UI           | User Interface                                          |                                                                                                                                                                                           |
| UTC          | Coordinated Universal Time                              | All timestamps are stored in UTC. Date filters use inclusive UTC days.                                                                                                                    |

### **Acronyms & Abbreviations – Database & Data-Types: Table 2**

| **Term**              | **Meaning**                                                                                                                                                                    |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| BIGINT                | 64-bit integer. Used for all surrogate keys, declared GENERATED ALWAYS AS IDENTITY.                                                                                            |
| INT / SMALLINT        | 32-bit and 16-bit integers.                                                                                                                                                    |
| VARCHAR(n)            | Variable-length text of at most n characters.                                                                                                                                  |
| TEXT                  | Unbounded text, such as feedback_text and incident_notes.                                                                                                                      |
| DECIMAL(p,s)          | Exact fixed-point number. DECIMAL(10,2) for money and DECIMAL(5,4) for stored rates. Never FLOAT, so rounding is reproducible.                                                 |
| TIMESTAMPTZ           | Timestamp with time zone, stored as UTC. Naive TIMESTAMP is never used.                                                                                                        |
| CHECK constraint      | Database rule restricting a column to allowed values.                                                                                                                          |
| ENUM                  | Shorthand in the data dictionary for a VARCHAR column plus a CHECK constraint. It is not a native PostgreSQL ENUM type, so adding a value needs no migration of a custom type. |
| Controlled vocabulary | The fixed set of allowed values for a coded column (for example priority_tier: standard, urgent, critical).                                                                    |
| Surrogate key         | System-generated integer key with no business meaning. The human-facing identifier is reservation_number.                                                                      |
| Grant / database role | A PostgreSQL permission on a table, given to a role. Each agent has its own least-privilege role, so access limits are enforced by the database.                               |
| Snapshotting          | Copying a value onto a record at creation instead of joining to it later (for example sla_window_minutes), so historical reports never change when reference data does.        |

### **Acronyms & Abbreviations – Project & Domain Terms: Table 3**

| **Term**                                       | **Meaning**                                                                                                                                                                                                                            |
| ---------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Agent                                          | An independently deployed service with its own A2A endpoint and Agent Card. The system has five: orchestrator, reporting, sentiment, forecast, and QA.                                                                                 |
| Agent Card                                     | Metadata document an A2A agent publishes to advertise its identity, endpoint, and skills. The orchestrator routes on these skills and never sees the agent's tool schemas.                                                             |
| Agentic                                        | Describes a system in which software components interpret goals, choose actions, and delegate to other components rather than following a fixed script.                                                                                |
| Ambiguous / multi-domain / out-of-scope intent | The three non-clean routing cases. An ambiguous intent is not force-routed. A multi-domain question returns an instruction to ask each part separately. An out-of-scope question is declined.                                          |
| Archived request                               | A completed request with final billing (archived_requests). Cancelled requests are never archived.                                                                                                                                     |
| Backtest                                       | Fitting a forecast on earlier weeks and scoring it against later, withheld weeks.                                                                                                                                                      |
| Circuit breaking                               | Stopping calls to a failing service for a period, so failures do not cascade.                                                                                                                                                          |
| Cold start                                     | The delay when a scaled-to-zero service receives its first request.                                                                                                                                                                    |
| Confidence score                               | The classifier's softmax probability for its predicted sentiment class. Low scores are flagged for human review.                                                                                                                       |
| Contract tier                                  | Account level (standard, priority, enterprise) that determines the default SLA window.                                                                                                                                                 |
| Defense in depth                               | Layering independent controls (scoped MCP tools and per-agent database roles) so no single control is load-bearing.                                                                                                                    |
| Degraded result                                | The response returned after final QA failure or the 120-second ceiling: best available output, an explicit warning, and an escalation flag. Never presented as verified.                                                               |
| Dispatch                                       | Assignment of a technician to a request. dispatched_at is the SLA clock start.                                                                                                                                                         |
| Escalation flag                                | Marker telling the user a human should review the result.                                                                                                                                                                              |
| First-time fix rate                            | Share of completed requests with no follow-up (child) request pointing back to them. A cancelled child does not count against its parent.                                                                                              |
| Frozen corpus                                  | The committed, LLM-written feedback text the generator reads. The generator itself never calls an API (ADR-030).                                                                                                                       |
| Generation parameters                          | The known true values (seasonality, trend, coupling, anomalies, seed) used to create the synthetic data, persisted in generation_parameters.                                                                                           |
| Ground-truth tables                            | Used only offline, for generation, training, and evaluation. No agent that answers questions can read them.                                                                                                                            |
| Holdout                                        | Data withheld from training, used to score a model: the last ~26 weeks for the forecast, and the labeled set for sentiment.                                                                                                            |
| Incident                                       | A quality event requiring investigation, recorded with type, severity, and root cause.                                                                                                                                                 |
| Incident rate                                  | Incidents per 100 completed requests in a period. It can exceed 1.                                                                                                                                                                     |
| Intent classification                          | Mapping a user's natural-language question to a route (reporting, sentiment, forecast, or decline).                                                                                                                                    |
| Least privilege                                | Granting each component only the access its job requires.                                                                                                                                                                              |
| MCP server / MCP tool                          | A service exposing narrow, purpose-built functions (for example get_incidents_by_date_range). The system exposes no raw-SQL tool.                                                                                                      |
| Meridian Field Services                        | The fictional field-service organization the synthetic database represents.                                                                                                                                                            |
| Model-agnostic                                 | Agents call models through a single provider interface (packages/llm), so the provider can change without touching orchestration.                                                                                                      |
| Monorepo                                       | One repository holding all services and shared packages, with each service still built and deployed separately.                                                                                                                        |
| Orchestrator                                   | The agent that classifies intent, routes over A2A, and returns the verified response.                                                                                                                                                  |
| Priority tier                                  | Request urgency (standard, urgent, critical), which with contract tier sets the SLA window.                                                                                                                                            |
| Production-grade                               | Meeting the concrete checklist in architecture.md §7. Items not met are explicitly scoped out with a reason.                                                                                                                           |
| Prompt injection                               | Malicious instructions hidden in input text (here, customer feedback) that try to hijack an LLM. Feedback text is treated as untrusted.                                                                                                |
| Readiness / liveness probe                     | Health endpoints telling the platform whether a service is running (liveness) and able to take traffic (readiness).                                                                                                                    |
| Revision cycle                                 | One QA rejection followed by a specialist rework. Capped at two per request.                                                                                                                                                           |
| Scale-to-zero                                  | Cloud Run setting (min-instances = 0) that stops billing when a service is idle.                                                                                                                                                       |
| Seasonal-naive baseline                        | Benchmark forecast that predicts each week as the same week one year earlier.                                                                                                                                                          |
| Sentiment classes                              | Positive, neutral, negative, mixed.                                                                                                                                                                                                    |
| Service request                                | A field-service engagement (install, repair, maintenance, inspection, upgrade) in service_requests.                                                                                                                                    |
| SLA compliance (sla_met)                       | True when completed_at falls within dispatched_at plus the SLA window. Null when either timestamp is missing.                                                                                                                          |
| Specialist agent                               | One of the three domain agents: reporting, sentiment, or forecast.                                                                                                                                                                     |
| Sprint / Increment / Retrospective             | A two-week Agile time-box. The demoable result it must produce. The end-of-sprint review of what went well and what to change.                                                                                                         |
| Streamable HTTP                                | The HTTP-based transport used by both A2A and MCP.                                                                                                                                                                                     |
| Synthetic data                                 | Generated records with no link to any real employer or client data.                                                                                                                                                                    |
| Trace ID                                       | Identifier carried across every hop (gateway → orchestrator → agent → MCP) so one request can be followed in the structured logs.                                                                                                      |
| Univariate                                     | A model whose only input is the series' own history (date in, volume out).                                                                                                                                                             |
| Verification strategy                          | Reporting: recompute with its own SQL. Forecast: verify the input history and arithmetic, and check the stored back test error against a threshold. Sentiment: cross-check against star ratings and re-apply the confidence threshold. |

### **Solution Assumptions**

| **ID**    | **Area**       | **Assumption**                                                                                                                                                                                                                                                                          | **If it proves false**                                                                                                       |
| --------- | -------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| **TA-01** | Data           | The dataset is static and synthetic: 36 months ending 2026-08-30, about 15,000–25,000 service requests and about 7,200 feedback responses. It is generated once from a saved seed and a frozen feedback corpus, so it is exactly reproducible.                                          | Re-generate. Earlier results stop being comparable, and the reporting as-of date moves.                                      |
| **TA-02** | Data           | All agents and MCP servers are read-only. Only the offline generator writes, and it does so as its own database role.                                                                                                                                                                   | A write path would need new grants, new QA rules, and a revised security model.                                              |
| **TA-03** | Data / ML      | The forecast signal is recoverable. The series is weekly and univariate, with about 156 points (about 130 train, 26 held out). It carries Q4 seasonality (±25%), about +8%/yr trend, and three injected anomalies, and a lean regression is enough to model it.                         | The model may fail to beat the seasonal-naive baseline. That is reported honestly under FR-08.                               |
| **TA-04** | Data / ML      | Sentiment labels are defined by the written specification (mix 50/22/20/8, about 15% hard cases). Plain comments are judge-confirmed, and the synthetic text is realistic enough to train and evaluate BERT.                                                                            | Accuracy figures overstate real-world performance. This is recorded in the limitations log, not hidden.                      |
| **TA-05** | ML             | Both trained models are built offline on CPU-class hardware and are never trained by an agent at request time. The BERT service can classify a feedback batch on a CPU Cloud Run instance within its time budget.                                                                       | Inference moves to a larger instance (cost), or batch size is capped.                                                        |
| **TA-06** | Metrics        | The metric definitions in data dictionary §6 (SLA clock start, sla_met, incident rate, first-time fix rate, invoice rounding half-up to 2 decimals) are the single canonical specification. The reporting tools and the QA re-check both implement exactly these.                       | The agent and QA disagree on rounding or definitions, producing false QA failures.                                           |
| **TA-07** | Metrics        | Relative dates ("last month") resolve against the fixed as-of date REPORTING_AS_OF_DATE (default 2026-08-30), never the wall clock.                                                                                                                                                     | Answers drift outside the data window and stop being reproducible.                                                           |
| **TA-08** | Interaction    | Interaction is single-shot and one domain per question, with no sessions or conversation state. A2A is used as a minimal subset (Agent Card discovery and blocking SendMessage), with an in-memory task store.                                                                          | Multi-turn support needs orchestrator session state, and input-required and streaming come into play. A new ADR is required. |
| **TA-09** | LLM            | The Gemini free tier stays available at the limits verified in AI Studio on 2026-09-22. Flash-Lite: 15 requests/min, 250K tokens/min, 500 requests/day. Other Flash models: 5 requests/min, 20 requests/day.                                                                            | Switch providers through the packages/llm interface, or move to the paid spend-capped project.                               |
| **TA-10** | LLM            | Flash-Lite at minimal thinking is sufficient for every LLM role (routing, question parsing, QA). A role moves to a larger model only on measured evidence.                                                                                                                              | The Sprint 3 routing set reopens the decision via a new ADR.                                                                 |
| **TA-11** | LLM            | Per-minute rate limits are absorbed by bounded waits. A daily-quota 429 is treated as a hard failure. Evaluation runs that exceed 500 requests/day are split across days or run on the paid project (\$5 prepaid cap, auto-reload off).                                                 | Evaluation schedule slips, or paid spend rises toward the buffer.                                                            |
| **TA-12** | Latency        | Provider latency dominates request time, and occasional 503s occur. A 120-second ceiling is enough for a cold start plus up to two revision cycles. No response-time target is committed.                                                                                               | Legitimate requests return degraded results. Raising the ceiling needs a new ADR.                                            |
| **TA-13** | Protocols      | The pinned SDKs behave to spec: mcp2.2.0 (MCP 2026-07-28) and a2a-sdk1.1.5 (A2A v1.0). Every other dependency is locked by uv.lock. Upgrades need an ADR. A2A data parts carry numbers as doubles, so each is validated against a shared Pydantic schema, and money travels as strings. | Ecosystem churn breaks a hop. The hand-rolled fallback is a minimal Agent Card plus one RPC.                                 |
| **TA-14** | Infrastructure | The GCP account, existing credits, free tiers and a personal budget of about \$100 cover hosting, database and model spend. Budget alerts are set at \$50 and \$80.                                                                                                                     | Scale back deployment scope (stop Cloud SQL when idle, cut services) before touching verification.                           |
| **TA-15** | Infrastructure | Cloud SQL (PostgreSQL) supports the per-agent role and grant model. Local Docker Postgres 16 is a faithful stand-in until the Sprint 4 deploy, even though Cloud SQL provides cloudsqlsuperuser, not SUPERUSER.                                                                         | Migrations or grants need rework, discovered at the Sprint 4 deploy.                                                         |
| **TA-16** | Infrastructure | A Cloud Build success results in a serving revision. A post-deploy check confirms the new revision holds 100% of traffic, and Cloud Run's 300-second request timeout is not lowered below the 120-second ceiling.                                                                       | Stop rule: if not verified by 2026-11-04, record R-03 as realised and continue.                                              |
| **TA-17** | Infrastructure | Services scale to zero, and cold starts are accepted and warmed before demos.                                                                                                                                                                                                           | Latency at demo time rises. Mitigated by warm-up, or by min-instances at a cost.                                             |
| **TA-18** | Security       | Only the gateway is internet-reachable. Every internal hop is authenticated (IAM ID tokens), and requests without valid credentials are rejected before any model call. The user-facing access mechanism is chosen in Sprint 5.                                                         | Exposed model quota and an unauthenticated data path.                                                                        |
| **TA-19** | Capacity       | Usage is a handful of concurrent users (developer, instructor, demo audience), so no horizontal scaling, caching layer or load balancing beyond Cloud Run defaults is designed. Sprint 6 load testing measures latency, not throughput.                                                 | A scale claim would need a real capacity design.                                                                             |
| **TA-20** | Project        | One developer builds the system in six sprints ending 2026-12-05. CI, automated tests and AI-assisted review stand in for peer review. Sprint 6 is protected as genuine buffer.                                                                                                         | Schedule risk rises. Scope is cut from the optional items, never from verification.                                          |

.

## **Software & Technology**

The platform is written in Python 3.12 and runs as a set of containerized services on GCP. The database management system is PostgreSQL 16. It was chosen over lighter options because the security design depends on database-level permissions. Each agent connects with its own least-privilege role, which SQLite cannot provide. Agents hand work to one another over the Agent-to-Agent (A2A) protocol and reach data through Model Context Protocol (MCP) servers, both carried over HTTP. Language-model calls go to Google's Gemini API. The sentiment and forecast results come from models trained offline, not from the language model. A thin Next.js front end sits over a FastAPI gateway. A2A is a deliberate choice for modularity and standards alignment, not a necessity, since at this scale in-process calls would also work.

- **Language & Tooling:** Python 3.12. uv 0.12.19 manages the multi-package workspace and locks every dependency to an exact version, so local, CI, and container builds install identical packages. ruff 0.16.8 lints and formats, and pytest 9.1.1 runs the unit and integration suites. GitHub Actions runs both on every push, with integration tests executed against a PostgreSQL 16 service container.
- **Data Layer:** PostgreSQL 16, run in Docker during development and as Cloud SQL for PostgreSQL once deployed. Access uses SQLAlchemy 2.1.1 with psycopg 3.3.6. Schema changes are versioned with Alembic 1.20, and the same migrations run against both environments. Pydantic 2.13.5 defines the typed contracts passed between services.
- **Agent & Protocol Layer:** The official Python SDKs are pinned exactly: mcp 2.2.0 (MCP specification 2026-07-28) and a2a-sdk 1.1.5 (A2A v1.0), over streamable HTTP. Three MCP servers, one per specialist domain, expose narrow tools and never raw SQL. FastAPI 0.141.1 serves the gateway that the front end calls.
- **AI and ML:** gemini-3.5-flash-lite through google-genai 2.25.0 handles intent routing and question parsing QA's interpretation check on the Gemini API free tier. A separate, spend-capped paid project is reserved for evaluation runs. Sentiment uses a BERT classifier fine-tuned with PyTorch and Hugging Face Transformers, which supplies the confidence score. Forecasting uses a regression built with scikit-learn and statsmodels. Both models are trained offline and never at request time.
- **Interface:** Next.js 16.3 (patch version pinned at build time; 16.3.7 or later) with React 19.3, on Node.js LTS.
- **Platform & delivery:** Docker and Docker Compose run the full stack locally. On GCP, each component deploys as its own Cloud Run service that scales to zero when idle. Credentials live in Secret Manager, images in Artifact Registry, and builds and deployments run through Cloud Build. These managed services are unversioned.

## **Solution Blueprint(s)**

The platform accepts a plain-English question in a web interface and returns a verified answer. A backend of cooperating components does the work: an orchestrator that routes the question, three specialist agents that each answer one kind of question, a QA agent that checks every answer before it is released, and a PostgreSQL database that holds the data.

**Four Cross-Rutting Services Run Beneath**

- Credentials live in Secret Manager, never in code.
- Structured logs carry one trace ID per request across every hop.
- Authentication covers both user access at the gateway and identity between services.
- Every component is containerized and deployed on Google Cloud Platform.

**Two Choices Helped Shape the Design**

- First, data access is constrained twice: specialists reach data only through narrow tools on their own MCP server, and each connects with a database role that can read only what it needs. No agent can read customer contact details, so personal data never enters a language-model prompt.
- Second, verification is independent: QA checks against the database directly instead of reusing the specialist's tools, so a fault in a tool cannot pass its own check. That makes QA the broadest-access component in the system, an accepted trade-off.

_Figure 1 below shows the components and how a request moves through them._

**How a Question Flows**

1. The user types a question into the web UI.
2. The UI sends it to the API gateway over HTTPS, where it is authenticated and validated.
3. The gateway forwards the request to the orchestrator.
4. The orchestrator classifies the intent, using the Gemini language model, and delegates to the matching specialist (reporting, sentiment, or forecast) over the Agent-to-Agent (A2A) protocol. The specialist also uses the language model to turn the question into a structured request.
5. The specialist calls tools on its own Model Context Protocol (MCP) server. Each server exposes only narrow, purpose-built tools, never raw SQL.
6. The tools read the database through a role limited to what that specialist needs, and run the specialist's algorithm: deterministic metric calculations, the sentiment classifier, or the forecast regression.
7. The specialist returns its draft result to the orchestrator.
8. The orchestrator passes the draft to the QA agent, which verifies it independently by running its own SQL against the database under its own read role.
9. If QA passes the draft, the orchestrator returns the verified answer to the UI together with a QA status. If QA rejects it, the orchestrator sends the specialist QA's guidance and repeats steps 4–8, at most twice. If the limit is reached or 120 seconds elapse, the user receives a degraded result with a warning and an escalation flag, never unverified output presented as verified.

| **Component**       | **Layer**    | **Technology**                                  | **Responsibility**                                                                                                                                                                                                                                                                                                                                                          | **Connects to**                      |
| ------------------- | ------------ | ----------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------ |
| Web UI              | Frontend     | Next.js / React                                 | Takes the question; shows the answer, QA status, and any escalation flag. Holds no business logic.                                                                                                                                                                                                                                                                          | API gateway                          |
| API gateway         | Backend      | FastAPI                                         | Single entry point: authenticates, validates, enforces timeouts, relays responses.                                                                                                                                                                                                                                                                                          | Web UI, orchestrator                 |
| Orchestrator        | Backend      | Python, A2A, Gemini                             | Classifies intent and routes it. Declines ambiguous, multi-domain, and out-of-scope questions. Controls the QA loop and the 120-second limit.                                                                                                                                                                                                                               | Gateway, specialists, QA, Gemini     |
| Reporting agent     | Backend      | Python, A2A, Gemini                             | Incident and quality metrics (incident rate, SLA compliance, first-time fix rate) by account, region, service type, or technician.                                                                                                                                                                                                                                          | Orchestrator, incident tools         |
| Sentiment agent     | Backend      | Python, A2A, Gemini                             | Classifies customer feedback as positive, neutral, negative, or mixed, with a confidence score.                                                                                                                                                                                                                                                                             | Orchestrator, feedback tools         |
| Forecast agent      | Backend      | Python, A2A, Gemini                             | Forecasts weekly service-request volume and compares it to a seasonal-naive baseline.                                                                                                                                                                                                                                                                                       | Orchestrator, volume tools           |
| MCP servers (three) | Tool layer   | MCP over HTTP                                   | One per specialist. Narrow tools, each with its own restricted database role.                                                                                                                                                                                                                                                                                               | Specialist, database                 |
| Algorithms          | Analytics    | SQL/Python metrics; fine-tuned BERT; regression | The computation behind each specialist's answer.                                                                                                                                                                                                                                                                                                                            | Used through each specialist's tools |
| QA agent            | Verification | Python, A2A, SQL, Gemini                        | Reporting: recompute the figures with its own SQL and match. Forecast: verify the input history and arithmetic and check the stored back test error against a threshold. Sentiment: cross-check labels against star ratings, check the comment set and counts, and re-apply the confidence threshold. One language-model call checks the question was interpreted correctly | Orchestrator, database, Gemini       |
| PostgreSQL          | Data         | PostgreSQL 16                                   | Synthetic dispatch data, with one restricted role per agent.                                                                                                                                                                                                                                                                                                                | Tools, QA                            |
| Gemini API          | External     | Gemini 3.5 Flash-Lite                           | Language tasks only (routing, question interpretation, QA's interpretation check). Never produces a reported figure.                                                                                                                                                                                                                                                        | Orchestrator, specialists, QA        |

## **ER Diagrams or Equivalent**

**Database Tables (where applicable)**

| **Parent Table** | **Child Table**   | **Linking Column (in child)** | **Relationship**     | **Meaning**                                                          |
| ---------------- | ----------------- | ----------------------------- | -------------------- | -------------------------------------------------------------------- |
| accounts         | contacts          | account_id                    | One to many          | An account has many contacts                                         |
| accounts         | locations         | account_id                    | One to many          | An account has many service sites                                    |
| accounts         | service_requests  | account_id                    | One to many          | An account places many service requests                              |
| locations        | service_requests  | location_id                   | One to many          | Each request is serviced at one site                                 |
| contacts         | service_requests  | contact_id                    | One to many          | Each request has one customer contact                                |
| contacts         | incidents         | reported_by_contact_id        | One to many          | A contact can report many incidents                                  |
| contacts         | service_feedback  | submitted_by_contact_id       | One to many          | A contact can submit many surveys                                    |
| technicians      | technician_skills | technician_id                 | One to many          | A technician has many skills                                         |
| technicians      | service_requests  | assigned_technician_id        | Optional one to many | A request is assigned to one technician once dispatched              |
| technicians      | archived_requests | technician_id                 | One to many          | Each completed job records who performed it                          |
| technicians      | incidents         | attributed_technician_id      | Optional one to many | An incident may be attributed to one technician                      |
| internal_users   | service_requests  | created_by_user_id            | One to many          | Staff log service requests                                           |
| internal_users   | incidents         | created_by_user_id            | One to many          | Staff log incidents                                                  |
| service_requests | service_requests  | parent_request_id             | Optional one to many | A repeat visit links back to the original request                    |
| service_requests | archived_requests | request_id                    | One to zero-or-one   | A completed request gets one billing record; cancelled ones get none |
| service_requests | incidents         | request_id                    | One to many          | A request can have several incidents                                 |
| service_requests | service_feedback  | request_id                    | One to zero-or-one   | A request gets at most one survey response                           |
| incidents        | service_feedback  | incident_id                   | Optional one to many | Feedback may be linked to a complaint                                |
| service_feedback | sentiment_labels  | feedback_id                   | One to one           | Each survey response has one ground-truth sentiment label            |

**Algorithms**

The platform uses two trained models. A linear regression forecasts future service-request volume, and a fine-tuned BERT classifier reads customer feedback. Both are trained offline and loaded for use, never trained while a question is being answered. Reporting figures are computed by deterministic calculations and involve no model. The language model is used only to route and interpret questions, never to produce a reported number.

**Volume Forecast: Linear Regression**

| Purpose    | Forecast weekly service-request volume so operations leaders can plan technician capacity    |
| ---------- | -------------------------------------------------------------------------------------------- |
| Input      | Weekly request counts over the 36-month history (date and count only; no other data)         |
| Method     | Linear regression on the log of weekly volume, with a linear trend and annual seasonal terms |
| Output     | A forecast for each future week, with a prediction range, up to 26 weeks ahead               |
| Baseline   | Seasonal-naive: each week is predicted as the same week one year earlier                     |
| Evaluation | RMSE and MAPE on held-out weeks, compared with the baseline                                  |

**Verification**

The model is back tested: fitted on earlier weeks and scored on later weeks it has not seen. A fixed holdout of the final 26 weeks gives the headline RMSE and MAPE, and rolling forecast origins that include the Q4 peak confirm it handles the busiest season. At answer time the QA agent verifies the input history and the arithmetic and checks the model's stored back test error for the requested slice against a threshold. If the regression does not beat the seasonal-naive baseline, that is reported as a finding.

Because the data is synthetic, these results show how well the model recovers known patterns, not how it would perform on real demand.

**Sentiment: Fine-Tuned BERT Classifier**

| Purpose       | Classify each customer comment as positive, neutral, negative, or mixed, with a confidence score                                   |
| ------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Input         | Comment text only; the star rating is withheld from the model                                                                      |
| Model         | Pretrained BERT-base, fine-tuned for four-class text classification compared with TF-IDF                                           |
| Output        | A label and a confidence (the highest class probability) for each comment                                                          |
| Training data | About 7,500 synthetic comments labeled by written definitions, including about 15% deliberately hard cases (sarcastic or implicit) |
| Evaluation    | Precision, recall, and F1 per class, with hard cases reported separately                                                           |

BERT is a pretrained language model that turns a comment into a numeric representation of its meaning in context. A single classification layer on top converts that representation into four probabilities, one per sentiment, using a softmax. The predicted label is the most probable class, and that probability is the confidence. Fine-tuning adapts the pretrained model to this project's labels. The smallest class, mixed, is about 8% of comments, so the training loss is weighted to keep the model from ignoring it. The comments are split into training, validation, and test sets, stratified by class and hard-case type. Near-duplicate comments are kept on one side of the split so scores are not inflated.

**Confidence & Human Review**

Fine-tuned classifiers tend to be overconfident, so the confidence threshold is calibrated on the validation set: comments below it are flagged for human review, not presented as settled. The sentiment agent summarizes the classified comments as counts and shares by class and period.

**Verification**

Re-running the same classifier would prove nothing, so QA checks it differently.

At answer time it cross-checks labels against star ratings (clear contradictions only), verifies the comment set, counts, and cited comments, and re-applies the calibrated confidence threshold. Scoring against ground-truth labels happens offline, during evaluation, because new comments in real use have none. A trained classifier was chosen over prompting a language model because its probabilities give a usable confidence signal, it costs far less per comment, and text hidden in a comment cannot redirect it as it might a prompted model. The comments and labels are synthetic, so scores measure agreement with the written label definitions, and known limitations are reported alongside them.

**User Interface (UI)**

The platform has one screen. A thin web interface, built with Next.js and React, sits over the API gateway and shows only what the architecture needs: a place to ask a question, the answer, whether it was verified, and whether a person should look at it. The interface is a window into the system and deliberately has no other features. Each exchange is a single question and a single answer, so there is no conversation history and no user accounts or settings.

1. **Ask:** The user sees a question box (A) and an Ask button, with three example questions, one for each kind of question the platform answers (incidents, sentiment, volume).
2. **Working:** After the question is submitted, a progress indicator (B) replaces the answer area. The system waits for the backend, which always responds within 120 seconds, either with an answer or with a failure result.
3. **Verified Answer:** The answer display (C) shows the result as text and simple tables. Reporting answers state the data as-of date. A QA status bar (D) confirms that the independent check passed.
4. **Answer that Failed Verification:** If QA rejects the result after two revisions, or the time limit is reached, the screen shows a warning banner, marks the answer as unverified, and shows an escalation flag (E). The answer is never shown as verified when it was not.
5. **Question Not Answered:** If a question is unclear, outside the three supported topics, or covers more than one topic, the answer area shows a short message asking the user to rephrase or split the question. There is no QA status, because no answer was produced.

**Data Behind the Screen**

The UI sends the question to the gateway and receives one response holding the answer, any supporting figures, the as-of date, the QA status, and any warning and escalation flag. The UI only displays these fields and holds no business logic.

Sign-in is not shown, since access is restricted to authorized users through the gateway.

_Figure 2. Simplified UI mockup. Layout and styling will change; the core components will not._

# **Appendices: Security & Data Access Summary**

The platform protects data in layers, so no single control carries the whole burden.

Agents reach data only through narrow, purpose-built tools, never raw SQL. Each specialist connects only to its own tool server. Each agent also uses its own database role, so the database itself refuses anything outside that agent's job. A fifth role, used only by the offline data generator, is the sole role with write access. Two further read-only roles, for training and evaluation, run only on the developer's machine and are never deployed

The table below shows what each agent can read:

| **Table**             | **Reporting**           | **Sentiment**  | **Forecast**   | **QA** |
| --------------------- | ----------------------- | -------------- | -------------- | ------ |
| accounts              | Read                    | —              | —              | Read   |
| contacts              | —                       | —              | —              | —      |
| locations             | Read                    | —              | —              | Read   |
| technicians           | Read                    | —              | —              | Read   |
| technician_skills     | Read                    | —              | —              | Read   |
| internal_users        | —                       | —              | —              | —      |
| service_requests      | Read                    | —              | 3 columns only | Read   |
| archived_requests     | Read                    | —              | —              | Read   |
| incidents             | Read                    | —              | —              | Read   |
| service_feedback      | All except comment text | 4 columns only | —              | Read   |
| sentiment_labels      | —                       | —              | —              | —      |
| generation_parameters | —                       | —              | —              | —      |

**Design Guarantees**

- **No agent can read customer contact details**,
  - Personal data never enters a language-model prompt.
- **The sentiment agent cannot read the ground-truth labels, the star rating, or internal incident notes.**
  - Verification cannot become circular, the rating stays an independent check, and staff-written notes cannot leak into sentiment results.
- **The forecast agent sees three columns**
  - Nothing else, with no billing data and no customer or technician identifiers.
- **QA is deliberately the broadest reader**
  - This is because independent verification needs sources the specialists cannot see.
  - That makes it the highest-value target in the system, an accepted trade-off, limited by its read-only role.

These permissions are enforced by the database, not by code convention, and an automated test logs in as each role to confirm it can do exactly what the table says. Beyond the database, the design places credentials in Secret Manager, never in code or container images, and exposes only the gateway to the internet. Free-text customer comments are treated as untrusted input, and every tool call will be logged with a trace ID that follows the request across agents.
