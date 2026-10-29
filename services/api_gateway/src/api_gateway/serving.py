"""The UI export's static mount: cache headers and a path-only trailing-slash redirect (L-105).

Next.js content-hashes everything under `/_next/static/`, so those files never change under a
URL and can be kept for a year. Every other file (each page's `index.html`, favicons, images)
keeps its URL across deploys, so the browser must revalidate it: `no-cache` still allows a cached
copy, but only after an `ETag` / `Last-Modified` check, which Starlette's `FileResponse` answers
with a 304.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from fastapi.staticfiles import StaticFiles
from starlette.responses import RedirectResponse, Response
from starlette.types import Scope

HASHED_PREFIX = "/_next/static/"
REVALIDATE = "no-cache"
IMMUTABLE = "public, max-age=31536000, immutable"


class UIFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if isinstance(response, RedirectResponse):
            # Starlette builds the directory redirect from the request's scheme and host, which
            # behind Cloud Run's front end are `http` and the internal host. The gateway keeps
            # proxy_headers off on purpose, so send path and query only: the browser resolves
            # it against the https URL it is already on.
            target = urlsplit(response.headers["location"])
            relative = target.path + (f"?{target.query}" if target.query else "")
            response.headers["location"] = relative
        elif response.status_code in (200, 304) and scope["path"].startswith(HASHED_PREFIX):
            response.headers["Cache-Control"] = IMMUTABLE
        else:
            response.headers["Cache-Control"] = REVALIDATE
        return response
