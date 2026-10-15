# Session driver (ADR-110, owner verification session 1)

Spec for `scripts/session_driver.py`. Written before the code (Prompt S6-W1, 2026-10-15). The driver
sends owner-session traffic through the **deployed gateway**, counts every request in a ledger file
before it is sent, and writes one evidence line per request. It makes no model call itself; the gateway
and the services behind it do.

## What it relies on (verified in the repo, 2026-10-15)

| Fact | Where |
|---|---|
| An invite link is `<base>/#invite=<token>`; the token is exchanged with `POST /auth/exchange`, JSON body `{"token": ...}` | `scripts/invites.py:134`; `api_gateway/app.py:229-260` |
| Exchange needs `Origin` equal to the gateway's public origin and `Content-Type: application/json` | `api_gateway/app.py:193-200` |
| The session is the cookie `__Host-session` set by the exchange response | `api_gateway/session.py:13`; `app.py:250-258` |
| `/api/ask` reads that cookie, then needs the same `Origin` and JSON content type; body `{"question": ...}`, at most 500 characters | `app.py:203, 278-285, 38` |
| Hourly cap refusal: HTTP 429, body `{"error": "session_limit", "detail": "Too many questions this hour (limit 30). Please try again later."}` | `app.py:286-292` |
| Daily cap refusal: HTTP 429, body `{"error": "daily_limit", "detail": "Daily limit reached: ..."}` | `app.py:293-299` |
| Trace ID: response header `X-Trace-Id` on every response, and the body field `trace_id` of an answer | `common/logging.py:31`; `app.py:190`; `api_gateway/interpret.py:162` |
| No session: HTTP 401 `{"error": "sign_in_required"}` | `app.py:212-216` |
| Invalid exchange token: HTTP 401 `{"error": "invalid_invite", ...}` | `app.py:235-243` |

## Credential

The invite link (or the bare token) is read from the environment variable **`SESSION_INVITE_LINK`**.
It is never printed, logged or written to the evidence file. `--base-url` defaults to
`$GATEWAY_PUBLIC_ORIGIN`, else `https://ops-gateway-587647038690.us-central1.run.app` (the deterministic
host, ADR-107); it is also the `Origin` header.

## The ledger

A JSON file at `--ledger PATH`.

```
session_driver.py --ledger L init --max-requests 60 --max-dollars 0.25
session_driver.py --ledger L status
session_driver.py --ledger L tally --count N --note "TEXT" [--kind answered|declined|clarify|failure]
```

- `init` creates it and refuses to overwrite one (caps are never changed after creation).
- **Every request reserves its slot and the file is written before the request is sent**, under a lock
  file, so a crash never under-counts. A request that would pass either cap is refused before sending.
- **Costs are worst-case constants by request type**, from the plan's budget table (calls x $0.00058):
  `answered` $0.0029 (5 calls), `clarify` and `failure` $0.0023 (4), `declined` $0.0012 (2), `probe` $0.
  They are never read from a response.
- `tally` adds browser questions, which bypass the driver, at their type's constant (default `answered`).
- `status` prints requests and dollars against the caps.

## Network

IPv4 only on every connection. The driver imports `connect_socket` from `deploy/verify.py` (the
mechanism behind its `--ipv4`) and uses it with `ipv4=True`; the URL is never rewritten to an address, so
TLS server name and the `Host` header are untouched. A connect timeout of 10 s per address, a read
timeout of 150 s.

## Subcommands

All take `--scenario ID` (for example `TS-20-A`) and `--evidence PATH` (default: the ledger path with
`.evidence.jsonl`).

| Command | Does |
|---|---|
| `ask --question TEXT [--question ...] [--repeat N] [--parallel K] [--kind T]` | Exchanges the invite once, then sends each question N times, K at a time. Each request is reserved first. |
| `probe --url URL [--mode nosession\|badtoken\|wrongorigin] [--method M]` | One request with no invite (`nosession`), a made-up cookie (`badtoken`) or a wrong `Origin` (`wrongorigin`). Counted as a request at $0. Needs no credential. |
| `coldstart --path reporting\|sentiment\|forecast [--wait-seconds N]` | Exchanges the invite, waits N seconds with **no request**, then asks the path's fixed question once and prints the client-side latency and the trace ID. |
| `cap-test [--max 31] [--question TEXT]` | Sends up to 31 questions in sequence on one invite (default: a declined-at-routing question). Stops at the first refusal and records its 1-based index and its `error`. **Only `session_limit` at index 31 is `pass`**; a `daily_limit` refusal, a refusal at any other index, or no refusal is `inconclusive` (the error and index are in the evidence line). |

Fixed questions for `coldstart` are the `05` texts used in the plan: reporting TS-05-B, sentiment TS-07-A,
forecast TS-08-B.

## Evidence log

JSONL, one line per request: `at`, `scenario`, `subcommand`, `trace_id`, `status`, `latency_s`,
`outcome` (the answer's `outcome`, or the refusal's `error` code), `qa_status`, `answer_chars`, `index`.
**Never the answer text and never the question text**; only lengths.

## Exit codes

`0` done; `3` a cap was reached (nothing further sent); `4` the invite exchange failed; `2` usage.
