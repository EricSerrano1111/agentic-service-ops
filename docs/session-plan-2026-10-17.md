# Owner verification session 1: the plan (ADR-110)

*Drafted 2026-10-15 (Prompt S6-W0; owner-decided 2026-10-15; assistant-drafted). The session is Saturday
2026-10-17, owner present. Written with zero live calls: no model call, no `gcloud`, no GCP, no
`verify.py` run, no HTTP to `*.run.app`. Everything below is read from the repo at `6dd8ba8`.*

**What this file is.** A run sheet. It is not a result. Nothing in it has been run. Each step names who
runs it (**OWNER** or **CLAUDE-CODE**), the exact commands, the expected result and the evidence to keep.
Section 9 lists what the owner must decide or build before Saturday; section 3 says why the order differs
from the order the prompt listed.

All commands are Windows PowerShell 5.1 from the repo root. Every `gcloud` carries `--project`. Every comma
list is quoted (RUNBOOK_V, "Windows PowerShell 5.1 notes"). `verify.py` runs with `--ipv4`.

```powershell
$P  = 'a2a-agentic-service-ops-gcp'
$R  = 'us-central1'
$N  = '587647038690'
$G  = "https://ops-gateway-$N.$R.run.app"          # deterministic host; the only one invites may carry
$S  = "projects/$N/secrets/gateway-invites"
$DB = 'ops-db'
```

---

## 1. What the plan rests on (state check, 2026-10-15)

| Check | Finding |
|---|---|
| Tree and branch | Clean; `main` equals `origin/main` (`6dd8ba8`) after `git fetch`. |
| `9e25f03` (window-day tooling) | Is an ancestor of HEAD. |
| `verify.py --help` | Lists `--ipv4` and `--gcloud-timeout SECONDS` (default 300). Local, no calls. |
| `docs/academic/05-test-scenarios.md` | Exists. Last commit touching it: `a158faa`, 2026-10-15, "docs(academic): 05 latest revision". |
| Ledgers | **Two exist, and neither covers this session as built (below).** |
| Grading runbook | `deploy/RUNBOOK_GRADING.md` (open and close a window), `deploy/RUNBOOK_V.md` (steps 6, 10, 12 and the PowerShell notes). |
| Invite tooling | `scripts/invites.py --secret $S create --label ... --days ... --base-url $G`, `list`, `revoke --id`. |

**The two ledgers, stated plainly.**

1. `evals/ledger.py` is the Sprint 5 **W-gates** ledger (state file `evals/results/sprint5_w_ledger.json`).
   It wraps an in-process LLM client (`client.totals`), accepts only the paths `A1, A2, C1, C2`, and caps
   are fixed at file creation (`CAP_REQUESTS = 561`, `CAP_USD = 3.00`). It cannot count a deployed request.
   It is not usable here.
2. `evals/results/sprint5_x/harness.py` is the **X-evaluation** ledger (state file
   `evals/results/sprint5_x_ledger.json`, 186 requests, $0.1727 logged). It counts requests sent to the
   deployed orchestrator's `/ask` and reads `cost_usd` from the orchestrator's log line by trace ID. It is
   the right pattern. Its limits for this session:
   - it counts only **direct-to-orchestrator** requests; a question asked in the browser through the
     gateway never touches it;
   - its caps are module constants and its state file is fixed, so it needs a new state file and caps;
   - it uses `urllib` with no IPv4 forcing, and would hang on the owner's PC the way `verify.py` did for
     about 35 minutes on 2026-10-14 (RUNBOOK_V, PowerShell notes);
   - it is hard-wired to the routing and golden sets.

   **Consequence: "the ledger enforces the total" is not true for this session as the code stands.** Section
   5 says which traffic a ledger can see and which it cannot. The Sprint 5 retro rule (budgets by ledger,
   never by per-process caps) is met for the ledger-able requests and met only by an owner tally plus the
   gateway's own counters for the rest. This is open question Q1.

---

## 2. The deployed scenarios, quoted from `05`

By `05`'s own Environment column and wording, these are the cases that touch the deployed system: **TS-14-A
to D, TS-16-D, TS-18-C and D, TS-20-A to E.** `sprint-log.md` (Window A item, line 1093) also lists TS-17;
`05` marks TS-17 **Local** ("Level: Manual | Environment: Local") and each of its cases stops a service,
which on Cloud Run is a configuration change this session may not make. This plan follows `05`; the
mismatch is Q6. TS-15-D (logs) is `Local` in `05` and is read as a by-product of step 4 (zero extra calls).

Cases are quoted exactly. "Expected on the deployed system" is the plan's reading of what will happen, so a
known failure does not trip the stop rule.

| ID | Input / steps (verbatim) | Expected result (verbatim) | Expected on the deployed system |
|---|---|---|---|
| TS-14-A | "Open the interface with a valid invite link and ask a question. Then send a question with no session, and try an expired and a revoked invite." | "The first is answered. The others are refused before any model call, and the expired and revoked invites get the same refusal as an unknown one." | Runnable as written. |
| TS-14-B | "From outside the system, try to reach the orchestrator, each agent, and each tool server." | "Every one is unreachable or refused. Only the gateway responds." | The three **tool servers are sidecars with no URL of their own** (each runs "alongside its specialist in the same service", `05` §3); they cannot be tried separately. Run for the orchestrator and the four agent services (reporting, sentiment, forecast, QA); record the tool servers as not separately reachable. |
| TS-14-C | "Call a specialist directly without the orchestrator's service identity." | "Rejected." | Runnable. `verify.py` already makes this check with `probe-noauth`; step 3.2 repeats it by hand. |
| TS-14-D | "Search the code repository and the built container images for credentials." | "None found. Services read credentials from Secret Manager." | Repo search and the deployed configuration are cheap. Pulling and scanning every built image is heavy (nine images, torch among them); see Q5. |
| TS-16-D | "On the deployed system, after services have scaled to zero, send a reporting, a sentiment and a forecast question, each after an idle period." | "Each response arrives within 120 seconds, and each cold-start latency is recorded." | Runnable. Step 2. |
| TS-18-C | "On the deployed system, send several concurrent reporting questions while asking one forecast question." | "The forecast question is answered correctly. The reporting service scales up, and the forecast service does not." | The forecast answer is checkable. **Scale-up is not guaranteed**: the reporting service is `maxInstanceCount: 2` at `maxInstanceRequestConcurrency: 8`, and six concurrent requests may stay on one instance. Record what is observed; "the reporting service scales up" is the one clause that may not hold. |
| TS-18-D | "Through the interface, ask more questions with one invite than the hourly limit of 30 allows." | "The question over the limit is refused with a message stating the limit, and no model is called for it." | Runnable, with a driver (31 by hand is not sensible). Needs 30 accepted questions on one invite in under an hour. |
| TS-20-A | "Enter a reporting question in the interface." | "The answer is shown with its "Interpreted as" line (the measure, dates, region and any filter as the system read them), its verification line and the as-of date." | Runnable. |
| TS-20-B | "Trigger a degraded result." | "The interface shows the warning and "Sent for follow-up", and the answer is not displayed as verified." | **Not runnable on the deployed system without a deploy or a fault injection, both outside this session.** A stopped `ops-db` yields the 502 "data service is unavailable" message, not a degraded result (L-89, sprint-log 6.5 candidates). Record "not run, no trigger" (Q4). |
| TS-20-C | "Ask a sentiment question that includes comments flagged for review." | "The count flagged for human review is shown, and flagged results are not presented as certain." | Runnable. The step 2 sentiment question is the evidence. |
| TS-20-D | "Submit a question that is declined, needs clarification, or must be split." | "The explanation is shown clearly. There is no blank screen or raw error." | Runnable, three questions (declined, clarification, split). |
| TS-20-E | "Open the interface." | "It states that the data is synthetic and that the sentiment model was trained on synthetically written feedback, so it may not reflect real customers." | **Known failing** (`05` §7, "No synthetic-data notice in the interface"). Expected: the notice is absent. Record as found. Not a stop. |

Pass criteria, verbatim:

- **TS-14:** "All four cases show the expected result."
- **TS-16:** "No request exceeds the ceiling, and measurements exist for every request type."
- **TS-18:** "A, B and D behave as stated, with A and B using recorded real provider error responses, and C shows independent scaling." (A and B are local; the deployed ones are C and D.)
- **TS-20:** "All five cases show the expected result."

None of the four says "three of three runs". `05` §2 does: "Cases whose result depends on a model call are
therefore run three times, and the case passes only if all three runs meet the expected result." Whether
that general rule reaches these display and latency cases is Q3. This plan budgets both readings
(section 5) and runs **one** run of each case as the base, with repeats where they are cheap.

---

## 3. Run order and schedule

The prompt lists the steps as open, scenarios, cold start, failure path, grader check, close. **The run order
differs, and the step numbers are kept as labels.** Reason: a cold-start measurement needs the whole chain
idle for about 15 minutes, and any request to `*.run.app` (a scenario question, a probe, `verify.py`)
resets that. So the idle waits come right after `verify.py`, and the warm scenarios follow them.

Run order: **1** open, **2** cold starts (with the no-traffic part of 3 inside the waits), **5a** open the
grader session, **3** scenarios, **4** failure path, **3.7 and 3.8** (TS-18-C, TS-18-D, last), **5b**
revoke and re-test, **6** close.

Clock is minutes from **T0**, the moment the `ops-db` start command is issued. The stop is T0 + 240 (4 hours; moved from 3 hours, see "Owner decisions 2026-10-15" at the end).

| T0 + | What | Who |
|---|---|---|
| (before) | Console balance check, record it | OWNER |
| 0 | Start `ops-db`, wait for RUNNABLE ALWAYS | OWNER |
| 10 | `verify.py --ipv4` (budget **40 min**: the six-service run took about 40 min on 2026-10-14) | CLAUDE-CODE |
| 50 | Open the owner's browser tab, sign in, DevTools open; **no more requests**. Idle wait 1 starts. Inside it: TS-14-D repo scan, `invites list`, create the test invites. | OWNER, CLAUDE-CODE |
| 66 | Cold question 1 (sentiment) | OWNER |
| 68 to 83 | Idle wait 2 (log reads only) | CLAUDE-CODE |
| 84 | Cold question 2 (forecast) | OWNER |
| 86 to 101 | Idle wait 3 (R-05 second reading; log reads only) | CLAUDE-CODE |
| 102 | Cold question 3 (repeat of the slowest path) | OWNER |
| 105 | Grader session (clean profile), then TS-14-A/B/C and TS-20 | OWNER, CLAUDE-CODE |
| 130 | Failure path | CLAUDE-CODE |
| 140 | TS-18-C | CLAUDE-CODE |
| 150 | TS-18-D | OWNER (runs the driver) |
| 160 | Revoke, re-test, then close | OWNER, CLAUDE-CODE |
| 175 | Close complete (`ops-db` STOPPED NEVER) | OWNER |

That leaves **65 minutes of slack** to the 4-hour stop. **Cut order if behind:** (1) idle wait 3 and its repeat
question, (2) TS-18-C, (3) the TS-14-D image scan. (The 3.9 repeat runs are dropped: single run, decision 3.) Nothing is ever cut from
the close. **TS-18-D is the last step that may start, and only by T0 + 150**; after that go straight to 5b and 6.

---

## 4. Steps

### Step 1: Open

| # | Who | Command / action | Expected | Evidence |
|---|---|---|---|---|
| 1.1 | OWNER | Billing console, the paid project's prepaid balance. If under $5, top up to $5 or more (auto-reload stays off, ADR-105). | A figure of **$5 or more**. The prompt says $7.88 at 10-15; the repo's last figure is about $2.9 (R-21, 2026-10-13), so the console value is the only one that counts. There is no API. | Balance and time, for the log and for the $3 stop. |
| 1.2 | OWNER | `git fetch; git status --short; git rev-parse HEAD origin/main` | Clean; both equal `6dd8ba8` or a later docs-only commit. | Hashes. |
| 1.3 | OWNER | `curl.exe -4 -m 20 "$G/health"` | `200`, `{"status":"ok"}`. If it times out, IPv4 is also broken: stop. | Status. |
| 1.4 | OWNER | The runbook's start and wait loop: `gcloud sql instances patch ops-db --activation-policy ALWAYS --project $P`, then `do { $state = gcloud sql instances describe ops-db --project $P --format "value(state,settings.activationPolicy)"; $state; if ($state -notmatch 'RUNNABLE') { Start-Sleep -Seconds 15 } } while ($state -notmatch 'RUNNABLE')` | `RUNNABLE  ALWAYS` within 10 min (RUNBOOK_V rollback table). Write down **T0**. | State line, T0. |
| 1.5 | CLAUDE-CODE | `gcloud builds triggers describe deploy-reporting-slice --region $R --project $P --format "value(disabled)"` then `gcloud builds list --region $R --project $P --limit 1 --format "value(id,status,substitutions.COMMIT_SHA)"` | `True`; the latest build is still `0dc5aae1-2a6c-498e-bbca-f709c2c91149`, `SUCCESS`, `9ab7c775964bd0aae491ca72082e95229c994129`. PR #62 touched a trigger path (`deploy/verify.py`) and the trigger was enabled during Z2b, so a newer build would mean the deployed system is not the evaluated one: **stop**. | Both outputs. |
| 1.6 | CLAUDE-CODE | The eight variables of RUNBOOK_V step 6, then `.venv\Scripts\python deploy\verify.py --ipv4 --gcloud-timeout 600` | `PASS` on every line, exit 0. `EXPECTED_IMAGE_TAG` is the build's `COMMIT_SHA` (`9ab7c77...`), **not** HEAD. One end-to-end question, three paid model calls (about $0.0015). | The full output. |

```powershell
$env:PROJECT_ID = $P; $env:PROJECT_NUMBER = $N; $env:REGION = $R
$env:EXPECTED_IMAGE_TAG = (gcloud builds list --region $R --project $P --limit 1 --format "value(substitutions.COMMIT_SHA)")
$env:ORCHESTRATOR_SA = "run-orchestrator@$P.iam.gserviceaccount.com"
$env:REPORTING_SA = "run-reporting@$P.iam.gserviceaccount.com"
$env:PROBE_SA = "probe-noauth@$P.iam.gserviceaccount.com"
$env:CLOUD_SQL_INSTANCE_NAME = 'ops-db'
```

If a `FAIL` line appears: record it, do not fix it, and continue only if it is not a check the later steps
depend on (a failed `ops-db` or invoker check stops the session).

### Step 2: Cold start for the sentiment and forecast paths (TS-16-D; R-05)

**The figure.** 15 minutes idle is the project's working figure for scale-to-zero (RUNBOOK_V step 12; R-05
update of 2026-10-13, where the first question after 15 minutes took 55.87 s in the browser and 54.47 s at
the gateway). It is a working figure, not a Cloud Run guarantee; the Cloud Run documentation was not read
in this session. So every cold reading is **verified cold from the logs** (below) and a hop that was not
cold is recorded as warm and that path is repeated after another wait if time allows.

**How a reading is taken (same as 2026-10-13, so the numbers compare).** The whole chain is cold: gateway,
orchestrator, specialist, QA. The owner's browser tab is opened and signed in **before** the idle starts and
is **not reloaded**: loading the page or exchanging an invite is itself a request to the gateway and would
make it warm. The timed request is the first `/api/ask` of the tab.

| # | Who | Action | Expected | Evidence |
|---|---|---|---|---|
| 2.0 | OWNER | After 1.6: open `owner-laptop`'s link in the browser, sign in, open DevTools, Network, "Preserve log". Note the clock time of the last request. Do nothing else. | The UI loads and is signed in. If the owner's invite has lapsed or is missing, create a fresh one at the cost of one more idle start (`list` first). | Time of last request. |
| 2.1 | (wait) | 15 minutes with **no request to `*.run.app`**. Allowed: log reads (`gcloud logging read`), `scripts\invites.py list`, the TS-14-D repo scan, writing notes. Not allowed: any probe, `verify.py`, opening a new page, any `curl` to a service. | | |
| 2.2 | OWNER | Press Ask on **"What does customer sentiment look like across all sites for July 2026?"** (the `05` TS-07-A text). Stopwatch from the click to the answer; from DevTools read the `/api/ask` time and the `X-Trace-Id` response header. | An answer inside 120 s (`05` TS-16-D). About 56 s is the reference. | Seconds, trace ID, a screenshot of the answer (it is also TS-20-C evidence: flagged-for-review count). |
| 2.3 | CLAUDE-CODE | Per-hop durations by trace ID (RUNBOOK_V step 12.3) and the start-ups in the window (below). | One `request` line per service; the first request to a cold instance shows the start-up in its `duration_ms`; a start-up line (empty trace ID) in the minutes before the question for each hop. | The table: service, path, status, `duration_ms`. |
| 2.4 | (wait) | 15 minutes from the answer, same rules. | | |
| 2.5 | OWNER | Ask **"How many install requests should we expect over the next 8 weeks?"** (`05` TS-01-C and TS-08-B text). Same capture. | Within 120 s. Weeks 1 to 4 listed with the stored error and no number, weeks 5 to 8 served (`05` TS-08-B), as a free check. | As 2.2. |
| 2.6 | CLAUDE-CODE | As 2.3. | | |
| 2.7 | (wait) | 15 minutes from the answer. This is **R-05's second idle wait**. | | |
| 2.8 | OWNER | Repeat **one** question. **The rule is fixed now:** repeat the path with the highest first reading, counting the 55.87 s reporting reading of 2026-10-13 as a candidate. If reporting is highest, ask **"What was SLA compliance in the west region in July 2026?"** (`05` TS-05-B text); otherwise repeat the slower of the two paths just measured. | Within 120 s; a figure close to its first reading shows the 56 s was not a one-off. | As 2.2. |
| 2.9 | CLAUDE-CODE | As 2.3, then a free read of retry lines over the whole session: the logging of each failed model-call attempt (`llm attempt failed`, ADR-108) is "still not verified deployed" and shows only if a retry happened. Do not try to cause one. | Present or absent; record which. | Count of such lines. |

```powershell
# per-hop lines of one question (the form confirmed 2026-10-14, Z2b)
gcloud logging read "resource.type=cloud_run_revision AND jsonPayload.trace_id=`"<trace id>`" AND jsonPayload.msg=`"request`"" --project $P --freshness 2h --format "table(jsonPayload.service,jsonPayload.path,jsonPayload.status,jsonPayload.duration_ms)"
# start-ups in a window: start-up lines carry an empty trace ID; read the service's lines before the question
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=ops-sentiment AND timestamp>=`"<ISO start of the wait>`"" --project $P --freshness 2h --limit 50 --format "table(timestamp,jsonPayload.msg,jsonPayload.trace_id)"
```

Repeat the second command for `ops-gateway`, `ops-orchestrator`, the specialist and `ops-qa`. R-05's rule
stands: a service over 40 s alone is recorded under R-05 and `min_instances=1` is considered for it
(ADR-107 keeps it out of scope).

### Step 3: `05`'s deployed scenarios

**3.1 TS-14-D (inside idle wait 1; CLAUDE-CODE; zero requests).** The repo: `git grep -n -I -E "AIza[0-9A-Za-z_-]{35}|BEGIN [A-Z ]*PRIVATE KEY"` and a search of the tracked `.env*` names (expected: none, only `.env.example`
if any). The deployed configuration: for each of the six services,
`gcloud run services describe <svc> --region $R --project $P --format json` and check that every sensitive
variable is a `valueFrom.secretKeyRef`, never a literal `value`. The built images are **not** scanned
unless time allows (Q5). **Expected:** none found.

**3.2 TS-14-B and TS-14-C (CLAUDE-CODE; after step 2).** Unauthenticated, IPv4, zero model calls:

```powershell
foreach ($s in 'ops-orchestrator','ops-reporting','ops-sentiment','ops-forecast','ops-qa') {
  $u = gcloud run services describe $s --region $R --project $P --format "value(status.url)"
  "{0}: {1}" -f $s, (curl.exe -4 -s -o NUL -w '%{http_code}' -m 20 "$u/")
}
"gateway /health: " + (curl.exe -4 -s -o NUL -w '%{http_code}' -m 20 "$G/health")
```

**Expected:** `403` (or another refusal, never `200`) for the five internal services; `200` for the
gateway. The same five lines are TS-14-C ("Rejected"), since an unauthenticated call carries no
orchestrator identity. The tool servers: "not separately reachable (sidecars)".

**3.3 Grader session and TS-14-A (steps 5a, then OWNER).** See step 5. The valid-invite question is the
TS-20-A question below, asked from the clean profile. The three negatives:

| Case | Command | Expected |
|---|---|---|
| No session | `curl.exe -4 -s -X POST "$G/api/ask" -H "Origin: $G" -H "Content-Type: application/json" --data-raw '{\"question\":\"hello\"}' -w "`n%{http_code}"` (CLAUDE-CODE) | `401`; no model call (the router's `require_session` runs first). |
| Expired | OWNER: `invites.py create --label session1-expired --days 0.001 ...`, wait 2 min, `Test-Invite '<link>'` | `401`. |
| Revoked | OWNER: `create --label session1-revoked --days 0.25 ...`; CLAUDE-CODE: `invites.py --secret $S list`, then `revoke --id <id>`; wait **70 s** (the Secret Manager read is cached up to 60 s); OWNER: `Test-Invite '<link>'` | `401`, with a body **identical** to an unknown token's (`Test-Invite 'x#invite=not-a-real-token'`) and to the expired one. |

`Test-Invite` is the helper in RUNBOOK_V step 10 (it uses `-split '#invite='`, not `.Split`).

**3.4 TS-20-A (clean profile; OWNER).** Ask **"What was SLA compliance in the west region in July 2026?"**
(`05` TS-05-B text). Expected: an "Interpreted as:" line, a verification line, the as-of date (2026-08-30).
Evidence: screenshot, and the model-call cost from the logs.

**3.5 TS-20-C.** Taken from the step 2.2 answer. If its flagged-for-review count is not shown or the page
was not the final one, ask the same question once more here.

**3.6 TS-20-D (three questions; OWNER).**

| Kind | Question | Expected |
|---|---|---|
| Declined | "How do our response times compare with other field service companies?" (`05` TS-04-B) | A clear decline; no blank screen, no raw error. One model call. |
| Needs clarification | "What is the SLA compliance for technician Priya?" (`05` TS-06-D, second input) | A list of matching technicians (at most five) and a question about which is meant. This replaces TS-02-A, which is **known failing** (force-routed) and would answer. |
| Must be split | "How many repeat visits did we have last quarter, and what will request volume be next month?" (`05` TS-03-A) | The split instruction; no specialist called. |

**3.7 TS-18-C (CLAUDE-CODE, through the session driver and the gateway; the driver's `ask --parallel`, with the `session1-grader` invite; supersedes "direct to the orchestrator").** Six reporting
questions in parallel (threads) with one forecast question, the question text varied so no answer is shared:
the six are the `05` TS-05-B text with six different regions or months; the forecast is the TS-08-B text.
**Expected:** the forecast answered with weeks 5 to 8 served and weeks 1 to 4 unserved; the six reporting
questions answered. Scaling evidence is read afterwards: the number of distinct instances behind the
`request` lines of `ops-reporting` and `ops-forecast` in the window (the instance field name is confirmed on
the first read; it is not assumed here). A Cloud Monitoring `instance_count` reading, if the owner wants
the console view, is an OWNER read. **Expected, honestly:** the forecast service stays at one instance; the
reporting service **may or may not** reach two.

**3.8 TS-18-D (OWNER runs the driver; last of the warm steps).** With its own invite, `session1-cap`, so
nothing else stacks on its hour. The driver exchanges the link (held in the owner's shell, never printed),
then sends **31** copies of **"How do our response times compare with other field service companies?"**
(declined at routing: one model call, the cheapest accepted question) at the invite's normal pace.
**Expected:** 30 answered or declined normally, the **31st** refused with HTTP 429 and the message
"Too many questions this hour (limit 30). Please try again later.", and no model call for it (the counter
sits before the model call in `api_gateway/app.py`, `/api/ask`). The gateway runs `maxInstanceCount: 1`,
so its in-process counter is one counter; if the gateway was cold-started after the 30th, the counter
reset and the result is void: record it and stop. This test uses **30 of the 50 daily questions**.

**3.9 Repeat runs (optional, section 5's second reading of `05` §2).** CLAUDE-CODE, through the ledgered
driver, direct to the orchestrator: runs 2 and 3 of the TS-20-A, TS-20-C and the three TS-20-D questions,
checking `route`, `outcome`, `qa_status`, `parsed_request`. These check consistency, not rendering. First
to be cut.

### Step 4: One live failure path, for its log codes

**The goal.** Sprint log (2026-10-14, Z2b): `code` on a failed task and `outcome=degraded` were read from
the code, never seen. `docs/sprint-log.md` suggests "a refused name".

**Checked against the code, and it changes the choice.** A technician or account name that matches no one
or several is **not** a failed-task line: `services/orchestrator/src/orchestrator/app.py` returns the
`needs_clarification` answer for the `_CLARIFY` codes **before** it writes `agent task failed`. So a refused
name never writes a `.code`. The line with `.code` is written only for the other failure codes.

**The cheapest path that reaches it: an invalid range, two model calls (route and parse), no QA.** The
reporting agent fails the task with `code=invalid_range` when the tool rejects the range (start after end,
`mcp_incidents/queries.py`). The question: **"What was SLA compliance in the west region from August 2026
to January 2026?"** If the parser normalises the order and answers, record that, and try once more with
"from 2026-08-31 back to 2026-01-01". Budget two requests.

**Why not fewer calls.** Zero-call refusals (no session, over-length, expired invite) end at the gateway
and never reach the orchestrator, so no orchestrator `.code`. A routing-only decline is one call but is
`declined`, not a failure. Two calls is the cheapest path that reaches `agent task failed`.

**Not reachable live:** `outcome=degraded`. It needs a figures failure, a timeout, a stopped specialist or a
stopped QA, each a fault injection or a configuration change. It stays unexercised and is recorded as such;
the `degraded` line was read from the code only (Z2b, 2026-10-14).

| # | Who | Action | Expected | Evidence |
|---|---|---|---|---|
| 4.1 | CLAUDE-CODE | Send the question with the session driver's `ask --kind failure` through the gateway (supersedes "direct to the orchestrator"; the gateway returns the upstream 422 with the `invalid_range` or `unclear_question` error code). | HTTP `422`, `error` `invalid_range` (or `unclear_question`, if the parser rejects it first). **Not a 5xx.** | Status, body, `trace_id`. |
| 4.2 | CLAUDE-CODE | `gcloud logging read` by that `trace_id` (RUNBOOK_V step 12.3 form), without the `msg="request"` clause. | A `msg="agent task failed"` line with `.agent`, `.code` equal to the failure code, `reason_chars` and `reason_sha`; `request` lines for the orchestrator and reporting. **No** question text, no router reason, no exception message (ADR-108; TS-15-D). | The line, field by field. |

### Step 5: Grader-access check

| # | Who | Action | Expected | Evidence |
|---|---|---|---|---|
| 5.0 | OWNER | During idle wait 1 (Secret Manager only, no service traffic): `.venv\Scripts\python scripts\invites.py --secret $S create --label session1-grader --days 0.25 --base-url $G`; the same for `session1-cap`. Copy each link to the password manager. **Never into a chat, a commit or a document.** | A link prints once per invite. | Labels and ids from `list`; no link. |
| 5a | OWNER | A **new browser profile** (or a private window of a browser that has no owner session). Open the `session1-grader` link. | The page loads, the invite exchanges, a `__Host-session` cookie is set (`Secure; HttpOnly; SameSite=Strict`), and an answer comes back to the TS-20-A question. | Screenshot; the cookie flags (DevTools, Application). |
| 5b | CLAUDE-CODE, then OWNER | After step 3.8: `invites.py list`, `invites.py revoke --id <session1-grader id>`; wait 70 s; OWNER reloads the page and asks again. | The question is refused; `/api/session` refuses the old cookie. | The refusal and its body. |

### Step 6: Close (always runs, whatever the stop reason)

| # | Who | Action | Expected | Evidence |
|---|---|---|---|---|
| 6.1 | CLAUDE-CODE | `.venv\Scripts\python scripts\invites.py --secret $S list`, then `revoke --id` for each session invite that is not already revoked (`session1-grader`, `session1-cap`, `session1-expired`, `session1-revoked`). Never `owner-laptop`. | Every `session1-*` row is revoked or expired. | `list` output (labels, ids, status). |
| 6.2 | OWNER | `gcloud sql instances patch ops-db --activation-policy NEVER --project $P`, then `gcloud sql instances describe ops-db --project $P --format "value(state,settings.activationPolicy)"` | **`STOPPED  NEVER`**. Write down the stop time. | The state line. |
| 6.3 | CLAUDE-CODE | `gcloud builds list --region $R --project $P --limit 1 --format "value(id)"` and the trigger's `disabled` | Same build id as 1.5; `True`. | Both. |
| 6.4 | OWNER | The console balance again. | Opening balance minus closing balance against the logged `cost_usd` total: a free check on L-71's list-price estimate. | Balance, time. |
| 6.5 | CLAUDE-CODE | Append a dated entry to `docs/deploy-window-log.md`: date, `ops-db` start and stop times, opening and closing balance, the session invite ids and labels (**never a link or a token**), the steps run and not run, the stop reason if any, the ledger totals. | | The entry. |
| 6.6 | OWNER | Remove session variables: `Get-ChildItem env: | Where-Object Name -like 'DB_ROLE_*' | ForEach-Object { Remove-Item "env:$($_.Name)" }`, and delete the invite links from the shell history. | | |

---

## 5. Call budget

**Units.** A *request* is one `/ask`. A model call is the router call, the parse call and, on an answered
question, QA's interpretation check (advisory, ADR-102). Answered: 2 nominal + 1 advisory (the local proof
of 2026-10-14 made three calls for one question). Declined or split at routing: 1 nominal, 0 advisory
(assumed from the architecture; the logged `cost_usd` confirms or corrects it). Failure path and
clarification: 2 nominal, 0 advisory.

**Retry margin rule.** One retry per call, bounded by the Sprint 5 bound of **5 model calls per request**
(186 requests, 930 calls). So: worst case per request = min(2 x (nominal + advisory), 5).

**Dollars.** About $0.00053 a call nominal ($0.001604 for a verified question's three calls, ADR-091 /
R-05; $0.000948 for a degraded one's routing and parse; about $0.0015 for `verify.py`'s three; $0.1727 for
the 186 X requests, an average $0.00093). Worst case uses $0.00058 a call, the highest request cost seen
(`max_request_cost_usd` $0.001737, `sprint5_x_ledger.json`) over three calls. All list-price estimates
(L-71), not billing.

### Single run of each case (the base)

| Step | What | Requests | Nominal | Advisory | Worst calls | Est. $ | Worst $ |
|---|---|---:|---:|---:|---:|---:|---:|
| 1.6 | `verify.py` question | 1 | 2 | 1 | 5 | 0.0016 | 0.0029 |
| 2.2 | Cold sentiment | 1 | 2 | 1 | 5 | 0.0016 | 0.0029 |
| 2.5 | Cold forecast | 1 | 2 | 1 | 5 | 0.0016 | 0.0029 |
| 2.8 | R-05 repeat | 1 | 2 | 1 | 5 | 0.0016 | 0.0029 |
| 3.4 | TS-20-A (reporting; also TS-14-A valid) | 1 | 2 | 1 | 5 | 0.0016 | 0.0029 |
| 3.5 | TS-20-C (only if 2.2 did not show it) | 1 | 2 | 1 | 5 | 0.0016 | 0.0029 |
| 3.6 | TS-20-D declined | 1 | 1 | 0 | 2 | 0.0005 | 0.0012 |
| 3.6 | TS-20-D clarification | 1 | 2 | 0 | 4 | 0.0011 | 0.0023 |
| 3.6 | TS-20-D split | 1 | 1 | 0 | 2 | 0.0005 | 0.0012 |
| 3.2, 3.3 | TS-14-A/B/C refusals, 5 probes, TS-14-D | 0 | 0 | 0 | 0 | 0 | 0 |
| 3.7 | TS-18-C: 6 reporting + 1 forecast | 7 | 14 | 7 | 35 | 0.0111 | 0.0203 |
| 3.8 | TS-18-D: 30 accepted (+1 refused, no call) | 30 | 30 | 0 | 60 | 0.0159 | 0.0348 |
| 4 | Failure path (two attempts budgeted) | 2 | 4 | 0 | 8 | 0.0021 | 0.0046 |
| | **Total, base** | **48** | **64** | **13** | **141** | **0.041** | **0.082** |

Worst case is **141 calls, $0.08**, against the paid balance of **$7.88 at 10-15 (the prompt's figure;
unconfirmed, Q7)**. Dollars are not the binding constraint. The $3 floor cannot be reached by this session:
$7.88 minus $0.08. The binding limits are the gateway's counters and the clock.

### The three-run reading of `05` §2 (if the owner rules it applies)

Rows that depend on a model call are repeated three times. The two cold-start rows cannot be (each run is
a 15-minute idle wait).

| | Requests | Nominal + advisory | Worst calls | Est. $ | Worst $ |
|---|---:|---:|---:|---:|---:|
| Base (above) | 48 | 77 | 141 | 0.041 | 0.082 |
| TS-20-A, C, D x2 more | +10 | +20 | +36 | +0.011 | +0.021 |
| TS-18-C x2 more | +14 | +42 | +70 | +0.022 | +0.041 |
| TS-18-D x2 more | +60 | +60 | +120 | +0.032 | +0.070 |
| Failure path x2 more | +2 | +4 | +8 | +0.002 | +0.005 |
| **Total, three-run** | **134** | **203** | **375** | **0.108** | **0.217** |

Still far under $3. **But it does not fit the day:** gateway-counted questions would be 3 (cold) + 15
(TS-20 by hand, three runs) + 90 (TS-18-D three runs) = **108 against the 50 a day**. TS-18-D alone is 90.
So under the three-run reading, TS-18-D takes three separate days or one run is accepted and the
deviation from `05` §2 is recorded (Q3).

### Gateway counters: the arithmetic that actually binds

The hourly cap is `SlidingWindow(30, 3600.0)`, a **rolling 60 minutes per invite id**, not a clock hour
(`api_gateway/app.py`). Both counters are in process and reset on a gateway cold start (L-88). The gateway
runs one instance (`maxInstanceCount: 1`), so each is one counter.

| Rolling 60 min, per invite | Questions accepted (base) | Against the 30 cap |
|---|---:|---|
| `owner-laptop` | 3 (2.2, 2.5, 2.8) | 3 |
| `session1-grader` | 4 to 5 (3.4, 3.5, 3.6 x3) | 5 |
| `session1-cap` | **30** (+1 refused) | **Deliberately at the cap** |
| `verify.py` (1.6, direct to the orchestrator; tally it as 1) | n/a, ledger only | |

**The "24 or fewer an hour" rule cannot hold for TS-18-D.** The case needs 30 accepted questions on one
invite inside an hour. The plan keeps **every other invite at 5 or fewer** and gives TS-18-D its own invite
and the last warm slot. It does not drop or reshape the case (Q2). The daily cap: base gateway-counted
questions are 3 + 5 + 30 = **38 of 50**; the 31st TS-18-D question is refused before it takes a daily
slot.

**Busiest hour.** TS-18-D: 30 questions and 30 nominal model calls (60 worst) on one invite in about 5
minutes. Across everything, the warm phase (T0 + 105 to 160) carries about 63 nominal calls (122 worst).

### The ledger setting

| Setting | Value | What it enforces |
|---|---|---|
| State file | `evals/results/session1_ledger.json` (new; the existing files are never reused or reset) | |
| `cap_requests` | **60** (48 planned + 25%) | The driver refuses the 61st request it would send. Counts requests sent by the driver, plus one `sent` entry per owner browser question (a manual tally, entered by CLAUDE-CODE when the owner says "asked"). |
| `cap_model_calls` | 300 (60 x 5) | Bounded, not counted (L-94: the response has no call count). |
| `cap_usd` | **$0.25** (about 3 x the worst case) | Charged by `cost_usd` from the orchestrator's log line, one request behind; an unknown cost is charged at the highest seen (`max_request_cost_usd`). |
| Consecutive errors | 3 (not the X run's 5) | Stops the run on an outage. |

**What this does not enforce.** Questions typed into the browser go through the gateway and are invisible
to any driver; they are bounded by the owner's tally and the gateway's own caps. `verify.py` makes its own
call. The $3 balance floor has **no API**: the stop is estimated as opening console balance minus the
logged `cost_usd` total (and re-read from the console at step 6.4). Per-process caps (`LLM_MAX_REQUESTS`,
`LLM_MAX_SPEND_USD`) are not a limit on this session (L-93).

---

## 6. Stop rules

Stop and go to step 6 if **any** of:

1. the ledger reaches its total (60 requests or $0.25);
2. the balance would fall below **$3**: opening console balance minus the logged `cost_usd` total (an
   estimate, there is no API);
3. an **unexpected 5xx** appears. Expected statuses are: `200`; `422` for the failure path; `401`/`403` for
   the refusals and the probes; `429` for the 31st TS-18-D question. A 5xx from the gateway or the
   orchestrator is unexpected; so is a `degraded` answer to an ordinary warm question;
4. a step's result differs from its expected result. **Record it; don't fix it. No deploys during the
   session.** Cases `05` already records as known failing (TS-20-E, and TS-02-A if asked) are expected to
   fail and do not stop it; TS-20-B is recorded "not run, no trigger", not as a difference;
5. **4 hours** have passed since T0 (was 3; moved 2026-10-15, an assistant rule, not an ADR).

Also: if 1.5 shows a newer build, or the trigger enabled, stop before any model call. Whatever the stop
reason, **step 6 still runs**, and `ops-db` is never left running.

---

## 7. The record: where each result goes

| Result | Goes to |
|---|---|
| Raw capture (driver output, ledger, screenshots, log reads) | `evals/results/session1/2026-10-17/` (new). Ledger totals and the per-hop table with it. No generated row, no key, no link. |
| The session narrative, times, balance, invite ids and labels | `docs/deploy-window-log.md`, one dated entry (ADR-110). |
| Sprint 6 items ticked or annotated | `docs/sprint-log.md`: "Window A: run `05`'s deployed scenarios", "Window A: time the cold start on the sentiment and forecast paths", "Failure-path log codes", "Still not verified deployed" (retry logging), "Owner verification session 1". Dated entries, append-only. |
| Cold start numbers, second idle wait | `docs/risk-register.md` R-05, a new dated update. |
| Balance and the $-per-answer reading | R-21 and L-71, a dated update; R-21's "about $2.9" is stale (not edited by this plan). |
| A new limitation found (for instance TS-20-B has no trigger; a counter reset on cold start) | `docs/evaluation-report.md` Limitations log, a dated entry each. |
| `05` revision (statuses and results) | **Owner**, in `05`. Claude Code does not edit `05`. |
| `06`, **confirmation 1 (scenarios)** | TS-14-A to D, TS-18-C and D, TS-20-A to E, one line each: result, evidence path. |
| `06`, **confirmation 2 (cold starts)** | The TS-16-D table: path, idle minutes, verified cold (yes/no), seconds in the browser, per-hop `duration_ms`; reporting's two readings; the sentiment and forecast readings. |
| `06`, **confirmation 3 (grader access)** | Step 5: clean profile, exchange, answer, revoke, refusal; cookie flags. |
| Failure-path log codes | Not one of `06`'s three. Sprint log, and `RUNBOOK_GRADING.md` "Reading one request's logs" if a field differs from what it says. |

---

## 8. Owner time

| Block | Clock | Owner at the keyboard |
|---|---:|---:|
| Console balance, start `ops-db`, wait (T0 to T0 + 10; 5 min of the balance check before T0) | 10 min | 8 min |
| `verify.py` (T0 + 10 to + 50) | 40 min | 3 min |
| Browser tab, three idle waits, three cold questions, invites created inside the waits (T0 + 50 to + 102) | 52 min | 14 min |
| Clean profile, TS-14-A negatives, probes, TS-20 (T0 + 105 to + 130) | 25 min (+3 gap) | 24 min |
| Failure path, TS-18-C (CLAUDE-CODE) | 20 min | 0 min |
| TS-18-D (the owner runs the driver) | 10 min | 5 min |
| Revoke, re-test, close, closing balance | 15 min | 10 min |
| **Total** | **175 min from T0 (about 2 h 55 min), 65 min of slack to the 4 h stop** | **about 65 to 70 min** |

The longest single item is `verify.py` (about 40 min last time). If it runs past 50 minutes, cut idle wait
3 first.

---

## 9. Open questions and prerequisites for the owner

**Before Saturday (nothing here is built; this prompt may not build it):**

- **Q1. The driver and the ledger.** A small driver is needed: a new state file and caps per section 5,
  the `harness.py` ledger pattern (log-read `cost_usd`, one request behind), IPv4 forcing using the same
  approach as `verify.py` (`connect_socket(..., ipv4)`), a parallel mode for TS-18-C, a gateway mode that
  takes the invite link from the owner's environment and never prints it, and a `sent` entry for browser
  questions. Does the owner want it written in a separate prompt, or run the session without a
  ledger-enforced total and rely on the tally and gateway counters?
- **Q2. The 24-an-hour rule against TS-18-D.** Is "calls" model calls or gateway questions? Either way
  TS-18-D alone is 30. Confirm the exception for `session1-cap`.
- **Q3. Three runs.** Does `05` §2's three-run rule apply to TS-14, TS-16, TS-18 and TS-20? Their pass
  criteria do not say it. If yes: TS-18-D needs three days (90 of a 50-a-day cap) and TS-16-D three
  readings per path are three more idle waits each. If no: record that the display and latency cases ran
  once.
- **Q4. TS-20-B.** No trigger for a degraded result exists on the deployed system without a deploy or a
  fault injection. Accept "not run, no trigger", or defer it to a local run (the expected result is
  already covered by `services/orchestrator/tests/test_qa_loop.py`).
- **Q5. TS-14-D and TS-14-B.** The tool servers have no URL. Scanning nine built images for credentials is
  heavy. Accept repo grep plus the deployed configuration check as the evidence, and say so in `05`?
- **Q6. TS-17.** `05` says Local; `sprint-log.md` line 1093 says deployed. Each case stops a service, which
  Cloud Run only allows as a configuration change. Treat it as local and correct the sprint-log line (a
  dated entry), or schedule it with a rollback plan in a window?
- **Q7. Balance.** The prompt gives $7.88 at 10-15; the last repo figure is about $2.9 (R-21, 2026-10-13).
  Neither is a console reading in the repo. Step 1.1 records the real one.

**Things in `05` that cannot be run as written (quoted):**

- TS-20-B: "Trigger a degraded result." (no trigger without a deploy or fault injection)
- TS-14-B: "...and each tool server." (sidecars, no URL)
- TS-14-D: "Search the code repository and the built container images for credentials." (images: heavy)
- TS-18-C: "The reporting service scales up, and the forecast service does not." (scale-up not guaranteed at
  concurrency 8, max 2 instances)
- TS-18-D: "Through the interface, ask more questions with one invite than the hourly limit of 30 allows." (31 by
  hand is impractical; the plan drives the same gateway route with a script)
- TS-20-E: known failing, by `05` §7.
- TS-15-B (local, not in this session): "a question over 2,000 characters is refused with a clear message".
  The orchestrator's limit is 2,000 (`AskRequest`), but the gateway's `MAX_QUESTION_CHARS` is **500**
  (`api_gateway/app.py`), so through the interface the refusal comes at 500.

**A choice the plan made that the owner should confirm:** the failure path is an invalid range, not a
refused name, because a refused name returns `needs_clarification` before the `agent task failed` line is
written, so it would not show a `.code` (step 4).

---

## Owner decisions 2026-10-15

*Dated 2026-10-15 (Prompt S6-W1; owner-decided 2026-10-15; assistant-drafted). These supersede the text
above where they differ; the text above is edited only at the lines named in "Edits made".*

1. **Ledger.** `scripts/session_driver.py` enforces **60 requests and $0.25** (`init --max-requests 60
   --max-dollars 0.25`). Browser questions go in by `tally`. **Arithmetic the owner should check:** the
   driver counts exchanges and probes as requests too. About 44 driver questions, 4 tallies (three browser
   cold-start questions and `verify.py`), roughly 8 exchanges and 8 probes come to about 64. At 60 the
   driver will refuse the last few. Either `init` with `--max-requests 75` (the $0.25 cap is untouched
   and still the tighter limit on spend), or cut the optional items (3.5, the TS-14-B probes of
   services that `verify.py` already checks). The owner decides at `init`; the caps never change after.
2. **TS-18-D is an exception to the 24-per-hour rule, by design.** It runs on its own invite
   (`session1-cap`); the hourly cap is a rolling 60 minutes per invite.
3. **Single run for TS-14, TS-16, TS-18 and TS-20.** `05` §2's three-run rule is not applied to them;
   the owner scopes it in the `05` revision. The repeat runs (3.9) are dropped.
4. **TS-20-B is not run:** there is no trigger without a deploy, and deploys are barred in the session.
5. **TS-14-D's evidence is a grep of the build context** (the files each Dockerfile copies) at the
   deployed commit (`9ab7c77`), plus the deployed environment configuration. **Built images are not
   scanned; that is the recorded limit.**
6. **TS-17 stays Local,** per `05`.
7. **The balance is $7.88,** topped up 2026-10-15. Step 1.1's console reading governs.
8. **The failure path is an invalid date range,** for the reason given in step 4 (a refused name
   returns `needs_clarification` before `agent task failed` is written).
9. **The session stop moves from 3 hours to 4 hours** (T0 + 240). The 3-hour cap was an assistant rule,
   not an ADR, and the plan had 5 minutes of slack; it now has 65.

### Edits made

Stop rule 5, the schedule's slack and cut order, the owner-time total, and the three "direct to the
orchestrator" request steps (3.7, 4.1, the invite table) now say the driver and the gateway. Daily cap
arithmetic changes with them: gateway-counted questions are 3 (browser) + 4 to 5 (3.4, 3.6) + 7 (3.7) +
2 (4) + 30 (3.8) = **46 to 47 of 50**. That is tight; the 31st TS-18-D question is refused before it
takes a daily slot, and the gateway's counters reset on a cold start (L-88).

### The driver commands, in order

Windows PowerShell 5.1, from the repo root. The credential is **`SESSION_INVITE_LINK`**, one invite at a
time. Commands that read it are **OWNER**: the link prints once and never goes to a chat or to Claude Code.
`init`, `status`, `tally` and `probe` need no credential and are **CLAUDE-CODE**. Output is counts and
statuses only.

```powershell
$L = 'evals\results\session1\2026-10-17\ledger.json'
$D = '.venv\Scripts\python scripts\session_driver.py --ledger ' + $L

# Step 1 (after 1.5): create the ledger, then tally verify.py's question (1.6)           CLAUDE-CODE
.venv\Scripts\python scripts\session_driver.py --ledger $L init --max-requests 60 --max-dollars 0.25
.venv\Scripts\python scripts\session_driver.py --ledger $L tally --count 1 --kind answered --scenario S1-open --note "verify.py end-to-end question"

# Step 2: after each browser cold-start question (2.2, 2.5, 2.8), one tally each          CLAUDE-CODE
.venv\Scripts\python scripts\session_driver.py --ledger $L tally --count 1 --kind answered --scenario TS-16-D --note "browser cold start: sentiment"

# Step 3.2: TS-14-B and TS-14-C, no credential; one per URL from `gcloud run services describe`   CLAUDE-CODE
.venv\Scripts\python scripts\session_driver.py --ledger $L probe --scenario TS-14-B --url "<service url>/" --method GET --mode nosession

# Step 3.3: TS-14-A, no session and a made-up cookie                                       CLAUDE-CODE
.venv\Scripts\python scripts\session_driver.py --ledger $L probe --scenario TS-14-A --mode nosession
.venv\Scripts\python scripts\session_driver.py --ledger $L probe --scenario TS-14-A --mode badtoken

# Steps 5a, 3.4, 3.6: with session1-grader's link in the OWNER's shell                    OWNER
$env:SESSION_INVITE_LINK = '<session1-grader link>'
.venv\Scripts\python scripts\session_driver.py --ledger $L ask --scenario TS-20-A --question "What was SLA compliance in the west region in July 2026?"
.venv\Scripts\python scripts\session_driver.py --ledger $L ask --scenario TS-20-D --kind declined --question "How do our response times compare with other field service companies?"
.venv\Scripts\python scripts\session_driver.py --ledger $L ask --scenario TS-20-D --kind clarify --question "What is the SLA compliance for technician Priya?"
.venv\Scripts\python scripts\session_driver.py --ledger $L ask --scenario TS-20-D --kind declined --question "How many repeat visits did we have last quarter, and what will request volume be next month?"

# Step 4: the failure path (an invalid range)                                              OWNER
.venv\Scripts\python scripts\session_driver.py --ledger $L ask --scenario S4-failure --kind failure --question "What was SLA compliance in the west region from August 2026 to January 2026?"

# Step 3.7: TS-18-C, six reporting and one forecast at once                                OWNER
.venv\Scripts\python scripts\session_driver.py --ledger $L ask --scenario TS-18-C --parallel 7 `
  --question "What was SLA compliance in the west region in July 2026?" `
  --question "What was SLA compliance in the east region in July 2026?" `
  --question "What was SLA compliance in the central region in July 2026?" `
  --question "What was SLA compliance in the southeast region in July 2026?" `
  --question "What was SLA compliance in the northeast region in July 2026?" `
  --question "What was SLA compliance in the west region in June 2026?" `
  --question "How many install requests should we expect over the next 8 weeks?"

# Step 3.8: TS-18-D, with session1-cap's link (set SESSION_INVITE_LINK to it first)        OWNER
.venv\Scripts\python scripts\session_driver.py --ledger $L cap-test --scenario TS-18-D

# Any time, and at the close                                                               CLAUDE-CODE
.venv\Scripts\python scripts\session_driver.py --ledger $L status
Remove-Item Env:SESSION_INVITE_LINK
```

The optional driver cold start (`coldstart --path reporting|sentiment|forecast --wait-seconds 900`)
exchanges the invite, idles in-process with no request, then times one question. The browser technique
in step 2 stays the primary reading because it matches 2026-10-13's measurement; the driver's reading is
client-side only and is a cross-check. Evidence lines are in `ledger.json.evidence.jsonl` beside the
ledger. The regions in the TS-18-C questions are examples; use five region names the dataset has.
