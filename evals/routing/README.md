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

## routing_v1

`routing_v1.csv` holds 18 questions written by Eric in dispatch phrasing, blind to model
output. The CSV is the human-edited source; `routing_v1.jsonl` is the same rows in the
seed-set format (plus the `note` column) for `run_seed.py`. Each row's `note` records why
it carries its label.

Labelling rule: "A question routes to the agent whose domain it falls in, even when that
agent can't answer it yet; out_of_scope means no agent's domain covers it."

| Tag | Meaning | Count | Expected routes |
|---|---|---|---|
| ambiguous | two reasonable routes | 8 | reporting 3, sentiment 3, forecast 2 |
| near_miss | sounds operational, but no agent's domain covers it | 5 | out_of_scope 5 |
| technician | asks about individual technicians | 5 | reporting 5 |

Run it with `--file routing_v1`; results are written as
`evals/results/routing_routing_v1_<model>_<prompt>_<UTC time>.json`.
