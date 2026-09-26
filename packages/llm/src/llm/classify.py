"""Sorting a Gemini API error into what the client should do with it.

Lifted from `data/generator/build_corpus.py` (`GeminiApi.request`, `is_billing_error`,
`is_daily_quota_error`), which ran the corpus build through daily-quota, 5xx and billing
stops. One change of method, not of policy: build_corpus.py matched quota identifiers in
`str(exc)`. That string is rendered from `APIError.details`, the parsed error body, so
here the same identifiers are read from the structured field. Text matching remains only
as a fallback for a body without the structured detail.

Error body shape (google-genai 2.25.0 `errors.APIError.details`):
    {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "...",
               "details": [{"@type": "type.googleapis.com/google.rpc.QuotaFailure",
                            "violations": [{"quotaId": "GenerateRequestsPerDay..."}]},
                           {"@type": "type.googleapis.com/google.rpc.RetryInfo",
                            "retryDelay": "7s"}]}}
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any


class Kind(Enum):
    BILLING = "billing"
    AUTH = "auth"
    DAILY_QUOTA = "daily_quota"
    RATE_LIMIT = "rate_limit"
    TRANSIENT = "transient"
    REQUEST = "request"


# Lifted verbatim from build_corpus.py `_BILLING_MARKERS`. No structured field for billing
# problems has been observed, so this stays a text match on the error message.
_BILLING_MARKERS = (
    "billing",
    "prepay",
    "prepaid",
    "credit balance",
    "credits are depleted",
    "insufficient",
    "out of credit",
    "payment",
)
# build_corpus.py treats these codes as possible billing errors.
_BILLING_CODES = (400, 402, 403, 429)
# Lifted from build_corpus.py `is_daily_quota_error`; used only when no quotaId exists.
_DAILY_TEXT_MARKERS = ("perday", "per_day", "per day", "requestsperday")
# build_corpus.py RETRYABLE_CODES minus 429 (handled on its own), plus the other 5xx
# gateway codes the SDK's own retry list treats as transient.
TRANSIENT_CODES = frozenset({500, 502, 503, 504})
_AUTH_REASONS = frozenset({"API_KEY_INVALID", "API_KEY_EXPIRED", "PERMISSION_DENIED"})
_DELAY = re.compile(r"^\s*(\d+(?:\.\d+)?)s\s*$")


@dataclass(frozen=True)
class Classified:
    kind: Kind
    code: int | None
    quota_id: str | None = None
    retry_delay_s: float | None = None
    message: str = ""


def _body(exc: BaseException) -> dict[str, Any]:
    details = getattr(exc, "details", None)
    if not isinstance(details, dict):
        return {}
    inner = details.get("error")
    return inner if isinstance(inner, dict) else details


def _entries(body: dict[str, Any], type_suffix: str) -> list[dict[str, Any]]:
    return [
        d
        for d in body.get("details") or []
        if isinstance(d, dict) and str(d.get("@type", "")).endswith(type_suffix)
    ]


def quota_ids(body: dict[str, Any]) -> list[str]:
    return [
        str(v["quotaId"])
        for entry in _entries(body, "google.rpc.QuotaFailure")
        for v in entry.get("violations") or []
        if isinstance(v, dict) and v.get("quotaId")
    ]


def retry_delay_s(body: dict[str, Any]) -> float | None:
    """`RetryInfo.retryDelay` ("7s", "23.5s") in seconds, if the error states one."""
    for entry in _entries(body, "google.rpc.RetryInfo"):
        match = _DELAY.match(str(entry.get("retryDelay", "")))
        if match:
            return float(match.group(1))
    return None


def _reasons(body: dict[str, Any]) -> set[str]:
    return {str(e.get("reason", "")) for e in _entries(body, "google.rpc.ErrorInfo")}


def _is_daily(quota_id: str) -> bool:
    return "perday" in quota_id.lower()


def classify(exc: BaseException) -> Classified:
    """Decide how to treat an exception raised by the transport."""
    body = _body(exc)
    code = getattr(exc, "code", None)
    if not isinstance(code, int):
        code = body.get("code") if isinstance(body.get("code"), int) else None
    message = str(body.get("message") or getattr(exc, "message", None) or exc)

    if code is None:
        # No HTTP status: a transport-level failure (timeout, connection reset).
        name = type(exc).__name__.lower()
        if "timeout" in name or "connect" in name or isinstance(exc, TimeoutError | OSError):
            return Classified(Kind.TRANSIENT, None, message=message)
        return Classified(Kind.REQUEST, None, message=message)

    # Billing first, as in build_corpus.py: a depleted prepaid balance arrives as a 429.
    if code in _BILLING_CODES and any(m in message.lower() for m in _BILLING_MARKERS):
        return Classified(Kind.BILLING, code, message=message)
    if code in (401, 403) or _reasons(body) & _AUTH_REASONS:
        return Classified(Kind.AUTH, code, message=message)

    if code == 429:
        ids = quota_ids(body)
        if ids:  # the structured field exists: decide on it alone
            daily = next((q for q in ids if _is_daily(q)), None)
            if daily:
                return Classified(Kind.DAILY_QUOTA, code, quota_id=daily, message=message)
            return Classified(
                Kind.RATE_LIMIT,
                code,
                quota_id=ids[0],
                retry_delay_s=retry_delay_s(body),
                message=message,
            )
        if any(m in str(exc).lower() for m in _DAILY_TEXT_MARKERS):
            return Classified(Kind.DAILY_QUOTA, code, message=message)
        # A 429 without a daily marker is per-minute, as build_corpus.py treated it.
        return Classified(Kind.RATE_LIMIT, code, retry_delay_s=retry_delay_s(body), message=message)

    if code in TRANSIENT_CODES:
        return Classified(Kind.TRANSIENT, code, message=message)
    return Classified(Kind.REQUEST, code, message=message)
