"""`python -m agent_reporting` — serve the A2A endpoint."""

from __future__ import annotations

import os

import uvicorn
from common import configure_logging

from .app import create_app
from .config import Settings


def main() -> None:
    settings = Settings.from_env()
    configure_logging("agent_reporting", os.environ.get("LOG_LEVEL", "INFO"))
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_config=None)


if __name__ == "__main__":
    main()
