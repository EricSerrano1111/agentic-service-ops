# Project audit report (read-only), 2026-11-11

Audited at `main` = `0bab705` (PR #102 merge). Deployed commit `8ec22db`, build `8b6493d8-5004-4e9a-9627-4e68a9dab296` (SUCCESS, 2026-11-11). Nothing was changed; the only file written is this report.

## 1. Summary

**43 findings.** No finding shows the deployed system doing the wrong thing on a path the demonstration uses. The blocking items are all in documents: the demo runbook (stale and with two commands that fail as written) and four graded documents that contradict the current system.

| Severity | Count |
|---|---|
| Blocks demo | 4 |
| Blocks submission | 4 |
| Correctness bug | 5 |
| Records hygiene | 18 |
| Nice to have | 12 |

| Area (primary) | Count |
|---|---|
| 1 Records consistency | 11 |
| 2 Code against the spec | 6 |
| 3 Tests and CI | 11 |
| 4 Deployed configuration | 3 |
| 5 Security model | 6 |
| 6 Demo and grading readiness | 6 |

**Verified / Plausible:** 39 Verified, 4 Plausible (F-08, F-21, F-25, F-35; reasons in each row).

**Areas not completed:** none in full. All six areas returned (each subagent was interrupted by the usage limit and resumed from its saved state). Parts not completed, with reasons:

- **Area 1:** the 107 L-entries were cross-checked by pattern against "resolves / closes / fixed" claims, not each read in full against the code.
- **Area 2:** the §6 forecast-recompute rules and the repeat-driver rules were not read line by line against `agent_qa` and `mcp_incidents/repeats.py` (covered only by the passing unit suite). Integration checks are forbidden while `ops-db` is stopped.
- **Area 4:** the Docker Hub digest of `python:3.12-slim` (needs a command outside the allowed list); secret existence and versions; the runbooks' `logging read` filters were not exercised.
- **Area 5:** the per-container Cloud SQL socket on the deployed services. `describe` shows only the revision-wide annotation, so "socket in the sidecar only" is confirmed from the repo definitions and a unit test, not from the live service.
- **Area 6:** the raw deprecations table row. The page was read through the fetch tool, which summarises (see section 3, Area 6).

**Orientation facts, all reproduced:** the six serving revisions (gateway `00005-m67`, orchestrator `00012-t27`, reporting `00010-xtq`, sentiment `00006-8jp`, forecast `00006-nsf`, QA `00007-w9l`); build `8b6493d8…` SUCCESS at `8ec22db`; `ops-db` `STOPPED NEVER`; trigger `disabled: True`. Nothing under `services`, `packages` or `deploy` changed after `8ec22db`, so the deployed code equals `main` (two subagents, independently).

**One thing to settle first.** The audit prompt says the demonstration is about 11-15 to 11-22. `deploy/RUNBOOK_DEMO.md:12-13` says the slots are *announced* then, the date is `[TBD]`, and a slot outside Window B needs a new ADR. If the slot does fall before 12-01, section A's day-before steps (which open Window B) do not apply as written, and that ADR does not exist. This is recorded in the runbook itself, so it is not a finding; it decides how urgent F-04 and F-12 are.

## 2. Findings

### Blocks demo

| ID | Area | Severity | Verified / Plausible | Where | What's wrong | Why it matters | Suggested fix (one line) | Size | Required or portfolio |
|---|---|---|---|---|---|---|---|---|---|
| F-01 | 6 | Blocks demo | Verified | `deploy/RUNBOOK_DEMO.md:91-95`; `curl -s -o /dev/null -w "%{http_code} -> %{redirect_url}" https://ai.google.dev/gemini-api/docs/deprecations` → `301 -> https://aistudio.google.com/docs/deprecations` | The day-before deprecation check uses `curl.exe -s` with no `-L`. The page now redirects, so the saved file has no table and `Select-String` prints nothing. | The stop rule is "if it now names a shutdown date … stop". Empty output reads as "no date", so the one check R-15 relies on passes silently. | Add a dated note: use the new URL (or `-L`) and treat "no row found" as a failed check. | S | Required |
| F-02 | 4, 6 | Blocks demo | Verified | `deploy/RUNBOOK_DEMO.md:400`; `deploy/RUNBOOK_GRADING.md:118`; `deploy/verify.py:496-509` | Both runbooks give `verify.py --ipv4` as a standalone command. `verify.py` needs eight environment variables and exits 1 with `FAIL  configuration: unset …`. The recovery sequence loads only `$P $R $N $G $S` (`RUNBOOK_DEMO.md:391`); only `RUNBOOK_V.md:365` onward sets the eight. | It is step 1 of "the system is down", run inside a 10 to 20 minute buffer. It already failed this way on 2026-10-30 (`docs/deploy-window-log.md:594`) and the runbooks were not corrected. | Add a dated note pointing at the `RUNBOOK_V.md` variable block, or drop `verify.py` from the recovery step. | S | Required |
| F-03 | 6 | Blocks demo (low likelihood) | Verified | `deploy/RUNBOOK_DEMO.md:374-385`; `services/api_gateway/src/api_gateway/app.py:53-64` | Section F has no row for a model-side failure. The gateway has three fixed messages for it (rate-limited, daily quota used up, model unavailable). An exhausted prepaid balance is covered only in `RUNBOOK_GRADING.md:120-121`. | These are failures a rollback can't fix, and the runbook gives no line to say and no action. | Add a dated row: what each message means, the wait or top-up, then the screenshots. | S | Required |
| F-04 | 1, 4, 6 | Blocks demo | Verified | `deploy/RUNBOOK_DEMO.md:19, 36-40, 64-65, 70, 72, 387, 389`; `docs/deploy-window-log.md:699, 701` | The runbook's latest dated note is 2026-10-30 (file last changed 11-07, `ed6b26a`). It still says: the gateway check reads `ops-gateway-00004-zqw` (now `00005-m67`); ADR-120's fix is "Not yet verified: until the cold-start test in the next deploy session passes" (it deployed and ran 11-11); minimum instances "are listed for the next session"; a deadline of 11-09; and invite `owner-laptop-3` (expired). The current owner invite `owner-laptop-5` expires 2026-11-13, before any slot. | Section F's L-106 guidance drives a live go/no-go decision and is two sessions old; the precondition check would look like an unexpected deploy. | Append one dated note with the 11-11 state: revisions and build, hardening deployed, L-106's latest status, the owner invite's label and expiry. | S | Required |

### Blocks submission

| ID | Area | Severity | Verified / Plausible | Where | What's wrong | Why it matters | Suggested fix (one line) | Size | Required or portfolio |
|---|---|---|---|---|---|---|---|---|---|
| F-05 | 1 | Blocks submission | Verified | `README.md:15-27` | The Status section ("Updated 2026-10-18") says Sprint 6 runs 10-15 to 10-25 with the buffer from 10-26, and that FR-03 "failed two pre-registered gates". ADR-113 closed Sprint 6 on 10-18 (buffer from 10-19); `deploy/RUNBOOK_DEMO.md:358` says three attempts failed. Nothing on `route_v6` as the default, Sprint 6.5, the results page, or L-106. | The README is the front page of the 12-05 packet and contradicts the evaluation report and the demo's own Q&A. | Refresh the Status paragraph to the current build and calendar, with a new "Updated" date. | S | Required |
| F-06 | 1 | Blocks submission | Verified | `docs/architecture.md:103` | It says "the default routing prompt is still `route_v3`, which best-fit routes such questions". `route_v6` has been the default since ADR-116 (`services/orchestrator/src/orchestrator/routing.py:26`) and deployed since 10-28. No dated note on the line. | `architecture.md` is the current "what"; it contradicts the deployed system on the headline unmet requirement. | Add a dated note at line 103: `route_v6` is the default and FR-03 stays unmet. | S | Required |
| F-07 | 1 | Blocks submission | Verified | `docs/evaluation-report.md:198, 355, 394` and the change table at `:383-388` against the header notes at `:12, :14` | The body does not carry what the report's own header notes record. §4.6 says "every reading stayed inside the 120 s ceiling" and §10 "at most 61.2 s", with no mention of the failed cold starts of 10-30 (L-106) or the 11-11 result. `:355` says the L-105 pin is "to be fixed before Window B" (fixed and deployed 10-30). The change table stops at the 10-28 build. The body statements are scoped to their dates, so they are stale, not false. | The final pass is due 12-01 and no checklist of what it must pick up was found. | In the final pass, bring §4.6, §8 and §10 up to builds `9599bae` and `8ec22db`, L-105 fixed, and L-106's status. | M | Required |
| F-08 | 1 | Blocks submission (if the packet includes these copies) | Plausible: the file states are verified; whether the packet draws on them is the owner's to say | `docs/academic/06-production-support.md:8` (an 8-line file); `docs/academic/05-test-scenarios.md` (last commit `a158faa`, 2026-10-15); `docs/sprint-log.md:1264-1265` | The repository copy of the production-support document is a stub marked "Assignment incomplete", though the sprint log records it submitted 10-28. The test-scenarios copy predates its 10-22 submission. Owner's files: flagged only. | If the documentation packet draws on this folder, it holds a stub and a pre-submission draft. | Owner commits the submitted versions of both files. | S | Required |

### Correctness bug

| ID | Area | Severity | Verified / Plausible | Where | What's wrong | Why it matters | Suggested fix (one line) | Size | Required or portfolio |
|---|---|---|---|---|---|---|---|---|---|
| F-09 | 6 | Correctness bug (runbook) | Verified | `deploy/RUNBOOK_GRADING.md:92`; `deploy/RUNBOOK_DEMO.md:433`; `RUNBOOK_GRADING.md:23` | The close-the-window retry-log read uses `--freshness 7d`. Window B is 12 days (12-01 to 12-12), closed 12-13, so about 12-01 to 12-05 is never read. | "No output means no retry happened" would be recorded for days the read did not cover, including the expected grading day (about 12-05). | Add a dated note setting the freshness to the window's length plus a day (for example `14d`). | S | Required |
| F-10 | 3 | Correctness bug (process) | Verified | `gh api repos/{owner}/{repo}/branches/main/protection` → `404 Branch not protected`; `…/rulesets` → `[]`; `deploy/trigger_full.yaml:31-32`; `.github/workflows/ci.yml` | `main` has no branch protection and no rulesets. The deploy trigger fires on a push to `main` and the pipeline runs no tests. When the trigger is enabled for a deploy window, a red-CI merge or direct push deploys. No record covers it (a search of every `*.md` for branch protection, required checks and rulesets found nothing). Today the trigger is disabled and the last five CI runs on `main` are green. | Only owner discipline stops a broken commit reaching the demo deployment. | Require the lint, unit and integration checks on `main` with a branch protection rule. | S | Required (cheap) |
| F-11 | 3 | Correctness bug (test) | Verified | `tests/unit/test_results_data.py:57` | The assertion ends in `or True`, so it can never fail. | The file-ending and encoding check on `web/data/results.json` is not made. | Remove `or True`. | S | Required (trivial) |
| F-12 | 2 | Correctness bug (edge) | Verified | `services/api_gateway/src/api_gateway/upstream.py:91, 95-97`; `docs/data-dictionary.md:511, 513` | A non-JSON upstream reply raises in `resp.json()`, is caught by `except Exception`, and becomes `OrchestratorUnavailable` (503, "temporarily unavailable"). That covers an unhandled orchestrator 500 and Cloud Run's own HTML error pages. Rule 5 reserves that sentence for "orchestrator unreachable" and says any other status is 502 `upstream_error`. | An orchestrator crash is shown and logged as "unreachable" (`orchestrator call failed`, `JSONDecodeError`), which misleads diagnosis in a live session. All JSON error codes map correctly. | Treat a non-JSON body as `(status, {})` so it takes the `upstream_error` path, or record the behaviour in rule 5. | S | Portfolio |
| F-13 | 2 | Correctness bug (latent: needs `QA_INTERP_MODE=enforce`; deployed is `advisory`) | Verified by reading (`app.py:548, 798-801, 816`; `degraded.py:54-63, 96-97`; `interpret.py:22`); not executed | `services/orchestrator/src/orchestrator/app.py:798-801, 816`; `degraded.py:61-62, 96-97` | Attempt 1 fails interpretation, so `state.qa_failed` is set. If attempt 2's QA hop then hits the deadline, the cost cap or an outage, `best_answer` is attached and `answer_for` appends "Not verified: …", while `qa_status_for` returns `failed`. The gateway then says "the answer failed verification and is not shown" above a shown answer. | Status and text contradict each other. It can't happen in the deployed advisory mode, where the re-ask loop never fires. | Don't attach `best_answer` when `state.qa_failed`, or return `not_checked` for the second attempt. | S | Portfolio (latent) |

### Records hygiene

| ID | Area | Severity | Verified / Plausible | Where | What's wrong | Why it matters | Suggested fix (one line) | Size | Required or portfolio |
|---|---|---|---|---|---|---|---|---|---|
| F-14 | 1, 4, 6 | Records hygiene | Verified | `deploy/RUNBOOK_GRADING.md:3-4, 8-13, 45, 47, 52, 75, 103`; `scripts/invites.py:127-128`; `deploy/cloudrun/*.yaml` (`LLM_MODE: paid`) | The grading runbook is still written for Window A, which was never opened (ADR-118); the file last changed 10-16. `$end` defaults to `2026-11-09`, which gives a negative `--days` that `invites.py` refuses (it fails safe). The label is hard-coded `grader-A`; step 4 names `owner-laptop` "created 2026-10-13"; the banner warns the YAMLs "still say `LLM_MODE: free`" (all five say `paid`); line 103 says "15 … until Z2b deploys" (30 is deployed). | It is the runbook for opening Window B on 12-01 and for the demo's day-before step. | Append a dated "Window B" note: `$end`, label `grader-B`, current owner label, banner satisfied, cap line current. | S | Required |
| F-15 | 1 | Records hygiene | Verified | `docs/architecture.md:283, 384, 398` (file last changed 10-29) | No note after 10-28. `:283` still lists the L-105 pin as an open limit (fixed and deployed 10-30). `:384` says the 6.5 deploy window is "after Window A (about 11-10 onward)" (it ran 10-28; Window A was not opened). `:398`'s Buffer row says "presentation plus the completed project (ADR-044)" (replaced by ADR-117 and ADR-119). ADR-120, ADR-121 and L-106 are absent. | These are the places a grader checks deploy state and calendar. | Append one dated note per affected line. | M | Required for 283 and 384; the rest portfolio |
| F-16 | 1 | Records hygiene | Verified (ten declaring lines against eleven index rows) | `docs/decisions-log.md` index rows `:62` (048), `:69` (055), `:76` (062), `:92` (078), `:95` (081), `:96` (082), `:102` (088), `:107` (093), `:109` (095), `:117` (103), `:131` (117); declaring lines `:2568, :2587, :2734, :2789, :2987, :3091, :3192, :3271, :3474, :3548, :4128` | Eleven index rows don't show a partial supersession that a later entry declares: 078 by 084; 081 by 085; 055 by 088; 088 by 089; 082 by 093; 095 by 096; 062 by 098 and 100; 048 and 103 by 104; 093 by 106; 117 by 119. | The same drift class found by accident this month; the index is how a reader learns what still holds. | Fix the eleven Status cells to "Accepted — superseded in part by ADR-NNN" (index rows only). | S | Required (cheap) |
| F-17 | 1 | Records hygiene | Verified | `docs/decisions-log.md:89` | ADR-075's Status cell says "Accepted; not in effect … FR-03 open until Sprint 5 (L-58)". Sprint 5's gate also failed (ADR-101), the last attempt was a no-go (ADR-114), and ADR-116 put ADR-075's behaviour into effect through `route_v6`. | The cell says "not in effect" for behaviour that is deployed, and names a past deadline. | Update the index Status cell to the ADR-114 and ADR-116 outcome. | S | Required (cheap) |
| F-18 | 1 | Records hygiene | Verified | `docs/risk-register.md:32, 313` against `:436-442` | R-14 is Closed in the summary table and in its 2026-10-14 update, but the "Closed / Realized Risks" list holds only R-06, R-03, R-15 and R-19. | The closing list feeds the lessons-learned section and is one short. | Append an R-14 line to the list. | S | Required (cheap) |
| F-19 | 1 | Records hygiene | Verified for R-09 and R-21; R-10's wording not re-read by the lead | `docs/risk-register.md:220` (R-09), `:432` (R-21), `:243` (R-10); `docs/sprint-log.md:1264-1265`; `docs/deploy-window-log.md:726` | Three risks' latest notes are overtaken. R-09 says the two later assignments are "held, not submitted" (the sprint log records them submitted 10-22 and 10-28) and stays Monitoring. R-21 says the next balance check is "before the 6.5 deploy window" (four sessions have run since). R-10 still carries the superseded presentation dates. No boundary review after 10-18. | R-09's review condition looks met; R-21 governs Window B. | Append dated notes to R-09, R-21 and R-10, deciding R-09's status. | S | Required |
| F-20 | 3 | Records hygiene | Verified (doc lines); the CI count is the subagent's read of run `43099988944` | `docs/evaluation-report.md:340`; `docs/production-grade-audit.md:21`; `docs/architecture.md:281` | All three say CI is green with "2722 unit" passed (at `fa2c7cd`, 10-16). CI at `0bab705` shows 3068 passed, 3 skipped; locally 1598 + 1471 = 3069 passed, 2 skipped. Integration is unchanged at 1096 / 31. | The evaluation report is graded, and the results page tags the production-grade figure "current". | Refresh the row with the current commit and counts at the final pass. | S | Required |
| F-21 | 3 | Records hygiene | Plausible: the pins are verified; that the final pass will change these figures is a forecast | `tests/unit/test_results_data.py:165, 168`; `scripts/build_results_data.py:51` | The test pins figure strings from the evaluation report, including `"cost_gcp": "$8.79"` (a quote for 10-01 to 10-28) and `"production_grade": "11 of 12"`. Intended, but the 12-01 final pass breaks CI unless the report, the script, `results.json` and the test change together. The GCP cost predates four later deploy sessions. | In the path of the graded final pass. | Plan the final pass as one PR that updates all four. | M | Required |
| F-22 | 3 | Records hygiene | Verified | `tests/live/test_llm_roles_live.py:77-79` | Permanent skip: "no QA call exists until the Sprint 4 QA agent; add its smoke test then". The QA agent exists. | Stale placeholder; the QA role has no live smoke test in this file. | Add the QA smoke test or delete the placeholder. | S | Portfolio |
| F-23 | 3 | Records hygiene | Verified (README) | `README.md:276`; `.github/workflows/ci.yml:138-144` | CI is described as lint, unit, integration. There is a fourth job, `ui-build` (pull requests only). The owner's project-instructions file has the same gap in its CI paragraph (flag only). | Minor drift in a description a grader may read. | Add `ui-build` (PRs only) to the description. | S | Portfolio |
| F-24 | 2 | Records hygiene (user-visible) | Verified | `docs/data-dictionary.md:472`; `services/api_gateway/src/api_gateway/interpret.py:38, 93, 96` | For `metric: unsupported` the spec says the Measure part reads "not recognised"; the code prints "Measure: measure not recognised". No test covers the string. | An unsupported-metric decline in the demonstration shows a doubled word in the "Interpreted as" line. | Change the `METRICS["unsupported"]` value to "not recognised" and add a test, or amend rule 2 with a dated note. | S | Required (small; visible in the demo) |
| F-25 | 2 | Records hygiene | Plausible: the spec table order and the code order are verified; the pinning test line was not opened | `docs/data-dictionary.md:467, 474-478`; `interpret.py:133-141` | The spec says the parts appear "in this order": Area, Measure, Period, Horizon, Region, Slice. The forecast line is built Area, Measure, Slice, Period, Horizon, History. | The spec and the tested behaviour disagree on a line every forecast answer shows. | Add a dated §6 note stating the forecast order as built. | S | Portfolio |
| F-26 | 2 | Records hygiene | Verified for `config.py:3-8, 61`; the other three comments not opened | `services/orchestrator/src/orchestrator/config.py:3-8`; `app.py:125, 131, 560`; `result.py:115`; `services/api_gateway/src/api_gateway/app.py:5` | Stale in-code statements: the config docstring gives "30 + 60 = 90 s" and "30 + 85 = 115 s worst case" and omits the 50 s QA hop (165 s, bounded only by the deadline clamp); "PROVISIONAL … decided in Sprint 5" on the request shape; "only the reporting agent is routed to today"; the gateway's public-route list omits `/health`. | The repository is graded, and a reader of `config.py` gets a wrong worst case. | Update the four comments. | S | Portfolio |
| F-27 | 5 | Records hygiene | Verified | `docs/security-model.md:200`; `docker-compose.yml:334`; `tests/unit/test_compose_isolation.py:113, 209` | The row says only the orchestrator, QA and Postgres publish a port; the gateway publishes one too (loopback). It cites a test `…_and_no_models_folder` that no longer exists (now `…_and_no_volumes`). | A grader checking the named evidence finds a missing test and a fourth published port. | Add a dated note under the table naming the gateway port and the renamed test. | S | Required (packet accuracy) |
| F-28 | 5 | Records hygiene | Verified | `docs/security-model.md:156, 222`; `services/mcp_incidents/src/mcp_incidents/server.py` (seven `@server.tool`); `git ls-files` (twelve prompt files) | `:156` says `mcp_incidents` has six tools; it has seven. `:222` says "all ten prompt files (`route_v1` to `route_v5`, `parse_v1` to `parse_v3` …)"; there are twelve, and the active `route_v6` and `parse_v4` are not named. | The control holds, but the counts are wrong for the serving build. | Add a dated note with the current counts and active prompt versions. | S | Required (packet accuracy) |
| F-29 | 5 | Records hygiene | Verified | `docs/security-model.md:206-207`; `gcloud run services get-iam-policy ops-orchestrator` → `roles/run.invoker`: `build-deploy@…` and `run-gateway@…` | The model says each service's only invoker is its caller's account and the invokers "match ADR-099". The orchestrator has two: the gateway's account and the build account. ADR-085 records why, but these rows state the opposite. | The build account can call `/ask` without an invite, bypassing the gateway's hourly and daily caps; the security model should say so. | Add a dated note naming the build account as the orchestrator's second invoker and why (ADR-085). | S | Required (packet accuracy) |
| F-30 | 5 | Records hygiene | Verified | `docs/security-model.md:265`; `tests/unit/test_offline_roles_isolation.py:27, 40-45` | The row claims the generator, training, evaluation and admin credentials are never in a deployed file, citing one test. That test matches only `DB_ROLE_(EVAL|TRAIN)_` and scans compose files, Dockerfiles and `services/`, not generator or admin variables and not `deploy/cloudrun/*.yaml` or `deploy/cloudbuild.yaml`. | The claim holds on the deployed system (subagent check), but the cited evidence proves half of it. | Widen the test's pattern and file set, or reword the evidence cell. | S | Required for the wording; the wider test is portfolio |
| F-31 | 5 | Records hygiene | Plausible: L-61's text is verified; the secret accessor bindings are the subagent's read and were not rerun; access was inferred from IAM, not tested | `docs/evaluation-report.md:1116-1118` (L-61); `docs/security-model.md:275` | L-61 records that an agent and its sidecar share one service account "including its Cloud SQL network permission". It doesn't record that the same account can read both model keys and the database password through the Secret Manager API, so "the agent container holds no database credentials" is true of mounts only. | The separation between agent and sidecar is by mount, not by identity; a reader would assume more. | Append a dated note to L-61 saying the shared account can also read both containers' secrets. | S | Required (accuracy of an accepted limitation) |

### Nice to have

| ID | Area | Severity | Verified / Plausible | Where | What's wrong | Why it matters | Suggested fix (one line) | Size | Required or portfolio |
|---|---|---|---|---|---|---|---|---|---|
| F-32 | 3 | Nice to have | Verified | `.github/workflows/ci.yml:139` | `ui-build` runs only on `pull_request`, never on a push to `main`. It matches ADR-117 as written, but with F-10 a direct push changing `web/` gets no UI build before Cloud Build. | Safe only if every change goes through a PR, which nothing enforces. | Enforce PRs via F-10, or drop the `if:`. | S | Portfolio |
| F-33 | 3 | Nice to have | Verified | `tests/unit/test_results_data.py:63-74` | The test is named "the ten figure groups" and asserts nine. | Either the name or the set is wrong. | Reconcile the name with the set. | S | Portfolio |
| F-34 | 3 | Nice to have | Verified | `services/mcp_volume/tests/test_mcp_volume.py:224, 242`; `tests/unit/test_qa_forecast_equivalence.py:80`; `tests/integration/test_golden_oracles.py:93`; `git ls-files models` (six `volume_v2` files tracked) | Skip reasons say the `volume_v2` files are git-ignored or not in git. They are tracked. | The guards can't trigger in a clean checkout and the reasons are false. | Remove the guards or correct the reason. | S | Portfolio |
| F-35 | 3 | Nice to have | Plausible: the skip lines and `ci.yml:144` are verified; the Dockerfile line was not opened | `services/api_gateway/tests/test_ui_pages.py:138`; `test_gateway_security.py:114`; `ci.yml:144` | The two "real export" tests always skip in CI because no job produces `web/out`; `ui-build` stops at `--target ui`, so the CSP hashing step first runs in Cloud Build at deploy time. | It fails closed, but late. | Build `--target build` in `ui-build`. | S | Portfolio |
| F-36 | 3 | Nice to have | Verified | `.github/workflows/ci.yml:23, 24, 27` | Actions are pinned by floating major tag (`@v4`, `@v5`, `@v6`); no record covers it, while Cloud Build step images are digest-pinned (ADR-121). | Same class of risk as L-107, in CI only; it can't reach a deploy. | Record it as accepted, or pin by commit SHA. | S | Portfolio |
| F-37 | 4 | Nice to have | Verified | `deploy/RUNBOOK_V.md:289, 365`; `gcloud builds list --limit 3` (SUCCESS `8b6493d8`, FAILURE `51b9dc00`, SUCCESS `6f8abad0`) | `EXPECTED_IMAGE_TAG` and `$sha` come from `builds list --limit 1`, whatever the build's status. | After a failed build (the state from 11-10 to 11-11), `verify.py` compares against a commit that never deployed and reports false FAILs. It is correct today. | Add `--filter "status=SUCCESS"` to both. | S | Required (small) |
| F-38 | 4 | Nice to have | Verified on the gateway and orchestrator; the other four are the subagent's read | `gcloud run services describe ops-gateway` / `ops-orchestrator --format "yaml(metadata.annotations,spec.template.metadata.labels)"` | Deployed but in no repo YAML: a service-level `run.googleapis.com/maxScale: '20'` annotation, and a `client.knative.dev/nonce` template label on five services (not the gateway). | No functional effect (the revision-level maximums match), but "the whole definition replaces the template" is not literally true. | Record it in a dated note; no config change. | S | Portfolio |
| F-39 | 6 | Nice to have | Verified | `deploy/RUNBOOK_DEMO.md:132-139, 387, 418`; `RUNBOOK_GRADING.md:60` | The demo-day cap table (21 of 50) omits three questions prescribed elsewhere (the idle-gap reporting question, the smoke check, the recovery smoke check): 24 of 50. No step says how to read the cap's remaining headroom. | Still well under 50; the gap is that same-day grader use can't be seen in advance. | Add the three rows and a log-count headroom check. | S | Portfolio |
| F-40 | 1 | Nice to have | Verified (spacing on rows 58, 115, 127); the superseding-side inconsistency not re-read | `docs/decisions-log.md:58, 115, 127` | Three Status cells read "Accepted— superseded" with no space, and the superseding ADRs are inconsistent about showing "supersedes … in part" in their own cell. | Cosmetic. | Normalise the spacing; pick one convention. | S | Portfolio |
| F-41 | 1 | Nice to have | Verified | `docs/sprint-log.md:1397-1407` | The Cumulative Summary ends at Sprint 6; Sprint 6.5's work is recorded only as dated notes under Sprint 6. | The table is meant as the fast look-back for the report and the demo. | Append a 6.5 row at the 6.5 close. | S | Portfolio |
| F-42 | 2 | Nice to have | Verified (`app.py:595-603, 632-648`; single call site of `_llm_error` at `:599`) | `services/orchestrator/src/orchestrator/app.py:233-274, 595-603, 647-648` | `_llm_error`'s rate-limited, quota and outage branches are unreachable since ADR-089 (those errors now raise `DegradedResult` at `:600-603`). The "reporting is also the fallback for a route the table does not name" line is unreachable too: all six routes are handled above it. | Dead code reads as if routing can still return 429/503, and the fallback is a force-route no ADR describes. | Delete the dead branches; replace the fallback with an explicit error. | S | Portfolio |
| F-43 | 5 | Nice to have | Verified from the migrations only (the database is stopped) | `docs/security-model.md:13-14`; `data/migrations/versions/20260920_1215-7d54e0c9a318_roles_and_grants.py:238, 240`; `20261001_1200-95a2f308a9cd_offline_read_roles.py:192-193` | "The Postgres `PUBLIC` defaults are revoked" is broader than the migrations, which revoke `CONNECT` on the database and `ALL` on schema `public`. Postgres also grants `TEMPORARY` to `PUBLIC` by default; that is not revoked, so the read-only roles can create temporary tables. | No data exposure, but "defaults revoked" is slightly overstated. | Reword to name the two revokes, or add a forward migration revoking `TEMPORARY`. | S | Portfolio |

## 3. Per area: what was checked

### Area 1: records consistency

- **ADR index against entries (exhaustive):** 121 index rows and 121 headings, 001 to 121, none missing or duplicated; titles compared for all 121, no substantive mismatch. Every "supersedes" statement compared with the target's Status cell: F-16, F-17, F-40.
- **Risk register:** all 21 summary rows agree with each entry's latest status: F-18, F-19.
- **Limitations log:** 107 headings cross-checked by pattern; L-106 (open) and L-107 (resolved) match their latest notes. Nothing found. Depth limit noted in section 1.
- **Repeated figures:** revision names, build and commit hashes, window dates, prepaid balances ($6.21, $6.19, $6.18, $6.15 by date), caps and timeouts, the traceability count table. Nothing found beyond F-05 to F-07, F-15 and F-20.
- **Line references:** the runbooks, README, architecture, security model and traceability contain no `file:NN` references. About 85 in the audit, evaluation report, sprint log, decisions log and window log were resolved; several have drifted, all inside dated entries that were true when written. Nothing reported.
- **Calendar and deadlines:** the course dates agree everywhere. Disagreements are F-05, F-14, F-15.

### Area 2: code against the spec

Every named value matches its ADR in code defaults, in `deploy/cloudrun/*.yaml`, and in the live revisions read (subagent comparison; the lead re-read the files cited in F-12, F-13, F-24 to F-26 and F-42):

- Per-hop timeouts 60 / 85 / 60 s, QA hop 50 s (`orchestrator/config.py:53-61`): match.
- 120 s ceiling, reserve, clamp and propagation (ADR-034, ADR-088): match.
- Breaker (3 failures, 30 s, one trial), cost cap 0.02, QA retry bound 2: match.
- Gateway caps (30 an hour per invite, 50 a day Pacific, body and question limits): match.
- Liveness and readiness handlers (ADR-120): match.
- Log redaction (ADR-108): match.
- Routing default `route_v6` against `evals/freeze_s5.json` (`route_v3`): a recorded divergence (ADR-116), not a finding.
- Error codes traced from the orchestrator and agents to the gateway table: all map, except non-JSON bodies (F-12).
- Unit suite and ruff clean.

### Area 3: tests and CI

- `uv run --locked pytest tests/unit -q -rs`: `1598 passed, 1 skipped`.
- `uv run --locked pytest services -q -rs`: `1471 passed, 1 skipped`.
- `ruff check`: `All checks passed!`; `ruff format --check`: `425 files already formatted`; ruff 0.16.8.
- **Skips:** `tests/unit/test_mcp_feedback_image.py:90` (opt-in `RUN_DOCKER_BUILD`; valid). `services/api_gateway/tests/test_ui_pages.py:138` (no built UI export; a valid condition that CI can never satisfy, F-35).
- **Critical paths, all covered** (subagent read; not re-read by the lead): degraded path and breaker opening (`services/orchestrator/tests/test_resilience.py`, `tests/unit/test_circuit_breaker.py`, `tests/unit/test_llm_breaker.py`); cost cap (`test_resilience.py`, `tests/unit/test_request_cost.py`); deadline clamp (`tests/unit/test_deadline.py`); invite expiry (`services/api_gateway/tests/test_gateway_auth.py`).
- **Frozen literals and time-bombs:** only F-21 beyond the known one. No test pins the deployed commit, an ADR count or a live revision name; no calendar time-bomb.
- **CI:** lint, unit and integration run on every push and on PRs to `main`; `ui-build` on PRs only; no `continue-on-error`, no path filters; `REQUIRE_INTEGRATION_DB=1`.

### Area 4: deployed configuration

- **Six services against `deploy/cloudrun/*.yaml`:** image tag, probes, startup boost, min and max instances, concurrency, timeout, env, secret names, Cloud SQL annotation, service account, ingress. No functional difference. `cpu-throttling: 'false'` is deployed and not in the repo, already recorded (ADR-120).
- **Trigger against `deploy/trigger_full.yaml`:** every field matches; disabled.
- **Pipeline step images against ADR-121:** all three pins match the build's steps.
- **Runbook commands against script arguments and gcloud flags:** all match except F-02; F-37.

### Area 5: security model

Holds (subagent checks; the lead re-ran the orchestrator invoker read and re-read the cited files):

- The access matrix against the net effect of all nine migrations, all seven roles by thirteen tables.
- One role's credential per MCP server; QA holds only its own role.
- `allUsers` on the gateway only; each service runs as its own account; ingress `all` with IAM as the boundary.
- The paid key readable by the five model-calling accounts only; the gateway's secrets by the gateway only.
- ADR-108: no question text, token or exception message in any log call read; 47 gateway request-log entries in 7 days with no query string or token-like text.
- No real credential literal in tracked files.

Does not hold: F-27 to F-31, F-43.

Observation, not a finding: the repository is public and `docs/deploy-window-log.md` lists invite ids and labels of revoked or expired invites. That follows the grading runbook's own rule ("ids and labels only; never a link or a token").

### Area 6: demo and grading readiness

- **Runbooks read end to end:** F-01 to F-04, F-09, F-14, F-39.
- **Rule 9 example questions (all seven):** wording identical across the data dictionary, the UI and the demo runbook; no caption contradicts the code (subagent read).
- **`gemini-3.5-flash-lite` deprecation:** https://ai.google.dev/gemini-api/docs/deprecations now answers 301 to https://aistudio.google.com/docs/deprecations. Read 2026-11-11 through the fetch tool: release "July 21, 2026", shutdown "No shutdown date announced". This agrees with L-104 and R-15, but the tool summarises, so the owner should read the raw row once (F-01).
- **Daily cap:** 50, the code default (`gateway.yaml` does not set it), reset by Pacific day; per invite 30 an hour. Demo day is 24 of 50 with the omitted items; a same-day rehearsal makes 31. Model calls: about 68 typical for 24 questions, 168 at worst. No paid-tier daily limit is recorded anywhere.
- **Invite expiry:** an invite made per the runbook with the Window B `$end` is valid through 12-12 (subagent read of `invites.py`).

## 4. Dropped candidates

- **"The demo runbook has no date and assumes Window B" (Area 1, as Blocks demo):** recorded in the runbook itself as `[TBD]` with the rule for a slot outside the window. Kept as the note in section 1, not a finding.
- **"Deprecations page: not completed" (Area 6):** superseded; the lead read the redirected page.
- **Three duplicates merged:** the `verify.py` environment gap (Areas 4 and 6 → F-02), the stale demo runbook (Areas 1, 4 and 6 → F-04), the Window A grading runbook (Areas 1, 4 and 6 → F-14; Area 1 rated it Blocks submission, lowered because the default fails safe and the demo runbook already gives the Window B `$end`).
- **`architecture.md:255` ("`ops-db` stopped outside grading windows only"):** the sentence is still broadly true; dropped from F-15.
- **`RUNBOOK_V.md:207` ("no `traffic` block")** and old revision names in `RUNBOOK_V.md`: corrected by the file's own dated notes.
- **`evals/freeze_s5.json` naming `route_v3`:** the recorded frozen system (ADR-116).
- **A hop cut short by the deadline counting against a breaker:** as specified by ADR-088.
- **The 31 integration skips in CI:** known (L-78).
- **Drifted `file:NN` references inside dated entries:** true when written; append-only.

## 5. Commands run (purpose)

By the lead:

- `gcloud run services list`; `gcloud run services describe ops-gateway|ops-orchestrator --format "yaml(...)"`: revisions, annotations, labels.
- `gcloud run services get-iam-policy ops-orchestrator`: invoker bindings (F-29).
- `gcloud sql instances describe ops-db --format "value(state,settings.activationPolicy)"`: database state.
- `gcloud builds triggers describe deploy-reporting-slice --format "value(disabled)"`; `gcloud builds list --limit 3`: trigger and builds.
- `curl -s -o /dev/null -w …` on the deprecations URL (status line only); one fetch of the redirected Google page.
- `gh api …/branches/main/protection`, `…/rulesets`; `gh run list --branch main --limit 5`.
- `git status --short`, `git log -1 -- <file>`, `git ls-files`, `git check-ignore`, `git rev-parse`.
- File reads and searches of every cited file.

By the subagents (all read-only), in addition to the above kinds:

- `uv run --locked pytest tests/unit -q -rs`, `uv run --locked ruff check`, `ruff format --check`.
- `gcloud run services describe` (all six, export), `run revisions list`, `builds describe`, `container images describe`, `gcloud logging read` (gateway, limit 50, 7 days; field names and shapes only), `--help` on eight gcloud commands.
- `gh run view … --json jobs` and `--log` (summary lines).

**Outside the literal allowed list, disclosed:**

- Area 3 also ran `uv run --locked pytest services -q -rs` (offline; the repo's documented offline suite).
- Area 5 ran `gcloud projects get-iam-policy`, `gcloud secrets list` and `secrets get-iam-policy` (names and bindings only; no secret value), and `gcloud iam service-accounts list` / `get-iam-policy`. The lead's brief allowed these as the "read-only `get-iam-policy`" the area asks for; `secrets list` and `service-accounts list` go a step beyond that.
- Area 1 used inline Python scripts that print to stdout only.
- The lead's fetch of `aistudio.google.com/docs/deprecations` (Google's own page, reached by the redirect).

No `verify.py` or `invites.py` run, no `run.app` request, no model call, no state-changing `gcloud`, no token command. No `.env`, `evals/golden/` or `.local\` file other than this report was opened.
