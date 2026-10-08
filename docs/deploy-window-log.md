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
