"""What the UI shows for one answer: the "Interpreted as:" line and the `qa_status` wording.

The rules are data dictionary §6, "Answer display (UI)". The gateway builds these strings so the
UI computes nothing and the rules are tested in CI. Free text from the question (an account or
technician name) is passed as typed; the UI renders it as text.
"""

from __future__ import annotations

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

METRICS = {
    "incident_count": "incident count",
    "incident_rate": "incident rate",
    "sla_compliance": "SLA compliance",
    "first_time_fix_rate": "first-time fix rate",
    "repeat_visit_drivers": "repeat-visit drivers",
    "unsupported": "measure not recognised",
}
DOMAINS = ("reporting", "sentiment", "forecast")


def qa_text(qa_status: str) -> str | None:
    """The user-facing words for a `qa_status`; None (no line) for `not_applicable`."""
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


def view(question: str, body: dict) -> dict[str, Any]:
    """The UI's view of one orchestrator response: only the fields the display rules name."""
    warning = body.get("warning")
    return {
        "question": question,
        "answer": answer_without_warning(str(body.get("answer", "")), warning),
        "outcome": body.get("outcome"),
        "interpreted_as": interpreted_as(body),
        "qa_status": body.get("qa_status"),
        "qa_text": qa_text(str(body.get("qa_status"))),
        "escalate": bool(body.get("escalate")),
        "warning": warning,
        "trace_id": body.get("trace_id"),
    }
