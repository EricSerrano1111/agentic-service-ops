# Runbook for Prompt V: deploy the full system (ADR-098, ADR-099, ADR-100)

> **Updated 2026-10-14 (Z1). Executed 2026-10-12/13; see `docs/deploy-window-log.md`.** The three sittings ran
> 2026-10-12 (V1), 2026-10-13 morning (V2) and 2026-10-13 10:45 to about 12:15 CDT (V3, the paid-key switch,
> ADR-104). The body below is the runbook as written on 2026-10-12 and is kept as written except where marked
> *Updated 2026-10-14*. **For a grading window use `RUNBOOK_GRADING.md` (ADR-107).**
> **Corrections made in Z2a (2026-10-14), deployed with Z2b:** step 3 passes `--skip-deploy`; 5e reads the
> image tag at the service template; 5f and 5f-2 read the Cloud SQL annotation; step 6 runs the extended
> `verify.py` (all six services); step 7 states its scope and credentials; Windows PowerShell 5.1 notes are
> added; `/healthz` is replaced by `/health` for reachability and step 12 measures the cold start as a
> timed question plus the per-hop `request` lines; `plan_full.py` resolves `gcloud` without a shell.
> **Still open:** enabling the build trigger and its docs-only merge check (step 8; only after the
> paid-mode YAML sync is merged, ADR-104 note); the retried-call logging reaches the deployed services
> with ADR-108 in Z2b.

Written 2026-10-12 in Prompt U; **revised the same day in Prompt U2 (ADR-100)**: sentiment is no longer
blocked, the window is two sittings, and the deploy is one service at a time (R-20).
**Nothing here had been run against GCP when this was written (it has since, see the note above).** Every step has a
verification command and its expected output. Every `gcloud` command carries `--project`.
PowerShell, from the repo root, with `.venv` built (`uv sync --locked --all-packages --all-extras`).

```powershell
$P  = 'a2a-agentic-service-ops-gcp'
$R  = 'us-central1'
$N  = '587647038690'                       # project number
$DB = "${P}:${R}:ops-db"
$G  = "https://ops-gateway-$N.$R.run.app"  # the gateway; compare with step 5g before inviting anyone
```

## What is decided and what is not

- **Decided (ADR-100, resolves R-19): `ops-sentiment` deploys with the other five, reading stored
  predictions only.** `mcp-feedback` runs in scoring mode `stored_only` from the weight-free `stored`
  image target: no torch, no weights, no bucket. It answers only if every comment in range has a stored
  prediction under the manifest's model version, and otherwise fails closed (`predictions_incomplete`,
  shown to the user as "The data service is unavailable right now."). **That is why step 4 (the backfill
  and its fingerprint) must pass before sentiment deploys, and why it is never skipped or reordered.**
  If the fingerprint does not match, sentiment does not deploy: pass `_DEPLOY_SENTIMENT=false` in 5b and
  the other five proceed.
- **Client-IP rule on Cloud Run** (note under ADR-097). *Updated 2026-10-14:* step 5h ran on 2026-10-13 and the logged `remoteIp` was the caller's real address, not the spoofed one, which is consistent with the rule. The evidence is Cloud Run's logged `remoteIp` only, so it is observed, not documented; it stays a stated limit (L-88).
- **Prices:** the Google pricing pages could not be read (see Costs); figures there are estimates.

## The two sittings

| | Sitting 1 (planned Thu 2026-10-15, about 1.5 h; **ran 2026-10-12**) | Sitting 2 (planned Fri 2026-10-16, about 2.5 h; **ran 2026-10-13**) |
|---|---|---|
| Steps | 0 pre-flight (including Next.js), 1 start `ops-db`, 2 secrets, 3 service accounts and bindings, 4 backfill and its fingerprint, then stop `ops-db` | 0b to 0f again, start `ops-db`, re-run the fingerprint, then 5 deploy and everything after |
| Estimated | about 70 min (details under Time) | about 185 min in full; **about 140 min** without the three deferrable items (step 7, step 12's second idle wait, step 8's merge check) |
| Gate to leave | step 4's fingerprint equals the local value **exactly**; if not, stop: sentiment does not deploy | `verify.py` and 5d to 5f pass |

At the end of sitting 1, stop `ops-db` (End of window) **unless sitting 2 follows the same day**. Sitting 1
creates no Cloud Run service, so nothing serves and nothing needs the database overnight. Nothing in
sitting 1 depends on the order of the others except: 1 before 4 (the database must run), and 3 before 5
(propagation of IAM changes).

## 0. Pre-flight (before the window; no billing)

| # | Check | Command | Expect |
|---|---|---|---|
| 0a | The sentiment PR is reviewed and merged by the owner (sitting 2 builds from `main`; `feat/deploy-readiness` merged as #47) | `gh pr view feat/sentiment-stored-only --json state,mergedAt` | `MERGED` |
| 0b | On main, clean, suites green | `git switch main; git pull; git status --short; .venv\Scripts\python -m pytest tests/unit services -q` | no changes; all pass |
| 0c | The two images that bake the parameter files build locally | `docker compose build mcp_volume agent_qa` | `Built` for both |
| 0d | ID token and gcloud identity | `gcloud config get-value account; gcloud auth print-access-token --quiet \| Out-Null; $LASTEXITCODE` | the owner; `0` |
| 0e | `allUsers` is permitted by org policy | `gcloud resource-manager org-policies describe iam.allowedPolicyMemberDomains --effective --project $P` | `allValues: ALLOW` (read 2026-10-12) |
| 0f | Trigger exists, disabled | `gcloud builds triggers describe deploy-reporting-slice --region $R --project $P --format="value(disabled)"` | `True` |

**Next.js (the out-of-band security release announced for 2026-10-14).** Today's pin is 16.3.8
(sprint log, 2026-10-12). At the window:

```powershell
npm view next dist-tags --json                                   # what is `latest`
Invoke-RestMethod "https://api.github.com/repos/vercel/next.js/security-advisories?per_page=10" |
  Select-Object ghsa_id, published_at, severity, @{n='patched';e={$_.vulnerabilities.patched_versions}}
```

- **Released and an advisory names the patched version `X`:** set `"next": "X"` in `web/package.json`,
  raise the minimum in `web/scripts/check-next-version.mjs`, then
  `cd web; npm install --package-lock-only; npm ci; npm run build; npm audit --omit=dev --audit-level=high`.
  Expect `found 0 vulnerabilities`. Commit, push, merge before step 5.
- **Not released, or no advisory confirms a patched version:** deploy 16.3.8 and record it in the sprint
  log. A gateway-only redeploy later changes no answer (only `ops-gateway` is rebuilt; the other services'
  images are unchanged).
- The sprint log's tag URL `https://nextjs.org/blog/tag/security` is dead (404 on 2026-10-12). The
  sources used are the GitHub Security Advisories API for `vercel/next.js` and the npm registry; a dated
  note under that item says so.

## 1. Start `ops-db` (about 5 min)

```powershell
gcloud sql instances patch ops-db --activation-policy ALWAYS --project $P
gcloud sql instances describe ops-db --project $P --format="value(state,settings.activationPolicy)"
```

Expect `RUNNABLE  ALWAYS`. Stop and roll back: nothing to roll back; `--activation-policy NEVER` stops it.

## 2. Secrets (about 5 min)

The session key is generated and piped straight in; it is never written to disk or the repo.

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))" |
  gcloud secrets create gateway-session-key --replication-policy automatic --data-file=- --project $P
'{"invites": []}' |
  gcloud secrets create gateway-invites --replication-policy automatic --data-file=- --project $P
gcloud secrets list --project $P --format="value(name)"
```

Expect the nine existing names plus `gateway-invites` and `gateway-session-key`. (`plan_full.py` does the
same two steps, skipping a secret that exists.) Roll back: `gcloud secrets delete <name> --project $P`
(nothing reads them yet).

## 3. Service accounts and bindings (about 10 min)

```powershell
.venv\Scripts\python deploy\plan_full.py --dry-run --phases 1,2,3,4,5 --skip-deploy   # read it first
.venv\Scripts\python deploy\plan_full.py --phases 1,2,3,4,5 --skip-deploy             # skips what exists
gcloud iam service-accounts list --project $P --format="value(email)"
gcloud secrets get-iam-policy gateway-invites --project $P
```

Expect `run-sentiment`, `run-forecast`, `run-qa`, `run-gateway` in the list, and `run-gateway` as the
only accessor of `gateway-invites`. IAM changes take a few minutes to propagate (it took over a minute
on 2026-10-08): wait before step 5. Roll back: `gcloud iam service-accounts delete <email>`; the
bindings go with it.

## 4. Backfill `sentiment_predictions` (about 25 min, mostly unattended)

`load.py` truncates predictions, so this follows any data load. It re-scores every comment with the
local weights (about 8 comments a second, 7,521 comments, about 15 min) and stores them as `app_sentiment`
for the model version equal to the manifest's SHA-256. It does **not** copy rows from the local database.
Needs `models\sentiment\bert_v1` locally (present on this machine).

Terminal A (leave open):

```powershell
cloud-sql-proxy $DB --port 5433
```

Terminal B:

```powershell
$env:POSTGRES_HOST = '127.0.0.1'; $env:POSTGRES_PORT = '5433'; $env:POSTGRES_DB = 'service_ops'
$env:DB_ROLE_SENTIMENT_USER = 'app_sentiment'
$env:DB_ROLE_SENTIMENT_PASSWORD = (gcloud secrets versions access latest --secret db-role-sentiment-password --project $P)
$env:MODELS_DIR = 'models/sentiment/bert_v1'; $env:MANIFEST_PATH = 'ml/sentiment/artifacts/bert_v1.manifest.json'
.venv\Scripts\python -m mcp_feedback.backfill
```

Expect log lines ending `backfill done ... "complete": true`, exit code 0. Then the check:

```powershell
$env:DB_ROLE_EVAL_USER = 'app_eval'
$env:DB_ROLE_EVAL_PASSWORD = (gcloud secrets versions access latest --secret db-role-eval-password --project $P)
.venv\Scripts\python scripts\predictions_fingerprint.py
```

**Expected output (recorded locally on 2026-10-12):**

```
"model_version": "0fa27f641d95260d84b4742501dd47cade23f1f8ae0ff336d8cbf927f70333ad",
"rows": 7521,
"sha256": "a340b82d8af178173afae34cb17bb7f2a1e3a944baa879321f34c4ac137e259f"
```

The hash covers `feedback_id|label|confidence (4 places)|flagged`, ordered by `feedback_id`, with no
timestamps. **It must equal the local value exactly (count and hash). If it does not, stop: sentiment
does not deploy** (ADR-100). A different count means the cloud data differs from local (rerun README
step 8's dataset hash check); the same count with a different hash means scoring differs (check the
library versions, then the model version). Record the output in the sprint log. A **second** check of
the same output is made at the start of sitting 2 (step 5, "Before the build"): the deploy follows a
fingerprint taken that day. Unblocks (they skip without stored predictions):
`tests/integration/test_golden_oracles.py` (sentiment oracle), `test_qa_baseline.py` and
`test_qa_sentiment_agrees.py`, and the `mcp_feedback` and `agent_sentiment` figure suites.
Roll back: `DELETE` is not available to `app_sentiment`; rerunning `load.py` truncates the table.

## 5. Deploy (about 45 min, mostly the build)

**Before the build (sitting 2): the fingerprint again.** Sitting 2 is a new day and a new shell: start
`ops-db` (step 1's two commands), open Terminal A (`cloud-sql-proxy $DB --port 5433`), and in Terminal B
set the variables again (step 4's `POSTGRES_*` lines, `$P`/`$R`/`$N`/`$DB` from the top of this file, and
`DB_ROLE_EVAL_USER` / `DB_ROLE_EVAL_PASSWORD` from Secret Manager), then run
`.venv\Scripts\python scripts\predictions_fingerprint.py`. It must print the same `rows` and `sha256`
as step 4. Only then run 5b with `_DEPLOY_SENTIMENT=true` (the committed value). If it differs, run 5b
with `--substitutions _RUN_VERIFY=false,_DEPLOY_SENTIMENT=false`: the other five deploy and sentiment
answers "The data service is unavailable right now." **That override is for this one run only.** The
imported trigger carries `_DEPLOY_SENTIMENT: "true"`, so once step 8 enables it, the first merge to
`main` would deploy sentiment with no matching fingerprint. On a mismatch, before step 8, make the
trigger say `"false"` too (step 8 has the command), and put it back to `"true"` only after a fingerprint
that matches.

**Services are deployed one at a time (R-20).** `cloudbuild.yaml` chains the six deploy steps with
`waitFor` (QA, sentiment, forecast, reporting, orchestrator, gateway), and `deploy_service.py` waits for
each Cloud Run operation to finish before it exits. The definitions set no `traffic` block, so traffic
follows the latest ready revision, and the operation is done when that revision is serving. The next
service therefore starts only after the previous one is on its new revision. That is the mechanism, not
a measurement: 5e checks `traffic=100` on the ready revision for all six afterwards. **If a deploy is ever run by hand, run it the same way: one
service, wait for `latestReadyRevisionName` to hold `traffic=100`, then the next.**

Worst-case connections against `max_connections` = 60 (pool 2 + overflow 2 = 4 per instance; four
DB-connected services at `max_instances` 2; ADR-099's arithmetic):

| Moment | Instances holding a pool | Connections | Plus 10 reserved/admin | Plus 4 owner sessions |
|---|---|---|---|---|
| Steady state, all four at 2 | 4 × 2 = 8 | 32 | 42 | 46 |
| **One service mid-deploy** (its old and new revision at 2 each; the other three at 2) | 3 × 2 + 4 = 10 | **40** | **50** | **54** |
| Before this change: all four mid-deploy at once (ADR-099's ceiling) | 16 + 16 | 64 | 74 | 78 |

So the worst case under sequential deploys is **54 of 60 (headroom 6)**, and 50 with no owner session
open: the proxy from step 4 is idle during the build, and the backfill (which opens at most 4) is long
finished. It is a bound, not an expectation: a pool opens connections on demand, and a revision that has
no traffic yet holds none. The stop rule is unchanged: any `too many connections` in a service log.

**5a. Apply the full trigger (still disabled) and check what was imported:**

```powershell
gcloud builds triggers import --source deploy\trigger_full.yaml --region $R --project $P
gcloud builds triggers describe deploy-reporting-slice --region $R --project $P --format="yaml(disabled,includedFiles,ignoredFiles,substitutions)"
```

Expect `disabled: true`, the nine `includedFiles` and four `ignoredFiles` of `trigger_full.yaml`, and
`_DEPLOY_SENTIMENT: 'true'`. If the import rejects the file's format, `describe` the live trigger as
YAML, copy the new filters and substitutions onto it, and import that.

**5b. One run, with verification skipped (checks 4 and 6 need the invoker bindings, which need the
services):** if `run` refuses a disabled trigger, enable it first with the command in step 8 (the
consequence: a merge to `main` then deploys, which is intended while `ops-db` runs).

```powershell
gcloud builds triggers run deploy-reporting-slice --branch main --region $R --project $P `
  --substitutions _RUN_VERIFY=false
gcloud builds list --region $R --project $P --limit 1 --format="value(id,status,substitutions.COMMIT_SHA)"
```

Expect `SUCCESS` after about 25 to 40 min (nine parallel image builds on `E2_HIGHCPU_8`; the gateway
build runs `npm ci`, the version check and `npm audit`; the sentiment image is the `stored` target, so
it does not install torch and is the smallest of the MCP images). Roll back: nothing is serving the new tag yet
except the two existing services' new revisions; see "Rollback".

**5c. Invoker bindings, now that the services exist:**

```powershell
.venv\Scripts\python deploy\plan_full.py --phases 6 --skip-deploy
gcloud run services list --region $R --project $P --format="value(metadata.name)"
```

Expect `ops-forecast`, `ops-gateway`, `ops-orchestrator`, `ops-qa`, `ops-reporting` and
`ops-sentiment` (no step prints SKIP (blocked)).

**5d. Who may invoke what:**

```powershell
foreach ($s in 'ops-gateway','ops-orchestrator','ops-reporting','ops-sentiment','ops-qa','ops-forecast') {
  "== $s"; gcloud run services get-iam-policy $s --region $R --project $P --format="value(bindings.members)"
}
```

Expect `allUsers` on `ops-gateway` only; `run-gateway` (and `build-deploy`) on `ops-orchestrator`;
`run-orchestrator` on the other four. Anything else: stop.

**5e. Every service's serving revision holds 100% of traffic (R-03):**

```powershell
foreach ($s in 'ops-gateway','ops-orchestrator','ops-reporting','ops-sentiment','ops-qa','ops-forecast') {
  $j = gcloud run services describe $s --region $R --project $P --format=json | ConvertFrom-Json
  "{0}: ready={1} traffic={2}" -f $s, $j.status.latestReadyRevisionName,
    (($j.status.traffic | ForEach-Object { "$($_.revisionName)=$($_.percent)" }) -join ',')
}
```

Expect, for each, `traffic=<the same revision as ready>=100`, and the image tag equal to the build's
`COMMIT_SHA`. **Read the tag at the service template, not at a revision:** a revision's image fields show
digests, which is why the first run of this check could not compare them (2026-10-13).

```powershell
$sha = (gcloud builds list --region $R --project $P --limit 1 --format="value(substitutions.COMMIT_SHA)")
foreach ($s in 'ops-gateway','ops-orchestrator','ops-reporting','ops-sentiment','ops-qa','ops-forecast') {
  $j = gcloud run services describe $s --region $R --project $P --format=json | ConvertFrom-Json
  foreach ($c in $j.spec.template.spec.containers) {
    "{0}/{1}: tag matches build={2}" -f $s, $c.name, $c.image.EndsWith(":$sha")
  }
}
```

Expect `True` on every container (`deploy/verify.py` makes the same check for all six services).
**Stop and roll back** a service whose ready revision does not hold 100%.

**5f. The sockets and secrets are where ADR-099 says:**

Cloud Run's v2 resource shows the Cloud SQL socket as an **annotation** on the service template
(`run.googleapis.com/cloudsql-instances`), not as a volume mount on a container (found 2026-10-13):

```powershell
foreach ($s in 'ops-gateway','ops-orchestrator','ops-reporting','ops-sentiment','ops-qa','ops-forecast') {
  $j = gcloud run services describe $s --region $R --project $P --format=json | ConvertFrom-Json
  $a = $j.spec.template.metadata.annotations.'run.googleapis.com/cloudsql-instances'
  "{0}: cloudsql={1}" -f $s, $a
}
```

Expect `<project>:us-central1:ops-db` on `ops-reporting`, `ops-sentiment`, `ops-forecast` and `ops-qa`,
and nothing on `ops-gateway` and `ops-orchestrator` (exactly the four database services).

**5f-2. Sentiment carries no model (ADR-100):**

```powershell
gcloud run services describe ops-sentiment --region $R --project $P --format=json |
  ConvertFrom-Json | ForEach-Object { $_.spec.template.spec.containers | Where-Object name -eq 'mcp-feedback' |
    ForEach-Object { "mem={0} scoring={1} volumes={2}" -f $_.resources.limits.memory,
      (($_.env | Where-Object name -eq 'MCP_FEEDBACK_SCORING').value),
      (($_.volumeMounts | ForEach-Object { $_.name }) -join ',') } }
```

Expect `mem=512Mi scoring=stored_only volumes=` (empty: the socket is the annotation of 5f, not a
volume; read 2026-10-14). Then the container's log must say the artifact
was verified with `"scoring_mode": "stored_only"` and `"files"` of the manifest, and contain no
`model loaded` line:
`gcloud logging read "resource.labels.service_name=ops-sentiment AND resource.labels.container_name=mcp-feedback" --limit 20 --project $P`.

**5g. The gateway's origin is the URL invites will carry:**

```powershell
gcloud run services describe ops-gateway --region $R --project $P --format="value(status.url)"
```

Expect it to equal `$G`. If Cloud Run reports a different host (`...-uc.a.run.app`), set
`GATEWAY_PUBLIC_ORIGIN` in `deploy/cloudrun/gateway.yaml` to that value, redeploy the gateway only, and
use that host as `--base-url` below; the `Origin` check refuses any other.

**5h. The client-IP rule (note under ADR-097):**

```powershell
$body = '{"token":"not-a-real-token"}'
1..2 | ForEach-Object {
  try { Invoke-WebRequest -Method Post -Uri "$G/auth/exchange" -ContentType 'application/json' `
        -Headers @{ Origin = $G; 'X-Forwarded-For' = '203.0.113.7' } -Body $body -UseBasicParsing | Out-Null }
  catch { "status " + $_.Exception.Response.StatusCode.value__ }
}
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=ops-gateway AND httpRequest.requestUrl:/auth/exchange" `
  --limit 2 --project $P --format="value(httpRequest.remoteIp)"
```

Expect `status 401` twice. `remoteIp` is the connecting address Cloud Run logged. The gateway keys its
sign-in limit by the last `X-Forwarded-For` entry: if that is the logged `remoteIp` and not `203.0.113.7`,
the rule holds (add a dated note under ADR-097). If it is `203.0.113.7`, set
`GATEWAY_TRUSTED_PROXY_HOPS` accordingly and record the fix. Either way it is a stated limit (L-88).

## 6. Verification run from the owner's machine (about 10 min)

```powershell
$env:PROJECT_ID = $P; $env:PROJECT_NUMBER = $N; $env:REGION = $R
$env:EXPECTED_IMAGE_TAG = (gcloud builds list --region $R --project $P --limit 1 --format="value(substitutions.COMMIT_SHA)")
$env:ORCHESTRATOR_SA = "run-orchestrator@$P.iam.gserviceaccount.com"
$env:REPORTING_SA = "run-reporting@$P.iam.gserviceaccount.com"
$env:PROBE_SA = "probe-noauth@$P.iam.gserviceaccount.com"
$env:CLOUD_SQL_INSTANCE_NAME = 'ops-db'
.venv\Scripts\python deploy\verify.py --ipv4
```

*Updated 2026-10-15 (S6-T1): `--ipv4` because this runs from the owner's PC, where IPv6 to `*.run.app`
black-holes (PowerShell notes below). Leave it off from a machine where IPv6 works.*

Expect `PASS` on every line and exit 0. *Updated 2026-10-14 (Z2a): `verify.py` now covers all six
services: for each, the exact invoker set (ADR-099), the dedicated service account, 100% of traffic on the
latest ready revision with the image tag read at the template, and paid mode on exactly the five
model-calling containers (ADR-104). The end-to-end question stays one question.* Steps 5d to 5f are the
same checks by hand. Check 6 makes two model calls (free tier when written; the paid key since 2026-10-13, ADR-104).

## 7. Real-data suites on Cloud SQL (L-78) (about 20 min)

*Updated 2026-10-14 (Z2a): scope and credentials.* Run **only** the sentiment figures suite and
`tests/integration/test_qa_sentiment_agrees.py` here, and only if their fixtures run with read-only roles
and without the superuser (`sprint-log.md`, the Z2a note of 2026-10-14, records what was found). The
whole `tests/integration` run needs `POSTGRES_ADMIN_*` (the grants suite creates and drops objects), and
running fixtures with superuser rights against the evaluation database was refused on 2026-10-13. A run
that needs it stays deferred; do not export `POSTGRES_ADMIN_*` into this shell to make it pass. Windows
PowerShell 5.1 has no `pwsh` and turns an unquoted comma list into an array: quote them.

With the proxy from step 4 still running:

```powershell
$env:POSTGRES_HOST = '127.0.0.1'; $env:POSTGRES_PORT = '5433'; $env:POSTGRES_DB = 'service_ops'
foreach ($r in 'reporting','sentiment','forecast','qa','eval','generator','train') {
  Set-Item "env:DB_ROLE_$($r.ToUpper())_USER" "app_$r"
  Set-Item "env:DB_ROLE_$($r.ToUpper())_PASSWORD" (gcloud secrets versions access latest --secret "db-role-$r-password" --project $P)
}
$env:REQUIRE_INTEGRATION_DB = '1'
# the scoped suites only (see the note above); never `tests/integration` as a whole from here
.venv\Scripts\python -m pytest tests/integration/test_agent_sentiment_figures.py tests/integration/test_qa_sentiment_agrees.py -q -rs
```

Expect no failures; the skips are the live-model ones only. A skip naming "no stored bert_v1
predictions" means step 4 did not finish: **stop**. (This suite does not call a model.) Then clear the
variables: `Get-ChildItem env: | Where-Object Name -like 'DB_ROLE_*' | ForEach-Object { Remove-Item "env:$($_.Name)" }`.

## 8. Enable the trigger (about 3 min)

From this point a merge to `main` that touches an image's inputs deploys all six services.

```powershell
(Get-Content deploy\trigger_full.yaml) -replace '^disabled: true', 'disabled: false' |
  Set-Content "$env:TEMP\trigger_enabled.yaml" -Encoding utf8
# Only if step 4's or the sitting-2 fingerprint did NOT match (see step 5, "Before the build"):
# (Get-Content "$env:TEMP\trigger_enabled.yaml") -replace '_DEPLOY_SENTIMENT: "true"', '_DEPLOY_SENTIMENT: "false"' |
#   Set-Content "$env:TEMP\trigger_enabled.yaml" -Encoding utf8
gcloud builds triggers import --source "$env:TEMP\trigger_enabled.yaml" --region $R --project $P
gcloud builds triggers describe deploy-reporting-slice --region $R --project $P --format="value(disabled)"
Remove-Item "$env:TEMP\trigger_enabled.yaml"
```

Expect `False` (the field prints empty or `False` when enabled; `True` means still disabled). Check that
a docs-only change cannot deploy: open a one-line change to `docs/sprint-log.md` as a PR, merge it, and
confirm no new build: `gcloud builds list --region $R --project $P --limit 1` shows the same id as
before. (The filter itself is tested offline in `tests/unit/test_deploy_trigger.py`.) Disable again:
repeat with `disabled: true`.

## 9. Invites (about 10 min)

```powershell
$S = "projects/$N/secrets/gateway-invites"
.venv\Scripts\python scripts\invites.py --secret $S create --label owner-laptop --days 14 --base-url $G
.venv\Scripts\python scripts\invites.py --secret $S create --label owner-phone  --days 14 --base-url $G
.venv\Scripts\python scripts\invites.py --secret $S create --label test         --days 1  --base-url $G
.venv\Scripts\python scripts\invites.py --secret $S list
```

Each `create` prints its link once (`$G/#invite=...`); copy them to a password manager, never the repo.
Expect `list` to show three `active` rows and no hash. *Updated 2026-10-14: on 2026-10-13 two invites were created, `owner-laptop` (14 days) and `test` (`docs/deploy-window-log.md`, sitting 3); `owner-phone` was not.* Roll back: `scripts\invites.py --secret $S revoke --id <id>`.

## 10. Valid, expired and revoked (about 10 min)

A helper for the three checks (the token is the part after `#invite=`):

```powershell
function Test-Invite($link) {
  $t = ($link -split '#invite=')[1]   # not .Split('#invite='): in 5.1 that splits on each character
  $b = @{ token = $t } | ConvertTo-Json -Compress
  try { (Invoke-WebRequest -Method Post -Uri "$G/auth/exchange" -ContentType 'application/json' `
        -Headers @{ Origin = $G } -Body $b -UseBasicParsing).StatusCode }
  catch { $_.Exception.Response.StatusCode.value__ }
}
Test-Invite '<the test invite link>'                  # valid: 200
```

- **Expired:** create one that lapses in about 90 seconds, wait, then test:
  `scripts\invites.py --secret $S create --label expired --days 0.001 --base-url $G`, wait 2 minutes,
  `Test-Invite '<link>'` expects `401`. (`--days 0` is refused by the script on purpose.)
- **Revoked:** `scripts\invites.py --secret $S revoke --id <the test invite's id>`, wait 70 seconds (the
  Secret Manager read is cached up to 60), `Test-Invite '<the test link>'` expects `401`, and a session
  cookie from before the revoke is refused on `/api/session` within the same window.
- A valid exchange sets `__Host-session` (`Secure; HttpOnly; SameSite=Strict`); the body of a failed one is
  identical for expired, unknown and malformed tokens.

## 11. Three smoke questions in the deployed UI (about 15 min; about 9 model calls; the paid key since 2026-10-13, ADR-104)

Open the owner's link in a browser. The Prompt T list was not in the repository, so these three stand
in; replace them with Prompt T's if different:

1. `What was SLA compliance in the Northeast last month?`. Expect "Interpreted as:" with the area
   (incident reporting), measure, `2026-07-01 to 2026-07-31` and Northeast; "Figures checked for the
   request as interpreted."; no follow-up flag. (The local run took 8.9 s warm, 3 model calls.)
2. `How many service requests should we expect over the next 4 weeks?`. Expect a forecast answer, the
   area "volume forecast", and a verification line (QA recomputes the served numbers on `ops-qa`).
3. `Is customer sentiment trending down in the West?`. Expect a sentiment answer with a trend ("no clear
   change" or a significant move), "Area: customer sentiment" in the "Interpreted as:" line, a count of
   comments that equals the range's (all scored: `complete`), and a verification line. **If it instead
   says "The data service is unavailable right now. Please try again later."**, read the `ops-sentiment`
   log for `stored predictions incomplete` (it carries `n_comments` and `n_scored`): that is a gap in the
   stored predictions (rerun step 4's fingerprint), not an outage.

Stop and roll back the gateway if any answer shows upstream text, a stack trace or an `Interpreted as:`
line that does not match the question.

## 12. Cold-start timings after 15 minutes idle (about 45 min elapsed, 5 min of work)

*Updated 2026-10-14 (Z2a): the original per-service `/healthz` loop does not work. Cloud Run's front end
reserves `/healthz` on a service's public URL (found 2026-10-13: an empty 404 on both gateway hosts), so
the request never reaches the container. The gateway's public reachability probe is now `GET /health`
(ADR-097 note). The cold start is measured as below.*

R-05: the 120 s request deadline against a cold chain (gateway, orchestrator, then reporting or forecast
and QA). Wait 15 minutes with no traffic, then:

1. **Reachability, not a timing:** `Invoke-WebRequest "$G/health" -UseBasicParsing` returns 200 with
   `{"status":"ok"}` (the gateway only; the other five are not public).
2. **The timed first question**, through the UI or with a session cookie, as on 2026-10-13: note the
   elapsed time of one real question end to end.
3. **Where the time went**, once ADR-108 is deployed: read the question's `request` access lines by its trace
   id (the `X-Trace-Id` response header, or the `trace_id` the answer's log line carries). Each service
   writes one with `duration_ms`; the first request to a cold instance shows the start-up in that number.
   ```powershell
   gcloud logging read "resource.type=cloud_run_revision AND jsonPayload.trace_id=`"<trace_id>`" AND jsonPayload.msg=`"request`"" --project $P --format="table(jsonPayload.service,jsonPayload.path,jsonPayload.status,jsonPayload.duration_ms)"
   ```
   The field names are those of the services' JSON lines (`packages/common/src/common/logging.py`); Cloud
   Run turns stdout JSON into `jsonPayload`. *Confirmed 2026-10-14 (Z2b) against the deployed revisions:*
   the keys are `jsonPayload.trace_id`, `.service`, `.logger`, `.level`, `.msg` and `.ts` on every line;
   the access line is `logger=access`, `msg=request`, with `.method`, `.path`, `.status` and `.duration_ms`.
   The trace ID is empty on server start-up lines only. A request's other lines carry `.outcome`, `.route`,
   `.verdict`, `.cost_usd` and `.code` (a failed task); a question and a route reason appear only as
   `.question_chars`, `.reason_chars` and `.reason_sha`.
   Before ADR-108 is deployed, read the instance start-ups from the logs as on 2026-10-13
   (`docs/deploy-window-log.md`, sitting 3).

Record the end-to-end time and the per-hop durations. Then wait 15 minutes again and repeat the timed
question once. **Pass:** the end-to-end time is well under 120 s, and the real question returns an answer
(not the time-limit degraded result).
A service over 40 s alone: record it under R-05 and consider `min_instances=1` for it (cost below). The
sentiment sidecar no longer hashes 438 MB or loads a model (ADR-100): its start-up is a manifest read and
one database ping, so it should be in line with `ops-reporting`. If it is not, that is a finding.

## Windows PowerShell 5.1 notes (added 2026-10-14, Z2a)

Every command here is written for Windows PowerShell 5.1 (`powershell.exe`); `pwsh` is not assumed.

- **Quote every comma list.** `--update-env-vars "LLM_MODE=paid,LLM_MAX_REQUESTS=1500"`. An unquoted
  `A=1,B=2` is an array in 5.1; it turned `LLM_MODE` into one space-joined string on 2026-10-13 and the
  fail-fast config refused to start (`docs/deploy-window-log.md`, sitting 3). The same applies to
  `--phases 1,2,3`.
- **Split with `-split`, not `.Split('abc')`.** In 5.1 `.Split('abc')` splits on each of the characters.
  Step 10's helper uses `-split '#invite='` for that reason.
- **`gcloud` is `gcloud.cmd`.** `plan_full.py` and `verify.py` resolve it with `shutil.which` and start it
  with no shell; do not add `shell=True` back.
- **No `&&` or `||`.** Chain with `;` and test `$?`, or use separate commands.
- **Avoid `2>&1` on a native program.** In 5.1 it wraps each stderr line in an error record and sets `$?`
  to false even on exit code 0.
- **Write files that other tools read with `-Encoding utf8`** (`Set-Content` defaults to the ANSI code page).
- **IPv6 to `*.run.app` can black-hole from the owner's machine (found 2026-10-14, Z2b).** `curl -4` to
  the gateway's `/health` answered 200 while `curl -6` timed out, and `verify.py`'s end-to-end call
  (Python `urllib`, which tries IPv6 first) hung for about 35 minutes with a socket in `SynSent` to a Google
  `2600:1900:` address. Test with `curl.exe -4 -m 20 $G/health` before a window. If only IPv4 answers, run
  `verify.py` with `--ipv4`, which opens every HTTP connection over IPv4 only:
  `.venv\Scripts\python deploy\verify.py --ipv4`. Each `gcloud` call also took 1 to 4 minutes that day, so
  the six-service `verify.py` ran about 40 minutes. It now prints a line naming each `gcloud` call before
  it starts and each check's line as it finishes, so a slow call shows as a gap after its `INFO` line.
  Each call is cut off after 300 s (`--gcloud-timeout 600` raises that) and becomes a `FAIL` line; the run
  carries on with the checks that do not need it. A connect to `*.run.app` waits 10 s per address and
  is a `FAIL  ...: connect timeout` line if no address answers. The options are specified in
  `deploy/README.md`, "Window-day options".
  *Updated 2026-10-15 (S6-T1): the temporary wrapper (a script in `$env:TEMP` that set
  `socket.getaddrinfo` to `AF_INET` and called `runpy.run_path`) is replaced by `--ipv4`; no wrapper is
  needed.*

## Rollback (per service)

```powershell
gcloud run revisions list --service <svc> --region $R --project $P --format="table(metadata.name,status.conditions[0].status,metadata.creationTimestamp)"
gcloud run services update-traffic <svc> --to-revisions <previous-revision>=100 --region $R --project $P
gcloud run services describe <svc> --region $R --project $P --format="value(status.traffic[0].revisionName)"
```

Expect the last command to print `<previous-revision>`. For `ops-orchestrator` and `ops-reporting` there is a
previous revision (00004). For a service created in this window there is none: "roll back" means remove its
invoker binding (`gcloud run services remove-iam-policy-binding`), and leave the service, or delete it
(`gcloud run services delete <svc> --region $R --project $P`; ask first).

| At step | Stop and roll back when |
|---|---|
| 1 | the instance is not `RUNNABLE` within 10 min: stop; nothing to undo |
| 2, 3 | a binding or secret is wrong: fix it; nothing is serving yet |
| 4 | the count or hash differs: do not deploy sentiment (`_DEPLOY_SENTIMENT=false`); the rest can proceed |
| 5b | the build fails: read its log; nothing new serves (a failed deploy step leaves the old revision) |
| 5e | a revision is not at 100%: update traffic to the previous revision (R-03), then investigate |
| 6 | any `FAIL`: roll the failing service back; the others stay |
| 10 | a revoked or expired invite is accepted: disable the gateway's public binding at once (`remove-iam-policy-binding ... allUsers`) and revoke every invite |
| 11 | an answer shows upstream text: roll the gateway back |
| 12 | over the deadline: not a rollback; record R-05 and decide on `min_instances` |

The 2026-10-14 stop rule (ADR-078) is unchanged: if the revisions are not verified serving at the end of
2026-10-14, record R-03 as realised. *Updated 2026-10-14: met; the six revisions were verified serving at 100% on 2026-10-13 and R-03 is closed.*

## End of window

```powershell
gcloud sql instances patch ops-db --activation-policy NEVER --project $P
gcloud sql instances describe ops-db --project $P --format="value(state,settings.activationPolicy)"
```

Expect `STOPPED  NEVER`. Do this **at the end of sitting 1** (unless sitting 2 follows the same day) and
again at the end of sitting 2. **Leave it running** only if a grading window is open (Costs, below). Then
disable the trigger again (step 8's command with `disabled: true`) unless the database is staying up:
while `ops-db` is stopped a merge would deploy revisions that fail readiness (ADR-083). Stop the
Auth Proxy, and remove the `DB_ROLE_*` variables from the shell.

## Time

**Sitting 1 (planned Thu 10-15, ran 10-12; plan 1.5 h)**

| Step | Minutes |
|---|---|
| 0 pre-flight (incl. Next.js check) | 15 |
| 1 start the database | 5 |
| 2 secrets | 5 |
| 3 accounts and bindings (+ propagation wait) | 15 |
| 4 backfill and fingerprint | 25 |
| stop `ops-db` | 3 |
| **Sitting 1** | **about 68 (1 h 10 min), 20 min of slack in the 1.5 h** |

**Sitting 2 (planned Fri 10-16, ran 10-13; plan 2.5 h)**

| Step | Minutes |
|---|---|
| 0b to 0f again, start `ops-db`, proxy, fingerprint again | 15 |
| 5 build, one-at-a-time deploy, bindings, checks 5a to 5h (+ 5f-2) | 55 |
| 6 verify.py | 10 |
| 7 integration suites (**deferrable**) | 20 |
| 8 trigger, docs-only check (the merge check is **deferrable**, 5) | 10 |
| 9 invites | 10 |
| 10 valid, expired, revoked | 10 |
| 11 smoke questions | 15 |
| 12 cold starts (2 x 15 min idle; the second wait is **deferrable**, 20) | 40 |
| **Sitting 2** | **about 185 (3 h 5 min); about 140 (2 h 20 min) without the deferrable items** |

That does not fit 2.5 h in full: the three deferrable items (45 min) are what moves out. They need only
the database running, a merge, or a second idle wait; none of them is on the path that makes the system
serve. The part that must not split is 5 to 6 (the database is running and the trigger is off). Total
across both sittings, nothing deferred: about 253 min, 18 more than the single window of the first
runbook, from the second database start, the second fingerprint and the stop.

## Costs (estimate)

**The official pricing pages could not be read in this work.** The four pages (Cloud SQL
https://cloud.google.com/sql/pricing, Cloud Run https://cloud.google.com/run/pricing, Secret Manager
https://cloud.google.com/secret-manager/pricing, Cloud Build https://cloud.google.com/build/pricing) are
client-rendered: on 2026-10-12 a fetch returned 73 characters (the page title). The `docs.cloud.google.com`
variants redirect back to them, and `docs.cloud.google.com/secret-manager/docs/pricing` returned 404. What
was read: https://docs.cloud.google.com/sql/docs/postgres/start-stop-restart-instance (2026-10-12):
"Stopping an instance suspends instance charges" and "charges for storage and IP addresses continue to
apply." `ops-db` is `db-f1-micro`, Enterprise, zonal, 10 GB SSD, no backups, no autoresize (read with
`gcloud sql instances describe`, 2026-10-12). Confirm every figure below in the console's Billing > Reports
(filter label `component: deploy`) after the first day.

| Item | Estimate (**unverified**; the handoff's figure where there is one) |
|---|---|
| `db-f1-micro` running | about $0.30 a day (the handoff's number; not verified) |
| 10 GB SSD, running or stopped | on the order of $0.05 to $0.06 a day (list price recalled at about $0.17 per GB-month) |
| Cloud Run, `min_instances=0` | $0 compute while idle; requests at this volume fall inside the monthly free tier (recalled: 2 M requests, 180,000 vCPU-seconds, 360,000 GiB-seconds) |
| Secret Manager, about 100 accesses a day | about 3,000 a month, inside a recalled free tier of 10,000; active versions about $0.06 each a month beyond a free few: cents a month |
| `min_instances=1` on the gateway and the orchestrator (**option; not applied**) | an idle instance bills at a reduced rate; at 1 vCPU and 512 MiB, recalled at about $0.3 a day each, so about $0.65 a day for both |
| Cloud Build, one full build on `E2_HIGHCPU_8` | about 15 to 25 min; recalled at $0.016 a minute: $0.25 to $0.40 a build; the monthly free minutes apply to the default machine only |

**Grading window with `ops-db` running (database about $0.36 a day with storage; everything else
about $0.01 to $0.05):** **7 days about $2.5 to $3; 14 days about $5 to $6**, plus about $1 for builds
and any option above. Both are an order of magnitude under the $50 and $80 budget alerts (ADR-078).
*Updated 2026-10-14:* model calls were free tier (ADR-029) when this was written; the free tier failed on 2026-10-13 and the deployed system runs on the paid key (ADR-104). Measured: `verify.py`'s three paid calls cost about $0.0015, and Sprint 5's paid use is about $0.61 in list-price estimates (`sprint-log.md`, Sprint 5 close). The estimate above covers Cloud services only.

Idle storage while stopped: about $0.06 a day, so about $1.80 a month: stop `ops-db` between windows
and delete nothing.
