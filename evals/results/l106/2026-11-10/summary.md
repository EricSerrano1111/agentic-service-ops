# L-106 cold-start verification, 2026-11-10: summary

*2026-11-10 (owner present). Assistant-drafted, except the status line, which is owner-decided (G-REC, 2026-11-10).* The pre-registration is `evals/l106/README.md` (merged in PR #98, merge commit `f2cddf68ee8b23427d974f5701023318581cbdc8`; the extractor's committed blob has sha256 `ee282ac62ce0478bb308242b537065b3d140edbffe3b52727e6c6a476404540f`). Nothing in it was changed after a result was seen. Times are UTC unless marked CST (the owner's machine is UTC-6). Files beside this one: `starts.json`, `ledger.jsonl`, `fill_round.py`, `R0-qmap.json`. No invite link, token or invite id is in any of them.

## Verdict (README section 4)

**INCOMPLETE.** The ADR-120 deploy failed, so ADR-120 was never deployed and R1 to R4 did not run. Coverage for the pass rule is 0 of the required 3 autoscale starts each of `ops-reporting` and `ops-qa` (and 0 in R4). No autoscale start of R1 to R4 failed, because none happened; that is not a pass.

**Status line (owner-decided), README section 3, row "Either / coverage not met":**

> Open; incomplete. The ADR-120 deploy failed at its first deploy step, `deploy-qa` (the step image `cloud-sdk:slim` had no `python3` on its PATH), so ADR-120 was never deployed and R1 to R4 did not run. In the control (R0, the old configuration), 0 of 2 starts of `ops-reporting` and `ops-qa` failed (longest 23.6 s). L-106 is neither reproduced nor mitigated.

**The control (R0).** "Control fails" (section 3) means at least one autoscale start of `ops-reporting` or `ops-qa` failed or was indeterminate. It did not happen: the round had one autoscale start of each, both passed. The control is two starts of the affected pair (section 6, item 7). Reported beside it, not a condition (section 4): 0 failures in n = 2 starts has a one-sided 95% upper bound of 78% (`1 − 0.05^(1/2)`), which says almost nothing; on 10-30 the old configuration went from every autoscale start passing to 6 of 6 reporting and QA starts failing within one session.

- **P2 (retry):** not exercised. No first answer degraded in R0, and R1 to R4 did not run.
- **Starts over 60 s:** 0 of 7 (R0 only; the longest start to probe success was 23.6 s).
- **First answers `answered` and `verified`:** 3 of 3 (R0 only; R0 is outside the pass rule).

## What happened, in order

| Time (UTC) | Event |
|---|---|
| 21:20:48 | The owner started `ops-db` (operation `94ac93da…`; the instance read `RUNNABLE ALWAYS` at 21:30:24; the operation was `DONE` at 21:33:12) |
| 21:34:13 | R0 opened (the owner: "I will open browser now", treated as `go`) |
| about 21:42 | R0 closed (the owner reported 3:41 pm CST, 21:41); logs pulled 21:44:08 after the 2-minute wait |
| 21:54:55 | C4 `pre` retaken for all six services; identical to the copy from the morning |
| 21:56:40 | Trigger read back enabled (the owner ran the import) |
| 21:57:35 | The owner ran the trigger: build `51b9dc00-b524-4648-be92-70a6e7d841d7`, commit `f2cddf68…`, `_RUN_VERIFY` `true` |
| 22:01:22 | The build finished: **FAILURE** at step `deploy-qa` (see below). Stop rule: the build fails |
| 22:06:57 | The owner stopped `ops-db` (operation `2bfbf426…`, `DONE` 22:07:30) |
| 22:08:23 | End state read back (the trigger `disabled: True`, `ops-db` `STOPPED NEVER`) |

**The build failure.** Build `51b9dc00`: steps 0 to 9 (eight image builds, `push-images`, `render`) `SUCCESS`; step 10, `deploy-qa`, `FAILURE` at 22:01:11; the other five deploy steps and `verify` never ran (`QUEUED`). The message: `starting step container failed: ... exec: "python3": executable file not found in $PATH`, on the image `gcr.io/google.com/cloudsdktool/cloud-sdk:slim` (`deploy/cloudbuild.yaml:134-136`, `entrypoint: python3`). Build `6f8abad0` used the same step image name on 10-30 and its `deploy-qa` succeeded. Not read: the image digest of either build, and the images in Artifact Registry. No service changed: all six serve the 10-30 revisions at 100%, `latestRevision: true`, C4 `post` byte-identical to C4 `pre`. This is a separate defect (L-107), not a finding about L-106. The pipeline's one verify question did not run (0 of 1).

## R0, the starts (7 autoscale starts, 7 pass; kind from the Reason text; seconds after the start line)

| Start | Service | Revision | First log line (s) | Probe attempts | To probe success (s) | For |
|---|---|---|---|---|---|---|
| 21:34:23.291 | gateway | `00004-zqw` | 3.9 | 2 | 5.3 | the page load |
| 21:35:08.194 | gateway | `00004-zqw` | 4.1 | 2 | 5.3 | no request in the log within 1 s; before Q1 |
| 21:36:20.964 | orchestrator | `00011-mml` | 7.2 | 3 | 8.2 | Q1 |
| 21:36:31.390 | reporting | `00009-bjp` | 10.3 (`mcp-incidents`), 20.7 (`agent-reporting`) | 4 | 23.6 | Q1 |
| 21:36:56.926 | qa | `00006-dj4` | 13.2 | 5 | 14.6 | Q1 |
| 21:38:40.662 | sentiment | `00005-nzq` | 8.3 (`mcp-feedback`), 17.0 (`agent-sentiment`) | 3 and 4 | 20.1 | Q2 |
| 21:40:18.539 | forecast | `00005-k5r` | 9.5 (`mcp-volume`), 20.8 (`agent-forecast`) | 4 and 4 | 23.6 | Q3 |

Every service counted in R0 has an `AUTOSCALING` start line inside the round (README section 1). The first gateway instance shut down at 21:39:33; the second gateway start has no matching request, and no cause is named. A session-wide read (21:20 to 22:13) found no request and no start outside R0.

## R0, the questions (all `answered`, `verified`, no retry, `route_v6`, `gemini-3.5-flash-lite`)

| Q | Route | Trace | Gateway `duration_ms` | Browser | Orchestrator `duration_ms` | Model calls | `cost_usd` |
|---|---|---|---|---|---|---|---|
| Q1 | reporting | `dcc87f78dd4b410687588f080c1aa933` | 54,236 | 54.3 s | 43,596 | 3 | 0.001812 |
| Q2 | sentiment | `87f8d41dea87451db9c7be0d7cae94d9` | 23,583 | 23.7 s | 23,450 | 3 | 0.001636 |
| Q3 | forecast | `021c8e3e8ddf4e4cac73385f428d22d8` | 26,972 | 27.1 s | 26,831 | 3 | 0.001484 |

Q1 reached the gateway at 21:36:18, about two minutes after the page load (the owner's typing time), and 10.6 s passed before the orchestrator logged it (its cold start). All three browser times are under the 120 s ceiling.

## Spend against the caps

| Cap | Used | Limit |
|---|---|---|
| Owner questions through the gateway | 3 (R0) | 6 per round, 30 total |
| Model calls (metered `llm call` lines) | 9 | 30 per round, 150 total |
| List-price cost (`cost_usd`) | $0.004932 | $0.06 per round, $0.30 total |
| Session time from the `ops-db` start | 46 min (start 21:20:48, stop command 22:06:57) | 4 hours |
| The pipeline's verify question | 0 (the step never ran) | 1 |

The paid balance was $6.18 before the session (owner reading, 15:06 CST); no reading after. The gateway's own limits (30 an hour per invite, 50 a day) were not approached.

## Rulings and disclosures

- **Idle precondition (owner-decided at G0, 2026-11-10; it interprets README section 1 and changes nothing in it).** A request the session did not make (before the owner's first question in a round, not from the owner or the pipeline) is recorded in the ledger and does not reset the 20-minute idle clock. Any service, the gateway included, counts in a round only if an `AUTOSCALING` start line for it falls inside the round. A start line outside every round is recorded, is not a start of any round and enters no pass-rule count. **How it applied:** there was no such request or start during the session (21:20 to 22:13). One unsolicited request was seen before the session: the gateway, `2026-11-10T05:15:55Z`, HTTP 404. R0 is the control and was not subject to a 20-minute idle rule (README section 1: "before the deploy").
- **The invite.** The owner made the invite `owner-laptop-4` in their own terminal. Its expiry was read with `invites.py list` at 22:11:35Z, at the owner's instruction, printing only the label, state and expiry: **active, expires 2026-11-11T21:24:49Z (15:24:49 CST)**. The owner kept it active. No link, token or id is recorded here.
- **The `invite_id` field.** The gateway's own `ask answered` log lines carry a 12-character `invite_id`. It appeared in the assistant's tool output while reading R0 logs. It is not written to any file here. The owner decided it is not a stop (2026-11-10).

## Deviations from the prompt

1. **Phase 1 order.** The calibration, the idle read (C3) and the C4 `pre` read ran before the README was committed. All were read-only. C4 `pre` was retaken before the deploy as planned.
2. **The extractor's sha256 changed once, lint-only,** before any live result: the file as calibrated (`2cf8043b…`) failed CI's `ruff`; the committed file (`ee282ac6…`, the blob) has formatting changes only, and its output is identical on the 10-30 data (24 rows). The working-copy file on this Windows checkout has CRLF endings and hashes differently (`e17fd023…`); the blob is the identity.
3. **`.local\l106\` already held files** from an earlier session (`env`, `logs`, `build.log`, `build.sh`, `smoke.csv`, `summary.before`). They were not opened or changed.
4. **README 2a's variable names collide.** The snippet uses `$S` and `$s`, one variable in PowerShell. The first C4 `pre` retake covered QA only; it was rerun with distinct names.
5. **The pre-registered string in README 2b is wrong:** the probe-success line reads "after N attempts", not "attempt(s)" (`evals/l106/phase1-checks.md` section 2). The README was not edited.
6. **The extractor leaves `first_line` empty for single-container services** (gateway, orchestrator, QA): their stdout entries carry no `container_name` label. The verdicts do not use it. The committed extractor was not changed; `fill_round.py` fills the field for R0 and the question and trace fields are filled from `R0-qmap.json`.
7. **R0's open time** was taken from the owner's "I will open browser now" (treated as `go`).
8. **Time zones.** The assistant's early messages labelled local times CDT; the machine is UTC-6 (CST). The owner's "3:41 pm CST" is 21:41Z. This record uses UTC.
9. **The G-CLOSE table stated the invite expiry wrongly** ("by 2026-11-11 23:59 CST", the owner's limit). The actual expiry is 2026-11-11T21:24:49Z.
10. **The assistant ran `invites.py list`** at the owner's later instruction (the owner had earlier said not to), to read one expiry; the id was masked.
11. **The session ended on the stop rule "the build fails"** (README section 5), not on completion. R1 to R4 did not run, and `verify` did not run.
12. **The request match is incomplete in the extractor:** 12 of 18 starts matched a request in the 10-30 calibration and 6 of 7 in R0 (the second gateway start has none). Verdicts do not use it.
13. **Not recorded:** `startup_latencies` (no repo method, `phase1-checks.md` section 2), the v2 execution environment (no read mode; the C4 annotation `run.googleapis.com/execution-environment` is absent on all six services, so generation in use: not observable from outside), the Artifact Registry contents after the failed build, and the Service Health page reading (the failed start rule 2e applies to starts; no start failed).
14. **A ledger placeholder.** The `g2_go` line carried "about 15:5x local", not a time. It is corrected by an appended `correction` line (bounds: after the R0 summary, before 21:54:13Z), which also corrects "about 47" minutes of `ops-db` to 46.2.
15. **`fill_round.py` was rewritten for lint** after it had produced R0's fields. Rebuilt from scratch with the committed extractor and the committed `fill_round.py` on the raw R0 log (`--t1 2026-11-10T21:44:08Z`), it reproduces `starts.json` exactly (7 rows).

## What this session cannot distinguish (README section 6, copied verbatim)

1. **Which ADR-120 change mattered.** The boost and the longer window ship together. A start that passes after more than 20 attempts points at the window; one that passes in under 20 points at neither.
2. **ADR-120 from a fresh rollout.** New settings always arrive with new revisions. R4 runs past the point where 10-30 failed, but it can't separate the two.
3. **ADR-120 from platform state on the day.** 10-30 flipped with no change on our side. A clean session bounds the failure chance; it doesn't remove it.
4. **Where the time before the first log line goes.** The platform logs nothing between "Starting new instance" and the probe result.
5. **The execution environment in use,** while the setting is unset.
6. **The retry, unless a first answer degrades.** If a retry does run, a start still in progress under the 120 s window may serve it, which is a different path from a second start.
7. **The control is one round:** two starts of the affected pair.
8. **The zone or host of an instance.** Cloud Run doesn't expose it.
9. **Time before the gateway receives a request.** The 120 s ceiling doesn't cover it. Record the browser timer beside the gateway's `duration_ms`.

