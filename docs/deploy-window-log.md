# Deploy window log (ADR-045, ADR-078, ADR-081, ADR-084)

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
