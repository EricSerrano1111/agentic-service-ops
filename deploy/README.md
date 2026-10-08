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

Set once in your shell: `PROJECT_ID`, `PROJECT_NUMBER`, `REGION=us-central1`, `INSTANCE`
(instance name), `CONN=$PROJECT_ID:$REGION:$INSTANCE`, and the four account emails
(`ORCH_SA`, `REPORTING_SA`, `BUILD_SA`, `PROBE_SA`).

1. **Provision Cloud SQL**: PostgreSQL **16**, edition **Enterprise** chosen explicitly,
   smallest shared-core tier, **storage auto-increase off**, public IP on, **no authorized
   networks**. Confirm the monthly estimate in the console and record it.
2. **Secrets** (Secret Manager): `gemini-api-key` (the free key), `db-role-reporting-password`
   (the `app_reporting` password). Grant `roles/secretmanager.secretAccessor` per secret:
   `gemini-api-key` to the orchestrator and reporting accounts; `db-role-reporting-password`
   to the reporting account only.
3. **IAM bindings**, in this order:
   - runtime accounts: reporting gets `roles/cloudsql.client` (project); the orchestrator gets
     nothing on Cloud SQL;
   - build account: `roles/run.developer`, `roles/artifactregistry.writer`,
     `roles/logging.logWriter`, `roles/cloudsql.viewer` (for the verify step),
     `roles/iam.serviceAccountUser` **on each of the two runtime accounts**, and, for the
     verify step run from Cloud Build, `roles/iam.serviceAccountTokenCreator` on the probe
     account;
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
10. **Create the trigger** (below), then run it once (first deploy). After the services exist:
    ```
    gcloud run services add-iam-policy-binding ops-reporting --region $REGION \
      --member "serviceAccount:$ORCH_SA" --role roles/run.invoker
    gcloud run services add-iam-policy-binding ops-orchestrator --region $REGION \
      --member "serviceAccount:$BUILD_SA" --role roles/run.invoker
    ```
    The second lets the Cloud Build verify step call the orchestrator. Never add `allUsers`
    or `allAuthenticatedUsers`; `verify.py` fails the build if either appears on reporting.
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
account. Substitutions to set on the trigger: `_AR_REPO`, `_BUILD_SA`, `_ORCHESTRATOR_SA`,
`_REPORTING_SA`, `_PROBE_SA`, `_CLOUD_SQL_INSTANCE` (`project:region:instance`),
`_INSTANCE_NAME`, `_GEMINI_MODEL_ORCHESTRATOR`, `_GEMINI_MODEL_SPECIALIST` (`_REGION` and
`_POSTGRES_DB` default). An empty one fails the render step.

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
