# Interpretation gate for QA's `qa_interp_v1` (ADR-089)

QA's one language-model call checks that a specialist's reading of a question (the parsed
request: metric, range, breakdown, filters; or slice, horizon, period) matches the question.
This folder holds the pairs it is measured on and the gate it must pass, **all committed before
any live call**. Nothing here changes after a result is seen.

## The pairs (`pairs_v1.jsonl`, built by `build_sets.py`)

84 pairs, built programmatically, no hand-picking, with `random.Random(20261009)`:

| | source | correct pairs | wrong pairs |
|---|---|---|---|
| reporting | the 28 `parse_v4` items | 28 | 28 |
| forecast | the 14 forecast `parse_v1` items | 14 | 14 |
| | | **42** | **42** |

- **Correct pair**: the item's labelled *expected* request. A labelled decline (an unsupported
  metric, an unsupported area, a forecast the system cannot make) is a correct pair too.
- **Wrong pair**: the same request with exactly one thing changed to a wrong value.
  Reporting: the metric, the dates (both ends shifted by one month), `group_by`, region,
  account name or technician name; the operator and the value are drawn by the seed over a
  sorted candidate list, and a mutation that would make the agent decline the request is not
  used. A labelled decline is mutated into something that looks answerable (the metric of an
  unsupported-metric item, the region of an unsupported-area item), and that counts as wrong.
  Forecast: the slice, the horizon or the period; a labelled decline loses its `unsupported`
  flag.
- `python evals/qa_interp/build_sets.py --check` fails if the file is stale; a unit test runs it.
- The mutation distribution is printed by `build_sets.py` and recorded with the results.

## The runs

`qa_interp_v1` (`services/agent_qa/prompts/`), **k = 3** runs of all 84 pairs, Gemini
Flash-Lite on the **free key**, thinking level **minimal**, as-of **2026-08-30**: **252 calls**.
The model sees the question and the reading the service builds (the same functions); it never
sees the label. Output is schema-constrained (`faithful`, `differs_in`, `note`); a wrong answer
is not retried. Every run is saved to `evals/results/qa_interp/<date>/`.

## The gate, in **every** run

- **(a) False rejects:** at most **2** of the 42 correct pairs judged `faithful: false`.
- **(b) Catches:** at least **34** of the 42 wrong pairs judged `faithful: false` (80%).

Scoring choices, fixed now: a call that failed (an API error after the client's own retries)
counts against the pair, so a correct pair whose call failed is a false reject and a wrong pair
whose call failed is not caught. A run is complete only when all 84 pairs are judged; the gate
passes only with three complete runs that each meet (a) and (b). A daily-quota 429 stops the run
and it resumes the next day from where it stopped (`run.py --resume`). `gate.py` computes the
result and prints the per-run table.

## If the gate fails

At most **one** revision, `qa_interp_v2`, disclosed with what it targeted, run the next day
(another 252 calls). If the gate still fails, the interpretation check ships in **advisory
mode**: it is logged and reported on the verdict but never fails an answer or triggers a retry,
and the limitation is recorded. The gate is not loosened.

*Budget note, fixed now:* v1 (252) plus a v2 run (252) is 504 calls, above the 420-call cap on
the gate, so a revision run is not started on the strength of this prompt's budget alone: if v1
fails, the owner is asked before any v2 call.

## Not blind

The correct pairs come from parse sets drafted by assistants (L-69), and the mutations are
synthetic: a mutation is easier to spot than a real mis-parse, which tends to be subtler. A pass
here is evidence that the check catches blunt errors and rarely rejects a faithful reading. It is
not evidence about the rate of real mis-parses it would catch. Results say so.
