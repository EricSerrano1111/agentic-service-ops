"""`mcp_volume` and the forecast agent against the live database (ADR-072).

- History, read as `app_forecast` with the shared week rule, equals hand-written SQL run as
  `app_eval` (ADR-063): a different role and a different code path.
- The forecast agent runs in-process through the real A2A SDK with fixed
  `ForecastRequest`s; its MCP calls go to the real `mcp_volume` server code in-process.
  Forecasts come from the real `volume_v2` artifact when it is present locally, else from a
  hand-built one (CI has no `models/`); history comes from the live database either way.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import uuid
from pathlib import Path

import httpx
import numpy as np
import pytest
from a2a.client import ClientConfig, create_client
from a2a.types import Message, Part, Role, SendMessageRequest, TaskState
from agent_forecast import executor as executor_mod
from agent_forecast.app import create_app
from agent_forecast.config import Settings as AgentSettings
from agent_forecast.render import render_answer
from db_models.access_matrix import ROLE_EVAL
from google.protobuf.json_format import MessageToDict
from llm import LLMResult
from mcp import Client
from mcp_volume.artifact import load_verified
from mcp_volume.config import Settings as VolumeSettings
from mcp_volume.server import Backend, create_server
from mcp_volume.store import SqlStore, make_engine
from schemas import FORECAST_SLICES, HORIZON_BANDS, ForecastAnswer, ForecastRequest

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
REPO = Path(__file__).resolve().parents[2]
REAL_DIR = REPO / "models" / "forecast" / "volume_v2"
REAL_MANIFEST = REPO / "ml" / "forecast" / "artifacts" / "volume_v2.manifest.json"
BASE = "http://agent.test"

# Independent of the store: literal SQL, the 52 weeks before Monday 2026-08-31 (UTC).
WEEKLY_SQL = """
    SELECT ((scheduled_datetime AT TIME ZONE 'UTC')::date - DATE '2023-09-04') / 7 AS w,
           count(*)
    FROM service_requests
    WHERE scheduled_datetime >= TIMESTAMPTZ '2025-09-01 00:00+00'
      AND scheduled_datetime <  TIMESTAMPTZ '2026-08-31 00:00+00'
      AND (%(slice)s = 'total' OR service_type = %(slice)s)
    GROUP BY 1
"""


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
def store(live_database) -> SqlStore:
    return SqlStore(
        make_engine(
            VolumeSettings(
                db_host=os.environ["POSTGRES_HOST"],
                db_port=int(os.environ["POSTGRES_PORT"]),
                db_name=os.environ["POSTGRES_DB"],
                db_user=os.environ["DB_ROLE_FORECAST_USER"],
                db_password=os.environ["DB_ROLE_FORECAST_PASSWORD"],
            )
        )
    )


@pytest.mark.parametrize("slice_", ["total", "repair", "upgrade"])
@pytest.mark.parametrize("weeks", [1, 8, 52])
async def test_history_matches_independent_sql(loaded_database, connect_as, store, slice_, weeks):
    got = store.history(slice_, weeks)
    rows = dict(connect_as(ROLE_EVAL).execute(WEEKLY_SQL, {"slice": slice_}).fetchall())
    expected = [rows.get(w, 0) for w in range(156 - weeks, 156)]
    assert [h.count for h in got.weeks] == expected
    assert got.weeks[-1].week_start == dt.date(2026, 8, 24)
    assert got.weeks[0].week_start == dt.date(2026, 8, 24) - dt.timedelta(weeks=weeks - 1)


def _synthetic_artifact(tmp: Path) -> tuple[Path, Path]:
    files = {}
    for i, name in enumerate(FORECAST_SLICES):
        rec = {
            "slice": name,
            "k": 1,
            "year_end": True,
            "params": [4.0 + 0.1 * i, 0.001, -0.15, 0.2, 0.1],
            "scale": 0.1,
            "xtwx_inv": (np.eye(5) * 1e-3).tolist(),
            "last_t": 155,
            "horizon_cap": 26,
        }
        p = tmp / f"{name}.json"
        p.write_text(json.dumps(rec), encoding="utf-8")
        files[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    served = {("total", b) for b in HORIZON_BANDS} | {("install", "5-13"), ("repair", "5-13")}
    manifest = {
        "trained_on": ["2023-09-04", "2026-08-24"],
        "files": files,
        "serving_rule": "ADR-071",
        "serving": {
            "slices": {
                s: {b: {"served": (s, b) in served, "shown_error": 12.5} for b in HORIZON_BANDS}
                for s in FORECAST_SLICES
            }
        },
    }
    m = tmp / "volume_test.manifest.json"
    m.write_text(json.dumps(manifest), encoding="utf-8")
    return tmp, m


@pytest.fixture
def volume_backend(store, tmp_path, monkeypatch):
    directory, manifest = (
        (REAL_DIR, REAL_MANIFEST) if REAL_DIR.exists() else _synthetic_artifact(tmp_path)
    )
    artifact = load_verified(directory, manifest)
    server = create_server(
        VolumeSettings(db_host="-", db_port=0, db_name="-", db_user="-"),
        Backend(artifact=artifact, history=store.history, ready=store.ping),
    )

    async def in_process(url, tool, arguments, result_model, *, trace_id, timeout_s):
        async with Client(server) as client:
            result = await client.call_tool(tool, arguments)
        assert not result.is_error, result.content
        return result_model.model_validate(result.structured_content)

    monkeypatch.setattr(executor_mod, "call_tool", in_process)
    return artifact


class FixedLLM:
    def __init__(self, request: ForecastRequest) -> None:
        self.request = request

    async def generate(self, prompt, *, model=None, response_model=None, trace_id):
        return LLMResult(
            text=self.request.model_dump_json(),
            parsed=self.request,
            model="fixed",
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            latency_s=0.0,
            attempts=1,
        )


async def _ask(request: ForecastRequest) -> ForecastAnswer:
    app = create_app(AgentSettings(public_url=f"{BASE}/"), FixedLLM(request))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as http:
        client = await create_client(
            BASE, client_config=ClientConfig(streaming=False, httpx_client=http)
        )
        message = Message(message_id=uuid.uuid4().hex, role=Role.ROLE_USER, parts=[Part(text="q")])
        async for event in client.send_message(SendMessageRequest(message=message)):
            task = event.task
            break
    assert task.status.state == TaskState.TASK_STATE_COMPLETED
    text, data = task.artifacts[0].parts
    answer = ForecastAnswer.model_validate(MessageToDict(data.data))
    assert text.text == render_answer(answer)
    return answer


@pytest.mark.parametrize(
    "request_",
    [
        ForecastRequest(slice="install", horizon_weeks=10, want_history=True),
        ForecastRequest(period_start=dt.date(2026, 12, 1), period_end=dt.date(2026, 12, 31)),
        ForecastRequest(horizon_weeks=52),
    ],
    ids=["install-10-weeks", "december", "a-year"],
)
async def test_agent_figures_equal_the_artifact_and_the_database(
    loaded_database, connect_as, volume_backend, request_
):
    a = await _ask(request_)
    direct = volume_backend.forecast(request_.slice, 26)
    by_h = {w.horizon: w for w in direct.weeks}
    for w in a.weeks:
        ref = by_h[w.horizon]
        assert (w.served, w.point, w.lo80, w.hi80) == (ref.served, ref.point, ref.lo80, ref.hi80)
    assert a.model_version == volume_backend.model_version
    if a.period_total is not None:
        assert a.period_total == pytest.approx(sum(w.point for w in a.weeks), abs=1e-9)
    if request_.want_history:
        rows = dict(connect_as(ROLE_EVAL).execute(WEEKLY_SQL, {"slice": request_.slice}).fetchall())
        assert [h.count for h in a.history] == [rows.get(w, 0) for w in range(148, 156)]
    if request_.horizon_weeks == 52:
        assert (len(a.weeks), a.beyond_horizon_weeks) == (26, 26)
