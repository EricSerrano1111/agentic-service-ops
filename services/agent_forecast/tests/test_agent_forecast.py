"""Offline tests for the forecast agent (ADR-072). Assembled, not observed.

The A2A flow runs through the real SDK client and server in-process, as in the other
agents' tests; the LLM is a fake and the MCP calls are replaced. Period mappings are
checked against hand-worked calendars (the first forecast week is Monday 2026-08-31).
"""

from __future__ import annotations

import datetime as dt
import re
import uuid

import httpx
import pytest
from a2a.client import ClientConfig, create_client
from a2a.types import Message, Part, Role, SendMessageRequest, TaskState
from a2a.utils.constants import AGENT_CARD_WELL_KNOWN_PATH
from agent_forecast import executor as executor_mod
from agent_forecast.app import create_app
from agent_forecast.card import SKILL_ID, build_agent_card
from agent_forecast.config import Settings
from agent_forecast.parsing import first_forecast_week, mondays, next_month, resolve
from agent_forecast.render import YEAR_END, decline_message, render_answer
from fastapi.testclient import TestClient
from google.protobuf.json_format import MessageToDict
from llm import LLMOutputInvalid, LLMResult
from pydantic import ValidationError
from schemas import (
    BandVerdict,
    ForecastAnswer,
    ForecastRequest,
    ForecastWeek,
    HistoryWeek,
    VolumeForecast,
    VolumeHistory,
    band_of,
)

BASE = "http://agent.test"
AS_OF = dt.date(2026, 8, 30)
SETTINGS = Settings(public_url=f"{BASE}/")
FIRST = dt.date(2026, 8, 31)
VERSION = "c5284000" + "0" * 56


@pytest.fixture
def anyio_backend():
    return "asyncio"


def D(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


# --------------------------------------------------------------------------- period rules


def test_first_forecast_week_is_the_monday_after_the_as_of_date():
    assert first_forecast_week(AS_OF) == FIRST
    assert first_forecast_week(dt.date(2026, 8, 31)) == dt.date(2026, 9, 7)  # a Monday as-of


def test_next_month_is_september_and_its_weeks_are_mondays_inside_it():
    """Aug 31 is a Monday in August, so September's weeks start Sep 7 (horizons 2-5)."""
    assert next_month(AS_OF) == (D("2026-09-01"), D("2026-09-30"))
    r = resolve(ForecastRequest(period_start=D("2026-09-01"), period_end=D("2026-09-30")), AS_OF)
    assert r.requested == (D("2026-09-07"), D("2026-09-14"), D("2026-09-21"), D("2026-09-28"))
    assert (r.horizons, r.beyond, r.past, r.assumed) == ((2, 3, 4, 5), 0, False, False)


def test_bare_december_maps_to_its_four_mondays():
    r = resolve(ForecastRequest(period_start=D("2026-12-01"), period_end=D("2026-12-31")), AS_OF)
    assert r.requested == (D("2026-12-07"), D("2026-12-14"), D("2026-12-21"), D("2026-12-28"))
    assert r.horizons == (15, 16, 17, 18)


def test_q1_2027_crosses_the_cap():
    """13 Mondays from Jan 4 (h 19) to Mar 29 (h 31): h 19-26 inside, 5 beyond."""
    r = resolve(ForecastRequest(period_start=D("2027-01-01"), period_end=D("2027-03-31")), AS_OF)
    assert len(r.requested) == 13 and r.requested[0] == D("2027-01-04")
    assert (r.horizons, r.beyond) == (tuple(range(19, 27)), 5)


def test_wholly_beyond_the_horizon():
    r = resolve(ForecastRequest(period_start=D("2027-04-01"), period_end=D("2027-06-30")), AS_OF)
    assert (r.horizons, r.beyond, r.past) == ((), 13, False)


def test_a_horizon_of_52_weeks_is_served_to_26():
    r = resolve(ForecastRequest(horizon_weeks=52), AS_OF)
    assert (r.horizons, r.beyond) == (tuple(range(1, 27)), 26)


def test_past_and_partly_past_periods():
    past = resolve(ForecastRequest(period_start=D("2026-07-01"), period_end=D("2026-07-31")), AS_OF)
    assert past.past and past.requested == ()
    partly = resolve(
        ForecastRequest(period_start=D("2026-08-01"), period_end=D("2026-09-30")), AS_OF
    )
    assert not partly.past and partly.requested[0] == FIRST and partly.horizons == (1, 2, 3, 4, 5)


def test_a_period_with_no_monday_has_no_week():
    r = resolve(ForecastRequest(period_start=D("2026-09-01"), period_end=D("2026-09-06")), AS_OF)
    assert (r.requested, r.past) == ((), False)
    assert mondays(D("2026-09-01"), D("2026-09-06")) == []


def test_no_period_defaults_to_next_month_and_says_so():
    r = resolve(ForecastRequest(), AS_OF)
    assert r.assumed and r.horizons == (2, 3, 4, 5)


def test_request_validation():
    for bad in (
        {"slice": "region"},
        {"horizon_weeks": 0},
        {"period_start": "2026-09-01"},
        {"period_start": "2026-09-30", "period_end": "2026-09-01"},
        {"horizon_weeks": 4, "period_start": "2026-09-01", "period_end": "2026-09-30"},
        {"unsupported": "weather"},
    ):
        with pytest.raises(ValidationError):
            ForecastRequest(**bad)


# --------------------------------------------------------------------------- fixtures


def volume_forecast(slice_: str, horizon: int, served=lambda band: True) -> VolumeForecast:
    weeks = []
    for h in range(1, horizon + 1):
        band = band_of(h)
        start = FIRST + dt.timedelta(weeks=h - 1)
        nums = {}
        if served(band):
            p = 150.0 + h
            nums = dict(point=p, lo80=p - 20.4, hi80=p + 24.6, lo95=p - 30, hi95=p + 37)
        weeks.append(
            ForecastWeek(week_start=start, horizon=h, band=band, served=served(band), **nums)
        )
    bands = {w.band for w in weeks}
    errors = {"1-4": 43.69, "5-13": 17.96, "14-26": 29.37}
    return VolumeForecast(
        model_version=VERSION,
        trained_through=AS_OF,
        slice=slice_,
        horizon_weeks=horizon,
        weeks=weeks,
        bands={
            b: BandVerdict(served=served(b), shown_error=errors[b])
            for b in ("1-4", "5-13", "14-26")
            if b in bands
        },
        year_end_weeks=[
            d
            for d in (D("2026-12-21"), D("2026-12-28"))
            if d <= FIRST + dt.timedelta(weeks=horizon - 1)
        ],
    )


def answer_for(request: ForecastRequest, served=lambda band: True, history=None) -> ForecastAnswer:
    r = resolve(request, AS_OF)
    f = volume_forecast(request.slice, max(r.horizons, default=1), served)
    return executor_mod.build_answer(r, f, history, AS_OF)


# --------------------------------------------------------------------------- templates


def test_served_weeks_show_point_range_and_band_error():
    text = render_answer(answer_for(ForecastRequest(horizon_weeks=2)))
    assert "- Week of 2026-08-31: about 151 requests (80% range 131-176)" in text
    assert "On held-out weeks at 1-4 weeks ahead, forecasts were off by 43.7% on average." in text
    assert "Total over these 2 weeks: about 303 requests, the sum of the weekly forecasts" in text
    assert "no range is given for a total" in text


def test_served_and_unserved_split_names_the_unserved_band_and_gives_no_total():
    install = lambda band: band != "1-4"  # noqa: E731
    a = answer_for(ForecastRequest(slice="install", horizon_weeks=10), install)
    text = render_answer(a)
    assert (
        "Forecasts for install requests at 1-4 weeks ahead aren't shown: they were off by 43.7%"
        in text
    )
    assert "Week of 2026-08-31" not in text and "- Week of 2026-09-28" in text
    assert "On held-out weeks at 5-13 weeks ahead, forecasts were off by 18.0% on average." in text
    assert "No total is given, because some of these weeks aren't shown." in text
    assert a.period_total is None
    assert all(w.point is None for w in a.weeks if not w.served)


def test_all_unserved_shows_no_numbers_at_all():
    a = answer_for(ForecastRequest(slice="upgrade", horizon_weeks=3), lambda band: False)
    text = render_answer(a)
    assert "- Week of" not in text and "Total" not in text and "about" not in text
    assert "aren't shown: they were off by 43.7% on held-out weeks" in text


def test_year_end_caveat_when_and_only_when_a_marked_week_is_shown():
    dec = answer_for(ForecastRequest(period_start=D("2026-12-01"), period_end=D("2026-12-31")))
    nov = answer_for(ForecastRequest(period_start=D("2026-11-01"), period_end=D("2026-11-30")))
    assert YEAR_END in render_answer(dec) and dec.year_end_weeks == [
        D("2026-12-21"),
        D("2026-12-28"),
    ]
    assert YEAR_END not in render_answer(nov) and nov.year_end_weeks == []


def test_beyond_the_horizon_partly_and_wholly():
    year = render_answer(answer_for(ForecastRequest(horizon_weeks=52)))
    assert (
        "The remaining 26 weeks fall beyond the 26-week forecast horizon and aren't forecast."
        in year
    )
    q2 = answer_for(ForecastRequest(period_start=D("2027-04-01"), period_end=D("2027-06-30")))
    text = render_answer(q2)
    assert "All requested weeks fall beyond the 26-week forecast horizon" in text
    assert q2.weeks == [] and "- Week of" not in text


def test_assumed_range_and_history_lines():
    hist = VolumeHistory(slice="total", weeks=[HistoryWeek(week_start=D("2026-08-24"), count=136)])
    a = answer_for(ForecastRequest(want_history=True), history=hist)
    text = render_answer(a)
    assert "no period was named, so next month was assumed" in text
    assert "Recent actual weekly counts (total request volume): 2026-08-24: 136." in text


@pytest.mark.parametrize(
    "unsupported",
    ["sla", "incidents", "sentiment", "region", "account", "technician", "past_period", "other"],
)
def test_every_decline_names_what_is_supported(unsupported):
    text = decline_message(unsupported, AS_OF)
    assert "I can forecast weekly request volume, in total or by service type" in text
    assert "up to 26 weeks ahead" in text


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?", text))


def _allowed(a: ForecastAnswer) -> set[str]:
    out: set[str] = {"80", "26"}  # the range's level and the horizon cap: fixed text
    for w in a.weeks:
        out |= _numbers(w.week_start.isoformat())
        for v in (w.point, w.lo80, w.hi80):
            if v is not None:
                out.add(f"{round(v):,}")
    for v in a.bands.values():
        out.add(f"{v.shown_error:.1f}")
    if a.period_total is not None:
        out.add(f"{round(a.period_total):,}")
    for d in (
        a.as_of,
        a.trained_through,
        a.requested_first_week,
        a.requested_last_week + dt.timedelta(days=6),
    ):
        out |= _numbers(d.isoformat())
    out |= {
        str(len(a.weeks) + a.beyond_horizon_weeks),
        str(len(a.weeks)),
        str(a.beyond_horizon_weeks),
    }
    for h in a.history:
        out |= _numbers(h.week_start.isoformat()) | {f"{h.count:,}"}
    out |= {"1", "4", "5", "13", "14"}  # band names
    return out


@pytest.mark.parametrize(
    "request_",
    [
        ForecastRequest(slice="install", horizon_weeks=10),
        ForecastRequest(
            period_start=D("2026-12-01"), period_end=D("2026-12-31"), want_history=True
        ),
        ForecastRequest(horizon_weeks=52),
    ],
)
def test_the_text_carries_no_number_that_is_not_in_the_data_part(request_):
    served = (lambda band: band != "1-4") if request_.slice == "install" else (lambda band: True)
    hist = VolumeHistory(slice="total", weeks=[HistoryWeek(week_start=D("2026-08-24"), count=136)])
    a = answer_for(request_, served, hist if request_.want_history else None)
    assert _numbers(render_answer(a)) - _allowed(a) == set()


# --------------------------------------------------------------------------- A2A


class FakeLLM:
    def __init__(self, parsed: ForecastRequest | None = None, error: Exception | None = None):
        self.parsed, self.error = parsed, error
        self.prompts: list[str] = []

    async def generate(self, prompt, *, model=None, response_model=None, trace_id):
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        assert response_model is ForecastRequest
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


@pytest.fixture
def mcp_calls(monkeypatch):
    calls: list[dict] = []

    async def fake(url, tool, arguments, result_model, *, trace_id, timeout_s):
        calls.append({"tool": tool, **arguments})
        if tool == "get_volume_forecast":
            served = (
                (lambda band: band != "1-4")
                if arguments["slice"] == "install"
                else (lambda band: True)
            )
            return volume_forecast(arguments["slice"], arguments["horizon_weeks"], served)
        return VolumeHistory(
            slice=arguments["slice"],
            weeks=[HistoryWeek(week_start=D("2026-08-24"), count=136)],
        )

    monkeypatch.setattr(executor_mod, "call_tool", fake)
    return calls


async def _send(app, text="Forecast install requests for the next 10 weeks."):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE) as http:
        client = await create_client(
            BASE, client_config=ClientConfig(streaming=False, httpx_client=http)
        )
        message = Message(message_id=uuid.uuid4().hex, role=Role.ROLE_USER, parts=[Part(text=text)])
        async for event in client.send_message(SendMessageRequest(message=message)):
            return event.task
    raise AssertionError("no response")


def _failure(task):
    m = task.status.message
    return MessageToDict(m.metadata).get("error_code"), m.parts[0].text


@pytest.mark.anyio
async def test_a_forecast_question_calls_the_tool_with_the_horizon_needed(mcp_calls):
    task = await _send(
        create_app(SETTINGS, FakeLLM(ForecastRequest(slice="install", horizon_weeks=10)))
    )
    assert task.status.state == TaskState.TASK_STATE_COMPLETED
    assert mcp_calls == [{"tool": "get_volume_forecast", "slice": "install", "horizon_weeks": 10}]
    text, data = task.artifacts[0].parts
    a = ForecastAnswer.model_validate(MessageToDict(data.data))
    assert [w.served for w in a.weeks] == [False] * 4 + [True] * 6
    assert text.text == render_answer(a)


@pytest.mark.anyio
async def test_december_asks_for_18_weeks_and_keeps_its_four(mcp_calls):
    req = ForecastRequest(
        period_start=D("2026-12-01"), period_end=D("2026-12-31"), want_history=True
    )
    task = await _send(create_app(SETTINGS, FakeLLM(req)), "How busy will December be?")
    assert [c["tool"] for c in mcp_calls] == ["get_volume_forecast", "get_order_volume_history"]
    assert mcp_calls[0]["horizon_weeks"] == 18 and mcp_calls[1]["weeks"] == 8
    a = ForecastAnswer.model_validate(MessageToDict(task.artifacts[0].parts[1].data))
    assert [w.horizon for w in a.weeks] == [15, 16, 17, 18] and a.period_total is not None


@pytest.mark.anyio
@pytest.mark.parametrize(
    "request_",
    [
        ForecastRequest(
            unsupported="sla", period_start=D("2026-10-01"), period_end=D("2026-12-31")
        ),
        ForecastRequest(period_start=D("2026-07-01"), period_end=D("2026-07-31")),  # past
        ForecastRequest(period_start=D("2026-09-01"), period_end=D("2026-09-06")),  # no Monday
    ],
)
async def test_declines_make_no_mcp_call(mcp_calls, request_):
    task = await _send(create_app(SETTINGS, FakeLLM(request_)))
    assert task.status.state == TaskState.TASK_STATE_FAILED
    code, text = _failure(task)
    assert code == "not_supported" and "I can forecast weekly request volume" in text
    assert mcp_calls == []


@pytest.mark.anyio
async def test_parse_failure_is_a_coded_failed_task(mcp_calls):
    task = await _send(create_app(SETTINGS, FakeLLM(error=LLMOutputInvalid("x", raw_text="{}"))))
    assert _failure(task)[0] == "unclear_question" and mcp_calls == []


@pytest.mark.anyio
async def test_prompt_states_the_as_of_date_and_first_week(mcp_calls):
    llm = FakeLLM(ForecastRequest(horizon_weeks=4))
    await _send(create_app(SETTINGS, llm), "next 4 weeks?")
    [prompt] = llm.prompts
    assert "2026-08-30" in prompt and "2026-08-31" in prompt and "next 4 weeks?" in prompt


def test_card_served_at_well_known_path():
    card = build_agent_card(SETTINGS.public_url)
    assert [s.id for s in card.skills] == [SKILL_ID] and card.capabilities.streaming is False
    with TestClient(create_app(SETTINGS, FakeLLM())) as client:
        body = client.get(AGENT_CARD_WELL_KNOWN_PATH).json()
        assert client.get("/healthz").json()["service"] == "agent_forecast"
    assert [s["id"] for s in body["skills"]] == [SKILL_ID]


def test_mcp_client_is_the_shared_one():
    import inspect

    from agent_forecast import mcp_client as forecast_client
    from agent_sentiment import mcp_client as sentiment_client

    assert (
        inspect.getsource(forecast_client).split("\n", 1)[1]
        == inspect.getsource(sentiment_client).split("\n", 1)[1]
    )


def test_prompt_json_template_keys_follow_the_schema_property_order():
    """Gemini's structured output writes keys in the schema's property order. If the
    prompt's template orders them differently, the model can write a later key first and
    then has no way back to the ones it skipped (L-51, found in the reporting agent)."""
    import re

    from agent_forecast.parsing import load_parse_prompt

    template = next(line for line in load_parse_prompt().text.splitlines() if line.startswith('{"'))
    keys = re.findall(r'"(\w+)":', template)
    assert keys == list(ForecastRequest.model_json_schema()["properties"])
