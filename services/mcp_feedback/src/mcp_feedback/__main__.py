"""`python -m mcp_feedback` — verify the artifact, then serve /mcp and /healthz.

Start-up reads the manifest and checks every listed file's SHA-256; a mismatch stops the
process before it listens. The model itself loads on the first request that needs
scoring, so start-up is a hash check only.
"""

from __future__ import annotations

import os

import uvicorn
from common import configure_logging

from .config import Settings
from .server import create_app
from .wiring import build_backend


def main() -> None:
    settings = Settings.from_env()
    backend = build_backend(settings)  # raises ArtifactIntegrityError on a bad hash
    app = create_app(settings, backend)
    # After the MCPServer exists: it installs its own root handler, which this replaces.
    configure_logging("mcp_feedback", os.environ.get("LOG_LEVEL", "INFO"))
    uvicorn.run(app, host=settings.host, port=settings.port, log_config=None)


if __name__ == "__main__":
    main()
