# Sprint 5 gates and scoring rules (Prompt W, pre-registered)

Committed in one commit **before any Part C call** and before `evals/generated/` is opened
by this session. Nothing here changes after a result is seen; a mistake is disclosed as a new
dated entry, never edited in place.

Frozen inputs, for the record:

| What | Value |
|---|---|
| Harness commit (paid mode, ledger) | `adef7a9` |
| `route_v6` | commit `031426b878608678268954fb71ac3853dff52e63` (2026-10-12 16:18 CDT), prompt sha `a160b528247b` |
| `qa_interp_v3` | commit `07ca35b10227c76ff6839199738dbcabf7a9d26f` (2026-10-12 16:20 CDT), prompt sha `cccf19c29990` |
| Frozen generated sets | `evals/generated/manifest.json`, freeze commit `8ed47771fa084794fe663506ae489339f5db4459` (2026-10-11 15:04 CDT); hash test green at the start of this session |
| Model, key, thinking, as-of | `gemini-3.5-flash-lite`, paid key, thinking `minimal`, as-of 2026-08-30 (both the orchestrator and QA roles confirmed by a no-call check) |

## Blindness order

1. Part A wrote one revision each (`route_v6`, `qa_interp_v3`) from the used development
   material only (`seed_v1/v2`, `routing_v1/v2`, `fr03_fresh_v1`, the 84 used interpretation
   pairs). Neither prompt contains a question from any evaluation set; a test checks this on
   the prompt files themselves.
2. This file, then the gates, in this order. The A1 runs were **in progress** when this file
   was written; no criterion below was set from an A1 or A2 result. **(b1) uses the A1 runs,
   so its outcome is known to the session before the gate is "run"**; the rule was fixed by
   the Prompt W text, not by that outcome.
3. Part C runs each gate **once**. There is no third attempt in Sprint 5, whatever the result.
   After Part C no prompt changes and no reruns. The report gives counts and item IDs only for
   (c) misses and false rejects, never item text.

## Call budget and caps

The cap was recomputed from the real counts at §0 and set by the owner (decision, 2026-10-12)
**before any call**. The earlier plan assumed the interpretation check covers reporting and
forecast only. That assumption was wrong: the shipped check also runs on sentiment answers
(ADR-090, `reading_sentiment`, `QA_INTERP_MODE` is not domain-scoped), so the gate covers
sentiment and `enforce` would apply to it.

| Path | Calls |
|---|---|
| A1: `route_v6` k=3 on `seed_v2` (31) + `routing_v2` (18) + `fr03_fresh_v1` (15) | 192 |
| A2: `qa_interp_v3` k=1 on the 84 used pairs | 84 |
| C1: `route_v6` k=3 + `route_v3` k=3 on `fr03_fresh_v2` (16) | 96 |
| C2: `qa_interp_v3` k=3 on the 46 gate pairs | 138 |
| Retry margin (10% of 510) | 51 |
| **Total cap** | **561 requests; spend cap $3.00** |

- The advisory-call count is 0: the routing runner calls the router only, and `run.py` calls
  only the interpretation model (checked in the code).
- **Enforced at the harness.** `evals/ledger.py` keeps `evals/results/sprint5_w_ledger.json`;
  every paid runner invocation reads it before each call and appends to it after, counting
  HTTP requests (retries included) and list-price cost from response metadata, by path. A call
  that would exceed 561 requests or $3.00 is refused before it is sent. A call that retries can
  overshoot the request count by its retries; the next call is then refused. The caps are
  written at file creation and a later invocation passing different caps is refused.
  Unit-tested: `tests/unit/test_eval_ledger.py`.
- **Paid mode is explicit.** `--paid` is required together with `LLM_MODE=paid`, and refused
  otherwise (either one alone); `--path` names the ledger path. Free mode is unchanged.
- **Per-invocation process caps** (`LLM_MAX_REQUESTS`; `LLM_MAX_SPEND_USD` $1.00 each, the
  ledger governs the aggregate), summing to at most the total:

  | Path | Invocation | Cap | Count |
  |---|---|---|---|
  | A1 | `seed_v2` (31) / `routing_v2` (18) / `fr03_fresh_v1` (15) | 33 / 19 / 16 | 3 each = 204 |
  | A2 | 84 pairs, k=1 | 92 | 1 = 92 |
  | C1 | `fr03_fresh_v2` (16), `route_v6` and `route_v3` | 18 | 6 = 108 |
  | C2 | 46 pairs, k=1 | 51 | 3 = 153 |
  | | | | **557 ≤ 561** |

  `run.py --budget` is passed explicitly (its default of 252 is for the old gate).
- **Stop rules.** If the ledger's count or cost reaches its cap: stop and report; a part-run
  gate counts as failed. If the session hits its usage limit: resume with `claude --continue`
  and re-read the ledger and the results files before any further call. No cap is raised,
  reset or worked around.

## Before the first Part C call: the loader check (no model call)

The frozen sets' field names and label values are not known to this session until Part C (it
may not open `evals/generated/` before this commit). Both runners assume names (`id`,
`question`, `expected`, `tag`; `domain`, `label` in {`matches`, `mismatch`}, `request`), and a
mismatch in a label **value** would misscore without crashing. So the first Part C step is
`evals/sprint5_loader_check.py`, which makes **no model call** and prints only:
key names, the counts of each short categorical value, and role and domain counts (compared
with `pairs_provenance.json`: 23 correct, 23 wrong; reporting 10, forecast 7, sentiment 6 per
role) and the ambiguous / non-ambiguous split of `fr03_fresh_v2` (8 and 8). **No item text.**
Any fix it forces is **format mapping only** (field names and label values); it changes no
criterion, prompt, threshold or item, and is committed before the first paid call with the
check's output in its message.

## B1. The FR-03 gate on `fr03_fresh_v2`

`fr03_fresh_v2`: 16 items, 8 ambiguous and 8 non-ambiguous. `route_v6` k=3 and `route_v3`
k=3, each on the full set, run through `evals/routing/run_seed.py --paid --path C1`, one
invocation per run. ADR-076's criteria, scaled; computed by `evals/routing/fr03_gate.py`:

- **(a)** At most 1 non-ambiguous item-run routed `ambiguous`, across `route_v6`'s 3 runs.
- **(b1)** On the development sets (`seed_v2` + `routing_v2`, 44 non-ambiguous items),
  `route_v6`'s mean non-ambiguous correct count over its 3 A1 runs is at least `route_v3`'s
  recorded 3-run mean (43.00, ADR-076) minus 1 = **42.00**.
- **(b2)** On the fresh set's 8 non-ambiguous items, `route_v6`'s 3-run mean is at least
  `route_v3`'s 3-run mean minus 1.
- **(c)** At least ⌈2/3 × 8⌉ = **6 of 8** ambiguous items return `ambiguous` in at least 2 of 3
  runs.

A pass requires all four, on complete runs. A failed or errored call is scored wrong; a
part-run gate counts as failed.

- **Pass:** ADR-075 takes effect with `route_v6` as the default; L-58 closes with a reference.
- **Fail:** `route_v3` stays the default; FR-03 stays open and disclosed.

## B2. The interpretation gate

- **Scope: all three domains the shipped check covers** (reporting, forecast, sentiment): 23
  correct and 23 wrong pairs, `interp_pairs_v1`. **The sentiment slice is 6 pairs per role**;
  per-domain counts are reported and are not thresholds.
- **Prompt:** `qa_interp_v3`, as written, on the QA role's model, through
  `evals/qa_interp/run.py --paid --path C2 --k 1 --budget 51`, one invocation per run, the
  same reading functions the service uses.
- **Criteria: ADR-089's (a) and (b) as written were counts of 42; restated as rates and
  applied to 23, rounding in the strict direction** (fewer false rejects allowed, more
  catches required):
  - (a) 2 of 42 = 4.76%; 4.76% × 23 = 1.09, rounded **down** to **at most 1** false reject of
    the 23 correct pairs;
  - (b) 34 of 42 = 80.95%; 80.95% × 23 = 18.62, rounded **up** to **at least 19** of the 23
    wrong pairs caught.
- **Runs:** k=3, a pass requires both criteria in **all 3 runs**. The early-stop rule from the
  last gate is pre-registered now: **if a complete run fails (a) or (b), the gate has failed
  and the remaining runs are not made.** Computed by `evals/qa_interp/gate_s5.py`. A failed
  call counts against the pair.
- **Scope limits, written now:**
  - The frozen gate covers 1 decline pair; it does not test decline false rejects (the known
    failure kind). See the A2 development diagnostic, which is not held out.
  - A2 has no sentiment pairs: the sentiment section of `qa_interp_v3` got no development
    measurement before the gate.
  - The pairs are generated, not owner-written (ADR-094); correct pairs and mutations were
    built by script from model-written questions.
- **Pass:** a new ADR switches the default `QA_INTERP_MODE` to `enforce` for all three
  domains, which is then measured (Prompt X); `qa_interp_v3` becomes the shipped prompt; L-74
  closes.
- **Fail:** the check stays advisory with `qa_interp_v2`; L-74 stands; `qa_interp_v3` is not
  shipped.

## B3. Scoring for Prompt X, fixed now

**The held-out routing eval** (`routing_heldout_v1`, 50 items): k=3 on the default router
after Part C, on the deployed, frozen system. Report:

- per-run correct out of 50, the range and the flipping items (ADR-054, L-17);
- per-category accuracy;
- accuracy **with and without** the 7 ambiguous items.

If the default is `route_v3`, which has no `ambiguous` route, the ambiguous items are scored
**wrong** (FR-03 forbids force-routing); the without-ambiguous figure is reported alongside
and labelled as such.

**Failure-analysis taxonomy** (every wrong item-run gets exactly one): wrong area; ambiguous
not flagged; false ambiguous; multi-domain missed; out-of-scope accepted; in-scope declined;
error or timeout.

**The golden run** is scored by ADR-074's rules and `golden_v2`'s manifest, with the
sprint-log check notes (the region, account and tie-order items). This file does not define or
change them.

**Disclosure lines, verbatim in X's report:**

1. ADR-094's sentence: "In a real deployment, evaluation sets would come from real user
   questions and subject-matter experts. Here they were generated by an independent model
   under a written brief; the owner reviewed the brief and spot-checked the ambiguous labels."
2. "The sets were generated, not owner-written."
3. The persona-drop selection effect (L-86).
