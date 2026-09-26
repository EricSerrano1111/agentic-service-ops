"""Settings from environment variables. No database credentials exist here.

Timeout budget, inside the orchestrator's A2A timeout (60 s) and ADR-034's 120 s:
the parsing LLM call up to `parse_timeout_s`, then the MCP call up to `mcp_timeout_s`.
"""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass

from schemas import DATASET_WINDOW_END


@dataclass(frozen=True)
class Settings:
    mcp_incidents_url: str = "http://mcp_incidents:8101/mcp"
    #: Whole MCP call, connect included.
    mcp_timeout_s: float = 15.0
    #: The parsing LLM call, retries and 429 waits included.
    parse_timeout_s: float = 30.0
    #: Relative dates resolve against this, never the wall clock (ADR-050).
    as_of: dt.date = DATASET_WINDOW_END
    #: The URL advertised in the Agent Card: where peers send A2A requests.
    public_url: str = "http://agent_reporting:8001/"
    host: str = "0.0.0.0"
    port: int = 8001

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ.get
        d = cls()
        return cls(
            mcp_incidents_url=env("MCP_INCIDENTS_URL", d.mcp_incidents_url),
            mcp_timeout_s=float(env("MCP_TIMEOUT_S", str(d.mcp_timeout_s))),
            parse_timeout_s=float(env("PARSE_TIMEOUT_S", str(d.parse_timeout_s))),
            as_of=dt.date.fromisoformat(env("REPORTING_AS_OF_DATE") or d.as_of.isoformat()),
            public_url=env("AGENT_REPORTING_PUBLIC_URL", d.public_url),
            port=int(env("AGENT_REPORTING_PORT", str(d.port))),
        )
