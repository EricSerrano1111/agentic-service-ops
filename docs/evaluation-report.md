# Evaluation Report — Agentic Service Operations Intelligence Platform

*Stub. The report itself is written in Sprint 6 from the Sprint 5 eval runs (ADR-044).
Until then, only the limitations log below is maintained.*

---

## Limitations log

Append-only: one dated entry per limitation, each saying what it is, why it is accepted, and
where it is recorded. Never edit or delete an entry; if a limitation is later resolved or
changes, append a new dated entry that refers back to it. New limitations found during the
build are appended here as they are found (CLAUDE.md).

### L-01 — First-time fix rate is unrealistically high in the synthetic data (2026-09-26)
- **What:** Over the full window, first-time fix is about 98% (0.9798), well above what
  field-service operations typically report.
- **Why accepted:** It is an artifact of the generation parameters, not of the metric or
  the tools. Regenerating for it alone isn't worth it (R-07). Tune it in `parameters.py`
  only if the data is regenerated for another reason.
- **Recorded in:** first recorded here; R-07 covers when regeneration is warranted.

### L-02 — First-time fix excludes cancelled follow-up requests (2026-09-26)
- **What:** A cancelled child request does not count against its parent. 38 of 402 child
  requests are cancelled, drawn from the general cancellation rate, not generated
  deliberately. Full-window effect: 0.9798 with them excluded against 0.9777 counted.
- **Why accepted:** First-time fix measures whether a return visit happened, and a
  cancelled follow-up means none did (owner's decision under the FR-06 stop rule).
- **Recorded in:** `docs/data-dictionary.md` §6 (first-time fix definition).

### L-03 — The routing seed set is too easy to separate models (2026-09-26)
- **What:** `evals/routing/seed_v1.jsonl` has 28 questions, written by the same assistant as
  the routing prompt, so the two share vocabulary. Flash-Lite scored 28/28 and 3.7 Flash
  27/28. The one miss (s16, "Are complaints going up?") is on a contestable label.
- **Why accepted:** The seed set only seeds the Sprint 3 routing set. That harder set,
  with ambiguous and near-miss out-of-scope items written by the owner in dispatch
  phrasing, is the real test of both models.
- **Recorded in:** ADR-049; `evals/routing/README.md`; `evals/results/routing_seed_v1_*.json`.

### L-04 — Two Gemini error-body fixtures are assembled, not observed (2026-09-26)
- **What:** A pure per-minute 429, and a daily quota used up after normal traffic, have no
  captured real body. Their test fixtures are built from the observed zero-quota 429.
- **Why accepted:** Neither could be provoked on demand (the burst hit a 503 first).
  Passive first-429 capture in `packages/llm` logs the first real one a process receives.
- **Recorded in:** ADR-048; `tests/unit/test_llm_client.py` (OBSERVED and ASSEMBLED markers).

### L-05 — Provider capacity: free-tier "high demand" 503s (2026-09-26)
- **What:** Free-tier "high demand" 503s were observed on `gemini-3.7-flash`, including
  three in a row during a checkpoint e2e run.
- **Why accepted:** The orchestrator moved to Flash-Lite, which hasn't produced them so
  far. The bounded 5xx retry in `packages/llm` is the mitigation.
- **Recorded in:** R-15; ADR-049.

### L-06 — Reporting coverage at the end of Sprint 2 (2026-09-26)
- **What:** Incident counts can't be broken down; repeat-visit drivers are deferred to
  Sprint 3; technician home region isn't a breakdown.
- **Why accepted:** These are scope boundaries, not defects. An unsupported question gets
  a "not available yet" answer, never a guessed metric.
- **Recorded in:** here; `docs/sprint-log.md` (Sprint 2) records the repeat-visit deferral.

### L-07 — Stored site region is nullable in the database (2026-09-26)
- **What:** `locations.region` has no NOT NULL constraint.
- **Why accepted:** The column was added to an already-loaded table, and no migration may
  fill it without a second copy of the mapping or a live-data read (ADR-027).
  Completeness is enforced by the generator's invariants and `validate.py` check A23.
- **Recorded in:** ADR-051; `docs/data-dictionary.md` (`locations`).

### L-08 — Answer text ranks only groups with at least 20 cases (2026-09-26)
- **What:** Grouped answers leave groups with fewer than `REPORTING_MIN_GROUP_DENOMINATOR`
  cases (default 20) out of the ranked text, and say how many were left out.
- **Why accepted:** It is a presentation rule, not a metric definition: a group with a
  handful of cases can top a ranking on one event. The data part carries every group
  with its counts.
- **Recorded in:** `services/agent_reporting/src/agent_reporting/render.py` and its config;
  `docs/sprint-log.md`.

### L-09 — ADR-036: sentiment corpus labels and evidence (2026-09-26)
- **What (from the ADR):** "Plain labels are judge-confirmed, not only
  generator-intended. Hard-case labels remain intent verified by sampling." "Judge
  filtering biases plain cells toward comments Gemma reads clearly, so the plain subgroup
  is easier than real plain feedback." The single-annotator and believability limitations
  it also assigns were revised by ADR-040 (see L-12).
- **Why accepted:** Decided in ADR-036.
- **Recorded in:** ADR-036; re-pointed to this report by ADR-044.

### L-10 — ADR-038: anomaly strength (2026-09-26)
- **What (from the ADR):** "The final paper reports anomaly strength as z-scores against
  the effective noise."
- **Why accepted:** Decided in ADR-038.
- **Recorded in:** ADR-038; re-pointed to this report by ADR-044.

### L-11 — ADR-039: positive feedback on incident rows (2026-09-26)
- **What (from the ADR):** "The text of those rows carries no incident-specific signal,
  which is a realism cost stated in the paper."
- **Why accepted:** Decided in ADR-039.
- **Recorded in:** ADR-039; re-pointed to this report by ADR-044.

### L-12 — ADR-040: sentiment labels are specification-defined (2026-09-26)
- **What (from the ADR):** "The paper states that labels are specification-defined and that
  sentiment accuracy is measured against the specification. The owner's review results
  are reported as evidence of the category's ambiguity." "No believability claim is made
  for the corpus."
- **Why accepted:** Decided in ADR-040.
- **Recorded in:** ADR-040; re-pointed to this report by ADR-044.

### L-13 — ADR-043: the SLA-incident relationship is planted (2026-09-26)
- **What (from the ADR):** "The SLA-incident relationship is planted. When the reporting
  agent surfaces it, that is recovery of a known signal, useful for evaluation, and the
  paper says so."
- **Why accepted:** Decided in ADR-043.
- **Recorded in:** ADR-043; re-pointed to this report by ADR-044.

### L-14 — routing_v1 on route_v1: no Flash advantage; ADR-049 stands (2026-09-30)
- **What:** `evals/routing/routing_v1.csv` (18 questions written by Eric in dispatch
  phrasing, blind to model output) run on prompt `route_v1`:

  | | Flash-Lite (free key, thinking `minimal`) | 3.7 Flash (paid key, thinking `low`) |
  |---|---|---|
  | Overall | 17/18 (94%) | 16/18 (89%) |
  | ambiguous | 8/8 | 7/8 |
  | near_miss | 4/5 | 4/5 |
  | technician | 5/5 | 5/5 |
  | Errors | 0 | 0 |

  Misses: r11 for both (out_of_scope, routed to sentiment; see L-15), and r04 for 3.7 Flash
  (forecast, routed to out_of_scope, because `route_v1` defined forecast as request
  volume only). 3.7 Flash ran at thinking `low` because it rejects `minimal`, as in the
  2026-09-26 seed run, so the two models did not run at the same thinking level.
- **Why accepted:** This is the harder set L-03 called for, and 3.7 Flash showed no
  advantage on it either, so ADR-049 stands. With 18 questions, a one-question gap is
  within noise (L-17).
- **Recorded in:** `evals/results/routing_routing_v1_*_route_v1_*.json`; ADR-049.

### L-15 — routing_v1 r11 is a contested label (2026-09-30)
- **What:** r11, "Why did the Peterson account decide not to renew their service
  contract?", is labelled out_of_scope. Both models routed it to sentiment, reading the
  reason for non-renewal as something customers say in feedback.
- **Why accepted:** That reading is defensible, but the reason for a commercial decision
  isn't in the dispatch data, so the label is kept. r11 counts as a miss in every
  routing_v1 result.
- **Recorded in:** `evals/routing/routing_v1.csv` (r11 note).

### L-16 — routing_v1 is no longer blind (2026-09-30)
- **What:** `route_v2` (forecast covers forward-looking questions about the operation, not
  only request volume) was written after the routing_v1 results had been seen. Its
  rationale is to align the prompt with the routing_v1 labelling rule, which was written
  before any run. Even so, routing_v1 scores on `route_v2` and later prompts are no
  longer a held-out measurement.
- **Why accepted:** The prompt change follows a labelling rule fixed in advance, not
  individual misses. For an unbiased number, the Sprint 5 evaluation needs a fresh
  held-out routing set, including multi-domain questions in Eric's phrasing, that is
  never used to revise a prompt.
- **Recorded in:** ADR-053; `docs/sprint-log.md` (Sprint 5 Planned).

### L-17 — Routing is not deterministic at temperature 0 (2026-09-30)
- **What:** In the seed_v1 run on `route_v2` (Flash-Lite), s05 ("Which incident type was
  most common in July 2026 ...") was routed to forecast, with the reason that July 2026 is
  a future period. Three immediate repeats on each of `route_v2` and `route_v1` all
  returned reporting. The route prompt carries no current date, so the model's sense of
  "now" varies from call to call.
- **Why accepted:** Each recorded result is a single run, kept as run. A difference of one
  question between two single runs is within run-to-run variance, which affects every
  routing comparison so far (ADR-049, L-14). Giving the route prompt the dataset's as-of
  date (ADR-050) and running repeats would address it; neither is done yet.
- **Recorded in:** `evals/results/routing_seed_v1_gemini-3.5-flash-lite_route_v2_*.json`.

### L-18 — s05 and the as-of date; routing reported as a range of three runs (2026-09-30)
- **What:** L-17's s05 misroute ("July 2026" read as the future) came from a routing prompt
  with no current date. `route_v3` gives the router the as-of date the parser already uses
  (ADR-054), and s05 routed to reporting in all three `route_v3` runs. Run three times on
  Flash-Lite, routing still varies: seed_v1 27-28/28, routing_v1 16-17/18. s16 ("Are
  complaints going up?") flipped to forecast once and r02 flipped to out_of_scope once.
  The as-of date doesn't help s16, which has no date in it.
- **Why accepted:** The date fixes an inconsistency between the two LLM calls in one
  request. It does not remove run-to-run variance, which is model behaviour at temperature
  0. Reporting the range and the flipping questions makes that variance visible instead of
  hiding it in a single number. The improvement on s05 is not separable from noise
  (`route_v2` also returned reporting on three repeats), so no accuracy gain is claimed.
- **Recorded in:** ADR-054; `evals/results/routing_*_gemini-3.5-flash-lite_route_v3_*.json`;
  `docs/sprint-log.md` (Sprint 5 Planned).
