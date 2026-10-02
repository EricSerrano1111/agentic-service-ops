"""`python -m mcp_volume` — verify the artifact, then serve /mcp and /healthz.

Start-up checks every artifact file's SHA-256 against the manifest; a mismatch stops the
process before it listens.
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
    configure_logging("mcp_volume", os.environ.get("LOG_LEVEL", "INFO"))
    uvicorn.run(app, host=settings.host, port=settings.port, log_config=None)


if __name__ == "__main__":
    main()
