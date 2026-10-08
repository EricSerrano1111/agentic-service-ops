# Deploy: reporting slice on Cloud Run (ADR-078, ADR-079, ADR-081)

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
     `agent-reporting`. Never the paid key.
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

## The build trigger

Push to `main`, **included files** `services/**`, `packages/**`, `deploy/**`, `pyproject.toml`
and `uv.lock`, so a docs-only merge does not redeploy. Runs as the dedicated build service
account. The trigger lives in **us-central1**, the region of the Cloud Build 2nd gen connection
`GitHub-CloudBuild-A2A`, not as a global trigger. Substitutions to set on it:
`_CLOUD_SQL_INSTANCE` (`project:region:instance`), `_INSTANCE_NAME`,
`_GEMINI_MODEL_ORCHESTRATOR` and `_GEMINI_MODEL_SPECIALIST`. The rest default in
`cloudbuild.yaml` (`_AR_REPO`, the four service accounts, `_REGION`, `_POSTGRES_DB`,
`_RUN_VERIFY`) and the trigger may override them. An empty one fails the render step.

## What `verify.py` checks

1. Each service's serving revision is the one just deployed (images tagged with the commit
   SHA) and holds 100% of traffic.
2. An unauthenticated call to the orchestrator is refused (401/403).
3. Reporting refuses a caller that is not the orchestrator: an identity token minted by
   impersonating the no-role probe account, audience = the reporting URL, expects 403.
4. Reporting's IAM policy grants `roles/run.invoker` to exactly the orchestrator's account and
   binds neither `allUsers` nor `allAuthenticatedUsers`.
5. Neither service runs as the default compute service account, and each runs as its own.
6. The orchestrator answers one reporting question end to end (one live free-tier model call
   for routing and one for parsing).
7. Cloud SQL `authorizedNetworks` is empty.

Not tested, by design (printed as INFO): that the owner's own token is refused by reporting.
Project Owner invokes any service through the basic role, so the check would fail by design.

## Local parity

Compose is unchanged in shape: separate containers, TCP to Postgres (`POSTGRES_HOST`),
`MCP_*_URL` set to the service name. On Cloud Run the same images are configured by
environment only: `CLOUD_SQL_INSTANCE` replaces `POSTGRES_HOST` (the host becomes
`/cloudsql/<instance>`), `MCP_INCIDENTS_URL=http://localhost:8101/mcp`, and `A2A_AUTH=
google_id_token` on the orchestrator.
