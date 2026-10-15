# Deploy: reporting slice on Cloud Run (ADR-078, ADR-079, ADR-081)

> **Hard rule (Z2a, 2026-10-14): the build trigger may be enabled only after the paid-mode YAML sync (ADR-104 note of 2026-10-14) is merged to `main`.** Until then the repo definitions and the deployed services differ, and the first deploy would revert five services to the free key.
>
> **Updated 2026-10-14 (Z1):** the full system was deployed 2026-10-13 and runs on the paid key (ADR-104); `ops-db` is stopped outside announced grading windows (ADR-105); the window procedure is `RUNBOOK_GRADING.md` (ADR-107). The build trigger is disabled and must not be enabled until `cloudrun/*.yaml` is synced to paid mode (Z2). Statements below about the free key describe the reporting slice as deployed on 2026-10-08.
>
> **Full system (2026-10-12, ADR-099):** six services now. `RUNBOOK_V.md` is the window runbook, `plan_full.py` the plan, `cloudrun/*.yaml` the six definitions, `trigger_full.yaml` the trigger. Everything below describes the reporting slice and still holds for it; where this README and `RUNBOOK_V.md` differ, the runbook is current. `ops-sentiment` deploys with the others, reading stored predictions only (ADR-100, which resolved R-19); the runbook is two sittings.

Two Cloud Run services, `ops-orchestrator` and `ops-reporting` (the reporting agent with
`mcp_incidents` as a sidecar), in front of one Cloud SQL Postgres 16 instance. Everything in
this folder is a draft: it has been validated locally (YAML parses, placeholders render,
checks are unit-tested) and **never run against GCP**.

| File | What it is |
| --- | --- |
| `cloudrun/orchestrator.yaml`, `cloudrun/reporting.yaml` | Service definitions, Cloud Run Admin API **v2** format, with `${PLACEHOLDER}`s |
| `render.py` | Resolves placeholders from the environment; exits 1 if any is unset or remains |
| `deploy_service.py` | Creates or updates one service from a rendered definition (v2 REST API) |
| `cloudbuild.yaml` | Build and push three images (tag = commit SHA), render, deploy both, verify |
| `verify.py` | Post-deploy checks; PASS/FAIL per line; exit 1 on any FAIL |

## Cloud SQL mount (why v2, and not a gcloud flag or the v1 YAML)

ADR-079 and L-61 need the Cloud SQL connection inside `mcp-incidents` only. Checked against
current Google Cloud documentation on 2026-10-08:

- **Knative v1 service YAML** (what `gcloud run services replace` reads) attaches Cloud SQL
  with the revision-level annotation `run.googleapis.com/cloudsql-instances`. That reaches
  every container, so it cannot do this. Not used.
- **`gcloud run deploy`**: `--add-cloudsql-instances` is documented as a service-wide flag
  (outside the container-scoped group), and the documented `--add-volume` types are
  `cloud-storage`, `ephemeral-disk`, `in-memory` and `nfs`. No Cloud SQL type. Not used.
- **Cloud Run Admin API v2** models Cloud SQL as a `Volume` with `cloudSqlInstance`, and each
  container mounts it through its own `volumeMounts`; for Cloud SQL the mount path is empty or
  `/cloudsql`, and each instance appears as `/cloudsql/<instance-connection-name>`. This
  expresses the per-container mount, so the definitions use it, and `deploy_service.py` sends
  them to the v2 API (`POST .../services?serviceId=` to create, `PATCH` to update).

Sources: [Connect Cloud Run to Cloud SQL](https://docs.cloud.google.com/sql/docs/postgres/connect-run),
[Cloud Run: deploy multi-container services](https://docs.cloud.google.com/run/docs/deploying),
[`gcloud run deploy` reference](https://docs.cloud.google.com/sdk/gcloud/reference/run/deploy),
[Cloud Run Admin API v2 `Volume` / `VolumeMount`](https://docs.cloud.google.com/dotnet/docs/reference/Google.Cloud.Run.V2/latest/Google.Cloud.Run.V2.Volume),
[Cloud Run service YAML (v1) reference](https://docs.cloud.google.com/run/docs/reference/yaml/v1).

**To confirm in the window, on the first deploy:** that the `PATCH` without an `updateMask`
replaces the template as expected, and that the socket appears only in `mcp-incidents`
(`gcloud run revisions describe` shows the volume mounted on that container alone).

## The prep rule

**Before the window (allowed now; nothing here creates billable or stateful resources):**

- local code and tests; these config drafts;
- confirm the GCP project; budget alerts at $50 and $80;
- enable APIs (Cloud Run, Cloud Build, Artifact Registry, Secret Manager, Cloud SQL Admin, IAM,
  IAM Credentials);
- create the Artifact Registry repo;
- create the service accounts: orchestrator runtime, reporting runtime, **build**, and
  **probe** (`probe-noauth`, which gets no role and no binding of any kind).

**Inside the window (2026-10-12 to 10-14; ADR-078):** Cloud SQL; secrets; images; the build
trigger; IAM bindings, including the owner's token-creator binding on the probe account; the
data load; every deploy.

## Window runbook (in order)

Set once in your shell: `PROJECT_ID=a2a-agentic-service-ops-gcp`, `PROJECT_NUMBER`,
`REGION=us-central1`, `INSTANCE` (instance name), `CONN=$PROJECT_ID:$REGION:$INSTANCE`, and
the four account emails, each `<id>@$PROJECT_ID.iam.gserviceaccount.com`: `ORCH_SA`
(`run-orchestrator`), `REPORTING_SA` (`run-reporting`), `BUILD_SA` (`build-deploy`), `PROBE_SA`
(`probe-noauth`). Pass `--project=$PROJECT_ID` on every `gcloud` command.

1. **Provision Cloud SQL**: PostgreSQL **16**, edition **Enterprise** chosen explicitly,
   smallest shared-core tier, **storage auto-increase off**, public IP on, **no authorized
   networks**. Confirm the monthly estimate in the console and record it.
2. **Secrets** (Secret Manager). Names only here; a value is never written down, printed or
   passed as an echoed argument. All cloud passwords are **newly generated**, never copied from
   the local `.env`, and piped straight into `gcloud secrets create --data-file=-`.
   - `gemini-api-key`: the **free** Gemini key. **Mounted** in the orchestrator and in
     `agent-reporting`. *Updated 2026-10-14 (ADR-104):* the five model-calling services now also mount
     `gemini-api-key-paid` and run `LLM_MODE=paid`; the free key stays mounted beside it as
     `GOOGLE_AI_API_KEY`, so a revert to the free tier is a single env change. The reporting-slice
     deploy of 2026-10-08 used the free key only.
   - `db-role-reporting-password`: the `app_reporting` password. **Mounted** in `mcp-incidents`
     only.
   - **Stored only so the roles can be recreated; no service account has access** to any of
     them: `db-admin-password` (the `postgres` user) and the other six role passwords,
     `db-role-sentiment-password`, `db-role-forecast-password`, `db-role-qa-password`,
     `db-role-generator-password`, `db-role-eval-password` and `db-role-train-password`.
     Alembic's roles migration needs all seven `DB_ROLE_*` passwords to create the roles on
     Cloud SQL.
   - Grant `roles/secretmanager.secretAccessor` per secret, never project-wide:
     `gemini-api-key` to the orchestrator and reporting accounts; `db-role-reporting-password`
     to the reporting account only.
3. **IAM bindings**, in this order:
   - runtime accounts: reporting gets `roles/cloudsql.client` (project); the orchestrator gets
     nothing on Cloud SQL;
   - build account: `roles/run.developer`, `roles/artifactregistry.writer`,
     `roles/logging.logWriter`, `roles/cloudsql.viewer` (for the verify step),
     `roles/iam.serviceAccountUser` **on each of the two runtime accounts**, and, for the
     verify step run from Cloud Build, `roles/iam.serviceAccountTokenCreator` on the probe
     account **and on itself** (check 6 mints the build account's identity token by
     impersonating it; Cloud Build's metadata server issues none). Nothing else is granted on
     the build account itself;
   - owner: `roles/iam.serviceAccountTokenCreator` on the probe account (so `verify.py` can
     impersonate it);
   - the service-level invoker bindings need the services to exist; they are created in step
     10, immediately after the first deploy.
4. **Auth Proxy** from the owner's machine to the instance (`cloud-sql-proxy $CONN`); point
   `POSTGRES_HOST=127.0.0.1` at it for the next four steps. Never open an authorized network.
5. `alembic upgrade head` (admin credentials, from the owner's machine only).
6. **Load data** as the generator role: `python data/generator/load.py --corpus
   data/generator/corpus/feedback_text.jsonl`.
7. **Validation suite**: `python data/generator/validate.py`.
8. **Dataset hash check**: the new report's `meta.corpus_sha256`, `meta.master_seed` and
   `meta.rows` equal those in the committed `data/generator/validation/2026-10-01/report.json`.
9. **Grants suite**: `REQUIRE_INTEGRATION_DB=1 python -m pytest tests/integration -q -rs`
   against the proxy.
10. **Create the trigger** (below) with `_RUN_VERIFY=false` and run it once: the first deploy.
    **The first run must skip the pipeline's verify step.** The services-level invoker
    bindings cannot exist before the services do, so checks 4 (reporting's invoker) and 6
    (the end-to-end question, which needs the orchestrator to be allowed to call reporting)
    would fail the build for a reason that is not a defect. Once the services exist, bind:
    ```
    gcloud run services add-iam-policy-binding ops-reporting --region $REGION \
      --member "serviceAccount:$ORCH_SA" --role roles/run.invoker
    gcloud run services add-iam-policy-binding ops-orchestrator --region $REGION \
      --member "serviceAccount:$BUILD_SA" --role roles/run.invoker
    ```
    The second lets the Cloud Build verify step call the orchestrator. Never add `allUsers`
    or `allAuthenticatedUsers`; `verify.py` fails the build if either appears on reporting.
    Then set the trigger's `_RUN_VERIFY` back to `true` (its default) and re-run it, so every
    later deploy is verified. The build account's `serviceAccountTokenCreator` on the probe
    account (step 3) is what lets check 3 mint the probe's token inside Cloud Build.
11. **`verify.py`** from the owner's machine as well (the pipeline runs it as the build
    account): set the variables listed in its docstring and run `python deploy/verify.py`.
12. **Stop the instance at day end**: `gcloud sql instances patch $INSTANCE --activation-policy
    NEVER`, and start it again with `ALWAYS`. Storage still bills while stopped.

## The stop rule (ADR-078)

Stop at the **end of 2026-10-14** if the revision is not verified serving. Then: record R-03
as realised, write it up as the first incident in `06-production-support.md`, and leave the
Sprint 5 plan unchanged. Stop the Cloud SQL instance either way.

## Operating the deployed services

- **Start the database before any test or demo, stop it after.** The services are unavailable
  while `ops-db` is stopped (L-65): the sidecar's `/readyz` fails and the agent will not start.
  ```
  gcloud sql instances patch ops-db --project=a2a-agentic-service-ops-gcp --activation-policy=ALWAYS
  gcloud sql instances patch ops-db --project=a2a-agentic-service-ops-gcp --activation-policy=NEVER
  ```
  After adding an IAM binding, wait a few minutes before the first verify run (propagation took
  over a minute on 2026-10-08).
- **Roll back a revision that failed verification** (L-64). The pipeline deploys at 100% traffic
  and then verifies, so a failed verification leaves the new revision serving:
  ```
  gcloud run revisions list --service=<service> --region=us-central1 --project=a2a-agentic-service-ops-gcp
  gcloud run services update-traffic <service> --to-revisions=<previous revision>=100 \
    --region=us-central1 --project=a2a-agentic-service-ops-gcp
  ```
- **The build trigger is disabled between deploy windows** (ADR-083): while `ops-db` is stopped,
  any merge to `main` touching its paths would deploy a revision that fails readiness. gcloud
  has no disable flag for it. **To re-enable:** start `ops-db` first, then in the console go to
  Cloud Build, Triggers, region us-central1, `deploy-reporting-slice`, and enable it. Or call the
  API: `GET https://cloudbuild.googleapis.com/v1/projects/a2a-agentic-service-ops-gcp/locations/us-central1/triggers/e4c3b9df-07f4-4f8b-8acb-3d7443a5fa2c`,
  set `"disabled": false` in the returned resource, and `PATCH` the same URL with
  `?updateMask=disabled` and the whole resource as the body (it is how it was disabled on
  2026-10-08). Disabling is the same with `true`.

## The build trigger

Push to `main`, **included files** `services/**`, `packages/**`, `deploy/**`, `pyproject.toml`
and `uv.lock`, so a docs-only merge does not redeploy. Runs as the dedicated build service
account. The trigger lives in **us-central1**, the region of the Cloud Build 2nd gen connection
`GitHub-CloudBuild-A2A`, not as a global trigger. Substitutions to set on it:
`_CLOUD_SQL_INSTANCE` (`project:region:instance`), `_INSTANCE_NAME`,
`_GEMINI_MODEL_ORCHESTRATOR` and `_GEMINI_MODEL_SPECIALIST`. The rest default in
`cloudbuild.yaml` (`_AR_REPO`, the four service accounts, `_REGION`, `_POSTGRES_DB`,
`_RUN_VERIFY`) and the trigger may override them. An empty one fails the render step.

*Note, 2026-10-14 (Z2b):* the ignore list now has `deploy/**/*.md` in place of the single
`deploy/RUNBOOK_V.md`. `deploy/RUNBOOK_GRADING.md` matched `deploy/**` and was not ignored, so a
docs-only edit to it would have started a deploy. Markdown elsewhere is still not ignored (the
prompts under `services/*/prompts/` are `.md` and are baked into the images).
`tests/unit/test_deploy_trigger.py` covers both sides. The live trigger takes the change at the
next import of `trigger_full.yaml`.

## What `verify.py` checks

1. Each service's serving revision is the one just deployed (images tagged with the commit
   SHA) and holds 100% of traffic.
2. An unauthenticated call to the orchestrator is refused (401/403).
3. Reporting refuses a caller that is not the orchestrator: an identity token minted by
   impersonating the no-role probe account, audience = the reporting URL, expects 403.
4. Reporting's IAM policy grants `roles/run.invoker` to exactly the orchestrator's account and
   binds neither `allUsers` nor `allAuthenticatedUsers`.
5. Neither service runs as the default compute service account, and each runs as its own.
6. The orchestrator answers one reporting question end to end (one live model call
   for routing and one for parsing; free tier on 2026-10-08, the paid key since 2026-10-13, ADR-104).
7. Cloud SQL `authorizedNetworks` is empty.

Not tested, by design (printed as INFO): that the owner's own token is refused by reporting.
Project Owner invokes any service through the basic role, so the check would fail by design.

## Window-day options (added 2026-10-15, S6-T1)

```
python deploy/verify.py [--ipv4] [--gcloud-timeout SECONDS]
```

On 2026-10-14 (Z2b) IPv6 to `*.run.app` black-holed from the owner's PC and each `gcloud` call took
one to four minutes, so one `verify.py` run hung for about 35 minutes with nothing printed. These
options are for that PC. The pipeline passes no arguments, so its invocation is unchanged
(`cloudbuild.yaml` is not edited), and a run with no options does the same checks in the same
order with the same exit code.

1. **`--ipv4` (opt-in; default off).** Every HTTP connection `verify.py` opens to `*.run.app`
   resolves the host for IPv4 only and connects to those addresses only. The URL, the TLS
   server name and the `Host` header are unchanged. Without the flag, name resolution is
   unchanged (IPv4 and IPv6, in the resolver's order).
2. **Connect timeout on every HTTP call: 10 s, no flag.** It applies in both modes.
   - It is per resolved address, as with `socket.create_connection`: an address that does not
     answer in 10 s is abandoned and the next one is tried. Only when every address has failed
     to connect is the call a failure, and the check's line is `FAIL  <check name>: connect
     timeout` (never a traceback).
   - It covers connecting only. The read timeout stays 150 s, because the end-to-end question
     makes two model calls. A read timeout is not reported as a connect timeout.
   - **The one default-behaviour change:** before, a single 150 s timeout covered each connect
     attempt and each read. Now a connect attempt waits 10 s. This differs from the old
     behaviour only where a connect would otherwise have waited more than 10 s. On this PC, a
     black-holed IPv6 address now costs about 10 s before the IPv4 address is tried, so
     `--ipv4` mostly saves that wait, and no longer decides whether the run completes.
3. **Timeout on each `gcloud` call: 300 s, `--gcloud-timeout SECONDS` to change it.**
   - Before each `gcloud` call a line is printed naming it, for example
     `INFO  gcloud run services describe ops-gateway --region=us-central1 --format=json (timeout 300 s)`.
     Arguments only; `gcloud`'s output (tokens, the account) is never printed.
   - On expiry the call and its whole process tree are killed (on Windows `gcloud.cmd` starts a
     child, which must not be left holding the pipes), and the check that needed it prints
     `FAIL  <check name>: gcloud timed out after N s: <the call>`.
   - The run **continues** with every check that does not need the failed call; a check that
     needs it fails at once with the same reason, and the call is not repeated. Exit code 1.
   - A `gcloud` call that exits non-zero is a FAIL line with its first error line, not a
     traceback (check 6's mint failure already was).
4. **Incremental output.** Each check prints its `PASS` or `FAIL` line as it finishes, flushed.
   The closing INFO lines and the exit code are as before.

The checks themselves, their order and their pass conditions are unchanged. Three added
behaviours also apply in the pipeline, because they have no switch: the 10 s connect timeout,
the 300 s `gcloud` timeout, and the INFO line before each `gcloud` call (log text only).
Unit tests cover all four options with no network and no `gcloud`
(`tests/unit/test_verify_window_day.py`). The root `conftest.py` points `CLOUDSDK_CONFIG` at an
empty temporary folder for every test session and unsets `GOOGLE_APPLICATION_CREDENTIALS` and
`CLOUDSDK_CORE_PROJECT`, so no test can reach real `gcloud` state.

**Amended after implementation, 2026-10-15.** The sections above are the spec as written. The
build changed default behaviour beyond the timeouts and the flushing, and the pipeline gets all
of it, because none of it has a switch:
- A `gcloud` call that exits non-zero, or a missing `gcloud`, is a `FAIL` line with its first
  error line instead of a traceback.
- The run continues after a failure or timeout. A check that needs a failed call fails at once
  with the same reason, and the call is not repeated.
- An `INFO  gcloud …` line precedes every `gcloud` call, so it also appears in Cloud Build logs.
- Connecting to `*.run.app` without `--ipv4` waits about 10 s on a black-holed IPv6 address
  before trying IPv4.
- **The paid end-to-end question is guarded.** It is the only check that calls a model. Because
  the run now continues after a failure, it prints `FAIL  …: skipped: earlier failure` and makes
  no call (no token, no question) when any earlier check failed. Before, a failed pure check did
  not stop it; only an exception did. It is now stricter than that.

## Local parity

Compose is unchanged in shape: separate containers, TCP to Postgres (`POSTGRES_HOST`),
`MCP_*_URL` set to the service name. On Cloud Run the same images are configured by
environment only: `CLOUD_SQL_INSTANCE` replaces `POSTGRES_HOST` (the host becomes
`/cloudsql/<instance>`), `MCP_INCIDENTS_URL=http://localhost:8101/mcp`, and `A2A_AUTH=
google_id_token` on the orchestrator.
