# Reporting parse set (`parse_v3.jsonl`)

16 questions for the reporting agent's one LLM call (ADR-046, ADR-073), each labelled with
the `ReportingRequest` it should parse to. Written and committed before any live call;
**labels never change after a run.** A disputed label is judged on its merits and recorded
with the results, not edited here.

As-of date: 2026-08-30. Dates follow `services/agent_reporting/prompts/parse_v3.md`
(ADR-050): "last month" is July 2026, "last quarter" Q2 2026, "this quarter" 2026-07-01 to
2026-08-30. A question with no dates parses to null dates; code applies the default.

| Category | n | Notes |
|---|---|---|
| metric | 4 | one per metric, one with a breakdown |
| count_breakdown | 3 | incident counts by account, severity, incident type |
| technician | 3 | a unique full name (Ben Okafor), a shared first name (Priya: two technicians), a name nobody has (Marcus) |
| repeat_drivers | 2 | d01 is the business-case wording ("which incident types are driving the most repeat visits") |
| dates | 2 | "last quarter"; a bare month ("in March", L-38) |
| routing_v1 | 2 | r15 and r17, the technician questions routing sends here |

Scoring: field by field (`metric`, `group_by`, `technician_name`, `start`, `end`) and as
a whole request. `technician_name` is compared case-insensitively with whitespace
collapsed, because `find_technician` matches that way; every other field exactly. A
failed parse scores as wrong on every field.

Judgement calls behind the labels:
- **r15 "meeting his appointment windows"**: `sla_compliance`. The SLA window is the
  only completion-window metric; arrival against the scheduled slot isn't one the agent
  offers. No dates, so null.
- **r17 "average resolution time"**: `unsupported` (no resolution-time metric), with
  `technician_name` "Sarah" still copied, since the question names her; "the last two
  weeks" is the 14 days ending on the as-of date.
- **c03 "the past 30 days"**: the 30 days ending on the as-of date, 2026-08-01 to
  2026-08-30.
- **t03, r15, r17**: Marcus, Dave and Sarah match no technician; the parse copies the
  name and `find_technician` returns no match.

`run.py` runs the set k times with the agent's own `Parser` on the free key.
