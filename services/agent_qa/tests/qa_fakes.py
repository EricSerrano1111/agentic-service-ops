"""Fakes shared by the QA agent's offline tests: a canned database and a canned model."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from agent_qa.config import Settings
from agent_qa.db import GroupRow
from agent_qa.forecast import Manifest
from agent_qa.interpretation import Judgement
from common import add_cost
from llm import LLMResult

REPO = Path(__file__).resolve().parents[3]
MANIFEST_PATH = REPO / "ml" / "forecast" / "artifacts" / "volume_v2.manifest.json"
AS_OF = dt.date(2026, 8, 30)
SETTINGS = Settings(
    db_host="x",
    db_port=5432,
    db_name="x",
    db_user="x",
    public_url="http://agent.test/",
    interp_mode="enforce",  # most tests exercise the check as a gate; advisory has its own
)
ADVISORY = Settings(
    db_host="x",
    db_port=5432,
    db_name="x",
    db_user="x",
    public_url="http://agent.test/",
    interp_mode="advisory",
)
TECHNICIANS = [(7, "Priya Kim"), (8, "Priya Castillo"), (9, "Ben Okafor")]
ACCOUNTS = [
    (3, "Bluewater Energy Inc."),
    (4, "Bluewater Hospitality Partners"),
    (5, "Cedar Ridge Retail Inc."),
]


def manifest() -> Manifest:
    return Manifest.load(MANIFEST_PATH)


class FakeSource:
    """`Source` with canned answers. Each field is what the matching call returns; a field left
    None raises, so a test only provides what the code under test should read."""

    def __init__(self, **canned):
        self.canned = canned
        self.calls: list[tuple] = []

    def _get(self, name, *args):
        self.calls.append((name, *args))
        if name not in self.canned:
            raise AssertionError(f"unexpected database read: {name}")
        value = self.canned[name]
        if isinstance(value, BaseException):
            raise value
        return value(*args) if callable(value) else value

    def ping(self):
        return self._get("ping")

    def severity_counts(self, lo, hi, region, account_id, technician_id):
        return self._get("severity_counts", lo, hi, region, account_id, technician_id)

    def count_groups(self, lo, hi, group_by, region, account_id):
        return self._get("count_groups", lo, hi, group_by, region, account_id)

    def metric_counts(self, metric, lo, hi, region, account_id, technician_id):
        return self._get("metric_counts", metric, lo, hi, region, account_id, technician_id)

    def metric_groups(self, metric, lo, hi, group_by, region, account_id):
        return self._get("metric_groups", metric, lo, hi, group_by, region, account_id)

    def repeat_jobs(self, lo, hi):
        return self._get("repeat_jobs", lo, hi)

    def technicians(self):
        return self.canned.get("technicians", TECHNICIANS)

    def accounts(self):
        return self.canned.get("accounts", ACCOUNTS)

    def weekly_counts(self, slice_, first_week, last_week):
        return self._get("weekly_counts", slice_, first_week, last_week)


def row(label, numerator, denominator=0, group_id=None, key=None):
    return GroupRow(key or label, label, group_id, numerator, denominator)


class FakeLLM:
    """`LLMClient.generate` stand-in answering with a fixed judgement, or raising."""

    def __init__(self, judgement: Judgement | None = None, error: Exception | None = None):
        self.judgement = judgement or Judgement(faithful=True)
        self.error = error
        self.prompts: list[str] = []

    async def generate(self, prompt, *, model=None, response_model=None, trace_id):
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        assert response_model is Judgement
        add_cost(0.0001)  # as `LLMClient` adds each call's list-price cost to the request
        return LLMResult(
            text=self.judgement.model_dump_json(),
            parsed=self.judgement,
            model="gemini-3.5-flash-lite",
            input_tokens=700,
            output_tokens=30,
            cost_usd=0.0001,
            latency_s=0.1,
            attempts=1,
        )
