"""The call to the orchestrator: one POST, the request deadline, no retries (ADR-097, ADR-034).

On Cloud Run the call carries the gateway service account's ID token, audience the
orchestrator's base URL (ADR-081's pattern). Neither the token nor the header is logged.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from collections.abc import Callable

import httpx

log = logging.getLogger("gateway.upstream")

REFRESH_MARGIN_S = 300.0
UNKNOWN_EXPIRY_S = 60.0


def fetch_google_id_token(audience: str) -> str:
    import google.auth.transport.requests
    from google.oauth2 import id_token

    return id_token.fetch_id_token(google.auth.transport.requests.Request(), audience)


def _expiry(token: str, now: float) -> float:
    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return float(claims["exp"])
    except Exception:
        return now + UNKNOWN_EXPIRY_S


class IdTokenProvider:
    def __init__(
        self,
        audience: str,
        fetch: Callable[[str], str] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._audience, self._fetch, self._clock = audience, fetch, clock
        self._cached: tuple[str, float] | None = None
        self._lock = asyncio.Lock()

    async def token(self) -> str:
        async with self._lock:
            now = self._clock()
            if self._cached and self._cached[1] - now > REFRESH_MARGIN_S:
                return self._cached[0]
            token = await asyncio.to_thread(self._fetch or fetch_google_id_token, self._audience)
            self._cached = (token, _expiry(token, now))
            return token


class OrchestratorUnavailable(Exception):
    """The orchestrator could not be reached, timed out or could not be authenticated to."""


class OrchestratorTimeout(OrchestratorUnavailable):
    """The wait for the orchestrator ran out (the gateway's own deadline)."""


class Orchestrator:
    def __init__(
        self,
        base_url: str,
        timeout_s: float,
        *,
        tokens: IdTokenProvider | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = f"{base_url.rstrip('/')}/ask"
        self._tokens = tokens
        self._client = httpx.AsyncClient(timeout=timeout_s, transport=transport)

    async def ask(self, question: str) -> tuple[int, dict]:
        """(status, JSON body). Raises `OrchestratorUnavailable`; the cause is never passed
        on, since a transport error can name an internal host."""
        headers = {}
        try:
            if self._tokens is not None:
                headers["Authorization"] = f"Bearer {await self._tokens.token()}"
            resp = await self._client.post(self._url, json={"question": question}, headers=headers)
            body = resp.json()
        except httpx.TimeoutException as exc:
            log.warning("orchestrator call timed out", extra={"error": type(exc).__name__})
            raise OrchestratorTimeout from None
        except Exception as exc:
            log.warning("orchestrator call failed", extra={"error": type(exc).__name__})
            raise OrchestratorUnavailable from None
        return resp.status_code, body if isinstance(body, dict) else {}

    async def aclose(self) -> None:
        await self._client.aclose()
