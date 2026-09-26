"""Capture real Gemini API error bodies for the packages/llm test fixtures (ADR-048).

ADR-048 notes that no real 429 body was ever recorded in this repo, so the `QuotaFailure`
and `RetryInfo` shapes in tests/unit/test_llm_client.py are Google's standard types,
unobserved here. This script records real ones:

  (a) bursts tiny requests at the orchestrator model (GEMINI_MODEL_ORCHESTRATOR, or
      --model) until the first error, expected to be a per-minute 429;
  (b) makes one call to gemini-3.1-pro-preview, which has no free-tier quota
      (ADR-029), so the free key should get a 429 or 403 back.

Free key only (GOOGLE_AI_API_KEY): the paid key is never read, so this cannot spend
money. At most 25 requests in total, with the SDK's own retries off (one HTTP request
per call). Each error body is saved to tests/fixtures/gemini_errors/ as
<UTC timestamp>_<step>_<model>_<code>.json, with the key and any project identifiers
redacted first. Successful responses are not saved; only counts are printed.

    .venv\\Scripts\\python scripts/capture_gemini_429.py
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.metadata
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "tests" / "fixtures" / "gemini_errors"
FREE_KEY_VAR = "GOOGLE_AI_API_KEY"
PRO_MODEL = "gemini-3.1-pro-preview"
MAX_REQUESTS = 25  # hard ceiling for the whole run: the burst gets at most 24
PROMPT = "Reply with the single word OK."

# Anything that could identify the key or the project. Applied to the serialised body.
_REDACTIONS = [
    (re.compile(r"AIza[0-9A-Za-z_\-]{20,}"), "REDACTED_API_KEY"),
    (re.compile(r"projects/[^/\s\"']+"), "projects/REDACTED_PROJECT"),
    (re.compile(r"([?&]project=)[^&\s\"']+"), r"\1REDACTED_PROJECT"),
    (
        re.compile(
            r'("(?:consumer|project|projectId|project_id|projectNumber|project_number)"'
            r'\s*:\s*")[^"]*(")'
        ),
        r"\1REDACTED_PROJECT\2",
    ),
    # Project numbers are 12 digits; nothing else in an error body is a 10-13 digit run.
    (re.compile(r"(?<![\d.])\d{10,13}(?![\d.])"), "REDACTED_NUMBER"),
]


def redact(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "REDACTED")
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def _secrets(key: str) -> list[str]:
    """The key, plus the configured project ID and number if .env has them."""
    extra = [os.environ.get(v, "").strip() for v in ("GCP_PROJECT_ID", "GCP_PROJECT_NUMBER")]
    return [key, *[e for e in extra if e]]


class Budget:
    def __init__(self, limit: int) -> None:
        self.limit, self.used = limit, 0

    def take(self) -> None:
        if self.used >= self.limit:
            raise SystemExit(f"request ceiling of {self.limit} reached; stopping")
        self.used += 1


def save(step: str, model: str, attempt: int, exc: Exception, secrets: list[str]) -> Path:
    code = getattr(exc, "code", None)
    body: Any = getattr(exc, "details", None)
    record = {
        "captured_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "step": step,
        "model": model,
        "attempt": attempt,
        "http_code": code,
        "exception_type": f"{type(exc).__module__}.{type(exc).__name__}",
        "sdk": f"google-genai {importlib.metadata.version('google-genai')}",
        "note": "APIError.details, key and project identifiers redacted",
        "body": body if body is not None else {"unparsed": str(exc)},
    }
    text = redact(json.dumps(record, indent=2, ensure_ascii=False), secrets)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    path = OUT_DIR / f"{stamp}_{step}_{model}_{code or 'none'}.json"
    path.write_text(text + "\n", encoding="utf-8")
    return path


def quota_summary(exc: Exception) -> str:
    """One line: the quota ids and retry delay the error carries, if any."""
    body = getattr(exc, "details", None)
    inner = body.get("error", body) if isinstance(body, dict) else {}
    ids, delay = [], None
    for d in inner.get("details") or []:
        if not isinstance(d, dict):
            continue
        for v in d.get("violations") or []:
            if isinstance(v, dict) and v.get("quotaId"):
                ids.append(v["quotaId"])
        delay = d.get("retryDelay", delay)
    return f"status={inner.get('status')} quotaIds={ids or '-'} retryDelay={delay or '-'}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--model",
        help="burst model (default: GEMINI_MODEL_ORCHESTRATOR from the environment or .env)",
    )
    parser.add_argument(
        "--burst", type=int, default=MAX_REQUESTS - 1, help="max burst requests (<= 24)"
    )
    args = parser.parse_args(argv)

    from dotenv import load_dotenv
    from google import genai
    from google.genai import types

    load_dotenv(ROOT / ".env", override=False)
    key = os.environ.get(FREE_KEY_VAR, "").strip()
    if not key:
        raise SystemExit(f"{FREE_KEY_VAR} is not set (see .env.example)")
    model = (args.model or os.environ.get("GEMINI_MODEL_ORCHESTRATOR", "")).strip()
    if not model:
        raise SystemExit("set GEMINI_MODEL_ORCHESTRATOR in .env or pass --model")
    burst = max(0, min(args.burst, MAX_REQUESTS - 1))  # always leave one for the Pro call
    secrets = _secrets(key)
    budget = Budget(MAX_REQUESTS)

    client = genai.Client(
        api_key=key,
        http_options=types.HttpOptions(
            timeout=30_000, retry_options=types.HttpRetryOptions(attempts=1)
        ),
    )

    def call(target: str) -> None:
        budget.take()
        client.models.generate_content(model=target, contents=PROMPT)

    saved: list[Path] = []

    # (a) burst until the first error
    print(f"(a) bursting up to {burst} requests at {model} (free key)")
    ok = 0
    for attempt in range(1, burst + 1):
        started = time.monotonic()
        try:
            call(model)
            ok += 1
            print(f"    {attempt:>2}: ok ({time.monotonic() - started:.1f}s)")
        except Exception as exc:
            path = save("burst", model, attempt, exc, secrets)
            saved.append(path)
            print(
                f"    {attempt:>2}: {getattr(exc, 'code', type(exc).__name__)} {quota_summary(exc)}"
            )
            print(f"        saved {path.relative_to(ROOT)}")
            break
    else:
        print(f"    no error after {ok} requests; the per-minute limit was not reached")

    # (b) one call to the Pro preview model, which has no free-tier quota
    print(f"(b) one request to {PRO_MODEL} (free key; no free-tier quota expected)")
    try:
        call(PRO_MODEL)
        print("    ok: unexpectedly succeeded on the free key; nothing to save")
    except Exception as exc:
        path = save("pro", PRO_MODEL, 1, exc, secrets)
        saved.append(path)
        print(f"    {getattr(exc, 'code', type(exc).__name__)} {quota_summary(exc)}")
        print(f"        saved {path.relative_to(ROOT)}")

    print(f"done: {budget.used} request(s) sent, {len(saved)} error body(ies) saved")
    if saved:
        print("check each file for anything identifying before committing it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
