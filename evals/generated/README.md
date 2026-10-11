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
```

- `plan.md`: pool counts, filter rules, eligibility, set definitions and the seed, committed
  before any generation call.
- `schema.py` / `schema.json`: the item schema. `mapping.py`: brief routes to system routes.
  `periods.py`: deterministic period resolution for `interp_fresh_v1` eligibility.
- `generate_sets.py`: fill, generate, filter, select. `provenance.json`: model, settings,
  hashes, and per-call tokens, cost, latency and outcome.
- Line endings are pinned to LF (`.gitattributes`) so the raw-output hashes never drift.

## Status

Drafts only. Freezing (manifest hashes, git blob hashes, interpretation pairs built from
`intent`) happens after the owner's skim.
