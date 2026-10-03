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

Eight guarantees follow from the matrix and hold at the database level, whatever a prompt
or a model does, and three more follow from how the sentiment, forecast and reporting
agents are built:

1. **No agent reads `contacts`, so customer PII never enters a prompt.** No agent role
   (`app_reporting`, `app_sentiment`, `app_forecast`, `app_qa`) holds any grant on
   `contacts` or `internal_users`. Only the generator role writes them.
2. **The sentiment agent can't read `sentiment_labels`, `incidents`, the star rating or
   any account.** `app_sentiment` has a column-level grant on exactly four
   `service_feedback` columns (`feedback_id`, `request_id`, `submitted_at`,
   `feedback_text`), on `service_requests` (`request_id`, `location_id`) and `locations`
   (`location_id`, `region`) to resolve a comment's region, and on its own
   `sentiment_predictions`; nothing else. It can't check itself against the ground truth,
   staff-written incident notes can't reach its pipeline, `rating` stays an independent
   cross-check for QA (R-04, ADR-027), and it has no path to `accounts`, `account_id` or a
   site's address (ADR-067).
3. **The forecast agent sees three `service_requests` columns only.** `app_forecast` has a
   column-level grant on `request_id`, `scheduled_datetime` and `service_type`, and no
   grant on any other table. Billing, cancellation detail and every account, contact and
   technician identifier are withheld (ADR-035).
4. **`app_qa` is the broadest reader, limited by its read-only role.** Verification needs
   sources the specialists can't see, so `app_qa` can SELECT every operational table except
   `contacts` and `internal_users`. It holds no INSERT, UPDATE or DELETE grant anywhere.
5. **The runtime QA role can't read gold labels or generator parameters.** `app_qa` has no
   grant on `sentiment_labels` or `generation_parameters` (ADR-055, ADR-063). Those are read
   only by the offline `app_eval` role, which no deployed service holds: a unit test fails
   if any compose service, Dockerfile or file under `services/` references its credentials.
6. **Training can't read `rating` or `generation_parameters`.** The offline `app_train`
   role reads `sentiment_labels` and exactly the columns the runtime models read, so a model
   trained on the stars, or a forecast fitted to the generator's answer key, is ruled out by
   grant (ADR-027, ADR-058, ADR-063). Like `app_eval`, it is never held by a deployed
   service. Nor can it read `sentiment_predictions`, so the model never trains on its own
   output (ADR-067).
7. **The sentiment server writes only to its own predictions table, and no tool exposes a
   write.** `app_sentiment` holds INSERT on `sentiment_predictions` and nothing else that
   writes: no UPDATE or DELETE there, no write anywhere else, so a stored prediction can't
   be rewritten or erased by the server. Storing happens inside `mcp_feedback`
   (`ensure_scored`), never as a tool: both tools are reads, and neither accepts SQL or
   free text that reaches a query (ADR-023, ADR-067). Every other runtime role is
   read-only.
8. **Customer text reaches an LLM only through `get_feedback_examples`, at most 5 comments
   per call.** `get_sentiment_summary` returns counts, shares and buckets with no text and no
   comment ids; `get_feedback_examples` rejects a `limit` above 5. This bounds how much
   customer text, and how much injected text, any one call can put into a prompt
   (ADR-067).
9. **On the sentiment path, no customer comment is sent to any LLM at answer time.** The
   sentiment agent's only model call parses the user's question; figures come from
   `mcp_feedback` and the answer is rendered from templates, so the up-to-3 comments
   returned by `get_feedback_examples` reach only the template and the user (ADR-068).
   Customer text therefore has no model to instruct on this path. A unit test asserts no
   quoted comment appears in the parse prompt. **Sprint 4 QA must keep this true or say
   where it doesn't:** ADR-056 gives QA one LLM call that checks interpretation over the
   specialist's output, and a sentiment answer's text includes the quoted comments. Either
   QA's call is given the answer without the quoted comments, or this guarantee is
   narrowed to "no comment reaches a model except QA's interpretation check", and the QA
   prompt is treated as a prompt-injection surface (as "Still to write" already notes).
10. **`mcp_volume` never returns forecast numbers for a slice-band the manifest marks
    unserved, and the forecast path carries no customer text.** The server reads the
    `volume_v2` manifest's ADR-071 serving table and puts a week's point and ranges in
    its result only when that slice-band is served; otherwise the week carries its
    flag and the band its shown error, nothing else. The shared `ForecastWeek` contract
    rejects an unserved week carrying numbers, so neither the agent nor the orchestrator
    can pass one on (ADR-072). The forecast path reads three `service_requests` columns
    (`request_id`, `scheduled_datetime`, `service_type`; ADR-035) and the stored model:
    no comment, note or name reaches it, so its one LLM call (the parse) sees only the
    user's question.
11. **`find_technician` returns at most 5 names and accepts no patterns.** A name from the
    user's question is matched in code against the fixed technician list, case-insensitively
    and by whole word; it never reaches SQL. The tool rejects any character other than
    letters, spaces, apostrophes, hyphens and periods, so `%`, `_`, `*`, `?` and brackets
    can't be used to enumerate staff; it returns at most 5 matches (id and display name)
    and the total count, and logs only the count, not the name typed. The reporting agent
    resolves the name before any metric call: no match or several matches ends the turn
    with no figures, and names reach only the answer template, never a model (ADR-073).

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
QA agent. It reads the most (guarantee 4), though no longer the sentiment ground truth:
it cross-checks sentiment against star ratings instead (guarantee 5, ADR-063). It also
consumes specialists' outputs, which may carry injected text from feedback comments. Its
read-only role means a successful attack can disclose data but not alter it, and it still
can't reach customer PII. The two broadest credentials sit outside the agents entirely.
The `app_generator` role has full access to every table and is used at load time only, by
`data/generator/load.py`. Its credentials must never be present in any deployed service:
not in a service image, a Cloud Run environment, or the Secret Manager entries a service can
read. The same holds for the Postgres admin credentials the migrations run as. Today only the
MCP servers receive database credentials in docker-compose, each its own role's:
`mcp_incidents` holds `app_reporting`'s, `mcp_feedback` holds `app_sentiment`'s, the one
runtime role with a write (guarantee 7), and `mcp_volume` holds `app_forecast`'s. CI uses ephemeral generator credentials that never
leave the workflow.

## Still to write (Sprint 3, with `04`)

- MCP and A2A controls: tool scoping per server, Agent Card exposure, authentication
  between services (IAM ID tokens in the Sprint 4 deploy, ADR-045).
- Prompt-injection handling on the paths that ingest free text (feedback comments,
  questions).
- Secrets management in deployment (Secret Manager) and how each service's credentials are
  scoped.
- Logging: what is logged with each tool call and trace id, and what is redacted.
- The QA prompt as a prompt-injection surface: its one LLM call (ADR-056) ingests
  specialist output, which may carry text from customer comments.
- ~~The evaluation/training read role (ADR-055, ADR-062): `sentiment_labels` and
  `generation_parameters` move off `app_qa` before the QA agent is built in Sprint 4, so
  the runtime QA role never holds gold labels. Guarantee 4 changes when that lands.~~
  *Done 2026-10-01 (ADR-063): the offline `app_eval` and `app_train` roles hold them now;
  guarantee 4 changed and guarantees 5 and 6 were added.*
