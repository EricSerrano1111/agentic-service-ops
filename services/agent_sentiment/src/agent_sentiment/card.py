"""The sentiment agent's Agent Card.

Advertises the minimal A2A subset this system uses (ADR-047): a JSON-RPC interface on
A2A 1.0 with blocking `SendMessage` only. Streaming and push notifications are declared
off, so a client never attempts them.
"""

from __future__ import annotations

from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from a2a.utils.constants import PROTOCOL_VERSION_1_0, TransportProtocol

SKILL_ID = "feedback_sentiment"


def build_agent_card(public_url: str) -> AgentCard:
    return AgentCard(
        name="Sentiment Agent",
        description=(
            "Customer feedback sentiment for the field-service operation, from stored "
            "model predictions. Figures and quoted comments come from the feedback "
            "service; answers are templated."
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
                name="Feedback sentiment over a date range",
                description=(
                    "Counts and shares of positive, neutral, negative and mixed feedback over "
                    "a date range, for all sites or one region; a monthly or quarterly trend "
                    "in the negative share; and up to 3 quoted example comments. Returns a "
                    "short text answer and the figures as structured data."
                ),
                tags=["sentiment", "feedback", "customers"],
                examples=["Is sentiment trending down in the West?"],
                input_modes=["text/plain"],
                output_modes=["text/plain", "application/json"],
            )
        ],
    )
