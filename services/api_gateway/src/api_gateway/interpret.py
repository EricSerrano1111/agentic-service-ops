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
    return f"{start} to {end}" + (ASSUMED if assumed else "")


def _region(value: Any, *, allow_all: bool = True) -> str | None:
    if value == "unsupported":
        return "region not recognised"
    if value:
        return str(value).capitalize()
    return "all regions" if allow_all else None


def _person(request: dict) -> list[str]:
    out = []
    if request.get("account_name"):
        out.append(f"account: {request['account_name']}")
    if request.get("technician_name"):
        out.append(f"technician: {request['technician_name']}")
    return out


def _reporting(payload: dict | None, request: dict) -> list[str]:
    metric = request.get("metric")
    parts = [METRICS.get(metric, "measure not recognised") if metric else "incident figures"]
    if payload:
        period = _range(
            payload.get("start"), payload.get("end"), bool(payload.get("range_assumed"))
        )
    else:
        period = _range(request.get("start"), request.get("end"), False)
    if period:
        parts.append(period)
    parts.append(_region(request.get("region")))
    parts += _person(request)
    if request.get("group_by"):
        parts.append(f"by {_words(request['group_by'])}")
    return parts


def _sentiment(payload: dict | None, request: dict) -> list[str]:
    measure = "customer sentiment"
    if request.get("want_trend"):
        measure += " trend"
    if request.get("want_examples"):
        label = request.get("example_label")
        measure += " with example comments" + (f" ({label})" if label else "")
    parts = [measure]
    if payload:
        period = _range(
            payload.get("start"), payload.get("end"), bool(payload.get("range_assumed"))
        )
    else:
        period = _range(request.get("start"), request.get("end"), False)
    if period:
        parts.append(period)
    parts.append(_region(request.get("region")))
    if request.get("bucket"):
        parts.append(f"by {request['bucket']}")
    if request.get("unsupported"):
        parts.append(f"not supported: {_words(request['unsupported'])}")
    return parts


def _forecast(payload: dict | None, request: dict) -> list[str]:
    parts = ["weekly service request forecast"]
    slice_ = request.get("slice") or "total"
    parts.append("all service types" if slice_ == "total" else str(slice_))
    if payload and payload.get("requested_first_week") and payload.get("requested_last_week"):
        text = (
            f"weeks starting {payload['requested_first_week']} to {payload['requested_last_week']}"
        )
        parts.append(text + (ASSUMED if payload.get("range_assumed") else ""))
    elif request.get("period_start") and request.get("period_end"):
        parts.append(f"{request['period_start']} to {request['period_end']}")
    if request.get("horizon_weeks"):
        parts.append(f"next {request['horizon_weeks']} weeks")
    if request.get("want_history"):
        parts.append("with recent history")
    if request.get("unsupported"):
        parts.append(f"not supported: {_words(request['unsupported'])}")
    return parts


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
    return SEP.join(p for p in build(payload, request) if p)


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
