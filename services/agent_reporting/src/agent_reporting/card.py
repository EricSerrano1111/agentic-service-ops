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
            "Incident and quality metrics for the field-service operation: incident counts "
            "and rates, SLA compliance, first-time fix rate and repeat-visit drivers. Figures "
            "are computed deterministically from the operational database."
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
                name="Incident and quality metrics over a date range",
                description=(
                    "Incident counts (by severity, or by account, region, service type, "
                    "technician or incident type), incident rate, SLA compliance and "
                    "first-time fix rate over a date range, with the rates broken down by "
                    "account, region, service type or technician, or for one named "
                    "technician; and which incident types, service types, regions, accounts "
                    "or technicians have more repeat visits. Returns a short text answer "
                    "and the figures as structured data."
                ),
                tags=[
                    "incidents",
                    "metrics",
                    "reporting",
                    "sla",
                    "first-time-fix",
                    "technician",
                    "repeat-visits",
                ],
                examples=[
                    "How many incidents were reported last quarter, by severity?",
                    "What was our SLA compliance rate last quarter, by region?",
                    "What is Ben Okafor's first-time fix rate this year?",
                    "Which incident types are driving the most repeat visits this quarter?",
                ],
                input_modes=["text/plain"],
                output_modes=["text/plain", "application/json"],
            )
        ],
    )
