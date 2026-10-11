# QA fault injection, measurement 3, 2026-10-11 (ADR-095)

The same frozen catalogue and seed as measurements 1 and 2, run against QA with the forecast
recompute enabled (ADR-095). Measurements 1 and 2 are kept; this one replaces neither.

- `base_answers.json` is a copy of measurement 2's (byte-identical), so the same 390 cases ran
  (425 case records, as in m2).
- `hashes_before.txt` and `hashes_after.txt` are the SHA-256 of the four frozen files, taken
  before and after the run; they are identical to ADR-093's recorded LF values.
- **The fix was designed after seeing measurement 1's miss of owner fault 2.** This measurement
  shows it works on that case. It is evidence the fix works, not a catch rate for faults nobody has
  thought of (ADR-092, ADR-095); the faults are drafted by the assistant that built QA (L-85).
- No model was called (`LLM_MAX_REQUESTS=0`). The interpretation client is the same fake that always
  says `faithful`; measurements 1 and 2 logged 0 advisories, so no advisory result changed any outcome
  there and none is needed here.
- Compared with measurement 2, 19 case outcomes differ, all of them a newly fired
  `forecast_numbers_recomputed`: O2 6 of 6 (passed 0 of 6 before), F01 4 and F03 9 (caught either
  way, one more check fired). No other case changed.
