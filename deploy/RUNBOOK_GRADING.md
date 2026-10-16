# Runbook: open and close a grading window (ADR-107, extends ADR-105)

Written 2026-10-14 (Z1). Owner-decided 2026-10-14; assistant-drafted. Not yet run: the first use is
Window A (2026-10-31 to 2026-11-09). Windows PowerShell 5.1, from the repo root, with `.venv` built.
Every `gcloud` command carries `--project`. Every comma list is quoted (an unquoted comma is an array in
5.1; it broke `--update-env-vars` on 2026-10-13, `docs/deploy-window-log.md`).

> **Hard rule (Z2a, 2026-10-14): the build trigger may be enabled only after the paid-mode YAML sync (ADR-104 note of 2026-10-14) is merged to `main`.** Until then the repo definitions and the deployed services differ, and the first deploy would revert five services to the free key.
>
> **Warning: never enable the build trigger `deploy-reporting-slice` while `deploy/cloudrun/*.yaml` still
> say `LLM_MODE: free`.** The first deploy after an enable would redeploy the five model-calling
> services on the free key and silently revert ADR-104. The order is fixed in Z2: sync the YAML to paid
> first, then enable. This runbook never enables the trigger. Check it is still disabled (below).

```powershell
$P  = 'a2a-agentic-service-ops-gcp'
$R  = 'us-central1'
$N  = '587647038690'
$G  = "https://ops-gateway-$N.$R.run.app"   # the deterministic host: the only one invites may carry
$S  = "projects/$N/secrets/gateway-invites"
```

The windows (ADR-107): **A** 2026-10-31 to 2026-11-09; **B** 2026-12-01 to 2026-12-12.

## Open the window (do it the day before, or the morning of the start)

1. **Check the paid balance (owner, in the console; there is no API).** Billing > the paid project's
   prepaid balance. If under $5, top up to $5 or more. Auto-reload stays off (ADR-105). Note the balance
   and the date for the log (step 3 of closing).

2. **Start `ops-db` and wait for `RUNNABLE ALWAYS`.**
   ```powershell
   gcloud sql instances patch ops-db --activation-policy ALWAYS --project $P
   do {
     $state = gcloud sql instances describe ops-db --project $P --format "value(state,settings.activationPolicy)"
     $state
     if ($state -notmatch 'RUNNABLE') { Start-Sleep -Seconds 15 }
   } while ($state -notmatch 'RUNNABLE')
   ```
   Expect `RUNNABLE  ALWAYS`.

3. **Create the grader's invite, expiring at the window's end.** `--base-url` is the deterministic host
   (`$G`), never `status.url`. `--days` may be fractional; compute it to the end of the window's last day:
   ```powershell
   $end  = [datetime]'2026-11-09 23:59'                 # Window A; Window B: '2026-12-12 23:59'
   $days = [math]::Round(($end - (Get-Date)).TotalDays, 2)
   .venv\Scripts\python scripts\invites.py --secret $S create --label grader-A --days $days --base-url $G
   ```
   The link prints **once**. Copy it to a password manager. Never paste it into a chat, a commit or a
   document. Send it to the grader together with the window's start and end (ADR-105).

4. **Renew the owner's invite.** `owner-laptop` was created 2026-10-13 for 14 days (about 10-27). Create a
   new one covering the window, then revoke the old one by id from `list`:
   ```powershell
   .venv\Scripts\python scripts\invites.py --secret $S create --label owner-laptop --days $days --base-url $G
   .venv\Scripts\python scripts\invites.py --secret $S list
   .venv\Scripts\python scripts\invites.py --secret $S revoke --id <the old owner-laptop id>
   ```

5. **Smoke check.** In the browser, open the owner link and ask one question (for example "How many
   incidents last quarter?"). Expect an answer with an "Interpreted as:" line and a verification line. A
   first answer after idle can take about 56 s (cold start, 55.87 s on 2026-10-13; the deadline is 120 s).
   Reachability alone is `Invoke-WebRequest "$G/health" -UseBasicParsing` (200, `{"status":"ok"}`).
   `/healthz` does not work on the public URL: Cloud Run's front end reserves it.
   Also confirm the trigger is still disabled (expect `True`):
   ```powershell
   gcloud builds triggers describe deploy-reporting-slice --region $R --project $P --format "value(disabled)"
   ```

## Close the window (the day after the end, no later)

1. **Revoke the grader's invite.** Find its id with `list` (labels, expiry and status; no hashes):
   ```powershell
   .venv\Scripts\python scripts\invites.py --secret $S list
   .venv\Scripts\python scripts\invites.py --secret $S revoke --id <the grader-A id>
   ```

2. **Stop `ops-db`.**
   ```powershell
   gcloud sql instances patch ops-db --activation-policy NEVER --project $P
   gcloud sql instances describe ops-db --project $P --format "value(state,settings.activationPolicy)"
   ```
   Expect `STOPPED  NEVER`. Outside a window the system answers every data question with "The data
   service is unavailable right now." That is the intended state (ADR-105), not a fault.

3. **Record the dates** in `docs/deploy-window-log.md`: the window's start and end, the paid balance at
   opening, when `ops-db` was started and stopped, and the invite ids opened and revoked (ids and
   labels only; never a link or a token).

4. **Read the logs for a failed model-call attempt** (read-only, no model call; S6-A1, 2026-10-16). Retry logging stays unverified on the deployed system until a natural retry happens (ADR-108), so look at every close. The message is `llm attempt failed`. PowerShell 5.1 needs the inner quotes escaped with a backslash (checked 2026-10-16: a backtick escape splits the filter at its spaces):
   ```powershell
   gcloud logging read 'resource.type=cloud_run_revision AND jsonPayload.msg=\"llm attempt failed\"' --project $P --freshness 7d --format json
   ```
   No output means no retry happened; record that in the window log. A line shows `attempt`, `http_status`, `kind`, `next_wait_s` and `elapsed_s`; if one appears, copy its trace id and tick the sprint-log item "Still not verified deployed".

## Reference

- **List the active invites, without hashes:**
  `.venv\Scripts\python scripts\invites.py --secret $S list`
- **Why the host matters:** `status.url` reports the legacy host `ops-gateway-vszrpegifq-uc.a.run.app`.
  Both hosts serve, but the gateway's Origin check accepts only the deterministic one, so a link built on
  the legacy host would load the page and fail the exchange (ADR-107; deploy-window log, 2026-10-13).
- **Caps (ADR-097, ADR-107):** 50 questions a day globally; per invite, 30 an hour (ADR-107; 15 in the revision deployed on 2026-10-13, until Z2b deploys this change).
  The counters are in process and reset on a cold start (L-88).
- **Reading one request's logs (confirmed 2026-10-14, Z2b):** take the `X-Trace-Id` response header, then
  `gcloud logging read "resource.type=cloud_run_revision AND jsonPayload.trace_id=`"<id>`"" --project $P --freshness 1h --format json`.
  Fields: `jsonPayload.trace_id`, `.service`, `.logger`, `.msg`, `.level`, `.ts`; access lines are
  `.msg=request` with `.path`, `.status`, `.duration_ms`; answers carry `.outcome` and `.route`; a failed
  agent task carries `.code`. Questions and route reasons are logged as `.question_chars`,
  `.reason_chars` and `.reason_sha` only. The trace ID is empty on start-up lines. `verify.py` calls the
  orchestrator directly, so the gateway is on a trace only for a question asked through the UI. Run it
  from the owner's PC with `--ipv4`, because the PC's IPv6 to `*.run.app` black-holes (Windows PowerShell
  notes in `RUNBOOK_V.md`):
  `.venv\Scripts\python deploy\verify.py --ipv4` (*updated 2026-10-15, S6-T1*).
- **Spend ceiling:** the prepaid balance and the daily cap. The per-process caps are not one (L-93).
- **If the balance runs out mid-window:** the paid key fails closed and answers degrade (R-21). Top up in
  the console; no redeploy is needed.
