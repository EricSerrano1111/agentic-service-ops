# mcp_feedback live runs (observed), 2026-10-01

Real `mcp_feedback` container on the local Docker host at 1 CPU / 2 GiB (the ADR-065 proxy
configuration), called over MCP HTTP from the host. Every figure here is observed. L-28 still
applies: this is a local Docker measurement on a 2015-era laptop CPU, not Cloud Run.

Artifact `bert_v1`, `model_version` `0fa27f641d95260d84b4742501dd47cade23f1f8ae0ff336d8cbf927f70333ad`.
`sentiment_predictions` was empty before step 1.

**Images.** Steps 1–3 ran on the image built from `eaf8329`. Its insert count was logged as
−1 (a multi-row INSERT's rowcount through SQLAlchemy and psycopg; fixed in `338e9b8` with
`RETURNING`). The answers were unaffected, because they recount from the table. Steps 1–4
scored at batch 16 with a cap of 300 per call. After the throughput re-measurement below,
`348e8d6` set batch 8 and a cap of 250. Steps 5–6 ran on that image but scored nothing new.

## Results

| Step | Call | Wall time | n_comments | n_scored | complete |
|---|---|---|---|---|---|
| 1 | Cold start: `compose up` to ready (hash check only, no model) | 14.9 s | | | |
| 1′ | Cold start again, first start after a Windows restart (`348e8d6`) | 29.4 s | | | |
| 2a | Largest region-quarter (northeast, 2026 Q2), cold: lazy load + on-demand scoring | 45.0 s | 225 | 225 | true |
| 2b | Same, everything stored | 0.06 s | 225 | 225 | true |
| 3 | Largest all-accounts quarter (2025 Q4), before backfill | 43.1 s | 736 | 300 | false |
| 4 | Backfill (`docker compose run`), 6,996 inserted | 856.6 s (14.3 min) | 7,521 | 7,521 | true |
| 5a | 2025 Q4 after backfill | 1.03 s | 736 | 736 | true |
| 5b | West, 2026-03-01 to 2026-08-30, monthly | 0.07 s | 241 | 241 | true |
| 6a | Examples, negative, limit 5 (2025 Q4) | 0.10 s | 736 | 736 | true |
| 6b | Examples, mixed, limit 5 (2025 Q4) | 0.05 s | 736 | 736 | true |
| 6c | Examples, flagged_only, limit 5 (2025 Q4): 4 returned, all there are | 0.05 s | 736 | 736 | true |

Model load (lazy, logged): 1.18 s. In step 2a, scoring the 225 comments took 43.7 s; in step 3,
scoring 300 took 43.0 s. Step 3 stored 300 + 0: step 2's comments are outside 2025 Q4.

West monthly (step 5b), by bucket: n scored, then positive/neutral/negative/mixed, then flagged:
2026-03 36 (21/9/5/1, 0); 04 42 (20/15/5/2, 1); 05 49 (23/10/8/8, 0); 06 45 (22/12/8/3, 1);
07 37 (18/9/4/6, 0); 08 32 (16/4/7/5, 0).

## Throughput re-measurement (`throughput.json`, `throughput_measure.py`)

Real image, 1 CPU / 2 GiB (cgroup `cpu.max` 100000 100000, memory 2 GiB), 1 torch thread. Pure
inference through the service's `BertClassifier` on the 300 oldest 2025-Q4 comments, no
database writes. One untimed warm-up pass, then batch sizes interleaved, 3 repeats each.

| Batch | Runs (s) | Median s | Max s | Median /s | Slowest /s |
|---|---|---|---|---|---|
| 8 | 32.33, 31.84, 31.40 | 31.84 | 32.33 | 9.42 | 9.28 |
| 16 | 34.84, 35.45, 35.59 | 35.45 | 35.59 | 8.46 | 8.43 |

Batch 8 has the lower median. The cap is the largest multiple of 50 with cap ÷ 9.28 ≤ 30 s:
**250** (26.9 s worst case; 300 would be 32.3 s). The untimed first pass took 68.8 s,
including the 1.25 s model load: about twice a warm pass.

The proxy measured 10.74/s at batch 16. The comments here match the proxy's train-split
texts in length (24.6 against 24.4 mean tokens) and in padding (41.5 padded tokens per comment
at batch 16 in both), so the texts don't explain the gap. The proxy ran a separate image on a
Docker VM that has since been rebuilt; the cause isn't isolated. Batch 8 pads less: 38.2
padded tokens per comment against 41.5.

## Reproducibility and totals (`reproducibility_and_totals.json`, as `app_eval`)

The stored predictions for the 1,128 test-split comments match `2026-10-01_bert_v1/bert_v1.predictions.csv`
on predicted label 1,128/1,128 and on flag 1,128/1,128. The largest confidence difference is
0.00005, which is the 4-place storage rounding. This read predictions only: no labels, test
not scored, ledger untouched.

Stored, all 7,521: positive 3,771, neutral 1,685, negative 1,464, mixed 601; flagged 54
(0.72%): positive 33, negative 11, mixed 8, neutral 2.
