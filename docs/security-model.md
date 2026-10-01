# Security Model — Agentic Service Operations Intelligence Platform

*Seeded 2026-09-30 from `data-dictionary.md` §7 (the access matrix) and `architecture.md` §5.
Completed while drafting `04` in Sprint 3. Where this file and §7 disagree, §7 and
`packages/db_models/src/db_models/access_matrix.py` are the authority.*

## Database access: what the grants guarantee

Each agent reaches the database only through its own MCP server, and each MCP server
connects as its own least-privilege Postgres role. The grants are executable, not prose:
`access_matrix.py` defines them, the roles migrations apply them as frozen snapshots
(ADR-027), and `tests/integration/test_access_matrix_grants.py` asserts the migrated database
grants exactly that, reads and writes, in CI. The Postgres `PUBLIC` defaults are revoked
(ADR-025).

Four guarantees follow from the matrix and hold at the database level, whatever a prompt
or a model does:

1. **No agent reads `contacts`, so customer PII never enters a prompt.** No agent role
   (`app_reporting`, `app_sentiment`, `app_forecast`, `app_qa`) holds any grant on
   `contacts` or `internal_users`. Only the generator role writes them.
2. **The sentiment agent can't read `sentiment_labels`, `incidents` or the star rating.**
   `app_sentiment` has a column-level grant on exactly four `service_feedback` columns
   (`feedback_id`, `request_id`, `submitted_at`, `feedback_text`) and nothing else. It can't
   check itself against the ground truth, staff-written incident notes can't reach its
   pipeline, and `rating` stays an independent cross-check for QA (R-04, ADR-027).
3. **The forecast agent sees three `service_requests` columns only.** `app_forecast` has a
   column-level grant on `request_id`, `scheduled_datetime` and `service_type`, and no
   grant on any other table. Billing, cancellation detail and every account, contact and
   technician identifier are withheld (ADR-035).
4. **`app_qa` is the broadest reader, limited by its read-only role.** Verification needs
   sources the specialists can't see, so `app_qa` can SELECT every operational table except
   `contacts` and `internal_users`, plus `sentiment_labels` and `generation_parameters`. It
   holds no INSERT, UPDATE or DELETE grant anywhere.

The reporting agent's `service_feedback` grant also excludes `feedback_text`, so it can
count and average ratings but can't read a customer's words (ADR-025).

## Threat model

The attacker this design assumes is hostile text, not a hostile operator: a customer
comment, or a question typed into the UI, crafted to make a model call a tool or reveal
data it shouldn't. The defences are structural. No MCP server exposes raw SQL, only
narrow, purpose-built tools (`architecture.md` §5). Each agent connects only to its own MCP
server, which holds only its own role's credentials. The role's grants bound what any
manipulated call can return. A compromised sentiment agent, for example, has no connection to
the forecasting tools and no grant that reaches billing. The highest-value target is the
QA agent. It reads the most (guarantee 4), including the sentiment ground truth, and it
consumes specialists' outputs, which may carry injected text from feedback comments. Its
read-only role means a successful attack can disclose data but not alter it, and it still
can't reach customer PII. The two broadest credentials sit outside the agents entirely.
The `app_generator` role has full access to every table and is used at load time only, by
`data/generator/load.py`. Its credentials must never be present in any deployed service:
not in a service image, a Cloud Run environment, or the Secret Manager entries a service can
read. The same holds for the Postgres admin credentials the migrations run as. Today only
`mcp_incidents` receives database credentials (`app_reporting`) in docker-compose, and CI
uses ephemeral generator credentials that never leave the workflow.

## Still to write (Sprint 3, with `04`)

- MCP and A2A controls: tool scoping per server, Agent Card exposure, authentication
  between services (IAM ID tokens in the Sprint 4 deploy, ADR-045).
- Prompt-injection handling on the paths that ingest free text (feedback comments,
  questions).
- Secrets management in deployment (Secret Manager) and how each service's credentials are
  scoped.
- Logging: what is logged with each tool call and trace id, and what is redacted.
