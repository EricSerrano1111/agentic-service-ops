"""The harness's world: the three specialists and their tool servers in process, QA's real
checks over the real local database, and one rolled-back transaction for database faults.

Nothing here calls a model. The specialists run through the real A2A SDK with a fixed parse
(the item's expected request), their MCP calls go to the real server code, and QA is given a
fake interpretation client that always answers `faithful` (QA's interpretation check is
advisory, L-74, and never changes a verdict).

Database faults run on one shared connection that ignores commit, rollback and close, so the
specialist's tool server and QA both read the open transaction; the harness ends it itself
with a rollback. Row counts and a checksum of `sentiment_predictions` are taken before and
after to show nothing changed for anyone else.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import psycopg
from a2a.client import ClientConfig, create_client
from a2a.types import Message, Part, Role, SendMessageRequest, TaskState
from agent_forecast import executor as forecast_executor
from agent_forecast.app import create_app as create_forecast_app
from agent_forecast.config import Settings as ForecastAgentSettings
from agent_qa import forecast as qa_forecast
from agent_qa import sentiment as qa_sentiment
from agent_qa.config import Settings as QASettings
from agent_qa.db import PostgresSource
from agent_qa.interpretation import Judgement
from agent_qa.verify import Verifier
from agent_reporting import executor as reporting_executor
from agent_reporting.app import create_app as create_reporting_app
from agent_reporting.config import Settings as ReportingAgentSettings
from agent_sentiment import executor as sentiment_executor
from agent_sentiment.app import create_app as create_sentiment_app
from agent_sentiment.config import Settings as SentimentAgentSettings
from dotenv import load_dotenv
from google.protobuf.json_format import MessageToDict
from llm import LLMResult
from mcp import Client
from mcp_feedback.config import Settings as FeedbackSettings
from mcp_feedback.server import Backend as FeedbackBackend
from mcp_feedback.server import create_server as create_feedback_server
from mcp_feedback.store import SqlStore as FeedbackStore
from mcp_incidents.config import Settings as IncidentsSettings
from mcp_incidents.server import create_server as create_incidents_server
from mcp_volume.artifact import load_verified
from mcp_volume.config import Settings as VolumeSettings
from mcp_volume.server import Backend as VolumeBackend
from mcp_volume.server import create_server as create_volume_server
from mcp_volume.store import SqlStore as VolumeStore
from mcp_volume.store import make_engine as make_volume_engine
from schemas import (
    DATASET_WINDOW_END,
    ForecastRequest,
    ReportingRequest,
    SentimentRequest,
    VerificationRequest,
)
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool, StaticPool

REPO = Path(__file__).resolve().parents[2]
AS_OF = DATASET_WINDOW_END
BASE_URL = "http://agent.test"
VOLUME_ARTIFACTS = REPO / "models" / "forecast" / "volume_v2"
VOLUME_MANIFEST = REPO / "ml" / "forecast" / "artifacts" / "volume_v2.manifest.json"
SENTIMENT_MANIFEST = REPO / "ml" / "sentiment" / "artifacts" / "bert_v1.manifest.json"

REQUEST_MODELS = {
    "reporting": ReportingRequest,
    "forecast": ForecastRequest,
    "sentiment": SentimentRequest,
}
DECLINE_CODES = {
    "not_supported",
    "technician_not_found",
    "technician_ambiguous",
    "account_not_found",
    "account_ambiguous",
}


def connect_args() -> dict[str, Any]:
    return {
        "host": os.environ["POSTGRES_HOST"],
        "port": os.environ["POSTGRES_PORT"],
        "dbname": os.environ["POSTGRES_DB"],
    }


def role_url(user_var: str, password_var: str) -> URL:
    return URL.create(
        "postgresql+psycopg",
        username=os.environ[user_var],
        password=os.environ[password_var],
        host=os.environ["POSTGRES_HOST"],
        port=int(os.environ["POSTGRES_PORT"]),
        database=os.environ["POSTGRES_DB"],
    )


def admin_connection(cls: type = psycopg.Connection, **kwargs):
    return cls.connect(
        **connect_args(),
        user=os.environ["POSTGRES_ADMIN_USER"],
        password=os.environ["POSTGRES_ADMIN_PASSWORD"],
        **kwargs,
    )


class HeldOpen(psycopg.Connection):
    """Ignores commit, rollback and close, so nothing SQLAlchemy does ends the transaction."""

    def commit(self):
        return None

    def rollback(self):
        return None

    def close(self):
        return None

    def end(self):
        psycopg.Connection.rollback(self)
        psycopg.Connection.close(self)


class NoScoring:
    def predict(self, texts):  # the feedback server's cap is 0: it never scores
        raise AssertionError("the server tried to score a comment")


class Fixed:
    """`LLMClient.generate` stand-in that returns one fixed parse."""

    def __init__(self, parsed) -> None:
        self.parsed = parsed

    async def generate(self, prompt, *, model=None, response_model=None, trace_id):
        return LLMResult(
            text=self.parsed.model_dump_json(),
            parsed=self.parsed,
            model="fixed",
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            latency_s=0.0,
            attempts=1,
        )


class AlwaysFaithful:
    """The fake interpretation client: advisory mode never lets it change a verdict, and the
    prompt's reading is kept so the results can show what the real check would have been given."""

    def __init__(self) -> None:
        self.readings: list[tuple[str, str]] = []

    async def judge(self, domain, question, reading, *, trace_id):
        self.readings.append((question, reading))
        return Judgement(meaning="", faithful=True, differs_in=[])


@dataclass
class Reply:
    """What one specialist returned for one question."""

    kind: str  # answer | decline | other
    text: str
    answer: dict | None = None
    error_code: str | None = None
    parsed_request: dict | None = None


def feedback_settings() -> FeedbackSettings:
    return FeedbackSettings(
        db_host=os.environ["POSTGRES_HOST"],
        db_port=int(os.environ["POSTGRES_PORT"]),
        db_name=os.environ["POSTGRES_DB"],
        db_user=os.environ["DB_ROLE_SENTIMENT_USER"],
        db_password=os.environ["DB_ROLE_SENTIMENT_PASSWORD"],
    )


@dataclass
class Stack:
    """Everything in process. Build once; `shared_transaction` swaps the feedback server and
    QA's source onto one open transaction for a database fault."""

    sentiment_manifest: qa_sentiment.SentimentManifest
    forecast_manifest: qa_forecast.Manifest
    incidents: Any = None
    volume: Any = None
    feedback: Any = None
    qa_engine: Any = None
    feedback_engine: Any = None
    interpreter: AlwaysFaithful = field(default_factory=AlwaysFaithful)
    _source: Any = None

    # ------------------------------------------------------------------ construction

    @classmethod
    def open(cls) -> Stack:
        load_dotenv(REPO / ".env", override=False)
        stack = cls(
            sentiment_manifest=qa_sentiment.SentimentManifest.load(SENTIMENT_MANIFEST),
            forecast_manifest=qa_forecast.Manifest.load(VOLUME_MANIFEST),
        )
        stack.incidents = create_incidents_server(IncidentsSettings.from_env())
        volume_settings = VolumeSettings(
            db_host=os.environ["POSTGRES_HOST"],
            db_port=int(os.environ["POSTGRES_PORT"]),
            db_name=os.environ["POSTGRES_DB"],
            db_user=os.environ["DB_ROLE_FORECAST_USER"],
            db_password=os.environ["DB_ROLE_FORECAST_PASSWORD"],
        )
        store = VolumeStore(make_volume_engine(volume_settings))
        stack.volume = create_volume_server(
            volume_settings,
            VolumeBackend(
                artifact=load_verified(VOLUME_ARTIFACTS, VOLUME_MANIFEST),
                history=store.history,
                ready=store.ping,
            ),
        )
        stack.feedback_engine = create_engine(
            role_url("DB_ROLE_SENTIMENT_USER", "DB_ROLE_SENTIMENT_PASSWORD"), poolclass=NullPool
        )
        stack.feedback = stack._feedback_server(stack.feedback_engine)
        stack.qa_engine = create_engine(
            role_url("DB_ROLE_QA_USER", "DB_ROLE_QA_PASSWORD"), poolclass=NullPool
        )
        stack._source = PostgresSource(stack.qa_engine)
        for module, server in (
            (reporting_executor, lambda: stack.incidents),
            (forecast_executor, lambda: stack.volume),
            (sentiment_executor, lambda: stack.feedback),
        ):
            module.call_tool = stack._caller(server, module.McpToolError)
        return stack

    def _feedback_server(self, engine):
        store = FeedbackStore(engine)
        return create_feedback_server(
            feedback_settings(),
            FeedbackBackend(store, NoScoring(), self.sentiment_manifest.version, 0, store.ping),
        )

    @staticmethod
    def _caller(server_of, error):
        async def call(url, tool, arguments, result_model, *, trace_id, timeout_s):
            async with Client(server_of()) as client:
                result = await client.call_tool(tool, arguments)
            if result.is_error:
                raise error(str(result.content))
            return result_model.model_validate(result.structured_content)

        return call

    # ------------------------------------------------------------------ QA

    def qa_settings(self) -> QASettings:
        return QASettings(db_host="x", db_port=5432, db_name="x", db_user="x", as_of=AS_OF)

    def verifier(self, source=None) -> Verifier:
        return Verifier(
            source or self._source,
            self.qa_settings(),
            self.forecast_manifest,
            self.sentiment_manifest,
            self.interpreter,
        )

    async def verify(self, req: VerificationRequest, source=None):
        return await self.verifier(source).verify(req, trace_id=None)

    @property
    def source(self):
        return self._source

    # ------------------------------------------------------------------ the specialists

    async def ask(self, agent: str, request: dict | Any) -> Reply:
        """Run the real specialist, with `request` as its parse, and return what it said."""
        model = REQUEST_MODELS[agent]
        parsed = request if isinstance(request, model) else model.model_validate(request)
        make = {
            "reporting": lambda: create_reporting_app(
                ReportingAgentSettings(public_url=f"{BASE_URL}/"), Fixed(parsed)
            ),
            "forecast": lambda: create_forecast_app(
                ForecastAgentSettings(public_url=f"{BASE_URL}/"), Fixed(parsed)
            ),
            "sentiment": lambda: create_sentiment_app(
                SentimentAgentSettings(public_url=f"{BASE_URL}/"), Fixed(parsed)
            ),
        }[agent]
        app = make()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=BASE_URL
        ) as http:
            client = await create_client(
                BASE_URL, client_config=ClientConfig(streaming=False, httpx_client=http)
            )
            message = Message(
                message_id=uuid.uuid4().hex, role=Role.ROLE_USER, parts=[Part(text="q")]
            )
            task = None
            async for event in client.send_message(SendMessageRequest(message=message)):
                task = event.task
                break
        if task is None:
            return Reply("other", "")
        if task.status.state == TaskState.TASK_STATE_COMPLETED:
            text_part, data_part = task.artifacts[0].parts
            return Reply("answer", text_part.text, answer=MessageToDict(data_part.data))
        meta = MessageToDict(task.status.message.metadata) if task.status.message else {}
        code = meta.get("error_code")
        text = task.status.message.parts[0].text if task.status.message.parts else ""
        kind = "decline" if code in DECLINE_CODES else "other"
        return Reply(kind, text, error_code=code, parsed_request=meta.get("parsed_request"))

    # ------------------------------------------------------------------ database faults

    @contextlib.contextmanager
    def shared_transaction(self) -> Iterator[tuple[Any, PostgresSource]]:
        """One open admin transaction that the feedback server and QA both read. Yields the
        raw connection (for the mutation) and QA's source. Always rolled back."""
        conn = admin_connection(HeldOpen)
        shared = create_engine(
            "postgresql+psycopg://",
            creator=lambda: conn,
            poolclass=StaticPool,
            pool_reset_on_return=None,
        )
        previous = self.feedback
        try:
            with shared.connect() as first:  # let the dialect initialise before any change
                first.exec_driver_sql("SELECT 1")
            self.feedback = self._feedback_server(shared)
            yield conn, PostgresSource(shared)
        finally:
            self.feedback = previous
            conn.end()
            shared.dispose()

    def checksum(self) -> dict[str, Any]:
        """Row counts of the tables a fault may touch and a checksum of the predictions."""
        with admin_connection() as conn:
            counts = {
                t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]  # noqa: S608
                for t in ("sentiment_predictions", "service_feedback", "service_requests")
            }
            digest = conn.execute(
                "SELECT md5(string_agg(feedback_id::text || model_version || predicted_label"
                " || confidence::text || flagged::text, ',' ORDER BY feedback_id, model_version))"
                " FROM sentiment_predictions"
            ).fetchone()[0]
        return {**counts, "predictions_md5": digest}

    def close(self) -> None:
        for engine in (self.qa_engine, self.feedback_engine):
            if engine is not None:
                engine.dispose()


def digest(obj: Any) -> str:
    import json

    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:12]
