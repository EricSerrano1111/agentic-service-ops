# Golden run scoring: pre-registration (Prompt X)

**Fixed on 2026-10-13, after Prompt W and before any `golden_v2` call.** The first golden call
is made after the commit that adds this file. `evals/sprint5_gates.md` §B3 says only that the
golden run is "scored by ADR-074's rules and `golden_v2`'s manifest"; ADR-074 left the method
for `must_not` open ("owner review or a rubric"). This file fixes the method. The owner ruled on
it on 2026-10-13. It changes no set, prompt or threshold.

## What is the score

The **headline score is mechanical**: an item passes when **every applicable component**
below passes. Components are also reported separately. The assistant does not judge `must` or
`must_not`: they go to the owner (see "Owner review").

The run is one pass over the 36 items, sequential, against the deployed orchestrator `/ask`,
no harness retries. An item with no usable response (HTTP error, timeout, malformed body) fails
every component ("error or timeout").

### C1. Outcome (every item)

The response's `outcome` is in the item's `acceptable_outcomes`, **and** if that entry names a
`reason`, the response's `reason` equals it, **and** if that entry names a `route`, the response's
`route.route` equals it. `degraded` never matches (no item accepts it).

### C2. Route (every item)

`route.route` is in `acceptable_routes`. For `needs_clarification` with `intent_ambiguous`, the
route must be `ambiguous`; the deployed default is `route_v3`, which has no `ambiguous` route,
so G35 is expected to fail C2 and C1 (L-58). It is scored as it falls.

### C3. Figures (items with an `oracle`, only when `outcome == answered`)

Compared with `golden_v2.expected.json`. If an item is answered but its acceptable outcomes
include only declines, C1 already fails; C3 is not computed. If an item with an oracle is
declined (an acceptable `not_available`), C3 is "not applicable" and the item passes on C1+C2.
Money-style rates are the strings the system returns; they are compared as strings, exactly.

| Oracle | Rule |
|---|---|
| g03, g11, g13, g17 (reporting, ungrouped or by region/service type) | `start`, `end` equal; `figures.numerator`, `denominator`, `rate` equal `overall`; where `worst_first` is given, the payload groups with `denominator >= 20`, in the payload's order, begin with the expected list (group, numerator, denominator, rate all equal, same order). |
| g12 (by account) | as above against `worst_first_in_text` (top entries; `group_count` is also compared). |
| g14 | `incident_count` and `by_severity` equal; `group_by` is `severity` or null. |
| g15 | `numerator`, `denominator`, `rate` equal; `technician_name` is "Priya Kim". |
| g18 | `overall` (jobs, repeated, rate) equal; each expected group's jobs, repeated, rate, `compared`, `stands_out` equal; `group_by` is `region`. |
| g02 (stretch) | If answered: with `region` null, `overall` equals `all_regions`; with `region` central, equals `central`; any other region fails. Range equals `start`..`end`. |
| g04, g05 (stretch) | The queried range equals one of `acceptable_ranges`; the matching expected block's `comments`, `counts`, `shares`, `flagged` equal `summary.n_comments`, `counts`, `shares`, `flagged_count`; `region` equal. |
| g20, g21 | `start`, `end`, `region`, `comments`, `counts`, `shares`, `flagged` equal. g21 also: each `buckets` entry (comments, counts, flagged) equal; trend `verdict` equal; `latest`/`earlier` counts equal; `p_value` within 1e-6. |
| g22 | Range equals `start`..`end`; the examples returned are `examples_expected` (3); every example's `feedback_id` is in `eligible_feedback_ids` and its label is `mixed`. |
| g07, g10, g25, g26, g27 (forecast) | `model_version` equals `manifest_sha256`; the set of `week_start` values equals the expected set (G07: the 26 served weeks; `beyond_horizon_weeks` > 0); for each week: `served` equals expected, served weeks' `point` within 1e-6, unserved weeks carry no numbers. G27 (`withheld`): if answered, every week is unserved. G10 is a stretch item. |

### C4. Reason code (G01, G16, G35)

Covered by C1 (the `reason` equality). Reported on its own line.

## Owner review: `must` and `must_not`

Not scored by the assistant. After the run:

- `evals/results/sprint5_x/golden_owner_review.csv`: item id, question, answer text, `must`,
  `must_not`, empty `owner_pass`, empty `owner_note`. The owner fills it in during Prompt Y. It is
  a **second** column of results, not part of the headline.
- `evals/results/sprint5_x/golden_assistant_reading.md`: the assistant's own per-item reading of
  `must`/`must_not`. **Assistant opinion, not the score.**

## Reporting rules

- Overall, per behaviour, per author (owner vs drafted), the four stretch items (G02, G04, G05,
  G10; L-56) reported separately and also included in the overall.
- G35 reported on its own (expected to fail under `route_v3`, L-58).
- The check-note items (region, account, tie order; sprint log 2026-10-08 and 2026-10-09) are
  reported with the answer against the oracle expectation and, for any item whose expectation
  looks wrong, a flag for the owner. **The golden set is not edited.**
- Latency per item. Any request over the 120 s deadline (R-05) is listed.
