"""Shared builders for the gateway tests: an app over a file store and a stubbed orchestrator.
No model, no network: the orchestrator is an httpx MockTransport."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import httpx
from api_gateway.app import create_app
from api_gateway.config import Settings
from api_gateway.invites import FileInviteStore, Invite, hash_token
from api_gateway.limits import DailyCap, SlidingWindow
from api_gateway.upstream import Orchestrator
from fastapi.testclient import TestClient

ORIGIN = "https://testserver"
KEY = "k" * 48
NOW = dt.datetime(2026, 10, 12, 12, 0, tzinfo=dt.UTC)
JSON_HEADERS = {"Origin": ORIGIN, "Content-Type": "application/json"}


class Clock:
    """A settable clock for time and datetime."""

    def __init__(self) -> None:
        self.t = NOW.timestamp()

    def time(self) -> float:
        return self.t

    def now(self) -> dt.datetime:
        return dt.datetime.fromtimestamp(self.t, dt.UTC)


def answered(**more) -> dict:
    body = {
        "answer": "SLA compliance in the Northeast was 94.1% (2026-09-01 to 2026-09-30).",
        "outcome": "answered",
        "reason": None,
        "route": {"route": "reporting", "reason": "metric question"},
        "prompt_version": "route_v5",
        "reporting": {
            "request": {
                "metric": "sla_compliance",
                "group_by": None,
                "technician_name": None,
                "region": "northeast",
                "account_name": None,
                "start": None,
                "end": None,
            },
            "start": "2026-08-01",
            "end": "2026-08-30",
            "range_assumed": False,
            "as_of": "2026-08-30",
            "figures": {"metric": "sla_compliance"},
        },
        "task_id": "t1",
        "trace_id": "trace-1",
        "escalate": False,
        "warning": None,
        "unavailable_capability": None,
        "qa_status": "verified",
    }
    return body | more


class Upstream:
    """A stubbed orchestrator: records the requests and answers with `status`, `body`."""

    def __init__(self, status: int = 200, body: dict | None = None) -> None:
        self.status, self.body, self.requests = status, body or answered(), []
        self.raise_error: Exception | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.raise_error is not None:
            raise self.raise_error
        return httpx.Response(self.status, json=self.body)


class Kit:
    def __init__(self, tmp_path: Path, **settings) -> None:
        self.clock = Clock()
        self.store = FileInviteStore(tmp_path / "invites.json")
        self.upstream = Upstream()
        self.token = "tok-" + "a" * 40
        self.invite = Invite(
            "inv000000001", "grader", hash_token(self.token), NOW, NOW + dt.timedelta(days=7)
        )
        self.store.save([self.invite])
        fields = {
            "session_key": KEY,
            "public_origin": ORIGIN,
            "orchestrator_url": "http://orchestrator:8000",
        } | settings
        self.settings = Settings(**fields)
        self.orchestrator = Orchestrator(
            self.settings.orchestrator_url,
            5.0,
            transport=httpx.MockTransport(self.upstream.handler),
        )
        self.exchange_window = SlidingWindow(
            self.settings.exchange_per_minute, 60.0, clock=self.clock.time
        )
        self.session_window = SlidingWindow(
            self.settings.asks_per_session_hour, 3600.0, clock=self.clock.time
        )
        self.daily = DailyCap(self.settings.daily_question_cap, self.clock.now)
        self.app = create_app(
            self.settings,
            self.store,
            self.orchestrator,
            clock=self.clock.time,
            now=self.clock.now,
            exchange_window=self.exchange_window,
            session_window=self.session_window,
            daily=self.daily,
        )
        self.client = TestClient(self.app, base_url=ORIGIN)

    def exchange(self, token: str | None = None, **kw):
        body = {"token": self.token if token is None else token}
        return self.client.post("/auth/exchange", json=body, headers={"Origin": ORIGIN}, **kw)

    def sign_in(self) -> str:
        r = self.exchange()
        assert r.status_code == 200, r.text
        return r.cookies["__Host-session"]

    def ask(self, question: str = "What was SLA compliance in the Northeast last month?", **kw):
        return self.client.post(
            "/api/ask", json={"question": question}, headers={"Origin": ORIGIN}, **kw
        )


def raw_post(client: TestClient, path: str, content: bytes, headers: dict | None = None):
    return client.post(path, content=content, headers={**JSON_HEADERS, **(headers or {})})


def dumps(value) -> bytes:
    return json.dumps(value).encode()


def registered_routes(app) -> list[tuple[str, set[str]]]:
    """(path, methods) of every route registered on the app, through included routers (which
    newer FastAPI wraps) and mounts, so a route added later is enumerated too."""
    found: list[tuple[str, set[str]]] = []

    def walk(routes, prefix: str = "") -> None:
        for route in routes:
            inner = getattr(route, "original_router", None)
            if inner is not None:
                walk(inner.routes, prefix + getattr(route.include_context, "prefix", ""))
            elif getattr(route, "methods", None):
                found.append((prefix + route.path, set(route.methods)))
            elif getattr(route, "routes", None):
                walk(route.routes, prefix + getattr(route, "path", ""))

    walk(app.routes)
    return found
