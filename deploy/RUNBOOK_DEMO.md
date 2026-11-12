# Runbook: the live demonstration (ADR-117 item 6)

Written 2026-10-29 (ADR-117 item 6; owner inputs 2026-10-29; assistant-drafted). Not yet run. Windows
PowerShell 5.1, from the repo root, with `.venv` built. Every `gcloud` command carries `--project`.

**Owner inputs, 2026-10-29.**
- **Format:** live over Zoom, the owner sharing the screen.
- **Slot:** 60 minutes. Part 1 is a 30-minute overview. Part 2 is 10 to 20 minutes of instructor questions. The
  instructor holds the remaining 10 to 20 minutes as a buffer. **This plan does not use the buffer;** it is
  there only for recovering when something goes wrong.
- **No recording** (owner, 2026-10-29; ADR-119). The demonstration runs live, and nothing stands in for it.
- **Date and time:** `[TBD]`. Slots are announced about 11-15 to 11-22 and the owner chooses. **Prefer a slot
  inside Window B** (2026-12-01 to 12-12, ADR-107). A slot outside it means a new ADR to move the window.
  - *2026-11-12 (ADR-122; owner-decided; assistant-drafted.)* The warm instances of section H apply whatever the slot's date. A slot before 2026-12-01 still needs its own window ADR before section A's day-before steps are run (note under A1).
- **No slides** (ADR-117). The visual aids are the system's own pages (landing, How it works, Evaluation
  results), the public repository and the evaluation report.
- **Rehearsal:** the narration is rehearsed offline with the tabs. The only live run-through is A3, the day
  before.

**Deadline:** one owner deploy session before 2026-11-09 (Preconditions).

```powershell
$P  = 'a2a-agentic-service-ops-gcp'
$R  = 'us-central1'
$N  = '587647038690'
$G  = "https://ops-gateway-$N.$R.run.app"   # the deterministic host: the only one invites may carry
$S  = "projects/$N/secrets/gateway-invites"
```

**Sources used.** Every figure below is copied from a document named beside it. A fact the documents do not
hold is `[TBD]`, and a thing only the owner can say is `[OWNER]`. Nothing here comes from memory.

---

## Preconditions: read this before anything else

The plan below needs a live system that the records say does not yet exist. **One owner deploy session, before
2026-11-09,** puts it right. There is no recording and no rehearsal session (owner, 2026-10-29).

1. **The session uses the `owner-laptop-3` invite.** It expires 2026-11-09 23:59 (ADR-118,
   `docs/sprint-log.md`), so the session must end before then. Window B needs a new owner invite and the grader's
   (`RUNBOOK_GRADING.md`, "Open the window", steps 3 and 4).
2. **What the session does.**
   - **Deploys the L-105 fixes and the Evaluation results page.** Build `0b96ca2a` (commit `b6fa907`) deployed on
     2026-10-28 without them (`docs/sprint-log.md`, 2026-10-28: "The evaluation-results page and the
     demonstration runbook ... were not part of this deploy"; 2026-10-29: "merged, not deployed"; L-105,
     2026-10-29: "Deploys in the next window"). ADR-117 allows it: "Item 4 may deploy in a second small window if
     it misses the first." The deploy follows `RUNBOOK_V.md` and the 2026-10-28 procedure in
     `docs/deploy-window-log.md`. It ran on 2026-10-30 (`docs/deploy-window-log.md`, 2026-10-30). This runbook does not run it.
   - **Takes a current screenshot of each live example,** in light theme, at the browser zoom chosen in A4, from
     the signed-in page: the SLA answer, the answer journey, the sentiment answer, the forecast answer, the
     clarification ("How's the Southeast doing?") and the revenue decline. Save them under
     `docs/screenshots/demo-session-2026-10-30/`, one file per example. They replace the 2026-10-23 screenshots,
     which predate the deploy. They are committed in a later change.
3. **The session is an ADR-110 owner verification session.** `ops-db` is started and stopped in one sitting, with
   no grader invite and the paid balance at **$5 or more**, checked in the console (ADR-110). It gets a dated
   entry in `docs/deploy-window-log.md`. Run `RUNBOOK_GRADING.md`, "Open the window" steps 1 and 2 and the smoke
   check (step 5), and "Close the window" steps 2 to 4. Steps 3 and 4 of opening (a grader invite; renewing the
   owner's) are skipped: `owner-laptop-3` is the invite.
4. **Check whether the deploy has happened** (read-only; also a quick check before Window B):
   ```powershell
   curl.exe -4 -s -o NUL -w "%{http_code}`n" "$G/results/"
   gcloud run services describe ops-gateway --region $R --project $P --format "value(status.latestReadyRevisionName)"
   ```
   `200` from the first line means the page is served. The second line read `ops-gateway-00003-fgd` after the
   2026-10-28 deploy (`docs/deploy-window-log.md`, phase 2); the same name now means nothing newer has deployed.
   The trailing slash matters: the gateway redirects `/results` (L-105).
5. **If the deploy has not happened by the demonstration,** tab 3 does not exist. Show
   `docs/screenshots/results-page-2026-10-29/results-light-1280.png` and the report on GitHub (tab 5), and say so.

*2026-10-30 (deploy session; owner present; assistant-drafted.)* The deploy session ran on 2026-10-30 (`docs/deploy-window-log.md`, 2026-10-30): `/results/` is served, the L-105 fixes are live, and the screenshots are in `docs/screenshots/demo-session-2026-10-30/`. Item 2 is done; item 4's check now reads `ops-gateway-00004-zqw` (and `/results/` answers 200); item 5 applies only if the deploy is rolled back. **The system as left has an open failure (L-106): after an idle gap, a cold start of the reporting service or of QA can fail. Read section F before relying on a live run.** `owner-laptop-3` expires 2026-11-09 23:59.

*2026-11-12 (audit finding F-04, `docs/audits/2026-11-11-project-audit.md`; owner-decided; assistant-drafted.)* **The state as of 2026-11-11, replacing the stale lines above** (the audit's line numbers, at `0bab705`: the deadline at 19, the invite and revision names at 36-40, 64-65, 70 and 72, and, further down, the L-106 note and the ADR-120 note under section F).
- **The deploy sessions are over.** The ADR-120 deploy ran on 2026-11-11 as build `8b6493d8-5004-4e9a-9627-4e68a9dab296` at commit `8ec22db` (all 17 steps `SUCCESS`; ADR-121's pinned step images passed their first live run; `docs/deploy-window-log.md`, 2026-11-11; `evals/results/l106/2026-11-11/summary.md`). The 2026-11-09 deadline and the `owner-laptop-3` invite are history. Service code is frozen until after the demonstration (owner-decided 2026-11-11, `docs/sprint-log.md`), so `main` keeps matching `8ec22db`.
- **The six serving revisions, each at 100%:** gateway `ops-gateway-00005-m67`, orchestrator `ops-orchestrator-00012-t27`, reporting `ops-reporting-00010-xtq`, sentiment `ops-sentiment-00006-8jp`, forecast `ops-forecast-00006-nsf`, QA `ops-qa-00007-w9l` (read from the live services on 2026-11-12; the same names as `summary.md`). So item 4's gateway check now reads `ops-gateway-00005-m67`; a different name means something deployed after this note.
- **ADR-120 is deployed, and L-106 is open.** The owner-decided status line (2026-11-11): "Open; not reproduced on either configuration. … 0 of 8 starts of the pair failed … P2 (a retry after a degraded first answer) was not exercised. L-106 is neither reproduced, nor mitigated, nor fixed; ADR-120 is deployed and untested against the failure." So the "Not yet verified" in the ADR-120 note under section F is superseded: the cold-start test ran and passed its pre-registered verdict, and a retry after a degraded answer has still never run. **Read section F's L-106 guidance with that status, and section H for what ADR-122 does about it.**
- **Minimum instances are not set** (the "No minimum instances are set" line in section C and the L-106 note under section F say so, the latter with "listed for the next session"). ADR-122 sets them for the rehearsal and the demonstration only (section H).
- **The owner invite `owner-laptop-5` expires 2026-11-13** (17:10:59Z, as the owner read it; `summary.md`, "Rulings and disclosures"). No rehearsal or slot can fall before then (slots are announced about 11-15 to 11-22), so **a new owner invite must be made before the rehearsal:** on the rehearsal day, as step 4 of "Open the window" in `RUNBOOK_GRADING.md`. The expired one needs no revoke. No invite link or id is written here.

**Order:** deploy session (before 11-09) → Window B (grader invite, owner invite) → demonstration. The
demonstration's date is `[TBD]`. The slots are announced about 11-15 to 11-22 and the owner chooses. **Prefer a
slot inside Window B (ADR-107).** A slot outside it means a new ADR to move the window.

---

## A. The day before

1. **Open Window B** with `RUNBOOK_GRADING.md`, "Open the window", or confirm it is already open. Use
   `$end = [datetime]'2026-12-12 23:59'` (the file's own note for Window B).
   - Paid balance at **$5 or more**, read in the console (step 1; there is no API).
   - `ops-db` started and `RUNNABLE ALWAYS` (step 2).
   - The grader's invite, expiring 12-12 (step 3).
   - The owner's invite (step 4).
   - The smoke check (step 5). It also confirms the trigger is still disabled.

   *2026-11-12 (ADR-122; assistant-drafted.)* **A slot before 2026-12-01.** This step opens Window B, which ADR-107 puts at 12-01 to 12-12. A slot outside it needs its own window ADR first (ADR-119 item 5; the note at the top), and none exists. Do not run this step early on the strength of this runbook. ADR-122 itself (section H) applies whatever the date, but it needs `ops-db` running, so an earlier slot's window ADR must also cover starting it.
2. **Check the deprecations page for `gemini-3.5-flash-lite`** (L-104, R-15). The 2026-10-28 reading was the
   table row `gemini-3.5-flash-lite | July 21, 2026 | No shutdown date announced`, fetched with `curl`, the row
   itself and not a summary (`docs/deploy-window-log.md`, phase 0).
   ```powershell
   curl.exe -s -o "$env:TEMP\deprecations.html" https://ai.google.dev/gemini-api/docs/deprecations
   Select-String -Path "$env:TEMP\deprecations.html" -Pattern 'gemini-3.5-flash-lite' | Select-Object -First 3
   Remove-Item "$env:TEMP\deprecations.html"
   ```
   Read the row. **If it now names a shutdown date before the demonstration, stop.** Changing the model is a new
   decision (L-104: "This must be done before any role moves to a model newer than 3.5 Flash-Lite", and the
   evaluated system includes `temperature=0.0`). Do not change a model in the days before a demonstration.

   *2026-11-12 (audit finding F-01; owner-decided; assistant-drafted.)* **Use the new address, and treat "no row found" as a failed check.** `https://ai.google.dev/gemini-api/docs/deprecations` now answers `301` to `https://aistudio.google.com/docs/deprecations` (read 2026-11-12 with `curl -s -o /dev/null -w "%{http_code} -> %{redirect_url}"`). The `curl.exe -s` above, with no `-L`, saves a page with no table, so `Select-String` prints nothing, which reads like "no shutdown date". Fetch the new address with `-L` and read the row itself, not a summary:
   ```powershell
   curl.exe -sL -o "$env:TEMP\deprecations.html" https://aistudio.google.com/docs/deprecations
   Select-String -Path "$env:TEMP\deprecations.html" -Pattern 'gemini-3.5-flash-lite' -Context 0,3 | Select-Object -First 1
   Remove-Item "$env:TEMP\deprecations.html"
   ```
   **Expected** (assistant, `curl -sL` returned 200 with the table as raw text, 2026-11-12): the first match is the model's row, with the next lines "July 21, 2026" and "No shutdown date announced". Owner-read 2026-11-11: no shutdown date for `gemini-3.5-flash-lite`, listed as active. **The check fails if nothing prints, and it fails if the second line after the model name is not "No shutdown date announced".** Later matches on that page are other models' replacement columns and a notice about `gemini-2.5-flash`, not this row. If a shutdown date appears before the demonstration, the stop rule above applies unchanged.
3. **Run the whole of Part 1 once on the live system, timed** (the same signed-in browser, the same order as
   section D). **This is the only live run-through.** The narration is rehearsed offline with the tabs.
   - Write down the elapsed time the page shows for each question ("Answered in N.N s", data dictionary §6
     rule 7) and which questions were cold.
   - Note any example that misbehaves (rule 9: replace or remove it, and add a dated note there).
   - Part 1 asks 5 questions (A5). Do the two examples Part 1 does not use ("Which incident types were most
     common in July 2026?" and "Show examples of negative comments from last month") only if you want them ready
     for the instructor's questions.

   *2026-11-12 (ADR-122; owner-decided at gate W-G2; assistant-drafted.)* **This day is also the rehearsal of the warm-instance procedure (section H),** so demo day is not its first run. Run it for real, by the person who will run it on demo day, in this order, so L-106's next cold-start observation is kept (`docs/evaluation-report.md`, L-106, "Next step"; R-05, update 2026-11-11):
   1. `ops-db` up (H1), the minimums still at 0, and the services idle for 20 minutes or more.
   2. **Part 1 as written above, cold and timed.** This is the observation L-106 and R-05 name: record each "Answered in N.N s", which questions were cold, and any degraded answer.
   3. **Wait until every service has gone cold again:** about 15 minutes after the last Part 1 request each instance shuts down (`summary.md`, "Idle shutdowns"), so wait 20 minutes, and confirm with H3 (d)'s read (`Shutting down`, each service) using the time Part 1 began in place of `$t0`. **Without this wait the minimums are raised on services that are still running,** and H3 (b) may show no start line with the minimum's reason (the caveat in H3 (b)), so demo day would be the first observation of it, which defeats the rehearsal.
   4. Then H2 to H5 in full: capture, raise, readback, the three-question smoke check, **a 20-minute wait and one reporting question** (it must answer in seconds: a warm instance has to outlive the idle shutdown of about 15 minutes that every instance hit on 2026-11-11, `summary.md`, "Idle shutdowns"), lower, readback. **Record how long the six `--min` updates take** (on 2026-10-14 each `gcloud` call took 1 to 4 minutes, as noted in F) and what the `describe` shows, so the annotation name and the no-new-revision claim are observed, not assumed (ADR-122, Consequences).
   The rehearsal's warm period is about 1.5 hours, about $1 at list price; the wait in step 3 adds about 20 minutes of the evening, and no cost.
4. **Zoom check.**
   - Join a test meeting from a second device (a phone is enough).
   - Share the browser **window**, not the whole screen.
   - On the second device, confirm the code-style text and the source paths on the results page are readable.
     Set the browser zoom to what makes them readable (125% is a starting point). `[TBD]`: the zoom that worked.
   - **Use light theme.** The UI has no theme switch: `web/app/globals.css` follows `prefers-color-scheme`, so set
     Windows (and the browser, if it overrides) to light. Light holds up better under video compression (owner
     input).
5. **Count the model questions** against the daily cap. **ADR-097's cap is global, not per invite.**
   - **The daily cap** is **50 questions, counted by Pacific-time day, shared by every invite** (ADR-097; ADR-107
     keeps it at 50). **So the grader's questions on the same day do draw on the owner's 50.** If the grader works
     on the day of the demonstration, the demonstration can hit the cap. The grading is expected around 12-05
     (ADR-110, ADR-107).
   - **Every accepted question counts toward the 50, including a clarification, a decline and an error.** The
     gateway calls `daily_cap.take()` before it forwards the question, and nothing refunds it afterwards
     (`services/api_gateway/src/api_gateway/app.py`, the `ask` route). "Accepted" means it passed the session
     check, the body check and the hourly check, which run first.
   - **The per-invite cap** is **30 an hour** (ADR-107; the pre-6.5 build already carries it, evaluation report
     §2). It is keyed by invite id (ADR-097, note of 2026-10-12), so the grader's use does not touch the owner's
     hourly count. The hourly check runs before the daily one, so a question the daily cap refuses has already
     counted toward the hour. The sources do not say how the hour is measured, so this runbook does not either.
   - **Both counters are per instance and reset on a cold start** (L-88), so the cap is approximate. It is not an
     exact ceiling in either direction.
   - **The count for the demonstration day**, using the per-question model calls of 2026-10-28
     (`docs/deploy-window-log.md`, phase 4: 3 calls for an answer, 1 for a clarification or a decline):

     | Item | Questions | Model calls |
     |---|---|---|
     | Warm-up (C): reporting, sentiment, forecast | 3 | 9 |
     | Re-warm at segment 3 (C): the same three | 3 | 9 |
     | Part 1 live: SLA, sentiment trend, forecast, "How's the Southeast doing?", "What will revenue be next quarter?" | 5 | 11 |
     | **Part 1 with both warm-ups** | **11** | **29** |
     | Instructor's own questions, margin (my assumption: up to 10) | 10 | up to 30 |
     | **Total** | **21 of 50** | **about 59** |

     The "Show the answer journey" panel reuses the SLA answer and asks nothing. The list-price cost of Part 1 is
     about $0.006 (the five 2026-10-28 costs summed: $0.001792 + $0.001589 + $0.001516 + $0.000562 +
     $0.000507). The per-request cap is $0.02 (evaluation report §4.7). At 21 questions the hourly cap of 30 is
     not reached if they fall inside one hour.
   - **The day-before run** (5 questions) falls on a different Pacific-time day, so it does not draw on the
     demonstration day's 50.
   - **Before the demonstration:** `[OWNER]` ask the grader whether they plan to use the system that day, or
     choose a day they have said they will not.

*2026-11-12 (audit finding F-39; ADR-122; assistant-drafted.)* **The cap table above omits three questions the runbooks prescribe, and ADR-122 removes one.**

| Item | Questions | Model calls | Source |
|---|---|---|---|
| The table above, as written | 21 | about 59 | this step |
| + the idle-gap reporting question | 1 | 3 | the note at F, "ask one reporting question after a quiet period" |
| + the smoke check "How many incidents last quarter?" | 1 | 3 | `RUNBOOK_GRADING.md`, "Open the window", step 5 (counts toward the day only if Window B is opened that Pacific day) |
| + the recovery sequence's smoke check | 1 | 3 | F, recovery step 4 (only if recovery runs) |
| **As written, worst case** | **24 of 50** | **about 68** | |
| − the segment-3 re-warm (ADR-122 replaces it, the minimums being raised, H; owner-decided at gate W-G2) | −3 | −9 | C |
| **With ADR-122, worst case** | **21 of 50** | **about 59** | H4's smoke check keeps the warm-up's three |

Per question: 3 model calls for an answer, 1 for a clarification or a decline (as above). The idle-gap question cannot run cold while the minimums are 1 (note at F), so on demo day it is not asked; it is kept in the worst case as margin.

**Reading the headroom, read-only (no model call).** The gateway's counter is in process and cannot be read (L-88). The request log gives an upper bound: POST requests to `/api/ask` since Pacific midnight. It over-counts, because requests refused before the cap (no session, a bad body, the hourly cap) are logged too. **Validated 2026-11-12 against 2026-11-11:** the filter returned 18 requests, all HTTP 200, and `summary.md` ("Spend against the caps") records 18 questions through the gateway that day. Pacific midnight is 08:00Z under PST (2026-11-01 to 2027-03-14). Headroom is 50 minus the count; if it is below the worst case above, the cap, not the services, is today's risk (F, "The daily cap is reached"). Run it at T−75 and again before the T−30 smoke check (H).

PowerShell, the owner's terminal (read-only; the assistant may run it too):
```powershell
$pac   = [TimeZoneInfo]::FindSystemTimeZoneById('Pacific Standard Time')
$today = [TimeZoneInfo]::ConvertTimeFromUtc((Get-Date).ToUniversalTime(), $pac).Date
$since = [TimeZoneInfo]::ConvertTimeToUtc($today, $pac).ToString('yyyy-MM-ddTHH:mm:ssZ')
$f = 'resource.type="cloud_run_revision" AND resource.labels.service_name="ops-gateway" AND log_id("run.googleapis.com/requests") AND httpRequest.requestMethod="POST" AND httpRequest.requestUrl:"/api/ask" AND timestamp>="' + $since + '"'
(gcloud logging read ($f -replace '"','\"') --project $P --limit 500 '--format=value(timestamp,httpRequest.status)' | Measure-Object -Line).Lines
```
One line for the `!` prompt (Git Bash; `TZ=PST8` is the fixed UTC−8 that holds from 2026-11-01 to 2027-03-14):
```
SINCE=$(date -u -d "$(TZ=PST8 date +%Y-%m-%d) 08:00" +%Y-%m-%dT%H:%M:%SZ); gcloud logging read "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"ops-gateway\" AND log_id(\"run.googleapis.com/requests\") AND httpRequest.requestMethod=\"POST\" AND httpRequest.requestUrl:\"/api/ask\" AND timestamp>=\"$SINCE\"" --project a2a-agentic-service-ops-gcp --limit 500 '--format=value(timestamp,httpRequest.status)' | wc -l
```

## B. 30 minutes before

1. **The browser.**
   - A fresh profile, or a hard reload (L-105: until the fix is deployed a returning browser can show the
     pre-deploy UI; the owner saw exactly that on 2026-10-28).
   - **Redeem the owner invite before you start sharing.** The page sends the token, clears the fragment, and
     loads the app (ADR-097). Confirm the address bar shows **no** `#invite=...`.
   - The session lasts at most 12 hours (ADR-097), so redeem on the day, not the night before.
   - **Never share the GCP console's Secret Manager pages, or any invite link.**
2. **Tabs, in order.**
   1. The landing page (signed in).
   2. How it works.
   3. Evaluation results.
   4. The public repository's root (the GitHub page for `git remote get-url origin`).
   5. `docs/evaluation-report.md` on GitHub.
   6. `docs/decisions-log.md` on GitHub.
3. **Notes on a second screen,** not inside the shared window.
4. **Notifications off.**
   - Windows Do Not Disturb on.
   - Outlook, Teams and chat apps closed.
   - Zoom's own chat notifications muted, if you can.
5. **Network.** Wired if possible. Have a phone hotspot ready, with the Zoom app on the phone so you can rejoin by
   audio. If the PC's IPv6 to `*.run.app` black-holes, test with `curl.exe -4 -m 20 $G/health`
   (`RUNBOOK_V.md`, "Windows PowerShell 5.1 notes"; found 2026-10-14).

## C. 10 minutes before: warm-up

1. **Ask one question per area:** reporting, sentiment and forecast. Use the landing page's examples, which fill
   the input and do not submit it (rule 9).
   - Cold starts measured **26 to 61 s** in the browser on 2026-10-28 (26.3 s forecast, 26.9 s sentiment, 53.0 s
     and 61.2 s reporting); warm answers took about **3 s** (2.6 to 3.4 s) (`docs/deploy-window-log.md`, phase 4).
   - Ask these **before** joining the Zoom call, or before sharing.
2. **Confirm all three answered** (an answer, not a degraded result or an error).
3. **Ask nothing else** until the demonstration starts.

**Re-warm, and why.** The warm-up is at -10 minutes. Part 1's first live question is at 0:08, about 18 minutes
later, and the sentiment and forecast questions at 0:14, about 24 minutes later. The sentiment and forecast
services are separate from the reporting one, so the SLA question does not warm them.
- On 2026-10-28 a forecast question about 14 minutes after the last traffic still took 27.8 s (Q11,
  `docs/deploy-window-log.md`), and `RUNBOOK_V.md` step 12 treats 15 minutes idle as the cold condition.
- **No minimum instances are set:** `minInstanceCount: 0` in all six files under `deploy/cloudrun/`. Every service
  can scale to zero, and the documents do not say how long Cloud Run keeps an idle instance.
- **So re-warm at the start of segment 3 (0:06).** From a **second browser window that is not shared** (the Zoom
  share is the demonstration's browser window, so another window is not in it), resend the same three warm-up
  questions. The same browser profile keeps the same session, so they use the owner invite and its hourly count.
  They take 26 to 61 s cold and finish before segment 4 at 0:08.
- **If anything is still cold** when a live question is sent, narrate it (F: an answer over 30 s). The journey
  view (segment 5) is a good thing to talk through while a cold answer loads.

*2026-11-12 (ADR-122; owner-decided at gate W-G2; assistant-drafted.)* **Superseded while the minimums are raised.** With minimum instances of 1 on all six services (section H), the line "No minimum instances are set" above no longer holds, and nothing goes cold between T−60 and the end of the questions, so **the segment-3 re-warm is not done.** **C's warm-up becomes H4, the smoke check at T−30:** the same three questions from the landing page, asked before joining or sharing, each confirmed as an answer; the difference is that each is expected to answer in seconds (about 3 s warm on 2026-10-28, as cited above), not 26 to 61 s. **If the readback in H3 shows a service not at minimum 1, C and the re-warm apply to that service as written.**

## D. Part 1: the 30-minute overview

**Plan for 27 minutes,** which leaves 3 in hand. The segment times: 2 + 4 + 2 + 3 + 3 + 4 + 3 + 4 + 2 = **27**.
Each "say" is meant to be spoken in your own words; the sentences are the facts and their sources.

### 1. The problem: 0:00 (about 2 min)
- **On screen:** the landing page (tab 1).
- **Say:**
  - This is a multi-agent assistant over a synthetic field-service dispatch database. An orchestrator routes each
    question over A2A to a reporting, sentiment or forecast agent, each calling scoped tools through its own MCP
    server, and a QA agent checks the answer before it returns (evaluation report §1).
  - Everything here is synthetic: the notice at the top says "all data here is synthetic, generated for this
    project", and that the sentiment model was trained on synthetically written feedback (data dictionary §6,
    rule 6, revised 2026-10-22).
- **The audience should see:** the product name "Service Ops Intelligence", the synthetic-data notice, and the
  grouped example questions (rule 9).

### 2. The architecture: 0:02 (about 4 min)
- **On screen:** How it works (tab 2).
- **Say:**
  - A question goes to the orchestrator, which routes it to a specialist over A2A. Each specialist has its own
    MCP server as a sidecar, and that server holds only its own least-privilege database role (README,
    "Deployed architecture"; ADR-079; `docs/security-model.md`).
  - The QA agent has its own read-only role and its own SQL; it recomputes the figures independently, and the
    orchestrator owns the QA loop (ADR-055; `docs/security-model.md`, guarantee 4).
  - The gateway is the only public service, with invite-link access (ADR-097). Everything runs on Cloud Run over
    Cloud SQL (README).
  - **Why A2A and MCP at this scale?** At five agents in one codebase A2A is not necessary. It is a deliberate
    choice for portfolio value and a swappable orchestration contract, not a claim of necessity (ADR-001).
- **The audience should see:** the services diagram and the route of one question.

### 3. The code: 0:06 (about 2 min)
- **At the start of this segment, re-warm** (C, "Re-warm, and why"): in the second, unshared browser window, send
  the three warm-up questions again. They finish while you are in segment 3.
  - *2026-11-12 (ADR-122; assistant-drafted.)* Skipped when the minimums were raised and read back (section H); the note under C says why.
- **On screen:** the repository root (tab 4), then `docs/decisions-log.md` (tab 6) at ADR-001.
- **Say:**
  - `services/` holds the agents and MCP servers, `deploy/` the Cloud Run definitions and runbooks, `evals/` the
    evaluation sets and results, `docs/` the design records (README, "Repository layout").
  - Every locked decision is an ADR with the alternatives considered. ADR-001 is the example: it says plainly
    that A2A was not required at this scale.
- **The audience should see:** the folder layout and one ADR's "Alternatives considered" and "Consequences".

### 4. Live: the SLA example: 0:08 (about 3 min)
- **On screen:** landing page. Click "What was SLA compliance in the Northeast last month?" and send it.
  - If the warm-up did not hold, this may take up to about 60 s. Narrate the route while it loads (F).
- **Say:**
  - The large number is the headline figure. It is the figure exactly as it appears in the answer text, and it
    is shown only for a verified single-figure reporting answer (rule 8). On 2026-10-28 the answer was **88.13%
    (141 of 160)** (`docs/deploy-window-log.md`, phase 4, Q1).
  - "Interpreted as" is the system showing how it read the question, including the dates it resolved, so you can
    catch a misparse (rule 2). The data's as-of date is 2026-08-30 (evaluation report §2).
  - The verification line says "Figures checked for the request as interpreted. Check that the 'Interpreted as'
    line matches your question." **It does not say the question was understood.** The interpretation check
    failed its gate twice and is advisory (rule 3; L-74), and "verified" means QA's recomputation agrees, not that
    the definitions are right (L-75).
- **The audience should see:** the headline, the "Interpreted as" line, the verification line and the timer.

### 5. Live: the answer journey: 0:11 (about 3 min)
- **On screen:** the same answer. Click "Show the answer journey".
- **Say:**
  - The diagram highlights the services that were called, in order, and dims those that were not. The timeline
    shows each hop's duration, measured by the service that ran it (rule 10).
  - The chips show the model calls, the estimated cost (a list-price estimate, L-71) and QA's checks. On
    2026-10-28 the SLA answer took 3 model calls and cost $0.001792.
  - The journey never carries a figure, the question text or an error message (rule 10). The browser timer is
    shown separately because it includes the network and any cold start (rule 7).
- **The audience should see:** the highlighted route, the timeline bars, and the three chips.

### 6. Live: sentiment and forecast: 0:14 (about 4 min)
- **On screen:** "Is negative feedback trending up in the West?" then "What weekly request volume should we expect
  for the next 8 weeks?" Send each in turn.
- **Say (sentiment):**
  - Deployed sentiment reads **stored, offline-scored predictions** only, and no customer comment is sent to a
    language model at answer time (ADR-100; `docs/security-model.md`, guarantee 9).
  - The trend compares the latest month against the pooled earlier months with a two-proportion test, and the
    answer names the months it compared (data dictionary §6, sentiment rule 6).
- **Say (forecast):**
  - The answer gives ranges, and shows the model's held-out error beside each band. Slice-bands that did not
    pass the release gate are withheld, not shown with a number: 5 of 18 are served (results page; ADR-071;
    `docs/security-model.md`, guarantee 10).
  - **Be ready for a question about the error.** On 2026-10-28 the held-out error was larger at 1 to 4 weeks
    ahead (13.6%) than at 5 to 13 weeks (5.5%). That is unusual; it is the model's evaluation on this data and
    nothing was changed (`docs/deploy-window-log.md`, phase 4, forecast reader's note). Check the figures on the
    day against what the page shows.
- **The audience should see:** the sentiment buckets and the stated comparison; the forecast ranges and the
  error with each band.
- *2026-10-30 (deploy session; assistant-drafted.)* **The sentiment example can split.** "Is negative feedback trending up in the West?" failed its caption once on 2026-10-30: the router answered `split_required` ("Your question covers more than one area… please ask about each separately") and called no specialist. The same question passed on a retake that day and on 2026-10-28 (L-58 update; data dictionary §6, rule 9). If the split appears live, narrate it as the router asking for one question at a time, which is a designed outcome, then resend the question once or use the other sentiment example. No screenshot of the split exists. A stability check of all seven examples is planned.

### 7. Live: the boundaries: 0:18 (about 3 min)
- **On screen:** "How's the Southeast doing?" then "What will revenue be next quarter?"
- **Say:**
  - The first is too open, so the system asks you to choose (`needs_clarification`, `intent_ambiguous`; one model
    call on 2026-10-28; no verification line, because there are no figures to check, L-99). The second is out of
    scope, and the system declines (one model call).
  - **The honest FR-03 line** (evaluation report §1): FR-03 is **not met**. `route_v6`, the router now deployed,
    recognises 10 of 15 ambiguous items against 0 of 15 for the evaluated router, below the 75% floor, and the
    comparison is post hoc on sets already used (§6). About one ambiguous question in three is still best-fit
    routed (ADR-116).
- **The audience should see:** the clarification card and the decline, each without a verification line.

### 8. The evaluation: 0:21 (about 4 min)
- **On screen:** Evaluation results (tab 3).
- **Say, the method** (evaluation report §3, §6):
  - Gates were committed before the runs they judge (pre-registration). The sets are held out. Routing
    evaluations run three times (k=3, ADR-054).
- **Say, three or four figures** (the results page; each is on screen with its source path):
  - Held-out routing: **38 of 50** in each of three runs, and **38 of 43** without the 7 ambiguous items.
  - QA fault catch rate: **219 of 223** at first and **223 of 223** after fixes.
  - Forecast: `volume_v2` **8.81%** error against **14.80%** for seasonal naive on the 26-week holdout.
  - FR-03: **10 of 15** against **0 of 15**, tagged post hoc.
- **Read aloud the caveats, verbatim** (data dictionary §6, rule 11; the page prints them):
  - "All data in this system is synthetic."
  - "The evaluation sets were generated by a model of the same family as the system; 10 golden items are
    owner-written."
  - "QA's catch rate is an upper bound: its author drafted the faults."
  - "`route_v6`'s comparison was made after the results, on sets already used."
  - "These figures describe the evaluated Sprint 5 system unless marked otherwise."
- **The audience should see:** the cards, the tags on the figures that are not from the evaluated system, and the
  source paths in small type.

### 9. Production-grade, cost, what's next: 0:25 (about 2 min)
- **On screen:** the Production-grade card on the results page, then tab 5 at §8 or §9.
- **Say:**
  - **11 of the 12** production-grade checklist items are met. Item 5 (retries, timeouts, breakers) is met
    offline only, because no breaker or retry has acted live (evaluation report §8; the page says so under the
    card).
  - **Cost:** the held-out routing and golden run cost $0.172689 for 186 requests at list price, and the most
    expensive request was $0.001737 (§4.7). The 2026-10-28 window's 12 questions cost $0.0164 against a $0.40
    cap (§4.7). The database costs about $0.30 a day while it runs (owner-reported estimate, ADR-105), so it is
    stopped outside windows. The prepaid balance is the real spend ceiling (§4.7, L-93).
  - **What a real deployment would need:** real data and real users' questions for the evaluation sets (§3); user
    accounts and shared counters in place of invite links with per-instance limits (L-88); and the roadmap items
    not built: Terraform, the `verify-caller` account, a no-traffic deploy (L-64) and the batch-scoring job
    (ADR-100) (`docs/sprint-log.md`, "Planned vs done", 2026-10-18).
  - Hand over to questions.

**Never inject a fault live.** If asked about degradation, show the constructed image and say it is constructed
(section F), then describe the 2026-10-28 live test (evaluation report §10; `docs/deploy-window-log.md`, phase 5):
the forecast hop's timeout was set to 0.5 s on a healthy service, and the question returned `degraded` with HTTP
200, no figure, and "Not checked: the request ended before verification ran." The metric read 1 and the alert
emails arrived (owner-reported). It was one failure, so no breaker opened, and only the forecast service was
tested live (§8). No screenshot was taken of that live test.

## E. Part 2: instructor questions (10 to 20 minutes)

1. **Answer from the documents.** If a question needs evidence, open the matching tab (an ADR, a ledger, a
   result file, a test) rather than describing it.
2. **If the instructor asks you to try a question live,** type it as given.
   - If it is out of scope, the decline is itself the demonstration.
   - If it is ambiguous and gets best-fit routed, say so: about one ambiguous question in three still is
     (ADR-116, L-58).
3. **Questions and answers.** Each answer is 1 to 3 sentences, with its source.

| # | Question | Answer, and source |
|---|---|---|
| 1 | Why A2A and MCP at this scale? | At five agents in one codebase A2A isn't strictly needed. It was a deliberate choice to show protocol fluency and keep the orchestration contract swappable, not a claim of necessity. MCP is each specialist's own tool layer (ADR-001). |
| 2 | How do you know a figure is right? | The QA agent recomputes it with its own read-only SQL, and the orchestrator returns it only when QA agrees (ADR-055; `docs/security-model.md`, guarantee 4). "Verified" means the figures are right for the request as parsed. It does not mean the question was understood or the definitions are right (data dictionary §6 rule 3; L-74, L-75). |
| 3 | Why synthetic data, and what does that limit? | There is no real dispatch data at this scale, and the project is a synthetic-data capstone by design (L-102). So no figure shows how the system does on real service data. For example the first-time fix rate is about 98%, higher than real operations (L-01). |
| 4 | Why didn't FR-03 pass, and what did you do? | Ambiguous questions are still sometimes best-fit routed. Three attempts failed their pre-registered gates (ADR-075/076, ADR-101: 4 of 8 recognised, 6 needed; ADR-114: no-go). I then made `route_v6` the default on held-out evidence, 10 of 15 recognised against 0 of 15, and recorded FR-03 as not met (ADR-116; evaluation report §6). |
| 5 | Why this model, and what if it's deprecated? | Every role runs `gemini-3.5-flash-lite` (§2); ADR-049 kept the orchestrator on Flash-Lite on measured evidence. The deprecations page lists no shutdown date, read 2026-10-28 (L-104, R-15), and I check it the day before. Moving to a newer model needs a new decision and a fix for the `temperature` parameter first, and it would change what the report describes (L-104). `[OWNER]` your own words on the choice. |
| 6 | How much does it cost to run? | The 2026-10-28 window's 12 questions cost $0.0164 at list price (§4.7). The database costs about $0.30 a day running, so it is stopped by default (ADR-105). The caps are 50 questions a day and 30 an hour per invite, and the prepaid balance is the real ceiling (ADR-097, ADR-107, L-93). |
| 7 | How is data protected? | No agent role can read `contacts`, so customer PII never enters a prompt. The sentiment role sees four feedback columns, the forecast role three request columns, and every runtime role but one is read-only (`docs/security-model.md`, guarantees 1 to 4 and 7). The gateway is the only public service, with revocable invite links, hashed tokens, a signed session cookie and rate limits (ADR-097). Its limit: a session identifies an invite, not a person, and the auth code has had no independent review (L-88). |
| 8 | What stops a prompt or SQL injection reaching the database? | A user's words never become SQL: they become a typed request, the agent's code picks a fixed tool, and each value is an enum or a bound parameter. No MCP server exposes raw SQL, and no model is given a tool (`docs/security-model.md`, "Where user text meets SQL" and section 3). Customer comments never reach a model at answer time (guarantee 9). What an injected question can still do is get a wrong route or parameters, inside that specialist's grants. QA's one model call can at worst flip its own verdict (guarantee 12). |
| 9 | What happens when a part fails? | After 120 s, or on a failed hop, the system returns a defined degraded result (HTTP 200, no figure, "not verified") and the alert fires. This ran live on 2026-10-28 on the forecast hop, induced by a 0.5 s timeout; no breaker opened (§8, §10). A database outage behind a healthy agent is still a 502 error and not the degraded result (L-89). With `ops-db` stopped the gateway says "The data service is unavailable right now." (ADR-105). |
| 10 | How were the evaluation sets made, and why trust them? | A model, `gemini-3.8-flash`, wrote the routing, FR-03, interpretation and parse sets from a brief the assistant wrote and I reviewed; no item was edited after generation (ADR-094; §3). The golden set has 10 owner-written and 26 drafted items. Same model family (L-86). The rules were committed before the runs and the caveats are printed on the page. I don't claim these figures show real-user performance (§9). |
| 11 | What would you change for a real deployment? | Evaluation sets from real user questions and subject-matter experts (§3). Real data (L-102). Per-user accounts and shared-state limits in place of invite links (L-88). The roadmap items: Terraform, the `verify-caller` account, a no-traffic deploy (L-64), the batch-scoring job (ADR-100), and `min_instances` for the first-answer wait (ADR-107). |
| 12 | How were AI tools used in building it? | The records mark every dated entry "assistant-drafted" and "owner-decided". For example, in the 2026-10-28 deploy window I ran every state-changing GCP command by hand, ten in all, and the assistant ran only read-only checks (`docs/deploy-window-log.md`, "Who ran what"). The assistant drafted most of QA's injected faults and the evaluation briefs, which is why those figures are upper bounds or same-family (L-85, ADR-094). `[OWNER]` your own words: what you used it for and what you checked yourself. |
| 13 | What would you do differently? | `[OWNER]` |
| 14 | Why is the forecast error larger at 1 to 4 weeks than at 5 to 13? | It is the model's held-out evaluation on this data. It looked unusual on 2026-10-28 and I didn't change anything (`docs/deploy-window-log.md`, phase 4). The figure on screen is what the page shows on the day. |
| 15 | Why is the first answer after a quiet period slow? | A cold start: Cloud Run starts new containers down the chain (gateway, orchestrator, specialist, QA). It measured 26 to 61 s on 2026-10-28, inside the 120 s ceiling (§4.6, §10; R-05). Keeping a service warm (`min_instances`) was rejected for now as a standing cost to remove a delay inside the deadline (ADR-107). |

*2026-11-12 (ADR-122; assistant-drafted.)* **Rows 11 and 15 changed.**
- **Row 15 (why is the first answer slow):** on the day it should not be, because the services are held warm for the rehearsal and the demonstration (section H). Say that first, then the cold start as history: a cold reporting question took 42 to 58 s on 2026-11-11 (26 to 61 s on 2026-10-28), inside the 120 s ceiling (R-05). If asked why they are not left on: it is a cost choice. Instance-based billing makes the nine containers about $0.62 an hour at list price, about $177 for the 12 days of Window B, so they are warm for the two days that need it (ADR-122; ADR-107 still holds for the rest of Window B).
- **Row 11 (what would you change):** `min_instances` is no longer only a roadmap item; it is used for the demonstration. What a real deployment would still change is that the setting should not need an operator to raise and lower it, and that a cold start can fail at all (L-106 is open; its cause was never found).
- Everything else in rows 11 and 15 stands.

## F. If something goes wrong

There is no recording and no fallback video (owner, 2026-10-29; ADR-119): the demonstration runs live.

| Problem | What to do |
|---|---|
| An answer takes over 30 s | Say it's a cold start (R-05), and narrate the journey while waiting. Measured: 26 to 61 s on 2026-10-28, inside the 120 s ceiling. |
| A single example fails | Show its screenshot from the deploy session (`docs/screenshots/demo-session-2026-10-30/`), say so plainly, and move on. |
| The sentiment example answers "please ask about each separately" (a split, seen 2026-10-30) | Narrate it as designed: the router asking for one question at a time. There is no screenshot of the split to show. Resend once, or use the other sentiment example (L-58 update). |
| "The reporting service is temporarily unavailable", or "Not verified: the checking service was unavailable", after an idle gap (L-106) | A cold start of the reporting service or QA failed. Read the dated note below this table; no recovery has been found. |
| The degraded state is asked about | Show `docs/screenshots/answer-journey-2026-10-23/constructed-journey-degraded-light.png` and **say aloud that it is "constructed"**: built from test data, not captured from the live fault test. Then describe the 2026-10-28 live test (end of section D). |
| Zoom's screen share freezes | Stop sharing and share the window again. |
| The network drops | Rejoin by phone audio on the hotspot (B5) and carry on with whatever you can show. If the PC is offline, the live system cannot be shown: use the last step of the recovery sequence. |
| The system is down | Run the recovery sequence below inside the instructor's buffer. |
| The daily cap is reached (ADR-097) | The message is "Daily limit reached: this demo answers a fixed number of questions a day. It resets at midnight Pacific time." (data dictionary §6 rule 5). No step clears it inside the buffer. The counter is in process and resets on a cold start (L-88), but that is not tested as a fix, so do not rely on it. Show the screenshots and the report (tab 5), then use the last step of the recovery sequence. |
| Running long | Shorten segment 6 to one example, and segment 8 to two figures (keep the caveats). |

*2026-11-12 (audit finding F-03; owner-decided; assistant-drafted.)* **Model-side failures: three fixed messages, which a rollback does not fix.** The gateway maps a failure on the model's side to one of three sentences (`services/api_gateway/src/api_gateway/app.py:53-64`; `docs/data-dictionary.md:510`).

| The page says | What it means | What to do | What to say |
|---|---|---|---|
| "The language model is rate-limited right now. Please try again in about a minute." (429, `rate_limited`) | The provider is throttling the key. | Wait about a minute and resend once. Do not send a third. | "The model provider is rate-limiting us; it clears in about a minute." Narrate the route meanwhile. |
| "The language model's daily quota is used up. It resets at midnight Pacific time." (503, `daily_quota_exhausted`) | Google's daily quota for the key is used up. This is not the gateway's own 50-question cap, which has its own message (the row above, "The daily cap is reached"); the orchestrator maps Google's quota to this code (`docs/decisions-log.md`, ADR-097, "Daily cap arithmetic": "The real backstop is Google's quota"). | Waiting does not help before midnight Pacific. Check the paid balance in the console (R-21; there is no API) and top up if it is low; no redeploy is needed (`RUNBOOK_GRADING.md`, "If the balance runs out mid-window"). Then the screenshots. | "The model's daily quota is used up, so I'll show the recorded examples." |
| "The language model is temporarily unavailable. Please try again shortly." (503, `model_unavailable`) | The provider errored or timed out (for example the free-tier 504s of 2026-10-13, ADR-104). | Wait a few seconds and resend once, then the screenshots. | "The model service is down; here are the screenshots from the deploy session." |

**Which of these an exhausted prepaid balance produces is unverified:** the sources say only that answers "degrade" (R-21). The balance is read in A1, so it is not discovered live. In all three cases show `docs/screenshots/demo-session-2026-10-30/`, say plainly that the failure is the provider's or the balance's, and **do not roll back or redeploy; neither fixes it.** Never inject a fault to show it.

*2026-10-30 (L-106; deploy session; assistant-drafted.)* **A failure mode with no recovery found.** From 18:59 to 19:45 UTC on 2026-10-30, every new instance of the reporting service (four of four) and of QA (two of two) failed to start. The question waited 60 s, and the answer was "The reporting service is temporarily unavailable…", or came back "Not verified: the checking service was unavailable", after 60 to 92 s. Sentiment, forecast, the orchestrator and the gateway started normally in that period (a sentiment start at 19:48 failed for a different reason, after `ops-db` was stopped: L-106, next-session item 9). **What did not help:** repeating the question (every repeat failed) and rolling reporting back to its previous revision (it failed the same way). The cause is unknown (L-106). **What is known:** a question that lands on an instance that is already running answers normally, and the one reporting instance that ran that day, started by the deploy, shut down 15 minutes after its last request. **Until L-106 is resolved, do not count on a cold start of reporting or QA in a live run.** Before the demonstration, ask one reporting question after a quiet period of 15 minutes or more to see whether the failure persists, and decide then. If it fails live, say so plainly (the degraded notice is designed behaviour: HTTP 200, marked not verified), show the screenshots from the deploy session, and use the recovery sequence below, remembering that a rollback did not fix this failure. Minimum instances on reporting and QA are listed for the next session in L-106; they are not set.

*2026-10-30 (ADR-120; assistant-drafted.)* **After the hardening deploys,** a retry after a degraded first answer is expected to work, because a slow start now has about 120 s to finish and the next request finds a ready instance. **Not yet verified:** until the cold-start test in the next deploy session passes, treat the row above as it stands. The first request that hits a slow cold start can still degrade.

*2026-11-12 (ADR-122; owner-decided at gate W-G2; assistant-drafted.)* **With the minimums raised, the idle-gap question and the failure row change.** The "ask one reporting question after a quiet period of 15 minutes or more" in the L-106 note above cannot produce a cold start while the minimums are 1, so it is not asked on demo day; it is taken at the rehearsal, cold, as Part 1 itself, before the minimums are raised (the note under A3). A warm instance that dies is replaced by a cold start, and a question that lands on it takes the degraded path (HTTP 200, "Not verified"), whose retry has never run (L-106). **Never inject a fault live.**

**Recovery sequence: the system is down.** Run these in order from the owner's PC, with the `$P $R $N $G $S` block
loaded. Tell the instructor what you are doing. The buffer is 10 to 20 minutes, and on 2026-10-14 each `gcloud`
call took 1 to 4 minutes (`RUNBOOK_V.md`, "Windows PowerShell 5.1 notes"), so stop at the first step that fixes it.

1. **Check service status.**
   - Reachability: `curl.exe -4 -m 20 $G/health` answers 200 with `{"status":"ok"}` (`RUNBOOK_GRADING.md`, step 5;
     `/healthz` does not work on the public URL).
   - Per service, the serving revision: `gcloud run services describe <svc> --region $R --project $P --format
     "value(status.traffic[0].revisionName)"` (`RUNBOOK_V.md`, "Rollback").
   - All six at once: `.venv\Scripts\python deploy\verify.py --ipv4` (about 1 minute when healthy on 2026-10-28,
     `docs/deploy-window-log.md`, phase 3; it prints a line per check as it goes).
   - *2026-11-12 (audit finding F-02; owner-decided; assistant-drafted.)* **Drop `verify.py` from this live recovery.** It needs eight environment variables (`PROJECT_ID`, `PROJECT_NUMBER`, `REGION`, `EXPECTED_IMAGE_TAG`, `ORCHESTRATOR_SA`, `REPORTING_SA`, `PROBE_SA`, `CLOUD_SQL_INSTANCE_NAME`; `deploy/verify.py:496-509`), and the `$P $R $N $G $S` block loaded here sets none of them, so it exits 1 with `FAIL  configuration: unset …`. It already failed this way on 2026-10-30 (audit F-02, citing `docs/deploy-window-log.md:594`). It also asks a model question and sends refusal probes, which is more than a status check. **In a live recovery, step 1 is the browser plus a read-only `describe`:** the page and `/health` (the first bullet), the serving revision (the second bullet), and, while section H is active, the minimums read in H3. **`verify.py` belongs in the rehearsal only,** run after the variable block in `RUNBOOK_V.md` section 6, "Verification run from the owner's machine" (the `$env:PROJECT_ID = $P` lines above its `verify.py` call), has been pasted into the same PowerShell window.
2. **Check `ops-db` is running.** With it stopped the page shows "The data service is unavailable right now."
   (`RUNBOOK_GRADING.md`, "Close the window", step 2).
   ```powershell
   gcloud sql instances describe ops-db --project $P --format "value(state,settings.activationPolicy)"
   ```
   Expect `RUNNABLE  ALWAYS`. If not, run the start in `RUNBOOK_GRADING.md`, "Open the window", step 2 (the
   `patch ... ALWAYS` and its wait loop). `RUNBOOK_V.md`, step 1, budgets about 5 minutes for it.
3. **Roll back the failing service, or redeploy it.**
   - **Roll back** (`RUNBOOK_V.md`, "Rollback (per service)"): `gcloud run revisions list --service <svc> ...`, then
     `gcloud run services update-traffic <svc> --to-revisions <previous-revision>=100 ...`, then the `describe`
     above to confirm. This fits the buffer. The rollback pins traffic; the note of 2026-10-28 there says how to
     clear the pin afterwards, and once the explicit "latest revision, 100%" block is deployed a later deploy
     resets it (L-105).
   - **Redeploy** needs the build trigger enabled and a build: about 9 minutes on 2026-10-28
     (`docs/deploy-window-log.md`, phase 2; `RUNBOOK_V.md`, step 8). It probably does not fit the buffer, so
     prefer the rollback.
4. **Run the smoke check** (`RUNBOOK_GRADING.md`, "Open the window", step 5): ask one question ("How many
   incidents last quarter?"). Expect an answer with an "Interpreted as:" line and a verification line. A first
   answer after idle can take about 56 s.
5. **Last resort: `[OWNER]` asks the instructor for another slot.**

## G. After the demonstration

Close the window with `RUNBOOK_GRADING.md`, "Close the window": stop `ops-db`, revoke the grader invite, run the
retry-log check, and add the log entry. **Close the window only once grading no longer needs the live system,**
and no later than the day after Window B ends (that file's own rule). Window B ends 12-12, so that is 12-13.

*2026-11-12 (ADR-122; audit finding F-09; assistant-drafted.)* **Two corrections to this section.** (1) **Lower the minimums before stopping `ops-db`** (H5): while they are raised the services stay warm, and with the database stopped a warm service would only fail its requests. Lowering happens on the demonstration day, after the questions, not at the close of the window; if the window closes the same day, the order is lower, read back, then stop. (2) **The retry-log read below uses `--freshness 7d`, which misses the first days of a 12-day window** (12-01 to 12-12, closed 12-13). Use `--freshness 14d` (the same note is under "Close the window", step 4, in `RUNBOOK_GRADING.md`).

```powershell
.venv\Scripts\python scripts\invites.py --secret $S list
gcloud sql instances patch ops-db --activation-policy NEVER --project $P
gcloud sql instances describe ops-db --project $P --format "value(state,settings.activationPolicy)"
gcloud logging read 'resource.type=cloud_run_revision AND jsonPayload.msg=\"llm attempt failed\"' --project $P --freshness 7d --format json
```

Revoke each invite by `scripts\invites.py ... revoke --id <id>` after reading its id from `list`. Expect
`STOPPED  NEVER`. No output from the log read means no retry happened; record that in the log entry.

## H. Warm instances for the live run (ADR-122), added 2026-11-12

*2026-11-12 (ADR-122; owner-decided; assistant-drafted.) Written before the first run: nothing here has been run yet, and the day-before rehearsal (the note under A3) is its first run.* Every `gcloud` flag below was read in `--help` on this machine (gcloud 531.0.0), and every log read was run read-only on 2026-11-12 against the 2026-11-11 logs; the exceptions are marked **unobserved** and are what the rehearsal exists to observe.

**What it is.** Minimum instances of 1 on all six services, **from T−60 until after the instructor's questions, T being the slot's start, and the same at the day-before rehearsal.** Not for the rest of Window B (ADR-107 holds there). It holds whatever the slot's date. It is set at the **service level** with `--min`, which "can be modified without deploying a new Revision" (`gcloud run services update --help`; the Cloud Run minimum-instances page), so it creates no revision, changes no code and leaves `main` matching the deployed commit `8ec22db`. **Do not use `--min-instances`:** it deploys a revision. Cost: about $0.62 an hour for the nine containers at list price, so $1.23 for the two hours T−60 to the end of a 60-minute slot, and $1.85 for three hours, the ceiling (ADR-122; the free tier may cover it and is not counted on).

**The rules.**
- **`ops-db` first, minimums off first.** Start `ops-db` before raising; lower before stopping it (ADR-122, decision 3).
- **No pipeline deploy while the minimums are raised** (the code freeze already holds). **Re-read the minimums after any deploy:** `deploy/deploy_service.py:73-74` sends a PATCH with no update mask, and whether that clears a service-level minimum is **unverified**.
- **The service-level annotation's name is unobserved** (today's `describe` shows only `run.googleapis.com/maxScale` at the service level). H3 prints every `Scale` line so the new one is read, not assumed.
- **Never inject a fault live.** If a warm instance dies, its replacement starts cold and a question on it takes the degraded path (F).
- **Who runs what.** The owner runs every state-changing command (the `ops-db` start, the `--min` updates, the stop). The reads (`describe`, `revisions list`, `gcloud logging read`) are read-only and may be run by the owner or by the assistant.

The PowerShell block (the owner's terminal) extends the one at the top of this file; keep it in the same window for H2 to H5. The `!` forms are one line each, in Git Bash (use forward slashes), from the repo root; they start with their own variables because each `!` line is a fresh shell.

```powershell
$P = 'a2a-agentic-service-ops-gcp'; $R = 'us-central1'
$svc = 'ops-gateway','ops-orchestrator','ops-reporting','ops-sentiment','ops-forecast','ops-qa'
New-Item -ItemType Directory -Force .local\w1 | Out-Null    # .local/ is gitignored
```

| When | What | Who | Section |
|---|---|---|---|
| T−75 | `ops-db` running (start it if not); the cap headroom read | Owner starts; reads by either | H1; A5 note |
| T−60 | capture the state, then raise to 1 | Owner | H2 |
| T−55 | readback: each service at 1, a running instance shown from the system log | Either (read-only) | H3 |
| T−30 | smoke check: one question per area, each answering in seconds | Owner, in the browser | H4 |
| After the questions | lower to default, then readback | Owner, then either | H5 |

### H1. T−75: `ops-db` running

Read first. Expect `RUNNABLE  ALWAYS`. If it is not, start it with `RUNBOOK_GRADING.md`, "Open the window", step 2 (the `patch ... ALWAYS` and its wait loop). On 2026-11-11 `ops-db` read `RUNNABLE ALWAYS` 6 min 47 s after the start command, and the start operation read `DONE` after 9 min 29 s (`summary.md`, "What happened, in order"), so T−75 leaves room.

PowerShell (read; the start is the file step above):
```powershell
gcloud sql instances describe ops-db --project $P --format "value(state,settings.activationPolicy)"
```
`!` form, the read, then the start (owner) only if the read does not say `RUNNABLE  ALWAYS`:
```
gcloud sql instances describe ops-db --project a2a-agentic-service-ops-gcp --format "value(state,settings.activationPolicy)"
gcloud sql instances patch ops-db --activation-policy ALWAYS --project a2a-agentic-service-ops-gcp
```
Then read the headroom (the A5 note) and the paid balance (A1).

### H2. T−60: capture, then raise (owner)

The capture is read-only and is what H5 compares against. **Write down `$t0`:** the readback filters on it. **Capture and compare in the same shell** (PowerShell for both, or Git Bash for both): checked read-only on 2026-11-12, a capture written by PowerShell (`Out-File -Encoding utf8` adds a byte-order mark and CRLF line endings) and compared from Git Bash read `DIFFERENT` for all six services with nothing changed, and both shells read `same` when used alone.

PowerShell:
```powershell
foreach ($s in $svc) {
  gcloud run services describe $s --region $R --project $P --format export | Out-File -Encoding utf8 ".local\w1\$s-before.yaml"
  gcloud run revisions list --service $s --region $R --project $P --format "value(metadata.name)" | Out-File -Encoding utf8 ".local\w1\$s-revs-before.txt"
}
$t0 = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'); $t0 | Out-File -Encoding ascii .local\w1\t0.txt; "raising at $t0"
foreach ($s in $svc) { gcloud run services update $s --region $R --project $P --min=1 --async }
```
`!` form, two lines (the capture and the time, then the raise):
```
P=a2a-agentic-service-ops-gcp; R=us-central1; mkdir -p .local/w1; for s in ops-gateway ops-orchestrator ops-reporting ops-sentiment ops-forecast ops-qa; do gcloud run services describe $s --region $R --project $P --format export > .local/w1/$s-before.yaml; gcloud run revisions list --service $s --region $R --project $P --format "value(metadata.name)" > .local/w1/$s-revs-before.txt; done; date -u +%Y-%m-%dT%H:%M:%SZ | tee .local/w1/t0.txt
P=a2a-agentic-service-ops-gcp; R=us-central1; for s in ops-gateway ops-orchestrator ops-reporting ops-sentiment ops-forecast ops-qa; do gcloud run services update $s --region $R --project $P --min=1 --async; done
```
`--async` returns at once (`--help`); without it each call may take minutes (on 2026-10-14 each `gcloud` call took 1 to 4 minutes, see F), and six in series could run past T−55. **Record, at the rehearsal, how long the six updates take to take effect.** An `--async` error is not shown: H3 is what finds it.

### H3. T−55: readback (either; read-only)

Four reads. **Done means all four hold for every service:** the setting shows 1; a start line with the reason; a startup probe success for every container; no shutdown.

Setup for the PowerShell reads below. It is safe to run in a window that did not run H2, because it reads `$t0` back from the file H2 wrote (the `!` forms already do):
```powershell
$P = 'a2a-agentic-service-ops-gcp'; $R = 'us-central1'
$svc = 'ops-gateway','ops-orchestrator','ops-reporting','ops-sentiment','ops-forecast','ops-qa'
$t0 = (Get-Content .local\w1\t0.txt).Trim()
$sys = 'resource.type="cloud_run_revision" AND log_id("run.googleapis.com/varlog/system") AND timestamp>="' + $t0 + '" AND '
```

**(a) The setting.** Each service must show a service-level minimum of 1 (the key name is **unobserved**) and its template `autoscaling.knative.dev/minScale: '0'` unchanged.
```powershell
foreach ($s in $svc) { "=== $s"; gcloud run services describe $s --region $R --project $P --format "yaml(metadata.annotations,spec.template.metadata.annotations)" | Select-String -Pattern 'scale' }
```
```
P=a2a-agentic-service-ops-gcp; R=us-central1; for s in ops-gateway ops-orchestrator ops-reporting ops-sentiment ops-forecast ops-qa; do echo "=== $s"; gcloud run services describe $s --region $R --project $P --format "yaml(metadata.annotations,spec.template.metadata.annotations)" | grep -i scale; done
```

**(b) A start with the minimum's reason, per service.** Cloud Run logs each start as `Starting new instance. Reason: REASON - DESCRIPTION`, and an instance started for a minimum carries `MANUAL_OR_CUSTOMER_MIN_INSTANCE` (`https://docs.cloud.google.com/run/docs/logging`, read 2026-11-12, which lists it beside `AUTOSCALING` and `DEPLOYMENT_ROLLOUT`). **Expect six lines, one per service. The reason line itself is unobserved** until the rehearsal; the same read for `AUTOSCALING` was observed on 2026-11-11 and prints `Starting new instance. Reason: AUTOSCALING - Instance started due to configured scaling factors …`. If a service shows no line with the minimum's reason, read its newest `Starting new instance` line of any reason: **a service that already had a running instance when the minimum was raised may not start a second one (unobserved)**, and an instance that started earlier and has not shut down (the read in (d)) satisfies the minimum. A reason other than the two above is a new observation: record it.
```powershell
$f = $sys + 'textPayload:"MANUAL_OR_CUSTOMER_MIN_INSTANCE"'
gcloud logging read ($f -replace '"','\"') --project $P --order asc --limit 50 '--format=value(timestamp,resource.labels.service_name,labels.instanceId,textPayload)'
```
```
P=a2a-agentic-service-ops-gcp; T0=$(tr -d '\r' < .local/w1/t0.txt); gcloud logging read "resource.type=\"cloud_run_revision\" AND log_id(\"run.googleapis.com/varlog/system\") AND textPayload:\"MANUAL_OR_CUSTOMER_MIN_INSTANCE\" AND timestamp>=\"$T0\"" --project $P --order asc --limit 50 '--format=value(timestamp,resource.labels.service_name,labels.instanceId,textPayload)' | cut -c1-200
```

**(c) A startup probe success for every container: nine lines** (gateway, orchestrator, `agent-reporting` and `mcp-incidents`, `agent-sentiment` and `mcp-feedback`, `agent-forecast` and `mcp-volume`, `agent-qa`), shaped `STARTUP HTTP probe succeeded after N attempts for container "<name>" on port <p> path "<path>".` (observed 2026-11-11; that wording is not in Google's documentation, only in this project's logs). **A line that says `STARTUP HTTP probe failed` means that start failed:** do not go on to H4; see "If a readback fails" below.
```powershell
$f = $sys + 'textPayload:"STARTUP HTTP probe succeeded"'
gcloud logging read ($f -replace '"','\"') --project $P --order asc --limit 50 '--format=value(timestamp,resource.labels.service_name,textPayload)'
$f = $sys + 'textPayload:"STARTUP HTTP probe failed"'
gcloud logging read ($f -replace '"','\"') --project $P --order asc --limit 50 '--format=value(timestamp,resource.labels.service_name,textPayload)'
```
```
P=a2a-agentic-service-ops-gcp; T0=$(tr -d '\r' < .local/w1/t0.txt); for w in succeeded failed; do echo "--- probe $w"; gcloud logging read "resource.type=\"cloud_run_revision\" AND log_id(\"run.googleapis.com/varlog/system\") AND textPayload:\"STARTUP HTTP probe $w\" AND timestamp>=\"$T0\"" --project $P --order asc --limit 50 '--format=value(timestamp,resource.labels.service_name,textPayload)' | cut -c1-200; done
```
The second read (`failed`) must print nothing.

**(d) No shutdown line.** An instance's shutdown is logged on its stdout, not in the system log: the uvicorn line `Shutting down` in `jsonPayload.msg` (observed 2026-11-11, sentiment, 20:08:57Z). It carries the same `labels.instanceId` as the instance's start line (compare the last ten characters). **Expect nothing.** A line here means an instance went away after the raise: match its id to the start lines in (b) and (c); a shutdown of an instance that started before the raise, with a minimum instance still running, is not a failure.
```powershell
$f = 'resource.type="cloud_run_revision" AND jsonPayload.msg="Shutting down" AND timestamp>="' + $t0 + '"'
gcloud logging read ($f -replace '"','\"') --project $P --order asc --limit 50 '--format=value(timestamp,resource.labels.service_name,labels.instanceId)'
```
```
P=a2a-agentic-service-ops-gcp; T0=$(tr -d '\r' < .local/w1/t0.txt); gcloud logging read "resource.type=\"cloud_run_revision\" AND jsonPayload.msg=\"Shutting down\" AND timestamp>=\"$T0\"" --project $P --order asc --limit 50 '--format=value(timestamp,resource.labels.service_name,labels.instanceId)' | cut -c1-120
```

**If a readback fails.** A service shows no minimum: run its update once more (`--min=1`) and read again. A start line is missing or a probe failed: do not raise again blindly; read that service's system log since `$t0` (the `--order asc` read above without the text filter), and decide at T−30 whether the demonstration runs on that service cold (C and the re-warm of C apply to it as written, F covers a failed start). The rehearsal is the day this is found, not the demonstration.

### H4. T−30: the smoke check (owner, in the browser)

Count first: the headroom read (A5 note) must leave room for the worst case there. Then, **before joining Zoom or sharing,** ask one question per area from the landing page's examples (they fill the input and do not submit): reporting, sentiment, forecast (C, steps 1 and 2; it is the same warm-up). **Each is expected to answer in seconds** (about 3 s, 2.6 to 3.4 s, warm on 2026-10-28; `docs/deploy-window-log.md`, phase 4, as cited in C), and each must be an answer, not a degraded result or an error. **A first answer that takes over about 10 s** (assistant-proposed, not a measured threshold and not owner-decided) means an instance was not warm: stop and run H3 (b) to (d) again before going on. Three questions, 9 model calls (A5 note).

### H5. After the questions: lower, then read back (owner, then either)

Do not lower while the instructor may still ask for a live question. Lower only after the instructor ends the questions (or, at the rehearsal, after H4's wait and its last question). `--min=default` removes the service-level minimum (`--help`: "or 'default' to remove"), which returns each service to its state of 2026-11-12.

PowerShell:
```powershell
foreach ($s in $svc) { gcloud run services update $s --region $R --project $P --min=default --async }
```
```
P=a2a-agentic-service-ops-gcp; R=us-central1; for s in ops-gateway ops-orchestrator ops-reporting ops-sentiment ops-forecast ops-qa; do gcloud run services update $s --region $R --project $P --min=default --async; done
```
**Then read back (read-only), once the updates have taken effect.** Expected: `describe` shows **no service-level minimum** (the `Scale` lines of H3 (a) are back to today's: `run.googleapis.com/maxScale` and the template's `minScale: '0'`), **`revisions list` is the same as before** (no new revision from raising or lowering), and the `--format export` is the same as before (it proves the template did not change, not only the revision names; it is the C4 comparison of `evals/l106/README.md`).
```powershell
foreach ($s in $svc) {
  gcloud run revisions list --service $s --region $R --project $P --format "value(metadata.name)" | Out-File -Encoding utf8 ".local\w1\$s-revs-after.txt"
  gcloud run services describe $s --region $R --project $P --format export | Out-File -Encoding utf8 ".local\w1\$s-after.yaml"
  "{0}: revisions {1}; export {2}" -f $s,
    $(if (Compare-Object (Get-Content ".local\w1\$s-revs-before.txt") (Get-Content ".local\w1\$s-revs-after.txt")) {'DIFFERENT'} else {'same'}),
    $(if (Compare-Object (Get-Content ".local\w1\$s-before.yaml") (Get-Content ".local\w1\$s-after.yaml")) {'DIFFERENT'} else {'same'})
  gcloud run services describe $s --region $R --project $P --format "yaml(metadata.annotations,spec.template.metadata.annotations)" | Select-String -Pattern 'scale'
}
```
```
P=a2a-agentic-service-ops-gcp; R=us-central1; for s in ops-gateway ops-orchestrator ops-reporting ops-sentiment ops-forecast ops-qa; do gcloud run revisions list --service $s --region $R --project $P --format "value(metadata.name)" > .local/w1/$s-revs-after.txt; gcloud run services describe $s --region $R --project $P --format export > .local/w1/$s-after.yaml; echo "$s: revisions $(diff -q .local/w1/$s-revs-before.txt .local/w1/$s-revs-after.txt >/dev/null && echo same || echo DIFFERENT); export $(diff -q .local/w1/$s-before.yaml .local/w1/$s-after.yaml >/dev/null && echo same || echo DIFFERENT)"; gcloud run services describe $s --region $R --project $P --format "yaml(metadata.annotations,spec.template.metadata.annotations)" | grep -i scale; done
```
If the export shows `DIFFERENT`, read the differing lines (`Compare-Object` or `diff` on the two files). The export leaves out the volatile fields: read 2026-11-12, it holds no `operation-id`, no `lastModifier`, no `generation` and no `status`, so after lowering a `DIFFERENT` is a real difference, most likely a minimum annotation that was not removed. (Between H2 and the lowering, with the minimums raised, the only expected difference is the added service-level minimum.) **Only after this readback** stop `ops-db`, if the window is closing (G; the order is lower, read back, then stop). Record in the window log (`docs/deploy-window-log.md`): the time raised and lowered, the minutes the updates took, the six-by-nine readback results, and any shutdown line.
