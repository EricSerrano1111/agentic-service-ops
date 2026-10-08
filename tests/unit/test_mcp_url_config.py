"""Each agent reads its MCP server URL from an env var (compose name locally,
`http://localhost:<port>/mcp` as a sidecar on Cloud Run)."""

from __future__ import annotations

import pytest
from agent_forecast.config import Settings as Forecast
from agent_reporting.config import Settings as Reporting
from agent_sentiment.config import Settings as Sentiment

CASES = [
    (Reporting, "MCP_INCIDENTS_URL", "mcp_incidents_url", "http://mcp_incidents:8101/mcp"),
    (Sentiment, "MCP_FEEDBACK_URL", "mcp_feedback_url", "http://mcp_feedback:8102/mcp"),
    (Forecast, "MCP_VOLUME_URL", "mcp_volume_url", "http://mcp_volume:8103/mcp"),
]


@pytest.mark.parametrize(("cls", "var", "attr", "default"), CASES)
def test_default_is_the_compose_service_name(monkeypatch, cls, var, attr, default):
    monkeypatch.delenv(var, raising=False)
    assert getattr(cls.from_env(), attr) == default


@pytest.mark.parametrize(("cls", "var", "attr", "default"), CASES)
def test_env_var_overrides_for_a_sidecar(monkeypatch, cls, var, attr, default):
    monkeypatch.setenv(var, "http://localhost:9999/mcp")
    assert getattr(cls.from_env(), attr) == "http://localhost:9999/mcp"
