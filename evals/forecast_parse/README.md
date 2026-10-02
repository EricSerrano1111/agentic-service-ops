# Forecast parse set (`parse_v1.jsonl`)

14 questions for the forecast agent's one LLM call (ADR-072), each labelled with the
`ForecastRequest` it should parse to. Written and committed before any live call; **labels
never change after a run.** A disputed label is judged on its merits and recorded with the
results, not edited here.

As-of date: 2026-08-30. Periods follow `services/agent_forecast/prompts/parse_v1.md`:
forecast questions are about the future, so a bare month or quarter means its next
occurrence; "next month" is September 2026.

| Category | n | Notes |
|---|---|---|
| total | 3 | next month; next 8 weeks with history; December |
| service_type | 3 | f04 (install, 10 weeks) spans an unserved and a served band |
| beyond_horizon | 2 | next year (2027); Q2 2027 |
| unsupported | 4 | SLA outlook, incidents, by region, a past month; other fields as stated |
| ambiguous | 2 | see below |

Judgement calls behind the ambiguous labels:
- **f13 "in January"**: its next occurrence after the as-of date, January 2027, not
  January 2026, which has passed.
- **f14 "the coming quarter"**: the next calendar quarter, Q4 2026, per the prompt's rule.

`run.py` runs the set k times with the agent's own `Parser` on the free key.
