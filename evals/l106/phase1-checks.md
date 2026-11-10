# L-106 verification: Phase 1 checks (read-only, 2026-11-10)

*2026-11-10. Assistant-drafted; the owner is present. Companion to `README.md` (the frozen pre-registration), which is not edited. Every row names where it was verified. All commands here were read-only; no model call, no request to a `run.app` URL, no secret printed.*

## 1. State check (2026-11-10)

| Item | Result | Verified by |
|---|---|---|
| PR #97 | `MERGED` 2026-11-07T18:36:39Z, merge commit `a5f91073cc411cd72134b5efdd93206cb5418907` | `gh pr view 97 --json state,mergedAt,mergeCommit` |
| `origin/main` HEAD | `a5f91073cc411cd72134b5efdd93206cb5418907` (equals the PR #97 merge; local `main` equal, clean) | `git fetch`, `git rev-parse origin/main HEAD` |
| Serving revisions, all `latestRevision: true`, 100% | gateway `00004-zqw`, orchestrator `00011-mml`, reporting `00009-bjp`, sentiment `00005-nzq`, forecast `00005-k5r`, QA `00006-dj4` | `gcloud run services describe` for each (`status.traffic`) |
| `ops-db` | `STOPPED  NEVER` | `gcloud sql instances describe ops-db` |
| Trigger `deploy-reporting-slice` | `disabled: True`; `includedFiles`, `ignoredFiles`, `substitutions`, `filename` and `serviceAccount` equal `deploy/trigger_full.yaml`; push filter `^main$` | `gcloud builds triggers describe ... --format json`, compared in Python |
| Log retention | `_Default` bucket 30 days (the calibration works until about 2026-11-29) | `gcloud logging buckets describe _Default` |
| gcloud | Google Cloud SDK 531.0.0; account is the owner's; configuration `a2a-deploy` | `gcloud --version`, `gcloud config get-value account` |
| Paid Gemini balance | **Not yet given** (the owner types it at G0; $5 or more required) | n/a |

**Idle state today (C3, run once).** Newest request per service: gateway `2026-11-10T05:15:55Z` (HTTP 404: an unsolicited request to the public gateway, not ours); orchestrator `2026-10-30T19:41:30Z`; reporting `2026-10-30T19:25:28Z`; sentiment `2026-10-30T19:37:01Z`; forecast `2026-10-30T19:42:11Z`; QA `2026-10-30T19:42:12Z`. **Consequence for the idle rule:** the gateway has `allUsers` invoker, so unsolicited internet requests can start or keep a gateway instance outside our control. Each gate's idle check (C3) is read at the gate, and a gateway request we did not make is recorded, not hidden.

## 2. Section 2b: the "Unverified today" rows

| Row | Verdict | Source |
|---|---|---|
| `resource.labels.revision_name`, `resource.labels.location` | **Verified** | C1 on the 10-30 window returned 463 entries; the resource label keys on every entry are `configuration_name`, `location`, `project_id`, `revision_name`, `service_name`; the filter used `resource.labels.location="us-central1"` |
| `log_id()` | **Verified** | C2 (`log_id("run.googleapis.com/varlog/system")`, same window) returned 83 entries; C1 holds 83 entries whose `logName` ends `varlog%2Fsystem`. Equal counts |
| `--order asc` | **Verified** | `gcloud logging read --help` (SDK 531.0.0): `--order=ORDER; default="desc"`, values `desc`, `asc`; C1 ran with `--order asc` |
| `--freshness` ignored when the filter has a timestamp | **Verified** | same help text: "Works only with DESC ordering and filters without a timestamp." C1 and C2 (timestamp filters, `asc`) returned entries from 2026-10-30, 11 days old, with the default `--freshness` of `1d` in force. C3 has no timestamp and uses the default `desc` order with `--freshness 30d`, so freshness applies there |
| `run.googleapis.com/cpu-throttling` annotation | **Verified** | `.local/l106/svc-ops-reporting-pre.yaml` line 25: `run.googleapis.com/cpu-throttling: 'false'`; the annotation key is present on all six `pre` exports |
| `run.googleapis.com/startup-cpu-boost` annotation | **Not verifiable before the deploy.** The repo does not use an annotation name: `deploy/cloudrun/*.yaml` set the v2 field `resources.startupCpuBoost: true` (`reporting.yaml:73`, `:117`; `forecast.yaml:63`, `:103`; `gateway.yaml:56`; `orchestrator.yaml:70`; `qa.yaml:76`; `sentiment.yaml:66`, `:108`: nine containers), and ADR-120 item 1 names the same field. None gives the v1 `--format export` key. The six `pre` exports carry no boost key (consistent with "unset") | The readback will show what key the export uses. **If the readback shows no boost key anywhere, that is a "readback doesn't match" stop, and only a v2 read (no repo method, so none today) could tell "boost set, not shown in v1" from "not set".** I will not supply the key name from memory |
| The `\"` quoting helper | **Verified** | Read-Logs as written in 2a accepted a filter with inner quotes (`resource.type="cloud_run_revision" AND ... timestamp>="..."`) and returned 463 entries; C2 with `log_id("...")` returned 83 |
| `startup_latencies` | **Skipped.** No repo method | The 10-30 read was ad hoc Monitoring API GETs by the assistant (`docs/deploy-window-log.md:544`; `evals/results/deploy_window/2026-10-30/ledger.jsonl` line 48). The repo has no script for it: a search of `deploy/`, `scripts/`, `evals/` and `services/` for `startup_latencies` finds only that ledger line and docs. `scripts/alert_degraded.py:44-45` reads a log-based metric (`orchestrator_degraded_answers`), not this one, and calls `gcloud auth print-access-token` itself (`:240`). Writing new token code is out of scope, so no `startup_latencies` point is recorded this session |
| v2 `template.executionEnvironment` | **Skipped.** No read mode | `deploy/deploy_service.py:56-59`: `main` accepts one argument, a rendered JSON file, and creates or updates a service; there is no read. The record is the C4 annotation. **`run.googleapis.com/execution-environment` is absent from all six `pre` exports** (annotation keys listed per service; none contains it). Per 2f: "generation in use: not observable from outside" |

**Corrections to strings in 2b/2a (the README is not edited; these are the observed forms).**
- The probe-success line reads `STARTUP HTTP probe succeeded after N attempts for container "<name>" on port <p> path "<path>".` ("attempts", not "attempt(s)"; the singular form was not observed: the 10-30 data has N of 2, 3, 4, 6, 7, 9, 12). The extractor accepts `attempt` and `attempts`. Found because the first calibration run, written to the README's string, read every passed start as indeterminate.
- The rollout reason token is `DEPLOYMENT_ROLLOUT` (6 of 6 starts, 2026-10-30 17:50 to 18:30; `.local/l106/calib-rollout.json`); the autoscale token is `AUTOSCALING` (18 of 18 in 18:30 to 20:00). System entries also carry `labels.scaling_reason`. The extractor maps `AUTOSCALING` to autoscale, a token containing `ROLLOUT`, `DEPLOY`, `REVISION` or `TRAFFIC` to rollout, and anything else to `other:<token>`, which is neither.
- The requests-log entry for a failed start is timestamped at receipt, 0.04 to 0.1 s before "Starting new instance", carries the same `instanceId`, severity `ERROR`, status 503, and its message is in `textPayload`.
- Container logs carry `labels.container_name` and `labels.instanceId`; stdout lines are JSON (`jsonPayload.msg`).
- `instanceId` is a long hex string, and entries from different services share a prefix, so the extractor uses the full value.

## 3. Section 2c: the calibration

C1 on 2026-10-30T18:30:00Z to 20:00:00Z (463 entries: 457 in the four streams, 6 audit entries, which are ignored), parsed by `.local/l106/extract_starts.py calib`. **It reproduces L-106's tally from 18:59:13 to 19:45:** 4 failed `ops-reporting` starts (18:59:13, 19:12:13, 19:14:36 on `00009-bjp`; 19:25:29 on `00008-tt8`), 2 failed `ops-qa` starts (19:37:03, 19:42:12), 5 passed starts of the other services (orchestrator 19:18:48, 7 attempts; gateway 19:35:21, 12 attempts, and 19:43:47, 3; sentiment 19:36:40; forecast 19:41:31). 11 starts in the window, 0 left over.

Cross-checks against L-106's second-pass table: attempt counts equal for all 11 (gateway 12 and 3, orchestrator 7, sentiment 3 and 4, forecast 4 and 9, 20 of 20 on the six failures); first-log-line times equal to the decimal on the three starts checked (sentiment `agent-sentiment` 17.6 s, forecast `agent-forecast` 36.4 s, `mcp-volume` 10.6 s); failure probe lines 59.4 s after the start; for the rollout window, six `DEPLOYMENT_ROLLOUT` starts, all pass, 8.3 to 29.3 s to probe success (L-106: 8.1 to 29.1 s by `startup_latencies`; 8.3 to 29.3 s is from the start line to the last probe line).

Known limit of the calibration: it checks the pass and fail logic and the grouping. It does not check the kind classification for anything but `AUTOSCALING` and `DEPLOYMENT_ROLLOUT`, and it does not test a start that the window cuts off (a start whose probe lines fall after the read's end is `indeterminate`, with `window_complete: false` in its evidence).

## 4. The extractor, fixed before any result

`.local/l106/extract_starts.py`, sha256 `2cf8043b67f1261b97cb59c9c229ffa1209ae7eaac2714bd9915cdfe3c9c456e`. It is not committed with this PR (it lives in `.local\`, per the temporary-file rule); the owner decides at the records PR whether it joins `evals/results/l106/<run-date>/`.

- **Per start (2d):** one row per `(service, instanceId)` that has a `Starting new instance` line inside the read. Per container: first stdout or stderr line and its seconds after the start; the probe line verbatim, attempts, seconds after the start. `secs_to_probe_success` is the latest container's success, set only when the start passed.
- **Expected containers** (from the 10-30 table and the YAML container names): gateway `gateway`; orchestrator `orchestrator`; reporting `agent-reporting`, `mcp-incidents`; sentiment `agent-sentiment`, `mcp-feedback`; forecast `agent-forecast`, `mcp-volume`; QA `agent-qa`.
- **Verdict:** `fail` if any container has a probe-failed line; `pass` if every expected container has a probe-succeeded line; otherwise `indeterminate`. A failed reporting start shows only `mcp-incidents` failing (the agent waits for it); that is `fail`.
- **Over 60 s:** the flag is set on a passed start when the seconds to the last probe success exceed 60 **or** any container needed more than 20 attempts. Both numbers are kept. (README 2d writes "over 60 s (more than 20 attempts)"; with a 2 s initial delay and a 3 s period, attempt 20 is at about 59 s from the container's start, so the two tests agree to within the delay before the container is started.)
- **Request match (2d):** the requests-log entry on the same service and the same `instanceId`, timestamped 0 to 1 s before the start line. Calibration: 12 of 18 starts matched; the six without a match are not all explained, and two of them are autoscale starts in the 18:59 to 19:45 window (orchestrator 19:18:48, gateway 19:43:47) that have **no requests-log entry on that service within 30 s either side**. The `request` field is then `null`; verdicts do not use it. It is an open point about the request logs, not a defect in the verdicts.
- **Evidence (2e):** every non-pass, and every over-60 s start, gets the verbatim entries of the four streams for that service from 10 s before to 130 s after the start, with a count per stream, and `window_complete` (false when the read ended before start + 130 s).
- **Round reads:** each round's read ends at least 2 min after the round's last question and at least 130 s after the last start in it; a read with `window_complete: false` is pulled again before its rows are used.
- Question and trace fields are filled by hand from the orchestrator and gateway log lines after the round, not by the script.

## 5. Expected readback diff (C4 `pre` against `post`), written before the deploy

Source: the six `pre` exports taken 2026-11-10 (`.local/l106/svc-<service>-pre.yaml`), the nine rendered containers, and `git diff 9847772 a5f9107 -- deploy/cloudrun` (9 added `startupCpuBoost: true` lines; 9 `failureThreshold` lines changed, of which 8 go 20 to 40 and one, the sentiment agent, was already 40 and is rewritten as 40).

| Service / container | `startupProbe.failureThreshold` pre | expected post | Boost key |
|---|---|---|---|
| ops-gateway / gateway | 20 | 40 | appears |
| ops-orchestrator / orchestrator | 20 | 40 | appears |
| ops-reporting / agent-reporting | 20 | 40 | appears |
| ops-reporting / mcp-incidents | 20 | 40 | appears |
| ops-sentiment / agent-sentiment | **40** | 40 (no change) | appears |
| ops-sentiment / mcp-feedback | 20 | 40 | appears |
| ops-forecast / agent-forecast | 20 | 40 | appears |
| ops-forecast / mcp-volume | 20 | 40 | appears |
| ops-qa / agent-qa | 20 | 40 | appears |

- **Image tag:** every container, `9599bae33625823b2081f68e6da8c4bbc367e7ab` to the deployed commit (the merge commit of the docs PR; `git diff a5f9107..<merge>` must show only docs paths, checked after the merge).
- **Revision names:** each service gets a new revision.
- **Must not change:** `cpu-throttling: 'false'` on all six; `minScale` 0; `maxScale` 2 (gateway 1, orchestrator 3, per L-106); `containerConcurrency`; memory and CPU limits; `cloudsql-instances` and `container-dependencies` annotations; liveness probes (`failureThreshold` 3, `/healthz`); `LLM_MODE: paid`; env and secret names. `run.googleapis.com/execution-environment` must remain **absent**.
- **Server-managed noise, not a mismatch:** `client.knative.dev/nonce`, `run.googleapis.com/client-name`/`client-version` style labels if present, revision names, `creationTimestamp`, `generation`, `observedGeneration`, `latestCreatedRevisionName`, `latestReadyRevisionName`, status fields. Anything else that differs is a mismatch and a stop.
- **Boost key:** whichever key appears (see §2) must appear on all nine containers' services; if none appears, stop (§2).

## 6. Gate commands (proposal for the owner's approval)

The `!` prompt runs Git Bash, not PowerShell (`docs/deploy-window-log.md:547`: a backslash path failed on 10-30). Each gate therefore prints two forms: the runbook line verbatim with its file and line, and a one-line literal form for `!` (values expanded, forward slashes, no backticks, no `$env:`). The assistant runs only the reads.

| Gate | Runbook line (verbatim source) | Notes |
|---|---|---|
| G1 `ops-db` start | `deploy/RUNBOOK_GRADING.md:33` | the wait loop at `:34-38` is read-only and the assistant's; the owner runs the `patch` |
| G1 invite | `deploy/RUNBOOK_GRADING.md:55` form (`scripts/invites.py create`, `RUNBOOK_V.md:420`) | **The link prints once.** The owner runs it in their own terminal, not through `!`, and reports only the label and id from `list`. Through `!` the link would land in this conversation, which trips hard rule 4 |
| G2 enable | `deploy/RUNBOOK_V.md:400-405` | the temporary copy goes in `.local/l106/`, not `$env:TEMP` (rule 6); the assistant writes the copy and diffs it against `deploy/trigger_full.yaml` (only `disabled:` may differ); the owner runs the `import` |
| G2 run | `deploy/RUNBOOK_V.md:229-230` | with or without `--substitutions _RUN_VERIFY=false`: owner's decision at G0 (see `deploy/cloudbuild.yaml:41`, `:188-191`) |
| G2 disable | `deploy/RUNBOOK_V.md:216` form with the unmodified `deploy/trigger_full.yaml` (it carries `disabled: true`); the read-back is `:406` | given at once after the build ends, whatever its result |
| G-CLOSE stop | `deploy/RUNBOOK_GRADING.md:80` | read-back at `:81` |

`gcloud builds triggers import` replaces the whole trigger. The live trigger was compared with `deploy/trigger_full.yaml` on 2026-11-10 (§1: equal in all five fields), so an import of the repo file, or of its copy with `disabled: false`, changes only `disabled`.

## 7. Deviations from the prompt so far

- **Step order.** The calibration, the idle read (C3) and the C4 `pre` read ran before the README was committed (the extractor needed the calibration to be fixed first). All were read-only; nothing live had changed. **C4 `pre` will be taken again at G2, immediately before the deploy,** and that copy is the one compared with `post`.
- **`.local\l106\` already held files** from an earlier session (`env`, `logs`, `build.log`, `build.sh`, `smoke.csv`, `summary.before`). They were not opened or changed. The C4 `pre` read wrote only `svc-*-pre.yaml`.
