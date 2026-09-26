"""Settings from environment variables. No database credentials exist here.

Timeout budget inside ADR-034's 120 s ceiling: routing (one LLM call) up to
`route_timeout_s`, then the A2A call up to `a2a_timeout_s`, which covers the agent's own
LLM parse and MCP call. 30 + 60 = 90 s worst case.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    #: Base URL the reporting agent's Agent Card is fetched from (well-known path).
    agent_reporting_url: str = "http://agent_reporting:8001"
    #: The routing LLM call, retries and 429 waits included.
    route_timeout_s: float = 30.0
    #: Whole A2A exchange, card fetch included. Must exceed the agent's parse + MCP time.
    a2a_timeout_s: float = 60.0
    host: str = "0.0.0.0"
    port: int = 8000

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ.get
        d = cls()
        return cls(
            agent_reporting_url=env("AGENT_REPORTING_URL", d.agent_reporting_url),
            route_timeout_s=float(env("ROUTE_TIMEOUT_S", str(d.route_timeout_s))),
            a2a_timeout_s=float(env("A2A_TIMEOUT_S", str(d.a2a_timeout_s))),
            port=int(env("ORCHESTRATOR_PORT", str(d.port))),
        )
