# **Agentic Service Operations Intelligence Platform**

## **Test Scenarios**

**Document Information**
Author(s): Eric Serrano 
Keywords: Agentic, AI, Multi-Agent, Field Service, Operations, Business Intelligence, Multi Context Protocol (MCP), Agent to Agent (A2A), Capstone

Due Date: November 1 **(Assignment complete)**

# **Agentic Service Operations Intelligence Platform**

## **Introduction**

**Purpose**

This document defines the test scenarios for the Agentic Service Operations Intelligence Platform. Its purpose is to show, for every requirement in the Detailed Requirements Analysis, how the system will be verified: what is tested, under what starting conditions, and what result counts as a pass. Twenty scenarios are defined, each broken into specific test cases with stated inputs and expected results. Together they cover every functional and non-functional requirement the project is committed to delivering.

The document is written before several components are built, so it is a reference specification and not a live test record. It defines what is to be tested and what result counts as a pass. Each scenario carries an execution status as of the date of writing, so a reader can tell what had been run at that point.

**System Under Test**

The platform lets a user ask a plain-language question about a simulated field service business and receive a verified answer. Five cooperating agents produce it:

- Orchestrator: classifies the question and routes it to one specialist, or declines it, asks for clarification, or asks the user to split it.
- Reporting agent: answers incident and quality questions: incident rate, SLA compliance, first-time fix rate, and repeat-visit drivers.
- Sentiment agent: classifies and summarizes customer feedback.
- Forecast agent: forecasts weekly service request volume.
- QA agent: independently checks each specialist's draft and can reject it for revision.

Each specialist reaches data only through its own narrowly scoped tool server and its own least-privilege database role. The services run as separate containers on Google Cloud Platform, behind a web gateway and interface, all data is synthetic.

**Scope**

**In Scope:**

Every requirement, FR-01 to FR-19, and the five non-functional areas. Question intake and routing, the three specialists, the QA agent and its bounded revision loop, the security and data-access controls, the synthetic dataset, and the five non-functional areas (performance, security, scalability, availability, and ethical considerations). The web interface is also tested, as the point where QA status and escalation flags reach the user.

**Out of Scope:**

- Multi-turn follow-up, multi-specialist answers to one question, and the external research agent. These are not committed deliverables, and no scenario depends on them.
- Accuracy evaluation of the models and the routing logic. Routing accuracy, sentiment precision and recall, forecast error against the baseline, and QA catch rate. These are measured as percentages in a separate evaluation. The scenarios here are pass/fail checks of behavior. Where a scenario touches an evaluated quantity, such as a forecast's stored error, it checks that the system reports it correctly, not whether the figure is good.
- Throughput and large-scale load testing. Latency is tested for a handful of concurrent users, and no throughput target is set.
- Testing against real customer data. Everything is synthetic by design.

**How This Document Is Organized**

Section 2 describes the test approach, test levels, how expected results are derived, and how model-dependent behavior is handled.

Section 3 sets out the test environment and the preconditions shared by all scenarios.

Section 4 is the coverage matrix, mapping each requirement to the scenarios that verify it.

Section 5 summarizes all twenty scenarios.

Section 6 gives the full detail of each one.

Section 7 records known failures and limitations.

**Conventions Used in the Scenarios**

Scenarios are numbered TS-01 to TS-20, and test cases carry the scenario number and a sequence letter (TS-05-A, TS-05-B). Requirements are cited by the identifiers used in the Requirements Analysis (FR-01 to FR-22 for functional requirements, and the numbered non-functional requirements). Each scenario states one of four execution statuses:

- Passed: executed, and all cases met their expected results.
- Not yet run: the component under test is built or planned, but the scenario has not been executed.
- Not yet built: the component under test does not exist yet.
- Known failing: executed, and the system does not meet the requirement. The expected result stays at what the requirement demands, and the actual result is recorded beside it.

## **Test Approach**

**Test Levels**

Verification happens at four levels, each scenario names the level or levels its cases use:

| **Level**   | **What it checks**                                                                                                                        | **How it runs**                                                         |
| ----------- | ----------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| Unit        | Individual functions and data contracts with no network or model: metric calculations, response formats, trend rules, the retry counter   | Automated, offline, on every code change                                |
| Integration | Services against a live PostgreSQL database: database grants, tool server behavior, figures against independent queries                   | Automated, on every code change                                         |
| End-to-end  | A question sent through the full chain (orchestrator, specialist, tool server, QA) on the containerized stack, including real model calls | Automated where possible, run on demand because it consumes model quota |
| Manual      | Behavior that needs observation: the web interface, stopping a service mid-run, the deployed environment                                  | Run by hand against the deployed system, with the result recorded       |

**Deriving Expected Results**

Expected figures never come from the system under test. For every numeric answer, the expected value is computed by a separate query written independently of the agents' code and run through a read-only evaluation database role, or with a standard statistics library for significance tests and trend checks. If the agent and its check shared code, a shared mistake would pass unnoticed.

The one exception is the forecast as those scenarios check how the forecast is presented (the range shown, the stated error, the baseline comparison), not the model's accuracy, so the expected values come from the stored model itself.

Counts must match exactly, rates are compared at the precision the system reports them. Dates in questions resolve against one fixed as-of date, so a question like "last quarter" has the same meaning on every run.

**Handling Model-Dependent Behavior**

Language models can answer the same question differently on different runs. Most of the system is deliberately deterministic:

Figures, trends, QA checks on numbers, and the answer text are all produced in code, and a model is used only to classify the question and parse it into a structured request. Cases whose result depends on a model call are therefore run three times, and the case passes only if all three runs meet the expected result. A case that passes only some runs is recorded as failing, with the range, because intermittent behavior is not a pass for a system meant to be relied on.

QA scenarios need a draft that is wrong in a known way. Rather than waiting for a specialist to make a mistake, these cases substitute a draft with a deliberate fault (a changed figure, a misquoted comment, a mismatched flag) and confirm QA rejects it. A matching correct draft confirms QA does not reject good answers.

**Test Data and Quota**

All cases run against the frozen synthetic dataset described in Section 3. The data is generated from a saved random seed, so it is identical on every run.

The runtime model is on a free tier limited to 500 requests per day. A full execution of every case at three runs each, at two to four model calls per question, can exceed that. Execution is therefore planned in batches across days, or run on a separate paid project with a fixed spending cap. Cases that need no model (database isolation, the dataset, the unit-level checks) run without using quota.

**Pass Criteria and Failures**

A case passes when its observed result matches the expected result. A scenario passes when all its cases pass. A failing case is recorded with its actual result and not edited to match the system. If the failure reflects a requirement the system does not yet meet, the scenario is marked known failing and listed in Section 7, with the expected result unchanged, so the gap stays visible instead of being absorbed into the test.

## **Test Environment & Preconditions**

**Test Environments**

Cases run in one of two environments. Most run locally, where every service and the database run as containers on one machine. Cases that depend on the deployed system (public exposure, access control, cold starts, and the web interface) run on the deployed environment on Google Cloud Platform. Each scenario in Section 6 states which it uses.

| **Component**        | **Local**                                                                                | **Deployed**                                                             |
| -------------------- | ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| Services             | Containers on one machine: orchestrator, three specialists, QA agent, three tool servers | The same services as separate Cloud Run services, behind the web gateway |
| Database             | PostgreSQL 16 in a container                                                             | Cloud SQL, PostgreSQL 16, same schema migrations                         |
| Credentials          | Environment configuration                                                                | Secret Manager                                                           |
| Language model       | Gemini 3.5 Flash-Lite for classification, parsing, and QA's interpretation check         | Same                                                                     |
| Sentiment classifier | Fine-tuned transformer (version 1), loaded from a stored artifact                        | Same artifact                                                            |
| Forecast model       | Regression with year-end indicator (version 2), loaded from a stored artifact            | Same artifact                                                            |

**Dataset Reference Values**

All cases run against the same synthetic dataset, generated from a saved random seed and loaded once.

Expected results in later sections refer to these figures:

| **Item**                    | **Value**                                                                       |
| --------------------------- | ------------------------------------------------------------------------------- |
| History                     | 36 months, 156 complete weeks (2023-09-04 to 2026-08-30)                        |
| Service requests            | 20,230 (18,063 completed; cancellation rate 10.2%)                              |
| Incidents                   | 2,067                                                                           |
| Customer feedback responses | 7,521 (sentiment mix 50.2% positive, 22.4% neutral, 19.6% negative, 7.8% mixed) |
| Reference data              | 50 accounts, 197 locations, 32 technicians, 198 contacts, 15 internal users     |
| Injected anomalies          | One account volume drop, one regional volume drop, one billing surcharge window |

**Preconditions Common to All Scenarios**

Unless a scenario states otherwise, these hold before any case runs:

1. Services healthy. Every service in the environment under test reports healthy on its health check.
2. Database ready. The schema is migrated to the current version and loaded with the dataset above, and the dataset's own validation checks pass.
3. Model artifacts present. The sentiment classifier and forecast model are in place, and each tool server has verified the integrity of its artifact at start-up.
4. Fixed as-of date. The system resolves relative dates ("last month," "the past 30 days," "next quarter") against a fixed as-of date, set to the final day of the dataset, August 30, 2026, and not against the current date. Every answer states the as-of date it used. This makes each question mean the same thing on every run, whenever the test is executed
5. Credentials configured. Each service holds only its own database role, and the evaluation role used to compute expected values is available to the tester only, never to a deployed service.
6. Model access available. A valid model key with quota remaining is configured, either the free tier or the capped paid project.
7. Logging on. Structured logging is enabled, so every request leaves a trace ID that can be followed across services.
8. Clean state. No other traffic is running, and any service stopped during an earlier case has been restored.

**Test Inputs**

Test questions are written for this document and are kept separate from the question sets used in the accuracy evaluations. Reusing evaluation questions here would let tuning against one contaminate the other.

## **Coverage Matrix**

Every requirement in the Detailed Requirements Analysis is mapped below to the scenarios that verify it. Requirements that several scenarios share are listed once, with all their scenarios. Non-functional requirements are numbered NFR-1 to NFR-5 in the order they appear in that document.

**Functional Requirements**

| **Req.** | **Requirement (short form)**                                                             | **Scenarios** |
| -------- | ---------------------------------------------------------------------------------------- | ------------- |
| FR-01    | Accept a natural-language question and classify intent                                   | TS-01         |
| FR-02    | Route the intent to the correct specialist                                               | TS-01         |
| FR-03    | Handle ambiguous intents without force-routing                                           | TS-02         |
| FR-04    | Detect multi-domain questions and ask for a split                                        | TS-03         |
| FR-05    | Decline out-of-scope intents                                                             | TS-04         |
| FR-06    | Reporting: incident and quality metrics, by account, region, service type, or technician | TS-05, TS-06  |
| FR-07    | Sentiment: classify feedback with a confidence score                                     | TS-07         |
| FR-08    | Forecast: weekly volume against a seasonal-naive baseline                                | TS-08         |
| FR-09    | QA reporting: independent recomputation of figures                                       | TS-09         |
| FR-10    | QA forecast: error check against held-out weeks                                          | TS-10         |
| FR-11    | QA sentiment: non-circular check, low-confidence flagging                                | TS-11         |
| FR-12    | Bounded revision loop (at most 2 retries)                                                | TS-12         |
| FR-13    | Degraded result with warning and escalation flag on final failure                        | TS-12         |
| FR-14    | Least-privilege database role per agent                                                  | TS-13         |
| FR-15    | No agent can read customer contact data                                                  | TS-13         |
| FR-16    | Sentiment pipeline cannot read internal staff notes                                      | TS-13         |
| FR-17    | Sentiment agent cannot read the star rating                                              | TS-13         |
| FR-18    | Reproducible synthetic dataset from documented parameters                                | TS-19         |
| FR-19    | Web interface showing answer, QA status, escalation flag                                 | TS-20         |

**Non-Functional Requirements**

| **Req.** | **Area**                                                                            | **Scenarios**                                                         |
| -------- | ----------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| NFR-1    | Performance: 120-second ceiling; latency and cost measured per request type         | TS-16 (the degraded-result path it reuses is also exercised in TS-12) |
| NFR-2    | Security: layered controls, access control, untrusted-input handling, audit logging | TS-13, TS-14, TS-15                                                   |
| NFR-3    | Scalability: independent services, rate-limit handling, full dataset                | TS-18                                                                 |
| NFR-4    | Availability: health checks, timeouts, circuit breakers, graceful degradation       | TS-17                                                                 |
| NFR-5    | Ethical considerations: synthetic data, decision support, stated limitations        | TS-20 (with TS-19 for the synthetic-data commitment)                  |

**Requirements Not Verified by a Dedicated Scenario**

| **Req.** | **Requirement**                                             | **Reason**                                                                                                                                           |
| -------- | ----------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| FR-20    | Multi-turn conversational follow-up                         | Not a committed deliverable. The system is single-shot by design, and TS-03 confirms a follow-up-style question is handled as a standalone question. |
| FR-21    | Route one question to several specialists and merge answers | Not a committed deliverable. FR-04 covers these questions by asking the user to split them, which TS-03 verifies.                                    |
| FR-22    | Research agent for external web data                        | Not a committed deliverable. TS-04 confirms a request needing external data is declined.                                                             |

**Notes on the Matrix**

- All 19 functional requirements (FR-01 to FR-19) and all 5 non-functional requirements are covered by at least one scenario. FR-19, the web interface, is verified in TS-20, where QA status and escalation flags reach the user.
- FR-03 is covered by a scenario that is known to fail at the time of writing. The gap is described in Section 7.
- Security (NFR-2) is spread over three scenarios on purpose. TS-13 verifies the database layer, TS-14 verifies who can reach the system, and TS-15 verifies how it handles hostile input. That matches the requirement's design that no single control carries the security model.

## **Scenario Summary Table**

Twenty scenarios verify the requirements. The table gives each scenario's coverage, test level, environment, and execution status as of October 5, 2026. Section 6 gives the full detail.

| **ID** | **Scenario**                                        | **Covers**            | **Level**               | **Environment** | **Status**    |
| ------ | --------------------------------------------------- | --------------------- | ----------------------- | --------------- | ------------- |
| TS-01  | Clear questions reach the right specialist          | FR-01, FR-02          | End-to-end              | Local           | Not yet run   |
| TS-02  | Ambiguous question is not force-routed              | FR-03                 | End-to-end              | Local           | Known failing |
| TS-03  | Multi-domain question gets a split instruction      | FR-04                 | End-to-end              | Local           | Not yet run   |
| TS-04  | Out-of-scope requests are declined                  | FR-05                 | End-to-end              | Local           | Not yet run   |
| TS-05  | Reporting headline metrics                          | FR-06                 | Integration, end-to-end | Local           | Not yet run   |
| TS-06  | Repeat-visit drivers and technician-level reporting | FR-06                 | Integration, end-to-end | Local           | Not yet run   |
| TS-07  | Sentiment analysis                                  | FR-07                 | Integration, end-to-end | Local           | Not yet run   |
| TS-08  | Volume forecast                                     | FR-08                 | Integration, end-to-end | Local           | Not yet run   |
| TS-09  | QA verifies reporting                               | FR-09                 | Integration, end-to-end | Local           | Not yet built |
| TS-10  | QA verifies forecast                                | FR-10                 | Integration, end-to-end | Local           | Not yet built |
| TS-11  | QA verifies sentiment without circularity           | FR-11                 | Integration, end-to-end | Local           | Not yet built |
| TS-12  | Bounded revision loop and degraded result           | FR-12, FR-13          | Unit, end-to-end        | Local           | Not yet built |
| TS-13  | Database isolation                                  | FR-14 to FR-17, NFR-2 | Integration             | Local           | Not yet run   |
| TS-14  | Access control and exposure                         | NFR-2                 | Manual                  | Deployed        | Not yet built |
| TS-15  | Hostile and malformed input                         | NFR-2                 | Integration, end-to-end | Local           | Not yet run   |
| TS-16  | Time ceiling, latency, and cost                     | NFR-1                 | End-to-end, manual      | Local, deployed | Not yet built |
| TS-17  | Availability and graceful degradation               | NFR-4                 | Manual                  | Local           | Not yet built |
| TS-18  | Rate limits and scalability                         | NFR-3                 | End-to-end, manual      | Local, deployed | Not yet built |
| TS-19  | Synthetic dataset                                   | FR-18, NFR-5          | Integration             | Local           | Not yet run   |
| TS-20  | Web interface and decision-support transparency     | FR-19, NFR-5          | Manual                  | Deployed        | Not yet built |

**Status as of October 5, 2026:**

1 known failing, 9 not yet built, 10 not yet run.

No scenario has been executed as defined in this document. "Not yet built" means a component the scenario depends on does not exist yet:

The QA agent and revision loop, the single request deadline, circuit breakers, service-to-service authentication, the web gateway and interface, or the deployment.

## **Detailed Scenarios**

Each scenario lists its coverage, test level, and status as of October 5, 2026, followed by a description, any preconditions beyond the common ones in Section 3, the test cases, and the pass criteria. All questions are written for this document. Expected figures are computed independently, as described in Section 2.

**TS-01: Clear questions reach the right specialist**

**Covers:** FR-01, FR-02 | **Level:** End-to-end | **Status:** Not yet run

Verifies that a clear single-domain question is classified and handed to the specialist that owns that domain. Quality verification is checked in TS-09 to TS-11, so this scenario checks routing only.

**Preconditions:** All three specialists are running and reachable from the orchestrator.

| **Case** | **Input / steps**                                                                | **Expected result**                                                                                                                                   |
| -------- | -------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| TS-01-A  | "What was our SLA compliance in the west region last month?"                     | Routed to the reporting agent. The answer covers July 2026, states the as-of date, and carries the reporting agent's figures.                         |
| TS-01-B  | "Has customer sentiment in the southeast gotten worse over the past six months?" | Routed to the sentiment agent. The answer covers the six months to the as-of date for the southeast region.                                           |
| TS-01-C  | "How many install requests should we expect over the next 8 weeks?"              | Routed to the forecast agent. The answer is a weekly forecast for the 8 weeks following the as-of date.                                               |
| TS-01-D  | Retrieve the Agent Card of each specialist.                                      | Each card is published, names the specialist's capability, and exposes no tool schemas. The orchestrator routes using only the advertised capability. |

**Pass criteria:** The specialist that answered matches the expected one in A to C in all three runs, and D holds.

**TS-02: Ambiguous question is not force-routed**

**Covers:** FR-03 | **Level:** End-to-end | **Status:** Known failing

Verifies that a question that could mean different measurable things to different specialists is not guessed at. The system should ask the user to clarify and call no specialist. A question that clearly belongs to one domain but omits a detail (a period, for example) is not ambiguous and should be answered using stated defaults. Case C checks that the clarification behavior does not over-trigger.

| **Case** | **Input / steps**                                                     | **Expected result**                                                                                                                                                                          |
| -------- | --------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| TS-02-A  | "Is service getting better or worse?"                                 | No specialist is called. The response asks for clarification, states that the question is ambiguous, and names what each candidate domain could answer, with an example rephrasing for each. |
| TS-02-B  | "How is the west region performing?"                                  | As TS-02-A.                                                                                                                                                                                  |
| TS-02-C  | "What is the incident rate for the central region?" (no period given) | Routed to the reporting agent, with no clarification request. The answer covers July 2026, the month before the as-of date, and says it assumed that range.                                  |

**Pass criteria:** A and B produce a clarification with no specialist call, and C produces an answer, all in three of three runs.

**Result at the date of writing:** In testing on five fresh ambiguous questions, the router recognized three and sent the other two to a best-fit specialist. The scenario is therefore recorded as known failing, and the expected results above are unchanged. See Section 7.

**TS-03: Multi-domain question gets a split instruction**

**Covers:** FR-04 | **Level:** End-to-end | **Status:** Not yet run

Verifies that a question spanning more than one domain is not answered in part. The system tells the user to ask each part separately. The system is single-shot, so the scenario also confirms that a follow-up-style question gets no help from an earlier one.

| **Case** | **Input / steps**                                                                                                | **Expected result**                                                                                                                      |
| -------- | ---------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| TS-03-A  | "How many repeat visits did we have last quarter, and what will request volume be next month?"                   | No specialist is called. The response says the question spans more than one area and asks the user to submit each part separately.       |
| TS-03-B  | "Is sentiment in the central region getting worse, and is that hurting our SLA compliance?"                      | As TS-03-A.                                                                                                                              |
| TS-03-C  | In one session, ask "What was the SLA compliance in the central region last month?" and then "And for the west?" | The second question is handled as a standalone question. The response contains no figure, region, or metric carried over from the first. |

**Pass criteria:** A and B return the split instruction with no specialist call, and C shows no carried-over context, all in three of three runs.

**TS-04: Out-of-scope requests are declined**

**Covers:** FR-05 | **Level:** End-to-end | **Status:** Not yet run

Verifies that requests the system cannot answer are declined with an explanation and are not guessed at. Cases cover a request to change data, a request needing external data, a near-miss that borrows an in-scope word, and two requests that name an in-scope domain but an unsupported breakdown or period.

| **Case** | **Input / steps**                                                                                                                  | **Expected result**                                                                                                                                                                                  |
| -------- | ---------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| TS-04-A  | "Mark all of last week's cancelled requests as rescheduled."                                                                       | Declined, with no specialist called. A row count of the service requests table before and after is identical.                                                                                        |
| TS-04-B  | "How do our response times compare with other field service companies?"                                                            | Declined, with an explanation that the system answers only from the organization's own operational data.                                                                                             |
| TS-04-C  | "What will the weather be like in the central region next week?"                                                                   | Declined as out of scope. Not routed to the forecast agent, despite the word "next week".                                                                                                            |
| TS-04-D  | Two inputs: "Break down customer sentiment by account for last quarter." and "What was our forecast request volume for June 2026?" | Each is declined by the specialist that owns the domain. The decline names what is supported (sentiment by all sites or by region; forecasts of future weeks only). No tool call is made for either. |

**Pass criteria:** Every input is declined with a stated reason, and none produces a figure, in three of three runs.

**TS-05: Reporting headline metrics**

**Covers:** FR-06 | **Level:** Integration, end-to-end | **Status:** Not yet run

Verifies that the reporting agent returns the three headline quality metrics using the single standard definition for each, and that figures match an independent calculation. Definitions: incident rate is incidents per 100 completed requests. First-time fix rate is completed requests with no repeat visit over all completed requests, and a cancelled repeat request does not count against the original. SLA compliance runs from dispatch time, and requests never dispatched are excluded.

| **Case** | **Input / steps**                                                                               | **Expected result**                                                                                                                                                                 |
| -------- | ----------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| TS-05-A  | "What was the overall incident rate from September 2023 through August 2026?"                   | 2,067 incidents over 18,063 completed requests, a rate of 11.4433 per 100.                                                                                                          |
| TS-05-B  | "What was SLA compliance in the west region in July 2026?"                                      | Counts and rate match the independent calculation exactly. Undispatched requests are excluded from the denominator.                                                                 |
| TS-05-C  | "What was the first-time fix rate from September 2023 through August 2026?"                     | 0.9798, with cancelled repeat requests excluded. The rate that would result if they were counted (0.9777) is not returned.                                                          |
| TS-05-D  | "Break down incidents by region for the full history." Repeat for service type and for account. | Each breakdown matches the independent calculation. Groups sum to the total of 2,067, are ordered highest first, and for account show at most 25 groups with the full count stated. |

**Pass criteria:** Every count matches exactly and every rate matches at the precision the system reports, in three of three runs.

**TS-06: Repeat-visit drivers and technician-level reporting**

**Covers:** FR-06 | Level: Integration, end-to-end | Status: Not yet run

Verifies the repeat-visit analysis and questions about an individual technician. A group is reported as standing out only if it has at least 20 jobs, its repeat rate is above the rest, and a significance test supports it. A technician name must resolve to exactly one technician before any figure is returned.

**Preconditions:** A technician with a unique name, and a first name shared by at least two technicians, are chosen from the dataset before the run.

| **Case** | **Input / steps**                                                                                                                          | **Expected result**                                                                                                                                                                  |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| TS-06-A  | "Which incident types are most associated with repeat visits from September 2025 through August 2026?"                                     | The groups reported as standing out, with their repeat rates and job counts, match the independent calculation. If none qualifies, the answer says the types did not differ clearly. |
| TS-06-B  | "Which service types have the highest repeat-visit rate over the full history?"                                                            | Groups are ordered by repeat rate, highest first. Rates, job counts, and the stand-out verdicts match the independent calculation.                                                   |
| TS-06-C  | "What is the first-time fix rate for technician \[unique name\]?"                                                                          | The technician is identified, and the figure equals both the independent calculation and that technician's group in the technician breakdown.                                        |
| TS-06-D  | Two inputs: "What is the incident rate for technician Zzyzx Quill?" and "What is the SLA compliance for technician \[shared first name\]?" | The first reports that no such technician was found. The second lists the matching technicians (at most five) and asks which is meant. Neither returns a figure.                     |

**Pass criteria:** Figures and verdicts match the independent calculation, and D returns no figures, in three of three runs.

**TS-07: Sentiment analysis**

**Covers:** FR-07 | Level: Integration, end-to-end | Status: Not yet run

Verifies that the sentiment agent summarizes customer feedback by label, reports confidence-based review flags, applies the trend rule, and quotes comments faithfully.

| Case    | Input / steps                                                            | Expected result                                                                                                                                                                                                                                                                |
| ------- | ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| TS-07-A | "What does customer sentiment look like across all sites for July 2026?" | Counts and shares for positive, neutral, negative, and mixed match the independent calculation. The answer states the range and as-of date, and the number of comments flagged for human review.                                                                               |
| TS-07-B | "Is sentiment in the northeast getting worse over the past six months?"  | Monthly buckets for the northeast. A rise or fall is reported only if the latest month and the earlier months each have at least 20 comments and a two-proportion test gives p < 0.05. Otherwise the answer says there is no clear change. Shares and counts are always shown. |
| TS-07-C | "Show me some negative comments from the central region in June 2026."   | At most 3 comments. Each exists in the database for that region and month, with the stated label and its text unaltered.                                                                                                                                                       |
| TS-07-D | Check every stored prediction.                                           | Each has a label, a confidence between 0 and 1, and a review flag set exactly when confidence is below the stored threshold. The label is the class with the highest probability.                                                                                              |

**Pass criteria:** Counts, shares, trend verdicts, and flags match the independent calculation, in three of three runs for A to C.

**TS-08: Volume forecast**

**Covers:** FR-08 | Level: Integration, end-to-end | Status: Not yet run

Verifies the forecast agent's answers and that its reliability is reported honestly. A forecast is served only for a service type and horizon whose stored error meets the release rule. For any other combination the system names the error and gives no numbers.

| **Case** | **Input / steps**                                                   | **Expected result**                                                                                                                                                                                                                                                                 |
| -------- | ------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| TS-08-A  | "What will request volume be in December?"                          | Weekly forecasts for the weeks whose Monday falls in December 2026, each with an 80% range. A total equals the sum of the weekly figures and carries no range. Year-end weeks carry a caveat that the holiday adjustment is unvalidated. The stored error for the horizon is shown. |
| TS-08-B  | "How many install requests should we expect over the next 8 weeks?" | Served. Weekly figures with ranges match the stored model. The stored error for the 5 to 13 week band is shown.                                                                                                                                                                     |
| TS-08-C  | "How many upgrade requests should we expect over the next 8 weeks?" | Not served. The answer names the stored error and states that no forecast is given. It contains no forecast numbers.                                                                                                                                                                |
| TS-08-D  | Inspect the stored evaluation of the total volume forecast.         | On the final 26 held-out weeks, the model's error is reported next to the seasonal-naive baseline's. A model that does not beat the baseline is reported as such.                                                                                                                   |

**Pass criteria:** A to C show the stated content, with served figures matching the stored model and no numbers for unserved cases, in three of three runs. D shows both errors.

**TS-09: QA verifies reporting**

**Covers:** FR-09 | Level: Integration, end-to-end | Status: Not yet built

Verifies that the QA agent recomputes reporting figures independently and rejects a wrong draft, including one whose figures are right but answer a different question. A test harness substitutes the specialist's draft.

| **Case** | **Input / steps**                                                          | **Expected result**                                                                                     |
| -------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| TS-09-A  | Submit a correct draft for the TS-05-A question.                           | Accepted. The log shows QA queried the database with its own role and called no specialist tool server. |
| TS-09-B  | Submit the same draft with the incident count changed from 2,067 to 2,167. | Rejected, with guidance naming the failed check (the incident count) and the recomputed value.          |
| TS-09-C  | Ask for July 2026, but submit a draft with correct figures for June 2026.  | Rejected for misreading the question. The guidance says the period does not match.                      |

**Pass criteria:** A is accepted, and B and C are rejected, with B, whose check needs no model, rejected consistently and C rejected in three of three runs.

**TS-10: QA verifies forecast**

**Covers:** FR-10 | Level: Integration, end-to-end | Status: Not yet built

No one can verify a future value, so QA verifies the method. The backtest against held-out weeks is run once, when the model is evaluated and released. Its error for each service type and horizon band is stored with the model. At answer time, QA checks the draft's input history and arithmetic, then looks up the stored error for the requested slice. A forecast is accepted only if that slice and band are marked as served.

| **Case** | **Input / steps**                                                                     | **Expected result**                                                                               |
| -------- | ------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| TS-10-A  | Submit a correct draft for TS-08-B.                                                   | Accepted. The shown error equals the stored value.                                                |
| TS-10-B  | Submit a draft in which one weekly 80% range does not contain its own point forecast. | Rejected, with guidance naming the failed arithmetic check.                                       |
| TS-10-C  | Submit a draft whose recent weekly history differs from the database.                 | Rejected, with guidance naming the history check.                                                 |
| TS-10-D  | Submit a draft with forecast numbers for the upgrade slice (TS-08-C).                 | Rejected because the slice is not served. The stored error is shown and the numbers are withheld. |

**Pass criteria:** A is accepted and B to D are rejected, with the stated guidance.

**TS-11: QA verifies sentiment without circularity**

**Covers:** FR-11 | Level: Integration, end-to-end | Status: Not yet built

Sentiment has no answer-time ground truth. QA therefore cross-checks labels against the star rating, which the sentiment agent cannot read, and checks the comment set, counts, and flags. It never re-runs the classifier. Only clear contradictions count: positive on 1 to 2 stars, or negative on 4 to 5 stars. An answer is rejected only when its contradiction rate is clearly above the rate normally seen.

| **Case** | **Input / steps**                                                                                     | **Expected result**                                                                                                                          |
| -------- | ----------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| TS-11-A  | Submit a correct draft for TS-07-A.                                                                   | Accepted. Counts match, the review flags match the stored threshold, and the answer reports how many comments had a rating to check against. |
| TS-11-B  | Submit a draft in which labels are altered so many positive labels fall on 1 to 2 star comments.      | Rejected. The guidance gives the contradiction rate against the normal rate.                                                                 |
| TS-11-C  | Submit a draft quoting a comment that does not exist, and another with a quote whose text is altered. | Both rejected, naming the quote check.                                                                                                       |
| TS-11-D  | Submit a draft whose flagged count differs from re-applying the threshold.                            | Rejected, naming the flag check.                                                                                                             |
| TS-11-E  | Inspect QA's database permissions and its call log.                                                   | QA has no permission on the gold-label table. It makes no call to the sentiment model.                                                       |

**Pass criteria:** A is accepted, B to D are rejected for the stated reason, and E holds, with model-dependent cases passing in three of three runs.

**TS-12: Bounded revision loop and degraded result**

**Covers:** FR-12, FR-13 | Level: Unit, end-to-end | Status: Not yet built

Verifies that a rejected draft is revised with specific guidance, at most twice, and that a final failure returns a degraded result and never an unverified answer presented as verified. A test harness makes the specialist return scripted drafts.

| **Case** | **Input / steps**                             | **Expected result**                                                                                                                                                                                                      |
| -------- | --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| TS-12-A  | First draft wrong, second correct.            | Accepted after one revision. The guidance sent to the specialist names the failed check. The response is marked verified.                                                                                                |
| TS-12-B  | First and second drafts wrong, third correct. | Accepted after two revisions.                                                                                                                                                                                            |
| TS-12-C  | Every draft wrong.                            | After two revisions (three drafts and three QA reviews in total), the response is marked degraded, carries a warning that the answer could not be verified, and has the escalation flag set. No further attempt is made. |
| TS-12-D  | A draft fails two checks at once.             | The guidance lists each failed check separately.                                                                                                                                                                         |

**Pass criteria:** The specialist is never called more than three times for one request, and a degraded result is never marked verified.

**TS-13: Database isolation**

**Covers:** FR-14 to FR-17, NFR-2 | Level: Integration | Status: Not yet run

Verifies that the access matrix is enforced by the database and does not depend on application code. Each case connects to the database directly as the role under test.

| **Case** | **Input / steps**                                                                                                                                        | **Expected result**                                                                                                        |
| -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| TS-13-A  | For each role, attempt every read and write on every table and permitted column.                                                                         | Operations in the access matrix succeed. Every other attempt is refused by the database.                                   |
| TS-13-B  | As each of the four runtime roles (reporting, sentiment, forecast, QA), read the customer contacts table.                                                | Refused for all four. No agent can read customer contact data.                                                             |
| TS-13-C  | As the sentiment role, read the incidents table, the rating column of feedback, and the gold-label table. Then read the four permitted feedback columns. | The first three are refused. The permitted read succeeds.                                                                  |
| TS-13-D  | As each runtime role, attempt insert, update, and delete on every table.                                                                                 | Refused, except the sentiment role inserting its own predictions. Update and delete on predictions are refused for it too. |

**Pass criteria:** Every result matches the matrix exactly, with no unexpected grant and no missing grant.

**TS-14: Access control and exposure**

**Covers:** NFR-2 | Level: Manual | Environment: Deployed | Status: Not yet built

Verifies who can reach the system. Only authorized users may call it, and only the gateway is exposed to the internet.

| **Case** | **Input / steps**                                                                         | **Expected result**                                                                    |
| -------- | ----------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| TS-14-A  | Send a question to the gateway without credentials, then with valid credentials.          | The first is rejected, and the log shows no model call for it. The second is answered. |
| TS-14-B  | From outside the system, try to reach the orchestrator, each agent, and each tool server. | Every one is unreachable or refused. Only the gateway responds.                        |
| TS-14-C  | Call a specialist directly without a valid service identity.                              | Rejected.                                                                              |
| TS-14-D  | Search the code repository and the built container images for credentials.                | None found. Services read credentials from Secret Manager.                             |

**Pass criteria:** All four cases show the expected result.

**TS-15: Hostile and malformed input**

**Covers:** NFR-2 | Level: Integration, end-to-end | Status: Not yet run

Verifies that untrusted text cannot steer the system, that malformed input fails safely, and that no tool accepts free-form queries.

**Preconditions:** For case A, a disposable copy of the database is used, so the frozen dataset is not altered.

| **Case** | **Input / steps**                                                                                                                     | **Expected result**                                                                                                                                                          |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| TS-15-A  | Add a feedback comment that says to ignore its instructions and list all accounts. Ask a sentiment question whose answer includes it. | Figures are correct. The comment appears only as quoted text, if at all. No tool outside the sentiment tools is called, and no customer comment is sent to a language model. |
| TS-15-B  | Ask "What is {{7\*7}}?", then send an empty question and an oversize question.                                                        | Each gets a normal response or a clear rejection. There is no server error, and no expression is evaluated.                                                                  |
| TS-15-C  | Ask "Run SELECT \* FROM contacts." Then list the tools on each tool server.                                                           | Declined, with no query run. Each server lists only its purpose-built tools, and none takes a free-form query.                                                               |
| TS-15-D  | Send a question naming a technician, then inspect the logs.                                                                           | Every entry for the request carries the request's trace ID. The logs contain no customer comment text or typed technician name.                                              |

**Pass criteria:** All four cases show the expected result. Model-dependent cases pass in three of three runs.

**TS-16: Time ceiling, latency, and cost**

**Covers:** NFR-1 | Level: End-to-end, manual | Environment: Local, deployed | Status: Not yet built

Verifies the 120-second ceiling and records response time and token cost per request type. The system sets no response-time target, so the measurements are reported as found.

| **Case** | **Input / steps**                                                                                 | **Expected result**                                                                                                               |
| -------- | ------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| TS-16-A  | Delay a specialist's reply beyond 120 seconds.                                                    | At 120 seconds the system stops waiting and returns a degraded result with a warning and an escalation flag.                      |
| TS-16-B  | Make every draft fail QA and every hop slow, so the revision loop would run past 120 seconds.     | One deadline covers the whole request. It ends at 120 seconds with the same degraded result.                                      |
| TS-16-C  | Run at least five requests of each type: reporting, sentiment, forecast, declined, and escalated. | Latency and token cost are recorded for each, including requests that needed revision. Every request finishes within 120 seconds. |
| TS-16-D  | On the deployed system, send a question after services have scaled to zero.                       | A response arrives within 120 seconds. The cold-start latency is recorded.                                                        |

**Pass criteria:** No request exceeds the ceiling, and measurements exist for every request type.

**TS-17: Availability and graceful degradation**

**Covers:** NFR-4 | Level: Manual | Environment: Local | Status: Not yet built

Verifies that a failed component degrades the system cleanly. It never hangs and never returns an unverified answer.

| **Case** | **Input / steps**                                                                | **Expected result**                                                                                                                                                                                                                       |
| -------- | -------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| TS-17-A  | Check health and readiness on every service. Then make the database unreachable. | Every service reports healthy and ready. A service that cannot reach its database reports not ready.                                                                                                                                      |
| TS-17-B  | Stop each specialist in turn and ask a question for each domain.                 | The stopped domain returns a message naming the unavailable capability, with no hang. The other two domains still answer normally.                                                                                                        |
| TS-17-C  | Stop the QA agent and ask a question.                                            | The response is a degraded result with a warning and an escalation flag. It is never presented as verified.                                                                                                                               |
| TS-17-D  | Keep a specialist stopped and send repeated questions to it, then restart it.    | After a set number of consecutive failures the circuit breaker opens and calls fail immediately. After the cool-down one trial call is made, and once the specialist is back the breaker closes. Another service's breaker is unaffected. |

**Pass criteria**: All four cases show the expected result. The failure count and cool-down are recorded when the case is run.

**TS-18: Rate limits and scalability**

**Covers:** NFR-3 | Level: End-to-end, manual | Environment: Local, deployed | Status: Not yet built

Verifies behavior when the language model's limits are reached, and that services scale independently.

| **Case** | **Input / steps**                                                                                       | **Expected result**                                                                                              |
| -------- | ------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| TS-18-A  | Simulate a per-minute rate-limit response from the model provider.                                      | The system waits the stated delay within its bound and retries. The request then completes.                      |
| TS-18-B  | Simulate a daily quota exhausted response.                                                              | A clear "try again later" message is returned at once, with no silent failure and no retry loop.                 |
| TS-18-C  | On the deployed system, send several concurrent reporting questions while asking one forecast question. | The forecast question is answered correctly. The reporting service scales up, and the forecast service does not. |

**Pass criteria:** A and B behave as stated using recorded real provider error responses, and C shows independent scaling.

**TS-19: Synthetic dataset**

**Covers:** FR-18, NFR-5 | Level: Integration | Status: Not yet run

Verifies that the dataset is reproducible, contains the documented signals, satisfies its integrity rules, and contains no real personal data.

| **Case** | **Input / steps**                                                                          | **Expected result**                                                                                                                                                                                                                                                                                                        |
| -------- | ------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| TS-19-A  | Regenerate from the saved seed into an empty database and compare with the loaded dataset. | Identical: 20,230 requests, 2,067 incidents, 7,521 feedback responses, and matching row contents. No model API is called.                                                                                                                                                                                                  |
| TS-19-B  | Run the dataset's validation checks.                                                       | All pass. This includes annual growth near the designed 8%, the regional volume drop, the account drop, the surcharge window, and a sentiment mix within 1.5 points of each target.                                                                                                                                        |
| TS-19-C  | Check the integrity rules, and attempt invalid inserts.                                    | Every completed request has exactly one billing record, and no cancelled request has one. Every incident and feedback response resolves to a request, and every feedback response has a label. Credits never exceed invoices. The database refuses a rating of 6, a negative charge, and a request that is its own parent. |
| TS-19-D  | Inspect contact details.                                                                   | Every phone number is in the reserved 555-01xx range and every email uses example.com.                                                                                                                                                                                                                                     |

**Pass criteria:** All four cases show the expected result.

**TS-20:** **Web interface and decision-support transparency**

**Covers:** FR-19, NFR-5 | Level: Manual | Environment: Deployed | Status: Not yet built

Verifies that a user sees the answer together with how far it can be trusted: its QA status, any escalation flag, low-confidence sentiment results, and the system's stated limitations.

| **Case** | **Input / steps**                                                          | **Expected result**                                                                                                                                    |
| -------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| TS-20-A  | Enter a reporting question in the interface.                               | The answer is shown with its QA status and the as-of date.                                                                                             |
| TS-20-B  | Trigger a degraded result.                                                 | The interface shows the warning and escalation flag, and the answer is not displayed as verified.                                                      |
| TS-20-C  | Ask a sentiment question that includes comments flagged for review.        | The count flagged for human review is shown, and flagged results are not presented as certain.                                                         |
| TS-20-D  | Submit a question that is declined, needs clarification, or must be split. | The explanation is shown clearly. There is no blank screen or raw error.                                                                               |
| TS-20-E  | Open the interface.                                                        | It states that the data is synthetic and that the sentiment model was trained on synthetically written feedback, so it may not reflect real customers. |

**Pass criteria:** All five cases show the expected result.

## **Known Failures & Limitations**

The following were known at the date of writing, October 5, 2026.

| **Item**                                             | **Related scenario** | **Description**                                                                                                                                                                                                                                                                                                                                    |
| ---------------------------------------------------- | -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Ambiguous questions are force-routed (FR-03)         | TS-02                | In testing on five fresh ambiguous questions, the router recognized three and sent the other two to a best-fit specialist. The scenario's expected results stay at what the requirement demands. The attempted fix is not in use, because it recognized too few ambiguous questions on unseen data and over-flagged a clear question on seen data. |
| Logs may carry more than they should                 | TS-15-D              | Logs are known to include the router's model-written reasoning and unredacted error traces, which can repeat text the user typed. The case may fail until this is corrected.                                                                                                                                                                       |
| FR-10 is verified by lookup, not a repeated backtest | TS-10                | The requirement describes a backtest against held-out weeks. The backtest is run once, at model release, and QA checks each answer against the stored result. This is a difference in method and not a failure, and TS-10 is written to the method as built.                                                                                       |

**Limitations of the tests themselves.**

- All data is synthetic, so results show how well the system recovers known patterns. They do not show how it would perform on real data.
- The scenarios are pass/fail checks. Routing accuracy, sentiment precision and recall, forecast error against the baseline, and QA catch rate are measured separately.
- No throughput target is set, and latency is measured for a handful of concurrent users only.
- The system depends on a free-tier model whose limits and availability the project does not control, so cases that call it are run in batches across days.