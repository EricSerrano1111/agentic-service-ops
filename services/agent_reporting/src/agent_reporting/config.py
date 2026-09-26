"""Settings from environment variables. No database credentials exist here."""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    mcp_incidents_url: str = "http://mcp_incidents:8101/mcp"
    #: Whole MCP call, connect included. Inside the A2A timeout, inside ADR-034's 120 s.
    mcp_timeout_s: float = 15.0
    #: The URL advertised in the Agent Card: where peers send A2A requests.
    public_url: str = "http://agent_reporting:8001/"
    host: str = "0.0.0.0"
    port: int = 8001
    # TODO(ADR-046): replace with question parsing. Until the parsing prompt exists,
    # every question is answered for this fixed range (the last full quarter of data).
    skeleton_range_start: dt.date = dt.date(2026, 6, 1)
    skeleton_range_end: dt.date = dt.date(2026, 8, 30)

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ.get
        d = cls()
        return cls(
            mcp_incidents_url=env("MCP_INCIDENTS_URL", d.mcp_incidents_url),
            mcp_timeout_s=float(env("MCP_TIMEOUT_S", str(d.mcp_timeout_s))),
            public_url=env("AGENT_REPORTING_PUBLIC_URL", d.public_url),
            port=int(env("AGENT_REPORTING_PORT", str(d.port))),
            skeleton_range_start=dt.date.fromisoformat(
                env("SKELETON_RANGE_START", d.skeleton_range_start.isoformat())
            ),
            skeleton_range_end=dt.date.fromisoformat(
                env("SKELETON_RANGE_END", d.skeleton_range_end.isoformat())
            ),
        )
