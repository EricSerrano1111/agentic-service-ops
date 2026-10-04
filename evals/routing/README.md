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

## seed_v2 and routing_v2 (ADR-075)

Relabelled under ADR-075's definition before any `route_v4` run. A question is
**ambiguous** when it could reasonably mean different measurable things to different
specialists, so the answers would differ in kind; it expects route `ambiguous` with its
`candidates`. A question that clearly fits one domain but leaves out a detail (period,
region, bucket, which measure within the domain) is **underspecified** and keeps its
domain. Multi-domain asks for two things; ambiguous asks for one thing, but which is
unclear. The v1 files stay unchanged.

Each relabelled row keeps `expected_v1` and `tag_v1` and states its reason in
`relabel_v2`. These are owner judgement (L-57), and the v2 sets are not blind: they were
written knowing the `route_v3` behaviour they correct.

| Set | Ambiguous | Underspecified (was ambiguous, or new control) | Other |
|---|---|---|---|
| seed_v2 (31) | s15, s16, s20, s29 (new) | s17, s19, s30 (new), s31 (new) | s18 moved to multi_domain; 14 clear, 4 out_of_scope, 4 multi_domain unchanged |
| routing_v2 (18) | r02 | r01, r03, r04, r05, r06, r07, r08 | 5 near_miss, 5 technician unchanged |

## fr03_fresh_v1 (ADR-076)

15 questions written by the owner, Eric Serrano, on 2026-10-03, without viewing
`seed_v2`, `routing_v2` or any route prompt: 5 ambiguous, 5 underspecified, 5 clear (f14
and f15 are clear questions with feeling words, as a trap for sentiment routing). No
prompt has been tuned on this set; `route_v5` was frozen before it was written, and the
assistant saw the items only after `route_v5` was frozen.

`fr03_fresh_v1.source.md` is the owner's text, verbatim. `fr03_fresh_v1.jsonl` is a
mechanical conversion for `run_seed.py`: `category` to `tag`, `reason` to `note` (verbatim),
`candidates` as a list (empty for `-`), and the f14/f15 parenthetical "(feeling words, not
sentiment)" to `label_note`, with their tag kept as `clear`.
