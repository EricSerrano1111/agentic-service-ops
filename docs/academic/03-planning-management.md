# **Agentic Service Operations Intelligence Platform**

## **Planning and Management Document**

**Document Information**
Author(s): Eric Serrano 
Keywords: Agentic, AI, Multi-Agent, Field Service, Operations, Business Intelligence, Multi Context Protocol (MCP), Agent to Agent (A2A), Capstone

Due Date: October 18 **(Assignment complete)**

**Document Revision History**

| **Version** | **Date**   | **Author**   | **Changes Made**       |
| ----------- | ---------- | ------------ | ---------------------- |
| 1.0         | 09/25/2026 | Eric Serrano | Initial version        |
| 2.0         | 10/03/2026 | Eric Serrano | Minor language updates |
|             |            |              |                        |
|             |            |              |                        |

**Reviewers**

| **Name**                | **Contact Information** |
| ----------------------- | ----------------------- |
| Professor William Sunna | Canvas                  |
|                         |                         |


## **Executive Summary**

Meridian Field Services dispatches technicians to install, repair, maintain, and upgrade customer network and hardware infrastructure. As service volume grows, so does the operational data it generates: completed jobs, quality incidents, customer feedback, and demand across regions and skill categories. The questions leaders ask of that data (which incident types drive repeat visits, whether sentiment is falling in a region, how much technician capacity next month requires) currently go through an analyst. That path is slow and does not scale, leadership has signaled that it wants to grow analytical capability without growing analyst headcount. The harder requirement is trust as a wrong number that quietly informs a staffing or escalation decision is worse than no number, so answers must be verified before they reach a decision-maker.

The Agentic Service Operations Intelligence Platform lets an operations leader ask a question in plain English and receive a verified answer. An orchestrator classifies the question and routes it to one of three specialist agents (reporting, sentiment, or forecast). Each specialist reaches only the data it needs, through its own narrowly scoped tools. A separate QA agent checks every answer before it is returned. If verification fails, the system retries up to twice, then returns a degraded result with an explicit warning and an escalation flag for a person, never an unchecked answer. The system is built and validated against a synthetic operational dataset, deployed on Google Cloud, and delivered with a web interface that shows each answer beside its verification status. It answers questions only. It does not take action, hold multi-turn conversations, or connect to live systems.

As the sole developer, this project will be delivered in six two-week Agile sprints running from 09-14-2026 to the final submission on 12-05-2026. Live status is tracked in a sprint log. At the baseline, Sprints 1 and 2 are substantially complete: the data foundation, the access controls, and the first end-to-end slice are built, and the proposal and requirements documents are submitted. The remaining work is organized as a work breakdown structure of nine deliverable branches and 29 work packages. The critical path runs through the first cloud deployment, scheduled 2026-11-02 to 11-04 and timeboxed to three days with a stop rule. That deployment feeds the production support document due 2026-11-08, which leaves two days of float.

**Project Overview**

| **Dimension**            | **Details**                                                                                                                                     |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Delivery                 | Agile, six two-week sprints, 09-14-2026 to 12-05-2026                                                                                           |
| Team                     | One developer, at roughly 15–20 hours per week                                                                                                  |
| Status at Baseline       | Sprints 1–2 substantially complete as of 09-29-2026                                                                                             |
| Remaining work           | 29 work packages, about 211 hours including level-of-effort                                                                                     |
| Critical path            | First Cloud Run deployment (11-02 to 11-04) into 06 (due 11-08), two days of float                                                              |
| Budget                   | About \$100 target; about \$1.40 spent to date; about \$40 held as buffer as of 09-29-2026                                                      |
| Success measures         | Response time by question type; routing accuracy with documented failures; QA catch rate on injected errors; compute cost per answered question |
| Governance               | Numbered decision records, sprint reviews and retrospectives, risk register, budget alerts, automated tests, weekly status reports              |
| Business user enablement | Quick-start guide, sample-question catalog, demo script, final presentation                                                                     |

## **Project Information & Analysis**

**Resources & Budget:**

Runtime model calls use the Gemini free tier, with a separate spend-capped paid project for evaluation runs. The managed database is introduced in Sprint 4 rather than at the start, so the project does not pay for months of idle capacity. The largest planned infrastructure cost is the database at roughly \$10–15. The buffer covers overruns, and an optional comparison against a stronger QA model (about \$20–30) would be drawn from it.

**Governance & Enablement:**

Decisions are recorded as numbered records and are never edited after the fact, only superseded. Each sprint boundary includes a review, a retrospective, a risk-register update, and a re-baseline of remaining estimates. Enablement is sized to the audience as a one-page quick-start guide, a catalog of sample questions built from the evaluation sets, guidance on reading verification status and escalation flags, and a demo script.

**Structured Risk Control:**

Each success criterion has a named work package that produces its evidence: routing accuracy, QA fault injection, and latency and cost measurement. Deployment risk is reduced by deploying a small slice in Sprint 4 instead of first deploying at the end. Scope changes pass through a gate at the Sprint 4 boundary. Section 10 traces each criterion to its evidence and risk controls.

**Four Risks Remain - Stated Plainly**

1. **Capacity:** Estimated remaining effort is about 211 hours against roughly 146–194 hours available at the planned pace. This is the plan's principal schedule risk. It is managed by starting Sprint 3 work early, re-baselining at each sprint boundary, and a pre-agreed order for deferring lower-priority work.
2. **Single point of delivery:** No second reviewer exists, so automated tests and evaluation checkpoints substitute for one.
3. **Model rate limits:** Free-tier limits constrain throughput, and the design absorbs them with backoff and a clear "try again later" response.
4. **Synthetic Data:** Results are pilot evidence, not a production guarantee

## **Project Key Deliverables**

The project produces two kinds of deliverable: the working system and the academic documents that describe and support it. Each deliverable is defined by an acceptance criterion in the WBS dictionary, which serves as this plan's deliverables register, and each maps to a work package and a CPM activity. The deliverables below are the ones on which the project's success is judged.

- **Specialist Agents:** The forecast agent, whose model must beat a seasonal-naive baseline on held-out weeks (or document the gap), and the sentiment agent, which returns a four-class label with a confidence score and flags low-confidence results for human review. Each connects only to its own scoped tool server. The reporting agent is already delivered.
- **Orchestrator Routing:** Routes each question to the correct specialist, detects questions that span more than one domain and asks the user to submit each part separately, and declines out-of-scope questions instead of guessing.
- **QA Agent & Loop Control:** Three verification strategies (a reporting re-query, a forecast backtest, and a sentiment holdout check), a revision loop capped at two retries, and a degraded result with a warning and escalation flag on final failure. A 120-second ceiling and a per-request cost cap bound each request.
- **Evaluation evidence:** A set of known-correct answers, a labelled routing set, routing accuracy with failure cases documented, the QA agent's catch rate against deliberately injected errors, and an evaluation report that presents the results and states the system's limitations.
- **Deployed System:** All services running on Google Cloud, with a web interface that shows each answer alongside its QA status and any escalation flag. Only the gateway is reachable from the internet, and unauthenticated requests are rejected before any model is called.
- **Production Hardening:** Observability, complete continuous delivery, graceful degradation tested by stopping each specialist in turn, response time and cost measured for each request type, and an audit of the production-grade checklist.
- **Academic Deliverables:** Planning and Management and Design and Solution Architecture are due 10-18, Test Scenarios 11-01, and Production Support 11-08. Weekly status reports run through 11-22, and the final submission (the presentation plus the completed project) is due 12-05. The proposal and requirements documents are already submitted.
- **Business User Enablement:** A one-page quick-start guide, a catalog of sample questions drawn from the evaluation sets, guidance on reading QA status and escalation flags, a demo script, and the final presentation.

## **Work Breakdown Structure Approach**

The WBS is organized by deliverable, so each branch names something the project produces and each work package can be accepted or rejected against a stated criterion. It follows the 100% rule where every branch below the project level sums to the full scope, including completed work, which is shown with its final status rather than removed. Work packages are sized at three days or less of effort. Level 3 packages map one-to-one to the activities in the CPM network. Weekly reporting and sprint ceremonies are level-of-effort packages with no dependencies. As the single team member, I own every package.

Each package is tagged by basis:

- **Req** (traces to a functional or non-functional requirement or a stated success criterion).
- **Course** (an academic deliverable).
- **Bar** (the self-imposed production-grade standard).
- **Portfolio** (a deliberate demonstration beyond what the requirements need).

## **Work Breakdown Structure Diagram**



## **Work Breakdown Structure Outline**

| **WBS** | **Work package**                                                                                                          | **CPM #** | **Owner**    | **Effort (h)** | **Sprint** | **Basis** |
| ------- | ------------------------------------------------------------------------------------------------------------------------- | --------- | ------------ | -------------- | ---------- | --------- |
| 1       | Project Management & Governance                                                                                           |           |              | 13.5           |            |           |
| 1.1     | Weekly status reports (8 remaining, through 11-22)                                                                        | LOE       | Eric Serrano | 6              | 2–5        | Course    |
| 1.2     | Sprint review, retro, risk-register update, estimate re-baseline (5 boundaries)                                           | LOE       | Eric Serrano | 7.5            | 2–6        | Bar       |
| 1.3     | Decisions log and budget monitoring                                                                                       | LOE       | Eric Serrano | in-package     | all        | Bar       |
| 2       | Data Foundation (schema, ground truth, corpus, generator + validation, repo/CI)                                           |           | Eric Serrano | done           | 1          | Req       |
| 3       | Platform Core (roles and grants, incidents MCP, packages/llm, A2A skeleton, reporting agent, orchestrator classification) | 1         | Eric Serrano | done           | 1–2        | Req       |
| 4       | Specialist Agents                                                                                                         |           |              | 38             |            |           |
| 4.1.1   | MCP servers #2 and #3 (feedback, volume)                                                                                  | 4         | Eric Serrano | 6              | 3          | Req       |
| 4.2.1   | Forecast model + seasonal-naive backtest                                                                                  | 5         | Eric Serrano | 8              | 3          | Req       |
| 4.2.2   | Forecast agent (Agent Card, parsing, A2A)                                                                                 | 6         | Eric Serrano | 5              | 3          | Req       |
| 4.3.1   | Sentiment model fine-tune (BERT, offline)                                                                                 | 7         | Eric Serrano | 8              | 3          | Req       |
| 4.3.2   | Sentiment agent + confidence scoring + eval                                                                               | 8         | Eric Serrano | 8              | 3          | Req       |
| 4.4.1   | Orchestrator routes across all three                                                                                      | 9         | Eric Serrano | 3              | 3          | Req       |
| 5       | QA & Verification                                                                                                         |           |              | 24             |            |           |
| 5.1.1   | QA agent: three verification strategies                                                                                   | 13        | Eric Serrano | 12             | 4          | Req       |
| 5.2.1   | Retry loop (max 2) + escalation + per-request cost cap                                                                    | 14        | Eric Serrano | 6              | 4          | Req       |
| 5.3.1   | Fault-injection harness                                                                                                   | 15        | Eric Serrano | 6              | 4          | Req       |
| 6       | Interface, Deployment & Hardening                                                                                         |           |              | 58             |            |           |
| 6.1.1   | FastAPI gateway + minimal React UI                                                                                        | 21        | Eric Serrano | 13             | 5          | Req       |
| 6.2.1   | Cloud Run slice deploy + Cloud SQL (3-day timebox)                                                                        | 16        | Eric Serrano | 12             | 4          | Bar       |
| 6.2.2   | Slice hardening (Card TTL, trace id, readiness probe)                                                                     | 17        | Eric Serrano | 3              | 4          | Bar       |
| 6.3.1   | Deploy specialists, MCP, QA + full Cloud SQL migration                                                                    | 22        | Eric Serrano | 8              | 5          | Req       |
| 6.3.2   | Deploy gateway + UI; verify revision promotion                                                                            | 23        | Eric Serrano | 4              | 5          | Req       |
| 6.4.1   | Observability + CI/CD completion                                                                                          | 24        | Eric Serrano | 8              | 6          | Bar       |
| 6.4.2   | Graceful degradation                                                                                                      | 25        | Eric Serrano | 4              | 6          | Req       |
| 6.4.3   | Load / latency testing                                                                                                    | 26        | Eric Serrano | 3              | 6          | Req       |
| 6.4.4   | Production-grade checklist audit                                                                                          | 27        | Eric Serrano | 3              | 6          | Bar       |
| 7       | Evaluation                                                                                                                |           |              | 30             |            |           |
| 7.1.1   | Golden set                                                                                                                | 10        | Eric Serrano | 4              | 3          | Req       |
| 7.1.2   | Labelled routing set + model re-run                                                                                       | 11        | Eric Serrano | 5              | 3          | Req       |
| 7.2.1   | Routing eval harness + eval-run pricing + failure analysis                                                                | 19        | Eric Serrano | 9              | 5          | Req       |
| 7.2.2   | QA model comparison (Flash-Lite vs Pro)                                                                                   | 20        | Eric Serrano | 4              | 5          | Portfolio |
| 7.3.1   | Evaluation report                                                                                                         | 28        | Eric Serrano | 8              | 6          | Course    |
| 8       | Academic Deliverables                                                                                                     |           |              | 34             |            |           |
| 8.1     | Proposal & Business Case                                                                                                  | in 1      | Eric Serrano | done           | 1          | Course    |
| 8.2     | Requirements Analysis                                                                                                     | In 1      | Eric Serrano | Done           | 1          | Course    |
| 8.3.1   | Planning & Management (due 10-18)                                                                                         | 2         | Eric Serrano | 12             | 2          | Course    |
| 8.3.2   | Design & Solution Architecture + Security Model (due 10-18)                                                               | 3         | Eric Serrano | 10             | 3          | Course    |
| 8.4.1   | Test Scenarios (due 11-01)                                                                                                | 12        | Eric Serrano | 6              | 3          | Course    |
| 8.4.2   | Production Support (due 11-08)                                                                                            | 18        | Eric Serrano | 6              | 4          | Course    |
| 8.5.1   | Final submission (due 12-05)                                                                                              | 31        | Eric Serrano | 0              | 6          | Course    |
| 9       | Enablement & Delivery                                                                                                     |           |              | 14             |            |           |
| 9.1.1   | Enablement assets (guide, question catalog, demo script)                                                                  | 29        | Eric Serrano | 5              | 6          | Course    |
| 9.2.1   | Final presentation + demo rehearsal                                                                                       | 30        | Eric Serrano | 9              | 6          | Course    |

## **WBS Dictionary & Key Deliverables Register**

| **WBS**     | **Deliverable**                                               | **Acceptance criterion**                                                                                                                                                                                                                                                                                         |
| ----------- | ------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 4.1.1       | mcp_feedback, mcp_volume                                      | get_feedback_batch reads four columns of service_feedback with rating withheld; get_order_volume_history reads three columns of service_requests; grants suite green; each agent connects only to its own server                                                                                                 |
| 4.2.1       | agent_forecast/training/train.py + artifact                   | Beats seasonal-naive on the ~26 held-out weeks, or the gap is documented; artifact gitignored                                                                                                                                                                                                                    |
| 4.2.2       | agent_forecast service                                        | Agent Card served; answers a forecast question via A2A with baseline comparison                                                                                                                                                                                                                                  |
| 4.3.1       | agent_sentiment/training/train.py + artifact                  | BERT trained offline on sentiment_labels; softmax confidence available; holdout scores recorded                                                                                                                                                                                                                  |
| 4.3.2       | agent_sentiment service + eval                                | Four-class label plus confidence; eval reports neutral accuracy per kind and hard cases per type with judge disagreement rates; low-confidence results flagged                                                                                                                                                   |
| 4.4.1       | Orchestrator, three-way routing                               | Routes to all three specialists; detects multi-domain questions; declines out-of-scope                                                                                                                                                                                                                           |
| 5.1.1       | agent_qa (deterministic)                                      | Reporting: independent re-query matches. Forecast: backtest within RMSE/MAPE threshold. Sentiment: holdout scoring and rating cross-check, never re-running the same model                                                                                                                                       |
| 5.2.1       | Loop controller                                               | Max 2 revisions; 120 s ceiling; degraded result plus escalation flag on failure; MAX_COST_PER_RUN_USD wired                                                                                                                                                                                                      |
| 5.3.1       | evals/qa/ harness                                             | Injects known-bad outputs and reports catch rate                                                                                                                                                                                                                                                                 |
| 6.1.1       | api_gateway + web/                                            | Intent input, answer, QA status, escalation flag; only the gateway is internet-reachable; unauthenticated requests rejected before any model call                                                                                                                                                                |
| 6.2.1       | Deployed slice (orchestrator, agent_reporting, mcp_incidents) | Cloud Build trigger includes an explicit deploy step; serving revision is the one just built at 100% traffic; Secret Manager; IAM ID tokens; alembic upgrade head and the grants suite pass on Cloud SQL. Stop rule: not verified by end of 11-04 means stop and record it as the first incident in 06 (ADR-045) |
| 6.2.2       | Slice hardening                                               | Agent Card cached with TTL; trace id in access logs; readiness probe beside /healthz                                                                                                                                                                                                                             |
| 6.3.1       | All services on Cloud Run                                     | Every service deployed; Cloud SQL migration complete; revision promotion verified on each deploy                                                                                                                                                                                                                 |
| 6.3.2       | Gateway + UI deployed                                         | Reachable end to end; revision promotion verified                                                                                                                                                                                                                                                                |
| 6.4.1       | Observability, complete CD                                    | Structured logs with trace ids across hops; CD for every service                                                                                                                                                                                                                                                 |
| 6.4.2       | Degradation behavior                                          | Each specialist stopped in turn; system names the capability that is down and still answers the other domains                                                                                                                                                                                                    |
| 6.4.3       | Latency and cost report                                       | Response time and token cost per request type (reporting, sentiment, forecast, declined, escalated), including QA revision cycles and cold starts                                                                                                                                                                |
| 6.4.4       | Checklist audit                                               | Closed item by item, or scoped out with a documented reason                                                                                                                                                                                                                                                      |
| 7.1.1       | Golden set                                                    | Known-correct answers across all three domains, feeding 05 and Sprint 5 evals                                                                                                                                                                                                                                    |
| 7.1.2       | Labelled routing set                                          | Ambiguous, multi-domain, out-of-scope, and technician-level items in dispatch phrasing; both models re-run                                                                                                                                                                                                       |
| 7.2.1       | Routing eval results                                          | Accuracy across N intents with failure-case analysis; full run (~300–700 requests, two LLM calls each) priced first and run on the paid, capped project                                                                                                                                                          |
| 7.2.2       | QA comparison result                                          | Catch rate for Flash-Lite vs gemini-3.1-pro-preview on the spend-capped project                                                                                                                                                                                                                                  |
| 7.3.1       | docs/evaluation-report.md                                     | Results cite dated runs in evals/results/; limitations stated                                                                                                                                                                                                                                                    |
| 8.2.1–8.3.2 | 03, 04, 05, 06                                                | Submitted by the due dates                                                                                                                                                                                                                                                                                       |
| 8.4.1       | Final submission                                              | Presentation plus the completed project                                                                                                                                                                                                                                                                          |
| 9.1.1       | Enablement assets                                             | One-page quick-start, sample-question catalog, how to read QA status and escalation flags, demo script                                                                                                                                                                                                           |
| 9.2.1       | Presentation + rehearsal                                      | Delivered and rehearsed before 12-05                                                                                                                                                                                                                                                                             |

## **Schedule & Critical Path Management Approach**

This section sequences the work defined in the WBS and determines the project's critical path using the Critical Path Method. The network is built from the level-3 work packages, one activity per package. The 29 remaining activities are joined by two milestones: the completed foundation (Sprints 1–2 engineering and deliverables 01 and 02), which anchors the network at the status date, and the final submission. Each activity carries the number used in the WBS outline, so any node can be traced to its owner, deliverable, and acceptance criterion.

The network was built and calculated as follows:

- **Dependencies**: Finish to start and follow the technical logic of the architecture. For example, the forecast agent cannot begin until both the volume tool server and the forecast model exist, and the QA agent cannot begin until the specialists it verifies are built.
- **Durations**: Derived from effort as each activity's effort estimate, in hands on hours, is divided by 2.5 hours per day, which is the planned 17.5-hour week spread over seven days, and rounded to whole days with a one-day minimum. The one exception is the first cloud deployment, which is fixed at its three-day timebox.
- **Calendar & Constraints:** The status date is 09-29-2026 and the calendar is a seven-day week. Fixed dates enter as constraints with all academic deliverables and final submission by 12-05. The first cloud deployment cannot start before 11-02.
- **Calculation:** A forward pass gives each activity's earliest start and finish (ES, EF). A backward pass from the 12-05 deadline gives its latest start and finish (LS, LF). Total float is LS minus ES, in days. The values were calculated programmatically from the table's inputs.
- **Level of Effort (LOE):** Weekly status reports and sprint ceremonies have no dependencies and sit off the network. They are counted in the effort loading, at 13.5 hours.

## **Schedule & Critical Path Management – Activity & Dependency Table**

| **#** | **Activity**                                                 | **Branch**  | **Effort (h)** | **Dur (d)** | **Pred**        | **ES** | **EF** | **LS** | **LF** | **Float (d)** |
| ----- | ------------------------------------------------------------ | ----------- | -------------- | ----------- | --------------- | ------ | ------ | ------ | ------ | ------------- |
| 1     | Foundation complete (Sprints 1-2 engineering) DONE           | Milestone   | 0              | 0           | \-              | 09-29  | 09-29  | 10-13  | 10-13  | 15            |
| 2     | 03 Planning & Management (due 10-18)                         | Academic    | 12             | 5           | 1               | 09-29  | 10-03  | 10-14  | 10-18  | 15            |
| 3     | Design & Solution Architecture + Security Model (due 10-18)  | Academic    | 10             | 4           | 1               | 09-29  | 10-02  | 10-15  | 10-18  | 16            |
| 4     | MCP servers #2 and #3 (feedback, volume)                     | Specialists | 6              | 2           | 1               | 09-29  | 09-30  | 10-23  | 10-24  | 24            |
| 5     | Forecast model + seasonal-naive backtest                     | Specialists | 8              | 3           | 1               | 09-29  | 10-01  | 10-23  | 10-25  | 24            |
| 6     | Forecast agent (Agent Card, parsing, A2A)                    | Specialists | 5              | 2           | 4, 5            | 10-02  | 10-03  | 10-26  | 10-27  | 24            |
| 7     | Sentiment model fine-tune (BERT, offline)                    | Specialists | 8              | 3           | 1               | 09-29  | 10-01  | 10-22  | 10-24  | 23            |
| 8     | Sentiment agent + confidence scoring + eval                  | Specialists | 8              | 3           | 4, 7            | 10-02  | 10-04  | 10-25  | 10-27  | 23            |
| 9     | Orchestrator routes across all three                         | Specialists | 3              | 1           | 6, 8            | 10-05  | 10-05  | 10-28  | 10-28  | 23            |
| 10    | Golden set (known-correct answers)                           | Evaluation  | 4              | 2           | 6, 8            | 10-05  | 10-06  | 10-29  | 10-30  | 24            |
| 11    | Labelled routing set + model re-run                          | Evaluation  | 5              | 2           | 9               | 10-06  | 10-07  | 10-29  | 10-30  | 23            |
| 12    | 05 Test Scenarios (due 11-01)                                | Academic    | 6              | 2           | 10, 11          | 10-08  | 10-09  | 10-31  | 11-01  | 23            |
| 13    | QA agent: three verification strategies                      | QA          | 12             | 5           | 6, 8, 10        | 10-07  | 10-11  | 11-16  | 11-20  | 40            |
| 14    | Retry loop (max 2) + escalation + per-request cost cap       | QA          | 6              | 2           | 13              | 10-12  | 10-13  | 11-21  | 11-22  | 40            |
| 15    | Fault-injection harness                                      | QA          | 6              | 2           | 14              | 10-14  | 10-15  | 11-25  | 11-26  | 42            |
| 16    | Cloud Run slice deploy + Cloud SQL (fixed window from 11-02) | Deploy      | 12             | 3           | 1               | 11-02  | 11-04  | 11-04  | 11-06  | 2             |
| 17    | Slice hardening (Card TTL, trace id, readiness probe)        | Deploy      | 3              | 1           | 16              | 11-05  | 11-05  | 11-22  | 11-22  | 17            |
| 18    | 06 Production Support (due 11-08)                            | Academic    | 6              | 2           | 16              | 11-05  | 11-06  | 11-07  | 11-08  | 2             |
| 19    | Routing eval harness + eval-run pricing + failure analysis   | Evaluation  | 9              | 4           | 11, 14          | 10-14  | 10-17  | 11-25  | 11-28  | 42            |
| 20    | QA model comparison (Flash-Lite vs Pro)                      | Evaluation  | 4              | 2           | 15              | 10-16  | 10-17  | 11-27  | 11-28  | 42            |
| 21    | FastAPI gateway + minimal React UI                           | Interface   | 13             | 5           | 9               | 10-06  | 10-10  | 11-21  | 11-25  | 46            |
| 22    | Deploy specialists, MCP, QA + full Cloud SQL migration       | Deploy      | 8              | 3           | 17, 14, 6, 8, 4 | 11-06  | 11-08  | 11-23  | 11-25  | 17            |
| 23    | Deploy gateway + UI; verify revision promotion               | Deploy      | 4              | 2           | 21, 22          | 11-09  | 11-10  | 11-26  | 11-27  | 17            |
| 24    | Observability + CI/CD completion                             | Hardening   | 8              | 3           | 23              | 11-11  | 11-13  | 11-28  | 11-30  | 17            |
| 25    | Graceful degradation                                         | Hardening   | 4              | 2           | 22              | 11-09  | 11-10  | 11-29  | 11-30  | 20            |
| 26    | Load / latency testing                                       | Hardening   | 3              | 1           | 23              | 11-11  | 11-11  | 11-28  | 11-28  | 17            |
| 27    | Production-grade checklist audit                             | Hardening   | 3              | 1           | 24, 25, 26      | 11-14  | 11-14  | 12-01  | 12-01  | 17            |
| 28    | Evaluation report                                            | Delivery    | 8              | 3           | 19, 20, 26      | 11-12  | 11-14  | 11-29  | 12-01  | 17            |
| 29    | Enablement assets (guide, question catalog, demo script)     | Delivery    | 5              | 2           | 21, 10, 11      | 10-11  | 10-12  | 11-30  | 12-01  | 50            |
| 30    | Final presentation + demo rehearsal                          | Delivery    | 9              | 4           | 28, 27, 29      | 11-15  | 11-18  | 12-02  | 12-05  | 17            |
| 31    | Final submission (due 12-05)                                 | Milestone   | 0              | 0           | 30, 27          | 11-18  | 11-18  | 12-05  | 12-05  | 17            |

**Activity CPM Network Diagram**



**Critical Path & Float Analysis**

Total float is the number of days an activity can slip without moving a deadline. It is calculated as latest start minus earliest start. The network has two paths that matter.

| Path                            | Activities                                                                                                                                                                                              | Float   |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- |
| Critical Path (Least Float)     | First cloud deployment - Production Support document                                                                                                                                                    | 2 days  |
| Longest Path (Final Submission) | Foundation - first cloud deployment - deployment hardening → deploy backend services - deploy gateway and web UI - load and latency testing - evaluation report - final presentation - final submission | 17 days |

The critical path is short because two dates pin it in place. The first cloud deployment cannot start before 11-02, and the Production Support document, which reports on that deployment, is due 11-08. The deployment window is 11-02 to 11-04, and the two days between 11-04 and the latest allowable finish of 11-06 are the project's only near-zero margin. A stop rule protects it: if the deployment is not verified serving by the end of 11-04, work stops and the failure becomes the first incident documented in that document. The margin is preserved because the deployment is deliberately not allowed to run over.

The longest path is the one that decides whether the project finishes. It runs from the first deployment through full deployment, load testing, the evaluation report and the final presentation. Every step on it is deployment or delivery work, not research, so the schedule risk sits mostly in deployment. Its 17 days of float mean the logic alone would finish the project on 11-18, well ahead of the 12-05 deadline.

Every other activity has 15 or more days of float. The planning and design documents have 15 to 16 days before their 10-18 due date. The evaluation and QA work has about 40 days, and the user enablement materials have 50. None of these is close to critical.

This float overstates the real slack. The calculation assumes activities on separate paths run in parallel, and one developer cannot do that. The next section shows what the schedule looks like once that constraint is applied.

## **Resource Plan**

This plan uses one person and a small set of tools and services, all listed below. Costs are covered in the Budget section

| **Resource**                                   | **Role in the project**                                                                                                            | **Availability and timing**                               |
| ---------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- |
| **Developer: Eric Serrano**                    | Sole owner of every work package, from design and build to testing and documentation                                               | About 15–20 hours per week, any day; planned at 17.5      |
| **Course instructor: Professor William Sunna** | Reviews each academic deliverable                                                                                                  | At the due dates in the WBS                               |
| **Local development environment**              | Docker-based PostgreSQL database and the automated test suite                                                                      | Through Sprint 3                                          |
| **GitHub and GitHub Actions**                  | Source control and automated testing on every change                                                                               | Throughout                                                |
| **Google Cloud**                               | Each agent and tool server runs as its own scale-to-zero service; a managed PostgreSQL database; secrets, build, and image storage | Reporting slice from Sprint 4; all services from Sprint 5 |
| **Gemini API, free tier**                      | Runtime model for all agents, limited to 15 requests per minute and 500 per day                                                    | Throughout                                                |
| **Gemini API, separate paid project**          | Evaluation runs and an optional stronger-model QA comparison, under a hard spend cap                                               | Sprint 5                                                  |

**External dependencies:**

The project relies on the model provider's availability, pricing and free-tier limits, on Google Cloud, and on two open standards for connecting tools and agents. Both standards are pinned to specific versions and will not be upgraded mid-project unless a specific issue requires it.

**Effort loading:**

Because one person does all the work, effort is the binding resource. The table compares estimated hours in each sprint, including weekly reports and sprint ceremonies, with capacity at 15–20 hours per week.

| **Sprint**    | **Dates**      | **Estimated hours** | **Capacity** | **Load at 17.5 h/week** |
| ------------- | -------------- | ------------------- | ------------ | ----------------------- |
| 2 (remainder) | 09-29 to 10-11 | 15                  | 28–37        | 46%                     |
| 3             | 10-12 to 10-25 | 66                  | 30–40        | 189%                    |
| 4             | 10-26 to 11-08 | 48                  | 30–40        | 137%                    |
| 5             | 11-09 to 11-22 | 41                  | 30–40        | 117%                    |
| 6             | 11-23 to 12-05 | 41.5                | 28–37        | 128%                    |
| **Total**     | **\-**         | **211.5**           | **146–194**  | **124%**                |

## **Budget Requirements**

The project's target budget is about \$100 USD, with a hard ceiling in the low three figures, and it is treated as a design constraint. The largest avoidable cost is a managed database left running for the whole project, so the database is introduced only when cloud deployment begins in Sprint 4. Runtime model calls use a free tier, and any paid usage is confined to a separate spend-capped project. Planned costs come to roughly \$11–24, and with a \$40 buffer about \$51–64 of the \$100 target is allocated.

**Planned Costs**

- **Managed Database:** about \$10–15 in total, on the smallest instance, stopped when idle, from Sprint 4.
- **Cloud Services Each Agent & Tool Server:** about \$0–5, scaling to zero when idle. The free tier absorbs demo traffic.
- **Build, Image Storage & Secrets:** about \$0–3, within the free tier.
- **Model Inference:** about \$1.40 spent to date, on generating the feedback data. All other runtime calls use the free tier.
- **Buffer:** about \$40, for overruns, demo-day headroom, and two items not yet in the baseline. The first is an optional comparison against a stronger QA model (about \$20–30). The second is the paid evaluation runs, which will be priced in Sprint 4.

**Cost Controls**

- Budget alerts on the main project at \$50 and \$80.
- On the paid project, a \$10 alert, a \$5 prepaid balance with auto-reload off, and a per-session request cap enforced in code.
- A per-request cost cap, built in Sprint 4, and cost logged for every request.
- Compute cost per answered question, reported in the final evaluation as the business-case measure.

## **Operational Governance**

Governance for a one-person has no second reviewer to catch drift. The developer holds decision authority, and the instructor reviews each academic deliverable at its due date. In place of a review board, the plan relies on written decisions, fixed checkpoints at every sprint boundary, automated quality gates, and stop rules that prevent overruns. Each of these produces a record that can be inspected.

- **Decision Governance:** Every significant design choice is logged as a numbered decision record with its rationale and the alternatives rejected. Records are never edited afterward, only superseded by a new record that names the one it replaces.
- **Delivery Cadence:** A weekly status report runs through 11-22. Each sprint ends with a review and retrospective, a risk update, and a re-baseline of remaining estimates against actual hours. Facts that depend on outside parties, such as pricing, quotas, and course requirements, are sourced or marked unconfirmed, never assumed.
- **Change Control:** Scope expansion is allowed only at the Sprint 4 boundary, and only if the project is genuinely ahead of plan. It is limited to broader capability within the existing three domains, and it excludes new agents and the deferred features.
- **Stop Rules:** High risk work is timeboxed, and when a timebox expires the work stops and the outcome is documented instead of extended. The first cloud deployment is the clearest case: if it is not verified serving by the end of 11-04, work stops and the failure becomes the first incident recorded.
- **Risk Management:** A risk register records each risk with a mitigation and a review trigger. It is reviewed at every sprint boundary and whenever a trigger fires.
- **Quality Gates.** Every change passes automated linting, unit tests, and integration tests against a real database. Deployments are checked to confirm that the revision serving traffic is the one just built. The evaluation evidence (pre-defined question set, routing accuracy, fault-injection catch rate, latency and cost) gates the final claims. A production-grade checklist is audited item by item in Sprint 6.
- **Security & Cost:** Each agent uses its own least-privilege database role enforced by database permissions, and credentials live in a secrets manager, never in code. Only the gateway is reachable from the internet, and unauthenticated requests are rejected before any model is called. Spend is governed by budget alerts, a capped paid project, and a per-request cost cap.
- **Hand-off:** Ongoing operation of the running system (monitoring, incident response, support) is defined in the Production Support document, so this section covers governance of the project and that document covers governance of the product.

## **Business User Enablement**

The proposal promises that operations leaders can use the system with no query language, dashboard training or technical skills. Enablement is therefore light. The interface does most of the work, and a small set of materials teaches leaders what to ask and how to read what comes back. There is no training curriculum. The audience is Meridian's operations leaders, and the goal is that they can act on a verified answer directly, and know what to do when the system declines or escalates.

- **Quick-start guide (one page):** How to ask a question in plain English, what a good question looks like in each of the three domains (quality, sentiment, demand), and what to expect back.
- **Sample Question Catalog:** Example questions for each domain, drawn from the evaluation sets, so the examples are ones the system has been tested on. It also shows questions that will be declined or redirected, so leaders learn the boundaries by example.
- **Guide to Reading Results:** What the verification status on each answer means, what an escalation flag means and what to do when one appears (bring the case to a person), and how low confidence sentiment results are marked for human review.
- **Stated Limits:** The system answers questions only, takes no action, handles one question at a time, works in English, and in this phase runs on a representative dataset, not live operations data.
- **Built Into the Interface:** Every answer shows its verification status. A question that is ambiguous, spans more than one domain, or falls outside scope gets a plain message saying so and what to do next, such as asking each part separately.
- **Demonstration:** A demo script and the final presentation walk through a representative question in each domain, a declined question, and a case where verification fails and the system escalates.
- **Adoption:** The proposal assumes leaders will act on verified answers instead of routing questions to analysts by habit. That cannot be measured in this phase, because there are no live users. What the project delivers instead is the evidence leaders would weigh: verification catch rate, routing accuracy, and cost per answered question.

## **Schedule Reserve**

Schedule reserve is time held back to protect the 12-05 deadline. The network shows 17 days of float on the longest path, but that float is not usable reserve, because one person cannot work parallel paths. The real reserve was meant to be Sprint 6, and at current estimates it holds about 40 hours of planned work against 28 to 37 hours of capacity, so it is effectively zero.

The plan therefore creates reserve by deferring work (see Compression Options) instead of assuming it exists.

- **Time:** About zero in Sprint 6 at current estimates.
- **Cost:** A buffer of about \$40, described in the Budget section.
- **Checkpoint:** Reserve is re-measured at every sprint boundary, when remaining estimates are re-baselined against actual hours.

## **Business Compression Options**

The remaining schedule cannot be shortened by adding people, and overlapping work has already been used, since the independent Sprint 3 packages are starting early. The remaining lever is deferring scope in a fixed order.

**Trigger:** when re-baselined estimates at a sprint boundary exceed the remaining capacity, apply the next option below and log it as a decision.

| **Order** | **Option**                                                                          | **Hours affected**     | **Effect**                                               |
| --------- | ----------------------------------------------------------------------------------- | ---------------------- | -------------------------------------------------------- |
| **1**     | Move the fault-injection harness from Sprint 4 to Sprint 5                          | 6 (moved, not removed) | Relieves Sprint 4; no scope lost                         |
| **2**     | Cut the QA model comparison                                                         | 4, plus \$20–30        | Loses a portfolio finding; no requirement depends on it  |
| **3**     | Trim the web interface to the minimum: answer, verification status, escalation flag | Part of 13             | Less polish; required behavior kept                      |
| **4**     | Reduce enablement materials to the quick-start guide and demo script                | Part of 5              | Drops the question catalog and the results-reading guide |

**_\*Never cut:_** _routing evaluation, the QA catch-rate measurement, deployment with authentication, and the degradation tests. The success criteria depend on them. The Sprint 4 gate for adding scope stands: no expansion unless genuinely ahead._