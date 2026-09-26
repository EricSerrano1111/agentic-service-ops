"""Typed LLM errors. Every one inherits from `LLMError`, and none carries an API key."""

from __future__ import annotations


class LLMError(Exception):
    """Base class for every error the LLM client raises."""


class LLMConfigError(LLMError):
    """Startup configuration is missing or unsafe (e.g. paid mode without a cap)."""


class LLMRateLimited(LLMError):
    """Per-minute quota 429s did not clear within `LLM_MAX_RETRY_WAIT_S` of waiting."""


class LLMDailyQuotaExhausted(LLMError):
    """A daily quota 429. Not retried: it clears at Pacific midnight, not in seconds."""

    def __init__(self, model: str, quota_id: str | None = None) -> None:
        detail = f" ({quota_id})" if quota_id else ""
        super().__init__(f"daily quota exhausted for {model}{detail}")
        self.model = model
        self.quota_id = quota_id


class LLMUnavailable(LLMError):
    """Transient server errors (5xx, timeouts) persisted through the bounded retries."""


class LLMAuthError(LLMError):
    """Billing, key or permission problem. Retrying cannot fix it."""


class LLMRequestError(LLMError):
    """Any other client error (a malformed request, an unknown model). Not retried."""


class LLMBudgetExceeded(LLMError):
    """The paid-mode spend cap would be crossed. Raised before the call is sent."""


class LLMRequestCapReached(LLMError):
    """The per-process request cap is used up. Raised before the call is sent."""


class LLMOutputInvalid(LLMError):
    """The model's output did not validate against `response_model`. No repair retry."""

    def __init__(self, message: str, raw_text: str | None) -> None:
        super().__init__(message)
        self.raw_text = raw_text
