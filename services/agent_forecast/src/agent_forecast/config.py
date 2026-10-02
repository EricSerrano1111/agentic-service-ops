"""Settings from environment variables. No database credentials exist here.

Timeout budget, inside the orchestrator's 60 s A2A timeout and ADR-034's 120 s: the parsing
LLM call up to `parse_timeout_s`, then the MCP calls together up to `mcp_timeout_s`.
Forecasts are computed from stored coefficients, so the MCP calls take well under a second.
"""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass

from schemas import DATASET_WINDOW_END


@dataclass(frozen=True)
class Settings:
    mcp_volume_url: str = "http://mcp_volume:8103/mcp"
    #: Both MCP calls (forecast, then history if asked), connect included.
    mcp_timeout_s: float = 20.0
    #: The parsing LLM call, retries and 429 waits included.
    parse_timeout_s: float = 30.0
    #: Relative dates resolve against this, never the wall clock (ADR-050). The same variable
    #: as the other agents' and the router's, so all read one "today".
    as_of: dt.date = DATASET_WINDOW_END
    #: Recent actual weeks shown when the question asks for history.
    history_weeks: int = 8
    #: The URL advertised in the Agent Card: where peers send A2A requests.
    public_url: str = "http://agent_forecast:8003/"
    host: str = "0.0.0.0"
    port: int = 8003

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ.get
        d = cls()
        return cls(
            mcp_volume_url=env("MCP_VOLUME_URL", d.mcp_volume_url),
            mcp_timeout_s=float(env("MCP_TIMEOUT_S", str(d.mcp_timeout_s))),
            parse_timeout_s=float(env("PARSE_TIMEOUT_S", str(d.parse_timeout_s))),
            as_of=dt.date.fromisoformat(env("REPORTING_AS_OF_DATE") or d.as_of.isoformat()),
            public_url=env("AGENT_FORECAST_PUBLIC_URL", d.public_url),
            port=int(env("AGENT_FORECAST_PORT", str(d.port))),
        )
