# Report format (frozen with catalogue_v1.yaml)

`report.py` writes `report.md` from `results.json` in exactly this order. The definitions
below are fixed before any measurement run.

0. **Authorship and not-blind statement**, at the head and the foot. Assistant-drafted faults
   (R, F, S, K, M) were written by the assistant that built QA and know what QA checks.
   Owner-selected, AI-co-written faults (O) are reported in their own section, never mixed into
   the assistant-drafted totals.
1. **Clean base answers and controls**, per agent: answers, declines, controls run, false
   alarms (controls QA failed), items excluded.
2. **Overall catch rate on the caught-expected faults**, assistant-drafted classes `injected`
   and `database`, per agent and in total: number of faults, number of cases (state both),
   caught over cases with a 95% Wilson interval, and caught-by-an-expected-check over cases.
   A case is *caught* when QA's verdict is `fail`. It is *caught by an expected check* when a
   check named in the catalogue's `expected_checks` also failed.
3. **Per fault**: cases, caught, caught by an expected check, the checks that fired (with
   counts), and cases skipped.
4. **Misses**: every caught-expected case QA passed, with the base item, the question, the
   checks that ran and passed, and the case's note. The reason a check did not fire is written
   by hand after the run, in the results' README, not generated.
5. **False alarms**: failed controls over controls run, per agent, with each failing check.
6. **Rating sensitivity**: per contradiction level (0.5, 1, 2, 4, 8%), cases, covered-n range,
   cases the pre-registered rule (ADR-087: n >= 20 and P(X >= x | n, 0.01) < 0.01) predicts
   caught, cases QA caught, and cases where QA agrees with the rule; every disagreement listed.
7. **Known gaps**: consistent-misparse cases per agent, caught over cases, and cases with an
   advisory logged (always 0 with the fake interpretation client; the reading is kept).
8. **Owner-selected faults**, separately, one line per variant: owner's expected outcome,
   cases, caught, the owner's exact question's verdict and checks, and the recorded notes
   (shares reached, contradiction rates).
9. **Database integrity**: row counts and the predictions checksum before and after, per
   database case and for the whole run.
10. **Applicability and skipped cases**: applicable base answers, cases run and the reasons for
    skips, per fault.
11. **Not blind** statement.

Rules: no target rate is set; a miss is reported as measured; a fix for a miss goes in a
separate PR that re-runs this same frozen catalogue and seed and is reported as a second
measurement beside the first, never replacing it.
