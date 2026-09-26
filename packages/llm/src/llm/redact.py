"""Redaction for Gemini error bodies before they are logged or written to disk.

Shared by the client's passive 429 capture (`client.py`) and
`scripts/capture_gemini_429.py`, so both redact identically.
"""

from __future__ import annotations

import re

#: Anything that could identify the key or the project. Applied to the serialised body.
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


def redact(text: str, secrets: list[str] | tuple[str, ...]) -> str:
    """Replace each secret, then every key or project identifier pattern, in `text`."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, "REDACTED")
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text
