# The full rehearsal, 2026-11-23 (D2): summary

Assistant-drafted from the session's logs and the owner's statements; every owner decision is marked. Times are US Central (UTC minus 6) unless marked Z. Files beside this one: `ledger.jsonl` (one line per question, 21), `starts.json` (every instance start, from one log pull). Build under test: `8ec22db`. Session 18:28 to 21:05.

**Result in one line: P-B, P-C and P-D passed. P-E was not scored (Part 3 segment splits were not recorded). The rehearsal's own pass condition, "P-B, P-C, P-D and P-E pass", is therefore not met.** P-A is an observation.

## 1. The rules as written before the run (owner-decided 2026-11-23, verbatim)

**Caps:**
- Questions: **at most 25** in the session (the per-invite caps are 30 an hour and 50 a Pacific day). Keep a running count in the ledger.
- Warm time: minimums go up at G2 and **must be lowered by 3 h after G2 at the latest**, whatever state the session is in (ADR-122's ceiling is about $1.85 for 3 h).
- Session: if the session hasn't reached G4 by 17:30 Central, go straight to teardown (G4) and record what didn't run.

**Pass/fail rules:**

| Rule | Pass when | If it fails |
|---|---|---|
| **P-A, cold (an observation, not a pass/fail)** | Every Part 1 question is `answered` and `verified`, under the 120 s ceiling | Record it as an L-106 observation (start lines, probe results, timings) and **continue**: warm instances are the demo-day guard |
| **P-B, warm mechanics** | After `--min=1` on all six services: each service shows a service-level minimum of 1; **no new revision** on any service (the revision list and `spec.traffic` match G0); each service has an instance whose start is attributed to the minimum (ADR-122 expects a `MANUAL_OR_CUSTOMER_MIN_INSTANCE` start line, unobserved until today: record the exact text and annotation name you actually find) | **Stop.** Read back `spec.traffic` on the affected service, tell the owner, and go to teardown unless the owner decides otherwise |
| **P-C, warm hold** | After at least 20 minutes with no requests, one reporting question is `answered` and `verified` in **at most 15 s** in the browser. This bound is fixed now. It's well under any cold first answer seen so far (42 to 58 s on 2026-11-11). | Record it. Teardown proceeds. The owner decides what it means for demo day. |
| **P-D, teardown** | Every service is back at no minimum (`--min=default`), with no new revision; `ops-db` is `STOPPED NEVER`; the trigger is disabled | **Stop** and report what differs |
| **P-E, the script run** | Part 1 of the presentation, run in full, takes **30:00 or less**; every live question in the script is `answered`; every tab in the segment-6a list opens to its anchor | Record each overrun or failure by segment. This is a narration finding, fixed in the runbook afterwards. |

The rehearsal passes if P-B, P-C, P-D and P-E pass. P-A is reported, not graded.

**Separately, owner-decided after the run:** the demo-day H4 threshold (the runbook's "about 10 s" for a warm answer), set by the owner from the warm times measured in Parts 2 to 4. It is not the same thing as P-C's 15 s.

## 2. Pre-run amendments (owner-decided 2026-11-23, each recorded before the thing it governs)

0. **The cutoff.** G4 must be reached by **21:30 Central**. The 17:30 cutoff, set the morning of 2026-11-23, is superseded because the session started at 18:30. The 3 h warm ceiling from G2 is unchanged. (Set after the G0 report at about 18:31 and before any minimum was raised or any question asked. G4 was reached at 20:52.)
1. **P-E's second clause** now reads "every live question returns its expected status": the SLA, sentiment and forecast questions `answered` and `verified`; "How's the Southeast doing?" `needs_clarification`; "What will revenue be next quarter?" `declined` (out of scope). A different status is a P-E failure, recorded by segment.
2. **Part 4's cache check** (read-only, before G2). The code has no response cache: the gateway sets `no-store` and static-asset headers and keeps in-process rate counters; the orchestrator caches Agent Cards only (300 s TTL; metadata, not answers); each agent uses an in-memory single-shot task store and its MCP client sets `cache=None`; there is no `lru_cache`, memoisation or answer store under `services/` or `packages/`. The Gemini API's own prompt caching and Postgres buffers are not visible in the code and return no stored answer. **The SLA question stayed for Part 4.**
3. **Part 3b, five unscripted questions** (owner-decided, from `D2-addition-candidates.md`; the expectations were written into the draft at 19:06, before any was asked, and the owner accepted three differences at 19:18). Asked once each, after Part 3 and before the hold wait, never during an idle wait; one run each, a viability check and not a rate.
4. **Part 3b, a sentiment wording asked three times** (owner-decided; written at 19:53:54, before it was asked): S1, "Are customers in the West sounding more negative in their post-visit feedback comments lately?", worded from `route_v6`'s sentiment description with no reporting terms. Planned total 21 of 25.
5. **The invite.** `owner-laptop-6` did not exist at G0 and was created by the owner during the `ops-db` wait, in the owner's own terminal. **Created 2026-11-23 at 18:37:40** (assistant-read: the creation time of the secret's new version, metadata only; no token or link read), **expires 2026-12-07** (owner-reported; the read-only `invites.py list` shows it active, expiring 2026-12-08T05:54Z = 12-07 23:54 Central). The link is held by the owner.

## 3. Each rule's result

- **P-A (cold; observation): all three `answered` and `verified`, under the ceiling.** Detail in section 4.
- **P-B (warm mechanics): pass.** After the raise (calls 19:30:57 to 19:31:17): every service shows `run.googleapis.com/minScale: '1'` (service-level `metadata.annotations`; the template's `autoscaling.knative.dev/minScale: '0'` unchanged). No new revision: the revision list and `spec.traffic` of all six equal the G0 capture, compared in Git Bash for both; the `--format export` differs from G0 by exactly the one added line. Every service has one instance whose start line is `MANUAL_OR_CUSTOMER_MIN_INSTANCE` (section 5).
- **P-C (warm hold): pass.** The last request before it was the last Part 3b answer at 20:19:12; a check at 20:39:36 found no request to any service since, and no start, shutdown or probe failure. At 20:40:49 (**21 min 37 s** idle) "What was SLA compliance in the Northeast last month?" came back `answered`, `verified`, **2.6 s in the browser** (the bound was 15 s), gateway 2.61 s, with **no new instance start on any service**. The request log shows the orchestrator fetching the reporting and QA Agent Cards first, as expected after the 300 s card cache expired. 88.13% (141 of 160), the same figure as 2026-10-28.
- **P-D (teardown): pass.** The six `--min=default` calls ran 20:47:03 to 20:47:24. Read at 20:48: no service-level minimum on any service; the exports, revision lists and `spec.traffic` of all six identical to the G0 capture; all six `Ready=True`. `ops-db`: the stop was registered 20:51:15, operation `DONE` 20:51:58, `STOPPED` `NEVER` at 20:52. The trigger `deploy-reporting-slice` `disabled: True` (read at G0, G4 and 20:52).
- **P-E (the script run): not scored: Part 3 segment splits were not recorded.** (Owner-decided; the owner took no stopwatch because it would feel unnatural.) Context only: Part 3's five live questions reached the gateway between 20:01:07 and 20:07:01, 5 min 54 s apart. The owner spoke the segments aloud but clicked through the tabs and questions at speed, and reports that navigating the GitHub tabs was frustrating; no per-tab result was recorded. Facts, not a score: the five live questions returned their expected statuses (section 6); the five unscripted questions matched (section 7). **No narration cuts; the provisional timeline stays** (owner-decided).

## 4. Part 1 (cold): counts and timings

After the services had been idle since before 18:30. Page loaded 18:53:21 (the gateway started at 18:53:46). Per question (browser seconds read by the owner; gateway and orchestrator times from the logs):

| # | Question | Route | Status, QA | Browser | Gateway | Orchestrator | Instances started |
|---|---|---|---|---|---|---|---|
| 1 | What was SLA compliance in the Northeast last month? | reporting | answered, verified | **51.3 s** | 51.24 s | 42.9 s | orchestrator, reporting, QA |
| 2 | Is negative feedback trending up in the West? | sentiment | answered, verified | **23.4 s** | 23.25 s | 23.1 s | sentiment (one instance) |
| 3 | What weekly request volume should we expect for the next 8 weeks? | forecast | answered, verified | **20.1 s** | 19.96 s | 19.8 s | forecast |

**Starts** (all `AUTOSCALING`; seconds are from the start line to the last startup-probe success; `starts.json`): gateway 5.2 s, orchestrator 8.2 s, reporting 26.1 s (`mcp-incidents` 11.7 s), QA 11.8 s, sentiment 20.0 s, forecast 17.1 s. **Six autoscale starts, 0 failed, 0 over 60 s.** No probe failed and nothing degraded, so **P2 (a retry after a degraded first answer) was not exercised.** The first question started three instances in series (orchestrator, then reporting, then QA, which starts only after reporting answers); that is where its 51 s went. The last Part 1 request finished at 18:58:11.

**The idle wait.** Five services shut down between 19:09:51 and 19:13:20. **Unexpected: nine page requests reached the gateway at 19:12:09 to 19:12:11** (`GET /`, five static files, `/favicon.ico` 404, `/api/session` 401). Log facts: one user-agent string, Chrome 145, ending "(compatible; meta-webindexer/1.1 (+https://developers.facebook.com/docs/sharing/webmasters/crawler))"; eight distinct IPv6 addresses, none inside `2001:4860::/32` or `2600:1900::/28`; no `HeadlessChrome`; no referer; no sign-in exchange and no question. The owner's Part 1 client was Firefox 160 from one address. Similar Chrome 145 `GET /` requests appear in the log on 2026-10-29 and 2026-11-23 (04Z and 11Z). **Owner-decided: recorded as background crawler traffic (self-reported `meta-webindexer` user agent, unverified), no invite involved, no action.** The owner confirms the invite link was never sent anywhere or opened on another device. The gateway's idle clock restarted at 19:12:11, so the owner chose to wait for its shutdown (19:27:19) before raising the minimums, so that all six services started cold.

## 5. G2: ADR-122's mechanics, as observed

- **Annotation:** `run.googleapis.com/minScale: '1'` at the service level.
- **Start line, exact text:** `Starting new instance. Reason: MANUAL_OR_CUSTOMER_MIN_INSTANCE - Instance started because of customer-configured min-instances or manual scaling.` Six lines, one per service, all at 19:32:29 (within 50 ms of each other), 72 to 92 s after each service's own update call. Nine startup probes passed (last 19:32:56), none failed. The six updates took about 2 minutes to take effect (first call to last probe).
- **Update calls (Cloud Audit Log, `ReplaceService`):** gateway 19:30:57, orchestrator 19:31:01, reporting 19:31:05, sentiment 19:31:09, forecast 19:31:13, QA 19:31:17.
- **Revisions and traffic:** unchanged on all six (section 3). The `generation` fields read 6 (gateway) and 13 (reporting) after the raise; the pre-raise values were not captured.
- **After lowering,** the instances shut down on their own idle timers: sentiment and forecast 20:49:12 and 20:49:14, orchestrator, reporting and QA 20:55:53 to 20:56:01, the gateway 20:58:29. No minimum instance shut down before the lowering.
- **Unobserved:** the case of a service that already has a running instance when the minimum is raised (all six were cold); whether a deploy's PATCH clears a service-level minimum (nothing deployed).

## 6. G2 smoke check and Part 3 (the script's five live questions)

| # | When | Question | Route | Status, QA | Browser | Gateway |
|---|---|---|---|---|---|---|
| 4 | 19:36:42 | SLA, Northeast | reporting | answered, verified | 5.1 s | 5.02 s |
| 5 | 19:37:12 | Is negative feedback trending up in the West? | multi_domain | **`split_required`** (incident and quality reporting; customer feedback sentiment), 1 model call | not taken | 0.79 s |
| 6 | 19:38:50 | Weekly volume, 8 weeks | forecast | answered, verified | 3.4 s | 3.32 s |
| 7 | 19:41:36 | Q5 resent once (runbook F) | sentiment | answered, verified | 3.6 s | 3.50 s |
| 8 | 20:01:07 | SLA, Northeast (segment 4) | reporting | answered, verified | within 3 s | 2.82 s |
| 9 | 20:03:00 | Is negative feedback trending up in the West? (segment 6) | sentiment | answered, verified | within 3 s | 2.75 s |
| 10 | 20:03:42 | Weekly volume, 8 weeks (segment 6) | forecast | answered, verified | within 3 s | 2.10 s |
| 11 | 20:06:23 | How's the Southeast doing? (segment 7) | ambiguous | `needs_clarification`, not applicable | within 3 s | 0.87 s |
| 12 | 20:07:01 | What will revenue be next quarter? (segment 7) | out_of_scope | `declined`, not applicable | within 3 s | 0.79 s |

The segment 6 sentiment example split once, in the smoke check (a router outcome; no specialist ran; it answered on the single resend). **Counts only:** the original question has 2 splits in **7** recorded runs on the deployed system with `route_v6`: 2026-10-28 answered (1); 2026-10-30 split (1) and answered (1); 2026-11-23 answered 18:55, split 19:37, answered 19:41, answered 20:03. The 2026-10-23 run (HTTP 502) returned no routing outcome and is not counted. Single runs, not a rate.

No new instance start, shutdown or probe failure occurred from the raise to the lowering.

## 7. Part 3b: the five unscripted questions and S1 (20:13 to 20:19; one run each, not a rate)

Expectations were written at 19:06 (and 19:53 for S1), before any was asked; marked by the assistant after.

| Id | Question | Expected | Got | Marked |
|---|---|---|---|---|
| T1 | What was Diego's SLA compliance last quarter? | `needs_clarification`, both full names, no figures | `needs_clarification`; "2 technicians match Diego: Diego Ellis and Diego Hughes. Please ask again with the full name."; QA `verified` (a QA status on a clarification was not an expectation); browser 2.6 s. The reason code `technician_ambiguous` is not in the log fields read; the wording is ADR-073's. | matched |
| T2 | What was Diego Ellis's SLA compliance last quarter? | `answered`, `verified`, "based on n dispatched requests" | `answered`, `verified`; 88.52% from 2026-04-01 to 2026-06-30 (calendar Q2), "based on 61 dispatched requests: 54 completed within their SLA window"; n at least 20, so no "too few" sentence expected (the owner's paste ends after the first sentence, so its absence was not read); 2.6 s | matched |
| F1 | What repair volume should we expect over the next 8 weeks? | weeks 1 to 4 withheld, error 27.9%; weeks 5 to 8 served, error 10.8% | `answered`, `verified`; weeks of 08-31 to 09-21 not shown ("off by 27.9% on held-out weeks"); weeks of 09-28 to 10-19 shown at about 61 to 63 a week with 80% ranges, error 10.8%; no total; 2.5 s | matched (against the `volume_v2` manifest's serving table) |
| M1 | What was SLA compliance in the Midwest last month? | a decline naming the four regions, no figures (owner-accepted status: `not_available`) | `not_available`; names northeast, southeast, central, west; "Other areas, such as a state or a city, aren't mapped to a region"; no figures; 2.4 s | matched |
| MD1 | Which region has the worst SLA compliance, and are customers there unhappy? | `split_required` naming reporting and sentiment | `split_required`; "Your question covers more than one area: incident and quality reporting and customer feedback sentiment. I answer one area per question, so please ask about each separately."; 1 model call; 0.9 s | matched |
| S1a, S1b, S1c | Are customers in the West sounding more negative in their post-visit feedback comments lately? | each routed `sentiment`, `answered`, `verified` | **3 of 3.** 2.4, 2.7, 2.7 s. S1c in full: West, 2026-03-01 to 2026-08-30 ("no period was named, so this range was assumed"), 241 comments, "Trend: no clear change in the negative share. Latest month, 2026-08: 7 of 32 negative (21.9%). Earlier months, 2026-03 to 2026-07: 30 of 209 negative (14.4%). p = 0.2718." S1a and S1b were reported by their first line only. | matched, 3 of 3 |

No wording changes are proposed here; the owner decides which go on the Q&A card (rows 16 to 21 were drafted into `deploy/RUNBOOK_DEMO.md`, section E2, on the owner's instruction).

## 8. Warm and cold times, and the H4 threshold

- **Cold** (browser): 51.3 s (three services cold in series), 23.4 s and 20.1 s (one cold specialist each).
- **Warm, full specialist path** (3 model calls; 14 questions: the smoke check, Part 3, Part 3b, Part 4): gateway **2.10 to 5.03 s, median 2.60 s**. Browser: 11 readings (Part 3's five were reported only as "within 3 s"), **2.4 to 5.1 s, median 2.6 s**; sorted 2.4, 2.4, 2.5, 2.6, 2.6, 2.6, 2.7, 2.7, 3.4, 3.6, 5.1. The 5.1 s one was the first answer after the raise.
- **Router-only outcomes** (split, clarification, decline; 1 model call): 0.79 to 0.87 s at the gateway, 0.9 s in the browser.
- **H4 threshold: 10 s** (owner-decided 2026-11-23, from warm max 5.1 s, median 2.6 s, cold min 20.1 s). For demo day: a first answer over 10 s in the smoke check means an instance was not warm; stop and run H3 (b) to (d) again.

## 9. Counts, warm time and cost

- **Questions: 21 of 25** (Part 1: 3; smoke check: 4 including the resend; Part 3: 5; Part 3b: 8; Part 4: 1). The gateway's daily counter at the start read 0 (an upper bound from the request log). The per-invite cap of 30 an hour was not approached. List-price model cost of the 21 questions: **$0.0305**.
- **Warm time:** 1 h 16 min 27 s from the first `--min=1` call (19:30:57) to the last `--min=default` call (20:47:24); the ceiling was 3 h. The minimum instances ran from 19:32:29 to their shutdowns (20:49:12 to 20:58:29).
- **List-price cost estimate** at ADR-122's $0.6156 an hour for nine containers: **about $0.78** counted call to call, **about $0.84** counted from each instance's start to its shutdown. An estimate, not a bill; ADR-122's ceiling for 3 h was $1.85. `ops-db` ran about 2 h 11 min (start registered 18:40:26, stop operation done 20:51:58). The runtime uses the paid key (ADR-104, ADR-105). Tonight's 21 questions cost about $0.0305 at list price against the paid balance ($6.15 before the session, owner-read 2026-11-23). The balance is read at the 12-04 preflight (ADR-105 floor $5).

## 10. Final idle state (read at 20:52, shutdowns to 20:58:29)

No service-level minimum on any service; serving revisions `ops-gateway-00005-m67`, `ops-orchestrator-00012-t27`, `ops-reporting-00010-xtq`, `ops-sentiment-00006-8jp`, `ops-forecast-00006-nsf`, `ops-qa-00007-w9l`, each at 100%, all identical to G0; `ops-db` `STOPPED` `NEVER`; trigger `deploy-reporting-slice` disabled; all instances shut down. The invite `owner-laptop-6` is active until 2026-12-07.

## 11. What did not run or was not recorded

- Segment splits and Part 1's total time (P-E).
- Per-tab anchor results for tabs 7 to 15 (the owner reports the GitHub navigation was "frustrating"; **owner-reported observation only: "Github was frustrating to navigate while working through the demo script". No decision.** A slide deck would need a new ADR, because ADR-117 lists a separate slide deck among its rejected alternatives).
- The zoom check (A4 `[TBD]`): not run. The demonstration is on a Zoom call hosted by the instructor, and the owner joins as a guest, not the host. The browser zoom is set at the 12-04 check.
- Part 3's per-question browser seconds ("within 3 s"); Q5's browser time (not taken); S1a's and S1b's text beyond the first line; T2's trailing text.
- The paid balance (not recorded tonight; read at the 12-04 preflight); the H3 (b) already-running-instance case; whether a deploy's PATCH clears the minimum; the owner's pre-raise `generation` values.
- Nothing deployed (the trigger stayed disabled), by design.

## 12. Owner decisions at the end of the session, and what the records carry

- The L-106 status line (owner-decided): in `docs/evaluation-report.md`, L-106, note of 2026-11-23, with reporting at 26.1 s (owner-decided; `starts.json` reads 26.1 s).
- No narration cuts; the provisional timeline stays. The 12-04 check gains a timed solo run-through of Part 1 with splits and no warm instances (note under A3), **to be run after the cold question and the tab click-through** so that its own questions do not lose L-106's cold observation; each cold wait in it is noted in the splits so the talking time can be read net of it. The 12-04 check also gains a screen-share test on Zoom (owner-decided): sharing the browser window only, setting the browser zoom for readability on a shared screen, and confirming the session survives (signed in before sharing).
- The segment 6 sentiment question is typed as S1 (runbook note, owner-decided); the original question split in 2 of 7 recorded runs.
- `robots.txt` disallowing crawlers is added to the after-demonstration list (`docs/final-pass-checklist.md`).
