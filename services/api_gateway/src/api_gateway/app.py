"""The gateway: invite-link sign-in, the static UI, and `/api` in front of the orchestrator.

The security model is ADR-097; the display rules are data dictionary §6, "Answer display (UI)".

- Public: the static files, `POST /auth/exchange`, `POST /auth/logout`, `GET /healthz`.
- Everything under `/api/` is on a router whose dependency requires a valid session, so a
  route added there later is protected by construction (and a test enumerates the routes).
- Logs carry the invite id and label, never a token, cookie value or hash.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import time
from collections.abc import Callable
from typing import Any

from common import TraceAccessLog, current_trace_id, text_fields
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import csp, session
from .config import Settings
from .interpret import view
from .invites import Invite, InviteStore, find_by_id, find_by_token
from .limits import DailyCap, SlidingWindow
from .serving import UIFiles
from .upstream import Orchestrator, OrchestratorTimeout, OrchestratorUnavailable

log = logging.getLogger("gateway")

MAX_BODY_BYTES = 4096
MAX_QUESTION_CHARS = 500
#: Upstream `error` code -> (status, message). The message is the gateway's own fixed sentence;
#: the orchestrator's `detail` is never shown, it is logged with the trace ID (data dictionary §6,
#: "Answer display (UI)", rule 5). The status is the upstream's, kept when it is one of these.
DATA_UNAVAILABLE = "The data service is unavailable right now. Please try again later."
UPSTREAM_MESSAGES: dict[str, tuple[int, str]] = {
    "agent_task_failed": (502, DATA_UNAVAILABLE),
    "agent_unavailable": (502, DATA_UNAVAILABLE),
    # Deployed sentiment found a comment with no stored prediction (ADR-100): a pipeline fault.
    "predictions_incomplete": (502, DATA_UNAVAILABLE),
    "unclear_question": (422, "I couldn't interpret the question. Please rephrase it."),
    "invalid_range": (
        422,
        "The date range in the question can't be answered. Please check the dates and try again.",
    ),
    "rate_limited": (
        429,
        "The language model is rate-limited right now. Please try again in about a minute.",
    ),
    "daily_quota_exhausted": (
        503,
        "The language model's daily quota is used up. It resets at midnight Pacific time.",
    ),
    "model_unavailable": (
        503,
        "The language model is temporarily unavailable. Please try again shortly.",
    ),
    "internal_error": (500, "Something went wrong on our side. Please try again."),
}
UNKNOWN_UPSTREAM = "The service could not answer. Please try again."
DEADLINE_MESSAGE = (
    "The question took too long to answer. Please try again, or ask for a shorter period."
)
LOGGED_DETAIL_CHARS = 300
HSTS = "max-age=63072000; includeSubDomains"


class Reject(Exception):
    def __init__(self, status: int, error: str, detail: str | None = None) -> None:
        self.status, self.error, self.detail = status, error, detail


class AskBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    question: str = Field(max_length=MAX_QUESTION_CHARS * 4)

    @field_validator("question")
    @classmethod
    def _trimmed(cls, value: str) -> str:
        value = value.strip()
        if not value or len(value) > MAX_QUESTION_CHARS:
            raise ValueError("question length")
        return value


class ExchangeBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    token: str


def _error(status: int, error: str, detail: str | None = None) -> JSONResponse:
    body: dict[str, str] = {"error": error}
    if detail:
        body["detail"] = detail
    return JSONResponse(body, status_code=status, headers={"Cache-Control": "no-store"})


def client_ip(request: Request, trusted_hops: int) -> str:
    """The caller's address (ADR-097): the `X-Forwarded-For` entry `trusted_hops` from the
    right (default 1, the last: the one Cloud Run's front end appends), never the leftmost,
    which the client can set. With no such entry, the socket peer."""
    header = request.headers.get("x-forwarded-for", "")
    entries = [e.strip() for e in header.split(",") if e.strip()]
    if len(entries) >= trusted_hops >= 1:
        return entries[-trusted_hops]
    return request.client.host if request.client else "unknown"


async def read_json(request: Request) -> Any:
    """The JSON body, refusing a body over `MAX_BODY_BYTES` before reading all of it."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise Reject(413, "too_large")
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise Reject(413, "too_large")
        chunks.append(chunk)
    try:
        return json.loads(b"".join(chunks))
    except ValueError:
        raise Reject(400, "invalid_request") from None


def create_app(
    settings: Settings,
    store: InviteStore,
    orchestrator: Orchestrator,
    *,
    clock: Callable[[], float] = time.time,
    now: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.UTC),
    exchange_window: SlidingWindow | None = None,
    session_window: SlidingWindow | None = None,
    daily: DailyCap | None = None,
) -> FastAPI:
    app = FastAPI(title="gateway", docs_url=None, redoc_url=None, openapi_url=None)
    exchange_limit = exchange_window or SlidingWindow(settings.exchange_per_minute, 60.0)
    session_limit = session_window or SlidingWindow(settings.asks_per_session_hour, 3600.0)
    daily_cap = daily or DailyCap(settings.daily_question_cap, now)

    policy = None
    if settings.static_dir is not None:
        policy = csp.load_policy(settings.static_dir)  # raises: never serve an export unhashed
    api_policy = csp.build_policy([])

    # -- errors: fixed bodies, nothing of the cause ---------------------------------------
    @app.exception_handler(Reject)
    async def _reject(_: Request, exc: Reject) -> JSONResponse:
        return _error(exc.status, exc.error, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def _invalid(_: Request, __: RequestValidationError) -> JSONResponse:
        return _error(422, "invalid_request")  # the default handler echoes the input

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _error(exc.status_code, "not_found" if exc.status_code == 404 else "error")

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled error", extra={"error": type(exc).__name__})
        return _error(500, "internal_error")

    # -- headers on every response ---------------------------------------------------------
    @app.middleware("http")
    async def headers(request: Request, call_next) -> Response:
        response = await call_next(request)
        api = request.url.path.startswith(("/api/", "/auth/"))
        h = response.headers
        h["Content-Security-Policy"] = api_policy if api or policy is None else policy
        h["Referrer-Policy"] = "no-referrer"
        h["X-Content-Type-Options"] = "nosniff"
        h["Strict-Transport-Security"] = HSTS
        if api:
            h["Cache-Control"] = "no-store"
        return response

    # Outermost: every response, errors and static files included, carries the trace id, and one
    # access line per request is written with it (ADR-108). The gateway mints it when none came.
    app.add_middleware(TraceAccessLog, mint=True)

    # -- shared checks ----------------------------------------------------------------------
    def check_csrf(request: Request) -> None:
        """Same-origin JSON only: the Origin must be this gateway's, the body JSON. (The cookie is
        also SameSite=Strict.)"""
        if request.headers.get("origin") != settings.public_origin:
            raise Reject(403, "forbidden")
        media = request.headers.get("content-type", "").split(";")[0].strip().lower()
        if media != "application/json":
            raise Reject(403, "forbidden")

    def current_invite(request: Request) -> Invite | None:
        value = request.cookies.get(session.COOKIE_NAME)
        if not value:
            return None
        claims = session.verify(value, settings.session_key, clock())
        if claims is None:
            return None
        # Re-checked on every request: a revoked or expired invite ends its sessions.
        return find_by_id(store.invites(), claims.invite_id, now())

    def require_session(request: Request) -> Invite:
        invite = current_invite(request)
        if invite is None:
            raise Reject(401, "sign_in_required")
        return invite

    # -- public routes ----------------------------------------------------------------------
    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    # Cloud Run's front end reserves `/healthz` on a service's public URL (the request never
    # reaches the container), so the public reachability probe is `/health` (ADR-097 note).
    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/auth/exchange")
    async def exchange(request: Request) -> Response:
        ip = client_ip(request, settings.trusted_proxy_hops)
        if not exchange_limit.hit(ip):
            return _error(429, "too_many_attempts", "Too many attempts. Try again in a minute.")
        check_csrf(request)
        invalid = _error(401, "invalid_invite", "This invite link is not valid.")
        try:
            token = ExchangeBody.model_validate(await read_json(request)).token
        except (Reject, ValidationError):
            return invalid  # a malformed body is indistinguishable from a bad token
        invite = find_by_token(store.invites(), token, now())
        if invite is None:
            log.info("exchange refused")
            return invalid
        issued = clock()
        expires = min(invite.expires_at.timestamp(), issued + session.MAX_SESSION_S)
        value = session.sign(
            session.SessionClaims(invite.id, issued, expires), settings.session_key
        )
        response = JSONResponse({"signed_in": True}, headers={"Cache-Control": "no-store"})
        response.set_cookie(
            session.COOKIE_NAME,
            value,
            max_age=max(1, int(expires - issued)),
            path="/",
            secure=True,
            httponly=True,
            samesite="strict",
        )
        log.info("exchange ok", extra={"invite_id": invite.id, "invite_label": invite.label})
        return response

    @app.post("/auth/logout")
    async def logout(request: Request) -> Response:
        check_csrf(request)
        response = JSONResponse({"signed_in": False}, headers={"Cache-Control": "no-store"})
        response.delete_cookie(
            session.COOKIE_NAME, path="/", secure=True, httponly=True, samesite="strict"
        )
        return response

    # -- /api: every route needs a session ---------------------------------------------------
    api = APIRouter(prefix="/api", dependencies=[Depends(require_session)])

    @api.get("/session")
    async def whoami() -> dict[str, bool]:
        return {"signed_in": True}

    @api.post("/ask")
    async def ask(request: Request) -> Response:
        invite = require_session(request)  # also enforced by the router's dependency
        check_csrf(request)
        try:
            question = AskBody.model_validate(await read_json(request)).question
        except ValidationError:
            raise Reject(422, "invalid_request") from None
        if not session_limit.hit(invite.id):
            raise Reject(
                429,
                "session_limit",
                f"Too many questions this hour (limit {settings.asks_per_session_hour}). "
                "Please try again later.",
            )
        if not daily_cap.take():
            raise Reject(
                429,
                "daily_limit",
                "Daily limit reached: this demo answers a fixed number of questions a day. "
                "It resets at midnight Pacific time.",
            )
        try:
            forwarded = time.perf_counter()
            status, body = await orchestrator.ask(question, trace_id=current_trace_id())
            forward_ms = (time.perf_counter() - forwarded) * 1000
        except OrchestratorTimeout:
            raise Reject(504, "deadline_exceeded", DEADLINE_MESSAGE) from None
        except OrchestratorUnavailable:
            raise Reject(
                503, "service_unavailable", "The service is temporarily unavailable. Try again."
            ) from None
        if status == 200:
            log.info(
                "ask answered",
                extra={
                    "invite_id": invite.id,
                    "invite_label": invite.label,
                    "outcome": body.get("outcome"),
                    "qa_status": body.get("qa_status"),
                    "upstream_trace_id": body.get("trace_id"),
                    "question_chars": len(question),
                },
            )
            return JSONResponse(
                view(question, body, forward_ms), headers={"Cache-Control": "no-store"}
            )
        code, detail = body.get("error"), body.get("detail")
        log.info(
            "ask refused upstream",
            extra={
                "invite_id": invite.id,
                "status": status,
                "upstream_error": code[:40] if isinstance(code, str) else None,
                # Never returned and no longer logged as text: it can be an agent's own task
                # sentence, which can name what the user typed (L-89, ADR-108).
                **(text_fields("upstream_detail", detail) if isinstance(detail, str) else {}),
                "upstream_trace_id": body.get("trace_id"),
            },
        )
        mapped = UPSTREAM_MESSAGES.get(code) if isinstance(code, str) else None
        if mapped is not None and mapped[0] == status:
            raise Reject(status, code, mapped[1])
        raise Reject(502, "upstream_error", UNKNOWN_UPSTREAM)

    app.include_router(api)

    # Last, so it never shadows an API or auth route.
    if settings.static_dir is not None:
        app.mount("/", UIFiles(directory=settings.static_dir, html=True), name="ui")
    return app
