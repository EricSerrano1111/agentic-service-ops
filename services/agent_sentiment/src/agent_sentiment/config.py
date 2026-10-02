"""Settings from environment variables. No database credentials exist here.

Timeout budget, inside the orchestrator's sentiment A2A timeout (85 s) and ADR-034's 120 s:
the parsing LLM call up to `parse_timeout_s`, then both MCP calls together up to
`mcp_timeout_s`. With predictions stored, the MCP calls take about a second; the budget
covers on-demand scoring of up to 250 comments warm (about 27 s, ADR-067). A cold first
scoring pass can exceed it (L-35) and fails as a timeout rather than overrunning.
"""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass

from schemas import DATASET_WINDOW_END


@dataclass(frozen=True)
class Settings:
    mcp_feedback_url: str = "http://mcp_feedback:8102/mcp"
    #: Both MCP calls (summary, then examples if asked), connect included.
    mcp_timeout_s: float = 45.0
    #: The parsing LLM call, retries and 429 waits included.
    parse_timeout_s: float = 30.0
    #: Relative dates resolve against this, never the wall clock (ADR-050). The same
    #: variable as the reporting agent's and the router's, so all read one "today".
    as_of: dt.date = DATASET_WINDOW_END
    #: Quoted example comments per answer (ADR-068: at most 3).
    examples_limit: int = 3
    #: The URL advertised in the Agent Card: where peers send A2A requests.
    public_url: str = "http://agent_sentiment:8002/"
    host: str = "0.0.0.0"
    port: int = 8002

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ.get
        d = cls()
        return cls(
            mcp_feedback_url=env("MCP_FEEDBACK_URL", d.mcp_feedback_url),
            mcp_timeout_s=float(env("MCP_TIMEOUT_S", str(d.mcp_timeout_s))),
            parse_timeout_s=float(env("PARSE_TIMEOUT_S", str(d.parse_timeout_s))),
            as_of=dt.date.fromisoformat(env("REPORTING_AS_OF_DATE") or d.as_of.isoformat()),
            public_url=env("AGENT_SENTIMENT_PUBLIC_URL", d.public_url),
            port=int(env("AGENT_SENTIMENT_PORT", str(d.port))),
        )
