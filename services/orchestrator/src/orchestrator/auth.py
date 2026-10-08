"""Google ID tokens for outbound A2A calls to IAM-protected Cloud Run services.

With `A2A_AUTH=google_id_token` the orchestrator attaches `Authorization: Bearer <token>`
to every request it sends to a specialist: the Agent Card fetch and the message call alike,
because on Cloud Run both sit behind the same IAM check. The token's audience is the
target service's base URL. Locally (`A2A_AUTH` unset) no token is fetched or sent.

A token is reused until shortly before it expires. Neither the token nor the header is ever
logged; a failed fetch logs only the exception's type.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from collections.abc import Callable
from urllib.parse import urlsplit

import httpx

log = logging.getLogger("orchestrator.auth")

#: Refresh when fewer than this many seconds of validity remain. Google ID tokens last an
#: hour; five minutes is far more than any one A2A exchange (at most 120 s) needs.
REFRESH_MARGIN_S = 300.0
#: Lifetime assumed for a token whose `exp` claim cannot be read (it is then refetched soon).
UNKNOWN_EXPIRY_S = 60.0


class AgentAuthError(RuntimeError):
    """An ID token could not be obtained for the target service."""


def fetch_google_id_token(audience: str) -> str:
    """Blocking: ask Google for an ID token for `audience` as the runtime service account.

    On Cloud Run this is a call to the metadata server. Imported here so the offline
    suite and local runs never load `google-auth`.
    """
    import google.auth.transport.requests
    from google.oauth2 import id_token

    return id_token.fetch_id_token(google.auth.transport.requests.Request(), audience)


def _expiry(token: str, now: float) -> float:
    """The token's `exp` claim as a Unix time, read without verifying it (we only schedule
    a refresh; the receiving service verifies the token)."""
    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return float(claims["exp"])
    except Exception:
        return now + UNKNOWN_EXPIRY_S


class IdTokenProvider:
    """Fetches and caches one ID token per audience."""

    def __init__(
        self,
        fetch: Callable[[str], str] | None = None,
        *,
        clock: Callable[[], float] = time.time,
        refresh_margin_s: float = REFRESH_MARGIN_S,
    ) -> None:
        self._fetch = fetch
        self._clock = clock
        self._margin = refresh_margin_s
        self._cache: dict[str, tuple[str, float]] = {}
        self._lock = asyncio.Lock()

    async def token(self, audience: str) -> str:
        """A valid token for `audience`; raises `AgentAuthError` if none can be fetched."""
        async with self._lock:
            cached = self._cache.get(audience)
            now = self._clock()
            if cached and cached[1] - now > self._margin:
                return cached[0]
            try:
                token = await asyncio.to_thread(self._fetch or fetch_google_id_token, audience)
            except Exception as exc:
                log.warning(
                    "id token fetch failed",
                    extra={"audience": audience, "error": type(exc).__name__},
                )
                raise AgentAuthError("could not obtain an ID token for the agent") from None
            self._cache[audience] = (token, _expiry(token, now))
            return token


def audience_of(agent_url: str) -> str:
    """The service's base URL (scheme and host), the audience Cloud Run expects."""
    parts = urlsplit(agent_url)
    return f"{parts.scheme}://{parts.netloc}"


class BearerForOrigin(httpx.Auth):
    """Attach the bearer token to requests for one origin only.

    The message call goes to the URL in the Agent Card, which the target controls. Scoping
    the header to the audience's origin means a card pointing elsewhere cannot make us send
    the token to a different host.
    """

    def __init__(self, token: str, origin: str) -> None:
        self._header = f"Bearer {token}"
        self._origin = origin

    def __repr__(self) -> str:  # never print the token
        return f"BearerForOrigin(origin={self._origin!r})"

    def auth_flow(self, request: httpx.Request):
        url = request.url
        if f"{url.scheme}://{url.netloc.decode()}" == self._origin:
            request.headers["Authorization"] = self._header
        yield request
