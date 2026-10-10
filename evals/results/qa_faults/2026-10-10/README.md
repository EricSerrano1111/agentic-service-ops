# QA fault injection, 2026-10-10 (ADR-091)

- Freeze commit `b5ad1f4` (2026-10-10 12:32:45 CDT): catalogue v1, generator, seed `20261010`, mutations,
  report format. The first QA verdict was produced after it. `results.json` records the SHA-256 of the
  four frozen files; none changed after the freeze.
- `base_answers.json`: the 62 clean base answers (and the owner's anchors). `mutation_check.json`: the
  mutations made once with no QA, before the freeze. `results.json`: controls and cases. `report.md`:
  the tables of `report_format.md`.
- **Not blind.** The 47 assistant-drafted faults were written by the assistant that built QA. The owner's
  five faults (8 variants) are owner-selected, AI-co-written, and are reported in their own section.
- No model was called by the measurement. The interpretation client was a fake that always says
  `faithful`.

## Why the misses did not fire (written by hand after the run)

- **F08 (forecast text figure +1), 4 of 9 cases passed.** `forecast:f05`: the changed figure, 62, is the
  ceiling of the true 61.07; the text check accepts floor, ceiling and round of a rounded figure as the
  same number. `forecast:f14`, `f04`, `f02`: the changed figure equals another number the answer already
  states (another week's point forecast, or a range bound); the check compares the set of stated numbers
  and does not know which figure sits where (L-82).
- **O2 (owner: holiday weeks flattened), 6 of 6 passed.** Intervals, totals, served flags, shown errors and
  history were all consistent, which is all QA checks of a forecast; it does not recompute point
  forecasts (L-83). Stated in the catalogue before the run.
- **O4a / O4b (presentation of a small sample), 1 case each, passed.** The data part is untouched and
  every number in the text is in it; QA does not check the ranking or marking rule (L-84). Expected
  `known_gap`.
- **Misparse (M*, O5), 0 of 71 caught.** Figures are correct for the wrong request and the interpretation
  check is advisory (L-74). Expected `known_gap`.
- **False alarm, control `reporting:f09`.** A correct zero-denominator answer; QA's text check requires
  the numerator `0` to be stated and the text says "no dispatched requests" (L-81).

## Loop demonstration (5 of 10 live calls)

A fault-injecting proxy (`evals/qa_faults/proxy/`, a compose override, test only) sat between the
orchestrator and the reporting agent. Question: "How many incidents were reported in July 2026?"

| | FAULT=R01 (count +1) | FAULT=NONE |
|---|---|---|
| outcome | `degraded`, `escalate: true`, answer not shown | `answered`, 54 incidents |
| QA | `fail`, `figures_match_database`, attempt 1 | `pass`, attempt 1 |
| `qa_status` | `not_checked` (degraded result) | `verified` |
| reporting tasks | 1 (no retry) | 1 |
| live calls | 2 (routing, parse) | 3 (routing, parse, advisory interpretation) |
| list-price cost | $0.000948 | $0.001604 |
