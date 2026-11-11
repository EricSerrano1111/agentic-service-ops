# L-106 cold-start verification, attempt 2, 2026-11-11: summary

*2026-11-11 (owner present). Assistant-drafted, except the status line (owner-decided at G-REC, 2026-11-11), the rulings marked "owner-decided", and the one statement about ADR-120 decision 3 (liveness without the database; from L-106 item 9), whose wording is the owner's.* The pre-registration is `evals/l106/README.md` (merged in PR #98, merge commit `f2cddf68ee8b23427d974f5701023318581cbdc8`; sha256 `5de4856b3fb78c1573397ffbd9f398b71e33a88327a88c275ab6e7ebbe4dfde3`; the extractor's committed blob has sha256 `ee282ac62ce0478bb308242b537065b3d140edbffe3b52727e6c6a476404540f`). Nothing in either was changed after a result was seen. Attempt 2 re-ran everything from R0 under the same frozen pre-registration; **attempt 1's R0 (2026-11-10) does not count here.** Section 9 of `evals/l106/phase1-checks.md` (PR #101, merge commit `8ec22db032f8b5e66da166eeb0a84de84b2d4784`) was fixed before any result; that merge commit is the deploy target. Times are UTC unless marked CST (the owner's machine is UTC-6). Files beside this one: `starts.json` (R0 to R5; the six pipeline rollout starts are in `starts-rollout.json`), `ledger.jsonl`, `qmap.json`. They hold no invite link, token or invite id (the files were scanned for every invite id that appears in the session's raw gateway logs; none is present).

## Verdict (README section 4)

**PASS.** P1 holds with coverage met, and P2 is not exercised.

**Status line (owner-decided, G-REC 2026-11-11), README section 3, row "Control passes / post-deploy passes":**

> Open; not reproduced on either configuration. ADR-120 was deployed (build 8b6493d8, commit 8ec22db; its first live run also passed ADR-121's pinned step images). In the control (R0, the old configuration), 0 of 2 starts of ops-reporting and ops-qa failed (longest 21.8 s). In R1 to R4 (the ADR-120 configuration), 0 of 8 starts of the pair failed (longest 26.2 s; one-sided 95% upper bound on the pair's failure rate 31%), including starts past 10-30's 60 and 99-minute failure points, and 0 of 25 starts of all services failed or ran over 60 s; the README §4 verdict is PASS. P2 (a retry after a degraded first answer) was not exercised. L-106 is neither reproduced, nor mitigated, nor fixed; ADR-120 is deployed and untested against the failure.

- **P1 (starts), R1 to R4:** 25 autoscale starts (6, 6, 6, 7), all passed their startup probe; none failed, none indeterminate. Coverage: `ops-reporting` 4 autoscale starts and `ops-qa` 4 (the rule is at least 3 each, with at least 1 each in R4); R4 had 1 each. Coverage is met.
- **P2 (retry):** not exercised. No first answer degraded in any round, so the retry stays unverified.
- **Control label (R0):** the control **passed**: 0 of 2 starts of the affected pair failed (`ops-reporting` 21.8 s, `ops-qa` 14.7 s). "Control fails" (README section 3) did not happen. The control is two starts of the pair (section 6, item 7).
- **Beside the verdict, never a condition (section 4):** first answers `answered` and `verified`: 12 of 12 in R1 to R4 (and 3 of 3 in R0). Starts over 60 s: 0 of 25 in R1 to R4 (0 of 6 in R0). With 0 failures in n = 8 starts of the pair after the deploy, the one-sided 95% upper bound is `1 − 0.05^(1/8)` = 31%; for the control's n = 2 it is 78%. The longest start to probe success was 26.2 s (`ops-reporting`, R4).
- **No p-value is reported** (starts in one session are not independent).
- **Why PASS is not "mitigated".** The old configuration also passed in R0, so there was no failure to remove: on 10-30 the old configuration went from every autoscale start passing to 6 of 6 reporting and QA starts failing within one session. The R1 to R4 pass is consistent with ADR-120 working and with the failure not occurring today; this session cannot tell the two apart (section 6, items 1 to 3 below). 10-30's first failures came about 60 min (reporting) and 99 min (QA) after that day's rollout; here the build finished at 18:15:58Z, R3's reporting start was 72 min after it, and R4's reporting and QA starts were 106.6 and 107.1 min after it, and passed.

## What happened, in order

| Time (UTC) | Event |
|---|---|
| 17:41:48 | PR #101 merged (the section 9 records; merge commit `8ec22db`; diff against `5e91315` lists only `evals/l106/phase1-checks.md`) |
| 17:46:18.7 | The owner started `ops-db` (operation `48090a8c…` start; the session clock starts). `RUNNABLE ALWAYS` first read 17:53:05; the operation read `DONE` at 17:55:47 |
| 17:54:30 | R0 opened (the owner's `go`); the owner reported the last answer at 12:00 CST (18:00Z); logs pulled 18:02:31 |
| 18:04 to 18:05 | C4 `pre` retaken for all six services into `.local\l106b\` (distinct variable names); the temporary trigger copy differs from `deploy/trigger_full.yaml` only in `disabled` |
| 18:07:21 to 18:08:31 | The owner enabled the trigger (read back enabled at 18:08:31; `origin/main` re-read equal to `8ec22db`) |
| 18:09:23 | The owner ran the trigger: build `8b6493d8-5004-4e9a-9627-4e68a9dab296`, commit `8ec22db`, `_RUN_VERIFY` `true` |
| 18:15:58.5 | The build finished: **SUCCESS**, all 17 steps |
| 18:17:19 to 18:19:10 | The owner disabled the trigger (read back `disabled: True` at 18:19:10) |
| 18:37:33 to 18:40:44 | R1 |
| 19:01:12 to 19:04:45 | R2 |
| 19:27:38 to 19:30:37 | R3 |
| 20:02:05 to 20:05:13 | R4 (T = 20:05:12.8, the last answer, is the exploratory R5's reference time) |
| 20:11:45, 20:20:21 | Exploratory R5: E1 and E2 (out of scope, gateway and orchestrator only) |
| 20:27:36 to 20:28:18 | Exploratory R5: Q1 |
| 20:34:37.5 | The owner stopped `ops-db` (operation `9afc46c2…`, `DONE` 20:35:20.4); G-CLOSE |
| 20:37:08 | End state read back |

## The deploy

**Build `8b6493d8-5004-4e9a-9627-4e68a9dab296`:** commit `8ec22db032f8b5e66da166eeb0a84de84b2d4784`, `_RUN_VERIFY` `true`; created 18:09:23Z, started 18:10:17.6Z, finished 18:15:58.5Z (`SUCCESS`). All 17 steps passed, including `verify`. **This was the first live run of ADR-121's pinned step images: it passed.** `results.buildStepImages` (read with `--region=us-central1`) lists nine times `gcr.io/cloud-builders/docker@sha256:fbc05705e6f24467e40ae8a4097ab9b8fae1116551f838fa2c55f4367427fc36`, once `python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b`, and seven times `gcr.io/google.com/cloudsdktool/cloud-sdk@sha256:b38f2881552c3054d140c8eeb4ad88bdc0eb4deeeb38507c5dac1403adc3ee64`: the ADR-121 pins, step for step (the steps' `name:` fields carry the same digests).

**The pipeline's own rollout starts** (kind `DEPLOYMENT_ROLLOUT`; outside every round and every count, in `starts-rollout.json`): six starts, all passed their startup probe, none failed.

| Start (UTC) | Service | Revision | Kind | To probe success (s) | Probe attempts |
|---|---|---|---|---|---|
| 18:12:53.36 | qa | `00007-w9l` | rollout | 8.6 | 3 |
| 18:13:22.49 | sentiment | `00006-8jp` | rollout | 16.8 | 3 (`mcp-feedback`), 3 (`agent-sentiment`) |
| 18:13:53.32 | forecast | `00006-nsf` | rollout | 14.1 | 3 (`mcp-volume`), 2 (`agent-forecast`) |
| 18:14:29.37 | reporting | `00010-xtq` | rollout | 16.8 | 3 (`mcp-incidents`), 3 (`agent-reporting`) |
| 18:14:57.92 | orchestrator | `00012-t27` | rollout | 8.3 | 3 |
| 18:15:18.96 | gateway | `00005-m67` | rollout | 5.4 | 2 |

**The verify step** (outside the caps; at most 1 question): 1 question, `answered`, route `reporting`, 5,747 ms at the orchestrator, 3 model calls, $0.00183 (trace `fea3220392c34fcda06cd1b8c6addf8f`). Its log holds four HTTP 403 responses (18:15:31 to 18:15:33): they are `deploy/verify.py`'s refusal probes, each expected to be 401 or 403 (`refused()`, `deploy/verify.py:143-144`): the three unauthenticated `INGRESS_PROBES` (`:149-153`: orchestrator `POST /ask`, orchestrator `GET /`, reporting `GET /`) and the probe-service-account call `reporting refuses a caller that is not the orchestrator` (`:84`, `:573-584`: reporting `GET /.well-known/agent-card.json`). The four requests-log entries match them one for one (same methods, paths and order, user agent `Python-urllib`), and the step passed.

**Trigger.** Enabled from between 18:07:21 and 18:08:31 to between 18:17:19 and 18:19:10 (the exact times of the two imports were not read); read back `disabled: True` at 18:19:10, equal to `deploy/trigger_full.yaml` in every field (compared in Python), and `disabled: True` again at 20:37:08 (that later read covered the `disabled` value only). No other build ran.

**Readback, C4 `pre` against `post`** (key-by-key comparison of the six `gcloud run services describe --format export` files). It matches the expected readback of `phase1-checks.md` section 5, as restated in section 9.6; no stop:

| Change | Result |
|---|---|
| Startup CPU boost | the annotation `run.googleapis.com/startup-cpu-boost: 'true'` appears on all six services' revision templates (the key name `phase1-checks.md` section 2 said could not be known before the deploy), so it covers all nine containers |
| `startupProbe.failureThreshold` | 20 to 40 on eight containers; the sentiment agent was already 40 |
| Image tag | `9599bae33625823b2081f68e6da8c4bbc367e7ab` to `8ec22db032f8b5e66da166eeb0a84de84b2d4784` on all nine containers |
| Everything else | no difference: `cpu-throttling: 'false'` on all six, min and max scale, concurrency, limits, `cloudsql-instances`, `container-dependencies`, liveness probes (`failureThreshold` 3), `LLM_MODE`, env and secret names |
| `run.googleapis.com/execution-environment` | absent on all six, before and after: generation in use is not observable from outside |

New serving revisions, all 100% and `latestRevision: true`: gateway `00005-m67`, orchestrator `00012-t27`, reporting `00010-xtq`, sentiment `00006-8jp`, forecast `00006-nsf`, QA `00007-w9l`. (Before: `00004-zqw`, `00011-mml`, `00009-bjp`, `00005-nzq`, `00005-k5r`, `00006-dj4`.)

## R0, the control (old configuration; 17:54:30Z to about 18:00Z; logs pulled 18:02:31Z)

| Start (UTC) | Service | Revision | First log line (s) | Probe attempts | To probe success (s) | Over 60 s | For |
|---|---|---|---|---|---|---|---|
| 17:54:42.05 | gateway | `00004-zqw` | 5.5 | 3 | 8.6 | no | page load (no question) |
| 17:55:27.73 | orchestrator | `00011-mml` | 7.8 | 3 | 8.2 | no | Q1 |
| 17:55:38.50 | reporting | `00009-bjp` | 8.4 (`mcp-incidents`), 20.9 (`agent-reporting`) | 4 (`mcp-incidents`), 3 (`agent-reporting`) | 21.8 | no | Q1 |
| 17:56:02.02 | qa | `00006-dj4` | 11.4 | 5 | 14.7 | no | Q1 |
| 17:57:37.46 | sentiment | `00005-nzq` | 8.6 (`mcp-feedback`), 17.0 (`agent-sentiment`) | 3 (`mcp-feedback`), 3 (`agent-sentiment`) | 17.7 | no | Q2 |
| 17:58:53.26 | forecast | `00005-k5r` | 8.6 (`mcp-volume`), 20.6 (`agent-forecast`) | 4 (`mcp-volume`), 4 (`agent-forecast`) | 23.2 | no | Q3 |

Every service counted has an `AUTOSCALING` start line inside the round (README section 1).

| Q | Route | Trace | Gateway `duration_ms` | Browser | Orchestrator `duration_ms` | Model calls | `cost_usd` |
|---|---|---|---|---|---|---|---|
| Q1 | reporting | `2b11b90a0b214f67a1539a554cb0ce3e` | 50,431 | 50.6 s | 41,897 | 3 | 0.0018 |
| Q2 | sentiment | `0c5a045adb134accab48ca22c276f917` | 21,334 | 21.4 s | 21,138 | 3 | 0.001576 |
| Q3 | forecast | `e45e8cc4da3e4b01a233deea2d79c641` | 26,329 | 26.5 s | 26,187 | 3 | 0.001523 |

All `answered`, `verified`, no retry.

## R1 (ADR-120 configuration; 18:37:33Z to 18:40:44Z; idle 20 min 34 s at the gate read, 18:36:15Z; logs read 18:43:21Z)

| Start (UTC) | Service | Revision | First log line (s) | Probe attempts | To probe success (s) | Over 60 s | For |
|---|---|---|---|---|---|---|---|
| 18:37:36.33 | gateway | `00005-m67` | 2.4 | 2 | 5.3 | no | page load (no question) |
| 18:37:56.45 | orchestrator | `00012-t27` | 4.0 | 2 | 5.2 | no | Q1 |
| 18:38:03.32 | reporting | `00010-xtq` | 8.4 (`mcp-incidents`), 21.0 (`agent-reporting`) | 4 (`mcp-incidents`), 4 (`agent-reporting`) | 23.0 | no | Q1 |
| 18:38:28.15 | qa | `00007-w9l` | 11.6 | 5 | 14.7 | no | Q1 |
| 18:39:26.76 | sentiment | `00006-8jp` | 3.8 (`mcp-feedback`), 9.8 (`agent-sentiment`) | 2 (`mcp-feedback`), 2 (`agent-sentiment`) | 10.8 | no | Q2 |
| 18:40:21.46 | forecast | `00006-nsf` | 9.2 (`mcp-volume`), 19.0 (`agent-forecast`) | 4 (`mcp-volume`), 3 (`agent-forecast`) | 20.2 | no | Q3 |

| Q | Route | Trace | Gateway `duration_ms` | Browser | Orchestrator `duration_ms` | Model calls | `cost_usd` |
|---|---|---|---|---|---|---|---|
| Q1 | reporting | `883dae16a18b41abab920e8339dfaa29` | 47,795 | 47.8 s | 42,388 | 3 | 0.001817 |
| Q2 | sentiment | `5884b961b33047dc9b5d5a7b24e19ce7` | 14,713 | 14.8 s | 14,556 | 3 | 0.001634 |
| Q3 | forecast | `522aea58434848b482b56841bb74d54e` | 23,303 | 23.4 s | 23,249 | 3 | 0.001473 |

All `answered`, `verified`, no retry.

## R2 (19:01:12Z to 19:04:45Z; logs read 19:07:20Z)

| Start (UTC) | Service | Revision | First log line (s) | Probe attempts | To probe success (s) | Over 60 s | For |
|---|---|---|---|---|---|---|---|
| 19:01:14.92 | gateway | `00005-m67` | 2.5 | 2 | 5.3 | no | page load (no question) |
| 19:01:29.33 | orchestrator | `00012-t27` | 7.5 | 3 | 8.2 | no | Q1 |
| 19:01:40.70 | reporting | `00010-xtq` | 9.5 (`mcp-incidents`), 22.3 (`agent-reporting`) | 4 (`mcp-incidents`), 4 (`agent-reporting`) | 23.1 | no | Q1 |
| 19:02:05.52 | qa | `00007-w9l` | 12.3 | 5 | 14.7 | no | Q1 |
| 19:03:36.03 | sentiment | `00006-8jp` | 4.4 (`mcp-feedback`), 10.2 (`agent-sentiment`) | 2 (`mcp-feedback`), 2 (`agent-sentiment`) | 10.7 | no | Q2 |
| 19:04:21.93 | forecast | `00006-nsf` | 8.0 (`mcp-volume`), 16.7 (`agent-forecast`) | 3 (`mcp-volume`), 4 (`agent-forecast`) | 20.3 | no | Q3 |

| Q | Route | Trace | Gateway `duration_ms` | Browser | Orchestrator `duration_ms` | Model calls | `cost_usd` |
|---|---|---|---|---|---|---|---|
| Q1 | reporting | `dc66a46a7aa24e749a524a41996bac65` | 52,412 | 52.5 s | 43,997 | 3 | 0.001807 |
| Q2 | sentiment | `6bc9f02bb98b4003a8513a028c753baa` | 14,088 | 14.2 s | 13,904 | 3 | 0.001654 |
| Q3 | forecast | `95281417608a4097a76bd664afdbb2a7` | 24,198 | 24.3 s | 24,132 | 3 | 0.001525 |

All `answered`, `verified`, no retry.

## R3 (19:27:38Z to 19:30:37Z; logs read 19:33:19Z)

| Start (UTC) | Service | Revision | First log line (s) | Probe attempts | To probe success (s) | Over 60 s | For |
|---|---|---|---|---|---|---|---|
| 19:27:42.15 | gateway | `00005-m67` | 2.6 | 2 | 5.4 | no | page load (no question) |
| 19:28:02.08 | orchestrator | `00012-t27` | 3.3 | 2 | 5.2 | no | Q1 |
| 19:28:08.59 | reporting | `00010-xtq` | 8.6 (`mcp-incidents`), 22.3 (`agent-reporting`) | 4 (`mcp-incidents`), 4 (`agent-reporting`) | 23.3 | no | Q1 |
| 19:28:33.56 | qa | `00007-w9l` | 10.8 | 4 | 11.8 | no | Q1 |
| 19:29:28.45 | sentiment | `00006-8jp` | 4.1 (`mcp-feedback`), 10.0 (`agent-sentiment`) | 2 (`mcp-feedback`), 2 (`agent-sentiment`) | 10.7 | no | Q2 |
| 19:30:15.16 | forecast | `00006-nsf` | 8.0 (`mcp-volume`), 18.3 (`agent-forecast`) | 3 (`mcp-volume`), 4 (`agent-forecast`) | 20.1 | no | Q3 |

| Q | Route | Trace | Gateway `duration_ms` | Browser | Orchestrator `duration_ms` | Model calls | `cost_usd` |
|---|---|---|---|---|---|---|---|
| Q1 | reporting | `964fc1fa9e3b421e900da8afeed285d7` | 44,508 | 44.6 s | 39,203 | 3 | 0.001814 |
| Q2 | sentiment | `bf4ad83b5fc74c18908843b104af4ab0` | 14,304 | 14.4 s | 14,137 | 3 | 0.001599 |
| Q3 | forecast | `36fe06e2232647398459e47cc581777f` | 23,166 | 23.3 s | 23,110 | 3 | 0.001524 |

All `answered`, `verified`, no retry.

## R4 (20:02:05Z to 20:05:13Z; idle 30 min at the gate read, 20:00:59Z; opened 106 min after the build's `finishTime`; logs read 20:07:56Z)

| Start (UTC) | Service | Revision | First log line (s) | Probe attempts | To probe success (s) | Over 60 s | For |
|---|---|---|---|---|---|---|---|
| 20:02:08.79 | gateway | `00005-m67` | 2.5 | 2 | 5.3 | no | page load (no question) |
| 20:02:21.12 | orchestrator | `00012-t27` | 10.8 | 4 | 11.4 | no | Q1 |
| 20:02:35.37 | reporting | `00010-xtq` | 8.3 (`mcp-incidents`), 23.5 (`agent-reporting`) | 4 (`mcp-incidents`), 5 (`agent-reporting`) | 26.2 | no | Q1 |
| 20:03:03.21 | qa | `00007-w9l` | 11.8 | 5 | 14.7 | no | Q1 |
| 20:03:51.00 | sentiment | `00006-8jp` | 9.5 (`mcp-feedback`), 20.6 (`agent-sentiment`) | 4 (`mcp-feedback`), 4 (`agent-sentiment`) | 23.0 | no | Q2 |
| 20:04:14.03 | sentiment | `00006-8jp` | 4.8 (`mcp-feedback`), 10.7 (`agent-sentiment`) | 2 (`mcp-feedback`), 3 (`agent-sentiment`) | 13.7 | no | Q2 |
| 20:05:00.25 | forecast | `00006-nsf` | 3.6 (`mcp-volume`), 9.2 (`agent-forecast`) | 2 (`mcp-volume`), 2 (`agent-forecast`) | 10.7 | no | Q3 |

| Q | Route | Trace | Gateway `duration_ms` | Browser | Orchestrator `duration_ms` | Model calls | `cost_usd` |
|---|---|---|---|---|---|---|---|
| Q1 | reporting | `6e09a9d9e9f346b6a130dcd8720449e3` | 58,219 | 58.3 s | 46,722 | 3 | 0.001802 |
| Q2 | sentiment | `054b66d9df8c4cdba1416fece0808cf0` | 40,299 | 40.4 s | 40,102 | 3 | 0.001576 |
| Q3 | forecast | `312e28037b92405ea08e841d38d25011` | 13,584 | 13.6 s | 13,428 | 3 | 0.001493 |

All `answered`, `verified`, no retry, under the 120 s ceiling.

**An observation in R4's Q2 (no cause is named).** Two sentiment instances started 23 s apart. The first (20:03:51.0) served only the orchestrator's agent-card GET, which took 22.7 s. The task POST arrived at 20:04:14.005, as that instance became ready, and started a second instance (20:04:14.03; 14.7 s), which served the task. Both starts passed (23.0 s and 13.7 s). Q2 took 40.3 s at the gateway, against 14 to 15 s in R1 to R3. The first instance shut down at 20:08:57. Both starts count in P1 (every autoscale start of every service), and both passed.

**Idle shutdowns.** In every between-round wait the warm instances shut down about 15 minutes after their last request (the shutdown lines are in the read for the next round), so each round started cold. These are idle shutdowns, not an effect of `ops-db`.

## Exploratory R5 (outside the pre-registration; no pass-rule count, no coverage count, no control label, no README section 3 row)

**Added after R0 to R3 were seen and before R4** (owner-decided 2026-11-11, about 13:40 CST, recorded in the ledger at 19:45:33Z, with two adjustments recorded at 19:47:07Z). **Why:** on 2026-10-30 the failed reporting and QA starts came after a stretch of edge questions that kept the gateway and orchestrator warm while reporting and QA went cold. In R0 to R4 all six services start cold together. R5 reproduces that condition: a cold reporting and QA start behind a warm gateway and orchestrator.

**Procedure.** T = R4's last answer from the gateway log, 20:05:12.8Z. E1 at about T+6 and E2 at about T+15 (never before T+11, always before Q1), typed in the same page with no reload; both had to reach only the gateway and the orchestrator (route `out_of_scope` or ambiguous, no request to reporting or QA, QA not applicable). G-R5 at T+20 or later: reporting and QA 20 minutes or more idle from their own last request; gateway and orchestrator warm (last request under 10 minutes ago, no shutdown line since). Then Q1 only, in the same page. The owner changed E1 to "What's the weather in New York today?" (from "How's the Southeast doing?") because FR-03 is unmet and routing is not deterministic (L-17), so a best-fit route to reporting could have spoiled R5; both E1 and E2 were routed `out_of_scope` and declined on 10-30 (`docs/deploy-window-log.md`, rows P1 and 5). The assistant's first note on the timing had the direction reversed (an E2 later than T+14 does not break the idle condition; one earlier than T+11 does); the owner corrected it.

**G-R5 (read 20:26:01Z to 20:26:22Z, before any request reached the gateway):**

| Service | Newest request (UTC) | Idle | Condition | Holds |
|---|---|---|---|---|
| gateway | 20:20:20.8 (E2) | 5 min 40 s | warm: under 10 min, no shutdown line | yes |
| orchestrator | 20:20:20.97 (E2) | 5 min 40 s | warm: under 10 min, no shutdown line | yes |
| reporting | 20:03:01.6 (R4 Q1) | 22 min 59 s | 20 min or more | yes |
| QA | 20:05:12.1 (R4 Q3 verification) | 20 min 49 s | 20 min or more | yes |
| sentiment | 20:04:14.0 | 22 min | not required | cold |
| forecast | 20:05:11.0 | 21 min | not required | cold |

| Start (UTC) | Service | Revision | First log line (s) | Probe attempts | To probe success (s) | Over 60 s | For |
|---|---|---|---|---|---|---|---|
| 20:27:37.37 | reporting | `00010-xtq` | 10.1 (`mcp-incidents`), 22.5 (`agent-reporting`) | 4 (`mcp-incidents`), 4 (`agent-reporting`) | 23.3 | no | R5 Q1 (exploratory) |
| 20:28:02.49 | qa | `00007-w9l` | 11.7 | 5 | 14.5 | no | R5 Q1 (exploratory) |

| Q | Route | Trace | Gateway `duration_ms` | Browser | Orchestrator `duration_ms` | Model calls | `cost_usd` |
|---|---|---|---|---|---|---|---|
| E1 (20:11:45) | `out_of_scope`, `declined`, QA not applicable | `06b7fbb6b5344d0da909dc4056254733` | 983 | about 1.1 s (owner) | 841 | 1 | 0.000535 |
| E2 (20:20:21) | `out_of_scope`, `declined`, QA not applicable | `6b8beed0d75f401490625eaf409125a9` | 898 | about 1.1 s (owner) | 739 | 1 | 0.000524 |
| R5 Q1 (20:27:36) | reporting, `answered`, `verified` | `28cae26569d84b008c4cedd496c66003` | 41,846 | 42.0 s | 41,685 | 3 | 0.001814 |

E1 and E2 made no request to reporting, QA, sentiment or forecast and started no instance. The gateway and orchestrator had no start line and no shutdown line from E2 to the end of R5. **The 10-30 condition (cold reporting and QA behind a warm gateway and orchestrator) reproduced once; 0 of 2 starts failed; one observation, not a rate.** The status line above contains nothing from R5. Q1 had no retry. R5's starts are in `starts.json` as round `R5`, outside every count.

## ADR-120 decision 3 (liveness without the database; from L-106 item 9)

**Not exercised: no warm sidecar at the stop** (owner-decided wording). The `mcp-feedback` instance (sentiment `77a006`) shut down at 20:19:38Z and the `mcp-volume` instance (forecast `da3c1b`) at 20:20:19Z, both idle shutdowns before `ops-db` stopped at 20:34:37Z. It is not recorded as working. After the stop, the read to 20:37:42Z holds no request, start, shutdown or probe-failure line. Starts or shutdowns after that read are "after G-CLOSE" and counted nowhere (none were read).

## Spend against the caps

| Cap | Used | Limit |
|---|---|---|
| Owner questions through the gateway | R0 to R4: 15 (3 per round); R5: 3 (E1, E2, Q1); total 18 | 6 per round, 30 total |
| Model calls (metered `llm call` lines) | R0 to R4: 45 (9 per round); R5: 5; total 50 | 30 per round, 150 total |
| List-price cost (`cost_usd`) | R0 to R4: $0.024617 (about $0.005 per round); R5: $0.002873; total $0.027490 | $0.06 per round, $0.30 total |
| Session time from the `ops-db` start | 2 h 48 min 19 s (17:46:18.7Z to the stop command 20:34:37.5Z) | 4 hours |
| The pipeline's verify question | 1 (3 model calls, $0.00183), outside the caps | at most 1 |

The paid balance was $6.18 before the session (owner-read 11:30 CST). Paid balance after the session: $6.15 (owner-read 1456CST). (A drop of $0.03; this session's list-price total, including the verify step's question, is $0.02932. Balances are read to the cent, so the two are consistent, not proven equal.) The gateway's own limits (30 an hour per invite, 50 a day in total) were not approached: 18 questions through the gateway today, at most 6 in any hour.

## Rulings and disclosures

- **§8 rulings carried over unchanged** (`phase1-checks.md` section 9.4): idle precondition and round window (ruling 1); `_RUN_VERIFY` on (ruling 3); the extractor (ruling 4); the older `.local\l106\` files untouched (ruling 5). **How ruling 1 applied:** every round's idle read (C3) showed only requests we made; the one unsolicited request seen was the gateway's at 2026-11-11T00:27:09Z (HTTP 404), before the session. The pipeline's rollout starts and verify requests (18:12 to 18:16) fell outside every round and are recorded separately; the exploratory R5's starts are in `starts.json` as round `R5` and enter no count.
- **Ruling 2, restated (owner-decided):** the owner made the invite `owner-laptop-5` in the owner's own terminal and revoked `owner-laptop-4` on 2026-11-11 before the session. Its expiry as the owner read it: 2026-11-13T17:10:59Z, later than §8 ruling 2's limit, which the restatement replaced for attempt 2. It is the only active invite. All of this is owner-stated and unverified by the assistant. The assistant ran neither `create` nor `list`; no link or id is recorded.
- **The expected readback** (section 5, restated in 9.6) held; the image tag moved from `9599bae…` to `8ec22db…`.
- **Disclosures fixed before any result** (9.7): the rollout changes more than ADR-120's settings (the application images were rebuilt from unpinned Dockerfile `FROM` lines, ADR-121 decision 3, on a different date from 10-30, and the ADR-120 liveness handler change in `mcp_feedback` and `mcp_volume` shipped); this was the first live run of ADR-121's pinned step images (it passed); attempt 1's R0 is not counted.
- **The preflight (owner-decided deviation, 9.2).** The runbook loop on the owner's PC resolved the two `gcr.io` digests in all three runs and reset on `python:3.12-slim@sha256:5e2bdb1b…` each time (`wsarecv: An existing connection was forcibly closed`; recorded as "check not completed (network)"; run 2 was the assistant's own immediate retry, before the owner ruled). The owner ran the same `docker manifest inspect` from Google Cloud Shell: `exit=0` (owner-reported, not observed). The build later ran that digest as the `render` step.
- **The R5 ruling and its two adjustments** (owner-decided, above).

## Deviations from the prompt

1. **Preflight:** the runbook loop did not pass on the owner's PC (three network resets); the Cloud Shell read is owner-reported (above).
2. **Clock times.** The owner's reported times were minute-level (for example "1305 cst" for a last answer at 19:04:44.7Z); this record uses the gateway log's times. Round windows opened at the owner's `go` (the assistant's clock, to the second), not at the page load.
3. **Idle clock.** The 20-minute rule was applied from the last request's completion where that was later than its receipt time in the requests log (for example R1: 18:35:42Z from the verify step's request completing about 18:15:42Z).
4. **C4 `pre` was taken about 4 minutes before the enable and 5 before the run,** not "immediately before"; no service changed in between (C4 `post` differs from it only as expected).
5. **The assistant's wrong statements, each corrected by the owner before it mattered:** that R2 to R4 must each start both services cold (the rule is at least 3 starts each with at least 1 in R4, so R2 or R3 could have lost one); the direction of the R5 E2 timing risk; and, in one G-R5 note, "deviation: the gate print followed the owner's message", which the owner's later timing (Q1 asked at 14:27 to 14:28 CST; the log shows the gateway request began at 20:27:36Z, after the 20:26:01Z read) showed was not one. The ledger holds the earlier line and the appended correction.
6. **Two tool slips with no effect on a result:** a PowerShell call that contained a bash heredoc failed to parse and ran nothing (it was rerun as two calls); one early per-container attempt print used the wrong key (the rows were correct).
7. **The extractor leaves `first_line` empty for single-container services** (gateway, orchestrator, QA); the committed `evals/results/l106/2026-11-10/fill_round.py` (unchanged, run as committed) fills it, and the question and trace fields come from `qmap.json`.
8. **The trigger's enable and disable times** are bounded by reads (enabled by 18:08:31, disabled by 18:19:10), not exact.
9. **Not recorded:** `startup_latencies` (no repo method), the v2 execution environment (no read mode; the C4 annotation is absent on all six), the base-image digests inside the rebuilt application images, and the Service Health page reading (no start failed).
10. **Ledger:** written during the session from the assistant's reads; it holds one appended correction (Q1's timing). The owner's R5 ruling and its two adjustments are in it, verbatim, with their times.
11. **R5** was added after R0 to R3 were seen (owner-decided), and is outside the pre-registration.

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
