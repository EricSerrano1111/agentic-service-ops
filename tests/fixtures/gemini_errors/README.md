# Real Gemini API error bodies

Captured with `scripts/capture_gemini_429.py` on the free key (it never reads the paid
key). Each file is the SDK's `APIError.details` body plus capture metadata, with the API
key and any project identifiers redacted before it was written. Read a new file for
anything identifying before committing it.

`tests/unit/test_llm_client.py` builds its fixtures from these files. Error kinds with
no real body here yet (a pure per-minute 429, a daily quota used up after normal
traffic, billing errors) are assembled to the observed shape and marked ASSEMBLED
there. See ADR-048.
