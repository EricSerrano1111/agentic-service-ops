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
- **Update 2026-10-02 (correction, results):** the description above is wrong about the
  generator. `parameters.py` builds seasonality from monthly factors
  (`seasonality_monthly_raw`) plus a late-December trough (`late_december_trough`, Dec 20 to
  Jan 1), not from three harmonics. A linear trend with harmonics approximates the monthly
  shape; the calendar year-end indicator (ADR-070) covers the trough. K chosen by AICc on
  all 156 weeks (`volume_v2`): total 2, inspection 2, install 2, maintenance 6, repair 2,
  upgrade 2. On fold B, v1 chose total 2, inspection 5, install 2, maintenance 6, repair 2,
  upgrade 2; on the holdout fit, v1 total 3 against v2 total 2: the indicator absorbs what v1
  spent a harmonic approximating. Results: `evals/results/forecast/`.

### L-21 — Disruption down-weighting never uses the generator's anomaly list (2026-09-30)
- **What:** Disruptions in the volume history are down-weighted by a residual-based robust
  method using only information an operator would have, never the planted anomalies in
  `parameters.py` (ADR-058). The method may down-weight weeks that aren't planted anomalies
  or miss part of one that is.
- **Why accepted:** Using the anomaly list is answer-key leakage.
- **Recorded in:** ADR-058; ADR-038 (the planted anomalies).
- **Update 2026-10-02 (results):** weeks down-weighted below 0.5 by the `volume_v2` fit
  on all 156 weeks: total 2023-12-25, 2024-06-17, 2025-12-22, 2026-07-13; inspection
  2023-12-18, 2024-01-01, 2024-05-13, 2026-03-16, 2026-06-29, 2026-07-13; install
  2026-03-16, 2026-08-24; maintenance 2024-10-14, 2024-12-16, 2026-02-16; repair
  2024-01-29, 2024-06-17, 2026-03-09; upgrade 2024-06-17, 2024-08-12, 2025-01-13,
  2025-04-07, 2025-09-01, 2025-09-22, 2026-03-09. 2024-06-17 lies inside the planted volume
  drop (2024-06-10 to 06-23) for three slices; the other two planted periods
  (regional drop 2025-02-17 to 03-02, billing surcharge 2025-06-30 to 07-20) are not
  down-weighted on the total. Several year-end weeks are still down-weighted despite the
  indicator, because one indicator covers two weeks of unequal depth (L-43). The anomaly
  dates were read after fitting, for this note only.

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

### L-30 — Both BERT runs peaked at the epoch cap (2026-10-01)
- **What:** Both BERT runs reached their best validation macro-F1 at epoch 4, the maximum
  ADR-065 allowed (lr2e-5: 0.9401/0.9642/0.9679/0.9767). The model may be under-trained.
  The cap was fixed in advance and was not extended. This parallels L-26 for TF-IDF.
- **Why accepted:** Extending the cap after seeing the curve would be tuning outside the
  pre-registered budget (ADR-065, ADR-066). Like L-26, the gap is reported beside the
  comparison rather than closed.
- **Recorded in:** ADR-065, ADR-066; `models/sentiment/lr2e-5_v1/run.json`, `models/sentiment/lr3e-5_v1/run.json` (local, gitignored).

### L-31 — Calibration was fitted on the selection split, so validation calibration figures are optimistic (2026-10-01)
- **What:** T and τ for `bert_v1` were fitted on the same validation split used to select
  the run and epoch (ADR-066). Validation figures for calibration (ECE 0.0073 to 0.0063,
  un-flagged accuracy 99.0%, flag rate 1.9%) are therefore optimistic, and only the test
  figures are reported as results. Test bears this out: un-flagged accuracy is 98.65%,
  below the 99% the threshold was set to reach on validation.
- **Why accepted:** There is no third labelled split, and carving one out of train would
  have changed the pre-registered split (ADR-064). ADR-066 stated this consequence before
  calibration ran.
- **Recorded in:** ADR-066; `evals/results/sentiment/2026-10-01_bert_v1/calibration.json`,
  `bert_v1.test.metrics.json`.

### L-32 — The review flag catches about a third of BERT's errors (2026-10-01)
- **What:** On test, 16 of 1,128 comments (1.4%) fall below τ = 0.841 and are flagged.
  They hold 8 of BERT's 23 errors (35%); the other 15 errors are predicted with
  calibrated confidence of at least 0.841 and pass un-flagged. By subset: sarcastic 2 of 7
  errors flagged, implicit 3 of 9, mixed 2 of 4. Temperature scaling barely moved the
  probabilities (T = 1.032), so the model's confident errors stay confident.
- **Why accepted:** ADR-066's rule was fixed in advance and is not re-tuned on test. The
  finding is for the QA design (ADR-055): a flag means "look at this", but no flag does
  not mean "correct", so QA should not treat un-flagged sentiment results as verified.
- **Recorded in:** ADR-066; `evals/results/sentiment/2026-10-01_bert_v1/bert_v1.test.metrics.json`.

### L-33 — Answers above the on-demand cap are partial and leave out the oldest comments (2026-10-01)
- **What:** When a range holds more than 250 comments without a stored prediction,
  `mcp_feedback` scores the 250 newest and answers over the scored subset, with
  `complete: false` (ADR-067). A partial answer leaves out the oldest comments in range, so
  a monthly or quarterly trend can lack its earliest buckets, or show them thinly, and
  compare the latest period against an incomplete baseline. Observed: before the
  backfill, 2025 Q4 answered over 300 of 736 comments (at the time, cap 300 and
  oldest-first).
- **Why accepted:** Scoring on arrival plus the backfill keeps stored coverage complete
  in normal operation, so a partial answer means un-backfilled data. The agent must state
  the coverage (4b), and QA can check `n_scored` against `n_comments`.
- **Recorded in:** ADR-067; `evals/results/sentiment/2026-10-01_mcp_feedback_live/`.

### L-34 — Stored predictions belong to one model version; a new model needs a fresh backfill (2026-10-01)
- **What:** Predictions are keyed on the SHA-256 of the artifact manifest. A new model, or
  a new T or τ for the same model, is a new version with no stored predictions; until a
  backfill runs, every answer is scored on demand and is partial above the cap. The
  backfill took 856.6 s for 6,996 comments on 1 CPU. Rows of old versions stay in the table
  (`app_sentiment` can't delete), so it grows with every version.
- **Why accepted:** Versioned rows keep each answer traceable to the model that produced it
  and make a rollback a configuration change. Pruning old versions is the generator role's
  or an operator's job, not the server's.
- **Recorded in:** ADR-067; `evals/results/sentiment/2026-10-01_mcp_feedback_live/``reproducibility_and_totals.json`.

### L-35 — The real container is slower than the latency proxy, and a cold first request exceeds the warm budget (2026-10-01)
- **What:** In the real `mcp_feedback` image at 1 CPU / 2 GiB, warm inference on 300 real
  comments ran at 8.46/s at batch 16 and 9.42/s at batch 8 (slowest 9.28/s), against the
  proxy's 10.74/s at batch 16 (L-28). The texts match the proxy's in length and padding, so
  they don't explain it; the proxy ran a separate image on a Docker VM since rebuilt, and the
  cause isn't isolated. The cap was set from the slowest real repeat: 250 at batch 8
  (26.9 s). The first scoring pass after a start is about twice as slow (68.8 s for 300
  comments), so the first on-demand request after a cold start exceeds the 30 s warm budget;
  the 120 s ceiling (ADR-034) still holds for one pass.
- **Why accepted:** With predictions stored, on-demand scoring is the exception, not the
  normal path. A warm-up pass at start-up would fix the cold penalty, but it adds start-up
  time against the 20 s cold-start budget (L-36). It is left as a decision for the deploy.
- **Recorded in:** ADR-065, ADR-067; `evals/results/sentiment/2026-10-01_mcp_feedback_live/``throughput.json`.

### L-36 — Cold start is dominated by hashing the weights, and once exceeded the 20 s budget (2026-10-01)
- **What:** Start-up verifies every artifact file's SHA-256 before the server listens
  (ADR-066). Through the Windows bind mount, the 438 MB weights took the container to ready
  in 14.9 s, and in 29.4 s on the first start after a Windows restart (cold file cache),
  over ADR-065's 20 s cold-start budget. The model itself loads later, on first need
  (about 1.2 s).
- **Why accepted:** This is a local bind-mount measurement. On Cloud Run the artifact is
  baked into the image (ADR-062), so neither the bind mount nor the host's file cache
  applies; the budget is checked there. Skipping the hash check to start faster would give
  up the integrity guarantee.
- **Recorded in:** ADR-065, ADR-066, ADR-067; `evals/results/sentiment/2026-10-01_mcp_feedback_live/``live.json`.

### L-37 — Stored confidence is rounded, so the flag rule holds to a tolerance (2026-10-01)
- **What:** `confidence` is stored as NUMERIC(5,4), and `flagged` is decided on the
  unrounded probability. A comment within 0.00005 of τ can therefore show a stored
  confidence on the other side of τ from its flag. Observed against 3b's 6-decimal
  predictions: largest difference 0.00005, with flags matching on 1,128 of 1,128 test
  comments.
- **Why accepted:** Four places is ample for reporting, and the flag carries the decision.
  QA checks `flagged = confidence < τ` with a 0.00005 tolerance (data dictionary §8).
- **Recorded in:** ADR-066, ADR-067; `evals/results/sentiment/2026-10-01_mcp_feedback_live/``reproducibility_and_totals.json`.

### L-38 — "In August" parses as the current partial month, against the prompt's own rule (2026-10-01)
- **What:** Both parse prompts (`agent_reporting` `parse_v2`, `agent_sentiment` `parse_v1`)
  say a named month without a year is the most recent such month that *ends* on or before
  the as-of date. With the as-of date 2026-08-30, "in August" should therefore be August
  2025. In all three runs Flash-Lite returned 2026-08-01 to 2026-08-30, the current partial
  month (parse set item p14). The label was kept. On the merits, the model's reading is
  probably what a user means, so the rule is the likelier fault, not the model.
- **Why accepted:** One item of 14, consistent across runs, and the answer states its
  range, so the reader sees which August was used. Changing the rule is a prompt revision
  for both agents and a decision for the owner; no revision was made in 4b.
- **Recorded in:** ADR-050, ADR-068; `evals/results/sentiment_agent/2026-10-01/``parse_parse_v1_k3.json`.

### L-39 — The sentiment parse set is small and shares an author with the prompt (2026-10-01)
- **What:** parse_v1 has 14 questions, written by the same author as `parse_v1.md`, just
  after the prompt. 13/14 shows the prompt does what its author intended on phrasings its
  author chose; it is not a blind measure of real users' phrasing. No revision was made,
  so the set is still unused for tuning.
- **Why accepted:** It is a parse check, not the Sprint 5 evaluation. Held-out phrasings
  belong in the Sprint 5 golden set, written separately.
- **Recorded in:** ADR-068; `evals/sentiment_parse/`.

### L-40 — Fold A has one seasonal cycle of history and is reported only (2026-10-02)
- **What:** Fold A tests 2024-09-02 to 2025-03-02 on the 52 weeks before it: one year, so
  trend and season are barely separable. Its errors are reported but never gate a release
  (ADR-069). v2, fold A, total MAPE 9.9% against naive 11.8%; the planted regional drop
  (2025-02-17 to 03-02) falls in its test window.
- **Why accepted:** The deployed model trains on three years; gating on fold A would judge a
  condition the deployed model never faces.
- **Recorded in:** ADR-069; `evals/results/forecast/2026-10-02_folds/`, `2026-10-02_folds_v2/`, `2026-10-02_holdout/`.

### L-41 — Pre-registered result: `volume_v1` failed ADR-069's gate on the total (2026-10-02)
- **What:** On fold B, the total failed ADR-069's per-band rule in band 1-4 (model 11.9%
  against seasonal naive 4.3% MAPE) and band 14-26 (11.9% against 10.9%); it passed 5-13
  (5.5% against 12.9%). Over the full 26 weeks the model was better (9.7% against 10.6%).
  Every service-type slice failed at least one band too. The 14-26 loss is mostly one week:
  Christmas 2025 (actual 88, v1 134, naive 87). The 1-4 band holds 4 weeks.
- **Why accepted:** It is the pre-registered result and stays on the record; `gate_v1`
  reproduces it exactly from the committed fold results.
- **Recorded in:** ADR-069, ADR-070; `evals/results/forecast/2026-10-02_folds/gate.json`.

### L-42 — The gate correction and `volume_v2` were decided after the fold results (2026-10-02)
- **What:** ADR-070's corrected gate (26-week eligibility against seasonal naive, then a 20%
  ceiling per band) and `volume_v2` were decided after the ADR-069 fold results were seen and
  before any holdout result existed. `volume_v1`'s total passes the corrected gate as well
  (26-week MAPE 9.7% against 10.6%; bands 11.9%, 5.5%, 11.9%, all under 20%), so the
  correction, not v2, is what changed the total's verdict.
- **Why accepted:** Disclosed rather than hidden. The flaw it corrects (a model-against-
  baseline comparison on 4 weeks) does not depend on the direction of the result, and the
  holdout was scored once each for v1, v2 and seasonal naive, after both decisions.
- **Recorded in:** ADR-070; `evals/results/forecast/2026-10-02_folds_v2/gates.json`.

### L-43 — The year-end fix is untested blindly, and its fold evidence is mixed (2026-10-02)
- **What:** The headline holdout (March to August) contains no December, so the year-end
  indicator is supported only by fold results already seen. On fold B it cut the Christmas
  2025 overprediction (134 to 120 against an actual 88) but worsened New Year week (130 to
  117 against 132): one indicator covers two weeks of unequal depth. Its fold B coefficient
  on the total is -0.118, 95% CI [-0.251, 0.015], which includes zero; on all 156 weeks it
  is -0.153 [-0.259, -0.046].
- **Why accepted:** ADR-070 fixed the indicator before the holdout, and the calendar
  definition uses no generator knowledge. A two-week split, or a test on December data, is a
  new version and a new ADR.
- **Recorded in:** ADR-070; `evals/results/forecast/2026-10-02_folds/`, `2026-10-02_folds_v2/`, `2026-10-02_holdout/`.

### L-44 — Slice-bands that fail the corrected gate are not served (2026-10-02)
- **What:** Under ADR-070 on fold B, `volume_v2`: total passes all bands. Inspection is
  ineligible (26-week MAPE 24.4% against naive 23.8%), so none of its bands is served.
  Failing bands of eligible slices: install 1-4 (26.0%); maintenance 1-4 (27.4%), 5-13
  (22.9%) and 14-26 (22.7%); repair 14-26 (20.5%); upgrade 1-4 (70.2%). Served: total
  1-4, 5-13, 14-26; install 5-13 and 14-26; repair 1-4 and 5-13; upgrade 5-13 and 14-26.
  v2 fails maintenance 5-13, which v1 passed under the corrected gate (v1 15.5%).
- **Why accepted:** Service-type slices are small and noisy; serving them anyway would
  claim accuracy the folds don't support. QA refuses the failing slice-bands (ADR-055).
- **Recorded in:** ADR-070; `ml/forecast/artifacts/volume_v2.manifest.json`.

### L-45 — Interval coverage runs below nominal on several slices (2026-10-02)
- **What:** 80% intervals covered 58% to 88% of fold B weeks across slices (total 81%), and
  65% to 88% of holdout weeks (total 85%); 95% intervals covered 88% to 100% on fold B.
  The intervals assume log-normal errors with a constant robust scale, which noisy service-
  type series and level shifts violate.
- **Why accepted:** Coverage is reported, not gated (ADR-069). Answers should present the
  range as approximate for service-type slices.
- **Recorded in:** ADR-069; `evals/results/forecast/2026-10-02_folds/`, `2026-10-02_folds_v2/`, `2026-10-02_holdout/`.

### L-46 — Four slice-bands passed fold B and missed the 20% bar on the holdout (2026-10-02)
- **What:** Under ADR-070's gate these passed fold B, then exceeded 20% MAPE on the blind
  holdout with `volume_v2`: install 14–26 weeks (fold B 18.5%, holdout 29.4%), upgrade 5–13
  (17.3%, 26.9%), upgrade 14–26 (14.6%, 21.2%) and repair 1–4 (7.7%, 27.9%). ADR-071 removes
  them from service; L-44's "Served" list is narrowed accordingly.
- **Why accepted:** The rule only tightens what is served, and no evaluation figure changes.
  It was decided after the holdout, so it is disclosed as such (ADR-071).
- **Recorded in:** ADR-071; `ml/forecast/artifacts/volume_v2.manifest.json` (`serving`).

### L-47 — Weekly service-type forecasts are mostly not served at these volumes (2026-10-02)
- **What:** With about 15–45 requests a week per service type, weekly errors are large and
  unstable between windows. Under ADR-071 only install and repair at 5–13 weeks are served;
  the other 13 service-type slice-bands are refused with their error shown. The total is
  served at every band.
- **Why accepted:** Serving them would claim accuracy the data doesn't support. Monthly
  service-type forecasts, which would reduce the noise, are future work and need their own
  ADR.
- **Recorded in:** ADR-071.

### L-48 — The forecast parse set is small and shares an author with the prompt (2026-10-02)
- **What:** parse_v1 has 14 questions, written by the same author as `parse_v1.md`. 14/14
  in every run shows the prompt follows its own period rules on phrasings its author chose;
  it is not a blind measure of real users' phrasing. "Next year" (calendar 2027) and "the
  next year" (the coming 12 months) parse differently by rule, a distinction users may not
  draw.
- **Why accepted:** It is a parse check, as L-39 is for sentiment. Held-out phrasings belong
  in the Sprint 5 golden set; every answer states the weeks it covers, so a misread period
  is visible.
- **Recorded in:** ADR-072; `evals/forecast_parse/`, `evals/results/forecast_agent/2026-10-02/`.

### L-49 — A forecast question with no period gets next month, a default ADR-072 doesn't set (2026-10-02)
- **What:** When the question names neither a horizon nor a period, code applies next month
  (September 2026) and the answer says so. ADR-072 fixes the period rules but not this
  default; it mirrors ADR-050's previous-month default for reporting.
- **Why accepted:** It keeps the model from inventing a range, and the answer states the
  assumption. A different default is a one-line change and an ADR.
- **Recorded in:** ADR-072; `services/agent_forecast/src/agent_forecast/parsing.py`.

### L-50 — A month's forecast is a set of Monday-start weeks, not calendar days (2026-10-02)
- **What:** A period maps to the weeks whose Monday falls inside it (ADR-072), so "December"
  covers 2026-12-07 to 2027-01-03, and "next month" (September) starts 2026-09-07 because
  2026-08-31 is a Monday in August. A period total therefore counts whole weeks, which can
  include days of the next month and leave out the first days of the named one.
- **Why accepted:** The model forecasts weeks; splitting weeks by day would invent a daily
  profile it doesn't have. Every answer states the exact weeks covered.
- **Recorded in:** ADR-072; `evals/results/forecast_agent/2026-10-02/``e2e.json`.

### L-06 update — resolved by ADR-073 (2026-10-02)
- **What:** Incident counts now break down by account, region, service type, technician
  (attributed, with an "unattributed" group), incident type and severity; repeat-visit
  drivers are a tool (`get_repeat_visit_drivers`); one technician can be asked about by
  name (`find_technician` plus a `technician_id` filter on every reporting tool). L-06
  itself is unchanged; this entry records its resolution.
- **Still open from L-06:** technician home region isn't a breakdown.
- **Recorded in:** ADR-073; `docs/sprint-log.md` (Sprint 3).

### L-51 — parse_v3 lost every date to a key-order clash, caught by the parse eval (2026-10-02)
- **What:** Gemini's structured output writes keys in the response schema's property
  order. ADR-073's first build added `technician_name` after `end` in `ReportingRequest`,
  while parse_v3's JSON template puts it third. The model wrote it third and could not go
  back to the optional dates, so every dated question parsed with no range and would have
  been answered for the default month, with the answer saying so. The first k=3 run scored
  0, 1 and 0 of 16 (dates 1/16, the one undated item); 48 calls were spent and the results
  file was lost to a console-encoding crash in the runner. A two-item diagnostic showed the
  raw output omitting `start` and `end`; the same prompt with the schema reordered parsed
  both exactly. The field moved after `group_by`; prompt and labels unchanged; rerun 15/16
  x3.
- **Why accepted:** It is fixed, and a unit test now holds the prompt template's key order
  to the schema's. The coupling itself remains: any future field added out of template
  order would fail the same way. The test covers the reporting agent; the sentiment and
  forecast templates were checked by hand on 2026-10-02 and match their schemas, with no
  test.
- **Recorded in:** commit 77d2cee; `evals/results/reporting_agent/2026-10-02/`.

### L-52 — The repeat-driver significance rule still flags noise about 1 time in 20 (2026-10-02)
- **What:** Bonferroni holds the chance of any false standout at about 5% per question, not
  zero. For 2026 Q2 by service type, `repair` stands out (14 of 572 jobs repeated against 8
  of 1,104, adjusted p 0.027), though the generator draws priority and incidents
  independently of service type, so the difference is chance. Over the full window, no
  service type, region, account or technician stands out. Across many questions and
  ranges, standouts will appear at about that rate.
- **Why accepted:** The rule is ADR-073's and stays; it removes most noise and states its
  test. The answer says "beyond what chance explains", which overstates a 5% rule
  slightly; QA (Sprint 4) recomputes the p-values but can't tell a true driver from a
  chance one either.
- **Recorded in:** ADR-073; observed 2026-10-02 as `app_reporting`.

### L-53 — The reporting parse set is small; r17 parses stably wrong on two fields (2026-10-02)
- **What:** parse_v3 is 16 questions written by the prompt's author, as for L-48. r17 ("Is
  Sarah's average resolution time improving over the last two weeks?") misses in all three
  runs the same way: no `technician_name` (the model drops the name when the metric is
  unsupported) and a start of 2026-08-16, 15 days, against the label's 14 (2026-08-17).
  "The past 30 days" (c03) was read correctly.
- **Why accepted:** r17's metric is unsupported, so the agent declines it before using the
  name or the range; the answer is unaffected. The off-by-one would matter for a supported
  metric asked over "the last N weeks"; the golden set (5c-2) should include one.
- **Recorded in:** `evals/reporting_parse/`; `evals/results/reporting_agent/2026-10-02/`.

### L-54 — The fixed association caveat can contradict a short range's figures (2026-10-02)
- **What:** ADR-073 has every `by=incident_type` answer end with "Jobs with several
  incidents are more likely to need a repeat visit; this shows association, not cause."
  End to end for "this quarter" (2026-07-01 to 2026-08-30), jobs with any other incident
  repeated at 1.12% (1 of 89) and jobs with none at 1.21% (10 of 827), so the sentence
  states the opposite of the figures printed just before it. Over the full window it holds
  (4.24% against 1.81%).
- **Why accepted:** Not accepted yet; raised for a decision. The sentence is ADR-073's
  wording, and changing it changes an accepted ADR. A likely fix: state the association
  only when the any-other rate is above the none rate, and otherwise say the two don't
  differ in this range.
- **Recorded in:** `evals/results/reporting_agent/2026-10-02/e2e.json`.
