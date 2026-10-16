# Deploy window log (ADR-045, ADR-078, ADR-081, ADR-084)

> **Updated 2026-10-14:** this log now covers two deploy windows: 2026-10-08 to 10-10 (the reporting slice) and 2026-10-12 to 10-13 (the full system and the paid-key switch). The header paragraph below describes the first window; its stop rule was that window's. Grading windows (ADR-107) are recorded at the end of this file as they happen.

Project `a2a-agentic-service-ops-gcp`, region `us-central1`. Window 2026-10-08 to 2026-10-10;
the stop rule falls at the end of 2026-10-10. Evidence for `06` and the R-03 and R-14
updates. No secrets, and no values that could be secrets, appear here. Times are local
(CDT).

## 2026-10-08

### Phase 0 (earlier the same day)
- Active gcloud configuration `a2a-deploy`; Application Default Credentials work and use the
  project as quota project. All seven APIs were already enabled. Artifact Registry repo
  `agentic-service-ops` (Docker, us-central1). No Cloud SQL instance and no Cloud Run service.
- The default compute service account holds `roles/editor`. Nothing here runs as it.
- Service accounts `run-orchestrator`, `run-reporting`, `build-deploy`, `probe-noauth` created
  with no bindings. Fix PR #29 (labels, account-name defaults, secrets list) merged.
- Cloud Build 2nd gen connection `GitHub-CloudBuild-A2A` (us-central1), repository resource
  `EricSerrano1111-agentic-service-ops`.

### Phase 1: Cloud SQL, schema, data, grants
| Time | Step | Result |
|---|---|---|
| 15:33 | Start check: PR #29 on `main`, no instance, no service | pass |
| 15:33 to 15:43 | `gcloud sql instances create ops-db`: PostgreSQL 16, Enterprise, `db-f1-micro`, 10 GB SSD, zonal, public IP, no authorized networks, storage auto-increase off, automated backups off (README is silent; the data is synthetic and reloadable) | created in 9 m 42 s |
| 15:44 | Labels `app=agentic-service-ops`, `component=deploy` | `gcloud sql` has no label flag; set through the Admin API (`settings.userLabels`) |
| 15:45 | Eight secrets created from freshly generated passwords (admin and seven role passwords), piped into Secret Manager; admin password set on the instance from its secret; database `service_ops` created | pass |
| 15:47 | Auth Proxy on 127.0.0.1:5433; the local compose stack was already stopped (R-17) | up |
| 15:48 | `alembic upgrade head` as `postgres` through the proxy | **all 9 migrations ran unchanged on the first attempt, 27 s** |
| 15:49 | `alembic check` | no new upgrade operations |
| 15:49 | `load.py` as `app_generator` | 13 tables, committed, 31 s; row counts as the repo expects (accounts 50, locations 197, service_requests 20230, archived_requests 18063, incidents 2067, service_feedback 7521, sentiment_labels 7521, generation_parameters 140) |
| 15:49 | `validate.py` (reads as `app_forecast` and `app_eval`) | **67 pass, 0 fail**; report in `data/generator/validation/2026-10-08/` |
| 15:50 | Dataset identity vs the committed 2026-10-01 report | `corpus_sha256`, `master_seed` and `rows` identical |
| 15:50 to 15:52 | Integration suite, first run | 66 failed, 816 passed: `FATAL: remaining connection slots are reserved`. The instance default is `max_connections=25`, and the MCP figures tests build many engines whose pools are not disposed (fine against local Postgres, which allows 100). Not a grants failure. |
| 15:59 | `max_connections=60` set as a database flag (one restart, 38 s) | applied |
| 16:00 to 16:04 | Integration suite, second run, `REQUIRE_INTEGRATION_DB=1` | **882 passed, 1 skipped, 0 failed** (3 m 50 s). The skip is `test_golden_oracles`, which needs stored `bert_v1` predictions; the load truncates them and CI's database holds none either. Locally it runs because the local database holds them. |

R-14 so far: nothing in the roles migration, the `REVOKE`s or the column grants failed on
`cloudsqlsuperuser`. The only difference Cloud SQL showed was the connection limit.

### Phase 2: secrets, IAM, trigger, first deploy
| Time | Step | Result |
|---|---|---|
| ~16:05 | `gemini-api-key` created from the local free key | SHA-256 of the secret equals the free key's and differs from the paid key's |
| ~16:05 | IAM bindings: `secretAccessor` per secret (`gemini-api-key` to both runtime accounts; `db-role-reporting-password` to `run-reporting`); `cloudsql.client` (project) to `run-reporting`; build account `run.developer`, `logging.logWriter`, `cloudsql.viewer` (project), `artifactregistry.writer` (on the repo), `serviceAccountUser` on the two runtime accounts, `serviceAccountTokenCreator` on `probe-noauth`; owner `serviceAccountTokenCreator` on `probe-noauth` | all 12 created |
| 16:06 | Trigger `deploy-reporting-slice` in us-central1 (push to `main`, included files as the README, running as `build-deploy`; `_RUN_VERIFY` not set) | created |
| 16:06 | First deploy: trigger run with `_RUN_VERIFY=false`, commit `8880641` | build 34187d04: images built, pushed and definitions rendered (steps 1 to 5 passed); **`deploy-reporting` failed after 2 min** |

**Failure 1 (first deploy).** The v2 `CreateService` call returned `INVALID_ARGUMENT:
service.name must be empty on CreateServiceRequest`. Found in the Cloud Run Admin Activity
audit log (build step output was not visible in Cloud Logging). Cause: `deploy_service.py`
sent the definition's `name` on create. Both rendered definitions were then dry-run with
`validateOnly=true`: both valid once `name` is omitted. Fix PR #30 (`fix/deploy-create-name`,
with a test), awaiting the owner's merge. No service was created.

Note for `06`: this is a defect in a deploy script that had never run against GCP, found by
the first real run; the dry-run API (`validateOnly`) would have caught it before the window.

### End of this stretch
- Live model calls used: 0 of 8.
- Billed resources: Cloud SQL `ops-db` (stopped for the pause, see below), Secret Manager
  secrets (cents), Artifact Registry images (cents), one failed build.
- 16:20: Cloud cost control: the Auth Proxy was stopped and `ops-db` set to `NEVER` while the
  owner merges #30.

### Resumed 2026-10-08 (after PR #30 merged)
- **`max_connections=60`, and why.** The micro tier defaults to 25 (3 reserved). The integration
  suite's MCP figures tests build one engine per test and never dispose its pool, so a single
  pytest process exhausted the slots (66 failures, all "remaining connection slots"). Raised to
  60 as a database flag, one restart. **Per-process pool finding:** `mcp_incidents` creates one
  SQLAlchemy engine per process (`Backend.from_settings` once at start-up through `create_app`),
  never per request, with `pool_size=2` and `max_overflow=2`: at most 4 connections. The
  reporting service allows at most 2 instances, so at most 8 connections from the deploy
  against 60 (57 usable by non-superusers), with Cloud SQL's own agent using a few. The test
  suite's leak is a test-harness issue, not a runtime one.
- **Build logs.** The first build (34187d04) has no readable step output in Cloud Logging: its
  logs were written before the build account's `logging.logWriter` binding had propagated, or
  were not written. Every later build prints its steps with `gcloud builds log <id> --region
  us-central1 --project ...` (confirmed on 9f0be025 and d2e154c4). No fix needed.
- **PR #31** (follow-up test: create omits `name`, update keeps it, through `main`) opened.
- **Auto-triggered build 9f0be025 (21:22 UTC).** Merging #30 touched `deploy/**`, so the
  trigger fired by design, with verify on. `deploy-reporting` created `ops-reporting`, but
  its revision never became ready: the instance had been **stopped** for the pause, so the
  sidecar's `/readyz` failed 20 times ("database unreachable") and Cloud Run refused the
  revision. This is the readiness probe doing its job (ADR-079): the agent never took traffic.
- **Build 1dd47618 (instance running, `_RUN_VERIFY=false`).** A no-op: same commit, so an
  identical template, and `PATCH` kept the failed revision 00001. The empty service (no ready
  revision, no traffic) was deleted. Lesson: re-running a pipeline on the same commit does not
  re-roll a failed revision; deleting the service was the recovery.
- **Build d2e154c4 (first good deploy, `_RUN_VERIFY=false`, commit `a682a14`).** All eight
  steps passed in 3 min: `ops-reporting-00001-stw` and `ops-orchestrator-00001-fsn`, both
  labelled, each holding 100% of traffic. Images tagged with the commit SHA.
- **Service-level bindings.** `run-orchestrator` invoker on reporting; `build-deploy` invoker
  on the orchestrator. Reporting's policy has exactly one member. No `allUsers` or
  `allAuthenticatedUsers` anywhere.
- **`verify.py` by hand (first run): 7 of 9 lines PASS, 2 FAIL.**
  1. **FAIL "orchestrator refuses an unauthenticated call: HTTP 404".** Cloud Run's front end
     reserves `/healthz` and answers 404 before IAM sees the request. Without a token, `/`,
     `/ask` and `/docs` all give 403 on both services, and the card path gives 403 on
     reporting. The boundary holds; the check probes a path that cannot show it. The fix
     changes a verify.py check, so it was not made here (needs the owner's decision).
  2. **FAIL "orchestrator answers a reporting question end to end: HTTP 502 agent_unavailable".**
     Reporting returned 403 to the orchestrator's Agent Card fetch about 1 minute after the
     invoker binding was created: IAM propagation. A repeat of check 6's request a few
     minutes later returned HTTP 200, outcome `answered`, **54 incidents** (2026-07-01 to
     07-31; 6 high, 12 medium, 36 low), trace `c1bf1996994a4fd68d401dd5b8f38d34`.
  3. PASS: serving revisions (both), reporting refuses the probe account (403), reporting's
     invoker is exactly the orchestrator, both run as their dedicated accounts, Cloud SQL
     `authorizedNetworks` empty.
- **Live model calls used: 3 of 8** (1 routing call in the failed check 6, 2 in the repeat).

### Check 2 replaced, verify passes (2026-10-08, ~16:50)
- PR #32 (`fix/verify-ingress-probe`, owner-approved): without a token, `POST /ask` and `GET /`
  on the orchestrator and `GET /` on reporting must each return 401 or 403; any other status
  fails. `/healthz` stays as an INFO line (HTTP 404: Cloud Run's front end reserves it and
  answers before IAM). Unit tests cover the pass and fail cases.
- `verify.py` run locally with the new check against the live services: **all checks PASS**
  (revisions, three unauthenticated probes all 403, probe account 403, invoker exactly the
  orchestrator, dedicated accounts, end-to-end answered, `authorizedNetworks` empty), exit 0.
  Live calls used: 2 (5 of 8 in total).
- The answer 54 (2026-07-01 to 07-31; 6 high, 12 medium, 36 low) equals fresh SQL as `app_eval`
  through the Auth Proxy (6, 12, 36; total 54). No model call.

### Operating notes (for `06`)
- **The services are unavailable while `ops-db` is stopped.** By design, for cost: min-instances
  0 means any request needs a new instance, and a new `mcp-incidents` instance fails its
  startup probe (`/readyz`: database unreachable) until the database is up. Start the instance
  before any test or demo, stop it at day end.
- **A merge to `main` while `ops-db` is stopped produces a failed revision, and traffic stays on
  the old one.** Seen at build 9f0be025: the new revision never became ready, and Cloud Run
  kept serving the previous revision (here there was none yet, so nothing served). The
  pipeline fails at the deploy step, which is the correct, visible outcome. A rerun on the
  same commit does not re-roll the failed revision.
- **IAM propagation delay.** A new `run.invoker` binding took longer than about one minute to
  take effect: the orchestrator's Agent Card fetch got 403 from reporting about 1 minute after
  the binding was created, and the same request succeeded a few minutes later. After adding a
  binding, wait a few minutes before the first verify run (it cost one live call here).

### Step 8, first attempt: build a5f3e10d (commit `82bfc90`, `_RUN_VERIFY=true`), FAILED at verify
- Merging #32 fired the trigger. Steps 1 to 6 passed: images built and pushed, rendered,
  `ops-reporting` and `ops-orchestrator` **updated** (the first real use of the `PATCH` path),
  3 min 14 s in total.
- The verify step crashed before check 6 made any call (**no live model call used**; still 5
  of 8): `gcloud auth print-identity-token --audiences=...` exits non-zero for the build
  account's own metadata-server credentials. The probe-account impersonation (check 3) did work
  inside Cloud Build. The crash also hid the results of the earlier checks, because results
  print at the end.
- Fix: PR #33 (`fix/verify-ci-identity-token`): the caller's token comes from the metadata
  server when there is one (Cloud Build), else from gcloud (a developer machine); a failed mint
  is now a FAIL line instead of a crash. Awaiting the owner's merge, which re-fires the trigger.
- Lesson for `06`: running `verify.py` on a developer machine does not exercise the pipeline's
  credential path. The pipeline run is the only real test of that path.

### Step 8, second attempt: build 09af1023 (commit `ba4c2ef`, `_RUN_VERIFY=true`), FAILED at check 6 only
- Steps 1 to 7 ran in 3 min 50 s. Deploy steps passed (revisions `ops-orchestrator-00003-phl`
  and `ops-reporting-00003-94x`). The verify step now prints every result: **10 of 11 PASS**,
  including the three unauthenticated probes (403) and the probe-account refusal (403).
- **FAIL: end-to-end question: "could not mint an identity token for the caller: No identity
  token can be obtained from the current credentials."** The metadata-server route added in
  #33 returned nothing inside Cloud Build (its metadata server does not issue identity tokens
  for the build account), and the gcloud route fails for the same credentials. No live call
  was made (still 5 of 8).
- Root cause: inside Cloud Build the only way to get an identity token for the build account
  is to impersonate it, which needs `roles/iam.serviceAccountTokenCreator` for `build-deploy`
  **on itself**. The probe-account impersonation in check 3 works because that binding exists.
- This is an IAM design change (a new binding), so it is the owner's decision, not made here.

### IAM change approved by the owner: `build-deploy` token-creator on itself (2026-10-08, ~17:15)
- **Binding created:** `roles/iam.serviceAccountTokenCreator` for
  `serviceAccount:build-deploy@...` **on the `build-deploy` account itself**, and nothing else.
  It lets the build account mint tokens only as itself.
- **Reason:** inside Cloud Build, check 6 needs an identity token for the build account (it is
  the orchestrator's invoker). Neither the metadata server nor the build account's own
  credentials can issue one there; impersonation can (build 09af1023).
- **Alternative considered:** a separate `verify-caller` service account holding the
  orchestrator invoker, impersonated by the build account. It would keep the build account
  out of the orchestrator's invoker list, at the cost of another account and bindings.
  Deferred to Sprint 6.
- **Code:** PR `fix/verify-caller-impersonation`: check 6 impersonates `CALLER_SA` (set from
  `_BUILD_SA` in the pipeline) when set, and uses the owner's gcloud identity locally; the dead
  metadata-server route from #33 is removed; a failed mint stays a FAIL line.

### Step 8 passed: build 5a181fa1 (commit `1a3f1e3`, `_RUN_VERIFY=true`) SUCCESS (2026-10-08, 17:31 to 17:34)
- All eight steps passed in 3 min 28 s: built, pushed, rendered, both services updated
  (`ops-orchestrator-00004-c6f`, `ops-reporting-00004-5kz`), **verify run by the pipeline, as
  the build account, passed every check**: serving revisions (both); three unauthenticated
  probes 403; reporting refuses the probe account (403); invoker exactly the orchestrator; both
  services on their dedicated accounts; the end-to-end question answered (HTTP 200,
  `answered`); `authorizedNetworks` empty. Two INFO lines (`/healthz` 404; owner token).
- This is the "verified serving" evidence: a revision built and deployed by the pipeline,
  holding 100% of traffic, verified by the pipeline, inside the window (stop rule not triggered).
- **Live model calls used: 7 of 8** (2 in the hand run, 2 in this pipeline run, 1 in the
  check that hit IAM propagation, 2 in the repeat). No 503 or rate limit occurred (R-15 not hit).

### Step 9: trigger settings
`gcloud builds triggers describe deploy-reporting-slice` (us-central1): `filename:
deploy/cloudbuild.yaml`; `includedFiles`: `services/**`, `packages/**`, `deploy/**`,
`pyproject.toml`, `uv.lock`; `repositoryEventConfig.push.branch: ^main$`; `serviceAccount:
projects/a2a-agentic-service-ops-gcp/serviceAccounts/build-deploy@...`; substitutions set on the
trigger: `_CLOUD_SQL_INSTANCE`, `_GEMINI_MODEL_ORCHESTRATOR`, `_GEMINI_MODEL_SPECIALIST`,
`_INSTANCE_NAME`. **`_RUN_VERIFY` is not set on the trigger**, so it defaults to `true`.

### Step 10: log scan
- Exported the Cloud Logging entries of `ops-orchestrator` (92) and `ops-reporting` (189) for
  the last 8 hours. They hold three `answered` traces: `c1bf1996994a4fd68d401dd5b8f38d34` (the
  hand-run question), `a046a49713704ccaa951e29960e8e57f` and `9b69b8a0d23c4a9f9d7d4fbe739675de`
  (the hand-run and pipeline verify runs).
- Scan: the value of five secrets (Gemini key, reporting, admin, eval and generator
  passwords) compared by exact match; plus patterns for an authorization header or field with a
  value, an unmasked bearer token, a JWT-shaped string and a URL password. The authorization
  pattern was checked with positive controls (it matches `Authorization: Bearer x`,
  `{'authorization': 'x'}` and the JSON-escaped form, and does not match Cloud Run's own
  "set the proper Authorization header" text or the audit-log field `authorizationInfo`).
- **Result: 0 findings.** The first, broader pattern had 39 hits, all platform text (Cloud
  Run's IAM refusal messages for the unauthenticated probes) and audit-log field names.

### End of day
- 17:37: Auth Proxy stopped; `ops-db` set to `NEVER` (state STOPPED). Cloud Run services remain
  deployed at min-instances 0; they are unavailable while the database is stopped, by design.
- The trigger is **not** disabled; that is decided in the records PR (ADR-083).
- Billed resources at end of day: Cloud SQL `ops-db` (stopped; storage and reserved IP only),
  two Cloud Run services (idle, no cost at min-instances 0), Secret Manager (nine secrets),
  Artifact Registry images, Cloud Build minutes.

### Window closed
- **2026-10-08 (day one of three): the window closed, the reporting slice verified serving**
  (build 5a181fa1, commit `1a3f1e3`, revisions `ops-orchestrator-00004-c6f` and
  `ops-reporting-00004-5kz`), with `ops-db` stopped (`NEVER`) and the Auth Proxy stopped. The
  build trigger `deploy-reporting-slice` was disabled the same evening (ADR-083); re-enabling
  is in `deploy/README.md`. Live calls used: 7 of 8. Records: ADR-083 to ADR-085, L-64 to
  L-66, and the R-03, R-14 and R-15 updates.

## Deploy window 2026-10-12 to 2026-10-13 (Sprint 5, Prompts V1, V2, V3)

*Owner-endorsed, assistant-drafted from the Claude Code session reports. These sessions made no repo edits by design (the system was frozen), so this entry is the written record.*

### Sitting 1: 2026-10-12, 19:41 to 20:09 CDT (V1)

**Setup:** Windows PowerShell 5.1.19041 (`pwsh` isn't installed). The tree equaled `eval-freeze-s5^{tree}` (`117198ea…`). Pre-flight 0a to 0f passed; unit suite 2578 passed, 1 skipped.

**Step 1:** `ops-db` reached `RUNNABLE ALWAYS` in about 7 minutes.

**Step 2:** `gateway-session-key` and `gateway-invites` created. Windows PowerShell 5.1's piping adds a trailing CRLF to the stored value. That is harmless: the gateway signs and verifies with the same value, and the JSON parse ignores it.

**Step 3:** `plan_full.py`'s real run failed, for two reasons:
- the runbook's command lacks `--skip-deploy`, so it exits with code 2;
- the check step runs `subprocess.run` without `shell=True`, so on Windows `gcloud.cmd` gives `FileNotFoundError`.

So **the 22 mutating commands were run by hand, verbatim from the dry run,** each approved by the owner. All succeeded. Results:
- new service accounts: `run-sentiment`, `run-forecast`, `run-qa`, `run-gateway`;
- `run-gateway` is the only accessor of both gateway secrets.

**Step 4:**
- **Backfill:** 270.8 s (estimated 15 minutes), 7,521 of 7,521 inserted, `complete: true`.
- **Fingerprint:** rows 7521, sha256 `a340b82d…e259f`, model version `0fa27f64…33ad`. **Exact match.**

**End of window:** `ops-db` `STOPPED NEVER`; trigger disabled.

### Sitting 2: 2026-10-13, morning (V2)

**Database:** `ops-db` start took about 13 minutes, against the runbook's 5; the CLI's wait timed out. The fingerprint matched again.

**Build (5b):**
- build `3e63cdc4-1f11-4969-b1bb-deecbd5b51a8`, `COMMIT_SHA` `9607fa722c4d…`;
- SUCCESS in about 5.6 minutes;
- **the commit's tree equals the freeze tag's;**
- `triggers run` accepted the disabled trigger.

**5c:** 7 invoker bindings applied by hand from the dry run (the same Windows bug as step 3).

**5d:** `allUsers` on `ops-gateway` only.

**5e:** every service at 100% traffic. Revision-level image fields show digests, so the tag was checked at the service template instead.

**5f:** Cloud SQL appears as the `run.googleapis.com/cloudsql-instances` annotation, on exactly the four database services.

**5g:**
- `status.url` is the legacy host `ops-gateway-vszrpegifq-uc.a.run.app`;
- the deterministic host (`$G`) is listed in `run.googleapis.com/urls` and serves the app: `GET /` gave 200 with the app's title, and `/auth/exchange` with a bad token gave 401;
- `/healthz` returns an empty 404 on both hosts. Cloud Run's front end reserves the path, so it never reaches the container.

**5h:** the logged `remoteIp` was the caller's real address, not the spoofed `203.0.113.7`, so the client-IP rule holds.

**Step 6, `verify.py` check 6, failed twice:** the routing call timed out after 30 s each time. Diagnosis, in order:
1. **Configuration ruled out.** Comparing orchestrator revision 00004 (which worked) with 00005: identical key reference, egress and timeouts.
2. **Error class inferred** from the 0.27 s retry wait: a transient failure, not a 429.
3. **One local free-key call** gave `504 DEADLINE_EXCEEDED` after 29.96 s.
4. **One local paid-key call** answered 200 in 1.85 s.

**Conclusion:** the free-tier path for `gemini-3.5-flash-lite` was failing, not the deployment.

**Step 7, deferred:** the integration suites need `POSTGRES_ADMIN_*`, and running their fixtures with superuser rights against the evaluation database was refused. The fingerprint stands as the data-parity evidence.

**Step 8, deferred:** the trigger stays disabled until after Prompt X.

### Sitting 3: 2026-10-13, 10:45 to about 12:15 CDT (V3, paid-key switch)

**The record and the secret:**
- ADR-104 merged as PR #50 (docs only) before any change.
- `gemini-api-key-paid` created **by the owner in his own shell**, through a temp file without a newline. Its accessors are exactly the five model-calling service accounts.

**The first update failed:** `ops-qa-00002-zct` didn't start, with `LLMConfigError`. The cause was the unquoted commas in `--update-env-vars`, which Windows PowerShell 5.1 turns into an array, so `LLM_MODE` became one space-joined string. Fail-fast worked: **no traffic moved, and no model call was made.** The update was retried with the argument quoted.

**Serving revisions** (all at 100%, every container's image `9607fa72…`, model-calling containers on `LLM_MODE=paid`):

| Service | Revision |
|---|---|
| `ops-qa` | `00003-hwq` |
| `ops-sentiment` | `00002-cxz` |
| `ops-forecast` | `00002-m79` |
| `ops-reporting` | `00006-md5` |
| `ops-orchestrator` | `00006-bvj` |
| `ops-gateway` | `00001-8st` |

**`verify.py`:** 11 PASS, exit 0. 3 paid calls, about $0.0015.

**Owner steps 9 to 11:**
- invites created: `owner-laptop` (14 days) and `test`;
- the checks: valid gave 200, expired gave 401, revoked (after 70 s) gave 401;
- three smoke questions (reporting, sentiment, forecast) answered, with a correct "Interpreted as:" line and verification line each.

**The cold-start question** (after 15 minutes idle):
- 55.87 s in the browser, 54.47 s at the gateway, against 120 s;
- new instances at the gateway, orchestrator, reporting (about 20 s start) and QA (about 14 s start);
- each model call about 1.5 s.

**End:** `ops-db` left running for Prompt X; the trigger disabled.

## Addenda, 2026-10-14 (Z1, records reconciliation; the entries above are unchanged)

- **Sitting 2, step 5h ("the client-IP rule holds").** The logged `remoteIp` was the caller's real address, not the spoofed `203.0.113.7`, which is consistent with the rule. The evidence is Cloud Run's logged `remoteIp` only; the gateway's own keying was not shown, so the rule is observed, not documented (L-88, note under ADR-097).
- **Sitting 3, "`ops-db` left running for Prompt X".** True at the time. The owner stopped `ops-db` after the Sprint 5 close (2026-10-13, per ADR-105); a read-only `describe` on 2026-10-14 read `STOPPED NEVER`. The time of the stop is not recorded.
- **Invite host.** Every invite created in this window used the deterministic host, `--base-url $G` = `https://ops-gateway-587647038690.us-central1.run.app` (ADR-107).

## Z2b: deploy of the post-freeze fixes, 2026-10-14 (owner present; assistant-drafted)

Not a grading window. Deploy `main`, verify it, prove the trigger safe, leave the system stopped and locked.

**Before the deploy.**
- First §0 stopped on the Next.js rule: three advisories published 2026-10-14 name 16.4.1 (GHSA-2464-fhr4-w9xw, GHSA-673q-mjm6-r5xr, GHSA-p3m5-59mp-jv5r). The owner merged the 16.4.1 pin (PR #56).
- The second §0 found that `deploy/RUNBOOK_GRADING.md` matched `deploy/**` and was not ignored, so a docs-only edit to it would have started a deploy. The owner approved a widened ignore (`deploy/**/*.md`, PR #57), merged before the deploy; the trigger was re-imported disabled.
- Deploy target `9ab7c775964bd0aae491ca72082e95229c994129`. Prompt diff against `eval-freeze-s5` empty; freeze, manifest and trigger tests pass (38).
- `ops-db` started by the owner with `--async` (the assistant's `patch` was refused by the permission layer); `RUNNABLE ALWAYS` at about 20:17 CDT.

**Build.** Trigger run on `main` by the owner, `_RUN_VERIFY=false`. Build `0dc5aae1-2a6c-498e-bbca-f709c2c91149`, `SUCCESS`, `COMMIT_SHA` = the target, 01:26:16Z to 01:33:28Z (about 7 min 12 s).

**Serving revisions** (each at 100%, image tag `9ab7c775…`):

| Service | Revision |
|---|---|
| `ops-qa` | `00004-t6m` |
| `ops-sentiment` | `00003-hx4` |
| `ops-forecast` | `00003-ndv` |
| `ops-reporting` | `00007-8mm` |
| `ops-orchestrator` | `00007-b8z` |
| `ops-gateway` | `00002-w57` |

The previous set (`9607fa72…`) is the rollback target: gateway `00001-8st`, orchestrator `00006-bvj`, reporting `00006-md5`, sentiment `00002-cxz`, forecast `00002-m79`, qa `00003-hwq`.

**`verify.py`:** every line `PASS`, exit 0, six services: invoker sets (`allUsers` on the gateway only), dedicated service accounts, serving revision and image tag at the template, **paid mode on the five model-calling containers** (the YAML sync held: the deploy from the repo did not revert to the free key), `authorizedNetworks` empty, unauthenticated probes 403, and the end-to-end question (HTTP 200, `outcome=answered`). One live question.

**Finding: IPv6 black-hole.** The first `verify.py` run hung about 35 minutes at its end-to-end call: from the owner's PC, IPv6 to `*.run.app` times out and IPv4 answers (`/health` returned `{"status":"ok"}` over IPv4). No model call was made by the hung run. Re-run through a temp wrapper forcing IPv4 (no repo change); about 40 minutes in total because each `gcloud` call took 1 to 4 minutes. Noted in `RUNBOOK_V.md`.

**Log findings** (the end-to-end request, trace `d9f30a91…`):
- The trace ID is on 21 lines: orchestrator, reporting (including `mcp_incidents`' `tool call` line) and QA. The gateway was not on this path (`verify.py` calls the orchestrator).
- The field names actually used are in `RUNBOOK_V.md` step 12 and `RUNBOOK_GRADING.md` Reference: `trace_id`, `service`, `logger`, `level`, `msg`, `ts`; `path`, `status`, `duration_ms` on `msg=request`; `outcome`, `route`, `verdict`, `cost_usd`; `code` on a failed task.
- Plain text: `outcome=answered` and `verdict=pass` seen live. The failure paths log `code` as a plain field (reporting `task failed`, orchestrator `agent task failed`) and `outcome=degraded`; read from the code, not exercised live. No gap found.
- No router reason text (`reason_chars`, `reason_sha` only), no question text (`question_chars`), no exception text.

**Owner's smoke check (browser, paid key).**
- Q1 SLA compliance, Northeast, last month: 141 of 160, 88.13%, 2026-07-01 to 07-31, verification line shown; about 28 s.
- Q2 sentiment trend by month: 723 comments (positive 366, neutral 176, negative 128, mixed 53), no clear change in the negative share (p = 0.9096); about 27 s.
- Q3 weekly volume, next 8 weeks: 8 weeks from 2026-08-31, about 1,322 in total; about 39 s.
- Each showed its "Interpreted as:" line and the verification line. These timings are warm or partly cold instances and are not the R-05 measurement.

**Trigger proof and end state.** This entry is the docs-only merge under test, so its result is not in it. The enable, the merge check and the disable are reported in the Z2b report and recorded in the next dated entry.

### Z2b addendum, 2026-10-14: the trigger proof and the end state (the entry above is unchanged; owner-approved; assistant-drafted)

- **Enabled** by importing `deploy/trigger_full.yaml` with `disabled: false` from a temp copy (runbook step 8), about 22:19 CDT. The live trigger carried `deploy/**/*.md` in `ignoredFiles` (re-imported disabled before the deploy, PR #57). The latest build was `0dc5aae1-2a6c-498e-bbca-f709c2c91149`.
- **Docs-only merge:** the owner merged PR #58 (`docs/z2b-deploy-record`: `deploy/RUNBOOK_V.md`, `deploy/RUNBOOK_GRADING.md` and three files under `docs/`) at about 22:26 CDT; `origin/main` read `82501b0` at 22:27. Read-only `gcloud builds list` at 22:27, 22:30 and 22:33 CDT showed the latest build still `0dc5aae1…`: **no build started in at least 6 minutes** (the criterion was 3). The offline matcher (`tests/unit/test_deploy_trigger.py`) agreed (`builds: False` for the same file set).
- **Disabled again** the same way, from the repo file; `describe` reads `disabled: True`. The trigger was enabled for about 20 minutes with `ops-db` running.
- **End state:** six services serving the Z2b revisions; trigger disabled (ADR-107, ADR-083); `ops-db` stopped at the end of the window (below, if the stop is recorded). Window A opens 2026-10-31 from `deploy/RUNBOOK_GRADING.md`.
- **Not verified in Z2b:** the logging of each failed model-call attempt (no retry occurred); the failure-path `code` and `outcome=degraded` lines live (sprint-log, Sprint 6 items).


## Owner verification session 1, 2026-10-15 (ADR-110; owner present; assistant-drafted)

Run 2026-10-15 instead of the planned 2026-10-17 (owner decision). Plan: `docs/session-plan-2026-10-17.md`. Records: `evals/results/session1/2026-10-15/` (`summary.md`, `run-notes.md`, `ledger.json`, `ledger.json.evidence.jsonl`, `verify-output.txt`).

- **`ops-db`:** started by the owner, T0 17:39:04 CDT (`RUNNABLE ALWAYS`); stopped, `STOPPED NEVER`, read at 19:47:55 CDT (about 2 h 9 min; the 4-hour limit was not reached).
- **Deployed system:** build `0dc5aae1-2a6c-498e-bbca-f709c2c91149`, commit `9ab7c77`; unchanged at open and close. Trigger `deploy-reporting-slice` disabled throughout. No deploy, no configuration change.
- **Balance:** opening $7.88 (Google AI Studio credit balance, topped up 2026-10-15). No closing balance figure was provided. The owner reported AI Studio total spend $2.12 for 2026-09-18 to 10-15 and GCP billing $4.50 minus $1.64 savings = $2.86 for 2026-10-01 to 10-15, both cumulative. The session's own model spend is not separable from them.
- **Ledger:** 57 of 75 requests, $0.079 of $0.25.
- **Invites** (ids and labels only; no link or token is recorded): `owner-laptop` `77782f3db080`, `session1-grader` `764ff0288732`, `session1-cap` `3f1feaa4cb64`, `session1-expired` `7ff2c16a58f3`, `session1-revoked` `a39aa0ca51b1`. All `session1-*` invites were revoked or expired at the close.
- **`owner-laptop` revoked at the close, by the owner's decision:** its session cookie reached the assistant chat in a screenshot. The owner creates a fresh owner invite afterwards. (Plan step 6.1 said never revoke it.)
- **Two dead invite links were pasted into the assistant chat** (`session1-expired`, `session1-revoked`); both were already expired or revoked. The tokens were not written to any file.
- **Steps run:** `verify.py --ipv4` (35 PASS, 0 FAIL); cold-start readings for sentiment (61 s, then 30.64 s on repeat) and forecast (46 s); TS-14-A, B (five services), C, D; TS-16-D; TS-18-C; TS-18-D; TS-20-A, C, D; the failure path (HTTP 422 `invalid_range`); grader-access check and revoke re-test (5b).
- **Steps not run:** TS-20-B (no trigger), TS-20-E (interface notice not checked), the built-image scan for TS-14-D, the repeat runs (3.9, dropped by decision 3), the reporting-path re-measure after a cold chain.
- **Findings:** TS-18-C: reporting stayed at one instance under 6 concurrent requests, so the "scales up" clause did not hold. TS-15-D: `agent_reporting` and `mcp_incidents` log the tool's error text (parsed dates, window), not question text. The 429 wording was not seen, only the code. The first sentiment reading's gateway hop was not cold (owner reload about 3 min earlier).
- **Stop rules:** none fired. 3.8a: N = 7 and N = 15 (not above 19).
- **Not verified deployed:** the retry logging (ADR-108): no retry occurred.
- *Addendum, 2026-10-15 (same day; the entry above is unchanged).* **TS-20-E** was checked by the owner on the landing page at 20:00 CDT: no synthetic-data notice, FAIL, the known fail (`05` §7). It moves from "not run" to run. **TS-18-C's scaling-clause fail** is classed by the owner as a `05` criterion flaw, not a system fault.