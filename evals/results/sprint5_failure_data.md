# Sprint 5 failure-analysis data (Prompt X)

Run date 2026-10-13; deployed images tagged `9607fa72` (tree equals `eval-freeze-s5`), paid mode (ADR-104). Data and the pre-registered taxonomy only; no interpretation here.

**These sets are now spent for blind use** (`routing_heldout_v1` and `golden_v2` were run on 2026-10-13). Item text appears below and in the report; any later prompt change that reads this file must treat both sets as development data, not held-out data.

## 1. Held-out routing: wrong item-runs

Per-run correct: [38, 38, 38] of 50; without the 7 ambiguous items: [38, 38, 38] of 43. Flipping items: none.

Counts by taxonomy class (item-runs, 3 runs):

| Class | Item-runs |
|---|---|
| wrong area | 0 |
| ambiguous not flagged | 21 |
| false ambiguous | 0 |
| multi-domain missed | 0 |
| out-of-scope accepted | 15 |
| in-scope declined | 0 |
| error or timeout | 0 |

| Pass | ID | Category | Expected | Got | Class | Outcome | Question |
|---|---|---|---|---|---|---|---|
| 1 | ambiguous/AMB-03 | ambiguous | ambiguous | reporting | ambiguous not flagged | not_available | Give me a quick status update on Silver Creek Foods Inc. |
| 2 | ambiguous/AMB-03 | ambiguous | ambiguous | reporting | ambiguous not flagged | not_available | Give me a quick status update on Silver Creek Foods Inc. |
| 3 | ambiguous/AMB-03 | ambiguous | ambiguous | reporting | ambiguous not flagged | not_available | Give me a quick status update on Silver Creek Foods Inc. |
| 1 | ambiguous/AMB-10 | ambiguous | ambiguous | reporting | ambiguous not flagged | answered | Can you give me an overview of Northeast for Q2 2026? |
| 2 | ambiguous/AMB-10 | ambiguous | ambiguous | reporting | ambiguous not flagged | not_available | Can you give me an overview of Northeast for Q2 2026? |
| 3 | ambiguous/AMB-10 | ambiguous | ambiguous | reporting | ambiguous not flagged | answered | Can you give me an overview of Northeast for Q2 2026? |
| 1 | ambiguous/AMB-14 | ambiguous | ambiguous | reporting | ambiguous not flagged | not_available | How are our installs performing? |
| 2 | ambiguous/AMB-14 | ambiguous | ambiguous | reporting | ambiguous not flagged | not_available | How are our installs performing? |
| 3 | ambiguous/AMB-14 | ambiguous | ambiguous | reporting | ambiguous not flagged | not_available | How are our installs performing? |
| 1 | ambiguous/AMB-16 | ambiguous | ambiguous | forecast | ambiguous not flagged | answered | How do things look for next month? |
| 2 | ambiguous/AMB-16 | ambiguous | ambiguous | forecast | ambiguous not flagged | answered | How do things look for next month? |
| 3 | ambiguous/AMB-16 | ambiguous | ambiguous | forecast | ambiguous not flagged | answered | How do things look for next month? |
| 1 | ambiguous/AMB-22 | ambiguous | ambiguous | reporting | ambiguous not flagged | not_available | What's happening with Brightpath Foods Inc.? |
| 2 | ambiguous/AMB-22 | ambiguous | ambiguous | out_of_scope | ambiguous not flagged | declined | What's happening with Brightpath Foods Inc.? |
| 3 | ambiguous/AMB-22 | ambiguous | ambiguous | reporting | ambiguous not flagged | not_available | What's happening with Brightpath Foods Inc.? |
| 1 | ambiguous/AMB-23 | ambiguous | ambiguous | forecast | ambiguous not flagged | answered | How is maintenance work looking for the next 4 weeks? |
| 2 | ambiguous/AMB-23 | ambiguous | ambiguous | forecast | ambiguous not flagged | answered | How is maintenance work looking for the next 4 weeks? |
| 3 | ambiguous/AMB-23 | ambiguous | ambiguous | forecast | ambiguous not flagged | answered | How is maintenance work looking for the next 4 weeks? |
| 1 | ambiguous/AMB-25 | ambiguous | ambiguous | sentiment | ambiguous not flagged | answered | How are customer relations in Northeast? |
| 2 | ambiguous/AMB-25 | ambiguous | ambiguous | sentiment | ambiguous not flagged | answered | How are customer relations in Northeast? |
| 3 | ambiguous/AMB-25 | ambiguous | ambiguous | sentiment | ambiguous not flagged | answered | How are customer relations in Northeast? |
| 1 | near_miss/NM-14 | near_miss | out_of_scope | forecast | out-of-scope accepted | not_available | Forecast technician staffing headcounts needed in the West for the next 4 weeks. |
| 2 | near_miss/NM-14 | near_miss | out_of_scope | forecast | out-of-scope accepted | not_available | Forecast technician staffing headcounts needed in the West for the next 4 weeks. |
| 3 | near_miss/NM-14 | near_miss | out_of_scope | forecast | out-of-scope accepted | not_available | Forecast technician staffing headcounts needed in the West for the next 4 weeks. |
| 1 | near_miss/NM-20 | near_miss | out_of_scope | forecast | out-of-scope accepted | not_available | Can I see the dispatch calendar for all maintenance jobs tomorrow? |
| 2 | near_miss/NM-20 | near_miss | out_of_scope | forecast | out-of-scope accepted | not_available | Can I see the dispatch calendar for all maintenance jobs tomorrow? |
| 3 | near_miss/NM-20 | near_miss | out_of_scope | forecast | out-of-scope accepted | not_available | Can I see the dispatch calendar for all maintenance jobs tomorrow? |
| 1 | out_of_scope/OOS-01 | out_of_scope | out_of_scope | reporting | out-of-scope accepted | not_available | What was our total billed revenue from Ironwood Manufacturing last month? |
| 2 | out_of_scope/OOS-01 | out_of_scope | out_of_scope | reporting | out-of-scope accepted | not_available | What was our total billed revenue from Ironwood Manufacturing last month? |
| 3 | out_of_scope/OOS-01 | out_of_scope | out_of_scope | reporting | out-of-scope accepted | not_available | What was our total billed revenue from Ironwood Manufacturing last month? |
| 1 | out_of_scope/OOS-03 | out_of_scope | out_of_scope | reporting | out-of-scope accepted | not_available | How many hours of overtime did Elena Nakamura log during the past 2 weeks? |
| 2 | out_of_scope/OOS-03 | out_of_scope | out_of_scope | reporting | out-of-scope accepted | not_available | How many hours of overtime did Elena Nakamura log during the past 2 weeks? |
| 3 | out_of_scope/OOS-03 | out_of_scope | out_of_scope | reporting | out-of-scope accepted | not_available | How many hours of overtime did Elena Nakamura log during the past 2 weeks? |
| 1 | out_of_scope/OOS-14 | out_of_scope | out_of_scope | reporting | out-of-scope accepted | not_available | How much did we spend on technician mileage reimbursements last quarter? |
| 2 | out_of_scope/OOS-14 | out_of_scope | out_of_scope | reporting | out-of-scope accepted | not_available | How much did we spend on technician mileage reimbursements last quarter? |
| 3 | out_of_scope/OOS-14 | out_of_scope | out_of_scope | reporting | out-of-scope accepted | not_available | How much did we spend on technician mileage reimbursements last quarter? |

## 2. Golden run: failed items (mechanical score, golden_scoring.md)

| ID | Components | What failed | Question |
|---|---|---|---|
| G03 | C1 False, C2 True, C3 None | outcome=not_available reason=None route=reporting | which district had the worst SLA breach rate between June and August? |
| G05 | C1 True, C2 True, C3 False | range 2026-07-01..2026-07-31 is not an acceptable range | why did CSAT crater after the storm last weekend? |
| G07 | C1 True, C2 True, C3 False | weeks differ: 8 returned, 26 expected | how many total dispatches are we looking at through the end of next year? |
| G08 | C1 False, C2 False, C3 None | outcome=not_available reason=None route=forecast; route=forecast | what's our projected overtime labor spend for field techs this month? |
| G21 | C1 True, C2 True, C3 False | p_value got 0.3349, expected 0.334895628510519 | Is customer sentiment getting worse in the Northeast? |
| G28 | C1 False, C2 True, C3 None | outcome=answered reason=None route=forecast | What will volume be in Q2 2027? |
| G35 | C1 False, C2 False, C3 None | outcome=not_available reason=None route=reporting; route=reporting | How's the Southeast doing? |

Golden: 29/36 pass the mechanical score. `must` and `must_not` are not part of it (owner review; see `evals/results/sprint5_x/golden_owner_review.csv`).

## 3. Disclosures, verbatim

1. ADR-094's sentence: "In a real deployment, evaluation sets would come from real user questions and subject-matter experts. Here they were generated by an independent model under a written brief; the owner reviewed the brief and spot-checked the ambiguous labels."
2. "The sets were generated, not owner-written."
3. The persona-drop selection effect (L-86, update 2026-10-11): (1) The owner's drops at the skim were made on persona grounds: a question a dispatcher or call-centre agent would ask, but not a senior operations leader with an overview of the business unit (the brief's stated asker). Labels were not changed, and the owner had not seen any system output. Five of the 31 skimmed rows were dropped (all `ambiguous`). Persona drops may remove the more granular, operational questions, which leaves the sets weighted toward broad leadership questions.
