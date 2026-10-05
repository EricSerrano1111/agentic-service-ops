"""Offline tests for the sentiment agent (ADR-068). Assembled, not observed.

The A2A flow runs through the real SDK client and server in-process, as in
`agent_reporting`'s tests. The LLM is a fake with the `LLMClient.generate` signature,
and the MCP calls are replaced. The live hops are covered by the integration and e2e
runs.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from decimal import ROUND_HALF_UP, Decimal

import httpx
import pytest
from a2a.client import ClientConfig, create_client
from a2a.types import Message, Part, Role, SendMessageRequest, TaskState
from a2a.utils.constants import AGENT_CARD_WELL_KNOWN_PATH
from agent_sentiment import executor as executor_mod
from agent_sentiment.app import create_app
from agent_sentiment.card import SKILL_ID, build_agent_card
from agent_sentiment.config import Settings
from agent_sentiment.mcp_client import McpToolError
from agent_sentiment.parsing import previous_month, resolve, trend_default
from agent_sentiment.render import coverage_line, decline_message, render_answer
from agent_sentiment.trend import negative_trend, two_proportion_z
from fastapi.testclient import TestClient
from google.protobuf.json_format import MessageToDict
from llm import LLMOutputInvalid, LLMRateLimited, LLMResult
from pydantic import ValidationError
from schemas import (
    BucketCounts,
    FeedbackExample,
    FeedbackExamples,
    LabelCounts,
    LabelShares,
    SentimentAnswer,
    SentimentRequest,
    SentimentSummary,
    rate_string,
)

BASE = "http://agent.test"
AS_OF = dt.date(2026, 8, 30)
SETTINGS = Settings(public_url=f"{BASE}/")
JULY = (dt.date(2026, 7, 1), dt.date(2026, 7, 31))
VERSION = "0fa27f" + "0" * 58


@pytest.fixture
def anyio_backend():
    return "asyncio"


# --------------------------------------------------------------------------- builders


def bucket(name: str, n: int, negative: int, flagged: int = 0) -> BucketCounts:
    """A bucket of `n` comments: `negative` negative, the rest positive."""
    return BucketCounts(
        bucket=name,
        n_scored=n,
        counts=LabelCounts(positive=n - negative, neutral=0, negative=negative, mixed=0),
        flagged_count=flagged,
    )


def summary(
    buckets: list[BucketCounts],
    start=JULY[0],
    end=JULY[1],
    region=None,
    n_comments=None,
    bucket_kind="month",
) -> SentimentSummary:
    totals = {k: sum(getattr(b.counts, k) for b in buckets) for k in LabelCounts.model_fields}
    n = sum(b.n_scored for b in buckets)
    return SentimentSummary(
        model_version=VERSION,
        n_comments=n if n_comments is None else n_comments,
        n_scored=n,
        complete=n_comments is None or n_comments == n,
        start=start,
        end=end,
        region=region,
        bucket=bucket_kind,
        counts=LabelCounts(**totals),
        shares=LabelShares(**{k: rate_string(v, n) for k, v in totals.items()}),
        flagged_count=sum(b.flagged_count for b in buckets),
        buckets=buckets,
    )


def example(fid: int, text: str, label="negative", conf="0.9952") -> FeedbackExample:
    return FeedbackExample(
        feedback_id=fid,
        submitted_at=dt.datetime(2026, 7, 3, 14, 5, tzinfo=dt.UTC),
        region="west",
        label=label,
        confidence=conf,
        flagged=False,
        feedback_text=text,
    )


def answer(request: SentimentRequest, s: SentimentSummary, examples=(), as_of=AS_OF):
    resolved = resolve(request, as_of)
    return SentimentAnswer(
        request=request,
        start=resolved.start,
        end=resolved.end,
        range_assumed=resolved.assumed,
        as_of=as_of,
        summary=s,
        trend=negative_trend(s) if request.want_trend else None,
        examples=list(examples),
        quoted_feedback_ids=[e.feedback_id for e in examples],
    )


# --------------------------------------------------------------------------- schema


def test_request_defaults_and_vocabularies():
    r = SentimentRequest()
    assert (r.start, r.region, r.bucket, r.want_trend, r.want_examples) == (
        None,
        None,
        "month",
        False,
        False,
    )
    for bad in (
        {"region": "atlantis"},
        {"bucket": "week"},
        {"example_label": "angry"},
        {"unsupported": "state"},
        {"start": "2026-07-01"},
        {"start": "2026-07-31", "end": "2026-07-01"},
        {"surprise": True},
    ):
        with pytest.raises(ValidationError):
            SentimentRequest(**bad)


def test_answer_rejects_inconsistent_parts():
    s = summary([bucket("2026-07", 40, 4)])
    good = answer(SentimentRequest(start=JULY[0], end=JULY[1]), s)
    with pytest.raises(ValidationError, match="quoted_feedback_ids"):
        good.model_copy(update={"quoted_feedback_ids": [1]}).model_validate(
            good.model_dump() | {"quoted_feedback_ids": [1]}
        )
    with pytest.raises(ValidationError, match="unsupported request"):
        SentimentAnswer.model_validate(
            good.model_dump() | {"request": {"unsupported": "account", **_dates()}}
        )
    with pytest.raises(ValidationError, match="trend is present"):
        SentimentAnswer.model_validate(
            good.model_dump() | {"request": {"want_trend": True, **_dates()}}
        )


def _dates() -> dict:
    return {"start": JULY[0], "end": JULY[1]}


# --------------------------------------------------------------------------- dates


def test_dateless_trend_defaults_to_six_months_monthly():
    r = resolve(SentimentRequest(want_trend=True, bucket="quarter"), AS_OF)
    assert (r.start, r.end, r.bucket, r.assumed) == (
        dt.date(2026, 3, 1),
        AS_OF,
        "month",
        True,
    )
    assert trend_default(dt.date(2026, 2, 10)) == (dt.date(2025, 9, 1), dt.date(2026, 2, 10))


def test_dateless_summary_defaults_to_the_previous_month():
    r = resolve(SentimentRequest(), AS_OF)
    assert (r.start, r.end, r.assumed) == (*JULY, True)
    assert previous_month(dt.date(2026, 1, 15)) == (dt.date(2025, 12, 1), dt.date(2025, 12, 31))


def test_stated_dates_are_kept():
    r = resolve(SentimentRequest(start=JULY[0], end=JULY[1], want_trend=True), AS_OF)
    assert (r.start, r.end, r.assumed) == (*JULY, False)


# --------------------------------------------------------------------------- the trend rule
# Expected z and p are hand-computed (pooled two-proportion z-test, two-sided p = erfc(|z|/√2)):
#   rose:  15/50 vs 10/100: pooled 25/150, se = √(1/6·5/6·0.03) = 0.06455, z = 0.2/0.06455
#          = 3.0984, p = 0.0019
#   fell:   5/50 vs 30/100: pooled 35/150, se = 0.07326, z = -0.2/0.07326 = -2.7301, p = 0.0063
#   ns:     8/50 vs 12/100: pooled 20/150, se = 0.05888, z = 0.04/0.05888 = 0.6794, p = 0.4969
#   small: 10/19 vs  5/100: z = 5.7343, p < 0.0001, but 19 < 20: no clear change


def _trend(latest: tuple[int, int], earlier: list[tuple[int, int]]):
    buckets = [bucket(f"2026-0{i + 1}", n, x) for i, (n, x) in enumerate([*earlier, latest])]
    return negative_trend(summary(buckets))


def test_trend_rose():
    t = _trend((50, 15), [(50, 5), (50, 5)])
    assert (t.verdict, t.z, t.p_value, t.small_sample) == ("rose", 3.0984, 0.0019, False)
    assert (t.latest_bucket, t.latest_n, t.latest_negative) == ("2026-03", 50, 15)
    assert (t.earlier_buckets, t.earlier_n, t.earlier_negative) == (["2026-01", "2026-02"], 100, 10)


def test_trend_fell():
    t = _trend((50, 5), [(50, 15), (50, 15)])
    assert (t.verdict, t.z, t.p_value) == ("fell", -2.7301, 0.0063)


def test_trend_not_significant():
    t = _trend((50, 8), [(50, 6), (50, 6)])
    assert (t.verdict, t.z, t.p_value) == ("no clear change", 0.6794, 0.4969)


def test_trend_small_sample_is_no_clear_change_however_large_the_gap():
    t = _trend((19, 10), [(50, 2), (50, 3)])
    assert (t.verdict, t.small_sample, t.z) == ("no clear change", True, 5.7343)
    assert t.p_value < 0.05
    earlier_small = _trend((50, 25), [(19, 0)])
    assert (earlier_small.verdict, earlier_small.small_sample) == ("no clear change", True)


def test_trend_needs_two_periods():
    t = negative_trend(summary([bucket("2026-07", 40, 4)]))
    assert t.verdict == "needs two periods" and t.latest_n is None


def test_z_test_with_no_variation():
    assert two_proportion_z(0, 30, 0, 40) == (0.0, 1.0)


# --------------------------------------------------------------------------- rendering


def test_every_answer_states_range_as_of_counts_shares_and_flags():
    s = summary([bucket("2026-07", 40, 4, flagged=2)], region="west")
    text = render_answer(answer(SentimentRequest(start=JULY[0], end=JULY[1], region="west"), s))
    assert "in the West from 2026-07-01 to 2026-07-31 (inclusive, UTC), as of 2026-08-30" in text
    assert "40 comments: positive 36 (90.0%), neutral 0 (0.0%), negative 4 (10.0%)" in text
    assert "2 comments (5.0%) are low-confidence and flagged for review." in text


def test_coverage_line_appears_if_and_only_if_incomplete():
    req = SentimentRequest(start=JULY[0], end=JULY[1])
    complete = render_answer(answer(req, summary([bucket("2026-07", 40, 4)])))
    partial = render_answer(answer(req, summary([bucket("2026-07", 40, 4)], n_comments=300)))
    line = coverage_line(40, 300)
    assert line not in complete and "Based on" not in complete
    assert partial.splitlines()[0] == line
    assert line == (
        "Based on 40 of 300 comments in this range; the rest are still being scored, "
        "so the oldest period may be under-represented."
    )


def test_assumed_range_is_stated():
    text = render_answer(answer(SentimentRequest(), summary([bucket("2026-07", 40, 4)])))
    assert "no period was named, so this range was assumed" in text


@pytest.mark.parametrize(
    ("latest", "earlier", "phrase"),
    [
        ((50, 15), [(50, 5), (50, 5)], "Trend: the negative share rose."),
        ((50, 5), [(50, 15), (50, 15)], "Trend: the negative share fell."),
        ((50, 8), [(50, 6), (50, 6)], "Trend: no clear change in the negative share."),
    ],
)
def test_trend_text_shows_both_shares_and_counts(latest, earlier, phrase):
    buckets = [bucket(f"2026-0{i + 1}", n, x) for i, (n, x) in enumerate([*earlier, latest])]
    s = summary(buckets, start=dt.date(2026, 1, 1), end=dt.date(2026, 3, 31))
    req = SentimentRequest(start=dt.date(2026, 1, 1), end=dt.date(2026, 3, 31), want_trend=True)
    text = render_answer(answer(req, s))
    assert phrase in text
    n1, x1 = latest
    n2, x2 = sum(n for n, _ in earlier), sum(x for _, x in earlier)
    assert f"{x1} of {n1} negative ({100 * x1 / n1:.1f}%)" in text
    assert f"{x2} of {n2} negative ({100 * x2 / n2:.1f}%)" in text


def test_small_sample_and_single_bucket_texts():
    req = SentimentRequest(start=JULY[0], end=JULY[1], want_trend=True)
    one = render_answer(answer(req, summary([bucket("2026-07", 40, 4)])))
    assert "A trend needs at least two periods" in one
    small = summary([bucket("2026-06", 50, 2), bucket("2026-07", 19, 10)])
    req2 = SentimentRequest(start=dt.date(2026, 6, 1), end=JULY[1], want_trend=True)
    small_answer = answer(req2, small.model_copy(update={"start": dt.date(2026, 6, 1)}))
    text = render_answer(small_answer)
    assert "no clear change" in text and "at least 20 comments" in text


def test_examples_are_quoted_verbatim_with_label_and_confidence():
    quoted = [example(5531, 'Showed up "three days" late.'), example(5062, "Lost a day.")]
    req = SentimentRequest(start=JULY[0], end=JULY[1], want_examples=True, example_label="negative")
    text = render_answer(answer(req, summary([bucket("2026-07", 40, 4)]), quoted))
    assert "Example negative comments, quoted as written:" in text
    assert '- [negative, confidence 0.9952] "Showed up "three days" late." (feedback 5531' in text
    assert "Lost a day." in text


@pytest.mark.parametrize("dimension", ["account", "technician", "service_type", "other"])
def test_every_unsupported_value_has_a_decline_naming_what_is_supported(dimension):
    text = decline_message(dimension)
    assert "can't be broken down" in text or "isn't supported" in text
    assert "date range" in text and "region" in text and "example comments" in text


def _numbers_in(text: str) -> set[str]:
    return set(re.findall(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?", text))


def _numbers_from_data(data) -> set[str]:
    """Every number the template may print: each data field, raw and as a percentage."""
    out: set[str] = set()

    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, bool) or v is None:
            return
        elif isinstance(v, int):
            out.update({str(v), f"{v:,}"})
        elif isinstance(v, float):
            out.add(f"{v:.4f}")
        elif isinstance(v, str):
            out.update(_numbers_in(v))
            if re.fullmatch(r"\d+\.\d{4}", v):
                pct = (Decimal(v) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
                out.add(str(pct))

    walk(data)
    t = data.get("trend") or {}
    s = data["summary"]
    pairs = [(s["flagged_count"], s["n_scored"])]
    if t.get("latest_n"):
        pairs += [(t["latest_negative"], t["latest_n"]), (t["earlier_negative"], t["earlier_n"])]
    for x, n in pairs:
        if n:
            out.add(str((Decimal(rate_string(x, n)) * 100).quantize(Decimal("0.1"), ROUND_HALF_UP)))
    for e in data["examples"]:
        out.update(_numbers_in(e["submitted_at"][:10]))
    return out


@pytest.mark.parametrize("partial", [False, True])
def test_template_text_carries_nothing_that_is_not_in_the_data_part(partial):
    """Every number and every quoted comment in the text is in the data part."""
    buckets = [bucket("2026-05", 48, 4, 1), bucket("2026-06", 51, 6), bucket("2026-07", 44, 9, 2)]
    s = summary(
        buckets,
        start=dt.date(2026, 5, 1),
        region="west",
        n_comments=400 if partial else None,
    )
    req = SentimentRequest(
        start=dt.date(2026, 5, 1),
        end=JULY[1],
        region="west",
        want_trend=True,
        want_examples=True,
        example_label="negative",
    )
    quoted = [example(5531, "Showed up three days late for the 2 switch upgrades.")]
    a = answer(req, s, quoted)
    text = render_answer(a)
    data = a.model_dump(mode="json")
    assert _numbers_in(text) - _numbers_from_data(data) == set()
    for line in text.splitlines():
        if line.startswith("- ["):
            quoted_text = line.split('"', 1)[1].rsplit('"', 1)[0]
            assert quoted_text in [e["feedback_text"] for e in data["examples"]]


# --------------------------------------------------------------------------- Agent Card


def test_card_advertises_one_skill_and_the_minimal_subset():
    card = build_agent_card(SETTINGS.public_url)
    assert [s.id for s in card.skills] == [SKILL_ID]
    assert card.capabilities.streaming is False
    assert card.capabilities.push_notifications is False
    [interface] = card.supported_interfaces
    assert (interface.protocol_binding, interface.protocol_version) == ("JSONRPC", "1.0")


def test_card_served_at_well_known_path():
    assert AGENT_CARD_WELL_KNOWN_PATH == "/.well-known/agent-card.json"
    with TestClient(create_app(SETTINGS, FakeLLM())) as client:
        body = client.get(AGENT_CARD_WELL_KNOWN_PATH).json()
        assert client.get("/healthz").json()["service"] == "agent_sentiment"
    assert [s["id"] for s in body["skills"]] == [SKILL_ID]


# --------------------------------------------------------------------------- A2A task flow


class FakeLLM:
    """`LLMClient.generate` stand-in: returns `parsed`, or raises `error`."""

    def __init__(self, parsed: SentimentRequest | None = None, error: Exception | None = None):
        self.parsed, self.error = parsed, error
        self.prompts: list[str] = []

    async def generate(self, prompt, *, model=None, response_model=None, trace_id):
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        assert response_model is SentimentRequest
        return LLMResult(
            text=self.parsed.model_dump_json(),
            parsed=self.parsed,
            model="gemini-3.5-flash-lite",
            input_tokens=400,
            output_tokens=40,
            cost_usd=0.0001,
            latency_s=0.1,
            attempts=1,
        )


QUOTED = [example(5531, "Showed up three days late."), example(5062, "Lost a day.")]


@pytest.fixture
def mcp_calls(monkeypatch):
    """Replace the MCP calls; record them; answer with fixed figures."""
    calls: list[dict] = []

    async def fake(url, tool, arguments, result_model, *, trace_id, timeout_s):
        calls.append({"tool": tool, **arguments, "trace_id": trace_id})
        start = dt.date.fromisoformat(arguments["start"])
        end = dt.date.fromisoformat(arguments["end"])
        if tool == "get_sentiment_summary":
            return summary(
                [bucket("2026-06", 45, 3), bucket("2026-07", 40, 8, 1)],
                start=start,
                end=end,
                region=arguments.get("region"),
                bucket_kind=arguments["bucket"],
            )
        return FeedbackExamples(
            model_version=VERSION,
            n_comments=85,
            n_scored=85,
            complete=True,
            start=start,
            end=end,
            region=arguments.get("region"),
            label=arguments.get("label"),
            flagged_only=False,
            examples=QUOTED[: arguments["limit"]],
        )

    monkeypatch.setattr(executor_mod, "call_tool", fake)
    return calls


async def _send(app, text: str = "Is sentiment trending down in the West?", trace_id="t-1"):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE) as http:
        client = await create_client(
            BASE, client_config=ClientConfig(streaming=False, httpx_client=http)
        )
        message = Message(
            message_id=uuid.uuid4().hex,
            role=Role.ROLE_USER,
            parts=[Part(text=text)],
            metadata={"trace_id": trace_id},
        )
        async for event in client.send_message(SendMessageRequest(message=message)):
            return event.task
    raise AssertionError("no response")


def _failure(task) -> tuple[str, str]:
    message = task.status.message
    return MessageToDict(message.metadata).get("error_code"), message.parts[0].text


@pytest.mark.anyio
async def test_trend_question_calls_the_summary_only_and_answers_from_templates(mcp_calls):
    llm = FakeLLM(SentimentRequest(region="west", want_trend=True))
    task = await _send(create_app(SETTINGS, llm), trace_id="trace-xyz")

    assert task.status.state == TaskState.TASK_STATE_COMPLETED
    assert mcp_calls == [
        {
            "tool": "get_sentiment_summary",
            "start": "2026-03-01",
            "end": "2026-08-30",
            "bucket": "month",
            "region": "west",
            "trace_id": "trace-xyz",
        }
    ]
    [artifact] = task.artifacts
    text, data = artifact.parts
    a = SentimentAnswer.model_validate(MessageToDict(data.data))
    assert a.range_assumed and a.trend is not None and a.examples == []
    assert text.text == render_answer(a)


@pytest.mark.anyio
async def test_examples_are_requested_with_limit_3_and_never_reach_the_llm(mcp_calls):
    req = SentimentRequest(start=JULY[0], end=JULY[1], want_examples=True, example_label="negative")
    llm = FakeLLM(req)
    task = await _send(create_app(SETTINGS, llm), text="show me negative comments from July")

    assert [c["tool"] for c in mcp_calls] == ["get_sentiment_summary", "get_feedback_examples"]
    assert mcp_calls[1] | {"trace_id": None} == {
        "tool": "get_feedback_examples",
        "start": "2026-07-01",
        "end": "2026-07-31",
        "limit": 3,
        "label": "negative",
        "trace_id": None,
    }
    [artifact] = task.artifacts
    text, data = artifact.parts
    a = SentimentAnswer.model_validate(MessageToDict(data.data))
    assert a.quoted_feedback_ids == [5531, 5062]
    assert "Showed up three days late." in text.text
    # The one LLM call saw the question only: no comment text in any prompt.
    [prompt] = llm.prompts
    assert "show me negative comments from July" in prompt
    assert all(e.feedback_text not in prompt for e in QUOTED)


@pytest.mark.anyio
@pytest.mark.parametrize("dimension", ["account", "technician", "service_type", "other"])
async def test_unsupported_is_declined_without_any_mcp_call(mcp_calls, dimension):
    task = await _send(create_app(SETTINGS, FakeLLM(SentimentRequest(unsupported=dimension))))
    assert task.status.state == TaskState.TASK_STATE_FAILED
    code, text = _failure(task)
    assert (code, text) == ("not_supported", decline_message(dimension))
    assert mcp_calls == []
    assert not task.artifacts


@pytest.mark.anyio
async def test_parse_failures_end_in_coded_failed_tasks(mcp_calls):
    bad = await _send(create_app(SETTINGS, FakeLLM(error=LLMOutputInvalid("x", raw_text="{}"))))
    limited = await _send(create_app(SETTINGS, FakeLLM(error=LLMRateLimited("x"))))
    assert _failure(bad)[0] == "unclear_question"
    assert _failure(limited)[0] == "rate_limited"
    assert mcp_calls == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error", "code"),
    [
        (TimeoutError(), "tool_timeout"),
        (McpToolError("Error executing tool: feedback query failed"), "tool_error"),
        (McpToolError("range is outside the dataset window"), "invalid_range"),
        (ConnectionError("refused"), "tool_unavailable"),
    ],
)
async def test_mcp_failures_end_in_coded_failed_tasks(monkeypatch, error, code):
    async def fails(*args, **kwargs):
        raise error

    monkeypatch.setattr(executor_mod, "call_tool", fails)
    task = await _send(create_app(SETTINGS, FakeLLM(SentimentRequest(start=JULY[0], end=JULY[1]))))
    assert task.status.state == TaskState.TASK_STATE_FAILED
    assert _failure(task)[0] == code
    assert not task.artifacts


@pytest.mark.anyio
async def test_as_of_date_and_question_reach_the_parsing_prompt(mcp_calls):
    llm = FakeLLM(SentimentRequest(start=JULY[0], end=JULY[1]))
    await _send(create_app(SETTINGS, llm), text="How did customers feel in July?")
    [prompt] = llm.prompts
    assert "2026-08-30" in prompt and "How did customers feel in July?" in prompt
    assert "time and by the customer site's region only" in prompt


def test_mcp_client_raises_on_a_tool_error():
    """The MCP client is agent_reporting's, unchanged: a tool error becomes McpToolError."""
    import inspect

    from agent_reporting import mcp_client as reporting_client
    from agent_sentiment import mcp_client as sentiment_client

    body = inspect.getsource(sentiment_client).split("\n", 1)[1]
    assert body == inspect.getsource(reporting_client).split("\n", 1)[1]


def test_prompt_json_template_keys_follow_the_schema_property_order():
    """Gemini's structured output writes keys in the schema's property order. If the
    prompt's template orders them differently, the model can write a later key first and
    then has no way back to the ones it skipped (L-51, found in the reporting agent)."""
    import re

    from agent_sentiment.parsing import load_parse_prompt

    template = next(line for line in load_parse_prompt().text.splitlines() if line.startswith('{"'))
    keys = re.findall(r'"(\w+)":', template)
    assert keys == list(SentimentRequest.model_json_schema()["properties"])


#: Questions that look like template syntax. The question is data: it renders without
#: error and reaches the model client unchanged (security-model.md, section 3).
TEMPLATE_SYNTAX_QUESTIONS = [
    "what is {{x}}?",
    "show {0} incidents",
    "odd }}{{ braces",
    "{{as_of}} and {{question}} and {1} and {name}",
]


@pytest.mark.anyio
@pytest.mark.parametrize("question", TEMPLATE_SYNTAX_QUESTIONS)
async def test_parse_sends_template_syntax_in_a_question_unchanged(question):
    from agent_sentiment.parsing import Parser

    llm = FakeLLM(SentimentRequest())
    await Parser(llm, AS_OF).parse_request(question, trace_id="t-syntax")
    [prompt] = llm.prompts
    assert f"<question>\n{question}\n</question>" in prompt
    assert prompt.count(question) == 1
