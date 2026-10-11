# Evaluation-set generation plan (ADR-094)

Pre-registered before any generation call. Nothing here changes after the first call; a
deviation is reported, not edited in.

## Brief

`brief_v2.md` is the brief used. It is `brief_v1.md` with one owner-ruled edit (2026-10-11):
the label bullet "Asks about the future, whatever the measure" is replaced by two bullets, a
future question about the company's work is `forecast`, and a future question about an
out-of-scope subject is `out_of_scope` (ADR-094, reference-policy clarification). No other
wording changed. `brief_v1.md` is superseded and kept. The filled brief is
`brief_v2.filled.md`. Everything below that says "the brief" means `brief_v2.md`.

## Generator and settings

- Model `gemini-3.8-flash`, paid key, through `packages/llm` (`LLM_MODE=paid`).
- Budget 16 requests: 1 `models.list` (made directly through the SDK on 2026-10-11, before
  this plan, so `packages/llm` never counted it) + 11 generation + 4 retry margin. The client's
  cap is therefore `LLM_MAX_REQUESTS=15`. Spend cap `LLM_MAX_SPEND_USD=2.00`.
- `LLM_REQUEST_TIMEOUT_S=300`: output is 8 to 9K tokens plus thinking, and the 30 s default
  would classify a slow response as transient and retry it silently. The script compares
  `totals.requests` with `totals.calls` after every call and records any hidden retry; a
  hidden retry spends margin.
- Thinking level: the client's default for the model, its lowest supported level (ADR-052):
  `low` (the model supports low, medium, high; `minimal` is rejected).
- Temperature: the model's own default. The client's settings carry `temperature`, which the
  transport passes to the SDK; the script replaces it with `None`, which the SDK leaves out
  of the request (checked offline: the config dump has no `temperature`). No value is sent.
- Output: a JSON array. `response_model` is a root model over an array of objects with no
  per-item validation; per-item checks are filter removals.
- Only a response that is not a parseable JSON array is re-requested, once, from the margin.
- The one prompt: the filled brief, then `Write {count} questions in the category
  {category}.` and nothing else.

## Pool counts, one generation call each

| Category | Count |
|---|---|
| `clear_reporting` | 25 |
| `clear_sentiment` | 20 |
| `clear_forecast` | 20 |
| `underspecified` | 20 |
| `ambiguous` | 30 |
| `multi_domain` | 20 |
| `out_of_scope` | 15 |
| `near_miss` | 25 |
| `technician` | 15 |
| `filtered` | 20 |
| `unsupported_in_area` | 15 |
| **Total** | **225** |

## Stop rules

- After the third generation call, project the total from the mean cost per call so far; stop
  and report if it exceeds $1.50.
- Stop if the cap would be crossed, if a fifth retry would be needed, or if any category's
  second attempt also fails to parse.

## Ranking (the only source of randomness)

Seed `20261012`. Every draw ranks candidates by `sha256(f"{seed}|{key}")` ascending, hex digest
compared as a string, where `key` is `account:<account_id>`, `technician:<technician_id>` or
`item:<category>/<id>`. No shuffle, no RNG state: the order does not depend on iteration order.

## Filter rules (pool level)

An item is removed, with its reason, if:

1. **schema**: it fails `schema.py`, checked per item (one bad item never discards a batch);
2. **category**: its `category` differs from the category requested in that call;
3. **label**: `expected_route` disagrees with the category's route in `mapping.CATEGORY_ROUTE`,
   or, for categories with no fixed route, with `intent.area`; or `intent.area` disagrees with
   `expected_route` for any item with an intent; or the `ambiguous`/`multi_domain` candidates
   are inconsistent with the schema;
4. **no_unsupported_element**: an `unsupported_in_area` item with no unsupported element: no
   `measure: "other"`, no breakdown the area does not offer, and no `region: "unsupported"`.
   "Breakdown the area does not offer" means: sentiment with a breakdown other than `month`,
   `quarter` or `region`; forecast with a breakdown other than `work_type`; reporting with a
   breakdown of `month` or `quarter`;
5. **exact_duplicate**: equal after normalisation (lowercase, whitespace and punctuation removed);
6. **near_duplicate**: character 5-gram Jaccard > 0.6 (the corpus's method, `build_corpus.py`),
   within the pool (the lower-ranked item of a pair is removed) and against every existing
   evaluation set except `evals/golden/`, which is never opened.

## Eligibility for `interp_fresh_v1` only (items stay in the pool)

Ineligible if: `measure` is `other`; the item's category is `unsupported_in_area`; its `intent`
has no `measure`; or the date check fails.

The date check is `periods.check_item_period`, with as-of 2026-08-30:

- If `period_stated`, `period_text` must be a phrase `periods.py` recognises, and the
  deterministic resolution must equal `period_start` and `period_end`.
- Past periods resolve by ADR-050: "last month", "this month", "last quarter", "the past N
  days", and an explicit month or quarter with a year.
- Future periods resolve by ADR-072: "next month", "the next N weeks" (the N weeks after the
  as-of date, `horizon_weeks` must equal N), and a bare month or quarter, meaning its next
  occurrence; the current month or quarter is not guessed (L-38).
- Not recognised, so ineligible: "this quarter", "year to date", "the past N weeks", "next
  quarter", a bare month in a past question, and anything else. ADR-050 and ADR-072 do not
  define the first four, although the brief does.
- Forecast: `horizon_weeks` must equal the period's weeks ahead, rounded up, when a period is
  stated; otherwise it is null or within 1 to 26.
- If no period is stated, the period fields must all be null.

## Set definitions

The sets are disjoint, drawn by rank, and stratified by category. A stratum filled from several
categories draws the lowest-ranked items across them.

- **`routing_heldout_v1` (50):** clear 15 (5 each from `clear_reporting`, `clear_sentiment`,
  `clear_forecast`), underspecified 6, ambiguous 7, multi_domain 6, out_of_scope 5, near_miss 5,
  technician 2, filtered 2, unsupported_in_area 2.
- **`fr03_fresh_v2` (16):** ambiguous 8, underspecified 4, clear 2 (any clear category),
  multi_domain 2.
- **`interp_fresh_v1` (24, eligible items only, from clear, underspecified, filtered and
  technician):** reporting 10, including at least 2 filtered items (at least 1 with
  `region: "unsupported"`, if one is eligible) and at least 2 technician items; sentiment 7;
  forecast 7. The count of 10 + 7 + 7 is by `intent.area`.
- **`parse_filters_v1` (12 filtered items):** optional, for later changes to the reporting
  parse prompt.
- **Reserve:** everything else, in rank order within category and area.

Selection order: `interp_fresh_v1`, `fr03_fresh_v2`, `routing_heldout_v1`, `parse_filters_v1`.
For `interp_fresh_v1` the required minimums (filtered 2 including an unsupported region,
technician 2) are filled first, then the rest of the area by rank.

A set that cannot be filled is smaller, and says so. No category quota is borrowed from another.

## Replacement rule

When the owner drops an item at the skim, the next reserve item of the same category and
area takes its place, in rank order. For `interp_fresh_v1` the replacement must also be
eligible. If the reserve runs out, the set is smaller and says so.

## Label mapping

Brief route labels map to the system's route enums in `mapping.py`, from the six values of
`schemas.routing.Route` (reporting, sentiment, forecast, multi_domain, out_of_scope,
ambiguous). The brief uses the same six strings. Mapping `intent` to the specialists'
request schemas is Prompt R's job.

## Skim file

`skim/skim.csv` lists every `ambiguous`-labelled item in any set, every `fr03_fresh_v2` item,
and the first 6 ambiguous and first 2 underspecified items in the reserve (by rank). Columns:
`id, set, category, question, expected_route, candidate_areas, rationale, owner_agree,
owner_note`. The owner may drop an item, never fix one. The sets stay drafts; freezing is
Prompt R's job after the skim.
