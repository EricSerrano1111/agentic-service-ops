# Sentiment agent: parse evaluation and end-to-end (observed), 2026-10-01

All live calls used the free key on `gemini-3.5-flash-lite` (ADR-049): 42 in the parse
evaluation plus 12 end to end, **54 in total** against a budget of 70. No paid key.

## Parse evaluation (`parse_parse_v1_k3.json`)

Set `evals/sentiment_parse/parse_v1.jsonl` (14 questions, committed before any run),
prompt `parse_v1` (`0f61684af8cf`), as-of 2026-08-30, k = 3. Scored on the model's reading
before code applies a default range.

| Run | Exact match | start | end | region | bucket | want_trend | want_examples | example_label | unsupported |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 13/14 | 13 | 13 | 14 | 14 | 14 | 14 | 14 | 14 |
| 2 | 13/14 | 13 | 13 | 14 | 14 | 14 | 14 | 14 | 14 |
| 3 | 13/14 | 13 | 13 | 14 | 14 | 14 | 14 | 14 | 14 |

Range 13–13, no flips between runs. The stop rule (under 12/14) did not fire; no revision.
The one miss in every run is p14 "How was sentiment in August?": the model returned
2026-08-01 to 2026-08-30, against the label 2025-08-01 to 2025-08-31 that the prompt's own
rule gives. The label stands; judged on its merits in L-38.

## End to end (`e2e.json`)

The stack was brought up with `docker compose up -d orchestrator` (orchestrator,
agent_reporting, mcp_incidents, agent_sentiment, mcp_feedback; Postgres already running):
**50.7 s** to the orchestrator's first healthy response. Questions went through `POST /ask`
on the orchestrator's public port.

| Question | Wall time | HTTP | Outcome | Route |
|---|---|---|---|---|
| 1. "Is sentiment trending down in the West?" (first after cold start) | 2.62 s | 200 | answered | sentiment |
| 1. same, warm | 1.76 s | 200 | answered | sentiment |
| 2. "How did customers feel last quarter?" | 1.64 s | 200 | answered | sentiment |
| 3. "Show me a few negative comments from July." | 1.91 s | 200 | answered | sentiment |
| 4. "What's sentiment for our largest account?" | 1.39 s | 200 | not_available (decline) | sentiment |
| 5. "How many incidents were reported last month?" (seed_v1 s01) | 2.23 s | 200 | answered | reporting |

"Cold" here is the first question after the whole stack started. `mcp_feedback` did not
load the BERT model: every comment in range already had a stored prediction (ADR-067),
so no question needed on-demand scoring.

Question 1's trend figures were checked against independent SQL as `app_eval`: latest
month 7 of 32 negative, earlier months 30 of 209. By hand: pooled share 37/241, standard
error 0.0684, z = 1.099, p = 0.272; the agent reported p = 0.2718, "no clear change".

Live calls counted from the containers' metering lines: orchestrator 6 (routing),
agent_sentiment 5 (parses), agent_reporting 1; all `"mode": "free"`.

The full answers are in `e2e.json` (`runs[].response.answer`).
