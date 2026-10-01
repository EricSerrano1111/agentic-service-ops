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

### L-19 — The forecast headline holdout excludes the Q4 peak (2026-09-30)
- **What:** The headline holdout is the final 26 weeks, about March to August 2026, so it
  never contains the Q4 budget-flush peak. Rolling-origin folds with test windows over the
  Q4 2024 and Q4 2025 peaks cover it, each reported separately (ADR-057). The earliest
  fold, before Q4 2024, has about one year of history: one seasonal cycle to learn from.
- **Why accepted:** The 36-month window leaves no way to hold out a full year and still
  train on two; the folds test the peak with the history that exists.
- **Recorded in:** ADR-057; ADR-018; `data-dictionary.md` §6.

### L-20 — The generator's seasonality has three harmonics; K is chosen from data (2026-09-30)
- **What:** The generator builds annual seasonality from three sine/cosine pairs. The
  forecast model chooses its number of pairs, K, by an information criterion on training
  data and never fixes it at 3, which would recover the answer key (ADR-058). The chosen K
  may differ from 3 and is reported.
- **Why accepted:** A model told the generator's basis would show recovery of a known
  signal, not that the method works.
- **Recorded in:** ADR-058.

### L-21 — Disruption down-weighting never uses the generator's anomaly list (2026-09-30)
- **What:** Disruptions in the volume history are down-weighted by a residual-based robust
  method using only information an operator would have, never the planted anomalies in
  `parameters.py` (ADR-058). The method may down-weight weeks that aren't planted anomalies
  or miss part of one that is.
- **Why accepted:** Using the anomaly list is answer-key leakage.
- **Recorded in:** ADR-058; ADR-038 (the planted anomalies).

### L-22 — Sentiment test split and hard-case counts (2026-09-30)
- **What:** Computed from the loaded data (7,521 labelled feedback rows): a 15% split,
  stratified by class and hard-case type (ADR-059), gives about 1,128 test comments, of
  which 168 are hard cases: 42 sarcastic (all negative) and 126 implicit (32 negative, 94
  positive). Exact numbers are fixed when the split is made, since keeping near-duplicates
  on one side can move a few. Per-type scores on 42 or 126 comments are noisy, so counts
  are reported with every per-type score.
- **Why accepted:** The dataset size is fixed by ADR-038's corpus sizing; a larger test
  split would starve training.
- **Recorded in:** ADR-059; `sentiment_labels` counts as of the 2026-09-26 load.

### L-23 — Sentiment accuracy measures agreement with the specification (2026-09-30)
- **What:** Sentiment labels are defined by a written specification and applied to
  synthetic, LLM-written text (ADR-036, ADR-040). Accuracy therefore measures agreement
  with the specification on that text, not with how real customers write or what they
  meant. This extends L-12 from the labels to the trained model's reported accuracy.
- **Why accepted:** There is no real feedback corpus in this project (ADR-030).
- **Recorded in:** ADR-040; ADR-059; L-12.

### L-24 — Star ratings share the label's latent sentiment, so the QA cross-check is optimistic (2026-09-30)
- **What:** `generate.py` draws each rating from the row's true sentiment alone
  (`rating_given_sentiment` in `parameters.py`: positive 3-5, neutral and mixed 2-4,
  negative 1-3; 10% unrated). The comment's style, sarcastic or implicit, plays no part.
  Rating and text therefore share one latent variable, the label the text was written to.
  In the loaded data, no row is a clear contradiction (positive on 1-2 stars, negative on
  4-5): 0 of 7,521. So the "normal rate" ADR-055 measures on labelled data is zero here,
  and every clear contradiction in an answer is a misclassification. Real customers do
  give stars that disagree with their words, so the cross-check will agree more often here,
  and its QA catch rate will look better, than it would on real feedback. Hard cases get
  ratings that match their intended sentiment, so the check catches exactly the misreads
  that are hardest for the model.
- **Why accepted:** Changing how ratings are generated would mean regenerating the
  dataset (R-07). The rating remains a genuinely independent input to QA, since the
  sentiment agent can't read it (ADR-027). The optimism is stated with every QA catch-rate
  result.
- **Recorded in:** ADR-055; `data/generator/parameters.py` (`rating_given_sentiment`);
  `data/generator/generate.py` (`build_sentiment`).
- **Update 2026-09-30:** A Sprint 5 sensitivity check measures how much this optimism
  matters: flip a few percent of ratings to mimic real-world rating/text disagreement and
  report the QA catch rate with and without (`docs/sprint-log.md`, Sprint 5 Planned).

### L-25 — Grants control which tables and columns training reads, not which rows (2026-10-01)
- **What:** `app_train` reads `sentiment_labels` in full (ADR-063). Postgres grants scope
  tables and columns, not rows, so nothing at the database level stops a training script
  from reading the labels of the sentiment test split, or the forecast holdout weeks.
  The grant rules out `rating` and `generation_parameters`; it does not rule out training
  on the test set.
- **Why accepted:** Row-level security keyed to a split would mean storing the split in
  the database and a policy per table, for one developer on one machine. Split integrity
  rests instead on the split being fixed and committed before training, and on code review
  of the training scripts. ADR-057 fixes the forecast holdout by date; ADR-059 defines the
  sentiment split but does not yet require it to be committed before training, so the
  Sprint 3 training work has to do that.
- **Recorded in:** ADR-063; `docs/data-dictionary.md` §7.

### L-26 — The TF-IDF baseline's selected config sits at the edge of its fixed grid (2026-10-01)
- **What:** Of ADR-064's six configs, validation macro-F1 rose with C for both feature
  sets and peaked at the largest value, C=10 (word 1-2-grams 0.9333; `char_wb` 2-5-grams
  0.9280). A larger C might score higher, so the baseline BERT is compared against may be
  slightly understated.
- **Why accepted:** The grid was fixed before any result and is never extended (ADR-064);
  extending it after seeing validation scores is the search drift the protocol exists to
  prevent. The validation gain from C=1 to C=10 was 0.018 for word features.
- **Recorded in:** ADR-064; `evals/results/sentiment/2026-10-01_baselines/tfidf_validation_grid.json`.
- **Update 2026-10-01 (validation only):** C=30 and C=100 were run on validation, for
  both feature sets, without scoring test or changing the selected config. Validation
  macro-F1: word 1-2-grams 0.9413 (C=30) and 0.9396 (C=100); `char_wb` 2-5-grams 0.9408
  (C=30) and 0.9402 (C=100). Both peak at C=30. The best gain over the selected config
  (word, C=10, 0.9333) is +0.0080, from word C=30. The reported TF-IDF baseline is
  therefore about 0.008 validation macro-F1 below what a slightly wider grid would have
  found; ADR-065's comparison reports this beside the result. Results:
  `evals/results/sentiment/2026-10-01_baselines/grid_extension_validation_only.json`.

### L-27 — Length alone identifies minimal neutral comments (2026-10-01)
- **What:** The length-only diagnostic classifies every minimal neutral correctly on test
  (18 of 18) while scoring macro-F1 0.3331 overall. Minimal neutrals are written at 1-8
  words (the corpus cell's length bounds, ADR-036), so accuracy on that subgroup says little
  about reading the text. ADR-064's length rule (macro-F1 0.60 overall) did not fire.
- **Why accepted:** The subgroup is small (18 test rows) and is reported separately by
  neutral kind, so it can be read in that light. Changing the length rules would mean
  regenerating the corpus (ADR-030).
- **Recorded in:** ADR-064; `evals/results/sentiment/2026-10-01_baselines/diagnostic_length_logreg.test.metrics.json`.

### L-28 — BERT latency is a local CPU-limited proxy, not a Cloud Run measurement (2026-10-01)
- **What:** ADR-065's latency figures come from a local Docker container limited with
  `--cpus` and `--memory` on a 2015-era laptop CPU (Intel i7-6700HQ), running the pinned
  `bert-base-uncased` with an untrained head. Cloud Run's vCPU may be faster or slower
  per core, its cold start includes image pull and instance scheduling that a local
  `docker run` does not, and CPU throttling between requests differs. The numbers are
  labelled proxy for that reason.
- **Why accepted:** Measuring before training was the point (ADR-065): it catches a
  latency failure before hours of CPU training are spent. The latency item stays unticked
  until it is measured on the deployed container.
- **Recorded in:** ADR-065; `evals/results/sentiment/2026-10-01_latency_proxy/`.

### L-29 — Company-wide sentiment questions over a quarter or longer exceed the inference budget (2026-10-01)
- **What:** In the proxy, classifying the largest calendar quarter (736 comments) takes
  65 s at 1 CPU and 40 s at 2 CPUs; the last 12 months (2,666) 239 s and 148 s; the full
  window (7,521) 669 s and 410 s. All exceed ADR-065's 30 s warm budget, and the last two
  exceed the 120 s end-to-end ceiling (ADR-034) on their own. ADR-065 gates only on the
  largest single-account or single-region quarter, which passes, so a question like
  "sentiment last quarter" across all accounts is not covered by the gate. The 12-month
  and full-window figures are single runs (`--large-repeats 1`), not medians of three.
- **Why accepted:** For now, recorded rather than decided. ADR-065 already says
  whole-window questions need a different design (sampling or stored predictions). Whether
  company-wide quarters join the gate, or take that design too, is a decision for the
  `mcp_feedback` work.
- **Recorded in:** ADR-065; `evals/results/sentiment/2026-10-01_latency_proxy/summary.md`.
