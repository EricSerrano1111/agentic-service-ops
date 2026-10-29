# Runbook: the live demonstration (ADR-117 item 6)

Written 2026-10-29 (ADR-117 item 6; owner inputs 2026-10-29; assistant-drafted). Not yet run. Windows
PowerShell 5.1, from the repo root, with `.venv` built. Every `gcloud` command carries `--project`.

**Owner inputs, 2026-10-29.**
- **Format:** live over Zoom, the owner sharing the screen.
- **Slot:** 60 minutes. Part 1 is a 30-minute overview. Part 2 is 10 to 20 minutes of instructor questions. The
  instructor holds the remaining 10 to 20 minutes as a buffer. **This plan does not use the buffer;** it is
  there only for recovering when something goes wrong.
- **No recording** (owner, 2026-10-29). The demonstration runs live, and nothing stands in for it.
- **Date and time:** `[TBD]`. Slots are announced about 11-15 to 11-22 and the owner chooses. **Prefer a slot
  inside Window B** (2026-12-01 to 12-12, ADR-107). A slot outside it means a new ADR to move the window.
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
     `docs/deploy-window-log.md`. Its date is `[TBD]`. This runbook does not run it.
   - **Takes a current screenshot of each live example,** in light theme, at the browser zoom chosen in A4, from
     the signed-in page: the SLA answer, the answer journey, the sentiment answer, the forecast answer, the
     clarification ("How's the Southeast doing?") and the revenue decline. Save them under
     `docs/screenshots/demo-session-[TBD date]/`, one file per example. They replace the 2026-10-23 screenshots,
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
3. **Run the whole of Part 1 once on the live system, timed** (the same signed-in browser, the same order as
   section D). **This is the only live run-through.** The narration is rehearsed offline with the tabs.
   - Write down the elapsed time the page shows for each question ("Answered in N.N s", data dictionary §6
     rule 7) and which questions were cold.
   - Note any example that misbehaves (rule 9: replace or remove it, and add a dated note there).
   - Part 1 asks 5 questions (A5). Do the two examples Part 1 does not use ("Which incident types were most
     common in July 2026?" and "Show examples of negative comments from last month") only if you want them ready
     for the instructor's questions.
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

## F. If something goes wrong

There is no recording and no fallback video (owner, 2026-10-29): the demonstration runs live.

| Problem | What to do |
|---|---|
| An answer takes over 30 s | Say it's a cold start (R-05), and narrate the journey while waiting. Measured: 26 to 61 s on 2026-10-28, inside the 120 s ceiling. |
| A single example fails | Show its screenshot from the deploy session (`docs/screenshots/demo-session-[TBD date]/`), say so plainly, and move on. |
| The degraded state is asked about | Show `docs/screenshots/answer-journey-2026-10-23/constructed-journey-degraded-light.png` and **say aloud that it is "constructed"**: built from test data, not captured from the live fault test. Then describe the 2026-10-28 live test (end of section D). |
| Zoom's screen share freezes | Stop sharing and share the window again. |
| The network drops | Rejoin by phone audio on the hotspot (B5) and carry on with whatever you can show. If the PC is offline, the live system cannot be shown: use the last step of the recovery sequence. |
| The system is down | Run the recovery sequence below inside the instructor's buffer. |
| The daily cap is reached (ADR-097) | The message is "Daily limit reached: this demo answers a fixed number of questions a day. It resets at midnight Pacific time." (data dictionary §6 rule 5). No step clears it inside the buffer. The counter is in process and resets on a cold start (L-88), but that is not tested as a fix, so do not rely on it. Show the screenshots and the report (tab 5), then use the last step of the recovery sequence. |
| Running long | Shorten segment 6 to one example, and segment 8 to two figures (keep the caveats). |

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

```powershell
.venv\Scripts\python scripts\invites.py --secret $S list
gcloud sql instances patch ops-db --activation-policy NEVER --project $P
gcloud sql instances describe ops-db --project $P --format "value(state,settings.activationPolicy)"
gcloud logging read 'resource.type=cloud_run_revision AND jsonPayload.msg=\"llm attempt failed\"' --project $P --freshness 7d --format json
```

Revoke each invite by `scripts\invites.py ... revoke --id <id>` after reading its id from `list`. Expect
`STOPPED  NEVER`. No output from the log read means no retry happened; record that in the log entry.
