# Owner verification session 1: summary (ADR-110)

Run 2026-10-15 instead of the planned 2026-10-17 (owner decision); plan otherwise unchanged
(`docs/session-plan-2026-10-17.md`). Owner present throughout. `ops-db` started T0 = 17:39:04 CDT
(owner-reported) and read `STOPPED NEVER` at 19:47:55 CDT. Deployed system: build `0dc5aae1`, commit
`9ab7c77`, unchanged at open and close. Evidence: `run-notes.md`, `ledger.json`,
`ledger.json.evidence.jsonl`, `verify-output.txt` (this folder). No stop rule fired.

## Results

| Scenario | Result | Evidence |
|---|---|---|
| S1-open: state check, `verify.py --ipv4` | PASS (35 PASS lines, 0 FAIL, exit 0) | `verify-output.txt` |
| TS-14-A | PASS: valid invite answered; no session 401 `sign_in_required`; made-up cookie 401; expired, revoked and unknown tokens each 401 with the identical body `invalid_invite` | driver evidence lines; owner paste |
| TS-14-B | PASS for orchestrator, reporting, sentiment, forecast, QA (unauthenticated GET / = 403 each). Tool servers are sidecars with no URL: not separately reachable | driver probe lines |
| TS-14-C | PASS: same five unauthenticated calls refused (403) | driver probe lines |
| TS-14-D | PASS within the recorded limit: `git grep` at `9ab7c77` 0 matches; tracked env file `.env.example` only; every key and password variable in six services is a `secretKeyRef`; `GATEWAY_INVITES_SECRET` is a literal Secret Manager resource name, not a value; 0 secret-pattern matches in deployed config. Built images not scanned | run-notes 3.1 |
| TS-16-D sentiment | PASS (61 s, then 30.64 s repeat; ceiling 120 s) | below |
| TS-16-D forecast | PASS (46 s) | below |
| TS-18-C | Answers PASS: 6 reporting + 1 forecast all 200 `answered`, `qa_status=verified`. Scaling clause FAIL: `ops-reporting` stayed at 1 instance (19 request lines), `ops-forecast` 1 (4). Weeks 5-8 served / 1-4 unserved not verified for this forecast (driver captures `answer_chars` only) | `ledger.json.evidence.jsonl`; instanceId on request lines |
| TS-18-D | PASS: 30 answered, the 31st HTTP 429 `session_limit`, driver verdict pass, no model call for the 31st, no gateway restart. Refusal wording not seen (code, not wording) | driver output; log read |
| TS-20-A | PASS: west SLA July 2026 95.35% (82 of 86), as-of 2026-08-30, "Interpreted as" and verification lines shown | trace `29972a25...` |
| TS-20-B | NOT RUN (no trigger without a deploy or fault injection; decision 4) | plan |
| TS-20-C | PASS: "2 comments (0.9%) low-confidence and flagged for review" shown with the 212-comment split | trace `2d737c70...` |
| TS-20-D | PASS: declined, clarify (two Priya matches listed), split each showed a clear message, no blank screen or raw error | owner paste |
| TS-20-E | NOT RUN: the interface was not opened for the notice check. None of the answer pages quoted in the session showed a synthetic-data notice. `05` §7 records it as known failing | n/a |
| S4 failure path | PASS: HTTP 422 `invalid_range`, not a 5xx | trace `2e3dc32a...` |
| 5b grader re-test | PASS: after revoke, old cookie got 401 `sign_in_required` | owner paste |

## Cold-start readings (TS-16-D, R-05)

Browser, tab opened before the idle and not reloaded, stopwatch from the Ask click. `duration_ms` from the
`msg=request` lines of the trace.

| # | Path | Idle before | Verified cold | Stopwatch | Gateway | Orchestrator | Specialist | QA |
|---|---|---|---|---|---:|---:|---:|---:|
| 2.2 | sentiment | ~15 min | orchestrator, sentiment, QA yes; **gateway no** (owner page reload ~3 min earlier) | 61 s | 61,488 | 50,071 | 1,606 (+ ~34 s start-up before it) | 1,611 |
| 2.5 | forecast | ~16 min | all four hops yes | 46 s | 44,198 | 38,463 | 1,423 (two container starts) | 1,039 |
| 2.8 | sentiment (repeat; rule: highest first reading) | ~15.5 min | all four hops yes | 30.64 s | 25,684 | 20,045 | 1,180 | 1,362 |

Reference from 2026-10-13: reporting 55.87 s in the browser, 54.47 s at the gateway. The reporting path
was also cold at TS-20-A (clean-profile window): owner timer 29 s, gateway 29,937 ms. Every reading was
inside the 120 s ceiling. The orchestrator hop's `duration_ms` includes the specialist's and QA's
start-up. The specialist's own request duration was 1.2 to 1.6 s in every trace; its start-up time is
visible only as the gap before `task received`.

## Failure-path log codes seen live

- Orchestrator `msg=agent task failed`: `agent=reporting`, `code=invalid_range`, `reason_chars=211`,
  `reason_sha`. No question text.
- Reporting agent `msg=task failed`: `code=invalid_range`, **`reason=` the full reason string**,
  including the tool's error text with the parsed dates and the dataset window.
- `mcp_incidents`: `msg=tool rejected input` (`error_type=outside_window`) and a
  `Tool 'get_sla_compliance' failed: ...` line carrying the tool error message.
- Gateway `msg=ask refused upstream`: `upstream_error=invalid_range`, `upstream_detail_chars`,
  `upstream_detail_sha`; status 422.
- Gateway refusals: 401 `sign_in_required`, 401 `invalid_invite`, 429 `session_limit`.
- Not exercised: `outcome=degraded`. Retry logging (`llm attempt failed`, ADR-108): 0 lines in the
  session (a read for `attempt failed` from 22:30Z returned nothing; the `llm call` lines read showed
`attempts=1`); no retry occurred, so ADR-108's retry logging is still not verified deployed.

## Grader-access result

New browser profile with no owner session, `session1-grader` link: exchange succeeded, the cookie showed
HttpOnly, Secure and SameSite=Strict (owner-read from DevTools), and the TS-20-A question was answered.
After the invite was revoked and 70 s passed, the old cookie got 401 `sign_in_required` and the page showed
"An invite link is required. Open the link you were sent to sign in." The `/api/session` response was not
separately pasted.

## Ledger totals

57 of 75 requests, $0.079 of $0.25 (driver ledger, charged at the highest seen cost when unknown).
By kind: answered 12 (5 tallied: the `verify.py` question and four browser questions; 7 from the TS-18-C
driver run), declined 33 (31 TS-18-D, counting the refused 31st, and 2 tallied TS-20-D), clarify 1, failure 1,
probe 7, exchange 3. Gateway-counted questions today: 45 of 50 (log count 15 before TS-18-D, plus 30).
Cost lines logged: 0.00145 (2.2), 0.001294 (2.5), 0.001383 (2.8), 0.001555 (TS-20-A), 0.000297 + 0.000659
(failure path, two calls).

## Balance before and after

- Before: **$7.88**, owner-read (Google AI Studio credit balance, topped up 2026-10-15).
- After: **not provided as a balance figure.** The owner reported at close: AI Studio total spend
  $2.12 for 2026-09-18 to 2026-10-15 (cumulative, not the session); GCP billing $4.50 cost minus $1.64
  savings = $2.86 total for 2026-10-01 to 2026-10-15 (cumulative, not the session). The session's own
  model spend is not separable from these figures.

## Stop rules that fired

None. 3.8a was evaluated twice (N = 7 before 3.5/3.7, N = 15 before TS-18-D, both not above 19). No
unexpected 5xx. The 4-hour limit was not reached (about 2 h 9 min).

## Deviations from the plan

- Run 2026-10-15 instead of 2026-10-17 (owner decision); results folder is `2026-10-15`.
- Two dead invite links (`session1-expired`, `session1-revoked`) were pasted into the chat by the owner;
  both were already expired or revoked; tokens were not written to any file.
- `owner-laptop` (`77782f3db080`) revoked at the close (owner decision: its session cookie reached the
  assistant chat in a screenshot); plan 6.1 said never. A fresh owner invite is the owner's, after 6.2.
- TS-20-E and the sentiment-repeat's gateway hop (see above) were not as planned.

## For the 05 revision

- TS-14-B: tool servers are sidecars with no URL; "each tool server" cannot be tried separately.
- TS-14-D: evidence is the repo and deployed-configuration check at `9ab7c77`; built images were not scanned.
- TS-18-C: "the reporting service scales up" did not hold at 6 concurrent requests (1 instance,
  concurrency 8, max 2). The forecast service stayed at 1. Independent scaling is not shown.
- TS-18-D: the 429 refusal is evidenced by code `session_limit` and HTTP 429, not by its wording.
- TS-20-B: not run, no trigger on the deployed system.
- TS-20-E: not observed in this session.
- TS-15-D wording: `agent_reporting`'s `task failed` line and `mcp_incidents` log the tool's error text
  (parsed dates, window); no question text. This differs from "no exception message".
- The clarification answer shows a verification line ("Figures checked for the request as interpreted")
  although no figures were produced.
- `05` §2's three-run rule was not applied (single run, decision 3); the 3.9 repeats were dropped.
- The first sentiment cold reading (61 s) and the repeat (30.64 s) differ by 30 s on the same path.

## 06 confirmations

1. **Scenarios: not fully confirmed.** TS-14-A, B (five services), C, D (with its limit), TS-18-D,
   TS-20-A, C, D pass. TS-18-C fails its scaling clause. TS-20-B and TS-20-E were not run. Evidence above.
2. **Cold starts: confirmed, with one caveat.** Sentiment (61 s, 30.64 s) and forecast (46 s) are all
   inside 120 s, and the second idle wait was taken. The first sentiment reading's gateway hop was not cold.
   Reporting was not re-measured on a cold chain; its second reading is the 29 s at TS-20-A.
3. **Grader access: confirmed.** Clean profile, exchange, answer, revoke, refusal, cookie flags as
   above. Not separately evidenced: the cookie name and the `/api/session` response body.
