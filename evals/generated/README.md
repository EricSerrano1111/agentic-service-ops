# evals/generated: model-written evaluation sets (ADR-094)

These sets were written by an independent model (`gemini-3.8-flash`, paid key) from a fixed
brief, by script. They are **not owner-written** and **not blind to the assistant's framing of
the domain**; they are blind to the system. ADR-094 has the reasons and the same-family
disclosure.

## Rules

1. **No prompt-revision session reads this directory.** Not the raw output, the filtered pool,
   the drafts or the skim file. The sets exist to measure the system, not to tune it. The only
   readers are the owner (the skim), the evaluation runners, and the freeze step.
2. **The brief is fixed.** `brief_v2.md` is committed verbatim (`brief_v1.md` is superseded, kept for the record: see ADR-094); only its `{PLACEHOLDERS}` are
   filled, by script, from the database as `app_eval`. Its wording is never edited to match
   the system.
3. **The generator sees the brief and nothing else:** no project document, prompt, existing
   evaluation item or ADR text.
4. **Filtering only removes items.** No question or label is edited after generation. The owner
   may drop an item at the skim and never fix one.
5. Reports about these sets contain counts, hashes, costs and reasons, never item text.

## Pipeline

```
brief_v2.md  --fill-->  brief_v2.filled.md  --11 calls-->  raw/<category>.json
raw/  --schema, label, duplicate filters-->  filtered/pool.jsonl + filtered/removed.jsonl
pool  --seeded ranking-->  sets/<name>.draft.jsonl  +  skim/skim.csv
skim + drafts --apply_skim, build_pairs, freeze-->  sets/<name>.jsonl  +  manifest.json
```

- `plan.md`: pool counts, filter rules, eligibility, set definitions and the seed, committed
  before any generation call.
- `schema.py` / `schema.json`: the item schema. `mapping.py`: brief routes to system routes.
  `periods.py`: deterministic period resolution for `interp_fresh_v1` eligibility.
- `generate_sets.py`: fill, generate, filter, select. `provenance.json`: model, settings,
  hashes, and per-call tokens, cost, latency and outcome.
- Line endings are pinned to LF (`.gitattributes`) so the raw-output hashes never drift.

## Status: frozen (2026-10-11)

The sets are final. `manifest.json` records each file's SHA-256, git blob hash and line count
and the freeze commit; `tests/unit/test_eval_set_manifest.py` recomputes them in the normal
suite and fails on any difference. Final sets are **append-never**: a later change is a new
version (`_v2`) under a new ADR, never an edit.

| File | Items | Notes |
|---|---|---|
| `sets/routing_heldout_v1.jsonl` | 50 | held-out routing; 3 skim drops replaced |
| `sets/fr03_fresh_v2.jsonl` | 16 | FR-03 fresh set; 2 skim drops replaced |
| `sets/interp_fresh_v1.jsonl` | 23 | target 24; one sentiment slot unfilled (no eligible reserve item) |
| `sets/interp_pairs_v1.jsonl` | 46 | 23 correct + 23 wrong, one per item and role |
| `sets/parse_filters_v1.jsonl` | 12 | optional, for later reporting-parse changes |
| `sets/reserve.jsonl` | 107 | everything else, in rank order |

`apply_skim.py` applies the owner's skim (`sets/skim_applied.json`, IDs only), `build_pairs.py`
builds the pairs from `intent` by the rules of `pairs_plan.md` (`pairs_provenance.json` records
the name pool's hash, the counts and the interpretation set's removals and refills), and
`freeze.py` assembles the final files. `pairs_plan.md` was committed before `build_pairs.py`
existed; its one amendment (the selection rule) was made after a first build gave no
`name_swap` pairs and before any model saw a pair.

## Interpretation pairs: how they were built

"Correct pairs map the generated labels to request schemas by documented rules. Wrong pairs are
single, seeded mutations from a menu written by the assistant that built the system. So they
test the misparse kinds that assistant anticipated, not misparses observed in use."

Every field's mapping is cited to the data dictionary or an ADR in `pairs_plan.md`. A field with
no documented representation makes its items ineligible. The pair file carries `question`,
`domain`, `request`, `label` (`matches` or `mismatch`), `role`, `mutation` and `citations`, so
the existing runner (`evals/qa_interp/run.py`) can read it; its sentiment readings are new to
that runner. `want_history` is always false because the labels cannot carry it.

## Skim criterion (2026-10-11)

2026-10-11: owner drops at the skim were made on persona grounds: a question a dispatcher or
call-centre agent would ask, but not a senior operations leader with an overview of the
business unit (the brief's stated asker). Labels were not changed. The owner hadn't seen any
system output for these items.

**A selection effect to disclose.** Persona drops may remove the more granular, operational
questions, which leaves the sets weighted toward broad leadership questions. The failure
analysis reports the drop count.
