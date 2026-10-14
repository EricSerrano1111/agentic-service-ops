# Sprint 5 failure analysis (2026-10-13)

From the recorded data only: `sprint5_failure_data.md`, `routing_heldout_v1/2026-10-13/score.json`,
`golden_v2/2026-10-13/score.json`, `sprint5_x/golden_owner_review.csv` and
`sprint5_x/golden_assistant_reading.md`. No new runs. Both sets are spent for blind use; any
prompt change that reads this file turns them into development data.

## 1. Held-out routing: the 12 items behind the 36 wrong item-runs

All 36 wrong item-runs are in two classes; nothing else was wrong in 150 item-runs.

### The 7 ambiguous items (FR-03; 21 item-runs, L-58)

`route_v3` has no `ambiguous` route, so every one is wrong by construction. What the user got:

| Item | Question | Routed to | Outcome across runs 1, 2, 3 |
|---|---|---|---|
| AMB-03 | Give me a quick status update on Silver Creek Foods Inc. | reporting | not_available x3 |
| AMB-10 | Can you give me an overview of Northeast for Q2 2026? | reporting | answered, not_available, answered |
| AMB-14 | How are our installs performing? | reporting | not_available x3 |
| AMB-16 | How do things look for next month? | forecast | answered x3 |
| AMB-22 | What's happening with Brightpath Foods Inc.? | reporting (runs 1, 3); out_of_scope (run 2) | not_available, declined, not_available |
| AMB-23 | How is maintenance work looking for the next 4 weeks? | forecast | answered x3 |
| AMB-25 | How are customer relations in Northeast? | sentiment | answered x3 |

Three items (AMB-16, AMB-23, AMB-25) were answered with figures in every run, and AMB-10 in two
of three, without the question being flagged as ambiguous. That is the FR-03 harm: a confident
answer to one of several possible readings. The route reasons logged for AMB-10 and AMB-25
show the router picking a reading and saying so; `Interpreted as:` in the UI is the user's check
(R-18). The router's choice was the same in all three runs for six of the seven, so this is a
property of the prompt, not noise.

### The 5 out-of-scope items (15 item-runs, all `out-of-scope accepted`)

| Item | Subject | Future-tense? | Received by | What the user got |
|---|---|---|---|---|
| NM-14 | technician staffing headcount, West, next 4 weeks | yes ("next 4 weeks") | forecast | `not_available` x3, a decline |
| NM-20 | dispatch calendar, all maintenance jobs, tomorrow | yes ("tomorrow") | forecast | `not_available` x3, a decline |
| OOS-01 | billed revenue, Ironwood Manufacturing, last month | no | reporting | `not_available` x3, a decline |
| OOS-03 | one technician's overtime hours, past 2 weeks | no | reporting | `not_available` x3, a decline |
| OOS-14 | technician mileage reimbursement spend, last quarter | no | reporting | `not_available` x3, a decline |

In all 15 item-runs the specialist declined and no figure was shown. The route label was wrong;
the user-facing result was a decline. The two future-tense items went to forecast; under the
owner's 2026-10-11 clarification (ADR-094) a future question about an out-of-scope subject is
`out_of_scope`, while `route_v3` implements ADR-053's reading ("what will happen" goes to
forecast). So these two are a known policy gap, not a surprise. The three past-tense items
reached reporting, which declined them.

## 2. Golden: the seven mechanical failures

| ID | Author | Oracle reason | Owner | Classification |
|---|---|---|---|---|
| G03 | owner | C1: outcome `not_available`, item expects an answer ("district" read as an unsupported breakdown) | N | **Design limit.** The data has no districts; the item expects regions. The system declined honestly. Mapping "district" to region is a product ruling (L-95 (1)). |
| G05 | owner | C3: range 2026-07-01..07-31 is not an acceptable range ("storm last weekend" dropped) | N | **Design limit.** Stretch item; the qualifier is silently dropped, though the answer states the range was assumed and asserts no cause (L-56). |
| G07 | owner | C3: 8 weeks returned, 26 expected ("end of next year" read as calendar 2027) | N | **Item issue and design limit.** The period is ambiguous about its start; the system skipped Sept to Dec 2026. The owner marks it N whichever reading is right (L-95 (2)). |
| G08 | owner | C1 and C2: declined by forecast; route `forecast` is not an acceptable route for the item | Y, no reason recorded | **Design limit.** Same pattern as NM-14: a future-tense out-of-scope subject goes to forecast. The decline names only what forecast covers. No figures shown. |
| G21 | drafted | C3: `p_value` 0.3349 against 0.334895628510519 | Y, no reason recorded | **Scoring issue.** Every other figure matches; the display rounds to four places (L-95 (5)). 30/36 at display precision, labelled as a post-hoc correction. |
| G28 | drafted | C1: outcome `answered`, item accepts `not_available` | Y, no reason recorded | **Item or scoring issue.** The text says Q2 2027 is beyond the horizon and shows no figures; the item's accepted outcomes leave out a defensible label (L-95 (3)). |
| G35 | drafted | C1 and C2: routed to reporting, "That metric isn't supported yet" | N ("does not ask for specific metric within southeast") | **System defect, known and open.** FR-03 (L-58). Predicted before the run. |

Two items need a note beyond the failures:

- **G27 (mechanical pass, owner N).** The answer states both band errors and shows no number, which
  is what `must` and `must_not` say, and the assistant's reading marks it met. The owner's note is
  "Unsure as request goes below available data range." That reads as a doubt about the item's
  premise, not a defect the text shows. It is the owner's mark and stands.
- **G10 (mechanical pass, owner Y).** The assistant's reading found `must_not` breached: the answer
  never says its figures are for all installs, not fiber (L-95 (4)). The owner marked Y with the
  note "provided transparency on no weeks available and provided available metrics to best answer
  question." The two readings differ on what "say the figures are for all installs" requires.

## 3. Patterns across both (five)

1. **Ambiguity is answered, not flagged.** 21 held-out item-runs and G35. Existing: **L-58** (FR-03
   open; `route_v6` recognised 4 of 8 against 6 needed, ADR-101).
2. **A future-tense question on an out-of-scope subject is routed to forecast.** NM-14, NM-20, G08;
   the past-tense subjects reach reporting (OOS-01, OOS-03, OOS-14). The user always gets a decline,
   so no wrong figure is shown, but the route label is wrong and the decline text names only one
   specialist's coverage. **New limitation: L-96** (`docs/evaluation-report.md`): "The router
   sends out-of-scope subjects to the specialist whose tense matches; the specialist declines, so
   the route is wrong and the outcome is right. Accepted at this scale; the fix is a router
   revision that needs its own gate (the owner's 2026-10-11 clarification, ADR-094)."
3. **A qualifier the system cannot honour is dropped or not named.** G05 (storm, weekend), G10
   (fiber), G04 ("since the app update"). Existing: **L-56** and **L-95 (4)**; the user-facing
   mitigation is the `Interpreted as:` line (**R-18**).
4. **A term or period the data does not define is resolved by the system's own reading.** G03
   "district", G07 "end of next year". The reading is stated, not asked. Existing: **L-95 (1) and
   (2)**, **R-18**. Whether to map "district" to region and which start a period has are the
   owner's rulings, not code.
5. **The mechanical score and the owner's judgement disagree on 4 of 36, in both directions.**
   Mechanical-too-strict: G21 (display precision), G28 (outcome label), G08 (route label). Mechanical
   blind to the text: G27, and G10 on the assistant's reading. Owner-written items score lower than
   drafted ones on both scores (L-54). Existing: **R-16** (evaluation validity) and **L-95**; the
   `golden_v3` scoring change for G21 is in the Sprint 6 backlog.
