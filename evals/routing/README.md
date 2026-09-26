# Routing seed set

`seed_v1.jsonl` holds 28 hand-written questions, each with the route the orchestrator
should choose and a tag. It seeds the Sprint 3 routing eval set; it is not the eval
itself. Expected routes are for the owner to review. The ambiguous ones especially
encode judgement calls, noted below.

| Tag | Count | Expected routes |
|---|---|---|
| clear | 14 | reporting 6, sentiment 4, forecast 4 |
| ambiguous | 6 | reporting 4, sentiment 1, multi_domain 1 |
| out_of_scope | 4 | out_of_scope 4 |
| multi_domain | 4 | multi_domain 4 |

Judgement calls in the ambiguous set:
- s15 "How did the Northeast region do": performance of past records, so reporting.
- s16 "Are complaints going up?": complaints read as logged incidents (reporting), not
  feedback wording (sentiment). This is the most contestable label.
- s17 star ratings are structured records, so reporting. The route prompt's rules say
  so; the text of feedback is sentiment.
- s18 past volume plus future volume: reporting and forecast, so multi_domain.
- s19 "happy with the technicians": the customers' words, so sentiment.
- s20 "trend in request volume" with no future period: past volume, so reporting.

`run_seed.py` runs the set through the orchestrator's classifier (the same prompt and
code as the service) and writes results to `evals/results/`.
