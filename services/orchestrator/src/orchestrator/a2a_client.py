"""Delegation to a specialist over A2A: fetch its Agent Card, send one blocking message.

The card is cached per target URL for a set time (`AGENT_CARD_TTL_S`, default 300 s) and
dropped after any failed call, so a redeployed agent is picked up within the TTL or on the
first error. On Cloud Run each fetch is an authenticated round trip, which is why it is no
longer fetched per request. A cache miss fetches the card with the same ID token as the
message call.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable

import httpx
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers.proto_helpers import new_data_part
from a2a.types import (
    AgentCard,
    Message,
    Part,
    Role,
    SendMessageConfiguration,
    SendMessageRequest,
    Task,
)
from common import TRACE_ID_KEY, Deadline

from .auth import BearerForOrigin, IdTokenProvider, audience_of


class AgentProtocolError(RuntimeError):
    """The agent answered, but not with a Task (e.g. a bare Message)."""


class AgentCardCache:
    """Agent Cards by target URL, each valid for `ttl_s` seconds. A TTL of 0 caches nothing."""

    def __init__(self, ttl_s: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl_s = ttl_s
        self._clock = clock
        self._cards: dict[str, tuple[AgentCard, float]] = {}

    def get(self, url: str) -> AgentCard | None:
        entry = self._cards.get(url)
        if entry is None or self._clock() >= entry[1]:
            self._cards.pop(url, None)
            return None
        return entry[0]

    def put(self, url: str, card: AgentCard) -> None:
        if self._ttl_s > 0:
            self._cards[url] = (card, self._clock() + self._ttl_s)

    def invalidate(self, url: str) -> None:
        self._cards.pop(url, None)


async def send_question(
    agent_url: str,
    question: str,
    *,
    trace_id: str,
    timeout_s: float,
    transport: httpx.AsyncBaseTransport | None = None,
    token_provider: IdTokenProvider | None = None,
    card_cache: AgentCardCache | None = None,
    deadline: Deadline | None = None,
    data: dict | None = None,
    metadata: dict | None = None,
) -> Task:
    """Send `question` to the agent at `agent_url` and return the finished Task.

    Raises `TimeoutError` past `timeout_s`, card fetch included; SDK and transport
    errors propagate for the caller to map. With a `token_provider`, an ID token for the
    agent's origin goes on the card fetch and the message call alike (both share one HTTP
    client); a token that can't be fetched raises `AgentAuthError`. With a `card_cache`, a
    fresh cached card skips the fetch, and any failed call drops the card. `transport` is a
    test seam only. With a `deadline`, its absolute time goes to the agent in the message
    metadata; `timeout_s` is still the caller's, already clamped to it. `data` adds one
    structured data part after the text (the QA agent's verification request); `metadata` adds
    keys to the message metadata (the reviewer note a specialist is re-asked with).
    """
    message = Message(
        message_id=uuid.uuid4().hex,
        role=Role.ROLE_USER,
        parts=[Part(text=question)] + ([new_data_part(data)] if data is not None else []),
        # The request's one deadline travels with the trace id (ADR-088); the agent clamps its
        # own hops to it and never trusts it blindly.
        metadata=(metadata or {})
        | {TRACE_ID_KEY: trace_id}
        | (deadline.as_metadata() if deadline else {}),
    )
    request = SendMessageRequest(
        message=message,
        # Blocking: the call returns once the task is terminal (completed or failed).
        configuration=SendMessageConfiguration(
            return_immediately=False,
            accepted_output_modes=["text/plain", "application/json"],
        ),
    )
    # The HTTP timeout sits just above the overall one, so the deadline always surfaces
    # as TimeoutError rather than as an SDK error wrapping an httpx timeout.
    async with asyncio.timeout(timeout_s):
        auth = None
        if token_provider is not None:
            audience = audience_of(agent_url)
            auth = BearerForOrigin(await token_provider.token(audience), audience)
        async with httpx.AsyncClient(timeout=timeout_s + 1, transport=transport, auth=auth) as http:
            try:
                return await _exchange(agent_url, request, http, card_cache)
            except BaseException:
                if card_cache is not None:
                    card_cache.invalidate(agent_url)
                raise


async def _exchange(
    agent_url: str,
    request: SendMessageRequest,
    http: httpx.AsyncClient,
    card_cache: AgentCardCache | None,
) -> Task:
    card = card_cache.get(agent_url) if card_cache is not None else None
    if card is None and card_cache is not None:
        card = await A2ACardResolver(http, agent_url).get_agent_card()
        card_cache.put(agent_url, card)
    client = await create_client(
        card if card is not None else agent_url,
        client_config=ClientConfig(streaming=False, httpx_client=http),
    )
    async for event in client.send_message(request):
        if event.HasField("task"):
            return event.task
        raise AgentProtocolError("agent replied with a message, not a task")
    raise AgentProtocolError("agent returned no response")
