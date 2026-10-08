"""Settings from environment variables. No database credentials exist here.

Timeout budget inside ADR-034's 120 s ceiling: routing (one LLM call) up to
`route_timeout_s`, then the A2A call up to `a2a_timeout_s`, which covers the agent's own
LLM parse and MCP call. 30 + 60 = 90 s worst case. The sentiment agent gets
`sentiment_a2a_timeout_s`: its MCP calls may score up to 250 comments on demand (about
27 s warm, ADR-067), so 30 + 85 = 115 s worst case. The forecast agent gets
`forecast_a2a_timeout_s` = 60 s (ADR-072).
"""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass

from schemas import DATASET_WINDOW_END

A2A_AUTH_MODES = ("none", "google_id_token")


def _a2a_auth(raw: str | None) -> str:
    mode = (raw or "none").strip().lower()
    if mode not in A2A_AUTH_MODES:
        raise ValueError(f"A2A_AUTH must be one of {', '.join(A2A_AUTH_MODES)}, got {raw!r}")
    return mode


@dataclass(frozen=True)
class Settings:
    #: Base URL the reporting agent's Agent Card is fetched from (well-known path).
    agent_reporting_url: str = "http://agent_reporting:8001"
    #: Base URL the sentiment agent's Agent Card is fetched from (ADR-068).
    agent_sentiment_url: str = "http://agent_sentiment:8002"
    #: Base URL the forecast agent's Agent Card is fetched from (ADR-072).
    agent_forecast_url: str = "http://agent_forecast:8003"
    #: The routing LLM call, retries and 429 waits included.
    route_timeout_s: float = 30.0
    #: Whole A2A exchange, card fetch included. Must exceed the agent's parse + MCP time.
    a2a_timeout_s: float = 60.0
    #: The sentiment agent's whole A2A exchange: parse (30 s) plus MCP (45 s), with margin.
    sentiment_a2a_timeout_s: float = 85.0
    #: The forecast agent's whole A2A exchange: parse (30 s) plus MCP (20 s), with margin.
    forecast_a2a_timeout_s: float = 60.0
    #: Given to the routing prompt as today's date. Same variable and default as the
    #: reporting agent's (ADR-050), so both read dates against one "today" (ADR-054).
    as_of: dt.date = DATASET_WINDOW_END
    #: "none" (local) or "google_id_token": attach a Google ID token to every A2A request
    #: (Cloud Run IAM). Anything else is rejected at start-up.
    a2a_auth: str = "none"
    host: str = "0.0.0.0"
    port: int = 8000

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ.get
        d = cls()
        return cls(
            agent_reporting_url=env("AGENT_REPORTING_URL", d.agent_reporting_url),
            agent_sentiment_url=env("AGENT_SENTIMENT_URL", d.agent_sentiment_url),
            agent_forecast_url=env("AGENT_FORECAST_URL", d.agent_forecast_url),
            route_timeout_s=float(env("ROUTE_TIMEOUT_S", str(d.route_timeout_s))),
            a2a_timeout_s=float(env("A2A_TIMEOUT_S", str(d.a2a_timeout_s))),
            sentiment_a2a_timeout_s=float(
                env("SENTIMENT_A2A_TIMEOUT_S", str(d.sentiment_a2a_timeout_s))
            ),
            forecast_a2a_timeout_s=float(
                env("FORECAST_A2A_TIMEOUT_S", str(d.forecast_a2a_timeout_s))
            ),
            as_of=dt.date.fromisoformat(env("REPORTING_AS_OF_DATE") or d.as_of.isoformat()),
            a2a_auth=_a2a_auth(env("A2A_AUTH")),
            port=int(env("ORCHESTRATOR_PORT", str(d.port))),
        )
