# Sprint 5: blind evaluation runs (Prompt X), 2026-10-13

## What ran

- **Held-out routing**: `routing_heldout_v1`, 50 items, k=3, sequential, against the deployed
  orchestrator's `/ask`. Runs in `evals/results/routing_heldout_v1/2026-10-13/`.
- **Golden**: `golden_v2`, 36 items, one run. Run in `evals/results/golden_v2/2026-10-13/`.
- No harness retries. The services' own retries applied as deployed. No request errored or timed out.

## System under test

- Images tagged `9607fa722c4d1b2dc12478dbe4bb42f6c8d95bfb` (tree equals `eval-freeze-s5`;
  `git diff eval-freeze-s5 HEAD` showed docs only at the start of the run).
- Mode: `LLM_MODE=paid` on the five model-calling services (ADR-104).
- Default router `route_v3`; interpretation check advisory with `qa_interp_v2`.
- Revisions, identical at the start and at the end of the run:
  `ops-forecast-00002-m79`, `ops-gateway-00001-8st`, `ops-orchestrator-00006-bvj`,
  `ops-qa-00003-hwq`, `ops-reporting-00006-md5`, `ops-sentiment-00002-cxz`. `ops-db`
  `RUNNABLE` (left running); trigger `deploy-reporting-slice` disabled.
- Caller: the owner's own gcloud identity (user account), the method `deploy/verify.py` uses on
  the owner's machine. Direct to the orchestrator, never the gateway.

## Scoring

As pre-registered in `evals/sprint5_gates.md` B3 and ADR-074; the golden method was fixed in
`sprint5_x/golden_scoring.md` (commit `05a1708`, 2026-10-13 12:34:49 -05:00) before the first
golden call. `must` and `must_not` are not in the score: `sprint5_x/golden_owner_review.csv` is
for the owner; `sprint5_x/golden_assistant_reading.md` is the assistant's opinion.

## Results (headline)

| | Result |
|---|---|
| Held-out routing, per run | 38, 38, 38 of 50 (range 38 to 38; no flipping items) |
| Held-out routing without the 7 ambiguous items (labelled as such) | 38, 38, 38 of 43 |
| Taxonomy (item-runs) | ambiguous not flagged 21; out-of-scope accepted 15; all other classes 0 |
| Golden, mechanical | 29 of 36 |

Details: `evals/results/routing_heldout_v1/2026-10-13/score.json`,
`evals/results/golden_v2/2026-10-13/score.json`, `evals/results/sprint5_failure_data.md`.

## Ledger (`evals/results/sprint5_x_ledger.json`)

| | Used | Cap |
|---|---|---|
| Requests | 186 (X1 150, X2 36) | 186 |
| Cost by logged `cost_usd` | $0.1727 (X1 $0.1408, X2 $0.0319); 0 requests with an unknown cost | $1.50 |
| Model calls | not returned per request; bounded by 186 x 5 = 930 | 1,000 |

## Deviations (for Prompt Y)

1. **No cost or call count in the response.** The prompt assumed per-request cost and call counts
   in the orchestrator's response metadata. `AskResponse` has neither. Cost came from the
   orchestrator's `ask answered` log line (`cost_usd`), looked up by `trace_id` with
   `gcloud logging read`, one request behind; the owner approved this as option 1. Cost is a
   list-price estimate (L-71); the paid key's prepaid balance (auto-reload off) is the hard
   backstop. The model-call cap is bounded by the item count, not counted (L-94).
2. **The lookup made each request about 40 s wall-clock at the start** (so the sequential run took
   about 1.5 hours rather than 15 minutes). It did not change what was sent or when each request
   was made relative to its predecessor.
3. **One aborted launch, nothing sent.** The first start failed while minting the identity token
   (an explicit audience is only valid for a service account, the rule `deploy/verify.py`
   already has). The failure was before any HTTP request, but the ledger had already counted it.
   That ledger file (one counted request, no cost) was removed and the run restarted; the harness
   now mints the token before it counts a request.
4. **Data parity** (golden figures were computed on the local database; the deployed system
   reads Cloud SQL). Read-only as `app_eval` through the proxy, local against Cloud SQL, for the
   eight tables the oracles read: row counts and per-table and per-column hashes, ordered by
   primary key, all equal (`evals/results/sprint5_x/data_parity.py`,
   `data_parity_local.json`, `data_parity_cloud.json`). The local database had to be started
   (`docker compose up -d postgres`; its `./pgdata` volume held the data the golden set was built
   on). The `db-role-eval-password` secret was read once, inside the script, never printed.
5. **The scorer has one rule the system's display makes too strict**: G21's `p_value` is carried
   to four places (0.3349), the oracle holds the full value, and the pre-registered tolerance
   (1e-6) fails it. It is scored as pre-registered (fail) and noted; the rule was not changed
   (L-95).

## The sets are spent

`routing_heldout_v1` and `golden_v2` were run on 2026-10-13 and their items and answers are now in
this repository's results and in the failure-analysis data. They are **spent for blind use**:
any prompt or code change that reads those results turns them into development data, and the
interpretation of any later score on them must say so. The generated sets' remaining members
(`fr03_fresh_v2`, `interp_fresh_v1`, `interp_pairs_v1`, `parse_filters_v1`, `reserve`) were not
touched in this run.

## Disclosure lines (verbatim)

1. "In a real deployment, evaluation sets would come from real user questions and subject-matter experts. Here they were generated by an independent model under a written brief; the owner reviewed the brief and spot-checked the ambiguous labels."
2. "The sets were generated, not owner-written."
3. The persona-drop selection effect (L-86, update 2026-10-11) is in `evals/results/sprint5_failure_data.md`, section 3, verbatim.

The golden set is a different case from (1) and (2): 10 of its 36 items are owner-written
(ADR-074).
