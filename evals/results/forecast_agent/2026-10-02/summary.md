# Forecast agent: parse evaluation and end-to-end (observed), 2026-10-02

All live calls used the free key on `gemini-3.5-flash-lite` (ADR-049): 42 in the parse
evaluation plus 14 end to end, **56 in total** against a budget of 70. No paid key.

## Parse evaluation (`parse_parse_v1_k3.json`)

Set `evals/forecast_parse/parse_v1.jsonl` (14 questions, committed before any run), prompt
`parse_v1` (`44cd63997912`), as-of 2026-08-30, k = 3.

| Run | Exact match | slice | horizon_weeks | period_start | period_end | want_history | unsupported |
|---|---|---|---|---|---|---|---|
| 1 | 14/14 | 14 | 14 | 14 | 14 | 14 | 14 |
| 2 | 14/14 | 14 | 14 | 14 | 14 | 14 | 14 |
| 3 | 14/14 | 14 | 14 | 14 | 14 | 14 | 14 |

Range 14–14, no flips. No revision; the set stays unused for tuning.

## End to end (`e2e.json`)

`docker compose up -d orchestrator` brought up all seven services (Postgres already
running): 70.3 s to the orchestrator's first healthy response. Questions went through
`POST /ask` on the orchestrator's public port.

| Question | Wall time | Outcome | Route | Shape of the answer |
|---|---|---|---|---|
| "What will request volume look like next month?" | 2.54 s | answered | forecast | 4 weeks (Sep 7 to Oct 4), total 649, bands 1-4 (13.6%) and 5-13 (5.5%) |
| "Forecast install requests for the next 10 weeks." | 1.63 s | answered | forecast | weeks 1-4 refused (43.7%), weeks 5-10 served (18.0%), no total |
| "How busy will December be?" | 1.50 s | answered | forecast | 4 weeks (Dec 7 to Jan 3), total 555, year-end caveat |
| "Forecast volume for the next year." | 1.75 s | answered | forecast | 25 weeks served to the cap, 27 beyond the horizon |
| "What's the SLA outlook for Q4?" | 1.52 s | not_available | forecast | decline naming what is supported |
| "How many incidents were reported last month?" | 2.12 s | answered | reporting | unchanged: 54 incidents in July |
| "How did customers feel last quarter?" | 2.21 s | answered | sentiment | unchanged: 723 comments, Q2 2026 |

"The next year" parsed as the coming 12 months (Sep 2026 to Aug 2027), so its first week is
2026-09-07, as for "next month" (L-50). The full answers are in `e2e.json`.

Live calls counted from the containers' metering lines: orchestrator 7 (routing),
agent_forecast 5, agent_reporting 1, agent_sentiment 1; all `"mode": "free"`.
