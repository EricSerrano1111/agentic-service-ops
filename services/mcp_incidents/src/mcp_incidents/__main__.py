"""`python -m mcp_incidents` — serve the MCP endpoint at /mcp and /healthz."""

from __future__ import annotations

import os

import uvicorn
from common import configure_logging

from .config import Settings
from .server import create_app


def main() -> None:
    settings = Settings.from_env()
    app = create_app(settings)
    # After the MCPServer exists: it installs its own root handler, which this replaces.
    configure_logging("mcp_incidents", os.environ.get("LOG_LEVEL", "INFO"))
    uvicorn.run(app, host=settings.host, port=settings.port, log_config=None)


if __name__ == "__main__":
    main()
