"""Delegation to a specialist over A2A: fetch its Agent Card, send one blocking message.

The card is fetched on every request rather than cached. It costs one local HTTP round
trip and means an agent restart or redeploy is picked up without an orchestrator
restart; caching is a later optimisation if latency measurements (ADR-034) call for it.
"""

from __future__ import annotations

import asyncio
import uuid

import httpx
from a2a.client import ClientConfig, create_client
from a2a.types import Message, Part, Role, SendMessageConfiguration, SendMessageRequest, Task
from common import TRACE_ID_KEY

from .auth import BearerForOrigin, IdTokenProvider, audience_of


class AgentProtocolError(RuntimeError):
    """The agent answered, but not with a Task (e.g. a bare Message)."""


async def send_question(
    agent_url: str,
    question: str,
    *,
    trace_id: str,
    timeout_s: float,
    transport: httpx.AsyncBaseTransport | None = None,
    token_provider: IdTokenProvider | None = None,
) -> Task:
    """Send `question` to the agent at `agent_url` and return the finished Task.

    Raises `TimeoutError` past `timeout_s`, card fetch included; SDK and transport
    errors propagate for the caller to map. With a `token_provider`, an ID token for the
    agent's origin goes on the card fetch and the message call alike (both share one HTTP
    client); a token that can't be fetched raises `AgentAuthError`. `transport` is a test
    seam only.
    """
    message = Message(
        message_id=uuid.uuid4().hex,
        role=Role.ROLE_USER,
        parts=[Part(text=question)],
        metadata={TRACE_ID_KEY: trace_id},
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
            return await _exchange(agent_url, request, http)


async def _exchange(agent_url: str, request: SendMessageRequest, http: httpx.AsyncClient) -> Task:
    client = await create_client(
        agent_url, client_config=ClientConfig(streaming=False, httpx_client=http)
    )
    async for event in client.send_message(request):
        if event.HasField("task"):
            return event.task
        raise AgentProtocolError("agent replied with a message, not a task")
    raise AgentProtocolError("agent returned no response")
