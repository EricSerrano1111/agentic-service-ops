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
| R-02 | Budget | Runtime budget depends on unconfirmed Google AI credit coverage | Medium | High | Mitigating |
| R-03 | Deployment | Cloud Run build/deploy decoupling (recurred before) | Medium-High | Medium | Open |
| R-04 | ML / Verification | Sentiment task has weak natural verifiability | Medium | Medium-High | Mitigating |
| R-05 | Cost / Technical | QA retry loop cost or latency runaway | Low-Medium | Medium | Mitigating |
| R-06 | Schedule / Scope | A2A overhead consumes disproportionate solo dev time | Medium | Medium | Open |
| R-07 | Data | Synthetic generator produces a degenerate distribution | Medium | High | Open |
| R-08 | Compliance | Schema/data drifts toward resembling employer's real system | Low | High | Mitigating |
| R-09 | Academic | Course rubric diverges from the assumed deliverable plan | Medium | Medium-High | Open |
| R-10 | Schedule | Sprint 6 buffer erodes from earlier slippage | Medium | High | Open |
| R-11 | External / Budget | Vendor pricing or model access changes mid-project | Low-Medium | Medium | Open |
| R-12 | Technical / External | MCP/A2A ecosystem churn breaks a dependency | Medium | Medium | Open |

---

## Detail

### R-01 — Solo build, no peer review
**Description:** No second person to catch design blind spots, review code, or push back on a bad assumption before it's built on top of.
**Mitigation:** CI with real test coverage; eval harnesses (routing, forecast backtest, sentiment holdout, QA catch rate) substitute for a reviewer's judgment with measurable output instead; sprint retros are the deliberate moment to self-audit rather than assume things are fine.
**Review trigger:** Every sprint retro — explicitly ask "what would a reviewer have flagged this sprint?"

### R-02 — Runtime budget depends on unconfirmed credit coverage
**Description:** The cost plan assumes Google AI student credits cover Gemini runtime inference for all five agents across 12 weeks. Coverage and expiry haven't been confirmed.
**Mitigation:** Confirm in Sprint 1 — this is a named open item, not an assumption to defer. `packages/llm/` keeps every agent provider-agnostic, so a swap to another provider is a config change if credits fall short.
**Update 2026-09-22 (ADR-029):** Student credits confirmed not available. Development inference moved to the Gemini API free tier with Flash-Lite defaults, so credit coverage is no longer the exposure. What remains: free-tier rate limits (429 backoff required in `packages/llm/`) and any paid Sprint 5 eval spend, which runs in a separate spend-capped project. Free-tier limits are now confirmed in AI Studio (2026-09-22): Flash-Lite 15 RPM / 250K TPM / 500 RPD, Flash models 20 RPD, and no free-tier quota for Pro models. The remaining exposure is eval volume: a full routing eval run (300–700 requests) can exceed the 500 RPD Flash-Lite cap, so Sprint 5 evals must be split across days or run on a paid, spend-capped project.
**Review trigger:** Sprint 1 close-out. Re-check if GCP budget alerts fire.

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

### R-06 — A2A overhead consumes disproportionate solo dev time
**Description:** A2A's Agent Cards and task-lifecycle machinery are more plumbing than a single-codebase system strictly needs. Solo, on a fixed timeline, that overhead is a real opportunity cost.
**Mitigation:** Sprint 2 is deliberately the proof sprint for this exact risk — if the A2A path is disproportionately slow to stand up, that's the signal to reconsider before three more agents are built on top of it. No fallback plan currently drafted; if this risk is realized, the honest move is a documented scope conversation, not silent workarounds.
**Review trigger:** Sprint 2 retro, explicitly.

### R-07 — Synthetic generator produces a degenerate distribution
**Description:** Random or careless generation could produce a sentiment mix that's not realistic, a forecast signal that isn't recoverable, or an incident rate that doesn't resemble a real business — quietly invalidating every downstream metric.
**Mitigation:** Explicit validation step planned for Sprint 1 (data-dictionary.md §8 constraints and invariants); target distributions locked in advance (ADR-018, ADR-019, ADR-021) rather than left to chance.
**Review trigger:** Immediately after first generation run, Sprint 1 — before any agent code is built against the data.

### R-08 — Schema or data drifts toward resembling employer's real system
**Description:** The original draft schema showed signs of being modeled too closely on a real production system. The underlying pull toward "use what I already know" doesn't disappear just because the initial fields were corrected.
**Mitigation:** ADR-012 and ADR-013 establish the discipline; any new field added later should be sourced from general field-service domain principles, checked against this standard before being added, not copied from familiarity.
**Review trigger:** Any time a new table or field is proposed — a standing check, not a one-time fix.

### R-09 — Course rubric diverges from the assumed deliverable plan
**Description:** The academic deliverable sequencing in `architecture.md` §10 is a reasonable guess at typical capstone requirements, not a confirmed match to the actual rubric.
**Mitigation:** Reconcile explicitly against the real rubric — flagged as an open item since the plan was first drafted and still unresolved.
**Review trigger:** Should be closed in Sprint 1. If still open at the Sprint 2 retro, treat that as a process failure worth naming.

### R-10 — Sprint 6 buffer erodes from earlier slippage
**Description:** Sprint 6 is the only planned buffer in a 12-week solo timeline. Without a second person creating schedule pressure, slippage in Sprints 1–5 tends to get quietly absorbed rather than confronted.
**Mitigation:** Treat any missed sprint goal as an immediate scope conversation at that sprint's retro, not something to "catch up on later." Scope expansion is only considered if genuinely ahead, per the working agreement.
**Review trigger:** Every sprint retro — explicitly compare actual progress against the plan, not just against what felt productive.

### R-11 — Vendor pricing or model access changes mid-project
**Description:** Gemini pricing, free-tier rate limits, or model availability could change over a 12-week window in ways that affect the budget plan (see ADR-029).
**Mitigation:** Provider-agnostic LLM interface (ADR-006) keeps a provider swap mechanically cheap; GCP budget alerts at $50/$80 serve as an early warning regardless of root cause.
**Review trigger:** Any GCP budget alert firing; otherwise passive monitoring.

### R-12 — MCP/A2A ecosystem churn breaks a dependency
**Description:** Both protocols are new and moving fast — MCP had its largest spec revision to date in July 2026. An SDK update mid-project could introduce breaking changes.
**Mitigation:** Pin SDK versions at project start; don't chase spec updates mid-build. The project targets the 2026-07-28 MCP spec and A2A v1.0 as documented in `architecture.md` §3 — treat that as fixed unless a specific reason forces an upgrade.
**Review trigger:** Only if a dependency update is being considered — otherwise not time-based.

---

## Closed / Realized Risks
*(move entries here as they resolve, with the outcome noted — this becomes useful evidence for the final paper's lessons-learned section)*

*(none yet)*
