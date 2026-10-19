# Risk Register — Agentic Service Operations Intelligence Platform

**Purpose:** Risks named early are risks that get managed instead of discovered. Review and update this file at every sprint boundary — in the same sitting as the sprint retro. On a solo project, this file is doing some of the job a second team member would normally do: forcing an honest look at what could go wrong before it does.

**How to use:**
- **Likelihood / Impact:** Low / Medium / High. Don't over-engineer this into a numeric score — the point is triage, not precision.
- **Status:** `Open` (not yet mitigated), `Mitigating` (in progress), `Monitoring` (mitigation in place, watching for recurrence), `Closed` (no longer applicable), `Realized` (it happened — note the outcome).
- **Review at every sprint boundary:** re-read the whole table, not just add to it. A risk that's been sitting at "Open" for three sprints with no action is itself worth a retro note.
- Add new risks as they surface — a register that only shrinks isn't being used honestly.

---

## Summary Table

| ID | Category | Risk | Likelihood | Impact | Status |
|---|---|---|---|---|---|
| R-01 | Process | Solo build — no peer review | High | Medium | Mitigating |
| R-02 | Budget | Runtime budget depends on unconfirmed Google AI credit coverage (credits ruled out 2026-09-22; exposure is now free-tier limits and paid spend) | Medium | High | Mitigating |
| R-03 | Deployment | Cloud Run build/deploy decoupling (recurred before) | High | Medium | Closed |
| R-04 | ML / Verification | Sentiment task has weak natural verifiability | Medium | High | Mitigating |
| R-05 | Cost / Technical | QA retry loop cost or latency runaway | Medium | Medium | Mitigating |
| R-06 | Schedule / Scope | A2A overhead consumes disproportionate solo dev time | Medium | Medium | Closed |
| R-07 | Data | Synthetic generator produces a degenerate distribution | Medium | High | Monitoring |
| R-08 | Compliance | Schema/data drifts toward resembling employer's real system | Low | High | Mitigating |
| R-09 | Academic | Course rubric diverges from the assumed deliverable plan | Medium | High | Monitoring |
| R-10 | Schedule | Sprint 6 buffer erodes from earlier slippage | Medium | High | Monitoring |
| R-11 | External / Budget | Vendor pricing or model access changes mid-project | Medium | Medium | Open |
| R-12 | Technical / External | MCP/A2A ecosystem churn breaks a dependency | Medium | Medium | Mitigating |
| R-13 | Data / ML | Generated comments don't match their requested sentiment | Medium | High | Mitigating |
| R-14 | Technical / Deployment | Environment parity: everything verified only on local Docker Postgres with a true superuser | Medium | Medium | Closed |
| R-15 | External / Technical | Provider capacity: free-tier "high demand" 503s on the orchestrator's model, the first hop of every request | Low | High | Realized |
| R-16 | Evaluation | Evaluation validity: small, partly non-blind development sets and run-to-run variance make measured differences possibly noise | High | Medium | Open |
| R-17 | Technical / Environment | Local environment memory exhaustion (WSL/Docker) | High | Medium | Open |
| R-18 | Verification / Evaluation | Misinterpreted questions pass as verified | Medium | High | Open |
| R-19 | Deployment / ML | The sentiment model weights have no path into a Cloud Run image, so `ops-sentiment` cannot start | High | Medium | Closed |
| R-20 | Technical / Deployment | Cloud SQL `max_connections` (60 on `db-f1-micro`) is exceeded by instance fan-out during a rollout | Low | Medium | Monitoring |
| R-21 | Budget / Availability | Paid balance runs out during a grading window | Medium | High | Open |

---

## Detail

### R-01 — Solo build, no peer review
**Description:** No second person to catch design blind spots, review code, or push back on a bad assumption before it's built on top of.
**Mitigation:** CI with real test coverage; eval harnesses (routing, forecast backtest, sentiment holdout, QA catch rate) substitute for a reviewer's judgment with measurable output instead; sprint retros are the deliberate moment to self-audit rather than assume things are fine.
**Review trigger:** Every sprint retro — explicitly ask "what would a reviewer have flagged this sprint?"

**Update 2026-09-25:** CI is live (GitHub Actions: ruff lint, the offline unit suite, and the live grants integration suite against a Postgres 16 service container, with `REQUIRE_INTEGRATION_DB=1` so a missing database fails rather than skips). The eval harnesses are still to be built. Status stays Open.

**Update 2026-09-25 (Sprint 1 boundary review):** CI is live; the eval harnesses are not built yet. The reviewer question is answered in the Sprint 1 retro (`sprint-log.md`): assumptions repeated until they read as requirements, and ADR headers that understated supersession. Status: Open → Mitigating.

**Update 2026-09-30 (Sprint 2 boundary review):** The reviewer question is answered in the Sprint 2 retro (`sprint-log.md`): tests built from the author's assumptions passed while the code was wrong, and assistant-written instructions asserted repo state without checking it. The routing eval harness now exists (`evals/routing/run_seed.py`, three runs per evaluation, ADR-054). Status stays Mitigating.

**Update 2026-10-10 (Sprint 4 boundary review):** Reviewed. The reviewer question is answered in the Sprint 4 retro: QA was first built to accept every answer where §6 was silent (L-72), and that was caught at the owner's review, not by CI or process. Fault injection and the owner's own faults now stand in for part of a reviewer's judgment, and the owner's faults found what the assistant's did not (4a, 4b, 2). Status stays Mitigating.

**Update 2026-10-14 (Sprint 5 boundary review, Z1; owner-decided 2026-10-14; assistant-drafted):** Reviewed. The reviewer question is answered in the Sprint 5 retro: state checks caught wrong assumptions in prompts five times before damage. A read-only audit on 2026-10-14 then found 11 contradictions and 12 stale statements across the records, which is the kind of finding a second reviewer makes and evidence that the records drift between sprint boundaries. Status stays Mitigating.

### R-02 — Runtime budget depends on unconfirmed credit coverage
**Description:** The cost plan assumes Google AI student credits cover Gemini runtime inference for all five agents across 12 weeks. Coverage and expiry haven't been confirmed.
**Mitigation:** Confirm in Sprint 1 — this is a named open item, not an assumption to defer. `packages/llm/` keeps every agent provider-agnostic, so a swap to another provider is a config change if credits fall short.
**Update 2026-09-22 (ADR-029):** Student credits confirmed not available. Development inference moved to the Gemini API free tier with Flash-Lite defaults, so credit coverage is no longer the exposure. What remains: free-tier rate limits (429 backoff required in `packages/llm/`) and any paid Sprint 5 eval spend, which runs in a separate spend-capped project. Free-tier limits are now confirmed in AI Studio (2026-09-22): Flash-Lite 15 RPM / 250K TPM / 500 RPD, Flash models 20 RPD, and no free-tier quota for Pro models. The remaining exposure is eval volume: a full routing eval run (300–700 requests) can exceed the 500 RPD Flash-Lite cap, so Sprint 5 evals must be split across days or run on a paid, spend-capped project. If the paid route is taken, that project's cost is not yet included in the budget estimate, which so far covers only the ~$20–30 Pro-for-QA test. Pricing it is a Sprint 4 planning item.
**Review trigger:** Sprint 1 close-out. Re-check if GCP budget alerts fire.

**Update 2026-09-24 (ADR-041):** Paid spend now exists: remaining Flash-Lite corpus generation runs on a separate paid project (about $2 at list prices), bounded by a $10 project budget alert, the $50/$80 GCP budget alerts, and a hard per-session request cap in `build_corpus.py`.

**Update 2026-09-25:** Paid spend is bounded by a code-enforced per-session request cap in `build_corpus.py`, a $5 prepaid balance on the paid project with auto-reload off, and budget alerts at $10 (project) and $50/$80 (billing account). Corpus generation cost about $1.40 (estimate from list prices, not billing data). Status stays Mitigating.

**Update 2026-09-25 (Sprint 1 boundary review):** No budget alert has fired; about $1.40 spent. Next trigger: the Sprint 4 item that prices a full routing eval run (two LLM calls per request, ADR-046). Status stays Mitigating.

**Update 2026-09-30 (Sprint 2 boundary review):** Paid spend this sprint, computed from the eval result files in `evals/results/`: $0.0370 at list prices, from the two `gemini-3.7-flash` routing runs on the paid key (seed_v1 on 2026-09-26, $0.0201; routing_v1 on 2026-09-30, $0.0169). Every other run used the free key. This is a list-price estimate, not billing data, and it covers only calls recorded in the eval result files. No cap was hit and no budget alert fired. Status stays Mitigating.

**Update 2026-10-10 (Sprint 4 boundary review):** Reviewed. No paid model call was made in Sprint 4: the deploy window, the interpretation gate, the end-to-end runs and the loop checks used the free key. GCP billing for 2026-10-01 to 10-09 was $0.29 gross and $0.08 net (owner, Billing), covering the deploy window and storage. The Sprint 4 item that prices a full routing eval run is done: about $0.30 for 150 end-to-end requests at paid Flash-Lite list prices, with the Pro-for-QA test's ~$20-30 as a ceiling (architecture §9; official pricing page read 2026-10-10). Status stays Mitigating.

**Update 2026-10-13 (Sprint 5 close):** Paid spend this sprint, as list-price estimates (L-71): W $0.2719 (ADR-103, `evals/results/sprint5_w_ledger.json`) and X $0.1727 for 186 requests (`sprint5_x_ledger.json`). V3 about $0.0015 (3 paid `verify.py` calls, `docs/deploy-window-log.md` (2026-10-12/13)); the three smoke questions are not itemised. Owner-reported in the Prompt Y brief, not in a file in the repo: Q about $0.16. The prepaid balance is about $2.9 after X (the owner's figure in the brief; it is an estimate from list-price spend, not read from Billing, and ADR-104 recorded the budget as not re-verified). Auto-reload is off. The paid key is now the deployed system's spend path (ADR-104, ADR-105), bounded by the gateway's 50-question daily cap (about $0.35 a day at the cap), not by the per-process caps (L-93). The balance is below the $5 minimum ADR-105 sets before a window, so a top-up is due before the first one (R-21). Status stays Mitigating.

### R-03 — Cloud Run build/deploy decoupling
**Description:** A prior academic project hit successful Cloud Builds that didn't produce active Cloud Run revisions — a decoupled build/deploy pipeline. Same deployment target, same failure mode plausible.
**Mitigation:** Wire an explicit Cloud Build trigger → deploy step rather than an image push alone; verify revision promotion immediately on the first Sprint 5 deploy rather than waiting until later to check.
**Review trigger:** First deploy attempt in Sprint 5 — don't wait for the retro if this recurs, it blocks the sprint goal directly.

**Update 2026-09-25 (Sprint 1 boundary review):** Mitigation adds the Sprint 4 reporting-slice deploy (ADR-045, 2026-11-02 to 11-04) with a post-deploy check that the serving revision is the one just built and holds 100% of traffic. Review trigger moves to that deploy; its stop rule records R-03 as realised if the revision is not verified serving by end of 11-04. Likelihood normalised Medium-High → High. Status stays Open.

**Update 2026-09-30 (Sprint 2 boundary review):** Builds are now reproducible: CI and the service images install exactly what `uv.lock` pins (ADR-047). The trigger is still the Sprint 4 slice deploy (ADR-045). Status stays Open.

**Update 2026-10-05 (ADR-078):** The slice deploy is pulled forward to 2026-10-12 to 10-14, with the stop rule at the end of 10-14. The 2026-11-02 to 11-04 dates above are superseded; the post-deploy check and the consequence of the stop rule are unchanged. Status stays Open.

**Update 2026-10-08 (deploy window, ADR-084):** **Not realised.** The pipeline built, deployed and verified its own revision on day one: build 5a181fa1 (commit `1a3f1e3`) produced `ops-orchestrator-00004-c6f` and `ops-reporting-00004-5kz`, each at 100% traffic, and its `verify.py` step passed every check. The failure mode this risk names, a successful build with no active revision, did not occur. Two nearby problems did: a merge to `main` while the database was stopped produced a revision that failed its readiness probe (no traffic moved, L-65), and the pipeline deploys before it verifies, so a revision that fails verification keeps serving (L-64). Status: Open to Monitoring; it closes after the Sprint 5 deploy of all services.

**Update 2026-10-10 (Sprint 4 boundary review):** Not realised in the reporting-slice deploy (2026-10-08; see that update). Monitoring until the Sprint 5 deploy of every service, which re-runs the revision check; the trigger is disabled between windows (ADR-083). Status stays Monitoring.

**Update 2026-10-13 (Sprint 5 close):** **Not realised; closed.** The Sprint 5 deploy of all six services ran one service at a time, and traffic was verified at 100% on every service (step 5e and the serving-revisions check, `docs/deploy-window-log.md` (2026-10-12/13)); the one-at-a-time order is owner-reported in the Prompt Y brief. `evals/results/sprint5_x.md` records six revisions identical at the start and the end of the X run. The 2026-10-08 update set the close at this deploy. Reopen trigger: a build that succeeds with no serving revision, or the build trigger enabled again (Sprint 6) without the revision check. Status: Monitoring to Closed.

### R-04 — Sentiment task has weak natural verifiability
**Description:** Unlike reporting (deterministic) or forecasting (standard backtest metrics), sentiment has no natural ground truth. A QA check that just re-runs the same model is circular and proves nothing.
**Mitigation:** `sentiment_labels` holdout the sentiment agent never reads; the `rating` field on `service_feedback` gives QA a second, independent cross-check signal. Both already designed in — this is why status is "Mitigating" rather than "Open." Both are now enforced by database grant, not convention: the sentiment role has no grant on `sentiment_labels`, and since ADR-027 its `service_feedback` grant is column-level and excludes `rating`, so the second signal is independent by construction. `tests/integration/test_access_matrix_grants.py` asserts both against the live database.
**Review trigger:** Sprint 4, when the QA agent's sentiment-verification path is actually built and tested against real generated data.

**Update 2026-09-25 (Sprint 1 boundary review):** Reviewed, no change. Impact normalised Medium-High → High.

**Update 2026-09-30 (Sprint 2 boundary review):** Reviewed, no change.

**Update 2026-10-01 (ADR-063):** Gold labels are now held only by offline roles: `app_eval` (validation and evaluation) and `app_train` (training). `app_qa` can no longer read `sentiment_labels` or `generation_parameters`, so the runtime QA check cannot lean on gold labels; at answer time it rests on the rating cross-check (ADR-055), whose optimism on this data is L-24. Training is also barred from `rating` by grant, so the cross-check stays independent of the trained model too. Status stays Mitigating.

**Update 2026-10-10 (ADR-091, fault injection):** The sentiment path was measured against injected faults. Twelve assistant-drafted sentiment faults were caught 76 of 76 (counts, shares, flags, trend, quotes, coverage, text), and the owner's sarcasm fault (rating contradictions at 20-33% of the covered set) was caught 20 of 20 by the rating cross-check. The cross-check is the only independent signal on the label itself, and its sensitivity is now known: against the pre-registered rule it caught 0 of 10 at 0.5% and 1% contradictions, 1 of 10 at 2%, 8 of 10 at 4% and 10 of 10 at 8% (answers of 122 to 1,055 comments), agreeing with the rule in all 50 cases. So a modest shift in sentiment that leaves ratings roughly aligned is not caught, by construction (L-24, ADR-087). The catalogue is not blind (L-85). Status stays Mitigating.

**Update 2026-10-10 (Sprint 4 boundary review):** Confirmed. The 2026-10-10 update above (ADR-091: sentiment faults caught 76 of 76, the rating rule's sensitivity measured and matching its pre-registration, the owner's sarcasm fault caught 20 of 20) stands, and ADR-092 changed nothing in it. The weakness the register named is still there: a shift the ratings do not show is not caught, by construction (L-24). Status stays Mitigating.

**Update 2026-10-14 (Sprint 5 boundary review, Z1; owner-decided 2026-10-14; assistant-drafted):** Reviewed. QA measurement 3 caught 223 of 223 injected faults, owner fault 2 6 of 6, which is "evidence the fix works, not a catch rate" (ADR-092, L-85). Consistent misparses are still caught 0 of 71 and the interpretation check ships advisory (ADR-102, L-92). Deployed sentiment reads stored predictions (ADR-100); on the deployed system the counts, shares and flagged counts of G04, G20 and G21 equal the oracle. Status stays Mitigating.

### R-05 — QA retry loop cost or latency runaway
**Description:** Multi-agent systems with a verify-and-revise loop can fan out token usage and wall-clock time quickly if unbounded.
**Mitigation:** Bounded at 2 retries with escalation on final failure (ADR-022); per-run cost caps and model tiering already specified in the budget plan.
**Review trigger:** Sprint 4, once the loop is live and real cost/latency numbers exist to check against the plan.
**Update 2026-09-22 (ADR-034):** Latency is also bounded by a 120-second end-to-end ceiling, after which the request returns a degraded result with an escalation flag. Check in Sprint 5's first deploy whether cold starts alone approach the ceiling.

**Update 2026-09-25 (Sprint 1 boundary review):** Reviewed, no change. Likelihood normalised Low-Medium → Medium.

**Update 2026-09-30 (Sprint 2 boundary review):** Reviewed, no change.

**Update 2026-10-10 (ADR-091, loop demonstration):** A figures failure injected through a test-only proxy ended the request at the first verdict: one reporting task, no retry, the degraded result at list price $0.000948 (routing and parse; the interpretation call is skipped on a figures failure). The same question verified cost $0.001604 against the $0.02 cap. The interpretation retry, the path that multiplies calls, still cannot run because the check is advisory (L-74), so the loop's worst case is not exercised by live traffic. Status stays Mitigating; the trigger is when `QA_INTERP_MODE=enforce` is ever turned on.

**Update 2026-10-10 (Sprint 4 boundary review):** Confirmed. The 2026-10-10 update above stands. The interpretation re-ask, the path that multiplies calls, is built and tested but cannot run live while the check is advisory (L-74), so the worst case is still untested on real traffic; the trigger is the day `QA_INTERP_MODE=enforce` is turned on. Status stays Mitigating.

**Update 2026-10-12 (Prompt U, deploy readiness):** the cold-start measurement is planned in `deploy/RUNBOOK_V.md` step 12: one `/healthz` per service in chain order after 15 minutes idle, then one real question after another 15 minutes, against the 120 s deadline (ADR-034). The chain is now six services deep (gateway, orchestrator, a specialist, QA), each at `min_instances=0`; the sentiment sidecar's start-up hash of 438 MB cannot be measured until R-19 is decided. Nothing has been measured yet.

**Update 2026-10-13 (Sprint 5 close):** The cold-start chain was measured: the cold-start question took 55.87 s in the browser (54.47 s at the gateway) after 15 minutes idle, against the 120 s ceiling (ADR-034): new instances at the gateway, orchestrator, reporting (about 20 s start) and QA (about 14 s start), each model call about 1.5 s (`docs/deploy-window-log.md` (2026-10-12/13)). The second idle wait is a Sprint 6 backlog item. Warm latency in the X runs: golden median 3.93 s, max 5.9 s; routing per-run median 3.5 to 3.8 s, p95 5.1 to 17.6 s; nothing over 120 s. The retry loop's worst case is still not exercised on live traffic: the interpretation check stays advisory (ADR-102). Status stays Mitigating.

**Update 2026-10-15 (S6-D2; Owner-decided 2026-10-15; assistant-drafted.):** owner verification session 1 read the cold start on the sentiment and forecast paths (`evals/results/session1/2026-10-15/summary.md`, ADR-110). Sentiment **61 s** in the browser on the first reading, where the gateway hop was not cold (the owner reloaded the page about 3 minutes earlier), then **30.64 s** on the second idle wait with all four hops cold. Forecast **46 s**, all four hops cold. Reporting **29 s** at TS-20-A (the reporting path was cold). All are under the 120 s ceiling (ADR-034). Status unchanged.

### R-06 — A2A overhead consumes disproportionate solo dev time
**Description:** A2A's Agent Cards and task-lifecycle machinery are more plumbing than a single-codebase system strictly needs. Solo, on a fixed timeline, that overhead is a real opportunity cost.
**Mitigation:** Sprint 2 is deliberately the proof sprint for this exact risk — if the A2A path is disproportionately slow to stand up, that's the signal to reconsider before three more agents are built on top of it. No fallback plan currently drafted; if this risk is realized, the honest move is a documented scope conversation, not silent workarounds.
**Review trigger:** Sprint 2 retro, explicitly.

**Update 2026-09-25 (Sprint 1 boundary review):** Checkpoints: the skeleton hop (MCP tool → reporting agent → orchestrator over A2A, no LLM) working by 2026-10-02, or hold the scope conversation that day; an LLM-classified question answered end to end in docker-compose by 2026-10-07. Hours are logged per layer. Fallback: if the SDK is the friction, implement the small protocol surface actually used (the Agent Card endpoint plus `message/send`) directly on FastAPI/httpx. Collapsing to in-process calls would break ADR-001 and ADR-011; that is the documented scope conversation, not a silent workaround. Status stays Open.

**Update 2026-09-25 (walking skeleton):** The skeleton checkpoint is met ahead of 2026-10-02: orchestrator → A2A → reporting agent → MCP → Postgres runs in docker-compose with no LLM, and the e2e test passes. SDK friction was low, and the fallback was not needed. The friction points were protobuf float coercion of A2A data parts; the `message/send` → `SendMessage` rename in A2A v1.0; and the MCP 2.x API changes (`FastMCP` → `MCPServer`, the SDK replacing the root log handler, and an allowed-hosts list needed on the Docker network). The second checkpoint, an LLM-classified question answered end to end in docker-compose by 2026-10-07, stands. Status stays Open.

**Update 2026-09-26 (checkpoint 2):** Met on 2026-09-26, ahead of 2026-10-07. An LLM-routed, LLM-parsed question is answered end to end in docker-compose: all six checkpoint e2e assertions passed (routing to reporting, "last month" parsed to July 2026 per ADR-050, figures equal to independent SQL as `app_qa`, the trace id in all three services, the out-of-scope decline, and the sentiment "not available yet" answer). The sentiment assertion passed on a rerun after a provider 503 (R-15). The first run had failed on a configuration error, not on A2A: `gemini-3.7-flash` rejected thinking level `minimal` (ADR-049). Status stays Open until the Sprint 2 retro, which reviews this risk explicitly.

**Update 2026-09-30 (Sprint 2 boundary review):** Did not materialise. Status: Open → Closed. Evidence: both checkpoints were met early (the skeleton hop 2026-09-25 against 10-02; the LLM-classified question 2026-09-26 against 10-07), and SDK friction was low: protobuf float coercion of A2A data parts, the `message/send` → `SendMessage` rename, and the MCP 2.x API changes. The SDK fallback was not needed. Hours per layer were planned but not logged, so there is no time-per-layer figure behind "low"; the evidence is the checkpoint dates. Reopen trigger: wiring A2A into the sentiment or forecast agent takes more than one day of plumbing.

**Update 2026-10-10 (Sprint 4 boundary review):** Reviewed. The QA agent, the verification loop and the fault-injection proxy were all built over A2A in five days with no protocol friction recorded. Stays Closed; the reopen trigger has not fired.

### R-07 — Synthetic generator produces a degenerate distribution
**Description:** Random or careless generation could produce a sentiment mix that's not realistic, a forecast signal that isn't recoverable, or an incident rate that doesn't resemble a real business — quietly invalidating every downstream metric.
**Mitigation:** Explicit validation step planned for Sprint 1 (data-dictionary.md §8 constraints and invariants); target distributions locked in advance (ADR-018, ADR-019, ADR-021) rather than left to chance.
**Review trigger:** Immediately after first generation run, Sprint 1 — before any agent code is built against the data.

**Update 2026-09-25:** Still Open until `validate.py` runs against generated data. The feedback corpus is complete (13,184 comments, q99 rule); `generate.py` is in progress on `feat/generate`.

**Update 2026-09-25 (dataset loaded):** The dataset is generated and loaded into local Postgres (20,230 requests; sentiment mix, incident rate and anomalies land on target in the dry run). `validate.py` (signal recovery) is next. Status stays Open until it passes.

**Update 2026-09-25 (validate.py):** The review trigger is met: `validate.py` passed 66 of 66 checks against the loaded database, with truth read from `generation_parameters`. Headline results: sentiment mix 50.2/22.4/19.6/7.8; incidents on 10.2% of completed requests, missed_sla 24.4% of incidents; recovered growth 8.5% (designed 8%); seasonal peak-to-trough 0.39 against 0.42 designed in the same K=3 basis (the raw weekly design is 0.50, and three harmonics cannot follow the two-week December trough); residual sd 11.7% (designed effective ~10.6%); regional drop z 3.53; account drop 93% at account level; severity->sentiment, SLA->incident and rating->sentiment couplings all consistent with their designs (p >= 0.07). Status -> Monitoring: re-run `validate.py` after any regeneration.

**Update 2026-09-25 (Sprint 1 boundary review):** Reviewed, no change.

**Update 2026-09-30 (Sprint 2 boundary review):** Only `locations` changed, gaining the `region` column (ADR-051). The dataset hash changed, and `locations` with `region` removed hashes identically before and after, as recorded in ADR-051. `validate.py` passed 67/67 after the change (the previous 66 plus the region check). The feedback corpus is unaffected. Status stays Monitoring.

**Update 2026-10-10 (Sprint 4 boundary review):** Reviewed, no change. Sprint 4 queried the same 20,230-request dataset throughout, and on Cloud SQL the 67 validation checks ran unchanged with the same corpus hash, seed and row counts (2026-10-08). Status stays Monitoring.

**Update 2026-10-14 (Sprint 5 boundary review, Z1; owner-decided 2026-10-14; assistant-drafted):** Reviewed, no change. Sprint 5 changed nothing under `data/generator`, `data/migrations` or `packages/db_models` (git history since 2026-10-10). The deployed `sentiment_predictions` equals the local table in rows and content hashes (`evals/results/sprint5_x/data_parity_cloud.json`). Status stays Monitoring.

### R-08 — Schema or data drifts toward resembling employer's real system
**Description:** The original draft schema showed signs of being modeled too closely on a real production system. The underlying pull toward "use what I already know" doesn't disappear just because the initial fields were corrected.
**Mitigation:** ADR-012 and ADR-013 establish the discipline; any new field added later should be sourced from general field-service domain principles, checked against this standard before being added, not copied from familiarity.
**Review trigger:** Any time a new table or field is proposed — a standing check, not a one-time fix.

**Update 2026-09-25 (Sprint 1 boundary review):** Sprint 1's new fields (`sentiment_labels.hard_case_type`, `sentiment_labels.corpus_id`, the `world` and `feedback` `param_group` values) are generator internals, not modelled on any real system. Check passes; status stays Mitigating.

**Update 2026-09-30 (Sprint 2 boundary review):** Sprint 2's new field, `locations.region` (ADR-051), is a generic geography: the customer site's region, derived from its state by one committed mapping. Check passes; status stays Mitigating.

**Update 2026-10-10 (Sprint 4 boundary review):** Reviewed, no change. The fault catalogue's scenarios (an East region, a firmware rollout) were translated to the synthetic schema and name nothing from the employer's system. Status stays Mitigating.

**Update 2026-10-14 (Sprint 5 boundary review, Z1; owner-decided 2026-10-14; assistant-drafted):** Reviewed, no change. Sprint 5 added no table, column or field (nothing changed under `data/migrations` or `packages/db_models` since 2026-10-10); the invite store is a Secret Manager document, and the evaluation sets are generated synthetic items. Status stays Mitigating.

### R-09 — Course rubric diverges from the assumed deliverable plan
**Description:** The academic deliverable sequencing in `architecture.md` §10 is a reasonable guess at typical capstone requirements, not a confirmed match to the actual rubric.
**Mitigation:** Reconcile explicitly against the real rubric — flagged as an open item since the plan was first drafted and still unresolved.
**Review trigger:** Should be closed in Sprint 1. If still open at the Sprint 2 retro, treat that as a process failure worth naming. Added 2026-09-25: each deliverable's rubric is checked when drafting starts.

**Update 2026-09-25:** Still open at the end of Sprint 1. Per this entry's review trigger, if it is still open at the Sprint 2 retro, that is a process failure to name there.

**Update 2026-09-25:** The actual deliverables for weeks 1-2 are now known — Proposal/Business Case, Detailed Requirements Analysis, and weekly status reports — and they differ from the assumed plan in `architecture.md` §10 and the sprint log. Partly realised. Reconciling the full milestone plan is the next step, after the academic documents are reviewed. Weekly status reports are a recurring deliverable the plan must budget. Status: Mitigating.

**Update 2026-09-25 (calendar reconciled):** The actual deliverable calendar is now known and mapped to sprints in `architecture.md` §10 and `sprint-log.md`: `01` (due 09-27) and `02` (due 10-04) complete; `03` and `04` due 10-18 (Sprint 3); `05` due 11-01 and `06` due 11-08 (Sprint 4); weekly status reports through 11-22; final product due 12-05. The remaining exposure is per-deliverable rubric content, which is not yet known, and the schedule conflicts flagged for Sprint 2 planning (`sprint-log.md`): `06` due before the first deployment and before the Sprint 6 runbook work; `05` due before the eval runs, with the golden set needed by Sprint 4; `03` and `04` both due mid-Sprint 3; and whether a separate project charter is due. Status: Mitigating → Monitoring.

**Update 2026-09-25 (Sprint 1 boundary review):** The two remaining planning assumptions are resolved from the course materials: there is no charter deliverable, and there is no final paper (ADR-044). The schedule conflicts are resolved in Sprint 2 planning (ADR-045 and the Sprint 3 drafting dates). The remaining exposure is per-deliverable rubric content, checked when `03` drafting starts (2026-10-08). Impact normalised Medium-High → High. Status stays Monitoring.

**Update 2026-09-30 (Sprint 2 boundary review):** `03` and `04` are drafted (not submitted). Whether their rubrics were checked: Eric to confirm. Status stays Monitoring.

**Update 2026-09-30 (rubric checks):** Eric confirms he checked the rubrics for `03` and `04` before drafting them, so both rubric checks are done. The remaining exposure is the rubrics for `05` and `06`, checked when their drafting starts. Status stays Monitoring.

**Update 2026-10-10 (Sprint 4 boundary review):** Reviewed. The course's dates are unchanged. ADR-093 moves `05` (due 11-01) into Sprint 6's first week and `06` (due 11-08) onto its last day, and the weekly reports still run through 11-22. `03`'s calendar now differs from the plan twice (ADR-082, ADR-093); the divergence is on the list for the evaluation report. Status stays Monitoring.

**Update 2026-10-14 (Sprint 5 boundary review, Z1; owner-decided 2026-10-14; assistant-drafted):** Reviewed. `05` is marked "(Assignment complete)" (`05:9`, dating from 2026-10-05) but is held, not submitted, and will be revised with Sprint 5 evidence before 11-01 (owner, D1). `06` is an 8-line stub marked "Assignment incomplete" (`06:9`): no outline, and the repo holds no definition of "production support" beyond the file name; its outline waits on the assignment text (owner to supply). The 2026-09-30 line said the rubrics for `05` and `06` would be checked when their drafting starts; the repo has no record that the `05` rubric was checked, and `06` drafting has not started. Owner to confirm the `05` check, and to make `06`'s when the text arrives. Status stays Monitoring.

**Update 2026-10-18 (S6-D3; owner-decided 2026-10-18; assistant-drafted):** The assignment text has arrived and supersedes the 2026-10-14 line's description of `06` as a stub waiting on it. It has no rubric beyond four required parts, plus a note that it be written professionally: an application description, standard operating procedures, troubleshooting, and disaster recovery and clean restart. `06` is drafted in Word as version 1.3, dated 2026-10-18, about 29 pages; it is not submitted (due 2026-11-08), and the Markdown copy is committed to `docs/academic/` only after submission. Status stays Monitoring.

### R-10 — Sprint 6 buffer erodes from earlier slippage
**Description:** Sprint 6 is the only planned buffer in a 12-week solo timeline. Without a second person creating schedule pressure, slippage in Sprints 1–5 tends to get quietly absorbed rather than confronted.
**Mitigation:** Treat any missed sprint goal as an immediate scope conversation at that sprint's retro, not something to "catch up on later." Scope expansion is only considered if genuinely ahead, per the working agreement.
**Review trigger:** Every sprint retro — explicitly compare actual progress against the plan, not just against what felt productive.

**Update 2026-09-25:** The Sprint 1 goal was missed: the generator carries into Sprint 2, which is also the highest-risk sprint (first vertical slice through A2A and MCP). Kept Open; the Sprint 1 retro decides whether this counts as realised.

**Update 2026-09-25 (goal met):** The Sprint 1 goal was met on 2026-09-25, inside the sprint; the remaining Sprint 1 items (CI, the Alembic ruff hook) are being finished in Sprint 1 rather than carried over. This supersedes the earlier same-day note that the goal was missed. Status stays Open: the buffer risk applies to every sprint.

**Update 2026-09-25 (Sprint 3 academic load):** With the calendar reconciled, Sprint 3 carries two academic deliverables due the same day (`03` Planning & Management and `04` Design & Solution Architecture, both 2026-10-18) on top of the heaviest engineering sprint after Sprint 2 (MCP servers #2 and #3, the sentiment and forecast agents, and three-way routing). Sprint 4 then carries `05` and `06`. Any Sprint 2 slip lands directly on that load. Status stays Open.

**Update 2026-09-25 (Sprint 1 boundary review):** Likelihood Medium → High. Sprint 1's goal was met, but Sprint 3 gained the golden set, the labelled routing set, `security-model.md` and `05` drafting, and Sprint 4 gains the reporting-slice deploy (ADR-045). If Sprint 4 overflows, the fault-injection harness carries to Sprint 5 first. Status stays Open.

**Update 2026-09-30 (Sprint 2 boundary review):** Likelihood High → Medium. Sprint 2's engineering finished 2026-09-30, eleven days before the sprint's end, and two Sprint 3 items moved earlier: `04` is drafted and the labelled routing set is done. Sprint 3 still carries two agents (sentiment and forecast, with MCP servers #2 and #3), the golden set and `05`, plus the two items deferred from Sprint 2. Status stays Open.

**Update 2026-10-10 (Sprint 4 boundary review):** The buffer has grown, not eroded. Sprint 4's goal was met on day 5 of a planned 20 days (2026-10-06 to 10-25), ADR-093 pulls Sprints 5 and 6 forward, and the buffer goes from 2026-11-23 to 12-05 (13 days) to 2026-11-09 to 12-05 (27 days). The Sprint 5 workload is unchanged and heavy (the UI, the full deploy, the held-out routing eval, owner writing time), so the review trigger stays at every retro. Status: Open to Monitoring.

**Update 2026-10-14 (Sprint 5 boundary review, Z1; owner-decided 2026-10-14; assistant-drafted):** Reviewed. Sprint 5 closed 2026-10-13 against a plan of 2026-10-25 (ADR-093), returning 12 days. The scope decision moves from "the Sprint 5 close" (ADR-093, `architecture.md` §10, this entry's review trigger) to **the Sprint 6 close**, with Sprint 6.5 if any about 2026-11-09 to 11-29 (ADR-106). Sprint 6 itself now carries the `05` revision (11-01), `06` (11-08, its last day), observability, the Z2 fixes and Window A (2026-10-31 to 11-09, ADR-107), so slippage lands on 6.5 first. Status stays Monitoring.

**Update 2026-10-15 (Owner-decided 2026-10-15; assistant-drafted.):** The calendar moves again (ADR-109). Sprint 6 now runs 2026-10-15 to 10-25 and the buffer is 10-26 to 12-05. The scope decision (ADR-106) stays at the Sprint 6 close, now 10-25, and Sprint 6.5 if any starts 10-26 (was about 11-09) and runs to about 11-29. 6.5 can therefore start before `05` (11-01) and `06` (11-08) are submitted, so no 6.5 change is deployed before `06` is submitted. "Demo rehearsed" in the Sprint 6 goal is not expected inside the sprint; it is a buffer target (11-29). Status stays Monitoring.

### R-11 — Vendor pricing or model access changes mid-project
**Description:** Gemini pricing, free-tier rate limits, or model availability could change over a 12-week window in ways that affect the budget plan (see ADR-029).
**Mitigation:** Provider-agnostic LLM interface (ADR-006) keeps a provider swap mechanically cheap; GCP budget alerts at $50/$80 serve as an early warning regardless of root cause.
**Review trigger:** Any GCP budget alert firing; otherwise passive monitoring.

**Update 2026-09-25 (Sprint 1 boundary review):** Reviewed, no change; no alert has fired. Likelihood normalised Low-Medium → Medium.

**Update 2026-09-30 (Sprint 2 boundary review):** Reviewed, no change; no alert has fired.

**Update 2026-09-30 (free-tier limits):** The Gemini free-tier limits in use (ADR-029: Flash-Lite 15 RPM / 250K TPM / 500 RPD; Flash models 5 RPM / 20 RPD; no free Pro quota) were last verified in AI Studio on 2026-09-22. Re-verify them before any deliverable that states them.

**Update 2026-10-10 (Sprint 4 boundary review):** Reviewed. The official pricing page was read on 2026-10-10: paid Flash-Lite $0.30 input and $2.50 output per 1M tokens, which is what the client's logged costs use, so no change. The free-tier limits (ADR-029) were not re-verified in AI Studio this sprint and must be before any deliverable states them. No budget alert has fired. Status stays Open.

**Update 2026-10-14 (Sprint 5 boundary review, Z1; owner-decided 2026-10-14; assistant-drafted):** Reviewed. The deployed system runs on the paid key (ADR-104) after the free tier failed on 2026-10-13 (R-15). The pricing read on 2026-10-10 is unchanged in the records, and the logged cost uses it (L-71). Sprint 5's paid use is about $0.61 in list-price estimates (`sprint-log.md`, Sprint 5 close). **The free-tier limits were still not re-verified**, and `05` states the 500-a-day limit (`05:102`, `05:567`): re-verify them, or reword them as "paid key in deployment (ADR-104)" (owner item for the `05` revision). Status stays Open.

### R-12 — MCP/A2A ecosystem churn breaks a dependency
**Description:** Both protocols are new and moving fast — MCP had its largest spec revision to date in July 2026. An SDK update mid-project could introduce breaking changes.
**Mitigation:** Pin SDK versions at project start; don't chase spec updates mid-build. The project targets the 2026-07-28 MCP spec and A2A v1.0 as documented in `architecture.md` §3 — treat that as fixed unless a specific reason forces an upgrade.
**Review trigger:** Only if a dependency update is being considered — otherwise not time-based.

**Update 2026-09-25 (Sprint 1 boundary review):** Fires in Sprint 2, when the MCP and A2A SDKs are first added: pin exact versions and record them, and confirm the spec targets. Status: Open → Mitigating once pinned.

**Update 2026-09-25 (walking skeleton):** Pinned exactly: `mcp==2.2.0` and `a2a-sdk==1.1.5`. Both spec targets are confirmed from the installed packages and the release notes: the MCP SDK's `LATEST_PROTOCOL_VERSION` is `2026-07-28`, observed as the negotiated version, and the A2A SDK's `PROTOCOL_VERSION_CURRENT` is `1.0`. Evidence and the A2A subset used are in ADR-047. One naming change from the planning docs: v1.0's JSON-RPC method is `SendMessage`, where `message/send` is the v0.3 name. Every other dependency is pinned by `uv.lock`, which CI and the service images install from (ADR-047). Status: Open → Mitigating.

**Update 2026-09-30 (Sprint 2 boundary review):** Both SDKs stay pinned at those versions, and the lock file covers everything else. Status stays Mitigating.

**Update 2026-10-10 (Sprint 4 boundary review):** Reviewed. `mcp==2.2.0` and `a2a-sdk==1.1.5` are unchanged; the SDK's DEBUG logging of a bearer token (L-63) was handled in our code, not by an upgrade. Status stays Mitigating.

**Update 2026-10-14 (Sprint 5 boundary review, Z1; owner-decided 2026-10-14; assistant-drafted):** Reviewed. `mcp==2.2.0` and `a2a-sdk==1.1.5` are unchanged (read in the services' `pyproject.toml`, 2026-10-14); `uv.lock` changed in Sprint 5 for the gateway and the stored-only sentiment image, and neither changed those pins. The web pin is Next.js 16.3.8; the bump for the 2026-10-14 release is a Sprint 6 backlog item (gateway-only redeploy). Status stays Mitigating.

### R-13 — Generated comments don't match their requested sentiment
**Description:** `feedback_text` is LLM-generated to a requested label (ADR-030), and `sentiment_labels.true_sentiment` records that request, not a verified reading of the text. Comments that drift from their label would make the sentiment model's accuracy look worse than it is — the model gets marked wrong for reading the text correctly. Hard cases can fail the other way: sarcasm an LLM writes on request is often obvious, so "hard" comments may be easier than labeled and inflate hard-case accuracy.
**Mitigation:** Sampled label validation in `validate.py` before the corpus is accepted, plus exact and near-duplicate rejection so no comment spans the training and holdout splits.
**Review trigger:** Corpus generation in Sprint 1.

**Update 2026-09-23 (ADR-036):** The bake-off confirmed label drift for neutral: the generator wrote neutral as intended only about half the time, and a flat report of a working fix read as satisfied to both the human reviewer and the judge. Mitigation: a Gemma 4 judge labels every comment, and plain comments whose judge label differs from the intended one are rejected and replaced from spares; a blind, stratified review of ~200 comments follows. Hard cases (sarcastic, implicit) are not judge-filtered, so filtering cannot inflate hard-case accuracy. Remaining exposure: the human evidence is a single annotator, and believability is unproven (10 of 24 v3 comments sounded AI-written). Status: Open → Mitigating.

**Update 2026-09-23 (ADR-040):** Labels are now specification-defined: the ADR-036 written definitions are the ground truth, plain labels are generator intent confirmed by the judge, and hard-case labels are generator intent with their judge disagreement rate reported. The ~200-comment human review is reduced to a ~30-comment sanity spot-check for unusable comments, with no agreement scoring or regeneration gate. The remaining exposure is that the specification may not match every reader — the owner's own reviews read the problem-plus-recovery boundary both ways — and this is stated as a limitation. Status stays Mitigating.

**Update 2026-09-25 (final corpus):** Judge agreement before filtering, by class: mixed 95%, negative plain 94%, positive plain 82%, neutral plain 56%. Hard-case judge disagreement, unfiltered by design: positive implicit 20%, sarcastic 12%, negative implicit 3%. Accepted neutrals are 73% administrative, 19% status, and 8% minimal, because the judge accepted administrative notes far more often (78%) than status (27%) or minimal (52%), and most minimal comments were lost to duplicate rejection first. That skew likely makes neutral accuracy optimistic; the mitigation is per-kind reporting in the sentiment eval (Sprint 3). Status stays Mitigating.

**Update 2026-09-25 (Sprint 1 boundary review):** Reviewed, no change.

**Update 2026-09-30 (Sprint 2 boundary review):** No change. The trigger is the sentiment agent in Sprint 3.

**Update 2026-10-10 (Sprint 4 boundary review):** Reviewed, no change. Fault injection made no claim about the labels: its sarcasm fault (owner fault 3) acts on stored predictions and ratings, not on the generated text. Status stays Mitigating.

**Update 2026-10-14 (Sprint 5 boundary review, Z1; owner-decided 2026-10-14; assistant-drafted):** Reviewed, no change. The corpus is frozen and nothing under `data/generator` changed in Sprint 5 (git history since 2026-10-10). Labels were not re-judged. Status stays Mitigating.

### R-14 — Environment parity: verified only against local Docker Postgres
*Added 2026-09-25.*
**Description:** Every migration, grant and load so far has run only against local Docker Postgres, connected as a true superuser. Cloud SQL provides `cloudsqlsuperuser`, not SUPERUSER, so the roles migration (role creation, grants, the `PUBLIC` revokes of ADR-025) is unverified on the deployment target and may fail or behave differently there.
**Likelihood / Impact:** Medium / Medium. **Status:** Monitoring.
**Mitigation:** The Sprint 4 reporting-slice deploy (ADR-045) runs `alembic upgrade head` and the grants integration suite against Cloud SQL, a sprint before the full migration.
**Review trigger:** That deploy (2026-11-02 to 11-04).

**Update 2026-09-30 (Sprint 2 boundary review):** No change. The trigger is the Sprint 4 deploy.

**Update 2026-10-05 (ADR-078):** The deploy that triggers the review moves to 2026-10-12 to 10-14 (was 2026-11-02 to 11-04). Status stays Open.

**Update 2026-10-08 (deploy window, ADR-084):** **Not realised.** On Cloud SQL (PostgreSQL 16, Enterprise, `cloudsqlsuperuser`, not a true superuser), all nine migrations ran unchanged on the first attempt (27 s), including the roles migration, the `PUBLIC` revokes and the column grants. `alembic check` was clean, the loader and the 67 validation checks ran unchanged with the same corpus hash, seed and row counts as local, and the grants integration suite passed (882 passed, 1 skipped, the skip being `test_golden_oracles`, which needs stored predictions). The only difference was an operational one: the micro tier's `max_connections=25` default, which the test-suite pool leak exhausted (L-66); raised to 60. Status: Open to Monitoring; the full migration in Sprint 5 (all services, `sentiment_predictions`) remains the last unverified step.

**Update 2026-10-10 (Sprint 4 boundary review):** Not realised in the reporting-slice deploy (2026-10-08; see that update). Monitoring until the Sprint 5 deploy of every service, the first time the sentiment predictions backfill and the volume artifact run on Cloud SQL. Status stays Monitoring.

**Update 2026-10-14 (Sprint 5 boundary review, Z1; owner-decided 2026-10-14; assistant-drafted):** **Closed.** The review condition was "the Sprint 5 deploy of every service, the first time the sentiment predictions backfill and the volume artifact run on Cloud SQL" (2026-10-10 line above). The Sprint 5 deploy is done (six services, 2026-10-13); the backfill's rows and hashes match the local table (`data_parity_cloud.json`, `sprint-log.md` Sprint 5 close); and the forecast service, with its baked parameter files (ADR-098), answered a question on the deployed system. The scoped real-data suites on Cloud SQL (L-78, runbook step 7) were deferred and remain a Sprint 6 item; they test QA's agreement, not the parity this risk names. Status: Monitoring to Closed.

### R-15 — Provider capacity: free-tier 503s on the orchestrator's model
*Added 2026-09-26.*
**Description:** The 2026-09-26 capture run got a free-tier "This model is currently experiencing high demand" 503 from `gemini-3.7-flash` on its second request. That model is now the orchestrator's (ADR-049), so it is the first hop of every request: when it is overloaded, nothing is answered, even questions a specialist could handle. Its free-tier limits (5 RPM, 20 RPD, ADR-029) compound this.
**Likelihood / Impact:** Medium / High. **Status:** Mitigating.
**Mitigation now:** `packages/llm` retries 5xx errors twice with short jittered backoff, then raises `LLMUnavailable`. The orchestrator turns that into a clear 503 rather than hanging (ADR-048).
**Sprint 4 decision:** an orchestrator fallback to `gemini-3.5-flash-lite` on repeated 503s, and/or running eval jobs off-peak or on the paid key (ADR-041).
**Review trigger:** The Sprint 4 slice deploy (ADR-045).

**Update 2026-09-26 (orchestrator model):** The orchestrator moved off `gemini-3.7-flash` to `gemini-3.5-flash-lite` (ADR-049), after the seed set showed no accuracy advantage for 3.7 Flash (27/28 against Flash-Lite's 28/28) and 3.7 Flash returned three consecutive 503s during the checkpoint e2e. Flash-Lite had no 503s across 28 seed-set calls. Likelihood Medium → Low. The planned Sprint 4 fallback to Flash-Lite is likely unnecessary now, since the orchestrator already runs on it. Status: Mitigating → Open, because Flash-Lite can also return 503s and the bounded 5xx retry is the only mitigation in place.

**Update 2026-09-26 (mitigation in place):** Status: Open → Mitigating. The mitigation is in place: `packages/llm` retries 5xx errors twice with jittered backoff, then raises `LLMUnavailable`, which the services return as a clear 503 rather than hanging (ADR-048).

**Update 2026-09-30 (Sprint 2 boundary review):** Confirmed Low / Mitigating. No 503s were observed from Flash-Lite this sprint: every eval result file shows one request per call (no retries), and the checkpoint e2e runs on Flash-Lite needed no rerun.

**Update 2026-10-08 (deploy window):** **Not hit.** The window made 7 live free-tier calls, all through `verify.py` check 6, and none returned a 503 or a rate-limit error. Status stays Mitigating; one window is too little to call it.

**Update 2026-10-10 (Sprint 4 boundary review):** No 503 is recorded in the sprint log or its notes for Sprint 4's live calls (the deploy window, the gate and end-to-end runs and the two loop checks, all on the free key). One sprint is too little to call it. Status stays Mitigating.

**Update 2026-10-13 (Sprint 5 close):** **Realised**, in a related form. The free tier returned `504 DEADLINE_EXCEEDED` for `gemini-3.5-flash-lite` from Cloud Run twice and from the owner's machine once; the paid key answered the same call with 200 in 1.85 s (ADR-104). That is one call per key, so it shows the free tier failing that day, not a failure rate. It is a deadline error, not the 503 "high demand" this entry names, but the exposure is the same: the first hop of every request. Mitigation: ADR-104 moved the five model-calling services to the paid key and ADR-105 keeps it. Status: Mitigating to Realized (mitigated by ADR-104).

**Update 2026-10-14 (Z2a, ADR-108; owner-decided 2026-10-14; assistant-drafted):** the diagnosis gap this risk exposed on 2026-10-13 is closed in the repo: each failed model-call attempt now logs its attempt number, error class, HTTP status, failure kind, the wait before the next attempt and the elapsed time (never the key, the prompt or the error text). Tests: `tests/unit/test_llm_client.py` (a 504, a 503, a connection error and a 429). Not deployed until Z2b; status stays Realized.

### R-16 — Evaluation validity: measured differences may be noise
*Added 2026-09-30.*
**Description:** The development routing sets are small (28 and 18 questions), routing_v1 has been used to revise the routing prompt (L-16), and model output varies between runs even at temperature 0 (L-17, L-18). Together these mean a measured difference between models or prompts may be noise, and a reported accuracy may be optimistic.
**Likelihood / Impact:** High / Medium. **Status:** Open.
**Mitigation:** A held-out routing set never used to revise a prompt (Sprint 5); three runs per evaluation with the range and the flipping questions reported (ADR-054); limitations logged in `docs/evaluation-report.md`.
**Review trigger:** The Sprint 5 evaluation runs.

**Update 2026-10-10 (Sprint 4 boundary review):** New evidence, and it points the same way. The interpretation gate was judged on assistant-drafted pairs (L-69, L-74): both prompts failed, and the 84 pairs are now used up as a confirmation set. The fault catalogue is not blind (L-85), and consistent misparses were caught 0 of 71, so the QA numbers are upper bounds on what an independent reviewer would find. Measurement 2 (223 of 223) is the weaker of the two measurements: the fixes were designed from measurement 1's misses (ADR-092). Mitigation: the owner-written sets in Sprint 5 (held-out routing, a fresh FR-03 set, a fresh interpretation set, an option for owner-written faults). Status stays Open, likelihood High.

**Update 2026-10-11 (ADR-094):** The mitigation moves to the sets generated under ADR-094 (a held-out routing set, a fresh FR-03 set, a fresh interpretation set), written by an independent model, `gemini-3.8-flash`, from a fixed brief, not by the owner. They are blind to the system but not to the assistant's framing of the domain. **New evidence:** the generator is in the same model family as the system's models (`gemini-3.5-flash-lite`), so phrasing that the family finds easy may inflate accuracy (L-86). Status stays Open.

**Update 2026-10-13 (Sprint 5 close):** The mitigation ran. Held-out routing: 38, 38, 38 of 50 with no flipping items, and 38, 38, 38 of 43 without the 7 ambiguous items. Golden: 29 of 36 mechanical and 31 of 36 on the owner's judgement. The routing range was zero over three runs, so run-to-run variance did not move that figure on this set. The validity concerns stand: the generated sets come from the system's own model family (L-86), persona drops weight them towards broad questions, and the golden set's owner-written items score lower than the drafted ones (mechanical 6 of 10 against 23 of 26; owner 7 of 10 against 24 of 26), which is the check L-54 describes on drafted items favouring the system's phrasing. Ten and 26 items are too few to size that gap. Both sets are now spent for blind use. Status stays Open.

**Update 2026-10-14 (Sprint 5 boundary review, Z1; owner-decided 2026-10-14; assistant-drafted):** **G04, reconciled.** L-56 describes the question (complaint themes since an app update: a stretch item the system must not invent an answer to). The sprint log and R-16's earlier line describe the deployed answer (a one-region sentiment item whose counts equal the oracle). Both are right, about different things. From `evals/results/sprint5_x/golden_assistant_reading.md`: G04 passes mechanically; the system answered with the region's sentiment counts, shares and range, said the range was assumed, quoted comments verbatim, and invented no theme or app-update date; it did not say the "since the app update" qualifier was ignored, which is the stretch gap (L-56). So G04 is a stretch item whose deployed behaviour is a sentiment answer, not a decline; the 6.5 candidate that treats "complaint themes" as unsupported is right that theme extraction does not exist.

### R-17 — Local environment memory exhaustion (WSL/Docker)
*Added 2026-10-05, from the owner's Sprint 3 final retro review.*
**Description:** The local environment (Windows 10, Docker Desktop on WSL2, an Intel i7-6700HQ with 4 cores / 8 threads) has repeatedly run out of memory, which forced freeing memory and restarting the machine several times. The logs record no count or dates for these incidents (the only related record is a 29.4 s first container start after a Windows restart, L-36). Sprint 4 adds the QA agent and the deploy tooling to the local footprint.
**Likelihood / Impact:** High / Medium. **Status:** Open. The register's scale is Low / Medium / High; "likely" is High. The impact is lost time and interrupted runs.
**Trigger:** Docker or WSL fails, or the machine becomes unresponsive.
**Mitigation (owner-stated 2026-10-05; none of these is recorded elsewhere in the repo or logs, and none was verified):**
- A WSL memory cap, and `autoMemoryReclaim=dropcache`, set in `.wslconfig`. The cap's value is not recorded here.
- Docker's data kept on `D:`.
- Stop the stack before heavy jobs: BERT training or scoring, full-stack rebuilds, eval runs.
- Recover by restarting Windows, not with `wsl --shutdown`.
The same steps are in the README's "Local environment recovery". Check the memory headroom before any long run or full-stack rebuild.
**Review trigger:** The Sprint 4 close.
**Update 2026-10-08:** 2026-10-05, owner-verified: `.wslconfig` has `memory=6GB` and `autoMemoryReclaim=dropcache`; Docker disk image at `D:\DockerData\DockerDesktopWSL`. The first two mitigations above are now verified rather than unverified, and the memory cap's value is recorded. The stop-the-stack and restart-Windows steps remain owner practice. Status stays Open.
**Update 2026-10-08 (incident):** The R-17 failure occurred during the Sprint 4 phase 1 work. A full-stack `docker compose up -d --build` left stale containers in `Dead` and `Created` states (and `removal already in progress` errors), and the compose build ran past 10 minutes. They had to be force-removed before a second `up` brought all eight containers healthy. No data was lost (Postgres stayed up). This is the first recorded dated incident; earlier ones have no dates (see the Description). Status stays Open; the Sprint 4 close review stands.

**Update 2026-10-10 (Sprint 4 boundary review):** **The review trigger was this close.** One dated incident is recorded (2026-10-08, a full-stack `docker compose up -d --build` that left stale `Dead` and `Created` containers and ran past 10 minutes), and the first two mitigations are verified (`memory=6GB`, `autoMemoryReclaim=dropcache`, Docker data on `D:`). Observed on 2026-10-10, during the fault-injection loop demonstration: a full-stack `docker compose up -d --build` (the Postgres container showed `Dead`, others `Created`) took about 10 minutes and then came up healthy with no intervention and no data loss. **Recorded as a probable recurrence** of the 2026-10-08 incident: the same symptom, memory not measured. **Owner (2026-10-10):** no memory incidents on 2026-10-08 to 10-10 beyond the 10-08 incident. Status stays Open, likelihood High. **Mitigation added:** on recurrence, capture `docker stats` and the host's memory before recovering, so the next incident is measured, not inferred.

**Update 2026-10-13 (Sprint 5 close):** No recurrence in Sprint 5 (owner-reported in the Prompt Y brief; no dated incident or `docker stats` capture is recorded in the repo). The local database was started for the data-parity check (`sprint5_x.md`, deviation 4) with no problem recorded. Status stays Open: one sprint without an incident does not move likelihood.

### R-18 — Misinterpreted questions pass as verified
*Added 2026-10-10 (Sprint 4 boundary review).*
**Description:** QA recomputes the figures for the request the specialist *parsed*; whether the parse matches the question is the interpretation check's job, and that check is advisory (L-74). A wrong month, region, metric, slice or label therefore returns an answer whose figures are right for the wrong question, marked `verified`. Users and the evaluation can read `verified` as "answered correctly".
**Likelihood / Impact:** Medium / High. **Status:** Open. It is a risk, not only a limitation, because the harm is a confident wrong answer to an operations leader, and the label that is meant to prevent that is the one carrying it.
**Evidence:** consistent misparses were caught 0 of 71 in the fault injection (reporting 0/30, forecast 0/19, sentiment 0/22; the owner's trailing-quarter case 0/10), measurement 1 and measurement 2 alike (ADR-091, ADR-092). The interpretation gate failed twice on assistant-drafted pairs and ships advisory (L-74). The catalogue's misparses are blunt and assistant-drafted, so the real rate is probably worse, not better (L-85).
**Mitigation:**
- Every answer states its range and filters, so the user can check what was asked (ADR-050, ADR-086); `verified` is documented as "the figures are correct for the request as parsed" (L-74, FR-09 to FR-11).
- An interpretation-gate reattempt on an owner-written set in Sprint 5, with a new pre-registered gate.
- For forecasts, an answer-time check that served numbers equal the model's own prediction (L-83(a)) narrows what a wrong parse can hide; it does not catch the parse itself.
**Review trigger:** The Sprint 5 interpretation-gate reattempt; every sprint retro.
**Update 2026-10-11:** the answer-time forecast check named in the mitigation (L-83(a)) is built (ADR-095): QA recomputes served forecast numbers from the stored parameters. Measurement 3 still catches consistent misparses 0 of 71; the check does not catch the parse itself, as stated here.
**Update 2026-10-12:** the single-screen UI built under ADR-097 shows an "Interpreted as:" line with every answer, and every decline that carries a parsed request: the measure, the resolved dates (and whether they were assumed), the region ("all regions", or "region not recognised"), account or technician, breakdown and forecast horizon (data dictionary §6, "Answer display (UI)"). It is the user's check on a misparse, which the mitigation above relied on the answer text alone to provide. The risk itself is unchanged: the line shows how the question was read, it does not make the reading correct, and `qa_status: verified` is worded "Figures checked for the request as interpreted" (L-74). Status stays Open.

**Update 2026-10-13 (Sprint 5 close):** The "Interpreted as:" line is deployed with the gateway (ADR-097; revision `ops-gateway-00001-8st`). The interpretation check is still advisory with `qa_interp_v2`: the Sprint 5 gate failed on (a), 3 false rejects of 23 against at most 1 (ADR-102), and the frozen gate holds one decline pair (L-92). The golden run shows the same exposure in a milder form: "district" (G03) and "end of next year" (G07) were resolved by the system's own reading and shown, not asked (L-95). Status stays Open.

### R-19 — The sentiment model weights have no path into a Cloud Run image
*Added 2026-10-12 (Prompt U, deploy readiness).*
**Description:** `mcp_feedback` hash-checks every file its manifest lists, including the 438 MB `model.safetensors`, at start-up and refuses to start if one is missing (ADR-066, ADR-067); it then loads BERT lazily for any comment in range without a stored prediction. The weights are gitignored (`/models/`), and the build trigger builds from git. ADR-062's Cloud Storage path was never built: no bucket exists (read 2026-10-12). A built `mcp-feedback` image therefore cannot start, and `ops-sentiment` cannot serve.
**Likelihood / Impact:** High (certain as the repo stands) / Medium (one of three specialist routes is unavailable in the deployed system; the other two and QA are unaffected). **Status:** Open.
**Mitigation:** the `ops-sentiment` definition is written and tested; its image build and deploy are gated behind `_DEPLOY_SENTIMENT=false` and marked BLOCKED in `plan_full.py` and the runbook, so the rest deploys. Until decided, a sentiment question answers "The data service is unavailable right now." Owner's choice: (A) ADR-062 as written: a bucket, a build step that pulls the pinned weights, read access for the build account (about 440 MB plus torch in the image; the start-up hash of 438 MB counts against the 120 s deadline, R-05); or (B) stored predictions only after a complete backfill, which drops on-demand scoring and relaxes the start-up check and needs its own ADR.
**Review trigger:** the owner's decision; the Prompt V window.
**Update 2026-10-12 (Prompt U2, ADR-100):** the owner chose (B). Deployed sentiment reads stored predictions only (`MCP_FEEDBACK_SCORING=stored_only`): the `stored` image target has no torch and no weights, the start-up check covers the manifest, and a comment in range without a stored prediction fails closed (`predictions_incomplete`). The blocker is removed: `_DEPLOY_SENTIMENT` is `true` and sentiment deploys with the other five. Coverage on the local database is complete (7,521 of 7,521, one model version, fingerprint `a340b82d…e259f`), so answers are identical to the lazy path. **Status: Monitoring** (the mitigation is in place in code and config; nothing is deployed yet). What is watched: the Cloud SQL backfill's fingerprint must match the local value; on a mismatch sentiment does not deploy (runbook step 4). Close it when the service is verified serving. R-05's cold start for this service no longer includes a 438 MB hash.

**Update 2026-10-13 (Sprint 5 close):** **Closed.** Sentiment is deployed (`ops-sentiment-00002-cxz`, `stored_only`, ADR-100) and serving: the golden items G04, G20, G21 and G22 answered on the deployed system, and the counts, shares and flagged counts of G04, G20 and G21 equal the oracle (`golden_assistant_reading.md`, check notes). That is the close condition above. The completeness evidence is the data-parity check (`sprint5_x.md`, deviation 4): `sentiment_predictions` on Cloud SQL equals the local table in row count and in per-table and per-column hashes ordered by primary key (`evals/results/sprint5_x/data_parity_cloud.json`, `data_parity_local.json`). The runbook step 4 fingerprint (`a340b82d…e259f`) matched exactly after the backfill and again after the 2026-10-13 database start (`docs/deploy-window-log.md` (2026-10-12/13)). What replaces this risk is L-91 (a comment added after the backfill makes its range fail closed). Status: Monitoring to Closed.

### R-20 — Cloud SQL connection ceiling during a rollout
*Added 2026-10-12 (Prompt U, ADR-099).*
**Description:** `ops-db` allows 60 connections. Four services connect, each container's pool is at most 4, and each is limited to 2 instances: 32 at the steady-state worst case, 46 with the reserved and owner sessions budgeted. During a rollout an old and a new revision can both hold instances, a theoretical 78. It is reached only if every instance of both revisions holds its whole pool at once.
**Likelihood / Impact:** Low (a handful of reviewers; pools open on demand) / Medium (`too many connections` makes the data services fail until instances drain). **Status:** Open.
**Mitigation:** the arithmetic is in ADR-099 and checked by `tests/unit/test_deploy_full.py` against the definitions and the pool settings in code. The runbook's stop rule is any `too many connections` in a service log.
**Review trigger:** the Prompt V window.
**Update 2026-10-12 (Prompt U2, runbook):** the services are deployed one at a time, each waiting for its revision to be ready and at 100% traffic before the next starts (`cloudbuild.yaml` chains the deploy steps and `deploy_service.py` waits for the operation; 5e verifies the traffic). With one service mid-deploy the worst case is 3 × 2 + 4 = 10 instances × 4 = 40 connections, 50 with the 10 reserved, 54 with the owner's 4 sessions, against 60 (headroom 6). ADR-099's all-at-once ceiling was 78. A bound, not an expectation: pools open on demand. Status: Mitigating until the deploy is run.

**Update 2026-10-13 (Sprint 5 close):** The services were deployed one at a time (owner-reported in the Prompt Y brief), the mitigation of the 2026-10-12 update. A count of `too many connections` lines in the service logs is not recorded in the repo, so this entry does not claim there were none. ADR-105 stops `ops-db` outside grading windows, which removes the exposure while it is stopped. Status: Mitigating to Monitoring.

### R-21 — Paid balance runs out during a grading window
*Added 2026-10-13 (Sprint 5 close; ADR-104, ADR-105).*
**Description:** The deployed system's model calls run on the paid key. If the prepaid balance reaches zero, every question fails while the services and the database are up, so the grader sees an unavailable system in the one period it most needs to answer. The balance is about $2.9 (R-02, an estimate), below the $5 minimum ADR-105 sets before a window, and auto-reload is off.
**Likelihood / Impact:** Medium (spend is small, but the balance is not watched and auto-reload is off) / High (a failed window, not a wrong figure). **Status:** Open.
**Mitigation:**
- Top up to at least $5 before each window, checked in the Billing console (ADR-105).
- The gateway's 50-question daily cap (ADR-097) bounds spend at about $0.35 a day (ADR-104).
- Paid mode fails closed: `LLM_MODE=paid` refuses to start without its own key and caps (`packages/llm/src/llm/config.py`) and does not take the free key. What a service does on an exhausted balance at call time has not been tested.
**Review trigger:** before each grading window; any budget alert.
**Update 2026-10-15 (S6-W1; owner-decided 2026-10-15; assistant-drafted):** the paid balance is **$7.88** after the 2026-10-15 top-up (owner-reported; the console reading at the next session's opening governs, ADR-105). The "about $2.9" in the Description above is the 2026-10-13 estimate and is superseded; it is not edited. The balance is above the $5 minimum ADR-105 sets. Status stays Open: the balance is still not watched programmatically and auto-reload is off.

**Update 2026-10-15 (S6-D2; Owner-decided 2026-10-15; assistant-drafted.):** session 1's opening balance was **$7.88** (owner-read). The session's ledger ceiling was **$0.079 worst case, for 57 requests** (driver ledger, charged at the highest seen cost when unknown). The closing figures the owner read, Google AI Studio $2.12 (2026-09-18 to 10-15) and GCP billing $2.86 (2026-10-01 to 10-15), are cumulative, so the session's own spend cannot be separated from them and no closing balance was recorded. Next check: before Window A (10-31). Status stays Open.

---

## Closed / Realized Risks
*(move entries here as they resolve, with the outcome noted — this becomes useful evidence for the evaluation report's lessons-learned section)*

- **R-06 — A2A overhead consumes disproportionate solo dev time.** Closed 2026-09-30: did not materialise (both checkpoints met early, low SDK friction). The detail and reopen trigger stay under R-06 above.
- **R-03 — Cloud Run build/deploy decoupling.** Closed 2026-10-13: did not materialise in either deploy (the 2026-10-08 slice and the Sprint 5 full deploy; traffic verified at 100%). The detail and reopen trigger stay under R-03 above.
- **R-15 — Provider capacity.** Realized 2026-10-13: the free tier returned 504s; mitigated by moving the deployed services to the paid key (ADR-104, ADR-105). The detail stays under R-15 above.
- **R-19 — The sentiment model weights have no path into a Cloud Run image.** Closed 2026-10-13: resolved by ADR-100 and verified serving. The detail stays under R-19 above.
