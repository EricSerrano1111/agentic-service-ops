# Requirements Traceability — Agentic Service Operations Intelligence Platform

*As of 2026-10-04 (Sprint 3 close), updated the same day after the pre-Sprint-4 fixes, and again on 2026-10-05 (L-60 recorded). Re-checked at every sprint close.*

One row per functional requirement (FR-01 to FR-22) and non-functional requirement (NFR-1 to NFR-5)
in `docs/academic/02-requirements-analysis.md`. Requirements are paraphrased.

**Status.** *Met*: evidence that exists today (a passing test, an evaluation result or an
end-to-end record); a design document alone is not evidence. *Partly met*: some of it is built.
*Not yet built (Sprint N)*: the plan puts it in that sprint. *Open*: attempted and failed, or
not met and covered by no sprint. *Optional, not planned (MVP: No)*: deliberately excluded and
not scheduled.

| Status | Count |
|---|---|
| met | 12 |
| partly met | 5 |
| not yet built | 6 |
| open | 1 |
| optional, not planned (MVP: No) | 3 |
| Total | 27 (22 FR, 5 NFR) |

## Unrecorded gaps

Requirements that are partly met or open, where this gap has no ADR or limitation recording it.
Listed, not fixed.

None open.

Resolved since the 2026-10-04 review: circuit breaking is decided in ADR-077 (Sprint 4); the
unauthenticated hops are accepted locally in L-59, with every published port now bound to
`127.0.0.1`; the `{{...}}` failure and the logged technician names and rejected argument values
are fixed in the `fix/pre-sprint4-hardening` change set; the router's model-written `reason` and
unredacted tracebacks in the logs are recorded in L-60 (2026-10-05).

## Matrix

| ID | Requirement | MVP | Status | Evidence | Notes |
|---|---|---|---|---|---|
| FR-01 | Accept a natural-language question and classify the user's intent. | Yes | met | `evals/results/routing_*_route_v3_*.json` (`route_v3`: seed_v1 27-28/28 and routing_v1 16-17/18 over 3 runs, ADR-054; 43/44 non-ambiguous on the v2 sets); `test_reporting_route_calls_the_agent_with_the_question`; the three e2e records. | Single-shot; reached through the orchestrator's `/ask`. The web interface is FR-19. |
| FR-02 | Route the classified intent to the correct specialist agent via A2A. | Yes | met | The e2e records for all three specialists (`evals/results/reporting_agent/2026-10-02/e2e.json`, `sentiment_agent/2026-10-01/e2e.json`, `forecast_agent/2026-10-02/e2e.json`); `evals/results/routing_*_route_v3_*.json`; ADR-047, ADR-068, ADR-072. | Measured on non-blind sets. The held-out routing set and failure analysis are Sprint 5. |
| FR-03 | Handle ambiguous intents without force-routing them. | Yes | open | ADR-075, ADR-076; L-58 and its 2026-10-04 update; `evals/results/routing_fr03_fresh_v1_*.json`; Sprint 5 item in `sprint-log.md`. | Attempted and failed two pre-registered gates; `route_v3` (best-fit) remains the default. `route_v3` emits `ambiguous` in about 1% of calls (2 of 192), which is not compliance. |
| FR-04 | Detect questions spanning several domains; tell the user to ask separately. | Yes | met | `test_multi_domain_names_the_domains_and_asks_for_a_split`; `route_v3` routed all 5 multi-domain items to `multi_domain` in each of 3 runs (`evals/results/routing_seed_v2_*_route_v3_*.json`). | ADR-032. Golden items G09, G33, G34 cover it, unrun until Sprint 5. |
| FR-05 | Decline out-of-scope intents rather than guessing. | Yes | met | `test_out_of_scope_gets_a_polite_decline`; `route_v3` routed 4/4 out-of-scope items to `out_of_scope` in every run (`routing_seed_v2_*`), and 4 of 5 near-miss items (`routing_routing_v2_*`). | r11 is a contested label that routes to sentiment in every run (L-15). |
| FR-06 | Reporting metrics (incident rate, SLA, first-time fix, repeat drivers) by account, region, type, technician. | Yes | met | `test_tool_figures_match_independent_sql`, `test_incident_count_breakdowns_match_independent_sql`, `test_technician_filter_matches_independent_sql`, `test_repeat_drivers_match_independent_sql_and_scipy`; `evals/results/reporting_agent/2026-10-02/` (parse 15/16 x3; e2e). | ADR-033, ADR-073. 'Every figure is verified before it is shown' depends on FR-09. |
| FR-07 | Classify customer feedback as positive, neutral, negative or mixed, with confidence. | Yes | met | `evals/results/sentiment/test_ledger.jsonl` (`bert_v1` test macro-F1 0.9713 against 0.9431 for TF-IDF); `test_answer_figures_match_independent_sql` (`test_agent_sentiment_figures.py`); `evals/results/sentiment_agent/2026-10-01/e2e.json`. | Scored against synthetic labels, so accuracy overstates real-world performance (limitations log). Review flags and calibrated confidence: ADR-066. |
| FR-08 | Forecast weekly request volume, compared against a seasonal-naive baseline. | Yes | met | `evals/results/forecast/2026-10-02_holdout/holdout.json` (total MAPE 8.81% against 14.80% for seasonal naive); `evals/results/forecast/test_ledger.jsonl`; `test_agent_figures_equal_the_artifact_and_the_database`; `evals/results/forecast_agent/2026-10-02/e2e.json`. | Met for the total. Most service-type slice-bands fail the gate and are withheld with their error shown (ADR-070, ADR-071; L-41 to L-46). The baseline comparison is in the evaluation record, not in each answer. |
| FR-09 | QA Reporting: re-run the query independently to cross-check figures. | Yes | not yet built (Sprint 4) | `services/agent_qa` is empty; Sprint 4 item in `sprint-log.md` (ADR-055, ADR-056). | Independent oracles exist for the golden set and the integration suite, but they are tests, not runtime QA. |
| FR-10 | QA Forecast: check input history, arithmetic and stored held-out error; refuse above threshold. | Yes | not yet built (Sprint 4) | `services/agent_qa` is empty; Sprint 4 item in `sprint-log.md`. | Groundwork exists: the manifest's served flags and shown errors (ADR-071), and `mcp_volume` already returns no numbers for unserved bands. The requirement text says a failing model is not deployed; ADR-071 serves per slice-band instead. |
| FR-11 | QA Sentiment: rating cross-check, comment and count checks, review-flag check. | Yes | not yet built (Sprint 4) | `services/agent_qa` is empty; Sprint 4 item in `sprint-log.md`. | The rating is withheld from the sentiment agent (FR-17), and predictions and flags are stored for QA to read. |
| FR-12 | Bounded revision loop: at most 2 retries, each with guidance. | Yes | not yet built (Sprint 4) | Sprint 4 item in `sprint-log.md` (owned by the orchestrator, ADR-055). | `MAX_QA_RETRY_ATTEMPTS` appears only in `.env.example`; no code reads it. |
| FR-13 | On final QA failure, return a degraded result with warning and escalation flag. | Yes | partly met | The degraded result exists (ADR-088): `outcome: degraded`, `escalate: true`, a warning and the unavailable capability, for the deadline, an open or failing dependency, the cost cap, and QA unavailable (wired, used in phase M): `test_the_response_model_ties_the_degraded_fields_together`, `test_qa_unavailable_is_degraded_marked_not_verified_with_the_escalation_flag`, `test_an_answer_that_failed_qa_is_never_shown_as_an_answer`, `test_no_traceback_token_or_raw_error_text_reaches_the_degraded_response`. | The final-QA-failure trigger itself is phase M. Shares the 120-second ceiling with NFR-1. |
| FR-14 | Each agent uses its own least-privilege database role, enforced by grants. | Yes | met | `tests/integration/test_access_matrix_grants.py` (`test_table_level_select_matches_matrix`, `test_column_level_select_matches_matrix`, `test_writes_match_matrix`); `tests/unit/test_access_matrix.py`; `tests/unit/test_compose_isolation.py`. | The roles are held by the MCP servers; the agents hold no database credentials. `app_qa` exists but its agent is not built. |
| FR-15 | No agent can read customer personal data (contacts). | Yes | met | `test_no_agent_role_reads_pii` (`test_access_matrix_grants.py`); security guarantee 1. |  |
| FR-16 | The sentiment pipeline cannot read internal staff notes (incidents). | Yes | met | `test_sentiment_still_cannot_read_table` (`test_access_matrix_grants.py`); security guarantee 2. |  |
| FR-17 | The sentiment agent cannot read the star rating. | Yes | met | `test_sentiment_cannot_read_rating` (`test_access_matrix_grants.py`); ADR-027. |  |
| FR-18 | Generate a synthetic dataset from documented, reproducible parameters. | Yes | met | `test_full_scale_is_deterministic`, `test_reduced_scale_is_deterministic` (`tests/unit/test_generate.py`); the `integration` job in `.github/workflows/ci.yml` generates and loads it on every run; `data/generator/validation/`. | 20,230 service requests and 7,521 feedback responses. |
| FR-19 | Web interface: enter a question; see the answer, QA status, escalation flag. | Yes | not yet built (Sprint 5) | `web/` and `services/api_gateway` hold only `.gitkeep`; Sprint 5 item in `sprint-log.md`. | Needs QA status (Sprint 4) to show. |
| FR-20 | Multi-turn conversational follow-up. | No | optional, not planned (MVP: No) | ADR-031 (single-shot is the committed scope). | MVP: No. Optional; not planned in any sprint. |
| FR-21 | Route one question to several specialists and merge their answers. | No | optional, not planned (MVP: No) | ADR-032 (detect and split instead; FR-04). | MVP: No. Optional; not planned in any sprint. |
| FR-22 | Research agent that pulls external web data. | No | optional, not planned (MVP: No) | ADR-002 (research agent cut). | MVP: No. Optional; not planned in any sprint. |
| NFR-1 | Performance: no request exceeds 120 seconds; degrade with warning and flag. | Yes | partly met | One deadline set at arrival and passed on every hop (ADR-088): `tests/unit/test_deadline.py`; `test_the_request_deadline_is_120_seconds_and_travels_to_the_agent`, `test_a_hop_is_clamped_to_the_time_left_minus_the_five_second_reserve`, `test_no_time_left_before_routing_is_the_degraded_result_with_no_model_call`, `test_the_deadline_goes_to_the_agent_in_the_a2a_message_metadata` (orchestrator); each agent's `test_*_deadline_cost.py` (expired, malformed and far-future deadlines are never trusted). Per-hop timeouts still fit the ceiling (the three `test_*timeouts_fit_inside_the_120s_ceiling`). | The QA loop's hops (phase M) are not yet inside the deadline. Response time and token cost per request type are measured in Sprint 6. |
| NFR-2 | Security in layers: narrow tools, roles, secrets, injection defences, logging, access control. | Yes | partly met | `docs/security-model.md` (every control marked built or planned, with evidence); `tests/unit/test_compose_isolation.py` (`test_every_published_port_binds_loopback_only`); `tests/integration/test_access_matrix_grants.py`; `tests/unit/test_prompt_rendering.py`; `test_technician_lookup_failures_log_counts_and_ids_not_names`. | Built: tools, roles, local secrets handling, structural injection defences, trace-id logging. Planned: Secret Manager and IAM tokens (Sprint 4, ADR-045), gateway and access control (Sprint 5), QA's injection-safe interpretation call (Sprint 4). The 2026-10-04 review findings were fixed in the `fix/pre-sprint4-hardening` change set (loopback-only ports with L-59, template rendering, log contents); one remains, accepted and recorded in L-60 (the router's `reason` and tracebacks in the logs). |
| NFR-3 | Scalability: each service scales independently; back off and say 'try again later'. | Yes | partly met | `test_llm_failures_end_in_coded_failed_task`, `test_rate_limited_carries_retry_guidance`; `tests/unit/test_llm_client.py`; the full 20,230-request dataset loads in CI and is queried by the integration suite. | Rate-limit handling is built. Independent Cloud Run services are not deployed yet (Sprint 4 for the reporting slice, Sprint 5 for the rest; ADR-045). |
| NFR-4 | Availability: health and readiness checks, timeouts, circuit breakers, degrade by domain. | Yes | partly met | `/healthz` and `/readyz` on every service. Circuit breakers (ADR-077, values in ADR-088): `tests/unit/test_circuit_breaker.py`, `tests/unit/test_llm_breaker.py`, `test_three_failures_open_the_breaker_and_the_fourth_request_fails_fast`, `test_one_domains_open_breaker_leaves_the_others_answering`, `test_one_trial_call_after_the_cooldown_closes_or_reopens_the_breaker`. A down specialist is named in the degraded result: `test_agent_transport_errors_are_a_degraded_result_naming_the_capability`, `test_unreachable_sentiment_agent_is_a_degraded_result_naming_sentiment`, `test_unreachable_forecast_agent_is_a_degraded_result_naming_forecast`; stopping the reporting agent end to end is recorded in `docs/sprint-log.md` (2026-10-09). | Breaker state is per process (L-70). QA's own breaker comes with the QA agent (phase M). Graceful degradation tested by stopping each specialist in turn is a Sprint 6 item. |
| NFR-5 | Ethics: synthetic data, no PII to agents, QA status shown, limits stated. | Yes | partly met | Synthetic data (FR-18); no PII to agents (FR-15); review flags in sentiment answers (`test_answer_figures_match_independent_sql`); `docs/evaluation-report.md` limitations log. | 'Every answer shows its QA status' and escalation of verification failures need the QA agent (Sprint 4) and the interface (Sprint 5). |
