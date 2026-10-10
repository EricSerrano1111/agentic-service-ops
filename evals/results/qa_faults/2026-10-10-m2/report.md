# QA fault-injection results

Catalogue v1, seed 20261010, run started 2026-10-10T18:50:19Z. QA ran: True.

## 1. Clean base answers and controls

| agent | answers | declines | controls run | false alarms |
|---|---|---|---|---|
| reporting | 23 | 8 | 31 | 0 |
| forecast | 11 | 4 | 15 | 0 |
| sentiment | 13 | 3 | 16 | 0 |

Excluded (neither an answer nor a decline): 0.

## 2. Overall catch rate (assistant-drafted faults expected to be caught)

Classes: injected and database. Rating contradictions, consistent misparses and the owner-selected faults are reported in their own sections.
| agent | faults | cases | caught (any check) | caught by an expected check |
|---|---|---|---|---|
| reporting | 14 | 104 | 104/104 = 100.0% (95% Wilson 96.4-100.0%) | 104/104 = 100.0% (95% Wilson 96.4-100.0%) |
| forecast | 8 | 43 | 43/43 = 100.0% (95% Wilson 91.8-100.0%) | 43/43 = 100.0% (95% Wilson 91.8-100.0%) |
| sentiment | 12 | 76 | 76/76 = 100.0% (95% Wilson 95.2-100.0%) | 76/76 = 100.0% (95% Wilson 95.2-100.0%) |
| total | 34 | 223 | 223/223 = 100.0% (95% Wilson 98.3-100.0%) | 223/223 = 100.0% (95% Wilson 98.3-100.0%) |

## 3. Per fault

| id | class | expected | fault | cases | caught | by expected check | checks that fired | skipped |
|---|---|---|---|---|---|---|---|---|
| R01 | injected | caught | a count off by 1 | 10 | 10 | 10 | figures_match_database x10 | 0 |
| R02 | injected | caught | a rate's last digit changed | 10 | 10 | 10 | figures_match_database x10 | 0 |
| R03 | injected | caught | a denominator off by 1 | 10 | 10 | 10 | figures_match_database x10 | 0 |
| R04 | injected | caught | one group dropped | 9 | 9 | 9 | figures_match_database x9 | 0 |
| R05 | injected | caught | two groups' order swapped | 9 | 9 | 9 | figures_match_database x9 | 0 |
| R06 | injected | caught | the full group count wrong | 9 | 9 | 9 | figures_match_database x9 | 0 |
| R07 | injected | caught | a 'too few' flag flipped | 2 | 2 | 2 | figures_match_database x2 | 0 |
| R08 | injected | caught | a filter silently dropped (figures from the unfiltered set while the request still names the filter) | 10 | 10 | 10 | figures_match_database x10 | 0 |
| R09 | injected | caught | a range shifted by a month in the data only | 10 | 10 | 10 | range_matches_request x10 | 0 |
| R10 | injected | caught | a figure in the text that differs from the data part | 10 | 10 | 10 | text_matches_data x10 | 0 |
| R11 | injected | caught | a decline that carries a figure | 8 | 8 | 8 | decline_no_figures x8 | 0 |
| R12 | injected | caught | a decline stating the wrong reason (not the first that applies) | 3 | 3 | 3 | decline_matches_reason x3 | 0 |
| R13 | injected | caught | a Fisher p-value changed | 2 | 2 | 2 | figures_match_database x2 | 0 |
| R14 | injected | caught | a standout flag flipped | 2 | 2 | 2 | figures_match_database x2 | 0 |
| F01 | injected | caught | numbers shown for an unserved slice-band | 4 | 4 | 4 | serving_matches_manifest x4, forecast_arithmetic x3 | 7 |
| F02 | injected | caught | a shown error that differs from the manifest | 10 | 10 | 10 | serving_matches_manifest x10 | 1 |
| F03 | injected | caught | an interval that doesn't contain its point | 9 | 9 | 9 | forecast_arithmetic x9 | 2 |
| F04 | injected | caught | a total that isn't the sum of its weeks | 6 | 6 | 6 | answer_malformed x6 | 0 |
| F05 | injected | caught | a horizon over 26 weeks | 2 | 2 | 2 | weeks_match_request x2 | 0 |
| F06 | injected | caught | a history week changed | 1 | 1 | 1 | history_matches_database x1 | 0 |
| F07 | injected | caught | the year-end caveat removed where it is required | 2 | 2 | 2 | year_end_caveat x2 | 0 |
| F08 | injected | caught | a text figure that differs from the data part | 9 | 9 | 9 | text_matches_data x9 | 2 |
| S01 | injected | caught | a label count changed | 10 | 10 | 10 | figures_match_database x10 | 0 |
| S02 | injected | caught | a share changed | 10 | 10 | 10 | figures_match_database x10 | 0 |
| S03 | injected | caught | the flagged count changed | 10 | 10 | 10 | figures_match_database x10 | 0 |
| S04 | database | caught | one stored prediction's flag inconsistent with tau outside the band | 10 | 10 | 10 | flags_consistent x10 | 0 |
| S05 | injected | caught | a trend verdict flipped | 4 | 4 | 4 | trend_matches x4 | 1 |
| S06 | injected | caught | a trend p-value changed | 4 | 4 | 4 | trend_matches x4 | 1 |
| S07 | injected | caught | a compared bucket mislabelled | 4 | 4 | 4 | trend_matches x4 | 1 |
| S08 | injected | caught | a quote's text changed by one word | 2 | 2 | 2 | quotes_valid x2 | 0 |
| S09 | injected | caught | a quote from another region | 1 | 1 | 1 | quotes_valid x1 | 0 |
| S10 | injected | caught | a quote that isn't in the rule's top 3 | 1 | 1 | 1 | quotes_valid x1 | 1 |
| S11 | database | caught | complete set to true on a partial answer | 10 | 10 | 10 | coverage_matches_database x10 | 0 |
| S12 | injected | caught | a text figure that differs from the data part | 10 | 10 | 10 | text_matches_data x10 | 0 |
| K05 | rating | per_rule | rating contradictions at 0.5% of the covered set | 10 | 0 | 0 | - | 2 |
| K10 | rating | per_rule | rating contradictions at 1% | 10 | 0 | 0 | - | 3 |
| K20 | rating | per_rule | rating contradictions at 2% | 10 | 1 | 1 | rating_contradiction x1 | 2 |
| K40 | rating | per_rule | rating contradictions at 4% | 10 | 8 | 8 | rating_contradiction x8 | 2 |
| K80 | rating | per_rule | rating contradictions at 8% | 10 | 10 | 10 | rating_contradiction x10 | 3 |
| MR1 | misparse | known_gap | a wrong month | 10 | 0 | 0 | - | 0 |
| MR2 | misparse | known_gap | a wrong region | 10 | 0 | 0 | - | 0 |
| MR3 | misparse | known_gap | a wrong metric | 10 | 0 | 0 | - | 0 |
| MF1 | misparse | known_gap | a wrong month | 9 | 0 | 0 | - | 0 |
| MF2 | misparse | known_gap | a wrong slice | 10 | 0 | 0 | - | 0 |
| MS1 | misparse | known_gap | a wrong month | 10 | 0 | 0 | - | 0 |
| MS2 | misparse | known_gap | a wrong region | 10 | 0 | 0 | - | 0 |
| MS3 | misparse | known_gap | a wrong label | 2 | 0 | 0 | - | 0 |
| O1a | owner | caught | 1a (primary, owner's ruling 2026-10-10): repeat links ignored, so repeats never count as failures and the rate is inflated | 4 | 4 | 4 | figures_match_database x4 | 0 |
| O1b | owner | caught | 1b (owner's ruling): the literal definition, completed jobs with no linked incident | 4 | 4 | 4 | figures_match_database x4 | 0 |
| O2 | owner | caught | 2 (as proposed): the forecast numbers for the holiday weeks are wrong, with intervals and totals internally consistent | 6 | 0 | 0 | - | 1 |
| O3a | owner | caught | 3a (owner's ruling): flip every non-positive prediction on a 1-2 star comment to positive | 10 | 10 | 10 | rating_contradiction x10 | 2 |
| O3b | owner | caught | 3b (owner's ruling): reach about 88% positive by also flipping non-positive predictions on 3-star and unrated comments | 10 | 10 | 10 | rating_contradiction x10 | 2 |
| O4a | owner | known_gap | 4a (as proposed): the grouped text is re-rendered with no minimum, so a group under 20 cases is ranked and the 'left out' sentence is gone | 1 | 1 | 1 | text_matches_data x1 | 2 |
| O4b | owner | known_gap | 4b (as proposed): the 'too few to compare reliably' marking removed from a real single-technician answer where n < 20 | 1 | 1 | 1 | text_matches_data x1 | 0 |
| O5 | owner | known_gap | 5 (as proposed): a consistent misparse, the range widened to the trailing quarter instead of the implied recent window | 10 | 0 | 0 | - | 0 |

## 4. Misses (caught-expected cases that passed)

| case | authorship | question | checks that ran (all passed) | note |
|---|---|---|---|---|
| O2|owner:A2 | owner-selected, AI-co-written | What technician capacity do we need across all regions for the next 4  | weeks_match_request, forecast_arithmetic, serving_matches_manifest, year_end_caveat, history_matches_database, text_matches_data | {"flattened": ["2026-11-23", "2026-11-30"], "level": 171.97} |
| O2|forecast:f02 | owner-selected, AI-co-written | Forecast total requests for the next 8 weeks, compared with recent wee | weeks_match_request, forecast_arithmetic, serving_matches_manifest, year_end_caveat, history_matches_database, text_matches_data | {"flattened": ["2026-10-12", "2026-10-19"], "level": 161.97} |
| O2|forecast:f07 | owner-selected, AI-co-written | What will volume be next year? | weeks_match_request, forecast_arithmetic, serving_matches_manifest, year_end_caveat, history_matches_database, text_matches_data | {"flattened": ["2027-02-15", "2027-02-22"], "level": 134.45} |
| O2|forecast:f13 | owner-selected, AI-co-written | How many requests should we expect in January? | weeks_match_request, forecast_arithmetic, serving_matches_manifest, year_end_caveat, history_matches_database, text_matches_data | {"flattened": ["2027-01-18", "2027-01-25"], "level": 137.43} |
| O2|forecast:f01 | owner-selected, AI-co-written | What will request volume look like next month? | weeks_match_request, forecast_arithmetic, serving_matches_manifest, year_end_caveat, history_matches_database, text_matches_data | {"flattened": ["2026-09-21", "2026-09-28"], "level": 157.84} |
| O2|forecast:f03 | owner-selected, AI-co-written | How busy will December be? | weeks_match_request, forecast_arithmetic, serving_matches_manifest, year_end_caveat, history_matches_database, text_matches_data | {"flattened": ["2026-12-21", "2026-12-28"], "level": 153.4} |

## 5. False alarms (failed controls)

| agent | failed controls | controls run |
|---|---|---|
| reporting | 0 | 31 |
| forecast | 0 | 15 |
| sentiment | 0 | 16 |

## 6. Rating sensitivity against the pre-registered rule (ADR-087)

| level | rate | cases | covered n | rule predicts caught | QA caught | QA agrees with the rule |
|---|---|---|---|---|---|---|
| K05 | 0.005 | 10 | 122-1055 | 0/10 | 0/10 | 10/10 |
| K10 | 0.01 | 10 | 122-1055 | 0/10 | 0/10 | 10/10 |
| K20 | 0.02 | 10 | 122-1055 | 1/10 | 1/10 | 10/10 |
| K40 | 0.04 | 10 | 122-1055 | 8/10 | 8/10 | 10/10 |
| K80 | 0.08 | 10 | 122-1055 | 10/10 | 10/10 | 10/10 |

## 7. Known gaps: consistent misparse (interpretation is advisory, L-74)

| agent | cases | caught | cases with an advisory logged |
|---|---|---|---|
| reporting | 30 | 0/30 = 0.0% (95% Wilson 0.0-11.4%) | 0 |
| forecast | 19 | 0/19 = 0.0% (95% Wilson 0.0-16.8%) | 0 |
| sentiment | 22 | 0/22 = 0.0% (95% Wilson 0.0-14.9%) | 0 |

The interpretation client in this harness is a fake that always says `faithful`, so an advisory can never be logged here; the reading QA would have shown a real interpretation call is kept per case in results.json (`interpretation_reading`).

## 8. Owner-selected, AI-co-written faults (reported separately)

| id | variant | owner's expected | cases | caught | owner's exact question: verdict | checks that fired there |
|---|---|---|---|---|---|---|
| O1a | 1a (primary, owner's ruling 2026-10-10): repeat links ignored, so repeats never count as failures and the rate is inflated | caught | 4 | 4 | fail | figures_match_database |
| O1b | 1b (owner's ruling): the literal definition, completed jobs with no linked incident | caught | 4 | 4 | fail | figures_match_database |
| O2 | 2 (as proposed): the forecast numbers for the holiday weeks are wrong, with intervals and totals internally consistent | caught | 6 | 0 | pass | - |
| O3a | 3a (owner's ruling): flip every non-positive prediction on a 1-2 star comment to positive | caught | 10 | 10 | fail | rating_contradiction |
| O3b | 3b (owner's ruling): reach about 88% positive by also flipping non-positive predictions on 3-star and unrated comments | caught | 10 | 10 | fail | rating_contradiction |
| O4a | 4a (as proposed): the grouped text is re-rendered with no minimum, so a group under 20 cases is ranked and the 'left out' sentence is gone | known_gap | 1 | 1 | fail | text_matches_data |
| O4b | 4b (as proposed): the 'too few to compare reliably' marking removed from a real single-technician answer where n < 20 | known_gap | 1 | 1 | fail | text_matches_data |
| O5 | 5 (as proposed): a consistent misparse, the range widened to the trailing quarter instead of the implied recent window | known_gap | 10 | 0 | pass | - |

- O1a|owner:A1: {"rate": "1.0000"} rating: None

- O1b|owner:A1: {"rate": "0.8926"} rating: None

- O2|owner:A2: {"flattened": ["2026-11-23", "2026-11-30"], "level": 171.97} rating: None

- O3a|owner:A3: {"flipped": 23, "low_star_flipped": 23, "positive_share": "0.6471", "covered_n": 84, "contradictions": 23, "contradiction_rate": 0.2738, "reached_88": false} rating: n=84, x=23, p0=0.01: fail

- O3b|owner:A3: {"flipped": 55, "low_star_flipped": 23, "positive_share": "0.8824", "covered_n": 107, "contradictions": 23, "contradiction_rate": 0.215, "reached_88": true} rating: n=107, x=23, p0=0.01: fail

- O4a|owner:A4a: {"groups_under_20": 12} rating: None

- O4b|owner:A4b: {} rating: None

- O5|owner:A5: {"wrong_request": {"region": "west", "start": "2026-06-02", "end": "2026-08-30", "bucket": "month", "want_trend": true}, "implied_window": ["2026-08-17", "2026-08-30"]} rating: n=69, x=0, p0=0.01: pass

- O5|owner:A3: {"wrong_request": {"region": "west", "start": "2026-06-02", "end": "2026-08-30", "bucket": "quarter", "want_trend": false, "want_examples": false}, "implied_window": ["2026-08-17", "2026-08-30"]} rating: n=69, x=0, p0=0.01: pass

## 9. Database integrity

Database-fault cases: 90; unchanged after rollback: 90. Whole run: before {'sentiment_predictions': 7521, 'service_feedback': 7521, 'service_requests': 20230, 'predictions_md5': '4f40e1929e5c9d7dc865aca893ecb665'}, after {'sentiment_predictions': 7521, 'service_feedback': 7521, 'service_requests': 20230, 'predictions_md5': '4f40e1929e5c9d7dc865aca893ecb665'}, unchanged True.

## 10. Applicability and skipped cases

| fault | applicable base answers | cases run | skipped (reason) |
|---|---|---|---|
| R01 | 23 | 10 | - |
| R02 | 16 | 10 | - |
| R03 | 16 | 10 | - |
| R04 | 9 | 9 | - |
| R05 | 9 | 9 | - |
| R06 | 9 | 9 | - |
| R07 | 2 | 2 | - |
| R08 | 12 | 10 | - |
| R09 | 23 | 10 | - |
| R10 | 23 | 10 | - |
| R11 | 8 | 8 | - |
| R12 | 3 | 3 | - |
| R13 | 2 | 2 | - |
| R14 | 2 | 2 | - |
| F01 | 11 | 4 | 7x every shown week is served |
| F02 | 11 | 10 | 1x no band is shown |
| F03 | 11 | 9 | 2x no served week |
| F04 | 6 | 6 | - |
| F05 | 2 | 2 | - |
| F06 | 1 | 1 | - |
| F07 | 2 | 2 | - |
| F08 | 11 | 9 | 2x no served week |
| S01 | 13 | 10 | - |
| S02 | 13 | 10 | - |
| S03 | 13 | 10 | - |
| S04 | 13 | 10 | - |
| S05 | 5 | 4 | 1x no trend comparison |
| S06 | 5 | 4 | 1x no p-value |
| S07 | 5 | 4 | 1x no comparison to mislabel |
| S08 | 2 | 2 | - |
| S09 | 1 | 1 | - |
| S10 | 2 | 1 | 1x no fourth comment in the set |
| S11 | 13 | 10 | - |
| S12 | 13 | 10 | - |
| K05 | 13 | 10 | 1x covered n = 76 is under 100; 1x covered n = 28 is under 100 |
| K10 | 13 | 10 | 1x covered n = 5 is under 100; 1x covered n = 28 is under 100; 1x covered n = 76 is under 100 |
| K20 | 13 | 10 | 1x covered n = 28 is under 100; 1x covered n = 76 is under 100 |
| K40 | 13 | 10 | 1x covered n = 5 is under 100; 1x covered n = 28 is under 100 |
| K80 | 13 | 10 | 1x covered n = 5 is under 100; 1x covered n = 28 is under 100; 1x covered n = 76 is under 100 |
| MR1 | 23 | 10 | - |
| MR2 | 20 | 10 | - |
| MR3 | 21 | 10 | - |
| MF1 | 9 | 9 | - |
| MF2 | 11 | 10 | - |
| MS1 | 12 | 10 | - |
| MS2 | 13 | 10 | - |
| MS3 | 2 | 2 | - |
| O1a | 4 | 4 | - |
| O1b | 4 | 4 | - |
| O2 | 7 | 6 | 1x fewer than three served weeks |
| O3a | 13 | 10 | 1x only 45 scored comments in the set; 1x only 9 scored comments in the set |
| O3b | 13 | 10 | 1x only 9 scored comments in the set; 1x only 45 scored comments in the set |
| O4a | 3 | 1 | 2x no group under 20 cases |
| O4b | 1 | 1 | - |
| O5 | 13 | 10 | - |

## 11. Not blind

Most of this catalogue (R, F, S, K, M) was written by the assistant that built QA, which knows what QA checks. The owner-selected faults (O) were chosen by the owner and co-written with the assistant; they are not independent of the project's design the way faults the owner wrote alone would be.

# Measurement 1 against measurement 2

The same frozen catalogue and seed (`catalogue_v1.yaml`, `faults.py`, `generate.py`, `report_format.md`, seed 20261010) against QA before and after the fixes of ADR-092. **The fixes were designed after seeing measurement 1's misses.** Measurement 2 shows they work on those cases; it is not new evidence that QA catches faults it has not seen. Both measurements are upper bounds (L-85).

Cases run in both: 390 of 390 and 390.

## Assistant-drafted faults expected caught: per agent

| agent | cases | m1 caught | m2 caught |
|---|---|---|---|
| reporting | 104 | 104 | 104 |
| forecast | 43 | 39 | 43 |
| sentiment | 76 | 76 | 76 |
| total | 223 | 219 | 223 |

## Per fault

| fault | cases | m1 caught | m2 caught | m2 checks that fired |
|---|---|---|---|---|
| R01 | 10 | 10 | 10 | figures_match_database x10 |
| R02 | 10 | 10 | 10 | figures_match_database x10 |
| R03 | 10 | 10 | 10 | figures_match_database x10 |
| R04 | 9 | 9 | 9 | figures_match_database x9 |
| R05 | 9 | 9 | 9 | figures_match_database x9 |
| R06 | 9 | 9 | 9 | figures_match_database x9 |
| R07 | 2 | 2 | 2 | figures_match_database x2 |
| R08 | 10 | 10 | 10 | figures_match_database x10 |
| R09 | 10 | 10 | 10 | range_matches_request x10 |
| R10 | 10 | 10 | 10 | text_matches_data x10 |
| R11 | 8 | 8 | 8 | decline_no_figures x8 |
| R12 | 3 | 3 | 3 | decline_matches_reason x3 |
| R13 | 2 | 2 | 2 | figures_match_database x2 |
| R14 | 2 | 2 | 2 | figures_match_database x2 |
| F01 | 4 | 4 | 4 | serving_matches_manifest x4, forecast_arithmetic x3 |
| F02 | 10 | 10 | 10 | serving_matches_manifest x10 |
| F03 | 9 | 9 | 9 | forecast_arithmetic x9 |
| F04 | 6 | 6 | 6 | answer_malformed x6 |
| F05 | 2 | 2 | 2 | weeks_match_request x2 |
| F06 | 1 | 1 | 1 | history_matches_database x1 |
| F07 | 2 | 2 | 2 | year_end_caveat x2 |
| F08 | 9 | 5 | 9 | text_matches_data x9 |
| S01 | 10 | 10 | 10 | figures_match_database x10 |
| S02 | 10 | 10 | 10 | figures_match_database x10 |
| S03 | 10 | 10 | 10 | figures_match_database x10 |
| S04 | 10 | 10 | 10 | flags_consistent x10 |
| S05 | 4 | 4 | 4 | trend_matches x4 |
| S06 | 4 | 4 | 4 | trend_matches x4 |
| S07 | 4 | 4 | 4 | trend_matches x4 |
| S08 | 2 | 2 | 2 | quotes_valid x2 |
| S09 | 1 | 1 | 1 | quotes_valid x1 |
| S10 | 1 | 1 | 1 | quotes_valid x1 |
| S11 | 10 | 10 | 10 | coverage_matches_database x10 |
| S12 | 10 | 10 | 10 | text_matches_data x10 |
| K05 | 10 | 0 | 0 | - |
| K10 | 10 | 0 | 0 | - |
| K20 | 10 | 1 | 1 | rating_contradiction x1 |
| K40 | 10 | 8 | 8 | rating_contradiction x8 |
| K80 | 10 | 10 | 10 | rating_contradiction x10 |
| MR1 | 10 | 0 | 0 | - |
| MR2 | 10 | 0 | 0 | - |
| MR3 | 10 | 0 | 0 | - |
| MF1 | 9 | 0 | 0 | - |
| MF2 | 10 | 0 | 0 | - |
| MS1 | 10 | 0 | 0 | - |
| MS2 | 10 | 0 | 0 | - |
| MS3 | 2 | 0 | 0 | - |
| O1a | 4 | 4 | 4 | figures_match_database x4 |
| O1b | 4 | 4 | 4 | figures_match_database x4 |
| O2 | 6 | 0 | 0 | - |
| O3a | 10 | 10 | 10 | rating_contradiction x10 |
| O3b | 10 | 10 | 10 | rating_contradiction x10 |
| O4a | 1 | 0 | 1 | text_matches_data x1 |
| O4b | 1 | 0 | 1 | text_matches_data x1 |
| O5 | 10 | 0 | 0 | - |

## Controls (false alarms)

| agent | controls | m1 failed | m2 failed |
|---|---|---|---|
| reporting | 31 | 1 | 0 |
| forecast | 15 | 0 | 0 |
| sentiment | 16 | 0 | 0 |

Controls that newly fail in m2: none.

## Rating sensitivity

| level | cases | rule predicts caught | m1 caught | m2 caught |
|---|---|---|---|---|
| K05 | 10 | 0 | 0 | 0 |
| K10 | 10 | 0 | 0 | 0 |
| K20 | 10 | 1 | 1 | 1 |
| K40 | 10 | 8 | 8 | 8 |
| K80 | 10 | 10 | 10 | 10 |

## Known gaps (consistent misparse)

| agent | cases | m1 caught | m2 caught |
|---|---|---|---|
| reporting | 30 | 0 | 0 |
| forecast | 19 | 0 | 0 |
| sentiment | 22 | 0 | 0 |

## Owner-selected, AI-co-written faults (expectations as recorded, never rewritten)

- **O1a** (1a (primary, owner's ruling 2026-10-10): repeat links ignored, so repe): expectation: caught; m1: caught 4 of 4; m2: caught 4 of 4
- **O1b** (1b (owner's ruling): the literal definition, completed jobs with no li): expectation: caught; m1: caught 4 of 4; m2: caught 4 of 4
- **O2** (2 (as proposed): the forecast numbers for the holiday weeks are wrong,): expectation: caught; m1: passed; m2: passed
- **O3a** (3a (owner's ruling): flip every non-positive prediction on a 1-2 star ): expectation: caught; m1: caught 10 of 10; m2: caught 10 of 10
- **O3b** (3b (owner's ruling): reach about 88% positive by also flipping non-pos): expectation: caught; m1: caught 10 of 10; m2: caught 10 of 10
- **O4a** (4a (as proposed): the grouped text is re-rendered with no minimum, so ): expectation: known_gap; m1: passed; m2: caught 1 of 1 (closed by the section 6 small-sample rule: groups under 20 are not ranked and the left-out count is QA's own)
- **O4b** (4b (as proposed): the 'too few to compare reliably' marking removed fr): expectation: known_gap; m1: passed; m2: caught 1 of 1 (closed by the section 6 small-sample rule: a filtered rate under 20 cases carries the marking)
- **O5** (5 (as proposed): a consistent misparse, the range widened to the trail): expectation: known_gap; m1: passed; m2: passed

## Every case whose verdict changed

- `F08|forecast:f02`: m1 pass, m2 fail ['text_matches_data']
- `F08|forecast:f04`: m1 pass, m2 fail ['text_matches_data']
- `F08|forecast:f05`: m1 pass, m2 fail ['text_matches_data']
- `F08|forecast:f14`: m1 pass, m2 fail ['text_matches_data']
- `O4a|owner:A4a`: m1 pass, m2 fail ['text_matches_data']
- `O4b|owner:A4b`: m1 pass, m2 fail ['text_matches_data']

Cases caught in m1 and passed in m2: none.
