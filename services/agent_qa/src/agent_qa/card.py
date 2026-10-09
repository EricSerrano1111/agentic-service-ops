"""The QA agent's Agent Card.

Advertises the minimal A2A subset this system uses (ADR-047): a JSON-RPC interface on A2A 1.0
with blocking `SendMessage` only. Streaming and push notifications are declared off.
"""

from __future__ import annotations

from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from a2a.utils.constants import PROTOCOL_VERSION_1_0, TransportProtocol

SKILL_ID = "verify_answer"


def build_agent_card(public_url: str) -> AgentCard:
    return AgentCard(
        name="QA Agent",
        description=(
            "Verifies the reporting and forecast agents' answers before they are returned: "
            "figures recomputed from the operational database, forecast arithmetic and the "
            "model manifest, answer text against data, and whether the question was understood. "
            "Returns a pass or fail verdict with the failed check codes."
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
        default_input_modes=["application/json"],
        default_output_modes=["text/plain", "application/json"],
        skills=[
            AgentSkill(
                id=SKILL_ID,
                name="Verify a specialist's answer",
                description=(
                    "Takes a question and a reporting or forecast agent's answer (or decline) as "
                    "a structured request and returns a verdict listing every check that ran."
                ),
                tags=["verification", "qa", "reporting", "forecast"],
                examples=["Verify this reporting answer against the database."],
                input_modes=["application/json"],
                output_modes=["text/plain", "application/json"],
            )
        ],
    )
