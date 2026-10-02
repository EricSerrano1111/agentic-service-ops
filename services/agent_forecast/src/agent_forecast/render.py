"""Template-rendered forecast answers (ADR-046, ADR-072). No model writes any of this text.

Every figure is a field of the `ForecastAnswer` data part, formatted: request counts
rounded to whole requests, errors to one decimal place. Numbers appear only for served
weeks; an unserved band is named with its error instead (ADR-071). A period total is the
sum of the weekly forecasts and carries no range.
"""

from __future__ import annotations

import datetime as dt

from schemas import HORIZON_BANDS, MAX_HORIZON_WEEKS, ForecastAnswer

BAND_TEXT = {"1-4": "1-4 weeks", "5-13": "5-13 weeks", "14-26": "14-26 weeks"}
SUPPORTED = (
    "I can forecast weekly request volume, in total or by service type (install, repair, "
    "maintenance, inspection, upgrade), up to 26 weeks ahead."
)
DECLINES = {
    "sla": "SLA outlook can't be forecast: there's no model for SLA compliance.",
    "incidents": "Incidents can't be forecast: there's no incident model.",
    "sentiment": "Customer sentiment can't be forecast.",
    "region": "Forecasts can't be broken down by region.",
    "account": "Forecasts can't be broken down by account.",
    "technician": "Forecasts can't be broken down by technician.",
    "other": "That isn't something I can forecast.",
}
YEAR_END = (
    "Christmas and New Year weeks include a holiday adjustment that hasn't been validated on "
    "held-out data."
)


def decline_message(unsupported: str, as_of: dt.date) -> str:
    if unsupported == "past_period":
        text = f"That period has already happened; forecasts cover weeks after {as_of.isoformat()}."
    else:
        text = DECLINES[unsupported]
    return f"{text} {SUPPORTED}"


def no_week_message(as_of: dt.date) -> str:
    return (
        "No forecast week starts in that period (weeks start on Monday). "
        f"Forecasts cover weeks after {as_of.isoformat()}. {SUPPORTED}"
    )


def slice_label(slice_: str) -> str:
    return "total request volume" if slice_ == "total" else f"{slice_} requests"


def _n(x: float) -> str:
    return f"{round(x):,}"


def _pct(x: float) -> str:
    return f"{x:.1f}%"


def render_answer(a: ForecastAnswer) -> str:
    lines: list[str] = []
    label = slice_label(a.request.slice)
    n_requested = len(a.weeks) + a.beyond_horizon_weeks
    last_end = a.requested_last_week + dt.timedelta(days=6)
    assumed = "; no period was named, so next month was assumed" if a.range_assumed else ""
    lines.append(
        f"Forecast of {label}, {n_requested} week{'s' if n_requested != 1 else ''} from "
        f"{a.requested_first_week.isoformat()} to {last_end.isoformat()} (weeks start on Monday, "
        f"UTC), as of {a.as_of.isoformat()}; the model is trained on data through "
        f"{a.trained_through.isoformat()}{assumed}."
    )
    if not a.weeks:
        lines.append(
            f"All requested weeks fall beyond the {MAX_HORIZON_WEEKS}-week forecast horizon, so "
            "none is forecast."
        )
    served = [w for w in a.weeks if w.served]
    for w in served:
        lines.append(
            f"- Week of {w.week_start.isoformat()}: about {_n(w.point)} requests "
            f"(80% range {_n(w.lo80)}-{_n(w.hi80)})"
        )
    if a.period_total is not None:
        lines.append(
            f"Total over these {len(a.weeks)} weeks: about {_n(a.period_total)} requests, the sum "
            "of the weekly forecasts; no range is given for a total."
        )
    elif len(a.weeks) > 1 and served and len(served) < len(a.weeks):
        lines.append("No total is given, because some of these weeks aren't shown.")
    for band in HORIZON_BANDS:
        v = a.bands.get(band)
        if v is None:
            continue
        if v.served:
            lines.append(
                f"On held-out weeks at {BAND_TEXT[band]} ahead, forecasts were off by "
                f"{_pct(v.shown_error)} on average."
            )
        else:
            lines.append(
                f"Forecasts for {label} at {BAND_TEXT[band]} ahead aren't shown: they were off "
                f"by {_pct(v.shown_error)} on held-out weeks."
            )
    if a.year_end_weeks:
        lines.append(YEAR_END)
    if a.beyond_horizon_weeks and a.weeks:
        k = a.beyond_horizon_weeks
        lines.append(
            f"The remaining {k} week{'s' if k != 1 else ''} fall beyond the "
            f"{MAX_HORIZON_WEEKS}-week forecast horizon and aren't forecast."
        )
    if a.history:
        recent = ", ".join(f"{h.week_start.isoformat()}: {h.count:,}" for h in a.history)
        lines.append(f"Recent actual weekly counts ({label}): {recent}.")
    return "\n".join(lines)
