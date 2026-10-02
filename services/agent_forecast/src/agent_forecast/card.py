"""The forecast agent's Agent Card.

Advertises the minimal A2A subset this system uses (ADR-047): a JSON-RPC interface on
A2A 1.0 with blocking `SendMessage` only. Streaming and push notifications are declared
off, so a client never attempts them.
"""

from __future__ import annotations

from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from a2a.utils.constants import PROTOCOL_VERSION_1_0, TransportProtocol

SKILL_ID = "volume_forecast"


def build_agent_card(public_url: str) -> AgentCard:
    return AgentCard(
        name="Forecast Agent",
        description=(
            "Weekly request-volume forecasts for the field-service operation, from the stored "
            "volume_v2 model. Numbers are shown only where the model has an adequate track "
            "record, always with its held-out error; answers are templated."
        ),
        version="0.1.0",
        supported_interfaces=[
            AgentInterface(
                url=public_url,
                protocol_binding=TransportProtocol.JSONRPC.value,
                protocol_version=PROTOCOL_VERSION_1_0,
            )
        ],
        capabilities=AgentCapabilities(streaming=False, push_notifications=False),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain", "application/json"],
        skills=[
            AgentSkill(
                id=SKILL_ID,
                name="Weekly request-volume forecast",
                description=(
                    "Weekly request-volume forecasts with 80% ranges, in total or by service "
                    "type, up to 26 weeks ahead, each with its held-out error; a period total "
                    "as the sum of weekly forecasts. Returns a short text answer and the "
                    "figures as structured data."
                ),
                tags=["forecast", "volume", "planning"],
                examples=["What will request volume look like next month?"],
                input_modes=["text/plain"],
                output_modes=["text/plain", "application/json"],
            )
        ],
    )
