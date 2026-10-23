"""What the UI shows for one answer: the "Interpreted as:" line, the `qa_status` wording and the
headline figure.

The rules are data dictionary §6, "Answer display (UI)". The gateway builds these strings so the
UI computes nothing and the rules are tested in CI. Free text from the question (an account or
technician name) is passed as typed; the UI renders it as text.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

SEP = " · "
ASSUMED = " (assumed: the question named no dates)"

QA_WORDS = {
    "verified": (
        "Figures checked for the request as interpreted. "
        "Check that the “Interpreted as” line matches your question."
    ),
    "failed": "Not verified: the answer failed verification and is not shown.",
    "unavailable": "Not verified: the checking service was unavailable.",
    "not_checked": "Not checked: the request ended before verification ran.",
}

#: Outcomes whose response carries no figures: a clarification of any `reason` and a specialist's
#: decline (`not_available`). A "figures checked" line on these claims a check with nothing to
#: check (L-99, data dictionary section 6, rule 3).
NO_FIGURES_OUTCOMES = ("needs_clarification", "not_available")

METRICS = {
    "incident_count": "incident count",
    "incident_rate": "incident rate",
    "sla_compliance": "SLA compliance",
    "first_time_fix_rate": "first-time fix rate",
    "repeat_visit_drivers": "repeat-visit drivers",
    "unsupported": "measure not recognised",
}
DOMAINS = ("reporting", "sentiment", "forecast")

#: Metrics that get a headline figure (data dictionary §6, rule 8), each with the denominator
#: noun the reporting renderer prints; None for a count, which has no denominator. Incident rate
#: is left out on purpose: its printed value reads ambiguously without the sentence around it.
HEADLINE_NOUNS: dict[str, str | None] = {
    "incident_count": None,
    "sla_compliance": "dispatched request",
    "first_time_fix_rate": "completed request",
}


def qa_text(qa_status: str, outcome: str | None = None) -> str | None:
    """The user-facing words for a `qa_status`; None (no line) for `not_applicable` and for an
    outcome that carries no figures."""
    if outcome in NO_FIGURES_OUTCOMES:
        return None
    return QA_WORDS.get(qa_status)


def _words(value: Any) -> str:
    return str(value).replace("_", " ")


def _range(start: Any, end: Any, assumed: bool) -> str | None:
    if not start or not end:
        return None
    return f"Period: {start} to {end}" + (ASSUMED if assumed else "")


def _region(value: Any) -> str:
    if value == "unsupported":
        return "Region: not recognised"
    return f"Region: {str(value).capitalize()}" if value else "Region: all regions"


def _person(request: dict) -> list[str]:
    out = []
    if request.get("account_name"):
        out.append(f"Account: {request['account_name']}")
    if request.get("technician_name"):
        out.append(f"Technician: {request['technician_name']}")
    return out


def _period(payload: dict | None, request: dict) -> str | None:
    if payload:
        return _range(payload.get("start"), payload.get("end"), bool(payload.get("range_assumed")))
    return _range(request.get("start"), request.get("end"), False)


def _reporting(payload: dict | None, request: dict) -> list[str]:
    metric = request.get("metric")
    measure = METRICS.get(metric, "not recognised") if metric else None
    parts = [
        "Area: incident reporting",
        f"Measure: {measure}" if measure else None,
        _period(payload, request),
        _region(request.get("region")),
        *_person(request),
        f"Breakdown: {_words(request['group_by'])}" if request.get("group_by") else None,
    ]
    return [p for p in parts if p]


def _sentiment(payload: dict | None, request: dict) -> list[str]:
    measure = "sentiment summary"
    if request.get("want_trend"):
        measure = "sentiment trend"
    if request.get("want_examples"):
        label = request.get("example_label")
        measure = "sentiment with example comments" + (f" ({label})" if label else "")
    parts = [
        "Area: customer sentiment",
        f"Measure: {measure}",
        _period(payload, request),
        _region(request.get("region")),
        f"Breakdown: {request['bucket']}" if request.get("bucket") else None,
        f"Not supported: {_words(request['unsupported'])}" if request.get("unsupported") else None,
    ]
    return [p for p in parts if p]


def _forecast(payload: dict | None, request: dict) -> list[str]:
    slice_ = request.get("slice") or "total"
    period = None
    if payload and payload.get("requested_first_week") and payload.get("requested_last_week"):
        period = (
            f"Period: weeks starting {payload['requested_first_week']} to "
            f"{payload['requested_last_week']}"
        ) + (ASSUMED if payload.get("range_assumed") else "")
    elif request.get("period_start") and request.get("period_end"):
        period = f"Period: {request['period_start']} to {request['period_end']}"
    parts = [
        "Area: volume forecast",
        "Measure: weekly service request volume",
        f"Slice: {'all service types' if slice_ == 'total' else slice_}",
        period,
        f"Horizon: next {request['horizon_weeks']} weeks" if request.get("horizon_weeks") else None,
        "History: included" if request.get("want_history") else None,
        f"Not supported: {_words(request['unsupported'])}" if request.get("unsupported") else None,
    ]
    return [p for p in parts if p]


def interpreted_as(body: dict) -> str | None:
    """The one-line reading of the question, or None when the response carries no parsed
    request (a split, out-of-scope or ambiguous question, or no specialist ran)."""
    domain = (body.get("route") or {}).get("route")
    if domain not in DOMAINS:
        return None
    payload = body.get(domain)
    request = payload.get("request") if isinstance(payload, dict) else None
    if request is None:
        request = body.get("parsed_request")
        payload = None
    if not isinstance(request, dict):
        return None
    build = {"reporting": _reporting, "sentiment": _sentiment, "forecast": _forecast}[domain]
    return SEP.join(build(payload, request))


def answer_without_warning(answer: str, warning: str | None) -> str:
    """A degraded `answer` begins with its warning; the warning is shown once, separately."""
    if warning and answer.startswith(warning):
        return answer[len(warning) :].lstrip("\n")
    return answer


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _share_figure(rate: Any) -> str | None:
    """A 4-place rate as the percentage the answer text prints ("0.8881" -> "88.81%")."""
    try:
        return f"{Decimal(rate) * 100:.2f}%"
    except (InvalidOperation, TypeError, ValueError):
        return None


def headline(body: dict, answer: str) -> dict[str, str] | None:
    """The single figure of a reporting answer, large above the text (§6, rule 8), or None.

    Shown only for an answered, verified reporting question with no breakdown, whose metric is an
    incident count, SLA compliance or a first-time fix rate. The figure comes from the specialist's
    data part, formatted as the answer text formats it, and must appear in `answer`; so must the
    "<M> <denominator words>" the caption quotes. Anything missing or off gives None, never an
    error. An answer filtered to a technician or an account gets none either: the caption names
    only the measure and the region, so the figure would read as the whole region's.
    """
    if body.get("outcome") != "answered" or body.get("qa_status") != "verified":
        return None
    if (body.get("route") or {}).get("route") != "reporting":
        return None
    payload = body.get("reporting")
    request = payload.get("request") if isinstance(payload, dict) else None
    figures = payload.get("figures") if isinstance(payload, dict) else None
    if not isinstance(request, dict) or not isinstance(figures, dict):
        return None
    metric = request.get("metric")
    if metric not in HEADLINE_NOUNS or request.get("group_by") is not None:
        return None
    if request.get("technician_name") or request.get("account_name"):
        return None
    if figures.get("metric") != metric or figures.get("group_by") is not None:
        return None

    caption = f"{METRICS[metric]}, {_region(request.get('region')).removeprefix('Region: ')}"
    noun = HEADLINE_NOUNS[metric]
    if noun is None:
        count = _int(figures.get("incident_count"))
        if count is None:
            return None
        figure = f"{count:,}"
        if f"{figure} incident" not in answer:
            return None
    else:
        figure = _share_figure(figures.get("rate")) if figures.get("rate") else None
        numerator, denominator = _int(figures.get("numerator")), _int(figures.get("denominator"))
        if figure is None or numerator is None or not denominator:
            return None
        base = f"{denominator:,} {noun}" + ("" if denominator == 1 else "s")
        if figure not in answer or base not in answer:
            return None
        caption += f" · {numerator:,} of {base}"
    return {"figure": figure, "caption": caption}


def journey_view(body: dict, forward_ms: float | None) -> dict[str, Any] | None:
    """The orchestrator's `journey` (§6, rule 10), passed through unchanged except that the
    gateway's own `forward` hop leads the hops. None when the response has none (an older
    orchestrator) or it is not the expected shape."""
    journey = body.get("journey")
    hops = journey.get("hops") if isinstance(journey, dict) else None
    if not isinstance(hops, list):
        return None
    if forward_ms is None:
        return journey
    forward = {
        "service": "gateway",
        "step": "forward",
        "attempt": 1,
        "start_ms": 0.0,
        "duration_ms": round(max(forward_ms, 0.0), 1),
        "status": "ok",
    }
    return {**journey, "hops": [forward, *hops]}


def view(question: str, body: dict, forward_ms: float | None = None) -> dict[str, Any]:
    """The UI's view of one orchestrator response: only the fields the display rules name."""
    warning = body.get("warning")
    answer = answer_without_warning(str(body.get("answer", "")), warning)
    return {
        "question": question,
        "answer": answer,
        "outcome": body.get("outcome"),
        "headline": headline(body, answer),
        "interpreted_as": interpreted_as(body),
        "qa_status": body.get("qa_status"),
        "qa_text": qa_text(str(body.get("qa_status")), body.get("outcome")),
        "escalate": bool(body.get("escalate")),
        "warning": warning,
        "trace_id": body.get("trace_id"),
        "journey": journey_view(body, forward_ms),
    }
