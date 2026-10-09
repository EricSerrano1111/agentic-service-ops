# Security Model — Agentic Service Operations Intelligence Platform

*Seeded 2026-09-30 from `data-dictionary.md` §7 (the access matrix) and `architecture.md` §5.
Completed 2026-10-04, at the Sprint 3 close. Where this file and §7 disagree, §7 and
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
    `find_account` follows exactly the same rules for account names, and the `region` filter
    accepts only the four site regions (ADR-086).

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

The controls that implement these defences, and what is still planned, are set out in the
sections below, each marked built or planned.

## Controls: as built and planned

Every control below is marked **Built** (the code or a test shows it today, and the evidence
is named) or **Planned** (not built, with the sprint). A built control with no test says so.
Checked against the code on 2026-10-04; the controls the reporting-slice deploy proved were marked Built on 2026-10-08 (evidence: the pipeline's `verify.py` run, build 5a181fa1, and `docs/deploy-window-log.md`); "by search" means a repository search, not a test.
Test names are in `services/*/tests/` and `tests/`. The guarantees above and the threat model
are unchanged; the rows cross-reference them.

### 1. MCP controls

| Control | Status | Evidence |
|---|---|---|
| Narrow, purpose-built tools; no raw-SQL or generic query tool (ADR-023). | Built | `test_only_the_narrow_tools_are_exposed` (`mcp_incidents`, six tools), `test_only_the_two_read_tools_are_exposed` (`mcp_feedback`, `mcp_volume`). By search, no raw `text()` SQL construct exists in `services/` or `packages/`. |
| One MCP server per specialist; each holds one database role's credentials and nothing else (guarantees 1 to 3). | Built | `tests/unit/test_compose_isolation.py`: `test_mcp_incidents_holds_only_app_reporting_credentials`, `test_mcp_feedback_holds_only_app_sentiment_credentials`, `test_mcp_volume_holds_only_app_forecast_credentials_and_no_model_key`, `test_agents_hold_no_database_variables`. Grants: `tests/integration/test_access_matrix_grants.py`. |
| No tool writes; the one write (predictions) happens inside `mcp_feedback`, not through a tool (guarantee 7). | Built | The same tool-list tests; `store.py` `insert` is reached only from `ensure_scored`. |
| Typed input validation before any query: enumerated values (`group_by`, `by`, `region`, `bucket`, `slice`, `label`), strict ISO dates inside the dataset window, strict integers. | Built | `test_metric_tool_rejects_an_unknown_breakdown`, `test_invalid_ranges_are_rejected`, `test_invalid_scopes_are_rejected` (which includes a date string carrying `'; DROP TABLE x;--`, rejected as not an ISO date), `test_unknown_slice_is_rejected`, `test_technician_id_must_be_a_positive_integer`. |
| Result caps. Tools return aggregates (counts and rates); the only row-like results are comment examples and technician matches, each capped at 5. | Built | Each row below. |
| Grouped results at most 25 groups, worst or highest first; the full count is reported. | Built | `test_truncation_keeps_the_worst_groups`, `test_more_than_25_groups_are_cut_after_ranking`; the shared result models reject more than 25 groups. |
| Comment examples at most 5 per call (the sentiment agent asks for 3), and never sent to a model (guarantees 8, 9). | Built | `test_limit_outside_1_to_5_is_rejected`, `test_examples_reject_a_limit_above_5`, `test_examples_are_requested_with_limit_3_and_never_reach_the_llm`. |
| On-demand scoring at most 250 comments per request, newest first, with coverage reported. | Built | `test_above_the_cap_the_newest_are_scored_and_coverage_is_partial`, `test_the_cap_and_batch_follow_the_real_container_measurement`. |
| Technician lookup returns at most 5 names plus the total, matches by whole word in code, and rejects wildcards and pattern characters (guarantee 11). | Built | `test_find_technician_rejects_wildcards_and_patterns`, `test_patterns_and_non_name_characters_are_rejected`, `test_at_most_five_matches_are_returned_with_the_total`; the name is never logged. |
| Account lookup (`find_account`) follows the technician rules exactly: at most 5 names plus the total, whole-word matching in code, patterns and wildcards rejected, the typed name never logged (only the match count, or the resolved `account_id`). A region filter takes only the four values, an account filter only a positive id; anything else is rejected before any query (guarantee 11, ADR-086). | Built | `test_find_account_rejects_wildcards_patterns_and_sql`, `test_find_account_rejects_an_oversized_empty_or_numeric_name`, `test_invalid_region_and_account_values_are_rejected_before_any_query`, `test_a_typed_account_name_is_never_logged`, `test_a_filtered_call_logs_the_account_id_and_region_not_the_account_name` (`mcp_incidents`); `test_account_lookup_failures_log_counts_and_ids_not_names`, `test_a_rejected_account_name_is_logged_without_the_name` (reporting agent). |
| Date span at most 731 days (feedback); forecast horizon 1 to 26 weeks and history 1 to 52 weeks. | Built | `test_span_of_exactly_731_days_is_allowed` and the "more than 731 days" case in `test_invalid_scopes_are_rejected`, `test_horizon_outside_1_to_26_is_rejected`, `test_history_weeks_outside_1_to_52_is_rejected`. |
| Database statement timeout of 10 seconds on every server that connects (`MCP_DB_STATEMENT_TIMEOUT_MS`). | Built (configuration; no test of the timeout firing) | `config.py` and the engine options in each server. |
| Forecast numbers only for slice-bands the model manifest marks served (guarantee 10). | Built | `test_no_numbers_ever_for_an_unserved_slice_band`, `test_real_artifact_serves_numbers_only_where_the_manifest_says`; the shared result contract rejects an unserved week carrying numbers (`test_numbers_for_an_unserved_week_are_rejected`, orchestrator). |
| Model artifacts are hash-checked at start-up; a changed or missing file stops the server. | Built | `test_refuses_to_start_on_an_altered_file` (`mcp_feedback`, `mcp_volume`), `test_refuses_to_start_on_a_missing_file` (`mcp_feedback`), `test_refuses_to_start_on_a_missing_file_or_no_serving_table` (`mcp_volume`). |
| Internal errors return a generic message; SQL detail stays in the log. | Built for two servers | `test_query_failure_does_not_leak_detail` (`mcp_incidents`), `test_store_failure_does_not_leak_detail` (`mcp_feedback`). `mcp_volume` follows the same pattern in code (`"volume query failed"`) with no test. |
| Host-header (DNS-rebinding) protection on the MCP endpoints, allowing only localhost and the service's own name. | Built (configuration; no test of a rejected host) | `server.py` `TransportSecuritySettings` and `config.py` `allowed_hosts` in each MCP server. |

**Where user text meets SQL.** A user's words never become SQL. They reach the models only as
the question inside a prompt; what comes back is parsed into a typed request (section 3), and
the agent's code, not the model, chooses the tool. From there each value is one of the
following.

| Value (from the parsed request) | Validated as | Reaches the database as |
|---|---|---|
| `metric` | enumerated type (`Metric`) | picks which fixed tool function runs (`TOOLS` in the agent's executor); never a query fragment |
| `group_by`, `by`, `region`, `bucket`, `slice`, `label` | enumerated types, checked again by the MCP server's input schema | picks among fixed column and join sets in code (`metrics.py`, `queries.py`, `repeats.py`); never interpolated |
| start and end dates | `date` values, sent as `YYYY-MM-DD`, parsed strictly again and range-checked by each server | `datetime` objects compared as bound parameters (SQLAlchemy Core, `bindparam` and column comparisons) |
| `technician_name` | text of 1 to 100 characters in the request; the lookup accepts only letters, spaces, apostrophes, hyphens and periods | never SQL: matched in Python against the technician list read whole |
| `technician_id` | integer of at least 1, taken from the lookup result, not typed by the model | bound parameter in `column == technician_id` (`_only` in `metrics.py`; `count_by_severity`) |
| `limit`, `flagged_only`, `weeks`, `horizon_weeks` | strict integers and booleans within the caps above | integer bounds, `LIMIT` and bound comparisons |

The only f-string in a connection setting is the statement timeout, which comes from
configuration, not from a question.

### 2. A2A and service-to-service

| Control | Status | Evidence |
|---|---|---|
| A2A v1.0 over JSON-RPC with the Agent Card at the well-known path and blocking `SendMessage` only; streaming and push declared off (ADR-047). | Built | `test_card_advertises_only_the_minimal_subset` (reporting), `test_card_advertises_one_skill_and_the_minimal_subset` (sentiment), `test_card_served_at_well_known_path` (all three agents). |
| The Agent Card advertises names, descriptions and example questions only: no tool schemas, credentials or internal addresses beyond the agent's own URL. | Built | `card.py` in each agent. |
| The orchestrator calls agents at fixed addresses from configuration (`AGENT_*_URL`), never discovered from input. | Built | `docker-compose.yml`, `config.py`; by search, no address is taken from a question or a model output. |
| Specialist answers are validated against shared typed contracts on receipt, with numbers as typed values. | Built | `test_answer_that_breaks_the_contract_is_rejected`, `test_metric_answer_with_a_float_rate_is_rejected`, `test_numbers_for_an_unserved_week_are_rejected`. |
| Network exposure under compose: only the orchestrator and Postgres publish a port, and both bind `127.0.0.1` only (the orchestrator since 2026-10-04); the agents and MCP servers are reachable only on the compose network. | Built | `test_only_orchestrator_publishes_a_port`, `test_every_published_port_binds_loopback_only` (`tests/unit/test_compose_isolation.py`); `docker-compose.yml`. |
| Per-hop timeouts that fit inside the 120-second ceiling. | Built | `test_timeouts_fit_inside_the_120s_ceiling`, `test_sentiment_timeouts_fit_inside_the_120s_ceiling`, `test_forecast_timeouts_fit_inside_the_120s_ceiling` (orchestrator tests). |
| A single per-request deadline passed through every hop. | Planned, Sprint 4 | Sprint 4 planning note in `sprint-log.md`. |
| **Authentication between services: none today.** No token, key or certificate is checked on any hop, and the compose network is the only boundary. The orchestrator's `/ask` is unauthenticated and spends the model quota, so it is published on loopback only (`127.0.0.1:8000`), reachable from the developer's machine and nothing else. Accepted for local development (L-59); IAM ID tokens and the gateway replace it in the deploy. | Not built; accepted locally | Absence confirmed by search of `services/` and `packages/` for tokens, keys and auth dependencies (2026-10-04). L-59. |
| IAM ID tokens between services, on the Agent Card fetch and the message call alike, audience the target's base URL, attached to the target's origin only, cached until shortly before expiry. On Cloud Run an agent's call to its own MCP server is localhost between sidecars of one service and carries no token (ADR-079). | **Built for orchestrator to reporting (2026-10-08)**; the rest, and agent to QA, Planned, Sprint 5 | `test_token_is_on_both_the_card_fetch_and_the_message_call_when_auth_is_on`, `test_the_bearer_goes_only_to_the_audience_origin`, `test_a_token_fetch_failure_is_specialist_unavailable_not_a_500` (orchestrator tests); the pipeline's check 6 answered a question through the signed hop (ADR-081, ADR-085). |
| Ingress is IAM only on both deployed services: no `allUsers` or `allAuthenticatedUsers`; reporting's only invoker is the orchestrator's service account; a caller that is not the orchestrator is refused. | **Built (2026-10-08)** | `verify.py` checks, passing in the pipeline: unauthenticated `POST /ask` and `GET /` on the orchestrator and `GET /` on reporting each 403; the probe account (no role) gets 403 from reporting; reporting's invoker is exactly the orchestrator; neither service runs as the default compute account. `test_unauthenticated_probes_pass_on_401_and_403` and the other `verify.py` unit tests. The project Owner can invoke any service through the basic role (ADR-081). |
| Only the gateway reachable from the internet; requests without valid credentials rejected before any model call (NFR-2). | Planned, Sprint 5 | The gateway (`services/api_gateway`) is not built; the access mechanism is chosen in Sprint 5. |

### 3. Prompt injection

The free text that enters the system is customer comments and the user's question. Staff
incident notes never leave the database through any tool and the sentiment role has no grant
on them (guarantee 2).

| Control | Status | Evidence |
|---|---|---|
| Customer comments are untrusted and are never sent to a language model. They reach only the fine-tuned classifier, whose output is one of four labels, and answers are rendered from templates (guarantee 9; ADR-046, ADR-068). | Built | `test_examples_are_requested_with_limit_3_and_never_reach_the_llm`; `test_examples_are_quoted_verbatim_with_label_and_confidence`; compose gives `mcp_feedback` no model key (`test_mcp_feedback_holds_no_model_key_or_setting`). |
| QA's interpretation call receives the answer with each quote replaced by its ID, not the quotes; quotes are checked mechanically against the database. | Planned, Sprint 4 | Sprint 4 planning note and guarantee 9 above. The QA agent (`services/agent_qa`) is not built. |
| The question is rendered into the prompt as data: one pass, values inserted literally, so template-looking text can't raise or be rewritten. | Built (2026-10-04) | `tests/unit/test_prompt_rendering.py`; the per-service `test_*template_syntax*` tests named below. |
| The question is delimited in every routing and parsing prompt and declared data, not instructions; it is limited to 2,000 characters. | Built | All ten prompt files (`route_v1` to `route_v5`, `parse_v1` to `parse_v3`, and the sentiment and forecast `parse_v1`) carry the line; `AskRequest` (`max_length=2000`). No test asserts the prompt line. |
| Model output is structured and validated: the call sets the response schema from the typed model, the reply is parsed against it, and an invalid reply fails with no repair and no default route or range. | Built | `packages/llm` `transport.py` and `client.py`; `test_invalid_parse_output_fails_and_never_guesses_a_range`, `test_unclear_question_asks_to_rephrase`. |
| No tools are exposed to a model, and automatic function calling is disabled. The agent's code picks the tool from the parsed metric (ADR-046). | Built | `packages/llm` `transport.py` (`automatic_function_calling` disabled); `test_each_metric_calls_its_own_tool`. |
| Model output is never executed: parsed values only select among fixed code paths. | Built | By search, no `eval`, `exec` or subprocess call in `services/` or `packages/`. |
| QA checks that the parsed request matches the question. | Planned, Sprint 4 | ADR-056; until it exists, nothing downstream checks the parse. |

**What an injected question could still achieve.** A wrong route or wrong parameters: another
specialist, another period, region, metric or technician, or a decline. The data returned stays
inside the chosen specialist's grants, from fixed queries, and the answer states the range it
used (and, for an assumed range, says so), so the user can see what was asked. It cannot make
the system run SQL, call a tool the model was not offered, or read a table outside the role's
grants. Two smaller effects remain: the router's one-sentence `reason` is model-written text
derived from the question, and it is returned in the response and logged; and quoted comments
(at most 3) appear verbatim in an answer, so the Sprint 5 interface must render them as plain
text (React escapes text by default; the interface is not built, so this is a requirement on it,
not a control). Until the QA agent exists (Sprint 4), nothing checks that a wrong route or
parameter was caught.

**A question is data, not template syntax.** Until 2026-10-04 a question containing text
such as `{{secret}}` made prompt rendering raise, and the orchestrator returned an unhandled
HTTP 500 before any model call; a question containing `{{as_of}}` was silently rewritten. It
failed closed and revealed nothing, but it was an unhandled error on user input. Fixed: the
shared renderer fills the template in one pass and inserts values literally, never rescanning
them, so `{{x}}`, `{0}` and `}}{{` reach the model unchanged. Every ordinary render is
unchanged (1,128 renders across 141 evaluation questions, identical before and after).
Evidence: `tests/unit/test_prompt_rendering.py` (the legacy algorithm kept as a reference),
`test_router_sends_template_syntax_in_a_question_unchanged` and
`test_template_syntax_in_a_question_is_a_normal_response_not_a_500` (orchestrator), and
`test_parse_sends_template_syntax_in_a_question_unchanged` (reporting, sentiment and forecast
agents).

### 4. Secrets

| Control | Status | Evidence |
|---|---|---|
| `.env` and `.env.*` are ignored by git; `.env.example` lists names with blank values. | Built | `.gitignore`; `.env.example`; by search of git history, `.env` was never committed. |
| No secret literals in the compose file; values come from `.env` at start-up, and a missing model key stops the start. | Built | `test_no_secret_literals_in_compose`; `${GOOGLE_AI_API_KEY:?...}` in `docker-compose.yml`. |
| Each service receives only the credentials it needs: agents get no database variables; each MCP server gets one role; LLM callers get only the free key; no service gets the paid key. | Built | `tests/unit/test_compose_isolation.py` (`test_agents_hold_no_database_variables`, `test_llm_callers_get_only_the_free_key`, `test_no_service_gets_the_paid_key`, and the per-server tests). |
| The generator, training, evaluation and admin credentials are never present in a deployed file or service. | Built | `tests/unit/test_offline_roles_isolation.py` (`test_no_deployed_file_references_offline_role_credentials`). |
| No credentials in images: the build context is an allowlist that excludes `.env`, `pgdata/`, `data/` and `docs/`. | Built (file; no test) | `.dockerignore`. |
| The model key appears in no log line, exception or repr; error bodies are redacted before logging. | Built | `test_key_appears_in_no_log_line_exception_or_repr`, `test_real_transport_repr_hides_the_key`, `test_first_429_capture_redacts_key_and_project_identifiers`. |
| Database passwords stay out of settings reprs. | Built (code; no test) | `Settings.__repr__` in each MCP server omits the password. |
| CI uses its own ephemeral role credentials and never `.env`. | Built | `.github/workflows/ci.yml`; the database is a service container destroyed at the end of the job. |
| Secret scanning of commits. | Built as a GitHub check, not in this repository | A "GitGuardian Security Checks" check passes on pull requests (observed on PR #23). It is not defined in `ci.yml`, so whether it scans pushes to `main` is not visible from the repository. |
| Secrets in GCP Secret Manager, never in code or images. On the reporting service the database password is mounted in `mcp-incidents` only and the Gemini key in the orchestrator and `agent-reporting`; the Cloud SQL socket is mounted in `mcp-incidents` only (Admin API v2 format, ADR-081). | **Built for the reporting slice (2026-10-08)**; the rest Planned, Sprint 5 | `test_cloud_sql_is_mounted_into_the_mcp_sidecar_only`, `test_secrets_go_only_to_the_containers_that_need_them` (`tests/unit/test_deploy_config.py`); the deployed revision runs and answers; the `gemini-api-key` secret was checked against the free key by SHA-256, not the paid key. |

### 5. Logging

Logs are JSON lines on stdout from every service, written by one formatter installed on the
root logger, so SDK loggers use it too (`packages/common/src/common/logging.py`).

| Control | Status | Evidence |
|---|---|---|
| One trace id per request, minted by the orchestrator and carried in the A2A message metadata and the MCP request metadata; every line written while handling the request carries it. | Built | `test_trace_id_from_meta_reaches_the_log` (`mcp_incidents`), `test_route_decision_is_logged_with_prompt_version`, `test_parsed_range_becomes_the_tool_arguments`. |
| Every MCP tool call logs one line: tool, range, breakdown or filter ids, counts, duration; a rejected input logs its tool and reason. | Built | `"tool call"` and `"tool rejected input"` lines in each MCP server. |
| Routing and parsing log the decision, prompt version and prompt hash, not the prompt text. | Built | `test_prompt_version_is_logged_with_the_parse`. |
| The question's length is logged, not its text. | Built | `"ask received"` and `"task received"` log `question_chars` only. |
| Bearer tokens, `authorization` fields and URL passwords are masked in every log line by the shared formatter, and the A2A SDK's loggers are held at INFO or above (it prints request headers at DEBUG). Pattern-based (L-63). | **Built; proved on Cloud Run 2026-10-08** | `test_token_and_header_never_reach_any_log_at_any_level`, `test_a_debug_root_level_still_emits_no_sdk_header_lines`, `tests/unit/test_log_exposure.py`. Step 10 of the window: 281 Cloud Logging entries from both services, covering the verify traces, were scanned for five secret values and for header, bearer, JWT and URL-password patterns: 0 findings. |
| Trace id on web-server access-log lines. | Planned, Sprint 4 | Sprint 4 item in `sprint-log.md`. Access lines are written through the same formatter today, without a trace id. |

**What the code logs about user text** (read from all 54 log calls in `services/` and
`packages/` on 2026-10-04, and changed the same day where noted):

- **Never logged:** the question text; any prompt; any model reply other than the router's
  `reason`; any customer comment (`feedback_text`); any contact data (no code path reads
  `contacts`); the model key; database passwords.
- **Fixed 2026-10-04.** A technician lookup that finds no one, or several, logs the match count
  and the technician ids, not the name as typed or the matching display names (the answer text
  is unchanged). A rejected tool argument logs its name and the kind of error (for example
  `start` and `not_iso_date`), not its value, and the tool's error message no longer echoes the
  value either, because the MCP SDK logs that message itself. Evidence:
  `test_technician_lookup_failures_log_counts_and_ids_not_names`,
  `test_a_name_the_lookup_rejects_is_logged_without_the_name` (reporting agent) and
  `test_rejected_arguments_are_logged_by_name_and_kind_never_by_value` (each MCP server), which
  search every log line, SDK loggers included, for the rejected value.
- **Still logged, derived from the question:**
  1. The router's `reason`: model-written, up to 300 characters, and it may paraphrase the
     question (`"route decision"`).
  2. Failure texts for other codes (`"task failed"`, `"agent task failed"`). They are fixed text,
     except `invalid_range`, which carries the dates the model read from the question.
  3. Tracebacks from `log.exception` go into the `exc` field in full and are **unredacted**:
     the formatter does no redaction of its own (redaction exists only for model-provider error
     bodies). The queries bind ids, dates, labels and numbers, never comment text or contact
     data, so a database error does not carry them; other exceptions were not audited for what
     their messages contain.
- **Staff names:** no longer logged. They are synthetic here; in a real deployment they would be
  personal data, and any logging of them would need review.

### Earlier to-do list, closed

The list headed "Still to write (Sprint 3, with `04`)" is closed as of 2026-10-04: the MCP and
A2A controls are in sections 1 and 2, prompt-injection handling (including the QA prompt as an
injection surface) in section 3, secrets in section 4, and logging in section 5. Its
evaluation/training read role item was done 2026-10-01 (ADR-063): the offline `app_eval` and
`app_train` roles hold `sentiment_labels` and `generation_parameters`; guarantee 4 changed and
guarantees 5 and 6 were added.
