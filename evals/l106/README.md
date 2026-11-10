# L-106 verification: evidence, interpretation table, pass rule (pre-registered)

Commit this section verbatim to `evals/l106/README.md` and push it **before any live action**. Nothing in it changes after a result is seen. Results are counts ("k of n starts"), never rates. No outcome names a cause.

## 1. Rounds

| Round | Configuration | Earliest start |
|---|---|---|
| R0 (control) | current revisions: 60 s startup window, no boost | before the deploy |
| R1, R2, R3 | ADR-120 revisions | 20 min after the last request to any service |
| R4 (late) | ADR-120 revisions | 20 min idle **and** 100 min after the rollout finished |

- **Why R4.** On 2026-10-30 the old configuration passed after its rollout too: reporting's first failure came 60 min after it, QA's 99 min after it. Rounds that end inside that span can't be told apart from 10-30's first hour.
- **Idle is 20 min, not 15.** On 10-30 an instance shut down 15 min after its last request, so 15 is the boundary.
- **Cold is proved, not assumed.** A service counts in a round only if the system log shows `Starting new instance. Reason: AUTOSCALING` for it inside the round. No such line means it was warm, and it is not counted.
- **Each round,** asked by the owner in the browser:
  1. load the page, then Q1 `What was SLA compliance in the Northeast last month?`
  2. Q2 `Show examples of negative comments from last month`
  3. Q3 `What weekly request volume should we expect for the next 8 weeks?`
- **Retry.** A degraded or "Not verified" answer gets the same question once more, within 30 s. No other retry.
- **Nothing wakes a service during an idle wait:** no `verify.py`, no request to a `run.app` URL, no page reload. `describe` and `logging read` are safe.

## 2. Evidence capture

### 2a. Commands (read-only, Windows PowerShell 5.1)

```powershell
$P = 'a2a-agentic-service-ops-gcp'
$R = 'us-central1'
$S = 'ops-gateway','ops-orchestrator','ops-reporting','ops-sentiment','ops-forecast','ops-qa'
New-Item -ItemType Directory -Force '.local\l106' | Out-Null

function Read-Logs([string]$Filter, [string]$OutFile, [int]$Limit = 20000) {
  # PowerShell 5.1 drops inner double quotes on native calls; \" keeps them.
  $a = $Filter -replace '"', '\"'
  gcloud logging read $a --project $P --order asc --limit $Limit --format json |
    Out-File -Encoding utf8 $OutFile
}
```

**C1. Every Cloud Run entry in a window** (system, requests, stdout, stderr; all six services). This is the record; parse it locally.

```powershell
$t0 = '2026-10-30T18:30:00Z'; $t1 = '2026-10-30T20:00:00Z'   # calibration window
Read-Logs ('resource.type="cloud_run_revision" AND resource.labels.location="us-central1" AND timestamp>="' + $t0 + '" AND timestamp<="' + $t1 + '"') '.local\l106\calib-all.json'
```

**C2. Quick look at the system log,** for gate checks:

```powershell
$f = 'resource.type="cloud_run_revision" AND log_id("run.googleapis.com/varlog/system") AND timestamp>="' + $t0 + '" AND timestamp<="' + $t1 + '"'
gcloud logging read ($f -replace '"','\"') --project $P --order asc --limit 1000 '--format=value(timestamp,resource.labels.service_name,resource.labels.revision_name,labels.instanceId,textPayload)'
```

**C3. Idle check:** the newest request per service.

```powershell
foreach ($s in $S) {
  $f = 'resource.type="cloud_run_revision" AND resource.labels.service_name="' + $s + '" AND log_id("run.googleapis.com/requests")'
  gcloud logging read ($f -replace '"','\"') --project $P --limit 1 --freshness 30d '--format=value(timestamp,resource.labels.service_name,httpRequest.status)'
}
```

**C4. Deployed configuration,** before the deploy (`pre`) and after the readback (`post`):

```powershell
foreach ($s in $S) {
  gcloud run services describe $s --region $R --project $P --format export |
    Out-File -Encoding utf8 ".local\l106\svc-$s-pre.yaml"
}
```

**C5. One revision's conditions and image digests:**

```powershell
gcloud run revisions describe $rev --region $R --project $P --format yaml |
  Out-File -Encoding utf8 ".local\l106\rev-$rev.yaml"
```

Notes:
- `Out-File -Encoding utf8` writes a byte-order mark in 5.1. Read the files as `utf-8-sig`.
- Save to `.local\`; never print a whole file. Report extracted fields only.
- Don't run `gcloud auth print-access-token`. See the two reads marked "repo method" below.

### 2b. Where each field was verified

| Field or string | Verified |
|---|---|
| `resource.type="cloud_run_revision"`, `resource.labels.service_name` | Google docs: `cloud.google.com/run/docs/logging` (its `gcloud logging read` example) |
| System log `run.googleapis.com/varlog/system`; `Starting new instance. Reason: REASON - DESCRIPTION` | Same page |
| `labels.instanceId` on request and system entries | `cloud.google.com/run/docs/troubleshooting/overview` (request logs); system entries seen in a community post only |
| `STARTUP HTTP probe failed N times consecutively for container "<name>" on port <p> path "<path>". The instance was not started.` and `Connection failed with status ERROR_CONNECTION_FAILED.` | This project's L-106 record, verbatim from 10-30 |
| `STARTUP HTTP probe succeeded after N attempt(s) for container "<name>"` | Community post, plus L-106's "pass, N attempts" rows. Not in Google's docs |
| `The request failed because the instance failed the readiness check.` (requests log) | L-106 record |
| `run.googleapis.com/execution-environment` annotation; unset means Cloud Run selects | `cloud.google.com/run/docs/configuring/execution-environments` |
| App fields `trace_id`, `msg`, `outcome`, `route`, `verdict`, `cost_usd`, `duration_ms` | This project's deploy-window log, 2026-10-14 |
| `resource.labels.revision_name`, `resource.labels.location` | **Unverified today.** L-106's 10-30 table has a revision per start, so the label worked then |
| `log_id()`, `--order asc`, `--freshness` ignored when the filter has a timestamp | **Unverified today** (from memory of the gcloud and Logging references) |
| `run.googleapis.com/startup-cpu-boost`, `run.googleapis.com/cpu-throttling` annotation names | **Unverified today.** Take the names from `deploy/cloudrun/*.yaml` and ADR-120 |
| The `\"` quoting helper on this machine | **Unverified.** The calibration below is its test |
| `run.googleapis.com/container/startup_latencies` | L-106 record (read on 10-30). **Repo method:** reuse the 10-30 read exactly, or skip it and say so |
| v2 `template.executionEnvironment` | **Repo method:** only if `deploy/deploy_service.py` has a read mode. Otherwise the C4 annotation is the record |

### 2c. Calibration (before G0)

Run C1 on the 10-30 window above and build the per-start extraction. It must reproduce L-106's tally from 18:59:13 to 19:45: **4 failed `ops-reporting` starts, 2 failed `ops-qa` starts, 5 passed starts of the other services.** If it doesn't, stop. The default log retention is 30 days, so this works only until about 11-29.

### 2d. Record per start (`starts.json`, one row per instance)

- round; service; revision; `instanceId`; kind (rollout or autoscale, from the Reason text);
- instance start time (the `Starting new instance` line);
- per container: first stdout or stderr line, and seconds after the start;
- per container: the probe line verbatim, its attempt count and time;
- seconds from start to probe success, and a flag if **over 60 s** (more than 20 attempts): a start the old window would have failed;
- the request that asked for the start (requests log, within 1 s before it): status, latency, message;
- which question and trace it belongs to;
- verdict: pass, fail or indeterminate. **Indeterminate never counts as a pass.**

### 2e. Extra record for every failed, indeterminate or over-60 s start

- every entry in all four streams from 10 s before the start to 130 s after it, verbatim, with a count per stream;
- C5 for the revision, read within 5 min: `status.conditions` and each container's image digest;
- the orchestrator's lines for the trace: the `dependency failed` line, and whether a breaker opened;
- for a retry: which `instanceId` served it, and whether a second `Starting new instance` line appeared;
- the owner's read of the Google Cloud Service Health page for Cloud Run in `us-central1`, with the time read;
- the `startup_latencies` point, if the 10-30 method is available.

### 2f. Record per question and once per session

- **Per question:** round, Q, retry or not, trace, route, outcome, `qa_status`, gateway `duration_ms`, the browser timer the owner types, model calls, `cost_usd`.
- **Once:** C4 `pre` and `post` for all six. The diff must show only ADR-120's settings and the image tags.
- **Execution environment:** record the annotation value, or "absent". If absent, write "generation in use: not observable from outside". Don't infer it.

## 3. Interpretation table (fixed now)

"Control fails" means at least one autoscale start of `ops-reporting` or `ops-qa` in R0 fails or is indeterminate. "Post-deploy passes" means the pass rule in §4 holds.

| Control (R0) | Post-deploy (R1 to R4) | L-106 status recorded | Next step |
|---|---|---|---|
| Fails | Passes | **Mitigated; cause unknown.** Never "fixed" | The Window B grader note. Its wording follows P2 and the over-60 s count. No gen1 experiment |
| Fails | Fails | **Open; ADR-120 insufficient.** Record whether the signature is 10-30's (no log line in the whole window) or a new one (a container logged, the probe still failed) | The gen1 experiment on one service, under its own ADR, in its own session |
| Passes | Passes | **Open; not reproduced on either configuration.** ADR-120 is deployed and untested against the failure. Never "fixed", never "mitigated" | No further experiment. The next observation is the run-through the day before the demonstration |
| Passes | Fails | **Open; failure seen on the ADR-120 configuration (k of n).** Not evidence that ADR-120 made it worse: on 10-30 the old configuration flipped mid-session | As for "fails, fails" |
| Either | Coverage not met | **Open; incomplete,** with the reason | Owner decides whether to rerun |

## 4. Pass rule (R1 to R4 only; R0 never enters it)

- **P1, starts.** Every autoscale start of every service passes its startup probe. Coverage: at least 3 autoscale starts each of `ops-reporting` and `ops-qa`, with at least 1 each in R4.
- **P2, retry.** Every degraded first answer has a retry that returns `answered` and `verified`. If no first answer degraded, P2 is **"not exercised"**: it doesn't fail the session, and the retry stays unverified.
- **Verdict:**
  - PASS if P1 holds with coverage met, and P2 holds or is not exercised;
  - FAIL if any autoscale start fails or is indeterminate, or any retry fails;
  - INCOMPLETE otherwise.
- **Reported beside the verdict, never a condition:**
  - first answers that came back `answered` and `verified`, k of n;
  - starts over 60 s, k of n;
  - with 0 failures in n starts of the affected pair, the one-sided 95% upper bound `1 − 0.05^(1/n)`: 31% at n = 8, 39% at n = 6.
- **No p-value is reported.** Starts in one session aren't independent: 10-30 went from 5 of 5 passing to 6 of 6 failing on one configuration.
- All rounds run after a failure, within the caps. Each start record is evidence.

## 5. Caps, gates, stop rule

| Cap | Per round | Total (R0 to R4) |
|---|---|---|
| Owner questions through the gateway | 6 (3, plus at most 3 retries) | 30 |
| Model calls (the per-call metered log lines) | 30 | 150 |
| List-price model cost (`cost_usd`) | $0.06 | $0.30 |
| Session time, from the `ops-db` start | n/a | 4 hours |

- The pipeline's own verify question is outside these: at most 1.
- The gateway's own limits also hold: 30 an hour per invite, 50 a day in total.
- A cap is checked before each round. A round that could cross one isn't started.

**Gates.** At each one, print the state, the cap totals and the exact command for the owner, then wait for `go`.

| Gate | Before |
|---|---|
| G0 | anything live: preflight, the calibration result, the pre-registration commit SHA |
| G1 | the owner starts `ops-db` and makes a new owner invite (`owner-laptop-3` has expired) |
| G-R0 | the control round: print the six idle timestamps |
| G2 | the deploy: enable, run, **disable at once**, then the readback against C4 |
| G-R1 to G-R4 | each round: the six idle timestamps; for R4, minutes since the rollout |
| G-CLOSE | the owner stops `ops-db`; read the end state |
| G-REC | the owner picks the status line from §3 |

**Stop and go to G-CLOSE if:**
- the calibration doesn't reproduce 10-30;
- a cap is reached;
- `ops-db` isn't `RUNNABLE` 20 min after the start command;
- the build fails;
- the readback doesn't match the declared configuration;
- any secret, token or invite text appears in output;
- the owner says stop.

## 6. What this session can't distinguish (copy into `summary.md`)

1. **Which ADR-120 change mattered.** The boost and the longer window ship together. A start that passes after more than 20 attempts points at the window; one that passes in under 20 points at neither.
2. **ADR-120 from a fresh rollout.** New settings always arrive with new revisions. R4 runs past the point where 10-30 failed, but it can't separate the two.
3. **ADR-120 from platform state on the day.** 10-30 flipped with no change on our side. A clean session bounds the failure chance; it doesn't remove it.
4. **Where the time before the first log line goes.** The platform logs nothing between "Starting new instance" and the probe result.
5. **The execution environment in use,** while the setting is unset.
6. **The retry, unless a first answer degrades.** If a retry does run, a start still in progress under the 120 s window may serve it, which is a different path from a second start.
7. **The control is one round:** two starts of the affected pair.
8. **The zone or host of an instance.** Cloud Run doesn't expose it.
9. **Time before the gateway receives a request.** The 120 s ceiling doesn't cover it. Record the browser timer beside the gateway's `duration_ms`.
