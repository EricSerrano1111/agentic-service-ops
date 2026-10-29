# Evaluation Report — Agentic Service Operations Intelligence Platform

*2026-10-18 (B-E1; owner-decided 2026-10-18; assistant-drafted.)* **This report is now a skeleton.** Each section below says what goes in it and lists the figures it will cite, each copied from its dated source file with the path. Prose is written in the buffer, with the draft by 11-08 and the final by 12-01 (ADR-113). No figure here is typed from memory or taken from another summary; where a summary and its source file disagree, both are given under "Conflicts" and the skeleton does not choose between them. The Limitations log below is untouched.
*Updated 2026-10-14.*

**Dates in this skeleton** are the dates in the source files' folder names and headings, not file timestamps. "Sprint 5 system" means the frozen system of ADR-103; "current build" means the commit `9ab7c77`.

## 1. Summary

**What goes here:** the report's summary, written last.
**Figures to cite:** none yet.
**Status:** skeleton (left empty on purpose).

## 2. The system evaluated

**What goes here:** the frozen Sprint 5 system, the current build, what changed between them and the proof that no answer changed, and the paid key.

**Figures to cite:**
- Frozen system: images tagged `9607fa722c4d1b2dc12478dbe4bb42f6c8d95bfb`; "tree equals `eval-freeze-s5`"; mode `LLM_MODE=paid` on the five model-calling services (ADR-104); default router `route_v3`; interpretation check advisory with `qa_interp_v2`; revisions `ops-forecast-00002-m79`, `ops-gateway-00001-8st`, `ops-orchestrator-00006-bvj`, `ops-qa-00003-hwq`, `ops-reporting-00006-md5`, `ops-sentiment-00002-cxz`, identical at the start and end of the run. Source: `evals/results/sprint5_x.md`, "System under test".
- Freeze record: `evals/freeze_s5.json` (ADR-103): `default_router` `route_v3`; `shipped_interpretation_prompt` `qa_interp_v2`; parse prompts in service `reporting` `parse_v4`, `sentiment` `parse_v1`, `forecast` `parse_v1`; models for orchestrator, specialist and QA all `gemini-3.5-flash-lite` at thinking level minimal; flags `QA_INTERP_MODE` `advisory`, `QA_FORECAST_RECOMPUTE` `on`, `MCP_FEEDBACK_SCORING_deploy` `stored_only`; `as_of_date` `2026-08-30`.
- Tree check run for this skeleton (`git rev-parse <ref>^{tree}`, 2026-10-18): `eval-freeze-s5` and `9607fa722c4d1b2dc12478dbe4bb42f6c8d95bfb` both give tree `117198ea86fca83118d9e1cd22ac43601708f458`; `9ab7c77` gives `a399ae2e69837bfce44e4099dd394cd81ae7de27`. `git diff --name-only eval-freeze-s5 9ab7c77 | grep '/prompts/'` printed nothing (no prompt file differs between the freeze and the current build). `eval-freeze-s5` is a lightweight tag at commit `133b6fd`; the images were built from `9607fa72`, whose tree is the same.
- Current build: build `0dc5aae1-2a6c-498e-bbca-f709c2c91149` from `9ab7c775964bd0aae491ca72082e95229c994129`, six revisions serving at 100% (`docs/sprint-log.md`, "Z2b status, 2026-10-14"); "Deployed system: build `0dc5aae1`, commit `9ab7c77`, unchanged at open and close" (`evals/results/session1/2026-10-15/summary.md`); nine images at tag `9ab7c775964bd0aae491ca72082e95229c994129`, digests equal to the serving revisions' (9 of 9) (`evals/results/ts14d/2026-10-18/summary.md`).
- What changed between them (`docs/sprint-log.md` lines 1175 to 1184): "Each is one of the changes ADR-103 allows after the freeze (logging, the trace ID, deploy config and tooling); none changes an answer, a route, a parse, a QA verdict or §6's answer wording, and no prompt file changed." Items: the trace ID end to end (ADR-108); the L-60 redaction (ADR-108); the YAML sync to paid mode for the five model-calling containers; the hourly cap of 30 (ADR-107) and daily cap 50; logging of each failed model-call attempt; the public `GET /health`; `plan_full.py` and `verify.py` tooling. Also the Next.js bump to 16.4.1 (`docs/sprint-log.md` line 1197).
- Proof of no answer change (`docs/sprint-log.md` line 1189, local stack, paid mode, 2026-10-14): 12 requests (3 before, 9 after), $0.0042 on the 9 after-run calls; Q1 "What was SLA compliance in the Northeast last month?" main against `fix/z2-post-freeze`: route `reporting`, `prompt_version` `route_v3`, outcome `answered`, `qa_status` `verified`, figures (141 of 160, rate 0.8813) and answer text identical. **Limit, copied:** "*Q2, sentiment trend by month, after only:*", "*Q3, weekly volume for the next 8 weeks, after only:*", and "*Not covered live:* sentiment and forecast before/after (the cap)." Only Q1 was compared before and after. **Conflict recorded there:** "the prompt asks for the three questions before and after (18 calls) under a 12-request cap, so the before run asked only question 1 (3 calls) and the after run asked all three (9 calls); the cap was kept."
- The paid key: ADR-104 (`docs/decisions-log.md`, "Deployed model calls use the paid key for the evaluation and grading window"); `evals/results/sprint5_x.md`: "`LLM_MODE=paid` on the five model-calling services (ADR-104)".

**Conflicts:**
- **Resolved.** `evals/freeze_s5.json` records `llm_mode_in_services` `free`; `evals/results/sprint5_x.md` records `LLM_MODE=paid` on the five model-calling services. The dated note under ADR-103 (`docs/decisions-log.md` line 3460, 2026-10-14) says: "For deployed serving that is superseded by ADR-104". Both paths kept. Owner ruling 2026-10-18.

**Status:** skeleton.

## 3. Methods

**How the sets were built.** The golden set (`golden_v2`) has 36 items: 10 owner-written and 26 drafted. Its expected answers come from oracles that share no code with the system, except the forecast's, which use the server's own prediction code (ADR-074, L-55). The other sets were generated, not owner-written: `gemini-3.8-flash` wrote `routing_heldout_v1`, `fr03_fresh_v2`, `interp_fresh_v1` and `parse_filters_v1` from a brief that the assistant that built the system wrote and the owner reviewed (ADR-094). No item was edited after generation. The owner skimmed every ambiguous-labelled item and could drop an item but not fix one. Five of 31 skimmed rows were dropped on persona grounds, which weights the sets toward broad leadership questions, and generator and system are both Gemini (L-86). The disclosure for every figure from these sets: "In a real deployment, evaluation sets would come from real user questions and subject-matter experts. Here they were generated by an independent model under a written brief; the owner reviewed the brief and spot-checked the ambiguous labels." Spent for blind use: `routing_heldout_v1` and `golden_v2` (run 2026-10-13), and `fr03_fresh_v2`, which judged `route_v6` (ADR-101) and then, with `routing_heldout_v1`, chose a thinking level (ADR-114). The interpretation pairs were used in the Prompt W gates. `parse_filters_v1` and the reserve were not touched in the 2026-10-13 run.

**How scoring worked.** Routing evaluations run three times (k=3, ADR-054), because one run cannot separate a change from run-to-run variance (L-17). Each reports the per-run score, the range and every item whose route changed between runs (flipping items). The golden run was a single pass (L-103). Rules were committed before the runs they judge: the interpretation gate on 2026-10-09 at 09:29:14 CDT (`6c79e50`, ADR-089); the Sprint 5 gates on 2026-10-12 at 16:24:33 CDT, with the first Part C call at 16:34 CDT; the golden scoring method on 2026-10-13 at 12:34:49 CDT (`05a1708`), before the first golden call. The golden headline is mechanical: an item passes only if its outcome, route and figures each pass against the oracle. The owner judges `must` and `must_not` in a second column, and the assistant's own reading of them is kept apart as opinion, not score. Rules changed after results are named in §6.

**The QA fault harness.** QA is tested by changing correct answers in known ways and checking that QA fails them, with unmodified answers as controls. The catalogue, case generator, seed (20261010), mutation code and report format were committed together at `b5ad1f4` (2026-10-10 12:32:45 CDT), before any QA verdict existed (ADR-091). A miss is a finding and is not tuned away: a fix goes in a separate change that reruns the same catalogue and seed and is reported as a further measurement. The harness replaces QA's interpretation check with a client that always answers `faithful`, and the assistant that built QA drafted most faults (L-85). Counts are in §4.3.

**The offline component protocols.** For sentiment (ADR-064 to ADR-066), near-duplicates were grouped before a fixed split, whose hash was committed before any training code. Settings were chosen on validation only, and each model was scored on test once, in an append-only ledger. BERT counts as better than the TF-IDF baseline only if the paired bootstrap interval excludes zero or McNemar's p is below 0.05, and every subset is reported. For forecasting (ADR-069 to ADR-071), fold A is reported, fold B sets the release gate, and the holdout is scored once, after the folds. ADR-070 corrected the gate after the fold results and ADR-071 set the serving rule after the holdout; both are disclosed (§4.4, §6).

**Ledgers and caps.** The paid runs each kept a ledger with a request cap and a spend cap. Prompt W (the gates): 561 requests and $3.00 (`evals/results/sprint5_w_ledger.json`). Prompt X (held-out routing and golden): 186 requests, $1.50 and 1,000 model calls (`evals/results/sprint5_x_ledger.json`). Owner session 1: 75 requests and $0.25. The third FR-03 attempt: 1,550 requests and $2.50 (`evals/fr03_v3/ledger.jsonl`). The Prompt W and FR-03 harnesses refused a call that would cross a cap. Per-process caps are a backstop (L-88, L-93). Costs are list-price estimates (L-71) and model calls are bounded, not counted (L-94). Earlier live runs were bounded by a stated call budget, for example 5 of 10 calls in the ADR-091 loop demonstration. What each run used is in §4.7 and §6.

*Sources:* `docs/decisions-log.md` (ADR-054, ADR-064 to ADR-066, ADR-069 to ADR-071, ADR-074, ADR-089, ADR-091, ADR-094, ADR-101, ADR-114), `evals/sprint5_gates.md`, `evals/results/sprint5_x.md`, `evals/results/sprint5_x/golden_scoring.md`, `evals/results/sprint5_x_ledger.json`, `evals/results/session1/2026-10-15/ledger.json`, `evals/fr03_v3/ledger.jsonl`.

**Status:** draft 2026-10-28.

## 4. Results

Subsections 4.1, 4.2, 4.6 and 4.7 are for the frozen Sprint 5 system (§2). Subsections 4.3 to 4.5 are offline evaluations of the QA, forecast and sentiment components, run between 2026-10-01 and 2026-10-12, not against the deployed frozen system. All data are synthetic (L-102). The evaluation sets were generated by a model, not written by the owner, except 10 of the 36 golden items (§3, L-86). Three terms recur. A "k=3" result is three full runs of the same set, reported as a range. A held-out set is one that no prompt or model was written or tuned on. Pre-registered means the rule and its thresholds were committed before the run they judge.

### 4.1 Routing (held-out)

The router scored 38 of 50 held-out questions in each of three runs (range 38 to 38, no item changed between runs). The router is `route_v3`, frozen under ADR-103. The wrong answers fall into two classes: ambiguous questions that were not flagged (21 item-runs) and out-of-scope questions accepted by a specialist (15 item-runs). Nothing else was wrong in 150 item-runs: no wrong-area routes, false ambiguous flags, in-scope declines, errors or timeouts.

`route_v3` has no `ambiguous` route, so the 7 ambiguous items are scored wrong by construction (FR-03, L-58). Without them the score is 38 of 43 in each run, a diagnostic beside the headline 38 of 50. By category (item-runs, items times 3), every clear, filtered, technician, unsupported-in-area, multi-domain and underspecified category was fully correct (15/15 for each clear type, 6/6, 6/6, 6/6, 18/18, 18/18). Near miss scored 9/15, out of scope 6/15 and ambiguous 0/21.

All 15 out-of-scope misses were declined by the specialist with no figure shown, so the route label was wrong and the outcome was not (L-96). Two of the five items are future-tense questions on an out-of-scope subject (NM-14, NM-20) and went to forecast; the owner's 2026-10-11 clarification says these are `out_of_scope`. AMB-16, AMB-23 and AMB-25 were answered with figures in every run despite being ambiguous.

The result does not show how the router does on real users' questions. The set was written by a model of the same family as the system, and the owner made 3 drops at the skim of this set, replaced from reserve items of the same category (sprint log, 2026-10-11). Drops on persona grounds skew the generated sets toward broad leadership questions (L-86). Ambiguity labels are owner judgement (L-57). The set was run on 2026-10-13 and is spent for blind use. The later `route_v6` router is reported in §6.

*Sources:* `evals/results/routing_heldout_v1/2026-10-13/score.json`, `evals/results/sprint5_failure_analysis.md`, `evals/sprint5_gates.md`, `docs/sprint-log.md`.

**Status:** draft 2026-10-23.

### 4.2 Golden

The golden set scored 29 of 36 by its mechanical rules and 31 of 36 by the owner's judgement. The scores agree on 32 items. They differ on G08, G21 and G28 (mechanical fail, owner pass) and on G27 (mechanical pass, owner fail).

The expected answers were computed independently of the system (ADR-074) and the scoring method was fixed before the first call. The set was run once, not three times (L-103). The 10 owner-written items scored 6 of 10 mechanically and 7 of 10 by the owner; the 26 drafted items scored 23 and 24 of 26. The gap is four items and carries no significance claim (L-54). Three of the four stretch items (G02, G04, G10) passed.

| ID | Mechanical failure | Owner |
|---|---|---|
| G03 | "district" read as an unsupported breakdown; the item expects regions (L-95) | N |
| G05 | "storm last weekend" dropped, range assumed; stretch item (L-56) | N |
| G07 | 8 weeks returned, 26 expected; "end of next year" read as calendar 2027 (L-95) | N |
| G08 | future-tense out-of-scope question routed to forecast, which declined (L-96) | Y |
| G21 | p-value 0.3349 against 0.334895628510519; every other figure matches (L-95) | Y |
| G28 | outcome `answered` with no weeks; the item accepts `not_available` (L-95) | Y |
| G35 | ambiguous question routed to reporting (FR-03, L-58) | N |

G21 and G28 point at scoring or item issues, not answer defects. On G27 the owner noted that the request "goes below available data range", which reads as a doubt about the item's premise. On G10 the assistant's reading found a `must_not` breach (the answer never says its figures are for all installs, not fiber) and the owner marked Y; that reading is kept apart from the owner's marks.

The result does not show how the system does on questions other people would write: the owner-written items are the only owner-phrased evidence (L-86), and 36 items is a small set. The forecast expectations come from the same prediction code the server runs (L-55). The set is spent for blind use.

*Sources:* `evals/results/golden_v2/2026-10-13/score.json`, `evals/results/sprint5_x/golden_owner_review.csv`, `evals/results/sprint5_failure_analysis.md`, `evals/results/sprint5_x/golden_assistant_reading.md`.

*Notes on sources:* G21 would score 30 of 36 if compared at display precision. That is a correction made after seeing the results and is not the pre-registered score (L-95).

**Status:** draft 2026-10-23.

### 4.3 QA fault catch rate

The QA agent caught 219 of 223 injected-fault cases in measurement 1 (98.2%, 95% Wilson interval 95.5 to 99.3%) and all 223 in measurement 2 (100.0%, 98.3 to 100.0%). **Both are upper bounds.** The faults were drafted by the assistant that built QA's checks, so they are the faults its author thought of, not an estimate for faults nobody thought of (L-85).

Fault injection means changing a correct answer in a known way (a count off by 1, a group dropped) and checking that QA fails it. The Wilson interval is a 95% range for a proportion that stays sensible near 100%. The catalogue of 34 faults (223 cases, beside 62 unmodified controls) was frozen at commit `b5ad1f4` before the first QA verdict.

- **Measurement 1:** reporting 104/104, sentiment 76/76, forecast 39/43. All four misses were one fault (F08, a text figure changed by 1): QA's text check treats a figure's floor, ceiling and rounding as the same number and compares sets of numbers (L-82). One of 62 controls raised a false alarm (`reporting:f09`, L-81). The owner's faults 4a and 4b (a small sample ranked or left unmarked, 1 case each) passed in measurement 1 (L-84).
- **Measurement 2:** the same catalogue after fixes designed from measurement 1's misses. 223/223 and no false alarms. This is the weaker evidence: it shows the fixes work on the cases they were written for.
- **Measurement 3:** the same catalogue with QA's forecast recompute enabled (ADR-095), a check on one fix and not a third catch rate. The owner's fault 2 (holiday-week forecasts flattened, intervals and totals consistent) was caught 0 of 6 in measurements 1 and 2 (L-83) and 6 of 6 in measurement 3. On clean forecasts the recompute found 0 mismatches in 171 forecasts and 2,320 numbers. It leaves the 95% interval ends and a total interval unchecked (L-87).

A consistent misparse, where the figures are correct for the wrong request, passed every time: 0 of 30 reporting, 0 of 19 forecast and 0 of 22 sentiment cases, and 0 of 10 for the owner's trailing-quarter case. The interpretation check that would catch these is advisory because it failed its gates (§6, L-74; on the 42 pairs used in development `qa_interp_v2` falsely rejected 7 and `qa_interp_v3` 3, not held out), and the harness uses a fake interpretation client that always answers `faithful`, so these zeros measure the figure checks alone. The rating-contradiction check is optimistic because star ratings share the label's latent sentiment in this data (L-24).

*Sources:* `evals/results/qa_faults/2026-10-10/report.md`, `evals/results/qa_faults/2026-10-10/README.md`, `evals/results/qa_faults/2026-10-10-m2/report.md`, `evals/results/qa_faults/2026-10-11-m3/report.md`, `evals/results/qa_faults/2026-10-11-m3/README.md`, `evals/results/qa_forecast_recompute/2026-10-12/clean_check.json`.

*Notes on sources:* L-85 and the measurement 1 README say 47 assistant-drafted faults; the reports score 34 (223 cases) because rating contradictions and consistent misparses have their own sections. The README's "Misparse (M*, O5), 0 of 71" is loose wording: 71 is the M* count and O5 (0 of 10) is reported apart.

**Status:** draft 2026-10-23.

### 4.4 Forecast

On the 26-week headline holdout, the production model `volume_v2` scored 8.81% MAPE on total weekly request volume against 14.80% for seasonal naive. MAPE is mean absolute percentage error. Seasonal naive predicts each week as the same week 52 weeks earlier, and is the baseline to beat: the pre-registered rule for "beats the baseline" is a lower holdout MAPE than seasonal naive on the total (ADR-069), which 8.81 against 14.80 meets. The model also beat it on the total in both folds. A fold is a backtest: fit on the weeks before an origin, score the next 26. Fold A had one year of history and is reported only; fold B had two and set the release gate; the holdout was scored once.

| Slice | Fold A model / naive MAPE % | Fold B model / naive MAPE % | Holdout model / naive MAPE % |
|---|---|---|---|
| total | 9.91 / 11.80 | 9.46 / 10.61 | 8.81 / 14.80 |
| inspection | 20.36 / 31.38 | 24.40 / 23.76 | 27.82 / 43.14 |
| install | 26.47 / 25.01 | 19.48 / 25.62 | 26.40 / 30.51 |
| maintenance | 24.28 / 23.76 | 23.50 / 24.79 | 14.27 / 20.20 |
| repair | 17.92 / 17.35 | 15.20 / 18.66 | 13.37 / 16.17 |
| upgrade | 35.25 / 29.88 | 24.11 / 35.59 | 27.10 / 32.24 |

The model is below naive on every holdout slice, but not on every fold slice: it is above naive on four of six slices in fold A (install, maintenance, repair, upgrade) and on one in fold B (inspection).

**Release gate.** The pre-registered gate (ADR-069) passed a slice and horizon band if, on fold B, its MAPE was at most 30% and no higher than naive's. `volume_v1` failed it on the total in band 1 to 4 (11.9% against 4.3%) and band 14 to 26 (11.9% against 10.9%), on a 4-week comparison that cannot separate two forecasters at about 10% weekly noise (L-41). ADR-070 changed the gate after the fold results and before the holdout (a 26-week comparison against naive, then a 20% ceiling per band) and added a year-end indicator, making `volume_v2` (L-42). ADR-071, decided after the holdout, serves a slice-band only if it passes on fold B and its holdout MAPE is at most 20%, and shows the larger error. 5 of 18 slice-bands are served:

| Slice | Band (weeks) | Fold B MAPE % | Holdout MAPE % | Shown error % |
|---|---|---|---|---|
| total | 1-4 | 11.77 | 13.58 | 13.58 |
| total | 5-13 | 5.49 | 5.41 | 5.49 |
| total | 14-26 | 11.49 | 9.70 | 11.49 |
| install | 5-13 | 17.96 | 14.33 | 17.96 |
| repair | 5-13 | 10.84 | 9.23 | 10.84 |

The other 13 are refused with their error shown. Four of them passed fold B and missed 20% on the holdout: install 14-26, repair 1-4, upgrade 5-13 and upgrade 14-26 (L-46).

The holdout (March to August 2026) excludes the Q4 peak (L-19), and fold A covers Q4 2024 on one year of history (L-40). The year-end indicator is untested blindly, and its fold evidence is mixed (L-43). Intervals run below nominal: 80% intervals covered 58% to 88% of fold B weeks across slices (L-45). The gate correction and serving rule were decided after seeing results, so the served slice-bands have no further blind test, and with 15 to 45 requests a week per service type most slice-bands are refused (L-47). The forecast agent's parse evaluation scored 14/14 in each of 3 runs, on a small set that shares an author with the prompt (L-48), and 7 end-to-end questions ran on the local stack on 2026-10-02.

*Sources:* `evals/results/forecast/2026-10-02_folds_v2/fold_A.json`, `evals/results/forecast/2026-10-02_folds_v2/gates.json`, `evals/results/forecast/2026-10-02_folds/gate.json`, `evals/results/forecast/2026-10-02_folds/fold_B.json`, `evals/results/forecast/2026-10-02_holdout/holdout.json`, `ml/forecast/artifacts/volume_v2.manifest.json`, `evals/results/forecast_agent/2026-10-02/summary.md`.

*Notes on sources:* `holdout.json` also holds `loglinear_robust_v1` (total holdout MAPE 9.26 against the same 14.80 baseline). ADR-070 chose `volume_v2` after the fold results and before the holdout.

**Status:** draft 2026-10-23.

### 4.5 Sentiment

The fine-tuned BERT model (`bert_v1`) scored macro-F1 0.9713 on the 1,128-comment test split, against 0.9431 for a TF-IDF plus logistic regression baseline. The difference is 0.0282 (paired bootstrap 95% interval 0.0116 to 0.0456), so BERT is better overall.

| Model | Macro-F1 | Accuracy |
|---|---|---|
| `bert_v1` | 0.9713 | 0.9796 |
| `tfidf_logreg` | 0.9431 | 0.9566 |
| `diagnostic_majority` (always the majority class) | 0.1673 | 0.5027 |

Macro-F1 is the mean of the per-class F1 scores, so small classes count equally. The paired bootstrap resamples the same test comments 10,000 times and recomputes the difference. McNemar's exact test compares only the comments one model gets right and the other wrong: BERT alone was right on 36, TF-IDF alone on 10 (p = 0.000156). The rules were fixed before the results (ADR-064 to ADR-066): BERT counts as better only if the interval excludes zero or McNemar's p is below 0.05, and every subset is reported. The rule that would have judged BERT on hard cases alone, if TF-IDF reached 0.95, did not fire.

| Hard-case subset | n | BERT | McNemar p | Verdict |
|---|---|---|---|---|
| sarcastic | 42 | accuracy 0.8333 | 1.0 | not distinguishable |
| implicit | 126 | accuracy 0.9286 | 0.266845703125 | not distinguishable |
| mixed | 88 | recall 0.9545, F1 0.9333 | 0.1796875 | not distinguishable |

BERT is not shown to be better than TF-IDF on the hard cases; the subsets are too small (L-22).

On test, expected calibration error (ECE, the gap between stated confidence and accuracy) was 0.0106 raw and 0.0094 after temperature scaling. 16 of 1,128 comments (rate 0.0142) were flagged for human review; accuracy was 0.5 on flagged and 0.9865 on unflagged comments. The flags hold 8 of BERT's 23 errors, so a missing flag does not mean a correct answer (L-32). The validation figures (temperature 1.032156, threshold 0.840840745682907, 21 of 1,129 flagged) are optimistic because both were fitted on the split used to select the model (L-31). Only the test figures are results.

Accuracy measures agreement with a written specification on synthetic, model-written text, not with real customers (L-23). TF-IDF's selected setting sits at the edge of its fixed grid, and a wider grid scored about 0.008 higher on validation (L-26). Both BERT runs peaked at the epoch cap and may be under-trained (L-30). The deployed service reads stored predictions and cannot score new comments (L-91). The parse evaluation (13/14 in each of 3 runs) used a small set that shares an author with the prompt (L-39).

*Sources:* `evals/results/sentiment/2026-10-01_bert_v1/bert_v1.test.metrics.json`, `evals/results/sentiment/2026-10-01_baselines/tfidf_logreg.test.metrics.json`, `evals/results/sentiment/2026-10-01_baselines/diagnostic_majority.test.metrics.json`, `evals/results/sentiment/2026-10-01_bert_v1/comparison.json`, `evals/results/sentiment/2026-10-01_bert_v1/calibration.json`, `evals/results/sentiment_agent/2026-10-01/summary.md`.

*Notes on sources:* the validation and test calibration blocks differ because they are different splits. The test block is the result.

**Status:** draft 2026-10-23.

### 4.6 Latency and cold starts

Warm requests were fast and cold starts were slow, but every reading stayed inside the 120 s ceiling (ADR-034, R-05). In held-out routing the per-run median was 3.7, 3.5 and 3.81 s and the p95 was 17.62, 5.36 and 5.06 s, with no question over its deadline. In the golden run the median was 3.93 s, the maximum 5.9 s and none exceeded 120 s. These are the frozen system.

A cold start is the first request after idle, when Cloud Run starts new containers. In the deploy window the reporting path took 55.87 s in the browser and 54.47 s at the gateway (2026-10-13). Session 1 (2026-10-15) ran on the current build `9ab7c77` (§2):

| Path | Reading |
|---|---|
| sentiment | 61 s stopwatch; gateway 61,488 ms (the gateway hop was not cold) |
| sentiment, repeat | 30.64 s |
| forecast | 46 s |
| reporting (TS-20-A) | 29 s; gateway 29,937 ms |

Independent scaling was not shown: in scenario TS-18-C the scaling clause failed, with `ops-reporting` and `ops-forecast` each staying at 1 instance (L-101). The session 1 readings are single readings (L-103).

The BERT latency figures are a proxy from a local CPU-limited container, not Cloud Run (L-28): cold start a median of 13.12 s at 1 CPU and 13.02 s at 2 CPU against a 20 s budget, and 9.8 s at 1 CPU for the largest account-by-quarter slice (107 comments) against 30 s. The real container was slower, and its first scoring pass after a start exceeded the warm budget (L-35).

*Sources:* `evals/results/routing_heldout_v1/2026-10-13/score.json`, `evals/results/golden_v2/2026-10-13/score.json`, `docs/deploy-window-log.md`, `evals/results/session1/2026-10-15/summary.md`, `evals/results/sentiment/2026-10-01_latency_proxy/summary.md`.

*Notes on sources:* `evals/results/sprint5_summary.md` rounds the routing latency to "3.5 to 3.8 s" and "p95 at most 17.6 s"; the figures above are from `score.json`.

**Status:** draft 2026-10-23.

### 4.7 Cost

The measured runs were cheap at list price. The held-out routing and golden run cost $0.172689 for 186 requests, the most expensive request was $0.001737, and no request had an unknown cost. These are list-price estimates from the logs, not the invoice (L-71, L-94).

| Run | Date | Requests (cap) | List-price cost (cap) |
|---|---|---|---|
| Held-out routing and golden | 2026-10-13 | 186 (186) | $0.172689 ($1.50) |
| Interpretation and FR-03 gates | 2026-10-12 | 418 (561) | $0.2719 ($3.00) |
| Owner verification session 1 | 2026-10-15 | 57 (75) | $0.079 ($0.25) |

The owner's console readings are dated and not reconciled with the table. On 2026-10-15, before session 1, the AI Studio credit balance was $7.88. At close, AI Studio total spend was $2.12 for 2026-09-18 to 2026-10-15, and GCP billing was $4.50 cost minus $1.64 savings, $2.86, for 2026-10-01 to 2026-10-15. On 2026-10-16 the owner read a prepaid balance of $7.85 and GCP cost to date of $3.15, with budget alerts at $10, $50 and $80.

The guardrails are a per-request cap of $0.02 and per-process caps of `LLM_MAX_REQUESTS=1500` and `LLM_MAX_SPEND_USD=1.00`. The per-process caps are not global (L-88, L-93), so the prepaid balance is the real ceiling. The table lists three runs only; it is not the project's total spend.

*Sources:* `evals/results/sprint5_x_ledger.json`, `evals/results/sprint5_x.md`, `evals/sprint5_gates.md`, `evals/results/session1/2026-10-15/ledger.json`, `evals/results/session1/2026-10-15/summary.md`, `docs/production-grade-audit.md`.

*Notes on sources:* the console readings cover different dates and windows ($7.88 against $7.85 for the prepaid balance; $2.86 against $3.15 for GCP cost), so they are listed separately.

**Status:** draft 2026-10-23.

## 5. Failure analysis

The Sprint 5 failures from the held-out routing and golden runs fall into five patterns. Item-level detail, including the 12 items behind the 36 wrong held-out item-runs, is in `evals/results/sprint5_failure_analysis.md`, with the data in `evals/results/sprint5_failure_data.md`. Both sets are spent, so reading either file to revise a prompt makes them development data.

1. **Ambiguity is answered, not flagged.** 21 held-out item-runs and G35 (FR-03, L-58). Since then, ADR-114's third attempt ended in a no-go, and ADR-116 made `route_v6` the default router. It recognises 10 of 15 ambiguous items across two sets, and FR-03 stays not met (§6).
2. **A future-tense question on an out-of-scope subject goes to forecast.** NM-14, NM-20 and G08 (L-96). The specialist declines, so the route is wrong and the outcome is right. `route_v6` states the rule for these questions, and its held-out non-ambiguous score rose from 38 to 42 of 43 (ADR-116, §6). That comparison is post hoc and on a spent set. ADR-116 does not say NM-14 or NM-20 now route correctly, and G08 was not rerun.
3. **A qualifier the system cannot honour is dropped or not named.** G05 failed. G04 and G10 passed mechanically, and the assistant's reading found a `must_not` breach in G10 (L-56, L-95 (4), R-18).
4. **A term or period the data does not define is resolved by the system's own reading.** G03 ("district") and G07 ("end of next year"). The reading is stated and not asked, and the rulings are the owner's (L-95 (1) and (2), R-18).
5. **The mechanical score and the owner's judgement disagree on 4 of 36, in both directions.** The mechanical rule was too strict on G08, G21 and G28 and blind to the text on G27 (R-16, L-95; §4.2).

The failures above are the frozen system's (§2). `route_v6` takes effect at the Sprint 6.5 redeploy (ADR-116).

*Sources:* `evals/results/sprint5_failure_analysis.md`, `evals/results/sprint5_failure_data.md`, `docs/decisions-log.md` (ADR-114, ADR-116).

**Status:** draft 2026-10-28.

## 6. Gates that failed

A gate is a pass or fail rule committed before the run it judges (pre-registration). FR-03 is the requirement that the router asks the user to rephrase an ambiguous question and does not best-fit route it. The FR-03 gates come first, then the interpretation gates, then the third FR-03 attempt and the decision that followed.

**FR-03, the first two attempts (ADR-075, ADR-076; 2026-10-03 and 10-04).** ADR-075's gate asked that few clear questions be flagged ambiguous, that accuracy hold against `route_v3`, and that at least 4 of 5 ambiguous items be recognised. `route_v4` failed the first: r05, a clear sentiment question, was flagged in 2 of 3 runs. `route_v5` failed the second, scoring 41 in run 2 against a floor of 42. ADR-076 then corrected the accuracy test after the result, because it used one `route_v3` run where ADR-054 requires k=3; the original verdict stays on record. On the development sets `route_v5` then scored 44, 41, 43 (mean 42.67) against `route_v3`'s 43, 43, 43. On 15 fresh owner-written questions it flagged 0 clear item-runs, scored 10, 10, 10 on non-ambiguous items against 10, 10, 9, and recognised 3 of 5 ambiguous items (needed 4). `route_v3` stayed the default (L-58).

**The Sprint 5 FR-03 gate (ADR-101; 2026-10-12).** `route_v6` replaced examples with a rule ("the measure decides, never the place, team or period") and was committed before it ran. ADR-101 applied ADR-076's four criteria, scaled, to `fr03_fresh_v2` (8 ambiguous and 8 other questions). Non-ambiguous item-runs flagged: 0 of 24. Development mean: 43, 43, 43. Fresh non-ambiguous correct: 7, 7, 7 against 8, 8, 8 (floor 7.00). Ambiguous items recognised: **4 of 8, fail** (needed 6); AMB-08, AMB-11, AMB-17 and AMB-18 were missed in every run. `route_v3` stayed the default.

**The interpretation gates (ADR-089, ADR-102; 2026-10-09 and 10-12).** QA's interpretation check asks a model whether the parsed request faithfully restates the question. ADR-089 pre-registered limits on false rejects and catches over 84 pairs at k=3 (commit `6c79e50`). `qa_interp_v1` and `qa_interp_v2` both failed the false-reject limit in run 1 (6 and 7 of 42) and were stopped early; that stop was not pre-registered. ADR-102 restated the gate as rates on frozen generated pairs. `qa_interp_v3` had 3 false rejects of 23 (limit 1; reporting 1 of 10, forecast 1 of 7, sentiment 1 of 6) and 19 of 23 wrong pairs caught (floor 19) in run 1; runs 2 and 3 were not made. The check stays advisory with `qa_interp_v2`: it is logged and never fails an answer (L-74). The frozen gate holds one decline pair, though declines are the failure kind that sank all three prompts, so it does not test the main failure (L-92). The two Sprint 5 gates used 418 of 561 requests and $0.2719 of $3.00.

**The third and final FR-03 attempt (ADR-114, ADR-115; 2026-10-22).** `route_v6` was kept unchanged and the routing call's thinking level (how many tokens the model may spend reasoning first) was varied. ADR-114 fixed five go criteria before the first call (G1 to G5: ambiguous recognition, gain over `minimal`, false flags, development accuracy, latency and cost); the table gives the thresholds for G1 to G4, and G5 was median at most 5 s, p95 at most 10 s and cost at most $0.003 per call. At `minimal`, `route_v6` recognised 10 of the 15. `low` reported zero thinking tokens on all 10 probe calls and was dropped; ADR-115 wrote that rule after the probe, using only the token count. The recorded prior was that a pass was less likely than not.

| Level | G1 (≥11 of 15) | G2 (≥+3) | G3 (≤11 of 285) | G4 (≥42.00) | G5 median / p95 / cost | Result |
|---|---|---|---|---|---|---|
| `medium` | 11 | +1 | 4 | 43.00 | 1.67 s / 3.31 s / $0.00166 | fail: G2 |
| `high` | 9 | −1 | 3 | 42.67 | 2.66 s / 5.23 s / $0.00274 | fail: G1, G2 |

A higher thinking level did not add a measurable gain: `medium` recognised one more item than `minimal` and `high` one fewer. G2 did its job and separated a real gain from a one-item difference. Two fresh misses (AMB-11, AMB-17) persisted at every level. The result was a no-go: no blind set, no gate, FR-03 unmet, no further attempt. The attempt used 870 of 1,550 requests and $1.641 of $2.50 at list price, above the $0.50 to $1.50 estimate because `high` cost about $0.0027 per call. The disclosures in ADR-114's result note: the level was chosen on two spent generated sets; the `low` probe started from uncommitted code; the `high` probe's `git_dirty` flag came from the run's own outputs; a harness fix (`b004a58`) landed between pre-registration and the `high` probe and changed no criterion; and request pacing of 60 per minute was not specified in the ADR.

**What shipped instead (ADR-116; 2026-10-22).** This is a decision, not a gate result. `route_v6` became the default router at `minimal`. It was decided after the results, was not pre-registered and sets no threshold. FR-03 stays not met: 10 of 15 is below ADR-101's 75% floor, and about one ambiguous question in three is still best-fit routed.

| Set | Measure | `route_v6` | `route_v3` (deployed) |
|---|---|---|---|
| `fr03_fresh_v2` (ADR-101) | ambiguous recognised, of 8 | 4 | 0 |
| `fr03_fresh_v2` (ADR-101) | non-ambiguous correct, per run, of 8 | 7, 7, 7 | 8, 8, 8 |
| `routing_heldout_v1` (ADR-114 baseline; Prompt X) | ambiguous recognised, of 7 | 6 | 0 |
| `routing_heldout_v1` (ADR-114 baseline; Prompt X) | non-ambiguous correct, per run, of 43 | 42, 42, 42 | 38, 38, 38 |
| **Both** | **ambiguous recognised** | **10 of 15** | **0 of 15** |
| **Both** | **non-ambiguous correct, per run** | **49 of 51** | **46 of 51** |

On an ambiguous question `route_v6` was never worse than `route_v3`; where it misses, it best-fits, as `route_v3` always does. Known costs: CS-10, a clear sentiment question, is routed `multi_domain` in 3 of 3 runs; r06 is over-flagged; s20 is no longer recognised. Its routing call reads about 1,400 input tokens against about 600 (about $0.0005 against $0.0003 at list price, L-71). It was committed before `routing_heldout_v1` was first run, so that set did not tune it, but both sets come from the router's own model family and are spent. The switch takes effect only at the Sprint 6.5 redeploy, so the system evaluated in §2 and §4 uses `route_v3`.

**What the failed gates show about the method.** Pre-registration caught prompt revisions that had learned their examples and not the concept: `route_v5` recognised 5 of 5 ambiguous items on the sets it was revised against and 3 of 5 on fresh questions, and `route_v6` recognised 5 of 5 on `fr03_fresh_v1`, which was development material by then, and 4 of 8 on `fr03_fresh_v2`, missing the same items every run. Rules were nonetheless changed after results, and the records say so. ADR-070 corrected the forecast gate after the fold results, and that correction turned the total slice's recorded failure into a pass (ADR-070 says so); ADR-071 then also required the blind holdout. ADR-076 corrected the accuracy criterion after `route_v5` failed it, and the gate still failed on ambiguous recognition. ADR-115 changed a stop rule after one probe result. ADR-116 chose the default router after the results. Every such change is disclosed in its own entry, the original verdicts stay on record, none is presented as pre-registered, and where possible a later blind test was required. With 5 to 8 ambiguous items per fresh set, these failures show that these prompts did not clear these bars, not that FR-03 cannot be met.

*Sources:* `evals/sprint5_gates.md`, `docs/decisions-log.md` (ADR-075, ADR-076, ADR-089, ADR-101, ADR-102, ADR-114 and its result note, ADR-115, ADR-116), `evals/fr03_v3/ledger.jsonl`, `evals/results/fr03_v3/`.

*Notes on sources:* ADR-101 gives `route_v6` 11 of 16 against 8 of 16 on the fresh set; `evals/sprint5_gates.md` gives the 8 non-ambiguous items as 7, 7, 7 against 8, 8, 8. They reconcile: 7 + 4 = 11, and 8 + 0 = 8.

**Status:** draft 2026-10-23.

## 7. Divergences from the submitted documents

The built system differs from the submitted documents `02` (Detailed Requirements Analysis), `03` (Planning and Management Document), `04` (Project Design and Solution Architecture) and `05` (Test Scenarios). Nothing in a submitted document was edited. Nothing from Sprint 6.5 is counted in `05` or `06` (Production Support Document) (ADR-106), and the owner revises the academic documents in the final documentation packet (ADR-117). Items marked "not deployed" take effect at the Sprint 6.5 redeploy and need a second look in the final report.

**`02`**
- FR-10 says a model that fails the threshold on held-out weeks is not deployed. The system deploys `volume_v2` and withholds each failing slice-band, with its error shown (ADR-071; sprint log, 2026-10-04).

**`03`**
- The calendar and the deploy window (2026-11-02 to 11-04) were moved by ADR-078 and ADR-082 (2026-10-05, 10-08), ADR-093 (10-10), ADR-109 (10-15), ADR-113 (10-18) and ADR-117 (10-22). The final date, 12-05, is unchanged.
- `03` plans a final presentation. The final package is now code, a documentation packet and a live demonstration, with no slide file (ADR-117, which supersedes ADR-044 in part).

**`04`**
- TA-16 quotes the stop date 2026-11-04. ADR-078 moves the deploy window to 2026-10-12 to 10-14 (sprint log, 2026-10-05, recorded twice).
- "Each component deploys as its own Cloud Run service." ADR-079 runs each MCP server as a sidecar of its agent.
- The interface "on Node.js LTS." ADR-080 serves a static export from the gateway, so no Node.js runs in production.
- Table 3 says the orchestrator routes on Agent Card skills. `route_v3` hard-codes the domain descriptions, and the card supplies only the agent's URL.
- Three sentiment lines differ: deployed sentiment reads stored predictions only (ADR-100; sprint log, 2026-10-13).

**`05`**
- TS-20-E records a known fail: no synthetic-data notice. The repository now has a notice that also covers the sentiment model's synthetic training data (data dictionary §6, rule 6, dated block; sprint log, 2026-10-22). It is not deployed, and `05`'s recorded result stands (ADR-106).
- TS-02 records FR-03 as a known fail. `route_v6` partly addresses it, in the redeploy after `06` (ADR-116). `05` and `06` describe FR-03 as unmet (ADR-106), and it stays not met.

**Not tied to a named document**
- Identity-Aware Proxy was replaced by invite-link access (ADR-097; sprint log, 2026-10-13). A search of `02` to `06` found no mention of it.
- The UI and API additions are differences from the evaluated system (ADR-103), not from a named document (ADR-117). Example questions, a "How it works" page, an FAQ and a CI build of the UI are merged. The answer journey, an added field in the orchestrator's response, is also merged (sprint log, 2026-10-22 and 10-23). None is deployed. The evaluation results page and the demonstration runbook are planned.

*Sources:* `docs/sprint-log.md` (the post-submission divergence lists of 2026-10-04, 10-05, 10-08, 10-10 and 10-13; the "divergence list" item and its sub-bullets; the carried-over notes of 2026-10-22 and 10-23), `docs/decisions-log.md` (ADR-044, ADR-097, ADR-100, ADR-103, ADR-106, ADR-113, ADR-116, ADR-117), `docs/data-dictionary.md` (§6, rule 6).

**Status:** draft 2026-10-28.

## 8. Production-grade status

**What goes here:** the production-grade checklist verdicts and what the evidence does and does not show. The audit itself is `docs/production-grade-audit.md` (dated 2026-10-16, S6-P1).

**Figures to cite:** the summary table of `docs/production-grade-audit.md`, copied as it stands (lines 13 to 26, including item 12's dated notes). Its "Ticks:" line (line 28) is not copied: it predates item 12's later verdict, which the table row records.

| # | Item | Required or portfolio | Verdict | Basis |
|---|---|---|---|---|
| 1 | Containerized, reproducible builds | Required | **Met, deployed** | Nine Dockerfiles install `--locked` from `uv.lock`; all six services serve the commit-tagged image from build `0dc5aae1`. Base images are floating tags (a limit). |
| 2 | Config and secrets | Required | **Met, deployed** | Per-container mounts read from the live services; guard tests in CI; 0 secret patterns in 14 days of logs. Pattern-based. |
| 3 | Structured logging, trace IDs | Required | **Met, deployed** | One trace on 22 entries across gateway, orchestrator, reporting plus sidecar and QA, with access lines (read from Cloud Logging). L-98 limit stands. |
| 4 | Health checks and readiness | Required | **Partly met** | Endpoints and startup probes exist; **the QA container's startup probe is `/healthz`, not `/readyz`**; no Cloud Run liveness probe anywhere. |
| 5 | Retries, timeouts, breakers (120 s) | Required | **Met, offline only** | Tested offline; the 30 s routing timeout acted live on the previous build; cold starts held 120 s. Retry logging unverified deployed (0 lines in 30 days). |
| 6 | Graceful degradation | Required | **Met, offline only** | ADR-088 behaviour tested; alert verified live with a synthetic entry; real degradation seen on the previous build only. **No specialist-unavailable path has run on the current build.** |
| 7 | Test suite | Required | **Met, offline only** | CI green on `fa2c7cd`: 2722 unit and 1096 integration passed; 2722 passed again in a fresh clone. 31 integration skips are the local-only sentiment tests (L-78). |
| 8 | Eval harness | Required | **Met, offline only** | Harness plus dated results: held-out routing 38/50, golden 29/36, QA faults 223/223 (upper bound). The evaluation report is not written. |
| 9 | CI pipeline | CI required; CD portfolio | **Partly met** | CI is green on `main` and both Z2 conditions are done. But the pipeline's verify step has run in Cloud Build only for the two-service slice (2026-10-08); both full-system deploys ran with `_RUN_VERIFY=false` and a hand-run `verify.py`. |
| 10 | Least-privilege DB roles | Required | **Met, offline only** | Already ticked; grants asserted in CI; the deployed role per container is read from the services. Not re-run on Cloud SQL. |
| 11 | Cost guardrails and caps | Required | **Met, deployed** | Caps tested and read from the live services; the owner's console readings (2026-10-16) give budget alerts at $10, $50 and $80, a $7.85 prepaid balance and $3.15 GCP cost to date. The caps are per process, so the balance is the real ceiling. |
| 12 | README, diagram, setup from clean | Required | **Not met** | Step 3 (`docker compose up -d postgres`) fails on a missing `GOOGLE_AI_API_KEY` the README never mentions at that step; the diagram is a placeholder. *2026-10-18 (S6-R1; owner-decided 2026-10-16; assistant-drafted.) Re-run: setup half **met, offline only** (every step before the key-and-weights step passes, and the README warns before it); the diagram is now Mermaid source in the README, not validated (no Node here) and not yet seen rendered. Verdict stays **Not met** until the owner confirms the render; see "Fresh-clone record, re-run 2026-10-18".* *2026-10-18 (S6-R1 follow-up; owner-decided 2026-10-18; assistant-drafted.) The owner saw the diagram render on GitHub, and it validated with mermaid-cli 11.4.2 in headless Chromium with no errors (branch commit `8b55192`). Verdict now **Met, offline only**; ticked in `architecture.md` §7.* |

**Conflicts:** none found in the copied table. The table's item 8 basis, "held-out routing 38/50, golden 29/36, QA faults 223/223 (upper bound)", matches sections 4.1 to 4.3.

**Status:** skeleton.

## 9. Threats to validity

**What goes here:** one line each, with its limitation ID. Wording is written in the buffer.

**Figures to cite:**
- Synthetic data: L-102 (the whole evaluation runs on synthetic, generated data); L-01 records one consequence, first-time fix of about 98% (0.9798).
- Generated sets from the same model family as the system: L-86.
- QA's faults drafted by its author: L-85 (and `evals/results/qa_faults/2026-10-10/README.md`, "Not blind").
- Owner-written items scoring lower than drafted ones: L-54; 6 of 10 against 23 of 26 mechanical (`evals/results/golden_v2/2026-10-13/score.json`); "the gap is four items and carries no significance claim" (`evals/results/sprint5_summary.md`).
- Single runs against k=3: L-103 (the golden run and owner session 1 are single runs; the routing evals are k=3). Detail: routing k=3 (L-17, L-18: "Each recorded result is a single run, kept as run"); the golden set one run (`evals/results/sprint5_x.md`); the BERT proxy's full-window and 12-month figures single runs (L-28); owner session 1 "single run, decision 3" (`evals/results/session1/2026-10-15/summary.md`, "For the 05 revision").
- Both blind sets spent after 2026-10-13: `evals/results/sprint5_x.md`.

**Conflicts:** none found.

**Status:** skeleton.

## 10. After the evaluation (Sprint 6.5)

**What goes here:** a placeholder.

To be written if 6.5 changes answers (ADR-113).

**Status:** skeleton.

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

### L-54 — The golden set exists and is blind until Sprint 5 (2026-10-02)
- **What:** `evals/golden/golden_v1.jsonl` (36 items) and its expected figures were built
  without calling any agent, the orchestrator or an MCP server, and no LLM call was made.
  Nothing about how the current system answers these questions is known yet; the first
  run is the Sprint 5 evaluation (ADR-074). The questions' authorship is partly shared
  with the system's: the 26 drafted items, like the parse sets (L-48, L-53), were written
  by the same process that wrote the prompts, so they may favour phrasings the prompts
  handle. The 10 owner-written items are the check on that.
- **Why accepted:** Running it now would end its blindness. If it is ever used to revise
  a prompt, it becomes v2 and that use is disclosed (ADR-074).
- **Recorded in:** ADR-074; `evals/golden/golden_v1.manifest.json` (SHA-256 of the
  questions and expected files).

### L-55 — The forecast oracle shares prediction code with the server (2026-10-02)
- **What:** The golden set's forecast expectations come from `packages/forecast_runtime`,
  the same prediction code `mcp_volume` runs. A bug in that code would appear in both the
  answer and the expectation, and the golden set wouldn't catch it.
- **Why accepted:** ADR-074's documented exception. The golden set checks that the agent
  presents the model's served numbers, ranges and errors correctly and withholds the
  rest; the model's accuracy is judged by the holdout (ADR-069 to ADR-071). One forecast
  week (G25, week 1) is also computed by hand from the stored coefficients, without
  `forecast_runtime`, in `tests/integration/test_golden_oracles.py`.
- **Recorded in:** ADR-074.

### L-56 — Four golden items are stretch items the current design may fail (2026-10-02)
- **What:** Each asks for something the data or design doesn't support, and checks that
  the answer says so rather than substituting:
  - G02, a city ("repeat truck rolls in Chicago"): regions only; must not present
    all-region or Central figures as Chicago.
  - G04, complaint themes since an app update: no theme extraction and no app-update date;
    must not invent either.
  - G05, a cause ("why did CSAT crater after the storm"): must not assert a cause or a
    trend.
  - G10, a product line ("fiber install"): install volume only; must say it isn't
    fiber-specific, and withhold the unserved weeks.
- **Why accepted:** They record behaviour a correct system should show. Their failures
  will be reported in Sprint 5 as known limitations, not hidden (ADR-074).
- **Recorded in:** `evals/golden/golden_v1.jsonl` (`stretch: true`).

### L-57 — Ambiguity labels are owner judgement, and the v2 routing sets are not blind (2026-10-03)
- **What:** Whether a question is *ambiguous* (it could mean different measurable things to
  different specialists) or only *underspecified* (one domain clearly fits, a detail is
  missing) is a judgement, made by the owner under ADR-075's definition. Reasonable
  people could label several items the other way: r03 ("Why are escalations up in district
  4?") is kept as reporting, s19 ("Are customers happy with the technicians?") as
  sentiment, and r06 ("Is the field team falling behind today?") as reporting. The
  relabelled `seed_v2` and `routing_v2` were written knowing how `route_v3` behaves on
  these questions, so they are not blind, and the ambiguous category holds only 5 items.
- **Why accepted:** Every relabel records its reason (`relabel_v2`), and the labels were
  committed before any `route_v4` run. The golden set, still blind, is the independent
  check in Sprint 5.
- **Recorded in:** ADR-075; `evals/routing/README.md`; commit 660d88d.

### L-58 — FR-03 is not met: ambiguous questions are still best-fit routed (2026-10-03)
- **What:** ADR-075's `ambiguous` route is built and tested, but neither prompt that
  produces it passed the pre-registered gate. `route_v4` flagged a clear sentiment question
  (r05) as ambiguous in 2 of 3 runs; `route_v5` fixed that but dropped to 41 of 44
  non-ambiguous items in one run, against a floor of 42. The default is still `route_v3`,
  which best-fit routes an ambiguous question such as "How's the Southeast doing?" to one
  specialist, which answers a question the user may not have asked. `golden_v2`'s G35
  expects the clarification, so it will fail in Sprint 5 unless this is resolved first.
- **Why accepted:** For now, because the alternative was loosening a pre-registered gate
  or exceeding the call budget. Both `route_v4` and `route_v5` recognised every ambiguous
  item in at least 2 of 3 runs; the failures are on the non-ambiguous side, and two of
  `route_v5`'s three misses are near-miss items that `route_v3` gets wrong or nearly wrong
  as well. A fresh budget and a decision on the next revision are needed.
- **Recorded in:** ADR-075 (results); `evals/results/routing_*_v2_*route_v{3,4,5}_20261003T*.json`.

### L-58 update — the corrected FR-03 gate also failed (2026-10-04)
- **What:** ADR-076 corrected ADR-075's comparison (3 `route_v3` runs, as ADR-054 requires)
  and confirmed on `fr03_fresh_v1`, 15 owner-written questions no prompt was tuned on.
  `route_v5` passed (a), (b1) and (b2): it flagged no clear or underspecified question as
  ambiguous and matched `route_v3` on non-ambiguous accuracy. It failed (c): of 5 fresh
  ambiguous questions it recognised 3, routing f03 ("Are we on track going into Q4?") to
  forecast and f05 ("Where are we losing customer goodwill?") to sentiment in all three
  runs. Its 5 of 5 on the v2 ambiguous items did not carry over to fresh questions.
- **Status:** FR-03 stays open. `route_v3` remains the default, and under ADR-076 there
  are no further attempts before Sprint 5. L-58 above stands as written.
- **`route_v3` emits `ambiguous` occasionally:** it doesn't define the route, but the
  `RouteDecision` schema accepts it (ADR-075), so the model can choose it. Across the 9
  `route_v3` runs made since the schema gained it (192 routing calls, 2026-10-03 and
  2026-10-04), it did so 2 times (1.0%), both on f02 ("Is the repair side of the
  business in trouble?", labelled ambiguous), both with valid candidates. Its 6 earlier
  runs could not emit it. When it happens, the orchestrator answers with the
  clarification, falling back to all three domains if candidates are missing (unit-
  tested). This is measured behaviour and is kept; it is not FR-03 compliance.
- **Recorded in:** ADR-076 (results).

### L-59 — Service-to-service hops are unauthenticated in local compose (2026-10-04)
- **What:** No token, key or certificate is checked on any hop between the orchestrator, the
  agents and the MCP servers, and the orchestrator's `/ask` has no authentication. The compose
  network is the only boundary. Until 2026-10-04 `/ask` was also published on every host
  interface; every published port is now bound to `127.0.0.1`
  (`test_every_published_port_binds_loopback_only`), so the unauthenticated entry point is
  reachable from the developer's machine only.
- **Why accepted:** It is local development against synthetic data, and the ports are bound to
  localhost. IAM ID tokens arrive with the Sprint 4 deploy of the reporting slice (ADR-045), and
  the rest in Sprint 5 with the gateway, which replaces `/ask` as the entry point.
- **Recorded in:** `docs/security-model.md`, section 2.

### L-60 — The router's model-written `reason` and unredacted tracebacks appear in the logs (2026-10-05)
- **What:** The orchestrator logs the router's `reason` on every routing decision (up to 300 characters, written by the model), and services log unredacted exception tracebacks. Both can carry text paraphrased or quoted from what the user typed, such as a technician's name or a phrase from the question. The pre-Sprint-4 hardening removed typed technician names and rejected argument values from the logs, but not these two.
- **Why accepted:** For now. The data is synthetic and the logs are local. The `reason` is also what makes a routing result traceable to a decision. Redaction is revisited with the Sprint 6 hardening.
- **Recorded in:** `docs/security-model.md`, section 5; `docs/requirements-traceability.md` (NFR-2). This clears the last unrecorded traceability gap.

**Update 2026-10-14 (Z2a, ADR-108; owner-decided 2026-10-14; assistant-drafted): resolved in the repo, not yet deployed.** The router's `reason` is logged as its length and a short hash, and an exception is logged as its class names and frames with no message (`packages/common/src/common/logging.py`: `text_fields`, `safe_exception`); an agent's failure sentence and the gateway's upstream detail are logged the same way. Tests: `services/agent_reporting/tests/test_log_redaction.py` (`test_a_typed_technician_name_is_in_no_log_line_from_any_service`, `test_an_exception_is_logged_as_classes_and_frames_not_its_message`, `test_the_routers_reason_is_a_length_and_a_hash`, `test_a_sdk_debug_line_cannot_carry_the_question`). The test runs orchestrator and reporting agent in-process at DEBUG with the services' logging configuration. **Not covered:** Google's own error sentence for a rejected request is still logged (capped), and the QA and sentiment and forecast services share the formatter but have no end-to-end name test of their own. The deployed services log as before until Z2b.

### L-61 — Each agent and its MCP sidecar share one service account (2026-10-05)
- **What:** On Cloud Run an agent and its MCP server run as containers of one service (ADR-079), so they share one service account, including its Cloud SQL network permission. The agent container holds no database credentials: they are mounted only into the MCP container, and the database role still limits what that container can read.
- **Why accepted:** Separate identities would need separate services, with an extra cold start and an IAM hop per domain (ADR-079). The control that matters here, the database role, is unchanged.
- **Recorded in:** ADR-079.

### L-62 — Reporting has no single-region or single-account filter (2026-10-05)
- **What:** The reporting tools filter only by technician. A question scoped to one region or account ("SLA compliance in the west region") either gets a full breakdown across all regions or accounts, or, if the parser reads it as one overall figure, an unscoped figure presented as scoped. QA's recompute would not catch the second case, because it would recompute the same unscoped figure. No eval covers a single-region reporting question.
- **Affects:** 05 TS-01-A, TS-02-C and TS-05-B.
- **Why accepted:** For now. Region and account filters, a `parse_v3` update and a parse eval re-run are a Sprint 4 item, built before QA.
- **Recorded in:** the Sprint 4 planned items in `docs/sprint-log.md`.

**Update 2026-10-08 (resolved, ADR-086):** the four incident tools take `region` and `account_id` filters, `find_account` resolves a name, and `parse_v4` (gate passed) extracts both from a question. A filtered figure equals its group's row in the unfiltered breakdown, proved against raw SQL. The unscoped-figure-presented-as-scoped failure is closed for these four tools; what remains is L-67 and L-68. The 05 scenarios TS-01-A, TS-02-C and TS-05-B can be corrected.

### L-63 — Log redaction masks bearer tokens, authorization fields and URL passwords by pattern only (2026-10-08)
- **What:** The shared JSON formatter (`packages/common`) masks `Bearer <token>`, `authorization` header fields and the password in `scheme://user:password@host` in every log line. It is a pattern match, not a guarantee: a secret in another shape, or split across fields, is not caught. It was added because the A2A SDK logs the whole server call context, request headers included, at DEBUG, so an agent running with `LOG_LEVEL=DEBUG` on Cloud Run would otherwise log the caller's ID token. The router's `reason` and tracebacks (L-60) are not redacted by it.
- **Why accepted:** Production runs at INFO, where the SDK does not log headers, and the application code never logs the header, the token or the database URL (asserted by tests at every level). The pattern covers the shapes this system can produce.
- **Recorded in:** `tests/unit/test_log_exposure.py`; `services/orchestrator/tests/test_orchestrator.py` (token exposure).

### L-64 — A revision that fails pipeline verification keeps serving (2026-10-08)
- **What:** The pipeline deploys at 100% traffic, then runs `verify.py`. If verification fails, the build fails but the new revision is already serving. Rollback is manual: `gcloud run services update-traffic <service> --to-revisions=<previous revision>=100 --region=us-central1 --project=a2a-agentic-service-ops-gcp`. The command is in `deploy/README.md`.
- **Why accepted:** For the reporting slice: one user, synthetic data, a few deploys. Promoting only after verification needs a no-traffic deploy and a revision-URL check, which is more pipeline than this slice needs.
- **Sprint 6 candidate:** deploy with no traffic, verify the revision's own URL, then move traffic.
- **Recorded in:** ADR-085; `deploy/README.md`.

### L-65 — The deployed services are unavailable while `ops-db` is stopped (2026-10-08)
- **What:** The reporting sidecar's `/readyz` fails until the database answers, so the agent will not start, and any request needs a new instance at min-instances 0. A merge to `main` while the instance is stopped produces a revision that fails its readiness probe (seen on 2026-10-08).
- **Why accepted:** By design, for cost: the instance is stopped at the end of every day. The readiness probe doing its job is the control.
- **Operation:** start the instance with `--activation-policy=ALWAYS` before any demo or test, and stop it afterwards. The build trigger is disabled between deploy windows (ADR-083).
- **Recorded in:** ADR-083; `deploy/README.md`; the window log.

### L-66 — The integration suite leaks connection pools (2026-10-08)
- **What:** The MCP figures tests build an engine per test and never dispose it. Against Cloud SQL's default `max_connections=25` on the micro tier, 66 tests failed with "remaining connection slots are reserved". The window raised the limit to 60. Production is not affected: each process holds one engine (`pool_size=2`, `max_overflow=2`, so at most 4 connections), and the reporting service runs at most 2 instances, so at most 8 connections.
- **Why accepted:** For now. Local Postgres allows 100 connections, so the leak is invisible locally and in CI.
- **Fix:** dispose the engines in a test fixture (Sprint 4 backlog).
- **Recorded in:** `docs/deploy-window-log.md`; the Sprint 4 backlog in `docs/sprint-log.md`.

**Update 2026-10-08 (resolved):** `tests/integration/conftest.py` gives every MCP server built during a test a pool-less engine (`NullPool`) and disposes it at the end of the test. Evidence: against local Postgres with `max_connections=25` (a temporary compose override, not committed), the two figures test files had 11 failures before the fixture, and the full integration suite then passed (883 passed). The servers' own code is unchanged.

### L-67 — Repeat-visit drivers cannot be filtered to one region or account (2026-10-08)
- **What:** `get_repeat_visit_drivers` takes neither `region` nor `account_id` (ADR-086). A question such as "what drives repeat visits in the west?" is declined with a message naming what is supported (repeat drivers by region or by account). The significance rule compares a group against all other jobs, so a filter changes what "the rest" means; that needs its own decision.
- **Why accepted:** For this phase. The four other metrics are filterable, and the decline is explicit.
- **Recorded in:** ADR-086; `docs/data-dictionary.md` §6.

### L-68 — Areas other than the four regions are declined, not mapped (2026-10-08)
- **What:** A state, a city or a broader area ("Texas", "the Midwest", "the East Coast") parses to `region: "unsupported"` and the answer declines, naming northeast, southeast, central and west. No synonyms, and nothing says which states belong to which region, because the data holds a region per site and no mapping table. "Western" and similar adjectives are not mapped either. A user who means a region by another name gets a decline, not a guess.
- **Why accepted:** A silent mapping would be an unrecorded choice, the Sprint 2 stop rule's point. Declining is honest and cheap to lift later, if the owner decides a mapping.
- **Recorded in:** ADR-086; `docs/data-dictionary.md` §6; parse items f11 and f12.

### L-69 — The parse_v4 set was drafted by the prompt's author, so it is not blind (2026-10-08)
- **What:** The 12 filter items in `evals/reporting_parse/parse_v4.jsonl` were written by the assistant that wrote `parse_v4`. They were committed before any run and the prompt's examples were kept out of them (a test checks that), but their phrasing is the author's. 12 of 12 in all three runs shows the prompt parses these questions; it does not show how it parses the owner's wording. No account with a similar name to another beyond "Silver Creek" and "Bluewater" (ambiguity), no misspelling and no lowercase-only question was tried.
- **Why accepted:** For now (R-16). An owner-written fresh set is the fix, to be used for any later prompt change; the Sprint 5 routing evaluation is the natural place.
- **Recorded in:** ADR-086; `evals/reporting_parse/README.md`.

### L-70 — Circuit-breaker state is per process (2026-10-09)
- **What:** Each breaker (ADR-088) lives in one process. The orchestrator keeps one per specialist, and each service keeps one for the Gemini transport. Two Cloud Run instances keep two breakers, so one instance can have a dependency's breaker open while the other still sends it requests, and a new instance starts with all breakers closed. A breaker that opens on one instance protects only that instance's callers.
- **Why accepted:** At this scale a service runs one or two instances, and a shared breaker would need a shared store (Redis or the database) for a protection NFR-4 asks for in its plainest form. The cost of a wrong call is a few slow requests, bounded by the per-request deadline.
- **Recorded in:** ADR-088; `packages/common/src/common/breaker.py`.

### L-71 — The per-request cost cap counts list-price estimates (2026-10-09)
- **What:** `MAX_COST_PER_RUN_USD` (default $0.02) is compared with the sum of each model call's list-price cost, computed from token counts and `prices.toml`. It is an estimate, also in free mode where nothing is billed. It does not include thinking tokens the API does not report in the usage fields, it is checked before a specialist hop with the total already incurred (so one hop can overshoot the cap by its own cost), and it covers only what the services report in response metadata; a service that does not report a cost adds nothing. It guards against a runaway loop; it is not a budget control.
- **Why accepted:** At Flash-Lite list prices a normal request costs well under $0.01, so the cap sits far above any real request and far below anything that matters to the project budget, whose real controls are the account alerts and the per-process spend caps (ADR-041, ADR-048).
- **Recorded in:** ADR-088; `packages/common/src/common/cost.py`.

### L-72 — QA is tolerant where the data dictionary is silent (2026-10-09) — resolved the same day, see the last update
- **What:** The brief for QA's checks said to stop and ask when a definition is ambiguous for a case the code hits. Building QA from data dictionary §6 alone, these cases came up, and this session could not ask, so five are handled by accepting every reading the specialists' code could have taken, and two are choices (marked below). None changed a result on the loaded database (`tests/integration/test_qa_agrees_with_tools.py`, 100 cases). **They need the owner's ruling:** (1) *Fisher's exact test, two-sided (a choice):* §6 names no convention; QA computes scipy's (the probability of every table no more likely than the observed one), where doubling the one-sided p is another. A different convention would change borderline p-values. (2) *Rate breakdowns:* §6 gives the order only for incident counts (highest first, ties by name). For the three rates QA checks worst-first order, groups with no rate last and that no group cut off at 25 is worse than a kept one, but accepts any order among ties. (3) *Repeat drivers by incident type:* a type with no job in the range may be listed with zero jobs or left out; QA accepts both. (4) *A group that is every job in the range* leaves no "rest" to compare with; QA does not check that group's test. (5) *"Whole word"* in the technician and account lookup is a whitespace-separated word; punctuation inside a word (an apostrophe, a period) is part of it. (6) *Several decline reasons can apply to one request;* a decline passes if the reason its text states is any true one. (7) *Technician filter with repeat drivers (a choice)* is declined by the specialist (ADR-073) but is not stated in §6; QA treats it as a decline reason.
- **The text check has limits:** it fails a number the verified figures do not support and a missing headline number. It cannot catch two real figures swapped, a right number beside a wrong label, or a sentence that misreads right numbers.
- **Why accepted:** For now. Each tolerance can only let a differently-ordered but correct answer pass; none lets a wrong figure pass, and the figures themselves are always recomputed.
- **Recorded in:** ADR-089; `services/agent_qa/src/agent_qa/reporting.py`, `repeats.py`, `stats.py`, `names.py`, `textcheck.py`.

**Update 2026-10-09 (the seven gaps in full, for the owner's ruling).** No code changes were made for this update. Gaps 1 and 7 are ruled (accepted, below); 2 to 6 await a ruling. Specialist lines are as of commit `ee5c564`.

**Correction to the entry above:** gap 5 is not a tolerance. QA's lookup (`agent_qa/names.py`) uses the same whitespace reading as the specialist, so it accepts only that reading and would flag a specialist that changed it. So gaps 2, 3, 4 and 6 are tolerances, and 1, 5 and 7 are readings QA shares with the specialists. ADR-089 says "five tolerant, two choices"; read it as "four and three".

| # | The exact case | What QA accepts today | What the specialist does today | Example where the readings give different figures |
|---|---|---|---|---|
| 1 | The two-sided Fisher p-value of a repeat-driver group (and of the any-other-incident comparison). | Only scipy's: the sum of the probabilities of every table with the same margins that is no more likely than the observed one, with a 1e-7 relative tolerance for ties (`agent_qa/stats.py`); p-values compared to 1e-6. | The same definition, `fisher_exact`, `mcp_incidents/repeats.py:56-74` (tolerance at `:71`). | Doubling the one-sided p is the other common reading. For the table 3 repeated of 20 jobs against 9 of 120: scipy 0.3789, doubled 0.4685. For 1 of 25 against 9 of 75: 0.4439 against 1.0 (capped). Either would move a group across the 0.05 line only near it. |
| 2 | Rate breakdowns (incident rate, SLA, first-time fix) when groups tie or have no rate, at the 25-group cap. §6 gives order only for counts (highest first, ties by name). | Any order among equal rates; groups with no rate after all that have one; no group cut off at 25 may be worse than a kept one. | Worst first, no rate last, then group name ascending, then the first 25 (`mcp_incidents/metrics.py:135-140`). | First-time fix by account, 2026-08-01 to 08-30: 43 accounts, 39 tied at 1.0000. The specialist shows the first 25 by name (the last is Riverbend Distribution Holdings) and cuts Summit Distribution Co. (34 of 34 jobs). Ordering ties by more jobs first would keep Summit and cut smaller accounts. The figures shown differ; QA passes both. |
| 3 | Repeat drivers by incident type, for a type with no completed job in the range. | Listed with zero jobs, or left out. | Left out: only types present among the range's jobs (`mcp_incidents/repeats.py:137`). | 2026-08-01 to 08-03: 34 jobs, only 2 of the 6 types occur. The specialist returns `group_count` 2; the other reading returns 6, four of them with 0 jobs and no rate. |
| 4 | A repeat-driver group that is every job in the range, so there is no "rest" to compare with. | Not checked for significance: `compared`, p-values, `stands_out` and `groups_compared` are skipped; counts, rates and order still are (`agent_qa/reporting.py`, `_repeat`). | `compared` is false when the rest is empty (`repeats.py:151`), so no test and not counted in `groups_compared`. | Constructed, not found in the loaded data: 30 completed jobs in the range, all repair, by service type. The specialist: `compared` false, p null, `groups_compared` 0. Reading §6's "at least 20 jobs" alone: `compared` true, `groups_compared` 1, p 1.0 (a degenerate table), `stands_out` false. |
| 5 | "Whole word" in the technician and account lookup (§6: every word of the query must be a whole word of the name). | Only whitespace-separated words, case-folded (`agent_qa/names.py`). | The same: `text.casefold().split()` (`mcp_incidents/queries.py:292-293`; used at `:315` for technicians, `:380` for accounts). | An account is "Summit Distribution Co." (with the period). The query "Summit Distribution Co" finds 0 accounts and the answer is `account_not_found`; "Summit Distribution Co." finds 1. Reading words without punctuation would find it for both. 17 of the 50 account names end in a period. |
| 6 | A request that breaks several decline rules at once. | A decline passes if the reason its text states is any one that applies (`agent_qa/reporting.py`, `decline_reasons`). | The first rule in a fixed order is stated (`agent_reporting/executor.py:106` unsupported metric, `:108`, `:110`, `:115` area, `:121` repeat with region or account, `:128`, `:133`, `:138-144` technician). | "Repeat visit drivers by region for the west and Ben Okafor": three rules apply. The specialist states the region-or-account one (`:121`); stating the technician one is also true. No figures either way; only the wording of the reason differs. |
| 7 | A technician filter on repeat-visit drivers. | Treated as a decline reason (`repeat_technician`). | Declined (`agent_reporting/executor.py:138-143`); the tool takes no technician argument (`mcp_incidents/server.py:412-414`). | Not a difference in figures: it is the case where a reading could answer ("Ben's repeat rate") and the specialist declines. |

**Ruled by the owner (2026-10-09), to go into data dictionary §6 as written here when §6 is next edited (not edited in this change):**
- *Rule for gap 1.* "Fisher's exact test, two-sided: the p-value is the sum of the probabilities, under the hypergeometric distribution with the table's margins, of every 2×2 table whose probability is no greater than the observed table's (a relative tolerance of 1e-7 for ties). This is the definition of `scipy.stats.fisher_exact` with `alternative='two-sided'`, the one ADR-073's unit test checks."
- *Rule for gap 7.* "Repeat-visit drivers take no technician filter, as they take neither a region nor an account filter (ADR-073, ADR-086). A repeat-drivers question that names a technician is declined, with the reply to ask for repeat drivers by technician instead."

**Update 2026-10-09 (resolved: the owner's rulings).** All seven gaps are ruled and each is now one reading, written into data dictionary §6 ("Rules fixed by the owner on 2026-10-09") and enforced by the specialists and by QA alike. QA has no tolerance left.

| # | Ruling | Specialist change | QA now |
|---|---|---|---|
| 1 | Fisher two-sided is scipy's definition (accepted as drafted). | None (`repeats.py:56-74` already is). | Unchanged: scipy's, p-values to 1e-6. |
| 2 | Ties: worst rate first, then the larger denominator, then the name; groups with no rate last in the same order. | `mcp_incidents/metrics.py` `_rank` sort key now `(no rate, rate, -denominator, name)`. Tests: `test_section6_rulings.py` (equal rates by denominator then name; a worse rate still first; no-rate last; the 40-account tie keeps the 34-job account in the 25) and, on the loaded database, `test_section6_rulings_figures.py` (First-time fix by account, 2026-08-01 to 08-30: Summit Distribution Co. is in the 25, second after Pinecrest Manufacturing Group, among the 21 tied places). | Exactly the first 25 of its own ranking, in order (`_rank_key`); a different order or cut fails. |
| 3 | Zero-job incident types are not listed; `group_count` counts the groups listed. | None (`repeats.py:137` already is); test added. | A group listed with zero jobs fails; `group_count` must equal the groups QA lists. |
| 4 | A group equal to all jobs is listed with its rate, not compared: out of the Bonferroni count, p null, never stands out. | None needed: `repeats.py:151` already does this; a specialist test now pins it (`test_a_group_that_is_every_job_is_listed_with_its_rate_but_not_compared`, `test_a_group_with_no_rest_is_left_out_of_the_bonferroni_count`). | Compares `compared`, p, `stands_out` and `groups_compared` exactly; the skip is gone. |
| 5 | Name words: whitespace split, strip leading and trailing non-alphanumerics from each word, case-folded; same for `find_account` and `find_technician`; pattern rejection unchanged. | `mcp_incidents/queries.py` `_words` (used by both lookups). Tests: "Summit Distribution Co" finds 1 account, "Co" and "Co." find the same, "Mary-Ann" keeps its hyphen, "Neil" does not find "O'Neil", `St John` finds `St. John Reyes`, pattern characters still rejected; on the loaded database both spellings find "Summit Distribution Co.". | `names.words` is the same rule. |
| 6 | The executor's decline order is the rule; QA requires the first applicable reason, with no figures. | None (`executor.py:106-144` is the order). | `decline_reason` returns the first rule that applies; the text must state exactly that reason (the phrases no longer overlap); a name decline is wrong when a rule declines first, and an account decline is wrong unless the technician (if named) resolved. |
| 7 | A technician filter on repeat drivers is declined (accepted as drafted). | None. | Unchanged. |

Evidence: the QA-vs-tools integration cases (100) and the new ones pass against the loaded database; the whole suite and ruff are green (2,092 unit and service tests, 1,077 integration tests, ruff clean; see ADR-089's dated note). The earlier "Correction" paragraph above stands as history: gaps 2 to 6 are no longer open.

### L-73 — Sentiment answers are not verified until phase M2 (2026-10-09)
- **What:** Reporting and forecast answers go through QA. Sentiment answers do not: the orchestrator returns them with `qa_status: not_checked` and a visible "Not verified: sentiment answers are not yet checked by the verification agent." line. The sentiment rating cross-check (ADR-087) has its rule and baseline but no code yet.
- **Why accepted:** For now. The line is the user's warning, and the status is machine-readable for the Sprint 5 interface. M2 builds the check.
- **Recorded in:** ADR-089; `docs/requirements-traceability.md` (FR-11); `services/orchestrator/tests/test_qa_loop.py`.

**Update 2026-10-09 (resolved by ADR-090).** Sentiment answers now go through QA and come back `verified`; the "Not verified" line is removed. `qa_status: not_checked` is still emitted, now only for a request that ended before a check ran (a degraded result).

### L-74 — The interpretation check failed its gate twice and ships advisory (2026-10-09)
- **What:** Neither `qa_interp_v1` nor `qa_interp_v2` met the pre-registered gate (at most 2 false rejects of 42 correct pairs and at least 34 of 42 wrong pairs caught, in every run). v1: 6 false rejects and 37 caught in run 1. v2: 7 and 39. So QA runs the check on every reporting and forecast answer, logs it and reports it on the verdict as an advisory, but it never fails an answer, triggers a re-ask or makes QA unavailable. A wrong parse is therefore not caught by QA today. The re-ask loop in the orchestrator is built and tested but never fires in a running system until a prompt passes and `QA_INTERP_MODE=enforce`.
- **The measurement is also weak evidence either way:** the correct pairs come from parse sets drafted by assistants (L-69) and the mutations are synthetic and blunt, so the 80% catch rate overstates how well it would catch a subtle mis-parse. The model, Flash-Lite at the `minimal` thinking level, mis-computed dates and contradicted its own stated meaning on several correct pairs.
- **Why accepted:** The gate was not loosened and the brief's fallback applies. Options for a later attempt, each a new decision with a new gate: a higher thinking level for this one call, a stronger model (the optional Sprint 5 comparison, ADR-056), or computing the expected dates in code and giving the model only the comparison.
- **Recorded in:** ADR-089; `evals/qa_interp/README.md`; `evals/results/qa_interp/2026-10-09/`.

**Update 2026-10-09 (what "verified" means now, and the rejected pairs).**
- **What `verified` means:** a `qa_status: verified` answer means *the figures are correct for the request as the specialist parsed it*. It does not mean the request was parsed correctly. A misparse (the wrong metric, month, region, breakdown or slice, or a technician or account dropped) can still pass, because the check that would catch it is advisory. **The range and the filters the answer states are the user's check on the parse.** The answer text always says the dates it covers, and a filter, breakdown or name it applied.
- **The 13 correct pairs rejected across both runs** (run 1 of each; the check judged `faithful: false` for a reading that was the pair's label), so the labels and the judge can be reviewed. "Field" is what the model said differed.

| Prompt | Pair | Question | Field flagged | The model's reason |
|---|---|---|---|---|
| v1 | `r-d01-ok` | Which incident types are driving the most repeat visits this quarter? | dates | The date range should be set to the entire current calendar quarter instead of ending prematurely on August 30. |
| v1 | `r-q01-ok` | What was the incident rate last quarter? | dates | The date range should be the first quarter of 2026. |
| v1 | `r-f12-ok` | How many incidents were reported in the Midwest in Q2 2026? | region | The region should have been central because the question asks for the Midwest. |
| v1 | `f-f10-ok` | How many incidents will we have next month? | metric, unsupported | The question asks about incidents, which cannot be forecasted. |
| v1 | `f-f11-ok` | Forecast request volume in the West for the next 8 weeks. | region, unsupported | The question asks for a forecast in the West region, which the system does not support. |
| v1 | `f-f12-ok` | What was request volume in July? | dates, unsupported | The question asks about July 2026, which is in the past, but the system should have treated it as a forecast request or flagged it as unsupported instead of treating it as a valid past period. |
| v2 | `r-d01-ok` | Which incident types are driving the most repeat visits this quarter? | dates | The date range for this quarter should be from July 1, 2026 to August 30, 2026, but the system used an incorrect date range. |
| v2 | `r-q01-ok` | What was the incident rate last quarter? | dates | The dates should be the previous quarter ending 2026-03-31. |
| v2 | `r-f11-ok` | What was SLA compliance in Texas last month? | region | The question asks about Texas, which is not one of the four supported regions. |
| v2 | `r-f12-ok` | How many incidents were reported in the Midwest in Q2 2026? | region | The system should have read the region as unsupported because Midwest does not map to northeast, southeast, central, or west. |
| v2 | `f-f10-ok` | How many incidents will we have next month? | unsupported | The reading should have set unsupported to null because the system can forecast incident volume. |
| v2 | `f-f11-ok` | Forecast request volume in the West for the next 8 weeks. | region, unsupported | The system should have set the region to west and unsupported to null. |
| v2 | `f-f12-ok` | What was request volume in July? | horizon, dates, unsupported | The reading should have set the period to July 2026 in the future instead of marking past period as unsupported. |
  Reading the table: `r-q01-ok` ("last quarter" at an as-of date of 2026-08-30 is Q2 2026, the label) was misjudged both times, the model computing the wrong quarter. `r-d01-ok` ("this quarter" labelled 2026-07-01 to 2026-08-30, to the as-of date) is a convention the model disputed in v1 and then stated correctly in v2 while still answering `false`. The Texas and Midwest pairs (`r-f11-ok`, `r-f12-ok`) and the three forecast declines (`f-f10-ok`, `f-f11-ok`, `f-f12-ok`) are labelled as correct readings of questions the system declines; the model's own reasons in several rows agree with the label while its verdict says otherwise. I think the labels are right in each case and the model is wrong, but the owner should review them: the sets were drafted by assistants (L-69).

**Update 2026-10-10 (the gap as a number, ADR-091).** With figures correct for a wrong request, QA passed all 71 consistent-misparse cases: 0 of 71 caught (reporting 0 of 30, forecast 0 of 19, sentiment 0 of 22; 95% Wilson 0 to 5.1% overall), across a wrong month, region, metric, slice and label. The owner's trailing-quarter case passed 10 of 10 (0 caught). The interpretation client in the harness is a fake, so no advisory was logged; the readings QA would have given a model are kept per case in `results.json`. This is the measured size of the advisory gap, on blunt, assistant-drafted misparses (L-69).

### L-75 — A verified answer means QA's recomputation agrees, not that the definitions are right (2026-10-09)
- **What:** QA and the specialists' tools are written independently, but both from data dictionary §6. A defect in §6 itself (a wrong rule for the SLA clock, a wrong denominator) would be implemented twice and agree. QA also cannot check a forecast's point values, which no one can, and for sentiment (when built) the rating is an independent signal only where it exists.
- **Why accepted:** This is what an independent recomputation can show, and the data dictionary is the shared specification the brief chose. The defence against a wrong definition is review of §6, which the owner does.
- **Recorded in:** ADR-087, ADR-089; `docs/data-dictionary.md` §6.

### L-76 — A routing failure no longer tells the caller to retry later (2026-10-09)
- **What:** A routing call that cannot run (rate-limited, out of daily quota, unavailable, bad credentials, its breaker open, a timeout) is now the degraded result naming `routing` (HTTP 200), where it used to be a 429 with `Retry-After`, or a 503 saying when the daily quota resets, or a 504. The degraded warning says the service is temporarily unavailable; it does not say how long to wait or that the daily quota is spent. The log still has the cause.
- **Why accepted:** One failure shape for every dependency (FR-13, NFR-4) was the brief's choice. NFR-3's "say 'try again later'" is met by the warning's wording; a retry hint can be added to the degraded result in Sprint 5 if the interface needs it.
- **Recorded in:** ADR-089; `services/orchestrator/tests/test_orchestrator.py`, `test_resilience.py`.

### L-77 — The flag rule is exact on stored values; the stored confidence is rounded (2026-10-09)
- **What:** QA enforces `flagged == (confidence < τ)` on the stored `confidence`, which is rounded to 4 places, as the owner's brief for the sentiment checks wrote it. The data dictionary says the flag was decided before rounding. A probability between τ (0.8408407…) and the rounding step above it (0.84085) is not flagged but is stored as 0.8408, below τ, and would fail the rule. The window is about 9e-6 wide; none of the 7,521 stored predictions is in it (0 inconsistent), so no answer fails today.
- **Why accepted:** For now, with one reading kept. A ruling is needed on whether to keep the rule literal (false failures are possible but about one in 100,000 comments), or define consistency against the rounding interval of the stored value. QA has not chosen.
- **Recorded in:** ADR-090; data dictionary §6 "Sentiment answers" rule 5; `agent_qa/db.py` `sentiment_inconsistent_flags`.

**Update 2026-10-09 (ruled by the owner; resolved).** The check is strict unless `|stored confidence − τ| ≤ 0.00005` (half a rounding step of the 4-place value); inside that band either flag is accepted. Written into data dictionary §6 rule 5. QA's SQL (`sentiment_inconsistent_flags`) applies it with exact decimal arithmetic. Tests, both sides: `tests/integration/test_qa_sentiment_flag_band.py` (19 cases against the database: well below τ, inside the band, just outside it above τ, far above, and the edge itself at exactly 0.00005 on both sides; it needs only the loaded feedback, so it runs in CI). A Sprint 6 option is recorded: store the unrounded confidence, which would make the rule exact.

### L-78 — The real-data sentiment tests need the stored predictions, so they run locally only (2026-10-09)
- **What:** `tests/integration/test_qa_sentiment_agrees.py` compares QA with the real feedback server over the stored predictions of the current model version. CI loads the data but holds no predictions (they come from the heavy local backfill), so those tests skip there (a skip, not a failure, by design). The canned-database tests (`test_qa_sentiment_checks.py`, `test_qa_sentiment_service.py`) and the written rules run in CI. A new model version needs a fresh backfill before this suite means anything again.
- **Why accepted:** Backfilling in CI is about 15 minutes of CPU per run. The local run is recorded in ADR-090.
- **Recorded in:** ADR-090.

**Update 2026-10-09 (accepted).** A Sprint 5 item is added: run the real-data suites (`test_qa_sentiment_agrees.py` and the existing sentiment figures suites) on Cloud SQL after the predictions backfill there.

**Update 2026-10-14 (Z2a; owner-decided 2026-10-14; assistant-drafted):** status: **met locally; Cloud SQL parity proven by fingerprint and table hashes (`evals/results/sprint5_x/data_parity_cloud.json`, `sprint5_x.md`); the suites were not run on Cloud SQL because their fixtures need the superuser.** `tests/integration/conftest.py` (`live_database`) and `test_agent_sentiment_figures.py`, and two tests in `test_qa_sentiment_agrees.py`, connect as `POSTGRES_ADMIN_*`; running them against the evaluation database with superuser rights was refused on 2026-10-13. The plan for Z2b is in `sprint-log.md` (Z2a status, 2026-10-14).

### L-79 — Sentiment points the ADRs left to the agent's code are now written rules (2026-10-09)
- **What:** For these, ADR-066 to 068 are silent and the sentiment agent's code is the only implementation, so data dictionary §6 writes the code's behaviour as the rule and QA enforces it. They need the owner's confirmation: (1) *Latest bucket:* the trend compares the latest bucket that holds scored comments with the pooled earlier such buckets; an empty bucket is not listed, so a range ending in a month with no comment compares the last month that has any. (2) *Nothing to test:* when the pooled share is 0 or 1, or a side is empty, `z = 0` and `p = 1`. (3) *Which comments are quoted:* not specified and not checked; the agent quotes the highest-confidence ones first, and QA checks each is a valid in-set quote of the label asked for. The agent cannot ask for flagged-only comments, though the server can return them (QA's quote rule holds for them). (4) *Decline reasons:* the brief expected "the first reason that applies, in the agent's fixed order". The agent has no order: its parse reports one reason (`account`, `technician`, `service_type` or `other`) and the decline states it. A question that breaks two is declined for the one the model chose, and QA can only check that the text states the reported reason. Whether the chosen one was right is the advisory interpretation check's question. (5) A comment is a row with text; `feedback_text` is never null in the loaded data.
- **Why accepted:** None changes a result on the loaded data. Each is a written rule the owner can change.
- **Recorded in:** ADR-090; data dictionary §6 "Sentiment answers".

**Update 2026-10-09 (ruled by the owner).**
- (1) *Latest bucket:* accepted, "the latest non-empty bucket", with a new requirement: the answer names the compared buckets (`latest_bucket`, `earlier_buckets` and the text's "Latest month, 2026-08:" and "Earlier months, 2026-03 to 2026-07:") and QA checks the data and the text (`test_the_text_must_name_the_compared_buckets`).
- (2) *Nothing to test:* `z = 0`, `p = 1` accepted, and QA also requires the verdict "no clear change" (`nothing_to_test_must_be_no_clear_change`, `test_nothing_to_test_must_read_no_clear_change`).
- (3) *Quote selection is checked.* The agent does select by a fixed rule (the feedback server's `examples` query, taking the first three: among the comments in the set, of the asked label if any, highest stored confidence first, ties by the lowest `feedback_id`). It is written into §6 rule 7 and QA recomputes the list; the quoted ids must equal it (`quotes_not_the_top_by_confidence`). The agent cannot ask for flagged-only comments, so a flagged-only selection is valid comments that fail the rule (`test_flagged_only_quotes_are_valid_comments_but_not_the_selection_rule`). The agent's real selections equal the rule over three labels (`test_the_agents_selection_is_the_top_three_by_confidence_then_lowest_id`).
- (4) *Single decline reason* and (5) *a comment is a row with text*: accepted as written.

### L-80 — With no label asked, the quoted comments skew to the majority label (2026-10-09)
- **What:** When a question asks for example comments without naming a label, the agent quotes the three highest-confidence comments in the set (§6 rule 7). Confidence is highest for the majority label, which is usually positive, so the quotes can be three positive comments sitting under an answer whose trend says the negative share rose. They are real, in-set and correctly described, and QA verifies them, but they do not illustrate the trend. The same holds for a plain summary with examples asked for. A user who wants the complaints must ask for them by label.
- **Why accepted:** For now. The rule is fixed and enforced (L-79), and it is deterministic and checkable. Changing which comments are quoted is a change to §6 rule 7 and to QA's check together.
- **Fix (Sprint 6 option):** when no label is asked, quote one comment per leading label, or the trend's label (the negative one for a trend question), by the same confidence and tie rules, and update §6 rule 7 and QA's check with it.
- **Recorded in:** ADR-090; data dictionary §6 "Sentiment answers" rule 7; the Sprint 6 option in `docs/sprint-log.md`.

### L-81 — QA fails a correct answer whose headline figure is zero and stated in words (2026-10-10)
- **What:** Found by the fault-injection controls (ADR-091). A reporting answer with a zero denominator, for example "SLA compliance for Summit Distribution in the west last month" (no dispatched requests), reads "completed no dispatched requests ... so there is no SLA figure". QA's text check requires the numerator, 0, to appear as a headline number, the text never prints it, and the check fails with `text_misses_headline_number`. A figures-class failure is never retried (ADR-088), so a correct answer would reach the user as a degraded result with an escalation. 1 of 31 reporting controls (1 of 62 in all).
- **Why accepted:** Not accepted as correct behaviour; recorded as a defect found by the measurement. It is left unfixed in this PR so the first measurement stands as measured.
- **Fix:** a separate PR: require a stated number only when the figure is non-zero or the text prints it, with a test for every zero-denominator and zero-count form. That PR re-runs the same frozen catalogue and seed and reports a second measurement beside the first.
- **Recorded in:** ADR-091; `evals/results/qa_faults/2026-10-10/` (control `reporting:f09`).

**Update 2026-10-10 (resolved by ADR-092).** The headline-number requirement is removed; a zero-denominator answer's slots are what data dictionary §6 "Answer text" rule 3 lists, per metric. Measurement 2 (the same frozen catalogue and seed): control `reporting:f09` passes, 0 of 62 controls fail. Tests for each metric's zero case.

### L-82 — QA's text check compares sets of numbers and tolerates the neighbouring whole number (2026-10-10)
- **What:** The text check collects every number the text states and requires each to be one the answer supports and the headline numbers to appear. It does not check which figure is stated where, and a figure shown rounded to a whole number accepts floor, ceiling and round. A text that states one week's forecast as another week's, or a point one above its rounded value, passes. 4 of 9 forecast text-figure faults (F08) were missed: one by the rounding tolerance, three because the changed figure equalled another figure the answer states.
- **Why accepted:** For now; the data part is checked exactly, and a text that disagrees with it by one in a figure the answer also states elsewhere is rare. The reporting and sentiment text faults (R10, S12) were caught in 20 of 20.
- **Fix:** a separate PR: compare the text against the template's own rendering of the verified data part for forecasts (a positional check), or at least bind each stated figure to its week; keep the tolerance only where the rendering rounds. Re-run the frozen catalogue as a second measurement.
- **Recorded in:** ADR-091; `evals/results/qa_faults/2026-10-10/report.md` section 4.

**Update 2026-10-10 (resolved by ADR-092).** The text check is positional against §6's slot lists and rounding rules, with no tolerance. Measurement 2: the four forecast text-figure misses are caught (F08 9 of 9, was 5 of 9), and no case caught in measurement 1 passes. Measurement 2 is the same catalogue the fixes were designed against, so it shows the fixes work on those cases, not that QA catches unseen text faults.

### L-83 — QA cannot see a wrong point forecast (2026-10-10)
- **What:** QA checks that a forecast's weeks are the weeks asked for, that each interval contains its point, that a total is the sum, that served flags and shown errors equal the `volume_v2` manifest, the year-end caveat and the history. It does not recompute the model's numbers and has no seasonal baseline at answer time. The owner's fault 2 (the holiday weeks flattened, intervals and totals consistent) passed 0 of 6, with the owner's expected outcome `caught` and the reason given there, a baseline and backtest comparison, being an offline evaluation. This was stated in the catalogue before the run.
- **Why accepted:** By design (architecture §3): nobody can say a point forecast is the right number at answer time, and the shown error per band (ADR-071) is what a user gets. The backtest against a seasonal-naive baseline is in the evaluation record, not in each answer (FR-08).
- **Fix (owner decision, Sprint 5 or 6 option):** a plausibility check at answer time, for example each shown week within a stated band around the seasonal-naive value, with its own false-alarm rate measured. This is new scope and is not started.
- **Recorded in:** ADR-091; catalogue fault O2.

**Update 2026-10-10 (split, records only, ADR-092).**
- **(a) Altered forecast numbers in an answer.** This is what the owner's fault 2 mutation did: served points and ranges changed with arithmetic kept consistent. An answer-time check can catch it. The deployed model is deterministic, so QA could re-implement the prediction from the manifest's stored coefficients and require every served number to match. That checks the answer against the model and does not predict the future, so it is consistent with ADR-055. It is a build decision, not started: a Sprint 5 decision item (build it or not); the owner leans towards building it, as the condition for "QA verifies forecasts" meaning more than arithmetic.
- **(b) A model that does not know a holiday** (the story of fault 2). Answer-time QA cannot catch this; it belongs to offline evaluation. The holdout contains no November, and ADR-070's unvalidated year-end caveat applies.
- Fault 2 as injected is (a); its owner-stated reason is (b). Measurement 2 still passes it 0 of 6.

**Update 2026-10-11 (part (a) addressed, ADR-095).** QA now recomputes the weekly point, the 80% range's ends and the period total from the `volume_v2` parameter files, with its own pure-Python code, and requires each to match after the display rule. Measurement 3: owner fault 2 caught 6 of 6 (0 of 6 in measurements 1 and 2), 223 of 223 overall, no regression, 0 false alarms on 171 unmodified forecasts (2,320 numbers). It is evidence the fix works on the case it was designed from, not a catch rate (ADR-092, L-85). **Part (b) remains**: a model that does not know a holiday matches its own recompute and is judged offline; the 95% interval ends are not compared (L-87).

### L-84 — QA does not check how a small sample is presented (2026-10-10)
- **What:** The reporting text ranks groups of at least 20 cases and marks a single filtered figure under 20 as "too few to compare reliably" (ADR-073, ADR-086). QA checks the figures and the numbers in the text, not that marking or ranking rule. Re-rendering a grouped answer with no minimum so that a one-job technician heads the list (4a), and removing the marking from a single-technician answer with one case (4b), both passed (0 of 1 each; the cases are few because few base answers have a group or filter under 20). The owner's expected outcome was `known_gap`, and it held. The owner's threshold was 15; the system's is 20.
- **Why accepted:** The data part carries every group and its counts, so the information is present; the presentation rule is a template property. Both known gaps were expected.
- **Fix (option):** check the template's presentation rules in QA (the minimum for ranking, the marking) by rendering the verified data part and comparing; this is the same mechanism as the L-82 fix.
- **Recorded in:** ADR-091; catalogue faults O4a and O4b.

**Update 2026-10-10 (resolved by ADR-092).** §6 rule 4 states the small-sample marking and the ranking minimum (20, the rule's value, not a setting), and QA enforces both. Measurement 2: owner faults 4a and 4b, recorded as expectation `known_gap`, are caught (1 of 1 each; the expectation is not rewritten). The cases are few because few base answers have a group or filter under 20. The owner's threshold was 15 and the system's is 20.

### L-85 — The catch rate is measured on faults drafted by the assistant that built QA (2026-10-10)
- **What:** 47 of the catalogue's fault definitions were written by the assistant that wrote QA's checks and know what they test; the five owner-selected faults were co-written with it. The 98.2% (219 of 223) is therefore the share of faults the checks' author thought of that the checks catch, and an upper bound on what an independent reviewer would find. Where the owner chose the scenario (faults 1 to 5), one of the three expected-caught faults (2) was not caught, and the three expected known gaps held.
- **Why accepted:** There is one reviewer on this project and no second author. The disclosure is in the catalogue, ADR-091 and the results.
- **Fix (option):** a Sprint 5 or 6 set of faults written by the owner alone in plain words, applied by the same harness and reported separately.
- **Recorded in:** ADR-091; `evals/qa_faults/catalogue_v1.yaml`.

**Update 2026-10-10 (ADR-092, measurement 2).** Both measurements are upper bounds. Measurement 2 (223 of 223, 100%) re-ran the same catalogue after fixes that were designed from measurement 1's misses, so it is the weaker evidence of the two: it shows the fixes work on the cases they were written for. It is not an estimate of how QA does on faults nobody has thought of, and it does not add a blind fault. An owner-written set remains the Sprint 5 or 6 option above.

### L-86 — Evaluation sets are model-generated, same family as the system (2026-10-11)
- **What:** `routing_heldout_v1`, `fr03_fresh_v2`, `interp_fresh_v1` and `parse_filters_v1` were written by `gemini-3.8-flash` from a brief the assistant wrote and the owner reviewed (ADR-094). They are not owner-written and not blind to the assistant's framing of the domain; they are blind to the system. The generator and the system's models are both Gemini, so phrasing the family finds easy may inflate accuracy. Realistic phrasing from someone who has asked these questions is conceded (ADR-074); the golden set's 10 owner-written items remain the only owner-phrased evidence. Labels were not edited after generation; the owner skims the ambiguous labels and may drop an item, never fix one.
- **Why accepted:** Owner capacity in Q4 and two concurrent courses; the owner has paid access to no other vendor. A Claude-written set would repeat the contamination L-85 records.
- **Disclosure wording:** "In a real deployment, evaluation sets would come from real user questions and subject-matter experts. Here they were generated by an independent model under a written brief; the owner reviewed the brief and spot-checked the ambiguous labels."
- **Recorded in:** ADR-094; `evals/generated/`; R-16.

**Update 2026-10-11 (the skim and the freeze).** Two selection effects to disclose. (1) The owner's drops at the skim were made on persona grounds: a question a dispatcher or call-centre agent would ask, but not a senior operations leader with an overview of the business unit (the brief's stated asker). Labels were not changed, and the owner had not seen any system output. Five of the 31 skimmed rows were dropped (all `ambiguous`). Persona drops may remove the more granular, operational questions, which leaves the sets weighted toward broad leadership questions. (2) `interp_fresh_v1` keeps only items whose period wording `periods.py` recognises and whose dates match its resolution, and whose fields have a documented request representation (`pairs_plan.md`): of the 42 interpretation-category items excluded for their dates in the pool, 28 had wording it did not recognise, 12 had dates that did not match and 2 had a horizon that did not match. The set therefore skews toward the easier date phrasings and the plainer questions, and the interpretation gate's result on it is an upper bound on how the check does on the phrasings that were left out. Wrong pairs are single seeded mutations from a menu the assistant that built the system wrote, so they test the misparse kinds it anticipated, not misparses observed in use.


**Update 2026-10-13 (sets spent for blind use).** `routing_heldout_v1` and `golden_v2` were run on the deployed, frozen system on 2026-10-13 (Prompt X). Their items, the system's answers and the wrong or failed ones are now in `evals/results/` (`sprint5_failure_data.md`). Neither set is blind any more: a later prompt or code change that reads those results makes them development data, and a score on them after that must say so. The persona-drop and generated-set disclosures above apply to the routing figures reported from this run.

### L-87 — QA's forecast recompute leaves the 95% interval ends and a total interval unchecked (2026-10-11)
- **What:** ADR-095 compares each number a served forecast *shows* (the weekly point, the 80% range, the period total) with QA's own recomputation. The data part also carries `lo95` and `hi95`, which no text displays, so no display rule exists for them and the check does not compare them (they are listed as "unchecked" in the passing check's detail). A total interval is not served (ADR-072), so there is none to check. A change to a 95% end alone passes the recompute (it is still caught if it breaks the interval's ordering, `forecast_arithmetic`).
- **Why accepted:** The retro-change rule: no number is compared without a documented rule for it. The 95% ends are not shown to a user.
- **Fix (option):** the owner rules that the 95% ends are compared after the same whole-number rule as the 80% ends (one line in data dictionary §6 and one in the check).
- **Also recorded:** the recompute needs the six `volume_v2` parameter files at start-up (a read-only mount; they are not in git and not in QA's image). A deployed QA needs them provided; that is a deployment step, not done in this change.
- **Recorded in:** ADR-095; data dictionary §6, "Forecast recompute (QA)", rule 7.

**Update 2026-10-12 (closed for the 95% ends).** Owner ruling of 2026-10-11 applied: QA compares `lo95` and `hi95` by the same whole-number rule as the 80% ends (ADR-096; data dictionary §6, rule 4a). Clean check: 0 mismatches in 171 forecasts. The total interval is still not served, so there is still none to check; that part of this entry stands.

**Update 2026-10-12 (ADR-098):** the six `volume_v2` parameter files are committed and baked into the `agent_qa` and `mcp_volume` images, which ends the "deployed QA needs them provided" step above. QA still refuses to start on a missing or altered file. The clean check: 0 mismatches in 171 forecasts.

### L-88 — Invite-link access has no per-user identity and per-instance limits (2026-10-12)
- **What:** the gateway admits anyone who holds an unexpired, unrevoked invite link (ADR-097). A forwarded link grants access until it expires or is revoked; a session identifies an invite, not a person; there are no user accounts. The rate limits (exchange per IP, questions per session) and the global daily question cap are counted in process, so they are per instance and reset on a restart or scale-to-zero. The client IP rule for the exchange limit is not verified against Cloud Run's documentation (Prompt U). The authentication code is the project's own and has had no independent review.
- **Why accepted:** at this scale (a handful of invited reviewers, synthetic data) a revocable link with a 12-hour session is proportionate, and Google's quota is the backstop for spend. A federated identity was the portfolio-value choice and was ruled out by the grader's account situation.
- **Fix (option):** per-user accounts, or a shared-state counter (Redis or Firestore) for the limits, each a new decision.
- **Recorded in:** ADR-097; data dictionary §6, "Answer display (UI)".

**Update 2026-10-12 (Prompt U):** the client-IP rule was not confirmed against Cloud Run's documentation for a service without a load balancer: the container-contract and HTTPS-request pages are silent, the request-headers URL returned 404, and the one page that describes `X-Forwarded-For` is Cloud Functions'. The default (the last entry) and its test are unchanged; the exchange limit is keyed by a weaker, unverified rule until the runbook's step 5h observes it (note under ADR-097).

**Update 2026-10-14 (Z1, records reconciliation; owner-decided 2026-10-14; assistant-drafted):**
- *Client IP.* The 2026-10-13 probe (runbook step 5h) logged a `remoteIp` that was the caller's real address, not the spoofed value, which is consistent with the rule. **The evidence is Cloud Run's logged `remoteIp` only, so the rule is observed, not documented**; the gateway's own keying was not shown. It stays a stated limit.
- *The backstop.* "Google's quota is the backstop for spend" assumed the free 500 requests a day. The deployed key is paid (ADR-104), so the backstop is the prepaid balance and the gateway's caps (L-93, ADR-105).
- *Grader caps.* ADR-097 sized 50 questions a day and 15 an hour per invite for the owner's own use; ADR-105 relies on graders using the system. ADR-107 raises the hourly cap to 30 (applied in Z2, gateway configuration only) and keeps the daily cap at 50.

### L-89 — A database outage behind a healthy agent is a 502 error, not the degraded result (2026-10-12)
- **What:** found in the Prompt T local smoke. With the database container stopped while the agents and MCP servers stayed up, a reporting question returned the orchestrator's `502 agent_task_failed` ("The incidents query failed.", the agent's `tool_error` task failure), not the `outcome: degraded` result of FR-13 / ADR-088 with `escalate: true`. The degraded result is produced for a breaker trip, a transport failure, a timeout, the cost cap or a QA failure; a task the agent itself reports as failed with `tool_error` takes the error path. The gateway passes the sentence on ("The incidents query failed."), so the user sees an honest error, but with no follow-up flag and no warning wording of §6, "Answer display (UI)", rule 4.
- **Why accepted (for now):** changing which failures count as dependency failures is a change to ADR-088's behaviour and to the orchestrator's error contract, outside this work's brief. No answer is wrong and no unverified figure is shown.
- **Fix (option):** map the agent's `tool_error` (and QA's `qa_unavailable`) task failures to `DegradedResult("dependency", capability)`, with a test over a stopped database; a new ADR superseding the relevant part of ADR-088.
- **Observed once, one question** (the degraded smoke), not measured.

**Update 2026-10-12 (Prompt U):** the display no longer shows the agent's sentence. The gateway maps each known orchestrator error code (`agent_task_failed`, `agent_unavailable`, `unclear_question`, `invalid_range`, `rate_limited`, `daily_quota_exhausted`, `model_unavailable`, `internal_error`) to one fixed message, and anything unrecognised to one generic message; the orchestrator's `detail` is logged with the trace ID and never returned (data dictionary §6, "Answer display (UI)", rule 5). With the database stopped the browser check showed "The data service is unavailable right now. Please try again later." and no upstream text. This changes no answer and no `qa_status`. The limitation itself stands: the outage is still a 502 error without the follow-up flag.

### L-90 — The sentiment service cannot be deployed: its model weights have no path into an image (2026-10-12)
- **What:** `mcp_feedback` refuses to start without the 438 MB BERT weights, which are gitignored, and no Cloud Storage bucket exists to pull them from (ADR-062 was never built). The deployed system therefore answers a sentiment question with "The data service is unavailable right now." The forecast, reporting and QA paths are unaffected. Found by reading the start-up code while preparing the full deploy.
- **Why accepted (for now):** the choice between a bucket and a build-time pull (A) and stored predictions only (B) is the owner's, and (B) needs its own ADR. Neither is made here.
- **Fix (option):** (A) or (B) in R-19; either is a decision recorded in `docs/decisions-log.md` before its code.
- **Recorded in:** R-19; ADR-099; `deploy/RUNBOOK_V.md`.
- **Update 2026-10-12 (Prompt U2, ADR-100): resolved for serving.** Option (B) was chosen: deployed sentiment reads stored predictions only, so no weights or bucket are needed in the image. The limitation as written no longer holds once sentiment is deployed; see L-91 for what replaces it.

### L-91 — Deployed sentiment can't score new comments; the fixed dataset is fully pre-scored; the batch job for growing data is designed, not built (2026-10-12)
- **What:** in `stored_only` mode (ADR-100) the deployed `mcp_feedback` has no model. It answers only when every comment in the requested range has a stored prediction under the manifest's model version, and otherwise fails closed (`predictions_incomplete`, shown as "The data service is unavailable right now."). The local database is complete: 7,521 comments, 7,521 predictions, one model version, fingerprint `a340b82d8af178173afae34cb17bb7f2a1e3a944baa879321f34c4ac137e259f`, so every answer equals the lazy path's. A comment added after the backfill would make every range that contains it fail until the offline backfill is rerun.
- **Why accepted:** the dataset is fixed and synthetic, so an unscored comment can only mean a pipeline fault, and failing closed is the right behaviour for a fixed dataset. Required at this scale; the alternative (a bucket, a 438 MB pull in every build, 2 GiB of memory for a path that never runs) was rejected in ADR-100.
- **Fix (designed, not built):** a scheduled batch-scoring job (a Cloud Run Job, weights from a bucket) that scores new comments at ingest; questions read stored predictions only and disclose "based on N of M comments" instead of failing; a classifier upgrade is a re-scoring backfill with the model version on every row. Sprint 6 backlog item, portfolio value (ADR-100).
- **Recorded in:** ADR-100; R-19; `deploy/RUNBOOK_V.md`.

### L-58 update — the Sprint 5 gate on `fr03_fresh_v2` also failed; FR-03 stands (2026-10-12)
- **Status: standing, open.** `route_v6` (the one Sprint 5 revision) recognised 4 of 8 fresh ambiguous questions in at least 2 of 3 runs against the pre-registered 6 of 8, so criterion (c) failed; (a), (b1) and (b2) passed ((b2) at its boundary, 7.00 against a floor of 7.00). `route_v3` stays the default, ADR-075 stays not in effect, and there are no further attempts in Sprint 5. AMB-08, AMB-11, AMB-17 and AMB-18 were missed in 3 of 3 runs.
- **What changed in the picture:** `route_v6` is better than `route_v3` on the fresh set (11 of 16 in every run against 8 of 16), because `route_v3` never returns `ambiguous` (0 of 8). On the development sets it regressed on one item (s20, previously recognised) and over-flags one underspecified question (r06) in 3 of 3 runs; its 5 of 5 on `fr03_fresh_v1` is development material, not confirmation.
- **Consequence for the evaluation:** `golden_v2`'s G35 and the held-out ambiguous items fail under `route_v3` by design; Prompt X reports accuracy with and without them.
- **Recorded in:** ADR-101; `evals/sprint5_gates.md`; `evals/results/routing_fr03_fresh_v2_*_route_v{3,6}_*.json`.

### L-58 update — the third and final attempt (ADR-114) was a no-go; FR-03 is unmet (2026-10-22)
- **Status: standing, final.** ADR-113 allowed one attempt, with a method different from the prompt-only revisions. ADR-114 chose a higher thinking level for the routing call, with `route_v6` unchanged. Neither `medium` nor `high` met the pre-registered go criteria in development selection, so no blind set was generated and no gate ran. FR-03 is recorded as unmet, with no further attempt.
- **Key figures:**
  - `route_v6` at `minimal` already recognised 10 of 15 discriminating ambiguous items;
  - `medium` recognised 11 (+1, against a required +3);
  - `high` recognised 9.
  - Two items were missed at every level.
- **A finding, not a gate result:**
  - **On `routing_heldout_v1`, `route_v6` at `minimal` recognised 6 of 7 ambiguous items and got 42 of 43 non-ambiguous items right in each run.** `route_v3`, the deployed default, scored 0 of 7 and 38 of 43 on the same set (Prompt X). `route_v6` was committed on 2026-10-12, before that set was first run (2026-10-13), so it was not tuned on it.
  - Over all 15 fresh ambiguous items it recognised 10, below the 75% floor ADR-101 required.
  - This is reported as evidence that `route_v6` narrows the gap. It is not a reason to ship it: the pre-registered gate failed (ADR-101), and ADR-113 allows no further attempt.
- **For a real deployment (roadmap):** sets drawn from real user questions; a decline-safe clarification path; and the alternatives ADR-114 set aside (a separate ambiguity check, or a stronger model judged on a blind set from a different model family).
- **Recorded in:** ADR-114 (result note), ADR-115; `evals/fr03_v3/ledger.jsonl`; `evals/results/fr03_v3/`.

### L-58 update — `route_v6` becomes the default; FR-03 partly addressed, still not met (2026-10-22)
- **Status: standing; partly addressed.** ADR-116 makes `route_v6` the default router on held-out evidence. Over 15 fresh ambiguous questions it recognised 10, against 0 for `route_v3`. On the clear questions of the same two sets it was correct on 49 of 51 per run, against 46. The 75% floor (ADR-101) is not met, so FR-03 stays not met. About one ambiguous question in three is still best-fit routed.
- **Disclosure:** the comparison was decided after the results, not pre-registered (ADR-116).
- **Takes effect in the hardening redeploy, after `06` is submitted.** Until then the deployed system is the evaluated one, `route_v3`.
- **Recorded in:** ADR-116.

### L-58 update — `route_v6` is the deployed default; one live sighting (2026-10-28)
*2026-10-28 (6.5 deploy window; owner present; assistant-drafted.)*
- **Status: standing; FR-03 stays not met.** The 6.5 deploy window (build `0b96ca2a`, commit `b6fa907`) put `route_v6` into production: the routing log line read `prompt_version=route_v6` on every live question (12 of 12). The ambiguous example, "How's the Southeast doing?", returned `needs_clarification` with reason `intent_ambiguous`, after one model call, and asked the user to choose between reporting, sentiment and forecast. The clear examples routed as captioned (reporting, sentiment, forecast), and "What will revenue be next quarter?" went `out_of_scope` and was declined.
- **What this is not:** one ambiguous question, asked once. It is not a measurement. It changes neither the held-out result (10 of 15 ambiguous items recognised) nor ADR-101's 75% floor, and about one ambiguous question in three is still best-fit routed.
- **Recorded in:** `docs/deploy-window-log.md`, 2026-10-28 (phase 4, question 6).

### L-74 update — the Sprint 5 interpretation gate also failed; the check stays advisory (2026-10-12)
- **Status: standing.** `qa_interp_v3` met the catch criterion in run 1 (19 of 23 caught, the floor) and failed the false-reject criterion (3 of 23 against at most 1: reporting 1 of 10, forecast 1 of 7, sentiment 1 of 6). Runs 2 and 3 were not made, as pre-registered. `QA_INTERP_MODE` stays `advisory`, `qa_interp_v2` stays the shipped prompt, and `qa_interp_v3` is not shipped.
- **What v3 fixed on the used pairs (development, not held out):** false rejects 7 of 42 (v2) to 3 of 42; the two quarter-range pairs are now accepted. The three remaining false rejects are decline pairs (3 of 7), the known failure kind (L-92).
- **The check covers sentiment too** (ADR-090), which the earlier plan missed; the gate included it (6 pairs per role), and `enforce` would have applied to it.
- **Options still open, each a new decision with a new gate:** a higher thinking level for this one call, a stronger model (ADR-056's optional comparison), or computing the expected dates in code and giving the model only the comparison, which would also remove the quarter arithmetic.
- **Recorded in:** ADR-102; `evals/sprint5_gates.md`; `evals/results/qa_interp/2026-10-12/`.

### L-92 — The frozen interpretation gate does not test declines (2026-10-12)
- **What:** `interp_pairs_v1` holds 1 decline pair among its 23 correct pairs. The failure kind that sank `qa_interp_v1`, `v2` and `v3` is a correct decline (an unsupported metric or area, or a forecast the system cannot make) judged unfaithful, and the frozen gate cannot measure it. The A2 development diagnostic on the used pairs found 3 false rejects on 7 decline pairs under `qa_interp_v3` ("development diagnostic, not held-out").
- **Why accepted:** the sets were generated once and frozen (ADR-094), and a third attempt in Sprint 5 is not allowed. Disclosed in the pre-registration before the gate ran. At this scale a gate that cannot see its known failure kind is a real weakness, not a portfolio choice.
- **Fix (option):** a decline-heavy interpretation set (new, generated or owner-written, before any further prompt work), and a gate stated on it.
- **Recorded in:** ADR-102; `evals/sprint5_gates.md` (B2 scope limits).
- *2026-10-28 (6.5 deploy window; owner present; assistant-drafted.)* **One live sighting of the known failure kind.** On the deployed system, QA received the clarification for "How did Lina do on first-time fixes last quarter?" (two technicians match; trace `9e8cfcb1a053445dbd419e68f303d9a0`) as a decline, and its advisory `interpretation_matches_question` check failed (`faithful=False`, `differs_in=dates`), although the parsed period (2026-04-01 to 2026-06-30) is last quarter as of the data's date. The check is advisory, so QA's verdict was `pass`, the gateway logged `qa_status=verified`, and the UI showed no verification line (L-99). This is one sighting, not a measurement; it changes neither the gate result nor this limitation.

### L-93 — Per-process model-call caps are not a spend ceiling (2026-10-13)
- **What:** the deployed containers run on the paid key (ADR-104) with `LLM_MAX_REQUESTS=1500` and `LLM_MAX_SPEND_USD=1.00` per process. The client counts these in memory, so they reset when an instance restarts or scales to zero, and each service can run several instances. The bound that actually holds is the gateway's 50-question daily cap (ADR-097), about 350 calls a day, plus the paid project's prepaid balance and budget alert (R-02), which were not re-verified on 2026-10-13.
- **Why accepted:** at this scale the daily cap keeps worst-case spend to cents a day. A shared, persisted spend counter is a build with no payoff at that volume.
- **Fix (option):** a billing budget with a programmatic stop on the paid project, or a counter in the database shared by the five services.
- **Recorded in:** ADR-104.

### L-94 — The orchestrator's response carries no per-request cost or call count (2026-10-13)
- **What:** `AskResponse` has `outcome`, `route`, `qa_status` and the payloads, but no cost and no model-call count. Per-request cost exists only in the `ask answered` log line (`cost_usd`, a list-price estimate, L-71), and the number of model calls is not recorded per request at all. The Prompt X harness ledger read cost from logs by trace ID, one request behind, and bounded the model-call cap by the item count (186 requests x 5 calls = 930 of 1,000).
- **Why accepted:** the response contract is provisional and the evaluation needed a cap, not an audit trail. The paid key's prepaid balance (auto-reload off) was the hard backstop. Total logged cost was $0.1727 for 186 requests.
- **Fix (option):** return `cost_usd` and `model_calls` in `AskResponse` (or response headers) when the gateway contract is decided; a redeploy, so after the evaluation freeze.
- **Recorded in:** `evals/results/sprint5_x.md`, deviation 1.
- *2026-10-23:* fixed in the repo (`journey.model_calls`, `journey.cost_usd`); not yet deployed.
- *2026-10-28 (6.5 deploy window; owner present; assistant-drafted.)* **Resolved on deploy.** The response now carries `journey.model_calls` and `journey.cost_usd`, and the UI's chips ("Model calls", "Estimated cost") showed on the answers the owner checked (owner's observation: the journey was good on every answer that had one). The window ledger took each question's calls and cost from the orchestrator's log line, which §6 rule 10 says the journey's totals equal; the journey's own values were not read against the log in this window.

### L-95 — Golden findings the routing taxonomy does not hold (2026-10-13)
- **What:** the first `golden_v2` run (29 of 36 mechanical) shows five behaviours outside the routing taxonomy. (1) "district" is read as an unsupported breakdown (G03), where the item expects regions. (2) "through the end of next year" is read as calendar 2027, so the weeks from September to December 2026 are not shown and 8 weeks are returned (G07). (3) A forecast request wholly beyond the horizon returns outcome `answered` with an empty week list and a sentence saying so, not `not_available` (G28). (4) A qualifier the system cannot honour (fiber, G10) is not named in the answer; the text says "install requests" and nothing about fiber. (5) The sentiment trend's p-value is carried and shown to four places, so an oracle comparison at full precision fails it (G21).
- **Why accepted:** none of these produces a wrong figure; (1) to (3) are interpretation or labelling, (4) is the known stretch gap (L-56), and (5) is a display rule.
- **Fix (option):** owner rulings on (1) and (2) as product questions; a `golden_v3` with disclosure only if the owner wants the expectations changed. Not done in this run.
- **Recorded in:** `evals/results/sprint5_x/golden_assistant_reading.md`.

### L-96 — Future-tense questions on out-of-scope subjects are routed to forecast; the user still gets a decline (2026-10-13)
- **What:** `route_v3` sends a question about what will happen to the forecast specialist even when its subject is out of scope (ADR-053's reading of "what will happen"). The owner's 2026-10-11 clarification (ADR-094) says such a question is `out_of_scope`. In the Sprint 5 runs this affected NM-14 (technician staffing headcount, next 4 weeks) and NM-20 (dispatch calendar, tomorrow) in all 3 runs, 6 of the 15 `out-of-scope accepted` item-runs, and golden G08 (overtime labour spend this month). Each ended as `not_available`: the specialist declined and no figure was shown. The route label is wrong and the outcome is right; the decline text names only the forecast specialist's coverage, not all three domains. Past-tense out-of-scope subjects (OOS-01, OOS-03, OOS-14) reached reporting and were declined there, the other 9 item-runs.
- **Why accepted:** no wrong figure is shown, and the clarification postdates `route_v3`. A router revision needs its own pre-registered gate on a fresh set (ADR-094: the sets are spent), and FR-03 work already failed its gate in Sprint 5 (ADR-101).
- **Fix (option):** a router revision stating the owner's rule, gated on a new set that includes future-tense out-of-scope subjects; or a decline text that names all three domains whichever specialist declines.
- **Recorded in:** `evals/results/sprint5_failure_analysis.md` (pattern 2); `evals/results/sprint5_failure_data.md`.

### L-97 — The freeze test does not check the data-dictionary hash (2026-10-14)
- **What:** ADR-103 says `tests/unit/test_eval_freeze.py` "recomputes" the freeze record. It recomputes the prompt-file hashes, the default router and interpretation prompt, the mode flags (QA's two in `deploy/cloudrun/qa.yaml` and sentiment's scoring mode), the role models and thinking levels, and the retry cap, as-of date and timeouts. It does not recompute `data_dictionary_sha256` (`evals/freeze_s5.json`, the data dictionary's whole-file hash). Found by the 2026-10-14 gap audit and confirmed by reading the test. Checked by hand the same day: the file's LF-normalised hash equals the recorded `8fccfe6f...ae18`, so the record holds today.
- **Why accepted:** the dictionary has not changed since the freeze and a one-off check shows it; the record is otherwise as ADR-103 states it. Adding the check is code, outside a docs-only reconciliation.
- **Fix (option):** add a test that recomputes the hash with the same LF normalisation.
- **Recorded in:** ADR-103 (note 2026-10-14); `tests/unit/test_eval_freeze.py`.

### L-98 — Tool error text reaches the logs (2026-10-15)
- **What:** in session 1's failure path (trace `2e3dc32a…`), `agent_reporting`'s `task failed` line carries a `reason=` field holding the tool's error text, with the parsed dates and the dataset window, and `mcp_incidents` logs the tool's error message. No question text appears: the orchestrator's and the gateway's lines are clean (code, length, hash). This is narrower than ADR-108's and TS-15-D's "no exception message".
- **Why accepted:** Only one failure path was observed. In it no question wording was logged, though the logged dates were parsed from the question. Other tool errors may carry values taken from the question (for example a name the tool could not match); not checked. The data is synthetic. Accepted pending the owner's decision on stating it in 06 or fixing it (see the sprint log).
- **Fix (option):** log the code, length and hash in those two places too. It changes logs only, not answers, but needs a redeploy of two services.
- **Recorded in:** `evals/results/session1/2026-10-15/summary.md` ("Failure-path log codes seen live", "For the 05 revision"). Owner-decided 2026-10-15; assistant-drafted.

**Update 2026-10-16 (S6-A1; owner-decided 2026-10-16; assistant-drafted):** the owner chose option (a): `06` states the limit, and the fix is decided at the 6.5 brainstorm and deployed only after `06` is submitted (ADR-109). `docs/security-model.md` §5 ("Still logged, derived from the question", item 2) already documented that `invalid_range` failure text carries dates parsed from the question; L-98 widens that to `mcp_incidents`' logged tool error message.

*2026-10-22 (ADR-113 item 1; assistant-drafted.)* Fixed in the repo (PR: this branch); not yet deployed. It deploys in the hardening window after `06` is submitted.

*2026-10-28 (6.5 deploy window; owner present; assistant-drafted.)* **Deployed and confirmed live, on the path observed.** On the `invalid_range` question (trace `aa80741778ee4e779470683b628aa690`), `agent_reporting` logged `tool failed code=tool_error error_chars=138 error_sha=5dceb5fcfcc0` and `task failed code=invalid_range reason_chars=211 reason_sha=dcda0dfd4821`; the orchestrator's `agent task failed` line and the gateway's `ask refused upstream` line carried the same length and hash. None of these lines carried error text. Only this one tool-error path was triggered in the window; other tool errors, which might carry values taken from the question, were not.

### L-99 — The verification line shows on a clarification (2026-10-15)
- **What:** a `needs_clarification` page (the "Priya" question, two technicians matched) shows "Figures checked for the request as interpreted", although no figures were produced. The display claims a check with nothing to check.
- **Why accepted:** the page also explains the clarification and lists both matches, so no wrong figure is shown; the cost is a misleading line.
- **Fix (option):** do not render the verification line when the outcome has no figures.
- **Recorded in:** `evals/results/session1/2026-10-15/summary.md` ("For the 05 revision"); `run-notes.md` (step 3.6). Owner-decided 2026-10-15; assistant-drafted.

*2026-10-22 (ADR-113 item 1; assistant-drafted.)* Fixed in the repo (PR: this branch); not yet deployed. It deploys in the hardening window after `06` is submitted.

*2026-10-28 (6.5 deploy window; owner present; assistant-drafted.)* **Deployed and confirmed live.** "How's the Southeast doing?" (`intent_ambiguous`) and "How did Lina do on first-time fixes last quarter?" (two technicians match) each showed a clarification with no verification line in the owner's browser. The fix is display-only: the response data for the second still carries `qa_status=verified` and QA ran on it (see the L-92 update of the same date).

### L-100 — A backwards date range is silently reordered (2026-10-15)
- **What:** "August 2026 to January 2026" was parsed as 2026-01-01 to 2026-08-31 and was then refused on the dataset window (422 `invalid_range`). The user is not told their range was backwards.
- **Why accepted:** this is an interpretation behaviour and any fix changes answers, so it is a 6.5 candidate (ADR-106), not a Sprint 6 change. In this case the request was refused, not answered with figures for a range the user did not write.
- **Fix (option):** have the parser reject, or ask about, an end before the start, gated like other interpretation changes.
- **Recorded in:** `evals/results/session1/2026-10-15/summary.md` (failure path); `run-notes.md` (step 4.1). Owner-decided 2026-10-15; assistant-drafted.

### L-101 — Independent scaling is not demonstrated on the deployed system (2026-10-15)
- **What:** under TS-18-C, six concurrent reporting questions at concurrency 8 per instance were served by one instance (`ops-reporting` 1 instance, `ops-forecast` 1). The design (separate services, max 2 instances each) allows independent scaling, but no deployed run has shown it.
- **Why accepted:** Scaling is Cloud Run behaviour set by the services' concurrency and maximum instances, and it does not affect answer correctness. Demonstrating it needs more than 8 concurrent questions to one service, a large share of the daily cap of 50, for portfolio evidence rather than a requirement at this scale. The TS-18-C clause that asked for it is classed by the owner as a 05 criterion flaw.
- **Fix (option):** a load test above 8 concurrent, sized against the daily cap of 50.
- **Recorded in:** `evals/results/session1/2026-10-15/summary.md` (TS-18-C); `run-notes.md` (step 3.7). Owner-decided 2026-10-15; assistant-drafted.

### L-102 — The evaluation runs on synthetic, generated data (2026-10-18)
- **What:** The database, the feedback corpus and the evaluation sets are all generated. Every figure in the report measures behaviour on that data, not on real field-service operations. L-12, L-13 and L-23 cover parts of it: sentiment labels are defined by a written specification, the SLA-incident relationship is planted, and sentiment accuracy is agreement with that specification.
- **Why accepted:** There is no real dispatch data at this scale, and the project is a synthetic-data capstone by design.
- **Fix (option):** none inside the project. A real deployment would be evaluated on real data and real user questions.
- **Recorded in:** `docs/data-dictionary.md`; L-01, L-12, L-13, L-23, L-86. Owner-decided 2026-10-18; assistant-drafted.

### L-103 — The golden run and owner session 1 are single runs, not k=3 (2026-10-18)
- **What:** The golden run (36 items, `evals/results/golden_v2/2026-10-13/`) and owner verification session 1 (`evals/results/session1/2026-10-15/`, "single run, decision 3") ran once each. The routing evaluations are k=3 (held-out routing, range 38 to 38). A single run carries no estimate of run-to-run variance (L-17), so a one-item difference on the golden set is within noise.
- **Why accepted:** The golden run's cost and the session's cap and time limit. The spent sets cannot be rerun blind.
- **Fix (option):** report the golden set at k=3 on a new owner-written set.
- **Recorded in:** `evals/results/sprint5_x.md`; `evals/results/session1/2026-10-15/summary.md`. Owner-decided 2026-10-18; assistant-drafted.

### L-104 — The runtime sends a deprecated sampling parameter; one evaluated model has been retired (2026-10-22)
- **What:** The runtime model client sends `temperature=0.0` on every call (`packages/llm/src/llm/transport.py`; default in `config.py`). Google's notice of 2026-10-22 says sampling parameters (`temperature`, `top_p`, `top_k`) have had no effect since Gemini 3.6 Flash and will return an error on upcoming models. The system is pinned to `gemini-3.5-flash-lite` and `google-genai==2.25.0` (ADR-048, ADR-049), where the parameter is honoured. Separately, `gemini-3.7-flash`, used only in ADR-049's seed-set comparison, is deprecated and its endpoint now routes to `gemini-3.8-flash`, so the two result files from that comparison are records that can't be re-run as measured.
- **Why accepted:**
  - The evaluated system (ADR-103) includes temperature 0.0 on Flash-Lite, so changing it would change what the report describes.
  - No runtime role uses 3.7 Flash.
  - `thinking_budget`, `top_p` and `top_k` are never sent (the project uses `thinking_level`, ADR-052).
  - Google's deprecations page, read 2026-10-22, lists no shutdown date for `gemini-3.5-flash-lite` or `gemini-3.8-flash`.
- **Fix (option):** send `temperature` only when it is explicitly configured, or refuse it at startup for models that ignore it (like ADR-052's thinking-level check), as a new decision. **This must be done before any role moves to a model newer than 3.5 Flash-Lite.**
- **Recorded in:** ADR-048 (item 5), ADR-049, ADR-052, ADR-103; Google notices of 2026-10-22; https://ai.google.dev/gemini-api/docs/deprecations (read 2026-10-22).
- *2026-10-28 (6.5 deploy window; assistant-drafted.)* Google's deprecations page, read again on 2026-10-28 (the table row, fetched with `curl`): `gemini-3.5-flash-lite | July 21, 2026 | No shutdown date announced`. No shutdown date before 2026-12-12 (R-15). The deployed routing line reads `model=gemini-3.5-flash-lite`, and `temperature=0.0` is still sent. Standing.

### L-105 — The gateway sends no cache headers and builds redirects with the wrong scheme; a deploy does not reset a manual traffic pin (2026-10-28)
- **What:** three defects found in the 6.5 deploy window, in the serving and deploy path. None changes an answer.
  - **No `Cache-Control` on the gateway's HTML, JS or CSS** (`ETag` and `Last-Modified` only). A browser may reuse a page it fetched earlier, so a returning viewer can see the pre-deploy UI until a hard reload. The owner's first view of the new build was the old UI (no notice, no examples, no other pages). The cause is inferred from the headers, not observed in the owner's browser.
  - **The gateway's `/faq` redirect (307) has `Location: http://…/faq/`**, the wrong scheme. Cloud Run's front end answers the plain-`http` request with a 302 to `https`, and the owner's browser ended on `https`, so the effect was nil in this check.
  - **A manual `update-traffic --to-revisions` pins traffic to a named revision,** and the deploy step (`deploy/deploy_service.py`) sends a PATCH with no `traffic` block. `RUNBOOK_V.md` assumes traffic follows the latest revision. Whether the PATCH resets a pin was not tested (the window avoided the question). If it does not, a pipeline deploy after any rollback or fault test puts its new revision at 0%, and the pipeline's verify step would fail the build.
- **Why accepted:** the first is a stale view for a returning viewer, cured by a reload; the second had no effect on the browser; the third was handled in the window by a clean revision and an unpin, verified read-only (`docs/deploy-window-log.md`, 2026-10-28, phase 5). Nothing merges during a deploy window, so the fix waits for the next PR.
- **Fix (option):** gateway: `Cache-Control` on HTML and forwarded-proto trust, one PR before Window B. The same PR adds an explicit "latest revision, 100%" `traffic` block to every `deploy/cloudrun/*.yaml`, with a test that every definition carries it, so a pipeline deploy resets any manual pin; hashed `/_next/static/` files can stay cacheable.
- **Recorded in:** `docs/deploy-window-log.md`, 2026-10-28 (phase 4 step 1; phase 5); `deploy/RUNBOOK_V.md`, Rollback. Owner-decided 2026-10-28; assistant-drafted.
