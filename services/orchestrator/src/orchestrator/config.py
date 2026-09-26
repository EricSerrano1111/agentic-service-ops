"""Settings from environment variables. No database credentials exist here."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    #: Base URL the reporting agent's Agent Card is fetched from (well-known path).
    agent_reporting_url: str = "http://agent_reporting:8001"
    #: Whole A2A exchange, card fetch included. Must exceed the agent's MCP timeout and
    #: stay well inside ADR-034's 120 s ceiling.
    a2a_timeout_s: float = 30.0
    host: str = "0.0.0.0"
    port: int = 8000

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ.get
        d = cls()
        return cls(
            agent_reporting_url=env("AGENT_REPORTING_URL", d.agent_reporting_url),
            a2a_timeout_s=float(env("A2A_TIMEOUT_S", str(d.a2a_timeout_s))),
            port=int(env("ORCHESTRATOR_PORT", str(d.port))),
        )
