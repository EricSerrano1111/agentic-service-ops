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
| R-01 | Process | Solo build — no peer review | High | Medium | Open |
| R-02 | Budget | Runtime budget depends on unconfirmed Google AI credit coverage (credits ruled out 2026-09-22; exposure is now free-tier limits and paid spend) | Medium | High | Mitigating |
| R-03 | Deployment | Cloud Run build/deploy decoupling (recurred before) | Medium-High | Medium | Open |
| R-04 | ML / Verification | Sentiment task has weak natural verifiability | Medium | Medium-High | Mitigating |
| R-05 | Cost / Technical | QA retry loop cost or latency runaway | Low-Medium | Medium | Mitigating |
| R-06 | Schedule / Scope | A2A overhead consumes disproportionate solo dev time | Medium | Medium | Open |
| R-07 | Data | Synthetic generator produces a degenerate distribution | Medium | High | Monitoring |
| R-08 | Compliance | Schema/data drifts toward resembling employer's real system | Low | High | Mitigating |
| R-09 | Academic | Course rubric diverges from the assumed deliverable plan | Medium | Medium-High | Monitoring |
| R-10 | Schedule | Sprint 6 buffer erodes from earlier slippage | Medium | High | Open |
| R-11 | External / Budget | Vendor pricing or model access changes mid-project | Low-Medium | Medium | Open |
| R-12 | Technical / External | MCP/A2A ecosystem churn breaks a dependency | Medium | Medium | Open |
| R-13 | Data / ML | Generated comments don't match their requested sentiment | Medium | High | Mitigating |

---

## Detail

### R-01 — Solo build, no peer review
**Description:** No second person to catch design blind spots, review code, or push back on a bad assumption before it's built on top of.
**Mitigation:** CI with real test coverage; eval harnesses (routing, forecast backtest, sentiment holdout, QA catch rate) substitute for a reviewer's judgment with measurable output instead; sprint retros are the deliberate moment to self-audit rather than assume things are fine.
**Review trigger:** Every sprint retro — explicitly ask "what would a reviewer have flagged this sprint?"

**Update 2026-09-25:** CI is live (GitHub Actions: ruff lint, the offline unit suite, and the live grants integration suite against a Postgres 16 service container, with `REQUIRE_INTEGRATION_DB=1` so a missing database fails rather than skips). The eval harnesses are still to be built. Status stays Open.

### R-02 — Runtime budget depends on unconfirmed credit coverage
**Description:** The cost plan assumes Google AI student credits cover Gemini runtime inference for all five agents across 12 weeks. Coverage and expiry haven't been confirmed.
**Mitigation:** Confirm in Sprint 1 — this is a named open item, not an assumption to defer. `packages/llm/` keeps every agent provider-agnostic, so a swap to another provider is a config change if credits fall short.
**Update 2026-09-22 (ADR-029):** Student credits confirmed not available. Development inference moved to the Gemini API free tier with Flash-Lite defaults, so credit coverage is no longer the exposure. What remains: free-tier rate limits (429 backoff required in `packages/llm/`) and any paid Sprint 5 eval spend, which runs in a separate spend-capped project. Free-tier limits are now confirmed in AI Studio (2026-09-22): Flash-Lite 15 RPM / 250K TPM / 500 RPD, Flash models 20 RPD, and no free-tier quota for Pro models. The remaining exposure is eval volume: a full routing eval run (300–700 requests) can exceed the 500 RPD Flash-Lite cap, so Sprint 5 evals must be split across days or run on a paid, spend-capped project. If the paid route is taken, that project's cost is not yet included in the budget estimate, which so far covers only the ~$20–30 Pro-for-QA test. Pricing it is a Sprint 4 planning item.
**Review trigger:** Sprint 1 close-out. Re-check if GCP budget alerts fire.

**Update 2026-09-24 (ADR-041):** Paid spend now exists: remaining Flash-Lite corpus generation runs on a separate paid project (about $2 at list prices), bounded by a $10 project budget alert, the $50/$80 GCP budget alerts, and a hard per-session request cap in `build_corpus.py`.

**Update 2026-09-25:** Paid spend is bounded by a code-enforced per-session request cap in `build_corpus.py`, a $5 prepaid balance on the paid project with auto-reload off, and budget alerts at $10 (project) and $50/$80 (billing account). Corpus generation cost about $1.40 (estimate from list prices, not billing data). Status stays Mitigating.

### R-03 — Cloud Run build/deploy decoupling
**Description:** A prior academic project hit successful Cloud Builds that didn't produce active Cloud Run revisions — a decoupled build/deploy pipeline. Same deployment target, same failure mode plausible.
**Mitigation:** Wire an explicit Cloud Build trigger → deploy step rather than an image push alone; verify revision promotion immediately on the first Sprint 5 deploy rather than waiting until later to check.
**Review trigger:** First deploy attempt in Sprint 5 — don't wait for the retro if this recurs, it blocks the sprint goal directly.

### R-04 — Sentiment task has weak natural verifiability
**Description:** Unlike reporting (deterministic) or forecasting (standard backtest metrics), sentiment has no natural ground truth. A QA check that just re-runs the same model is circular and proves nothing.
**Mitigation:** `sentiment_labels` holdout the sentiment agent never reads; the `rating` field on `service_feedback` gives QA a second, independent cross-check signal. Both already designed in — this is why status is "Mitigating" rather than "Open." Both are now enforced by database grant, not convention: the sentiment role has no grant on `sentiment_labels`, and since ADR-027 its `service_feedback` grant is column-level and excludes `rating`, so the second signal is independent by construction. `tests/integration/test_access_matrix_grants.py` asserts both against the live database.
**Review trigger:** Sprint 4, when the QA agent's sentiment-verification path is actually built and tested against real generated data.

### R-05 — QA retry loop cost or latency runaway
**Description:** Multi-agent systems with a verify-and-revise loop can fan out token usage and wall-clock time quickly if unbounded.
**Mitigation:** Bounded at 2 retries with escalation on final failure (ADR-022); per-run cost caps and model tiering already specified in the budget plan.
**Review trigger:** Sprint 4, once the loop is live and real cost/latency numbers exist to check against the plan.
**Update 2026-09-22 (ADR-034):** Latency is also bounded by a 120-second end-to-end ceiling, after which the request returns a degraded result with an escalation flag. Check in Sprint 5's first deploy whether cold starts alone approach the ceiling.

### R-06 — A2A overhead consumes disproportionate solo dev time
**Description:** A2A's Agent Cards and task-lifecycle machinery are more plumbing than a single-codebase system strictly needs. Solo, on a fixed timeline, that overhead is a real opportunity cost.
**Mitigation:** Sprint 2 is deliberately the proof sprint for this exact risk — if the A2A path is disproportionately slow to stand up, that's the signal to reconsider before three more agents are built on top of it. No fallback plan currently drafted; if this risk is realized, the honest move is a documented scope conversation, not silent workarounds.
**Review trigger:** Sprint 2 retro, explicitly.

### R-07 — Synthetic generator produces a degenerate distribution
**Description:** Random or careless generation could produce a sentiment mix that's not realistic, a forecast signal that isn't recoverable, or an incident rate that doesn't resemble a real business — quietly invalidating every downstream metric.
**Mitigation:** Explicit validation step planned for Sprint 1 (data-dictionary.md §8 constraints and invariants); target distributions locked in advance (ADR-018, ADR-019, ADR-021) rather than left to chance.
**Review trigger:** Immediately after first generation run, Sprint 1 — before any agent code is built against the data.

**Update 2026-09-25:** Still Open until `validate.py` runs against generated data. The feedback corpus is complete (13,184 comments, q99 rule); `generate.py` is in progress on `feat/generate`.

**Update 2026-09-25 (dataset loaded):** The dataset is generated and loaded into local Postgres (20,230 requests; sentiment mix, incident rate and anomalies land on target in the dry run). `validate.py` (signal recovery) is next. Status stays Open until it passes.

**Update 2026-09-25 (validate.py):** The review trigger is met: `validate.py` passed 66 of 66 checks against the loaded database, with truth read from `generation_parameters`. Headline results: sentiment mix 50.2/22.4/19.6/7.8; incidents on 10.2% of completed requests, missed_sla 24.4% of incidents; recovered growth 8.5% (designed 8%); seasonal peak-to-trough 0.39 against 0.42 designed in the same K=3 basis (the raw weekly design is 0.50, and three harmonics cannot follow the two-week December trough); residual sd 11.7% (designed effective ~10.6%); regional drop z 3.53; account drop 93% at account level; severity->sentiment, SLA->incident and rating->sentiment couplings all consistent with their designs (p >= 0.07). Status -> Monitoring: re-run `validate.py` after any regeneration.

### R-08 — Schema or data drifts toward resembling employer's real system
**Description:** The original draft schema showed signs of being modeled too closely on a real production system. The underlying pull toward "use what I already know" doesn't disappear just because the initial fields were corrected.
**Mitigation:** ADR-012 and ADR-013 establish the discipline; any new field added later should be sourced from general field-service domain principles, checked against this standard before being added, not copied from familiarity.
**Review trigger:** Any time a new table or field is proposed — a standing check, not a one-time fix.

### R-09 — Course rubric diverges from the assumed deliverable plan
**Description:** The academic deliverable sequencing in `architecture.md` §10 is a reasonable guess at typical capstone requirements, not a confirmed match to the actual rubric.
**Mitigation:** Reconcile explicitly against the real rubric — flagged as an open item since the plan was first drafted and still unresolved.
**Review trigger:** Should be closed in Sprint 1. If still open at the Sprint 2 retro, treat that as a process failure worth naming. Added 2026-09-25: each deliverable's rubric is checked when drafting starts.

**Update 2026-09-25:** Still open at the end of Sprint 1. Per this entry's review trigger, if it is still open at the Sprint 2 retro, that is a process failure to name there.

**Update 2026-09-25:** The actual deliverables for weeks 1-2 are now known — Proposal/Business Case, Detailed Requirements Analysis, and weekly status reports — and they differ from the assumed plan in `architecture.md` §10 and the sprint log. Partly realised. Reconciling the full milestone plan is the next step, after the academic documents are reviewed. Weekly status reports are a recurring deliverable the plan must budget. Status: Mitigating.

**Update 2026-09-25 (calendar reconciled):** The actual deliverable calendar is now known and mapped to sprints in `architecture.md` §10 and `sprint-log.md`: `01` (due 09-27) and `02` (due 10-04) complete; `03` and `04` due 10-18 (Sprint 3); `05` due 11-01 and `06` due 11-08 (Sprint 4); weekly status reports through 11-22; final product due 12-05. The remaining exposure is per-deliverable rubric content, which is not yet known, and the schedule conflicts flagged for Sprint 2 planning (`sprint-log.md`): `06` due before the first deployment and before the Sprint 6 runbook work; `05` due before the eval runs, with the golden set needed by Sprint 4; `03` and `04` both due mid-Sprint 3; and whether a separate project charter is due. Status: Mitigating → Monitoring.

### R-10 — Sprint 6 buffer erodes from earlier slippage
**Description:** Sprint 6 is the only planned buffer in a 12-week solo timeline. Without a second person creating schedule pressure, slippage in Sprints 1–5 tends to get quietly absorbed rather than confronted.
**Mitigation:** Treat any missed sprint goal as an immediate scope conversation at that sprint's retro, not something to "catch up on later." Scope expansion is only considered if genuinely ahead, per the working agreement.
**Review trigger:** Every sprint retro — explicitly compare actual progress against the plan, not just against what felt productive.

**Update 2026-09-25:** The Sprint 1 goal was missed: the generator carries into Sprint 2, which is also the highest-risk sprint (first vertical slice through A2A and MCP). Kept Open; the Sprint 1 retro decides whether this counts as realised.

**Update 2026-09-25 (goal met):** The Sprint 1 goal was met on 2026-09-25, inside the sprint; the remaining Sprint 1 items (CI, the Alembic ruff hook) are being finished in Sprint 1 rather than carried over. This supersedes the earlier same-day note that the goal was missed. Status stays Open: the buffer risk applies to every sprint.

**Update 2026-09-25 (Sprint 3 academic load):** With the calendar reconciled, Sprint 3 carries two academic deliverables due the same day (`03` Planning & Management and `04` Design & Solution Architecture, both 2026-10-18) on top of the heaviest engineering sprint after Sprint 2 (MCP servers #2 and #3, the sentiment and forecast agents, and three-way routing). Sprint 4 then carries `05` and `06`. Any Sprint 2 slip lands directly on that load. Status stays Open.

### R-11 — Vendor pricing or model access changes mid-project
**Description:** Gemini pricing, free-tier rate limits, or model availability could change over a 12-week window in ways that affect the budget plan (see ADR-029).
**Mitigation:** Provider-agnostic LLM interface (ADR-006) keeps a provider swap mechanically cheap; GCP budget alerts at $50/$80 serve as an early warning regardless of root cause.
**Review trigger:** Any GCP budget alert firing; otherwise passive monitoring.

### R-12 — MCP/A2A ecosystem churn breaks a dependency
**Description:** Both protocols are new and moving fast — MCP had its largest spec revision to date in July 2026. An SDK update mid-project could introduce breaking changes.
**Mitigation:** Pin SDK versions at project start; don't chase spec updates mid-build. The project targets the 2026-07-28 MCP spec and A2A v1.0 as documented in `architecture.md` §3 — treat that as fixed unless a specific reason forces an upgrade.
**Review trigger:** Only if a dependency update is being considered — otherwise not time-based.

### R-13 — Generated comments don't match their requested sentiment
**Description:** `feedback_text` is LLM-generated to a requested label (ADR-030), and `sentiment_labels.true_sentiment` records that request, not a verified reading of the text. Comments that drift from their label would make the sentiment model's accuracy look worse than it is — the model gets marked wrong for reading the text correctly. Hard cases can fail the other way: sarcasm an LLM writes on request is often obvious, so "hard" comments may be easier than labeled and inflate hard-case accuracy.
**Mitigation:** Sampled label validation in `validate.py` before the corpus is accepted, plus exact and near-duplicate rejection so no comment spans the training and holdout splits.
**Review trigger:** Corpus generation in Sprint 1.

**Update 2026-09-23 (ADR-036):** The bake-off confirmed label drift for neutral: the generator wrote neutral as intended only about half the time, and a flat report of a working fix read as satisfied to both the human reviewer and the judge. Mitigation: a Gemma 4 judge labels every comment, and plain comments whose judge label differs from the intended one are rejected and replaced from spares; a blind, stratified review of ~200 comments follows. Hard cases (sarcastic, implicit) are not judge-filtered, so filtering cannot inflate hard-case accuracy. Remaining exposure: the human evidence is a single annotator, and believability is unproven (10 of 24 v3 comments sounded AI-written). Status: Open → Mitigating.

**Update 2026-09-23 (ADR-040):** Labels are now specification-defined: the ADR-036 written definitions are the ground truth, plain labels are generator intent confirmed by the judge, and hard-case labels are generator intent with their judge disagreement rate reported. The ~200-comment human review is reduced to a ~30-comment sanity spot-check for unusable comments, with no agreement scoring or regeneration gate. The remaining exposure is that the specification may not match every reader — the owner's own reviews read the problem-plus-recovery boundary both ways — and this is stated as a limitation. Status stays Mitigating.

**Update 2026-09-25 (final corpus):** Judge agreement before filtering, by class: mixed 95%, negative plain 94%, positive plain 82%, neutral plain 56%. Hard-case judge disagreement, unfiltered by design: positive implicit 20%, sarcastic 12%, negative implicit 3%. Accepted neutrals are 73% administrative, 19% status, and 8% minimal, because the judge accepted administrative notes far more often (78%) than status (27%) or minimal (52%), and most minimal comments were lost to duplicate rejection first. That skew likely makes neutral accuracy optimistic; the mitigation is per-kind reporting in the sentiment eval (Sprint 3). Status stays Mitigating.

---

## Closed / Realized Risks
*(move entries here as they resolve, with the outcome noted — this becomes useful evidence for the final paper's lessons-learned section)*

*(none yet)*
