# Production-grade checklist audit (`architecture.md` §7)

*Dated 2026-10-16. S6-P1; owner-decided 2026-10-16; assistant-drafted.*

This audits the 12 items of `docs/architecture.md` §7, "Definition of Production-Grade", as that section stood on `main` at `fa2c7cd` on 2026-10-16: 12 unticked boxes except item 10 (least-privilege database roles), which is ticked. It is an audit, not a build: no model call, no GCP write, no `ops-db` start and no code change were made.

**Ordering disclosure (2026-10-16).** The criteria below were meant to be committed before any evidence was gathered. One thing came first: the read-only `gcloud run services describe` and `get-iam-policy` reads of the six services were taken at about 22:47Z, to apply the prompt's stop rule (the serving image must be `9ab7c77`) before writing any verdict. Before the criteria were written, the assistant had also read `docs/deploy-window-log.md`, the Sprint 6 section of `docs/sprint-log.md`, `docs/security-model.md` sections 2 to 5 and `README.md`. The criteria were written from §7's wording, the ADR titles and the project's scale, not from those reads' findings, but the reader should know the order. No other evidence was read between this paragraph and the criteria commit.

## Criteria

Each criterion says what "met" means at this project's scale: a solo, six-sprint capstone on Cloud Run with a roughly $100 budget (`architecture.md` §9). Verdict vocabulary (applied in the evidence commit): `Met, deployed` · `Met, offline only` · `Partly met` · `Deferred` · `Not met`.

Where §7's wording is vague, the reading chosen is stated. §7 itself says an item may be "explicitly scoped out with a documented reason"; a verdict of `Deferred` needs that reason in a record, not in this audit.

### 1. Containerized services, reproducible builds

- **Criterion.** Every deployable service (gateway, orchestrator, three agents, QA, and the three MCP servers) builds from its own Dockerfile in a clean checkout, runs in the local compose stack, and runs on Cloud Run from the image the build produced. "Reproducible" is read as **dependency reproducibility**: every Python dependency is installed from the committed `uv.lock` (`--locked`), the same lock feeds CI and the images, and the deployed image is identifiable by the commit it was built from (tag = commit SHA). It is **not** read as bit-for-bit identical images, and it does **not** require base images pinned by digest. Reason: §7 says "reproducible builds", the ADR that pins dependencies (ADR-047) is about the lock, and digest-pinning is a supply-chain hardening a solo capstone does not need. If base images turn out to be floating tags, that is reported as a limit on the verdict, not as a failure of the criterion.
- **Required or portfolio.** Required. Containers are the unit of deployment on Cloud Run (ADR-045, ADR-079). The digest-pinning stricter reading would be portfolio, and is not applied.

### 2. Config and secrets management: no hardcoded credentials

- **Criterion.** No credential value is committed or baked into an image; configuration comes from the environment. On the deployed system, each secret lives in Secret Manager and is mounted only into the container that needs it, and no secret value appears in logs. Locally, credentials come from the gitignored `.env`, and a test or check guards against literals in deployed files. "No hardcoded credentials" is checked by search of the repository and by the existing guard tests, not by a full history scan (secret scanning on pushes is outside §7 and is listed in the outside-the-checklist section).
- **Required or portfolio.** Required (ADR-028 and ADR-079 make it a design rule, not a flourish).

### 3. Structured logging with trace IDs correlated across agent hops

- **Criterion.** Every service writes JSON log lines through one formatter. One trace ID is minted or accepted at the entry point and appears on the log lines of every hop of a request: gateway, orchestrator, A2A agent, MCP server and QA agent, including web-server access lines (ADR-108). Met on the **deployed** system means a read of Cloud Logging shows one trace across more than one service. Logging the question text or secrets is a limit on the verdict, not a failure of "structured" or "correlated"; the redaction gaps are stated as limits (L-98 and the L-60 remainder).
- **Required or portfolio.** Required. Without it a failure across seven processes cannot be diagnosed (ADR-108).

### 4. Health checks and readiness probes on every service

- **Criterion.** Every service exposes a liveness endpoint (`/healthz`), and every service that has a dependency (an agent's MCP sidecar, an MCP server's database) exposes a readiness endpoint (`/readyz`) that checks it. "Readiness probe" is read for Cloud Run, which has **startup and liveness probes, not a separate readiness probe**: the criterion is a startup probe on every container that gates on `/readyz` where a dependency exists, plus the endpoints for liveness. §7 says "every service", so the gateway, orchestrator and QA agent are in scope. A configured Cloud Run `livenessProbe` is **not** required by §7's wording; if absent it is stated as a limit, and as a finding if a doc claims otherwise.
- **Required or portfolio.** Required: the sidecar start-up ordering depends on it (ADR-079).

### 5. Bounded retries, timeouts and circuit breaking on all inter-agent calls, within the 120-second ceiling

- **Criterion.** "All inter-agent calls" is read as: orchestrator to each specialist agent (A2A), orchestrator to QA, and the model transport (Gemini) called by the orchestrator, agents and QA. It does **not** include an agent's call to its own MCP sidecar over localhost, which carries no network risk of the same kind (ADR-079); if that call has a timeout anyway, it is noted. Met requires: one request deadline passed through every hop; a per-hop timeout that fits inside 120 s; a bounded retry; a breaker per specialist and for QA and the model transport; a bounded revision loop; and a defined result when a bound is hit. **Deployed** evidence means a bound or breaker was seen to act on Cloud Run; code and tests alone make the item `Met, offline only`. Retry *logging* is a separate sub-claim and is judged on its own evidence.
- **Required or portfolio.** Required for the 120 s ceiling and the NFR it serves (ADR-077, ADR-088); the breaker is deliberately minimal (ADR-077 titles it "minimal").

### 6. Graceful degradation: defined behaviour when any specialist agent is unavailable

- **Criterion.** There is a documented behaviour (ADR-088) for each unavailable dependency (routing, each specialist, QA); it returns a defined, honest result (HTTP 200, marked degraded and not verified) rather than an error or a hang; it is covered by tests; and a degraded answer is visible to the operator (the alert, ADR-112). Met on the deployed system means a real degraded path ran on the **current** build. A degradation observed on a previous build, or a synthetic alert entry, is evidence for the monitoring and for the previous build's behaviour only.
- **Required or portfolio.** Required: §7 names it, and ADR-088 defines the behaviour.

### 7. Test suite: unit and integration

- **Criterion.** An offline unit suite and a live-database integration suite exist, both run in CI on every push and pull request, and pass on `main`. "Integration" is read as the repository's own meaning (the grants and MCP-figures suites against Postgres), not a deployed end-to-end suite. Judged offline, because the criterion is about the suite itself. The two Cloud SQL-scoped suites deferred under L-78 are a limit on the verdict, not on the criterion.
- **Required or portfolio.** Required.

### 8. Eval harness

- **Criterion.** §7 says only "(see below)". Read as: the evaluation strategy in §8 has a working harness whose results are committed: routing accuracy on a labelled set with failure analysis, QA fault-catch measurement, and the golden-set run, each with dated results under `evals/results/`. The forecast and sentiment evals named in §8 count if their results exist. Not required: every §8 target being met. FR-03 failing its gates is a result to be reported, not a missing harness. Judged on the harness and committed results, not on re-running anything (no model calls in this audit).
- **Required or portfolio.** Required for the capstone (`architecture.md` §8 calls the routing harness the highest-value artifact; ADR-044 covers the evaluation report).

### 9. CI pipeline

- **Criterion.** Split in two, because §7 conflates them. **CI:** lint (`ruff check` and `format --check`), unit and integration run in GitHub Actions on every push and pull request to `main`, with CI's own ephemeral credentials and no model call. **CD:** a build trigger that builds the images, deploys, and verifies the revision (ADR-045, ADR-081, ADR-085). §7's own text says CD was proved on the reporting slice, and then names two conditions to reach the Z2 state: the paid-mode YAML sync and the docs-only merge check. The item is met only if CI is met and CD is **either** working as a default path **or** explicitly scoped to manual runs with a documented reason (ADR-105 disables the trigger outside deploy windows). How the six services were actually deployed is reported as a fact, not judged against the criterion.
- **Required or portfolio.** CI is required. Continuous deployment of a system with a stopped database and a spend cap is demonstrated for portfolio value; ADR-105's disabled trigger is the documented scope-out.

### 10. Least-privilege database roles per agent

- **Criterion.** Each runtime agent connects as its own database role with only the grants the access matrix gives it; offline roles (generator, eval, train) are not present in any deployed file; the grants are asserted by an automated test in CI against a real Postgres. This item is already ticked; the audit re-checks that the tick still holds, and re-checks nothing else about it.
- **Required or portfolio.** Required (ADR-023, ADR-063).

### 11. API cost guardrails and per-run caps

- **Criterion.** Spend on the paid model key is bounded at more than one level, and each level is a mechanism that acts, not a note: a per-run or per-request cap in code; a per-session or per-driver cap on evaluation runs; a per-invite or daily cap at the public entry point; a hard budget on the paid key (a prepaid balance or project cap); and billing alerts. Each guardrail is listed with its evidence and marked as a **list-price estimate** where its figure is computed from prices rather than read from a bill (L-71). Met requires that the code-level caps are tested and that the deployed limits (caps, balance, alerts) are read from the deployed system or a dated record. Not required: a programmatic stop on the account balance (L-93 keeps it an option).
- **Required or portfolio.** Required: the $100 budget is a design constraint (`architecture.md` §9) and a public endpoint spends the owner's money (ADR-107).

### 12. README with architecture diagram and local setup that actually works from clean

- **Criterion.** Two parts, both required, because §7 names both. **(a) Setup from clean:** a fresh clone, following the README's setup steps literally and in order, either works or stops at the first step that needs something a clean machine cannot have (a model key, a gitignored file, GCP access); the README must say before that step that it is needed. A README that stops a new developer at a step it did not warn about is a failure of "actually works from clean" even if the step is mentioned elsewhere in the README. The verdict for this half comes from the fresh-clone check (section 3 of the prompt), not from reading the README. **(b) Architecture diagram:** the README contains an architecture diagram (an image or a rendered diagram). A placeholder is not a diagram.
- **Required or portfolio.** Required: §7 says it, and the Solutions Architect narrative depends on the diagram (`architecture.md` §6 UI note).

## Changes to a criterion after evidence

*None yet. Any change is added here as a dated line under the item it changes, with the original kept.*
