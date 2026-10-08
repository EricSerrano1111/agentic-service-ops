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
| R-03 | Deployment | Cloud Run build/deploy decoupling (recurred before) | High | Medium | Open |
| R-04 | ML / Verification | Sentiment task has weak natural verifiability | Medium | High | Mitigating |
| R-05 | Cost / Technical | QA retry loop cost or latency runaway | Medium | Medium | Mitigating |
| R-06 | Schedule / Scope | A2A overhead consumes disproportionate solo dev time | Medium | Medium | Closed |
| R-07 | Data | Synthetic generator produces a degenerate distribution | Medium | High | Monitoring |
| R-08 | Compliance | Schema/data drifts toward resembling employer's real system | Low | High | Mitigating |
| R-09 | Academic | Course rubric diverges from the assumed deliverable plan | Medium | High | Monitoring |
| R-10 | Schedule | Sprint 6 buffer erodes from earlier slippage | Medium | High | Open |
| R-11 | External / Budget | Vendor pricing or model access changes mid-project | Medium | Medium | Open |
| R-12 | Technical / External | MCP/A2A ecosystem churn breaks a dependency | Medium | Medium | Mitigating |
| R-13 | Data / ML | Generated comments don't match their requested sentiment | Medium | High | Mitigating |
| R-14 | Technical / Deployment | Environment parity: everything verified only on local Docker Postgres with a true superuser | Medium | Medium | Open |
| R-15 | External / Technical | Provider capacity: free-tier "high demand" 503s on the orchestrator's model, the first hop of every request | Low | High | Mitigating |
| R-16 | Evaluation | Evaluation validity: small, partly non-blind development sets and run-to-run variance make measured differences possibly noise | High | Medium | Open |
| R-17 | Technical / Environment | Local environment memory exhaustion (WSL/Docker) | High | Medium | Open |

---

## Detail

### R-01 — Solo build, no peer review
**Description:** No second person to catch design blind spots, review code, or push back on a bad assumption before it's built on top of.
**Mitigation:** CI with real test coverage; eval harnesses (routing, forecast backtest, sentiment holdout, QA catch rate) substitute for a reviewer's judgment with measurable output instead; sprint retros are the deliberate moment to self-audit rather than assume things are fine.
**Review trigger:** Every sprint retro — explicitly ask "what would a reviewer have flagged this sprint?"

**Update 2026-09-25:** CI is live (GitHub Actions: ruff lint, the offline unit suite, and the live grants integration suite against a Postgres 16 service container, with `REQUIRE_INTEGRATION_DB=1` so a missing database fails rather than skips). The eval harnesses are still to be built. Status stays Open.

**Update 2026-09-25 (Sprint 1 boundary review):** CI is live; the eval harnesses are not built yet. The reviewer question is answered in the Sprint 1 retro (`sprint-log.md`): assumptions repeated until they read as requirements, and ADR headers that understated supersession. Status: Open → Mitigating.

**Update 2026-09-30 (Sprint 2 boundary review):** The reviewer question is answered in the Sprint 2 retro (`sprint-log.md`): tests built from the author's assumptions passed while the code was wrong, and assistant-written instructions asserted repo state without checking it. The routing eval harness now exists (`evals/routing/run_seed.py`, three runs per evaluation, ADR-054). Status stays Mitigating.

### R-02 — Runtime budget depends on unconfirmed credit coverage
**Description:** The cost plan assumes Google AI student credits cover Gemini runtime inference for all five agents across 12 weeks. Coverage and expiry haven't been confirmed.
**Mitigation:** Confirm in Sprint 1 — this is a named open item, not an assumption to defer. `packages/llm/` keeps every agent provider-agnostic, so a swap to another provider is a config change if credits fall short.
**Update 2026-09-22 (ADR-029):** Student credits confirmed not available. Development inference moved to the Gemini API free tier with Flash-Lite defaults, so credit coverage is no longer the exposure. What remains: free-tier rate limits (429 backoff required in `packages/llm/`) and any paid Sprint 5 eval spend, which runs in a separate spend-capped project. Free-tier limits are now confirmed in AI Studio (2026-09-22): Flash-Lite 15 RPM / 250K TPM / 500 RPD, Flash models 20 RPD, and no free-tier quota for Pro models. The remaining exposure is eval volume: a full routing eval run (300–700 requests) can exceed the 500 RPD Flash-Lite cap, so Sprint 5 evals must be split across days or run on a paid, spend-capped project. If the paid route is taken, that project's cost is not yet included in the budget estimate, which so far covers only the ~$20–30 Pro-for-QA test. Pricing it is a Sprint 4 planning item.
**Review trigger:** Sprint 1 close-out. Re-check if GCP budget alerts fire.

**Update 2026-09-24 (ADR-041):** Paid spend now exists: remaining Flash-Lite corpus generation runs on a separate paid project (about $2 at list prices), bounded by a $10 project budget alert, the $50/$80 GCP budget alerts, and a hard per-session request cap in `build_corpus.py`.

**Update 2026-09-25:** Paid spend is bounded by a code-enforced per-session request cap in `build_corpus.py`, a $5 prepaid balance on the paid project with auto-reload off, and budget alerts at $10 (project) and $50/$80 (billing account). Corpus generation cost about $1.40 (estimate from list prices, not billing data). Status stays Mitigating.

**Update 2026-09-25 (Sprint 1 boundary review):** No budget alert has fired; about $1.40 spent. Next trigger: the Sprint 4 item that prices a full routing eval run (two LLM calls per request, ADR-046). Status stays Mitigating.

**Update 2026-09-30 (Sprint 2 boundary review):** Paid spend this sprint, computed from the eval result files in `evals/results/`: $0.0370 at list prices, from the two `gemini-3.7-flash` routing runs on the paid key (seed_v1 on 2026-09-26, $0.0201; routing_v1 on 2026-09-30, $0.0169). Every other run used the free key. This is a list-price estimate, not billing data, and it covers only calls recorded in the eval result files. No cap was hit and no budget alert fired. Status stays Mitigating.

### R-03 — Cloud Run build/deploy decoupling
**Description:** A prior academic project hit successful Cloud Builds that didn't produce active Cloud Run revisions — a decoupled build/deploy pipeline. Same deployment target, same failure mode plausible.
**Mitigation:** Wire an explicit Cloud Build trigger → deploy step rather than an image push alone; verify revision promotion immediately on the first Sprint 5 deploy rather than waiting until later to check.
**Review trigger:** First deploy attempt in Sprint 5 — don't wait for the retro if this recurs, it blocks the sprint goal directly.

**Update 2026-09-25 (Sprint 1 boundary review):** Mitigation adds the Sprint 4 reporting-slice deploy (ADR-045, 2026-11-02 to 11-04) with a post-deploy check that the serving revision is the one just built and holds 100% of traffic. Review trigger moves to that deploy; its stop rule records R-03 as realised if the revision is not verified serving by end of 11-04. Likelihood normalised Medium-High → High. Status stays Open.

**Update 2026-09-30 (Sprint 2 boundary review):** Builds are now reproducible: CI and the service images install exactly what `uv.lock` pins (ADR-047). The trigger is still the Sprint 4 slice deploy (ADR-045). Status stays Open.

**Update 2026-10-05 (ADR-078):** The slice deploy is pulled forward to 2026-10-12 to 10-14, with the stop rule at the end of 10-14. The 2026-11-02 to 11-04 dates above are superseded; the post-deploy check and the consequence of the stop rule are unchanged. Status stays Open.

### R-04 — Sentiment task has weak natural verifiability
**Description:** Unlike reporting (deterministic) or forecasting (standard backtest metrics), sentiment has no natural ground truth. A QA check that just re-runs the same model is circular and proves nothing.
**Mitigation:** `sentiment_labels` holdout the sentiment agent never reads; the `rating` field on `service_feedback` gives QA a second, independent cross-check signal. Both already designed in — this is why status is "Mitigating" rather than "Open." Both are now enforced by database grant, not convention: the sentiment role has no grant on `sentiment_labels`, and since ADR-027 its `service_feedback` grant is column-level and excludes `rating`, so the second signal is independent by construction. `tests/integration/test_access_matrix_grants.py` asserts both against the live database.
**Review trigger:** Sprint 4, when the QA agent's sentiment-verification path is actually built and tested against real generated data.

**Update 2026-09-25 (Sprint 1 boundary review):** Reviewed, no change. Impact normalised Medium-High → High.

**Update 2026-09-30 (Sprint 2 boundary review):** Reviewed, no change.

**Update 2026-10-01 (ADR-063):** Gold labels are now held only by offline roles: `app_eval` (validation and evaluation) and `app_train` (training). `app_qa` can no longer read `sentiment_labels` or `generation_parameters`, so the runtime QA check cannot lean on gold labels; at answer time it rests on the rating cross-check (ADR-055), whose optimism on this data is L-24. Training is also barred from `rating` by grant, so the cross-check stays independent of the trained model too. Status stays Mitigating.

### R-05 — QA retry loop cost or latency runaway
**Description:** Multi-agent systems with a verify-and-revise loop can fan out token usage and wall-clock time quickly if unbounded.
**Mitigation:** Bounded at 2 retries with escalation on final failure (ADR-022); per-run cost caps and model tiering already specified in the budget plan.
**Review trigger:** Sprint 4, once the loop is live and real cost/latency numbers exist to check against the plan.
**Update 2026-09-22 (ADR-034):** Latency is also bounded by a 120-second end-to-end ceiling, after which the request returns a degraded result with an escalation flag. Check in Sprint 5's first deploy whether cold starts alone approach the ceiling.

**Update 2026-09-25 (Sprint 1 boundary review):** Reviewed, no change. Likelihood normalised Low-Medium → Medium.

**Update 2026-09-30 (Sprint 2 boundary review):** Reviewed, no change.

### R-06 — A2A overhead consumes disproportionate solo dev time
**Description:** A2A's Agent Cards and task-lifecycle machinery are more plumbing than a single-codebase system strictly needs. Solo, on a fixed timeline, that overhead is a real opportunity cost.
**Mitigation:** Sprint 2 is deliberately the proof sprint for this exact risk — if the A2A path is disproportionately slow to stand up, that's the signal to reconsider before three more agents are built on top of it. No fallback plan currently drafted; if this risk is realized, the honest move is a documented scope conversation, not silent workarounds.
**Review trigger:** Sprint 2 retro, explicitly.

**Update 2026-09-25 (Sprint 1 boundary review):** Checkpoints: the skeleton hop (MCP tool → reporting agent → orchestrator over A2A, no LLM) working by 2026-10-02, or hold the scope conversation that day; an LLM-classified question answered end to end in docker-compose by 2026-10-07. Hours are logged per layer. Fallback: if the SDK is the friction, implement the small protocol surface actually used (the Agent Card endpoint plus `message/send`) directly on FastAPI/httpx. Collapsing to in-process calls would break ADR-001 and ADR-011; that is the documented scope conversation, not a silent workaround. Status stays Open.

**Update 2026-09-25 (walking skeleton):** The skeleton checkpoint is met ahead of 2026-10-02: orchestrator → A2A → reporting agent → MCP → Postgres runs in docker-compose with no LLM, and the e2e test passes. SDK friction was low, and the fallback was not needed. The friction points were protobuf float coercion of A2A data parts; the `message/send` → `SendMessage` rename in A2A v1.0; and the MCP 2.x API changes (`FastMCP` → `MCPServer`, the SDK replacing the root log handler, and an allowed-hosts list needed on the Docker network). The second checkpoint, an LLM-classified question answered end to end in docker-compose by 2026-10-07, stands. Status stays Open.

**Update 2026-09-26 (checkpoint 2):** Met on 2026-09-26, ahead of 2026-10-07. An LLM-routed, LLM-parsed question is answered end to end in docker-compose: all six checkpoint e2e assertions passed (routing to reporting, "last month" parsed to July 2026 per ADR-050, figures equal to independent SQL as `app_qa`, the trace id in all three services, the out-of-scope decline, and the sentiment "not available yet" answer). The sentiment assertion passed on a rerun after a provider 503 (R-15). The first run had failed on a configuration error, not on A2A: `gemini-3.7-flash` rejected thinking level `minimal` (ADR-049). Status stays Open until the Sprint 2 retro, which reviews this risk explicitly.

**Update 2026-09-30 (Sprint 2 boundary review):** Did not materialise. Status: Open → Closed. Evidence: both checkpoints were met early (the skeleton hop 2026-09-25 against 10-02; the LLM-classified question 2026-09-26 against 10-07), and SDK friction was low: protobuf float coercion of A2A data parts, the `message/send` → `SendMessage` rename, and the MCP 2.x API changes. The SDK fallback was not needed. Hours per layer were planned but not logged, so there is no time-per-layer figure behind "low"; the evidence is the checkpoint dates. Reopen trigger: wiring A2A into the sentiment or forecast agent takes more than one day of plumbing.

### R-07 — Synthetic generator produces a degenerate distribution
**Description:** Random or careless generation could produce a sentiment mix that's not realistic, a forecast signal that isn't recoverable, or an incident rate that doesn't resemble a real business — quietly invalidating every downstream metric.
**Mitigation:** Explicit validation step planned for Sprint 1 (data-dictionary.md §8 constraints and invariants); target distributions locked in advance (ADR-018, ADR-019, ADR-021) rather than left to chance.
**Review trigger:** Immediately after first generation run, Sprint 1 — before any agent code is built against the data.

**Update 2026-09-25:** Still Open until `validate.py` runs against generated data. The feedback corpus is complete (13,184 comments, q99 rule); `generate.py` is in progress on `feat/generate`.

**Update 2026-09-25 (dataset loaded):** The dataset is generated and loaded into local Postgres (20,230 requests; sentiment mix, incident rate and anomalies land on target in the dry run). `validate.py` (signal recovery) is next. Status stays Open until it passes.

**Update 2026-09-25 (validate.py):** The review trigger is met: `validate.py` passed 66 of 66 checks against the loaded database, with truth read from `generation_parameters`. Headline results: sentiment mix 50.2/22.4/19.6/7.8; incidents on 10.2% of completed requests, missed_sla 24.4% of incidents; recovered growth 8.5% (designed 8%); seasonal peak-to-trough 0.39 against 0.42 designed in the same K=3 basis (the raw weekly design is 0.50, and three harmonics cannot follow the two-week December trough); residual sd 11.7% (designed effective ~10.6%); regional drop z 3.53; account drop 93% at account level; severity->sentiment, SLA->incident and rating->sentiment couplings all consistent with their designs (p >= 0.07). Status -> Monitoring: re-run `validate.py` after any regeneration.

**Update 2026-09-25 (Sprint 1 boundary review):** Reviewed, no change.

**Update 2026-09-30 (Sprint 2 boundary review):** Only `locations` changed, gaining the `region` column (ADR-051). The dataset hash changed, and `locations` with `region` removed hashes identically before and after, as recorded in ADR-051. `validate.py` passed 67/67 after the change (the previous 66 plus the region check). The feedback corpus is unaffected. Status stays Monitoring.

### R-08 — Schema or data drifts toward resembling employer's real system
**Description:** The original draft schema showed signs of being modeled too closely on a real production system. The underlying pull toward "use what I already know" doesn't disappear just because the initial fields were corrected.
**Mitigation:** ADR-012 and ADR-013 establish the discipline; any new field added later should be sourced from general field-service domain principles, checked against this standard before being added, not copied from familiarity.
**Review trigger:** Any time a new table or field is proposed — a standing check, not a one-time fix.

**Update 2026-09-25 (Sprint 1 boundary review):** Sprint 1's new fields (`sentiment_labels.hard_case_type`, `sentiment_labels.corpus_id`, the `world` and `feedback` `param_group` values) are generator internals, not modelled on any real system. Check passes; status stays Mitigating.

**Update 2026-09-30 (Sprint 2 boundary review):** Sprint 2's new field, `locations.region` (ADR-051), is a generic geography: the customer site's region, derived from its state by one committed mapping. Check passes; status stays Mitigating.

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

### R-10 — Sprint 6 buffer erodes from earlier slippage
**Description:** Sprint 6 is the only planned buffer in a 12-week solo timeline. Without a second person creating schedule pressure, slippage in Sprints 1–5 tends to get quietly absorbed rather than confronted.
**Mitigation:** Treat any missed sprint goal as an immediate scope conversation at that sprint's retro, not something to "catch up on later." Scope expansion is only considered if genuinely ahead, per the working agreement.
**Review trigger:** Every sprint retro — explicitly compare actual progress against the plan, not just against what felt productive.

**Update 2026-09-25:** The Sprint 1 goal was missed: the generator carries into Sprint 2, which is also the highest-risk sprint (first vertical slice through A2A and MCP). Kept Open; the Sprint 1 retro decides whether this counts as realised.

**Update 2026-09-25 (goal met):** The Sprint 1 goal was met on 2026-09-25, inside the sprint; the remaining Sprint 1 items (CI, the Alembic ruff hook) are being finished in Sprint 1 rather than carried over. This supersedes the earlier same-day note that the goal was missed. Status stays Open: the buffer risk applies to every sprint.

**Update 2026-09-25 (Sprint 3 academic load):** With the calendar reconciled, Sprint 3 carries two academic deliverables due the same day (`03` Planning & Management and `04` Design & Solution Architecture, both 2026-10-18) on top of the heaviest engineering sprint after Sprint 2 (MCP servers #2 and #3, the sentiment and forecast agents, and three-way routing). Sprint 4 then carries `05` and `06`. Any Sprint 2 slip lands directly on that load. Status stays Open.

**Update 2026-09-25 (Sprint 1 boundary review):** Likelihood Medium → High. Sprint 1's goal was met, but Sprint 3 gained the golden set, the labelled routing set, `security-model.md` and `05` drafting, and Sprint 4 gains the reporting-slice deploy (ADR-045). If Sprint 4 overflows, the fault-injection harness carries to Sprint 5 first. Status stays Open.

**Update 2026-09-30 (Sprint 2 boundary review):** Likelihood High → Medium. Sprint 2's engineering finished 2026-09-30, eleven days before the sprint's end, and two Sprint 3 items moved earlier: `04` is drafted and the labelled routing set is done. Sprint 3 still carries two agents (sentiment and forecast, with MCP servers #2 and #3), the golden set and `05`, plus the two items deferred from Sprint 2. Status stays Open.

### R-11 — Vendor pricing or model access changes mid-project
**Description:** Gemini pricing, free-tier rate limits, or model availability could change over a 12-week window in ways that affect the budget plan (see ADR-029).
**Mitigation:** Provider-agnostic LLM interface (ADR-006) keeps a provider swap mechanically cheap; GCP budget alerts at $50/$80 serve as an early warning regardless of root cause.
**Review trigger:** Any GCP budget alert firing; otherwise passive monitoring.

**Update 2026-09-25 (Sprint 1 boundary review):** Reviewed, no change; no alert has fired. Likelihood normalised Low-Medium → Medium.

**Update 2026-09-30 (Sprint 2 boundary review):** Reviewed, no change; no alert has fired.

**Update 2026-09-30 (free-tier limits):** The Gemini free-tier limits in use (ADR-029: Flash-Lite 15 RPM / 250K TPM / 500 RPD; Flash models 5 RPM / 20 RPD; no free Pro quota) were last verified in AI Studio on 2026-09-22. Re-verify them before any deliverable that states them.

### R-12 — MCP/A2A ecosystem churn breaks a dependency
**Description:** Both protocols are new and moving fast — MCP had its largest spec revision to date in July 2026. An SDK update mid-project could introduce breaking changes.
**Mitigation:** Pin SDK versions at project start; don't chase spec updates mid-build. The project targets the 2026-07-28 MCP spec and A2A v1.0 as documented in `architecture.md` §3 — treat that as fixed unless a specific reason forces an upgrade.
**Review trigger:** Only if a dependency update is being considered — otherwise not time-based.

**Update 2026-09-25 (Sprint 1 boundary review):** Fires in Sprint 2, when the MCP and A2A SDKs are first added: pin exact versions and record them, and confirm the spec targets. Status: Open → Mitigating once pinned.

**Update 2026-09-25 (walking skeleton):** Pinned exactly: `mcp==2.2.0` and `a2a-sdk==1.1.5`. Both spec targets are confirmed from the installed packages and the release notes: the MCP SDK's `LATEST_PROTOCOL_VERSION` is `2026-07-28`, observed as the negotiated version, and the A2A SDK's `PROTOCOL_VERSION_CURRENT` is `1.0`. Evidence and the A2A subset used are in ADR-047. One naming change from the planning docs: v1.0's JSON-RPC method is `SendMessage`, where `message/send` is the v0.3 name. Every other dependency is pinned by `uv.lock`, which CI and the service images install from (ADR-047). Status: Open → Mitigating.

**Update 2026-09-30 (Sprint 2 boundary review):** Both SDKs stay pinned at those versions, and the lock file covers everything else. Status stays Mitigating.

### R-13 — Generated comments don't match their requested sentiment
**Description:** `feedback_text` is LLM-generated to a requested label (ADR-030), and `sentiment_labels.true_sentiment` records that request, not a verified reading of the text. Comments that drift from their label would make the sentiment model's accuracy look worse than it is — the model gets marked wrong for reading the text correctly. Hard cases can fail the other way: sarcasm an LLM writes on request is often obvious, so "hard" comments may be easier than labeled and inflate hard-case accuracy.
**Mitigation:** Sampled label validation in `validate.py` before the corpus is accepted, plus exact and near-duplicate rejection so no comment spans the training and holdout splits.
**Review trigger:** Corpus generation in Sprint 1.

**Update 2026-09-23 (ADR-036):** The bake-off confirmed label drift for neutral: the generator wrote neutral as intended only about half the time, and a flat report of a working fix read as satisfied to both the human reviewer and the judge. Mitigation: a Gemma 4 judge labels every comment, and plain comments whose judge label differs from the intended one are rejected and replaced from spares; a blind, stratified review of ~200 comments follows. Hard cases (sarcastic, implicit) are not judge-filtered, so filtering cannot inflate hard-case accuracy. Remaining exposure: the human evidence is a single annotator, and believability is unproven (10 of 24 v3 comments sounded AI-written). Status: Open → Mitigating.

**Update 2026-09-23 (ADR-040):** Labels are now specification-defined: the ADR-036 written definitions are the ground truth, plain labels are generator intent confirmed by the judge, and hard-case labels are generator intent with their judge disagreement rate reported. The ~200-comment human review is reduced to a ~30-comment sanity spot-check for unusable comments, with no agreement scoring or regeneration gate. The remaining exposure is that the specification may not match every reader — the owner's own reviews read the problem-plus-recovery boundary both ways — and this is stated as a limitation. Status stays Mitigating.

**Update 2026-09-25 (final corpus):** Judge agreement before filtering, by class: mixed 95%, negative plain 94%, positive plain 82%, neutral plain 56%. Hard-case judge disagreement, unfiltered by design: positive implicit 20%, sarcastic 12%, negative implicit 3%. Accepted neutrals are 73% administrative, 19% status, and 8% minimal, because the judge accepted administrative notes far more often (78%) than status (27%) or minimal (52%), and most minimal comments were lost to duplicate rejection first. That skew likely makes neutral accuracy optimistic; the mitigation is per-kind reporting in the sentiment eval (Sprint 3). Status stays Mitigating.

**Update 2026-09-25 (Sprint 1 boundary review):** Reviewed, no change.

**Update 2026-09-30 (Sprint 2 boundary review):** No change. The trigger is the sentiment agent in Sprint 3.

### R-14 — Environment parity: verified only against local Docker Postgres
*Added 2026-09-25.*
**Description:** Every migration, grant and load so far has run only against local Docker Postgres, connected as a true superuser. Cloud SQL provides `cloudsqlsuperuser`, not SUPERUSER, so the roles migration (role creation, grants, the `PUBLIC` revokes of ADR-025) is unverified on the deployment target and may fail or behave differently there.
**Likelihood / Impact:** Medium / Medium. **Status:** Open.
**Mitigation:** The Sprint 4 reporting-slice deploy (ADR-045) runs `alembic upgrade head` and the grants integration suite against Cloud SQL, a sprint before the full migration.
**Review trigger:** That deploy (2026-11-02 to 11-04).

**Update 2026-09-30 (Sprint 2 boundary review):** No change. The trigger is the Sprint 4 deploy.

**Update 2026-10-05 (ADR-078):** The deploy that triggers the review moves to 2026-10-12 to 10-14 (was 2026-11-02 to 11-04). Status stays Open.

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

### R-16 — Evaluation validity: measured differences may be noise
*Added 2026-09-30.*
**Description:** The development routing sets are small (28 and 18 questions), routing_v1 has been used to revise the routing prompt (L-16), and model output varies between runs even at temperature 0 (L-17, L-18). Together these mean a measured difference between models or prompts may be noise, and a reported accuracy may be optimistic.
**Likelihood / Impact:** High / Medium. **Status:** Open.
**Mitigation:** A held-out routing set never used to revise a prompt (Sprint 5); three runs per evaluation with the range and the flipping questions reported (ADR-054); limitations logged in `docs/evaluation-report.md`.
**Review trigger:** The Sprint 5 evaluation runs.

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

---

## Closed / Realized Risks
*(move entries here as they resolve, with the outcome noted — this becomes useful evidence for the evaluation report's lessons-learned section)*

- **R-06 — A2A overhead consumes disproportionate solo dev time.** Closed 2026-09-30: did not materialise (both checkpoints met early, low SDK friction). The detail and reopen trigger stay under R-06 above.
