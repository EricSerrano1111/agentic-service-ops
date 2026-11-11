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
| Paid Gemini balance | **$6.18** (owner-read from AI Studio, 2026-11-10 at 3:06 pm CDT; $5 or more required) | the owner's reading; not verified by the assistant |

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

`evals/l106/extract_starts.py`, committed with the pre-registration (owner's decision 2026-11-10), **sha256 `ee282ac62ce0478bb308242b537065b3d140edbffe3b52727e6c6a476404540f`**. Every round runs this committed file, not a copy.

- **Lint-only change after the first recording.** This section first recorded sha256 `2cf8043b67f1261b97cb59c9c229ffa1209ae7eaac2714bd9915cdfe3c9c456e` (the file as calibrated). Copied into `evals/`, that file failed CI's `ruff check` (8 × E501, 1 × UP017) and `ruff format --check`. `ruff check --fix` and `ruff format` were applied; no logic was edited. Evidence that behaviour is unchanged: the extraction rows from the 10-30 window (18 starts) and the 17:50 to 18:30 window (6 starts) are identical, key by key, between the two versions; the calibration still prints `REPRODUCES 10-30: True` (4 / 2 / 5). Nothing had been measured live at the time of the change.
- **Audit (owner's two checks, 2026-11-10).** It opens a file in three places, each on a path given on the command line: the log export (`load`, `open(path)`), and, in `round` mode only, the `STARTS.json` it merges into and writes (`open(out)`, twice). It reads nothing else, and nothing from `.local\` by name (the string `.local/` appears only in the usage line of the docstring). It imports `json`, `re`, `sys` and `datetime` only: no `subprocess`, network, `os` or environment access. A search for `token`, `secret`, `password`, `api key`, `bearer`, `invite`, `credential` finds only the variable `token`, the Reason token parsed from a start line (`kind_of`, `extract`). It holds no project secret or credential.

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

The `!` prompt runs Git Bash, not PowerShell (`docs/deploy-window-log.md:547`: a backslash path failed on 10-30). Each gate therefore prints two forms: the runbook line verbatim with its file and line, and the literal one-liner the owner types (values expanded, forward slashes, no backticks, no `$env:`). **Owner's rulings (2026-11-10):** if a literal argument starts with `/`, the line is prefixed with `MSYS_NO_PATHCONV=1` so Git Bash does not rewrite it; and any case where the two forms could behave differently is flagged at the gate. The assistant runs only the reads.

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

## 8. Owner rulings at G0 (owner-decided 2026-11-10; assistant-drafted wording)

1. **Idle precondition (interprets README §1; changes nothing in it).** A request the session did not make (any request before the owner's first question in a round that is not from the owner or from the pipeline's verify step) is **recorded in the ledger, and does not reset the 20-minute idle clock.** The clock starts at the last request that the owner or the pipeline made. This covers the unsolicited gateway request seen on 2026-11-10 (§1). **Any service, the gateway included, counts in a round only if an `AUTOSCALING` start line for it falls inside the round** (§1, "cold is proved, not assumed"). A start line outside every round (for example, an instance started by an unsolicited request between rounds) is recorded in the ledger, is not a start of any round, and enters no pass rule count. It is disclosed in `summary.md` with this ruling.
   - *Round window used for "inside the round".* A round opens at the owner's `go` at the round's gate and closes when the owner reports the last answer of the round. The assistant records both times in the ledger.
2. **The invite.** The owner runs `scripts/invites.py create` in their own terminal, outside this session, with an expiry no later than 2026-11-11 23:59 CDT, and gives the assistant only the label and the id from `list`. **The assistant runs neither `create` nor `list`, and opens nothing in `.local\` that might hold invite output.** No invite text appears in the session.
3. **`_RUN_VERIFY` stays on** (the default, `deploy/cloudbuild.yaml:41`), as on 2026-10-30. Its one question is the allowance outside the caps (README §5). **If the build fails at the verify step, that is README §5's "the build fails" stop:** record which step failed and its logs as evidence, then G-CLOSE. **R1's idle clock starts at the verify step's last request** (read from the requests log; the pipeline's requests count for the clock, ruling 1).
4. **The extractor** is committed in this PR (§4).
5. **Pre-existing `.local\l106\` files** (`env`, `logs`, `build.log`, `build.sh`, `smoke.csv`, `summary.before`) are left untouched. Before every commit: `git status` shows nothing from `.local\`, and `git check-ignore -v .local/l106/env` shows `.gitignore:70:.local/` (checked 2026-11-10 before this PR's second commit).

## 9. Attempt 2 (2026-11-11)

*2026-11-11. Assistant-drafted, except where marked "owner-decided"; the owner is present. This section is appended; §1 to §8 are unchanged. Attempt 2 runs under the same frozen pre-registration (`README.md`, sha256 `5de4856b3fb78c1573397ffbd9f398b71e33a88327a88c275ab6e7ebbe4dfde3`) and re-runs everything from R0, because platform state changes from day to day (README §6, item 3). **Attempt 1's R0 (2026-11-10) does not count here.** Times are UTC unless marked CST (the owner's machine is UTC-6). Temporary files for this attempt are in `.local\l106b\`, not `.local\l106\`. All commands in this section were read-only; no model call, no request to a `run.app` URL, no secret, token, invite link or invite id printed.*

### 9.1 State check (2026-11-11)

| Item | Result | Verified by |
|---|---|---|
| `main` | Clean, equals `origin/main`: `5e9131561c46f8d14ed428c305a9944cee609ebc` (the PR #100 merge). No commit after `5e91315` | `git status --short`, `git fetch`, `git rev-parse HEAD origin/main`, `git log 5e91315..HEAD` |
| Serving revisions, each 100% and `latestRevision: true` | gateway `00004-zqw`, orchestrator `00011-mml`, reporting `00009-bjp`, sentiment `00005-nzq`, forecast `00005-k5r`, QA `00006-dj4` (`latestReady` and `latestCreated` equal the serving revision for all six) | `gcloud run services describe <service> --format json`, `status.traffic` |
| `ops-db` | `STOPPED  NEVER` | `gcloud sql instances describe ops-db` |
| Trigger `deploy-reporting-slice` | `disabled: True`. Equal to `deploy/trigger_full.yaml` in `name`, `id`, `description`, `filename`, `serviceAccount`, `repositoryEventConfig`, `includedFiles`, `ignoredFiles` and `substitutions`. `disabled` is also equal (the repo file ships `disabled: true`). The live trigger has two further keys, `createTime` and `resourceName`, which the file does not | `gcloud builds triggers describe ... --format json`, compared with the file in Python |
| Latest build | `51b9dc00-b524-4648-be92-70a6e7d841d7`, `FAILURE`, `finishTime` 2026-11-10T22:01:22Z, commit `f2cddf68…` (the attempt 1 build) | `gcloud builds list --region us-central1` |
| gcloud | Account is the owner's; configuration `a2a-deploy` | `gcloud config get-value account`, `gcloud config configurations list` |
| Paid Gemini balance | **$6.18** (owner-read on 2026-11-11 at 11:30 CST, 17:30Z; $5 or more required) | The owner's reading, not verified by the assistant |

### 9.2 ADR-121 preflight (first live use of `RUNBOOK_V.md`'s loop; owner-decided deviation)

The loop in `deploy/RUNBOOK_V.md:69-77` was run as written, three times on the owner's PC (Docker Desktop running; PowerShell 5.1):

| Run | Result |
|---|---|
| 1 | `gcr.io/cloud-builders/docker@sha256:fbc05705…` resolves; `gcr.io/google.com/cloudsdktool/cloud-sdk@sha256:b38f2881…` resolves; `python:3.12-slim@sha256:5e2bdb1b…`: `docker manifest inspect` ended with `wsarecv: An existing connection was forcibly closed by the remote host` on an IPv6 fetch from `production.cloudfront.docker.com`. Loop printed `DOES NOT RESOLVE` and `STOP` |
| 2 | The assistant's own immediate rerun, before the owner ruled: the same two resolve; the same reset on `python:3.12-slim`, on a different blob |
| 3 | After about 5 minutes (the owner's ruling below): the same two resolve; the same reset, on the same blob as run 1 |

No run returned "manifest unknown", "not found" or a 404. The two `gcr.io` digests resolved in all three runs.

**Owner ruling (owner-decided 2026-11-11), quoted as given:**

> A connection reset means the check couldn't run, not that the digest is gone. The stop is for a digest that doesn't resolve: "manifest unknown", "not found" or a 404. Record the two resets in the ledger as "check not completed (network)". Wait about 5 minutes, then rerun the exact runbook loop once. If python:3.12-slim fails again with a reset, I'll run the same read from Google Cloud Shell, which is off my home network: `docker manifest inspect python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b`. I'll tell you only the exit status and the first line. Record it as a deviation: same command, different machine, because the runbook loop on my PC could not complete. A "manifest unknown", "not found" or 404 from either place is a hard stop, as the runbook says. If Cloud Shell can't complete it either, stop the session. No §9 and no PR. Put this ruling in §9 when you write it.

**Cloud Shell read.** The command form the assistant gave the owner was `docker manifest inspect python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b > /dev/null; echo "exit=$?"`. The owner reported `exit=0` with no error output. **That result is owner-reported; the assistant did not observe it.** It is recorded as a deviation: the same read, on another machine, because the loop on the owner's PC could not complete. The loop itself did not pass on the PC in any of the three runs.

### 9.3 The sha checks and the calibration

- **README:** `git show HEAD:evals/l106/README.md | sha256sum` = `5de4856b3fb78c1573397ffbd9f398b71e33a88327a88c275ab6e7ebbe4dfde3`. Equal to the pre-registered value.
- **Extractor:** `git show HEAD:evals/l106/extract_starts.py | sha256sum` = `ee282ac62ce0478bb308242b537065b3d140edbffe3b52727e6c6a476404540f`. Equal. The working copy is CRLF and hashes differently (§4, attempt 1 deviation 2); the blob is the identity, and `git status` was clean when it was run.
- **Calibration (README §2c):** C1 on 2026-10-30T18:30:00Z to 20:00:00Z, written to `.local\l106b\calib-all.json` (463 entries), run through the committed `evals/l106/extract_starts.py calib`. 11 starts in the window. **4 failed `ops-reporting`, 2 failed `ops-qa`, 5 passed others, 0 other; `REPRODUCES 10-30: True`, exit 0.** The same starts as §3 (reporting 18:59:13, 19:12:13, 19:14:36 on `00009-bjp` and 19:25:29 on `00008-tt8`; QA 19:37:03 and 19:42:12). The 10-30 logs expire around 2026-11-29.

### 9.4 Owner rulings of §8, carried over unchanged

- **Ruling 1** (idle precondition and round window): applies as written, including the round window (a round opens at the owner's `go` and closes when the owner reports the last answer; both times go in the ledger) and the handling of requests and start lines the session did not make.
- **Ruling 3** (`_RUN_VERIFY` stays on): applies as written. A build failure at the verify step is README §5's "the build fails" stop. R1's idle clock starts at the verify step's last request.
- **Ruling 4** (the extractor): the committed file above, run unchanged.
- **Ruling 5** (older `.local\l106\` files): left untouched and not opened. Before every commit, `git status` shows nothing from `.local\`; `git check-ignore -v .local/l106b/calib-all.json` shows `.gitignore:70:.local/` (checked 2026-11-11).

### 9.5 Ruling 2, restated (owner-decided)

The owner made the invite `owner-laptop-5` in the owner's own terminal and revoked `owner-laptop-4` before this session started, on 2026-11-11. `owner-laptop-5` is the only active invite (owner-stated). Its expiry, as the owner read it: **2026-11-13T17:10:59Z**. Its creation time is not known to the assistant. All of this is owner-stated and unverified by the assistant.

**This replaces the limit in §8 ruling 2** ("an expiry no later than 2026-11-11 23:59 CDT") **for attempt 2.** The real expiry is later than that limit, and it covers today's session. The assistant runs neither `scripts/invites.py create` nor `list`, records labels and the expiry only, and writes no invite id or link anywhere. There is no invite step at G1.

### 9.6 §5, restated: the expected readback

The expected readback of §5 is **unchanged**, with one change: **the image tag moves from `9599bae33625823b2081f68e6da8c4bbc367e7ab` to the commit this session deploys**, the merge commit of the PR that carries this section (recorded at G0 and in the ledger; `git diff --name-only <5e91315>..<merge>` must list only `evals/l106/phase1-checks.md`). The C4 files go in `.local\l106b\`, with distinct variable names (the `$S`/`$s` collision of attempt 1, deviation 4, is not repeated).

Checked 2026-11-11 that §5's table still describes what the next build will deploy (read-only `git diff`):
- `git diff 9599bae 5e91315 -- deploy/cloudrun` is, line for line (index lines excluded), the same diff as `git diff 9847772 a5f9107 -- deploy/cloudrun`, the one §5 was built from. `git diff a5f9107 5e91315 -- deploy/cloudrun` is empty.
- `git diff 9599bae 5e91315` over `deploy/cloudrun services packages web ml models pyproject.toml uv.lock` touches the six `deploy/cloudrun` files and four files under `services/mcp_feedback` and `services/mcp_volume` (`server.py` and its test in each): ADR-120 item 3, liveness without the database. Nothing else.
- `deploy/cloudbuild.yaml` changed between `9599bae` and `5e91315` in 17 lines, all `name:` lines (ADR-121); no substitution, step order, entrypoint or argument changed.

The boost-key rule of §5 and §2 stands: if the readback shows no boost key on any service, that is a "readback doesn't match" stop, and no repo method can say whether the boost is "set, not shown in v1" or "not set".

### 9.7 Disclosures, fixed before any result

1. **The rollout changes more than ADR-120's settings.** The application images are rebuilt by this deploy from `FROM` lines that are not pinned by digest (`python:3.12-slim` and `node:24-slim`; ADR-121 decision 3, "22 `FROM` lines, none pinned"), on a different date from 10-30, so their base layers may differ from the ones the serving revisions run. The ADR-120 liveness handler change in `mcp_feedback` and `mcp_volume` (item 3) also ships. Neither the base-image drift nor the handler change can be separated from the boost and the window (README §6, item 2).
2. **This is the first live run of ADR-121's pinned step images.** Whether Cloud Build starts a step from a digest-pinned `name:` as it does from a tag is expected, not yet observed (ADR-121, Consequences). A failure at any deploy step is a pipeline result, recorded under L-107 and R-03, and README §5's "the build fails" stop applies.
3. **Attempt 1's R0 is not counted in attempt 2.** R0 here is a new control round, on today's platform state, before the deploy.
4. **The preflight deviation** (9.2): the loop did not pass on the owner's PC; the Cloud Shell read is owner-reported.
5. **Path change.** README §2a and §2e hardcode `.local\l106\`; attempt 2 writes to `.local\l106b\` (a hard rule of this session). No result changes.
6. **Continuity of the deploy target.** `gcloud builds triggers run --branch main` builds whatever is on `main` when it runs. At G2, immediately before the owner runs it, the assistant reads `origin/main` and confirms it equals this section's merge commit. If another merge has landed, the deploy target has moved, the readback above no longer holds, and the session stops to ask.
7. **Caps at the end of Phase 1:** owner questions 0 of 30; model calls 0 of 150; `cost_usd` $0 of $0.30; the pipeline's verify question 0 of 1; session time not started (it counts from the `ops-db` start).
