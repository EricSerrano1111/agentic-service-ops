# Interpretation pairs plan (ADR-094, retro change 1)

Written and committed **before** `build_pairs.py` exists and before any pair is built. It is
derived from the documents and the specialists' request schemas, not from the generated items.
Nothing here changes after a pair is built; a deviation is reported, not edited in.

## What was found (paths and field names; no item text)

- **Used pairs (Sprint 4):** `evals/qa_interp/pairs_v1.jsonl`, 84 pairs built by
  `evals/qa_interp/build_sets.py` (seed 20261009) from `parse_v4` (28 reporting items) and
  `forecast_parse/parse_v1` (14 forecast items). Fields per pair: `id`, `source_id`, `domain`
  (`reporting` or `forecast`), `question`, `request` (the specialist's request), `label`
  (`matches` or `mismatch`), `mutation` (null, or `{operator, change}`).
- **The gate's inputs:** `evals/qa_interp/run.py` takes a pair and builds the model's input with
  `agent_qa.interpretation.reading_reporting` / `reading_forecast` from `question`, `domain` and
  `request`; the label is never shown. `gate.py` scores `matches` and `mismatch`. The service has
  a `reading_sentiment` (`agent_qa/interpretation.py`) that `run.py` does not call yet: sentiment
  pairs are new to the runner (flag for Prompt Y).
- **Request schemas** (`packages/schemas/src/schemas/`):
  - `ReportingRequest`: `metric`, `group_by`, `technician_name`, `region`, `account_name`,
    `start`, `end`.
  - `SentimentRequest`: `start`, `end`, `region`, `bucket`, `want_trend`, `want_examples`,
    `example_label`, `unsupported`.
  - `ForecastRequest`: `slice`, `horizon_weeks`, `period_start`, `period_end`, `want_history`,
    `unsupported`.
- **As-of date:** 2026-08-30 (ADR-050; `REPORTING_AS_OF_DATE`'s default, the same value the
  evaluation-set generation used).

## (a) The correct-pair mapping, from `intent`, in code (`build_pairs.py`)

The pair set is `interp_fresh_v1`. `intent.area` picks the specialist. A field is mapped only
where a document or an ADR states the representation; otherwise the item is ineligible (retro
change 2; never an accept-any reading, L-72). Every mapping is cited.

### Reporting (`ReportingRequest`)

| Request field | From | Rule and source |
|---|---|---|
| `metric` | `intent.measure` | `incident_count`, `incident_rate`, `sla_compliance`, `first_time_fix_rate` as named; `followup_drivers` is `repeat_visit_drivers` (ADR-073; data dictionary §6, "Repeat-visit drivers"). |
| `group_by` | `intent.breakdown` | `account`, `region`, `technician`, `incident_type`, `severity` as named; `work_type` is `service_type` (ADR-073; §6 "Incident counts by breakdown"); `month` and `quarter` are `unsupported` (a breakdown the agent doesn't offer: the `ReportingRequest` field comment under ADR-046, §6 rule 6.2). Null is null. |
| `technician_name` | `intent.technician_name` | As written; never resolved or corrected (ADR-073). |
| `account_name` | `intent.account_name` | As written (ADR-086). |
| `region` | `intent.region` | The four values as named; `unsupported` as `"unsupported"` (ADR-086: any other area, never mapped to a region). |
| `start`, `end` | `intent.period_start`, `intent.period_end` | When a period is stated; null otherwise: the parse returns no dates for a question that names none and code applies the default (ADR-050). |

**Defaults the specialist applies for what the question leaves out** (needed only to decide
whether a mutation changes the answer): no period is the last full calendar month before the
as-of date (ADR-050); no breakdown for `repeat_visit_drivers` is `incident_type` (ADR-073); no
region and no account is the whole company (ADR-086).

### Sentiment (`SentimentRequest`)

| Request field | From | Rule and source |
|---|---|---|
| `start`, `end` | `intent.period_start/end` | As reporting (ADR-068: a period not named gets a range from code, never the model). |
| `region` | `intent.region` | The four values. |
| `bucket` | `intent.breakdown` | `month` or `quarter` as named; no breakdown is `month` (§6 sentiment rule 3, "the requested bucket (`month` by default)"). |
| `want_trend` | `intent.measure` | True for `sentiment_trend` (ADR-068). |
| `want_examples` | `intent.measure`, `intent.examples_requested` | True for `example_comments` or when examples are requested (ADR-068). |
| `example_label` | `intent.sentiment_label` | Only when `want_examples` (§6 sentiment rule 7: the quotes are "of the asked label when the question asked for one"). |
| `unsupported` | `intent.breakdown` | `account`, `technician` as named; `work_type` is `service_type`; `incident_type` and `severity` are `other` (§6 sentiment rule 8: a breakdown other than time and region, one reason from `account`, `technician`, `service_type`, `other`). |

**Defaults:** no period is the previous calendar month with the requested bucket; for a trend
question, the six whole calendar months ending at the as-of month in monthly buckets, whatever
bucket was asked (ADR-068; §6 sentiment rule 3).

### Forecast (`ForecastRequest`)

| Request field | From | Rule and source |
|---|---|---|
| `slice` | `intent.work_type` | The named type; no type is `total` (ADR-069 slices: the total and the five service types; the `ForecastRequest` default; ADR-089's reading of a question with no service type). |
| `horizon_weeks` | `intent.horizon_weeks` | Set when the stated period is "the next N weeks" or when no period is stated and a horizon is; otherwise null (ADR-072 and the `ForecastRequest` docstring: "either a horizon in weeks or a target period"; the request never carries both). |
| `period_start`, `period_end` | `intent.period_start/end` | Set when the stated period is a month or a quarter (ADR-072: a period maps to the ISO weeks whose Monday falls inside it); null for a horizon. |
| neither | | Both null when the question names neither: "neither when the question names none, and code applies the default" (`ForecastRequest` docstring, ADR-072). |
| `unsupported` | `intent.region`, `intent.account_name`, `intent.technician_name`, `intent.breakdown` | `region`, `account`, `technician` (ADR-072, "Declined: ... region, account or technician breakdowns"). |
| `want_history` | none | The labels cannot carry it; always `false`, the schema's default. Disclosed below. |

### Fields that are documented nowhere, so the items that need them are ineligible

These are listed here before any item is read. `build_pairs.py` records the count per field.

1. **Sentiment with `region: "unsupported"`.** `SentimentRequest.region` is the four site
   regions only; ADR-086's `"unsupported"` representation is reporting's.
2. **Sentiment with `breakdown: region`.** The request has a region filter and no region
   breakdown; §6 sentiment rule 8 says region is supported but not how it is carried.
3. **A work-type filter on reporting or sentiment** (`intent.work_type` set). Neither request has
   a field for it; `service_type` exists only as a breakdown.
4. **A named account or technician on sentiment** (a filter the request has no field for; rule 8
   covers breakdowns only).
5. **`sentiment_label` set on a question that does not ask for examples**, and
   `sentiment_label` or `examples_requested` on reporting or forecast.
6. **Forecast with a past period** (`period_start` on or before the as-of date). ADR-072 says
   past periods are declined and the schema has `past_period`, but not whether the dates are kept
   alongside it.
7. **Forecast with more than one unsupported reason** (a region and an account, say): no order
   among them is documented.
8. **A forecast breakdown with no documented representation.** `region`, `account` and
   `technician` map to their `unsupported` reasons (ADR-072) and `work_type` maps to the slice
   when a type is given. Everything else is ineligible: `incident_type`, `severity`, `month`,
   `quarter`, and `work_type` with no type given.
9. **The default horizon for a forecast that names neither horizon nor period is not documented
   and is not needed:** the request carries null, and no mutation depends on the default. Such
   items stay eligible. This is the one value that is not written anywhere; it is never used.

An item is also ineligible when no mutation in the menu applies (reported as its own reason),
and by the earlier eligibility (`plan.md`: measure `other`, no measure, date check).

## (b) The wrong-pair mutations

Each eligible item gets **exactly one** wrong pair.

### What "a different answer" means (the comparison)

Both requests are **normalised through the specialist's documented defaults**, then compared:

- **Reporting:** `("decline", reason)` when `agent_qa.reporting.decline_reason` returns one;
  otherwise `(metric, group_by or the default breakdown, technician, region, account, (start,
  end) or the default range)`.
- **Sentiment:** `("decline", unsupported)` when `unsupported` is set; otherwise `(region, range
  or the default range, bucket, want_trend, want_examples, example_label if examples)`. For a
  trend question with no stated period the bucket is dropped from the key (monthly whatever was
  asked).
- **Forecast:** `("decline", unsupported)`; otherwise `(slice, the ISO weeks the request covers,
  want_history)`, where a horizon above 26 is the 26-week cap.

A mutation applies only if (1) the result validates against the request schema, (2) its key
differs from the correct request's key, and (3) the result is **not a decline** when the correct
request is not one, and is not a decline when the correct request is one (a declined correct pair
is mutated into something answerable, as in `pairs_v1`). So a wrong pair is always a request the
specialist would answer.

### Menu

| Mutation | Rule | Reporting | Sentiment | Forecast |
|---|---|---|---|---|
| `period_shift` | Both ends back by the period's own length: a whole calendar month goes to the previous month, a whole quarter to the previous quarter, anything else back by its length in days. Needs a stated period; the new start must not precede the dataset window start (2023-09-04); for forecast the new start must stay after the as-of date. | yes | yes | yes (period requests only) |
| `region_change` | Another of the four regions; or one of the four where none (or `unsupported`) was named. | yes | yes | never |
| `measure_swap` | A different measure in the same area: reporting a different metric of the five; sentiment a different one of mix, trend, examples (`want_trend`, `want_examples` set accordingly, `example_label` cleared). | yes | yes | never (one measure) |
| `work_type_change` | A different slice (including `total`). Reporting and sentiment have no work-type filter field. | never | never | yes |
| `breakdown_change` | A different valid `group_by` (not `unsupported`), or one added where none; sentiment: the other bucket. | yes | yes | never |
| `filter_drop` | Removes one stated region, account or technician filter (a stated `unsupported` region is one). | yes | region only | never |
| `horizon_change` | `horizon_weeks` changed by at least 4, staying within 1 to 26. Needs a horizon request. | never | never | yes |
| `name_swap` | The account or technician replaced by a different real one. | yes | never | never |

**Real names** for `name_swap` come from the database as `app_eval`: `accounts.account_name`
and `technicians.full_name`. Their sorted list is hashed (SHA-256) and the hash recorded in
`pairs_provenance.json`, so the pool the draw used is on the record. The name drawn is the
candidate with the lowest `sha256(f"20261013|{item_id}|name_swap|{name}")`, excluding the name
the item already has (case-insensitive).

### Selection: round-robin by seed (literal)

1. Eligible items are walked in ascending `sha256(f"20261013|item:{uid}")` order (hex digest
   compared as a string; `plan.md`'s ranking convention; no RNG state).
2. The fixed type order is `period_shift`, `region_change`, `measure_swap`, `work_type_change`,
   `breakdown_change`, `filter_drop`, `horizon_change`, `name_swap`. A cyclic pointer starts at
   the first.
3. For each item, starting at the pointer and moving cyclically, the **first type that applies**
   is its mutation; the pointer then moves to the type after it.
4. Within a type the change is the candidate with the lowest
   `sha256(f"20261013|{uid}|{type}|{candidate}")`, `candidate` being the canonical JSON of the
   request after the change.
5. An item with no applicable type is ineligible (reason `no_applicable_mutation`).

Counts per type are reported.

### Names that match no record

`account_name` and `technician_name` carry the as-written value in the correct pair, resolved
or not. A wrong pair that does not touch a name keeps it as written.

## (c) Disclosure text

"Correct pairs map the generated labels to request schemas by documented rules. Wrong pairs are
single, seeded mutations from a menu written by the assistant that built the system. So they
test the misparse kinds that assistant anticipated, not misparses observed in use."

Added for the record: the labels cannot say whether a question asks for recent history, so
`want_history` is always `false`; and the items are the ones whose dates the deterministic
resolver recognised and whose fields have a documented representation, which skews the set
toward the easier date phrasings and the plainer questions.
