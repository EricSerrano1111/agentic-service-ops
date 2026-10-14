# Golden run: the assistant's reading of `must` / `must_not`

**Assistant opinion. Not the score.** The score is mechanical (`golden_scoring.md`, 29 of 36). The
owner judges `must` and `must_not` in `golden_owner_review.csv` during Prompt Y; where this file
disagrees with the owner, the owner's call stands. "Met" means the answer text does what the
criterion says; it is a reading of the text, not a check of any figure beyond the mechanical score.

Run: 2026-10-13, deployed `9607fa72`, paid mode. Answers are in the review CSV.

| ID | Mechanical | My reading of `must` / `must_not` |
|---|---|---|
| G01 | pass | must met (names no match), no figures, no substitute. |
| G02 | pass | Declines the city and says other areas are not mapped to a region. It does not use the word "city-level figures", but the sense is met. No Chicago figures. |
| G03 | **fail** | must not met: no ranking, no range stated. The answer is "That breakdown isn't supported yet" (the parse read "district" as an unsupported breakdown). Nothing in must_not breached. |
| G04 | pass | Counts, shares and range stated; says the range was assumed. It quotes comments verbatim and invents no theme or app-update date. It does not say the "since the app update" qualifier was ignored; that is a stretch gap. |
| G05 | **fail** | must not met: gives July 2026, not a weekend, and says it assumed the range. must_not met: no cause, no trend asserted. The "storm last weekend" qualifier is silently dropped (stretch, L-56). |
| G06 | pass | Names the supported slices; no numbers. Does not mention "emergency" (not needed by `must`). |
| G07 | **fail** | must not met: shows 8 weeks starting 2027-01-04, not weeks 1 to 26 from 2026-08-31, and gives no 1-4 or 5-13 band errors (only 14-26). It does say 44 weeks are beyond the horizon. must_not met: no figure beyond 2027-02-28, no total range. See the flag below. |
| G08 | **fail** | Declined by the forecast agent ("That isn't something I can forecast"), not as out of scope. Names what the forecast covers, not all three domains; no figures. |
| G09 | pass | Names both areas (generically) and asks for separate questions. |
| G10 | pass | Withholds weeks 1 to 3 with 43.7%, serves 2026-09-28 with 18.0%. **must not met:** it never says the figures are for all installs, not fiber. must_not "treat fiber as all installs without saying so" is breached by that omission. The mechanical score does not see this. Stretch. |
| G11 | pass | Rate, counts, range and as-of met. |
| G12 | pass | Worst first with counts. "46 accounts in total; the worst 25 are in the data" is how it states the left-out groups; no account under 20 jobs ranked. |
| G13 | pass | Worst first, counts, July 2026. |
| G14 | pass | Total and the three counts. |
| G15 | pass | Priya Kim's rate and "based on 127 dispatched requests". |
| G16 | pass | Lists both, asks for the full name, no figures. |
| G17 | pass | Range 2026-08-17 to 2026-08-30. |
| G18 | pass | Overall count and rate; repeat visits "recorded through a repeat-visit-required incident"; worst first; "No region stands out". |
| G19 | pass | Says unsupported and lists the supported metrics. |
| G20 | pass | Counts, shares, flagged count, range and as-of. |
| G21 | **fail** (4-place p) | Mechanically, every figure matches; only `p_value` is 0.3349 against the oracle's full-precision value (scorer tolerance 1e-6). On the text, all of `must` is met and "worse" is not claimed. See the flag below. |
| G22 | pass | Three mixed June comments (the CSV has the text). |
| G23 | pass | Says account breakdowns are not supported and names what is. |
| G24 | pass | Same for service type. |
| G25 | pass | Six weeks, 80% ranges, total with no range. The two band errors are printed (the text is cut in my excerpt; the CSV has all of it). |
| G26 | pass | Four weeks, 10.8% for 5 to 13. |
| G27 | pass | Both band errors stated, no numbers. |
| G28 | **fail** (outcome label) | Text meets `must` ("beyond the 26-week forecast horizon, so none is forecast") and shows no figures. Only the outcome is `answered` where the item accepts `not_available`. |
| G29 | pass | Names the supported slices. |
| G30 | pass | Says unsupported, lists what is supported, no figures. |
| G31 | pass | Declines; names the coverage. It does not say "the system doesn't take actions" in those words. No reassignment implied. |
| G32 | pass | Declines, names the coverage, no weather. |
| G33 | pass | Names both, asks for separate questions. |
| G34 | pass | Same. |
| G35 | **fail** (expected, L-58) | Routed to reporting and answered "That metric isn't supported yet". Under `route_v3` there is no `ambiguous` route, so no clarification. No figures shown. |
| G36 | pass | Says only request volume is forecast; no figures. |

## Items whose expectation may be wrong (for the owner; the set is not edited)

- **G07.** The expectation takes "through the end of next year" to mean weeks 1 to 26 from now. The system read it as the calendar year 2027 and so skipped September to December 2026. The oracle's reading is at least as plausible as the system's; I would not call the expectation wrong, but the question is ambiguous about the start of the period. A `golden_v3` could name the intended period.
- **G03.** The owner wrote "district"; the oracle reads it as region. The data has no districts. Whether "district" should map to region is a product question, not an oracle error.
- **G21.** The expectation is right; the scorer's tolerance did not allow for the 4-place p-value the agent reports and shows (ADR-068 style display). Not an item problem; a note on the rule.
- **G28.** `acceptable_outcomes` lists `not_available` only; `answered` with an empty week list and "beyond the horizon" text is a defensible alternative. The schema's behaviour for "decline" does not fit a forecast that says nothing is forecastable.

## The check notes (sprint log, 2026-10-08 and 10-09)

| Note | Items | Answer against the oracle |
|---|---|---|
| One region (ADR-086) | G04, G20, G21 (Southeast / Northeast sentiment) | Counts, shares and flagged counts equal the oracle's (G21 except the p rounding). The expectations hold under ADR-086; nothing to flag. |
| One account (ADR-086) | G12 (by account) | Top 5 accounts in the same order with the same counts. Expectation holds. |
| Tie order (L-72 ruling 2) | G03, G12, G13, G18 | G12, G13, G18 equal the oracle's order. G03 never ranked (declined). Expectation holds where answered. |
