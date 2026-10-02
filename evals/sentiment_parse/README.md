# Sentiment parse set (`parse_v1.jsonl`)

14 owner-reviewable questions for the sentiment agent's one LLM call (ADR-068), each
labelled with the `SentimentRequest` it should parse to. Written and committed before
any live call; **labels never change after a run.** A disputed label is judged on its
merits and recorded with the results, not edited here.

As-of date: 2026-08-30 (ADR-050). Dates follow `services/agent_sentiment/prompts/parse_v1.md`.

| Category | n | Notes |
|---|---|---|
| region_trend | 4 | p01 is FR-07's question, with no period: dates null (code applies ADR-068's default) |
| time_summary | 3 | last quarter, this year, a named month |
| examples | 2 | with a label; one with a region |
| unsupported | 3 | account, technician, service type; dates labelled as the question states them |
| ambiguous_date | 2 | see below |

Judgement calls behind the ambiguous labels:
- **p13 "in the spring"**: the prompt defines no seasons. Labelled as March to May of the
  as-of year (2026-03-01 to 2026-05-31), the meteorological spring most recently complete.
- **p14 "in August"**: the prompt's rule for a named month without a year is the most
  recent such month that *ends* on or before the as-of date. August 2026 ends on the 31st,
  after 2026-08-30, so the label is August 2025. A reader may well mean August 2026; the
  label tests the stated rule.

`run.py` runs the set k times with the agent's own `Parser` and the free key, scoring
per-field accuracy and whole-request exact match.
