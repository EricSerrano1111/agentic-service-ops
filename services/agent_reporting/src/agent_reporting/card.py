"""The reporting agent's Agent Card.

Advertises the minimal A2A subset this system uses (ADR-047): a JSON-RPC interface on
A2A 1.0 with blocking `SendMessage` only. Streaming and push notifications are declared
off, so a client never attempts them.
"""

from __future__ import annotations

from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from a2a.utils.constants import PROTOCOL_VERSION_1_0, TransportProtocol

SKILL_ID = "incident_metrics"


def build_agent_card(public_url: str) -> AgentCard:
    return AgentCard(
        name="Reporting Agent",
        description=(
            "Incident and quality metrics for the field-service operation. Figures are "
            "computed deterministically from the incidents database."
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
                name="Incident metrics over a date range",
                description=(
                    "Counts incidents reported in a date range, in total and by severity. "
                    "Returns a short text answer and the figures as structured data."
                ),
                tags=["incidents", "metrics", "reporting"],
                examples=["How many incidents were reported last quarter, by severity?"],
                input_modes=["text/plain"],
                output_modes=["text/plain", "application/json"],
            )
        ],
    )
