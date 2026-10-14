"""The trace id on every access line and every hop (ADR-108).

`TraceAccessLog` is the shared ASGI middleware; the services that install it are checked
here by reading their sources, and the gateway and orchestrator behaviours (a request with no
id gets one, a valid incoming id is kept and forwarded, a bad one is replaced) have their own
tests beside those services.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import pytest
from common import TRACE_ID_HEADER, JsonFormatter, TraceAccessLog, new_trace_id, valid_trace_id
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
HEX32 = re.compile(r"[0-9a-f]{32}")


async def hello(request):
    return PlainTextResponse("hi")


async def boom(request):
    raise RuntimeError("secret " + "typed text Ada Lovelace")


def make_app(**kw):
    app = Starlette(
        routes=[
            Route("/hello", hello),
            Route("/boom", boom),
            Route("/healthz", hello),
            Route("/readyz", hello),
        ]
    )
    app.add_middleware(TraceAccessLog, **kw)
    return app


class Lines:
    def __enter__(self):
        self.records: list[logging.LogRecord] = []
        self.lines: list[dict] = []
        outer = self
        fmt = JsonFormatter("test")

        class Collect(logging.Handler):
            def emit(self, record):
                outer.records.append(record)
                # Formatted now, as a real handler does: the trace id is read from the context.
                outer.lines.append(json.loads(fmt.format(record)))

        self.handler = Collect(logging.DEBUG)
        self.logger = logging.getLogger("access")
        self.before = (self.logger.level, self.logger.disabled, self.logger.propagate)
        self.logger.addHandler(self.handler)
        self.logger.setLevel(logging.DEBUG)
        self.logger.disabled = False
        return self

    def __exit__(self, *exc):
        self.logger.removeHandler(self.handler)
        self.logger.setLevel(self.before[0])
        self.logger.disabled = self.before[1]

    def json_lines(self):
        return self.lines


@pytest.mark.parametrize("value", ["", "x", "A" * 32, "a" * 31, "a" * 33, "a" * 31 + "\n", None, 5])
def test_only_32_lowercase_hex_is_a_valid_trace_id(value):
    assert valid_trace_id(value) is None


def test_a_minted_id_is_valid():
    assert valid_trace_id(new_trace_id()) is not None


def test_a_valid_incoming_id_is_kept_returned_and_on_the_access_line():
    tid = "ab" * 16
    with Lines() as lines:
        r = TestClient(make_app()).get("/hello?token=secret", headers={TRACE_ID_HEADER: tid})
    assert r.headers[TRACE_ID_HEADER] == tid
    [line] = lines.json_lines()
    assert line["trace_id"] == tid and line["msg"] == "request"
    assert (line["method"], line["path"], line["status"]) == ("GET", "/hello", 200)
    assert "secret" not in json.dumps(line)  # the query string is never logged


def test_an_invalid_incoming_id_is_replaced_when_minting():
    with Lines() as lines:
        r = TestClient(make_app(mint=True)).get("/hello", headers={TRACE_ID_HEADER: "evil\r\nid"})
    assert HEX32.fullmatch(r.headers[TRACE_ID_HEADER])
    assert lines.json_lines()[0]["trace_id"] == r.headers[TRACE_ID_HEADER]


def test_no_id_gets_one_only_when_minting():
    with Lines() as lines:
        minted = TestClient(make_app(mint=True)).get("/hello")
        plain = TestClient(make_app()).get("/hello")
    assert HEX32.fullmatch(minted.headers[TRACE_ID_HEADER])
    assert TRACE_ID_HEADER not in plain.headers
    assert lines.json_lines()[1]["trace_id"] is None


def test_a_probe_is_logged_at_debug_and_a_request_at_info():
    with Lines() as lines:
        client = TestClient(make_app())
        client.get("/healthz")
        client.get("/readyz")
        client.get("/hello")
    assert [r.levelno for r in lines.records] == [logging.DEBUG, logging.DEBUG, logging.INFO]


def test_a_request_that_raises_is_still_logged_as_a_500_without_the_message():
    with Lines() as lines, pytest.raises(RuntimeError):
        TestClient(make_app(mint=True)).get("/boom")
    [line] = lines.json_lines()
    assert line["status"] == 500
    assert "Lovelace" not in json.dumps(line)


@pytest.mark.parametrize(
    "path",
    [
        "services/api_gateway/src/api_gateway/app.py",
        "services/orchestrator/src/orchestrator/app.py",
        "services/agent_reporting/src/agent_reporting/app.py",
        "services/agent_sentiment/src/agent_sentiment/app.py",
        "services/agent_forecast/src/agent_forecast/app.py",
        "services/agent_qa/src/agent_qa/app.py",
        "services/mcp_incidents/src/mcp_incidents/server.py",
        "services/mcp_feedback/src/mcp_feedback/server.py",
        "services/mcp_volume/src/mcp_volume/server.py",
    ],
)
def test_every_http_server_installs_the_access_line(path):
    assert "add_middleware(TraceAccessLog" in (ROOT / path).read_text("utf-8"), path


def test_every_main_turns_uvicorns_own_access_log_off():
    mains = sorted((ROOT / "services").glob("*/src/*/__main__.py"))
    served = [p for p in mains if "uvicorn.run" in p.read_text("utf-8")]
    assert len(served) == 9
    for p in served:
        text = " ".join(p.read_text("utf-8").split())
        assert "access_log=False" in text, p
