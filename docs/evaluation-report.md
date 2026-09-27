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
