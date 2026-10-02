"""The sentiment agent's figures equal independent SQL over `sentiment_predictions` (ADR-068).

The agent runs in-process through the real A2A SDK; its LLM parse is replaced by fixed
`SentimentRequest`s. Its MCP calls go to the real `mcp_feedback` server code, in-process,
against the live database as `app_sentiment`. Predictions are written under a throwaway
`model_version` by a deterministic stub scorer (CI's database holds no stored
predictions), and deleted afterwards as the admin role. Expected figures come from
hand-written SQL run as `app_eval`.

Needs a migrated and loaded database. HTTP between the containers is covered by the e2e run.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import uuid
from collections.abc import Callable, Iterator, Sequence

import httpx
import psycopg
import pytest
from a2a.client import ClientConfig, create_client
from a2a.types import Message, Part, Role, SendMessageRequest, TaskState
from agent_sentiment import executor as executor_mod
from agent_sentiment.app import create_app
from agent_sentiment.config import Settings as AgentSettings
from agent_sentiment.render import render_answer
from db_models.access_matrix import ROLE_EVAL
from google.protobuf.json_format import MessageToDict
from llm import LLMResult
from mcp import Client
from mcp_feedback.classifier import Prediction
from mcp_feedback.config import Settings as FeedbackSettings
from mcp_feedback.server import Backend, create_server
from mcp_feedback.store import SqlStore, make_engine
from schemas import SENTIMENT_LABELS, SentimentAnswer, SentimentRequest

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
ConnectAs = Callable[[str], psycopg.Connection]
BASE = "http://agent.test"


class HashClassifier:
    """Deterministic stand-in for BERT: label and confidence from the text's hash."""

    def predict(self, texts: Sequence[str]) -> list[Prediction]:
        out = []
        for t in texts:
            h = int(hashlib.sha256(t.encode()).hexdigest(), 16)
            conf = 0.5 + (h % 5000) / 10000
            out.append(Prediction(SENTIMENT_LABELS[h % 4], conf, conf < 0.84))
        return out


class FixedLLM:
    def __init__(self, request: SentimentRequest) -> None:
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


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def version(loaded_database) -> Iterator[str]:
    v = f"itest-agent-{uuid.uuid4().hex}"
    yield v
    with psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_ADMIN_USER"],
        password=os.environ["POSTGRES_ADMIN_PASSWORD"],
        autocommit=True,
    ) as admin:
        admin.execute("DELETE FROM sentiment_predictions WHERE model_version = %s", (v,))


@pytest.fixture
def feedback_server(live_database, version, monkeypatch):
    """Route the agent's MCP calls to the real mcp_feedback server code, in-process."""
    settings = FeedbackSettings(
        db_host=os.environ["POSTGRES_HOST"],
        db_port=int(os.environ["POSTGRES_PORT"]),
        db_name=os.environ["POSTGRES_DB"],
        db_user=os.environ["DB_ROLE_SENTIMENT_USER"],
        db_password=os.environ["DB_ROLE_SENTIMENT_PASSWORD"],
    )
    store = SqlStore(make_engine(settings))
    server = create_server(settings, Backend(store, HashClassifier(), version, 250, store.ping))
    calls: list[str] = []

    async def in_process(url, tool, arguments, result_model, *, trace_id, timeout_s):
        calls.append(tool)
        async with Client(server) as client:
            result = await client.call_tool(tool, arguments)
        assert not result.is_error, result.content
        return result_model.model_validate(result.structured_content)

    monkeypatch.setattr(executor_mod, "call_tool", in_process)
    return calls


async def _ask(request: SentimentRequest) -> SentimentAnswer:
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
    answer = SentimentAnswer.model_validate(MessageToDict(data.data))
    assert text.text == render_answer(answer)
    return answer


# Independent of the server and the agent: literal SQL, UTC days, inclusive end day.
SCOPE = """
    FROM service_feedback f
    JOIN service_requests r ON r.request_id = f.request_id
    JOIN locations l ON l.location_id = r.location_id
    JOIN sentiment_predictions p ON p.feedback_id = f.feedback_id AND p.model_version = %(v)s
    WHERE f.submitted_at >= (%(start)s::date)::timestamp AT TIME ZONE 'UTC'
      AND f.submitted_at <  ((%(end)s::date + 1))::timestamp AT TIME ZONE 'UTC'
      AND f.feedback_text IS NOT NULL
      AND (%(region)s::text IS NULL OR l.region = %(region)s::text)
"""
BY_MONTH = (
    "SELECT to_char(f.submitted_at AT TIME ZONE 'UTC', 'YYYY-MM'), p.predicted_label, "
    "count(*), count(*) FILTER (WHERE p.flagged) " + SCOPE + " GROUP BY 1, 2"
)
TOP_EXAMPLES = (
    "SELECT f.feedback_id " + SCOPE + " AND p.predicted_label = %(label)s "
    "ORDER BY p.confidence DESC, f.feedback_id LIMIT 3"
)


@pytest.mark.parametrize(
    "request_",
    [
        SentimentRequest(
            start=dt.date(2026, 3, 1), end=dt.date(2026, 4, 30), region="west", want_trend=True
        ),
        SentimentRequest(
            start=dt.date(2026, 7, 1),
            end=dt.date(2026, 7, 31),
            want_examples=True,
            example_label="negative",
        ),
        SentimentRequest(
            start=dt.date(2026, 5, 1), end=dt.date(2026, 6, 30), region="central", want_trend=True
        ),
    ],
    ids=["west-trend", "july-examples", "central-trend"],
)
async def test_answer_figures_match_independent_sql(
    connect_as: ConnectAs, feedback_server, version, request_
):
    a = await _ask(request_)
    params = {
        "v": version,
        "start": request_.start,
        "end": request_.end,
        "region": request_.region,
        "label": request_.example_label,
    }
    rows = connect_as(ROLE_EVAL).execute(BY_MONTH, params).fetchall()
    n = sum(r[2] for r in rows)
    assert 0 < n <= 250, "pick ranges under the cap so the answer is complete"

    s = a.summary
    assert (s.n_comments, s.n_scored, s.complete, s.model_version) == (n, n, True, version)
    totals = {label: sum(c for _, lab, c, _ in rows if lab == label) for label in SENTIMENT_LABELS}
    assert s.counts.model_dump() == totals
    assert s.flagged_count == sum(r[3] for r in rows)

    months = sorted({m for m, *_ in rows})
    if request_.want_trend:
        t = a.trend
        neg = {m: sum(c for mm, lab, c, _ in rows if mm == m and lab == "negative") for m in months}
        size = {m: sum(c for mm, _, c, _ in rows if mm == m) for m in months}
        assert (t.latest_bucket, t.latest_n, t.latest_negative) == (
            months[-1],
            size[months[-1]],
            neg[months[-1]],
        )
        assert (t.earlier_n, t.earlier_negative) == (
            sum(size[m] for m in months[:-1]),
            sum(neg[m] for m in months[:-1]),
        )
    if request_.want_examples:
        expected = [r[0] for r in connect_as(ROLE_EVAL).execute(TOP_EXAMPLES, params)]
        assert a.quoted_feedback_ids == expected and len(expected) == 3
        assert all(e.label == "negative" for e in a.examples)
    assert feedback_server == (
        ["get_sentiment_summary", "get_feedback_examples"]
        if request_.want_examples
        else ["get_sentiment_summary"]
    )
