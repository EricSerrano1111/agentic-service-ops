"""A fault-injecting proxy for the loop demonstration (Prompt N, section 6). Test only.

It speaks A2A as the reporting agent: the orchestrator is pointed at it by a compose override
that is not used in normal runs. For each message it forwards the question and the metadata to
the real reporting agent, takes the real answer, applies the fault named in FAULT to the data
part and re-renders the text, and returns that as its own artifact. A decline or an error is
passed through unchanged. FAULT=NONE passes everything through.

Only R01 (a count off by one) is implemented here; it is the catalogue's R01 mutation, written
again so this file needs nothing but the reporting agent's image.
"""

from __future__ import annotations

import logging
import os
import uuid

import httpx
import uvicorn
from a2a.client import ClientConfig, create_client
from a2a.helpers.proto_helpers import new_data_part, new_task_from_user_message, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    add_a2a_routes_to_fastapi,
    create_agent_card_routes,
    create_jsonrpc_routes,
)
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import Message, Part, Role, SendMessageRequest, TaskState
from agent_reporting.card import build_agent_card
from agent_reporting.render import render_answer
from fastapi import FastAPI
from google.protobuf.json_format import MessageToDict
from schemas import ReportingAnswer, rate_string

log = logging.getLogger("fault_proxy")
UPSTREAM = os.environ.get("UPSTREAM_URL", "http://agent_reporting:8001/")
PUBLIC = os.environ.get("PROXY_PUBLIC_URL", "http://fault_proxy:8001/")
FAULT = os.environ.get("FAULT", "NONE")


def mutate_r01(data: dict) -> tuple[dict, str]:
    """R01: a count off by one, with the text re-rendered from the changed data part."""
    answer = ReportingAnswer.model_validate(data)
    d = answer.model_dump(mode="json")
    f = d["figures"]
    if f["metric"] == "incident_count":
        f["incident_count"] += 1
        f["by_severity"]["medium"] += 1
        if f["groups"] and not f["truncated"]:
            f["groups"][0]["count"] += 1
    elif f["metric"] == "repeat_visit_drivers":
        f["overall"]["repeated"] += 1
        f["overall"]["rate"] = rate_string(f["overall"]["repeated"], f["overall"]["jobs"])
    else:
        f["numerator"] += 1
        scale = 100 if f["metric"] == "incident_rate" else 1
        f["rate"] = rate_string(f["numerator"], f["denominator"], scale)
    mutated = ReportingAnswer.model_validate(d)
    return mutated.model_dump(mode="json"), render_answer(mutated, 20)


async def forward(question: str, metadata: dict):
    async with httpx.AsyncClient(timeout=110) as http:
        client = await create_client(
            UPSTREAM, client_config=ClientConfig(streaming=False, httpx_client=http)
        )
        message = Message(
            message_id=uuid.uuid4().hex,
            role=Role.ROLE_USER,
            parts=[Part(text=question)],
            metadata=metadata,
        )
        async for event in client.send_message(SendMessageRequest(message=message)):
            return event.task
    raise RuntimeError("no response from the reporting agent")


class FaultProxy(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task
        if task is None:
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        metadata = (
            MessageToDict(context.message.metadata) if context.message.HasField("metadata") else {}
        )
        upstream = await forward(context.get_user_input(), metadata)
        if upstream.status.state == TaskState.TASK_STATE_COMPLETED:
            artifact = upstream.artifacts[0]
            text_part, data_part = artifact.parts
            data, text = MessageToDict(data_part.data), text_part.text
            if FAULT == "R01":
                data, text = mutate_r01(data)
                log.warning("fault applied: %s", FAULT)
            await updater.add_artifact(
                [
                    new_text_part(text, media_type="text/plain"),
                    new_data_part(data, media_type="application/json"),
                ],
                name=artifact.name,
                metadata=MessageToDict(artifact.metadata),
            )
            await updater.complete()
            return
        message = upstream.status.message
        await updater.failed(
            updater.new_agent_message(
                [new_text_part(message.parts[0].text if message.parts else "")],
                metadata=MessageToDict(message.metadata) if message.HasField("metadata") else {},
            )
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError


def create_app() -> FastAPI:
    card = build_agent_card(PUBLIC)
    handler = DefaultRequestHandler(
        agent_executor=FaultProxy(), task_store=InMemoryTaskStore(), agent_card=card
    )
    app = FastAPI(title="fault_proxy")
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(card),
        jsonrpc_routes=create_jsonrpc_routes(handler, rpc_url="/"),
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "fault": FAULT}

    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(create_app(), host="0.0.0.0", port=8001)  # noqa: S104 - container-internal
