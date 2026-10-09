"""Reporting checks (ADR-087): QA recomputes every figure in a reporting answer with its own SQL
and compares, checks the request was one that should be answered, checks declines carry no
figures and say a true reason, and checks the answer text states the verified numbers.

Written from data dictionary §6 alone. It imports nothing from the reporting agent or the
incidents server (a test fails if it does). Where §6 is silent and the specialist's code reads
it one way, the check is tolerant of every reading and the gap is recorded in L-72:
- a rate breakdown's tie order and the place of groups with no rate (checked as "not out of
  order", and a cut-off group is never better than a kept one);
- an incident type with no job in a repeat-drivers range (listed with zero jobs, or absent);
- "whole word" tokenisation in name lookup (whitespace);
- which of several applicable reasons a decline states (any true one passes).
"""

from __future__ import annotations

import datetime as dt
import math
import re
from decimal import Decimal
from fractions import Fraction
from typing import Any

from schemas import (
    DATASET_WINDOW_END,
    DATASET_WINDOW_START,
    CheckResult,
    IncidentRateResult,
    IncidentSummary,
    RepeatDriversResult,
    ReportingAnswer,
    ReportingRequest,
)

from . import names, textcheck
from .config import Settings
from .db import UNATTRIBUTED, GroupRow, Source, utc_bounds
from .repeats import MIN_JOBS, Drivers, compute
from .stats import rate_string

MAX_GROUPS = 25
TEXT_GROUPS = 5

#: The breakdowns each metric offers (data dictionary §6).
BREAKDOWNS = {
    "incident_count": {
        "account",
        "region",
        "service_type",
        "technician",
        "incident_type",
        "severity",
    },
    "incident_rate": {"account", "region", "service_type", "technician"},
    "sla_compliance": {"account", "region", "service_type", "technician"},
    "first_time_fix_rate": {"account", "region", "service_type", "technician"},
    "repeat_visit_drivers": {"incident_type", "service_type", "region", "account", "technician"},
}

#: What a decline's text says for each reason class: a phrase that states it.
DECLINE_PHRASES = {
    "unsupported_metric": "metric isn't supported",
    "unsupported_breakdown": "breakdown isn't supported",
    "breakdown_not_offered": "can't be broken down by",
    "unsupported_area": "one of four regions",
    "repeat_region_or_account": "can't be filtered to one region or account",
    "repeat_technician": "can't be filtered to one technician",
    "region_same_dimension": "can't also be broken down by region",
    "account_same_dimension": "can't also be broken down by account",
    "technician_breakdown": "can't also be broken down",
}
DECLINE_CODES = {
    "not_supported",
    "technician_not_found",
    "technician_ambiguous",
    "account_not_found",
    "account_ambiguous",
}


def ok(code: str, check_class: str = "figures") -> CheckResult:
    return CheckResult(code=code, check_class=check_class, passed=True)


def bad(code: str, detail: str, check_class: str = "figures") -> CheckResult:
    return CheckResult(code=code, check_class=check_class, passed=False, detail=detail[:200])


def result(code: str, problems: list[str], check_class: str = "figures") -> CheckResult:
    """A pass, or a fail listing the problems (fixed phrases naming a field, never a value)."""
    if not problems:
        return ok(code, check_class)
    return bad(code, "; ".join(dict.fromkeys(problems)), check_class)


# --------------------------------------------------------------------------- the request


def decline_reasons(req: ReportingRequest) -> set[str]:
    """Every reason this request cannot be answered (§6, ADR-073, ADR-086), as reason classes.
    Empty when it should be answered."""
    reasons: set[str] = set()
    if req.metric == "unsupported":
        reasons.add("unsupported_metric")
        return reasons
    if req.group_by == "unsupported":
        reasons.add("unsupported_breakdown")
    elif req.group_by is not None and req.group_by not in BREAKDOWNS[req.metric]:
        reasons.add("breakdown_not_offered")
    if req.region == "unsupported":
        reasons.add("unsupported_area")
    if req.metric == "repeat_visit_drivers":
        if req.region is not None or req.account_name is not None:
            reasons.add("repeat_region_or_account")
        if req.technician_name is not None:
            reasons.add("repeat_technician")
    if req.region not in (None, "unsupported") and req.group_by == "region":
        reasons.add("region_same_dimension")
    if req.account_name is not None and req.group_by == "account":
        reasons.add("account_same_dimension")
    if req.technician_name is not None and req.group_by is not None:
        reasons.add("technician_breakdown")
    return reasons


def last_full_month(as_of: dt.date) -> tuple[dt.date, dt.date]:
    """The default range when the question names none (ADR-050): the calendar month before the
    as-of date's."""
    end = as_of.replace(day=1) - dt.timedelta(days=1)
    return end.replace(day=1), end


def _expected_range(req: ReportingRequest, as_of: dt.date) -> tuple[dt.date, dt.date, bool]:
    if req.start is None:
        start, end = last_full_month(as_of)
        return start, end, True
    return req.start, req.end, False


# --------------------------------------------------------------------------- rate groups


def _worse_key(rate: str | None, higher_is_worse: bool) -> tuple[bool, Decimal]:
    """Sorts worst first; a group with no rate sorts last."""
    if rate is None:
        return True, Decimal(0)
    value = Decimal(rate)
    return False, -value if higher_is_worse else value


def _compare_ranked(
    shown: list[Any],
    expected: list[tuple[Any, str | None]],
    shown_identity,
    shown_rate,
    group_count: int,
    truncated: bool,
    higher_is_worse: bool,
) -> list[str]:
    """Order and cut-off of a ranked list, tolerant of ties and of where a rate-less group
    falls inside the tie order: the shown groups must be in worst-first order, be the right
    number, and no cut-off group may be worse than a kept one."""
    problems = []
    if group_count != len(expected):
        problems.append("group_count")
    if truncated != (len(expected) > MAX_GROUPS):
        problems.append("truncated_flag")
    if len(shown) != min(MAX_GROUPS, len(expected)):
        problems.append("groups_shown")
    keys = [_worse_key(shown_rate(g), higher_is_worse) for g in shown]
    if keys != sorted(keys):
        problems.append("group_order")
    shown_ids = {shown_identity(g) for g in shown}
    if len(shown_ids) != len(shown):
        problems.append("duplicate_group")
    omitted = [
        _worse_key(rate, higher_is_worse) for ident, rate in expected if ident not in shown_ids
    ]
    if keys and omitted and max(keys) > min(omitted):
        problems.append("cutoff_group_kept_a_worse_one")
    return problems


def _compare_rate_groups(src_rows: list[GroupRow], figures, scale: int, higher: bool) -> list[str]:
    by_identity = {(r.label, r.group_id): r for r in src_rows}
    expected = [
        ((r.label, r.group_id), rate_string(r.numerator, r.denominator, scale)) for r in src_rows
    ]
    shown = figures.groups or []
    problems = []
    for g in shown:
        row = by_identity.get((g.group, g.group_id))
        if row is None:
            problems.append("group_not_in_database")
            continue
        if (
            g.numerator != row.numerator
            or g.denominator != row.denominator
            or g.rate != rate_string(row.numerator, row.denominator, scale)
        ):
            problems.append("group_figures")
    problems += _compare_ranked(
        shown,
        expected,
        lambda g: (g.group, g.group_id),
        lambda g: g.rate,
        figures.group_count,
        figures.truncated,
        higher,
    )
    return problems


# --------------------------------------------------------------------------- the figures


class Checker:
    def __init__(self, src: Source, settings: Settings) -> None:
        self.src = src
        self.settings = settings

    # ------------------------------------------------------------------ answers

    def check_answer(self, answer: ReportingAnswer, text: str) -> list[CheckResult]:
        req = answer.request
        checks = [
            result(
                "request_supported",
                ["answered a request that should be declined"] if decline_reasons(req) else [],
            ),
            self._check_range(answer),
        ]
        identity, ids = self._check_filters(answer)
        checks.append(identity)
        if not decline_reasons(req) and identity.passed:
            checks.append(self._check_figures(answer, ids))
        else:
            checks.append(bad("figures_match_database", "not compared: the request is not valid"))
        if all(c.passed for c in checks):
            checks.append(self._check_text(answer, text))
        return checks

    def _check_range(self, answer: ReportingAnswer) -> CheckResult:
        problems = []
        start, end, assumed = _expected_range(answer.request, self.settings.as_of)
        if (answer.start, answer.end) != (start, end):
            problems.append("range_differs_from_request")
        if answer.range_assumed != assumed:
            problems.append("range_assumed_flag")
        if answer.as_of != self.settings.as_of:
            problems.append("as_of_differs")
        if answer.start < DATASET_WINDOW_START or answer.end > DATASET_WINDOW_END:
            problems.append("range_outside_window")
        return result("range_matches_request", problems)

    def _check_filters(self, answer: ReportingAnswer) -> tuple[CheckResult, dict[str, Any]]:
        """The technician and account the figures are about are the ones the typed names pick
        out, by QA's own lookup; the region and breakdown are the request's."""
        req, f = answer.request, answer.figures
        problems: list[str] = []
        ids: dict[str, Any] = {"technician_id": None, "account_id": None}
        if req.technician_name is not None:
            found = names.match(req.technician_name, self.src.technicians())
            if found.total != 1 or getattr(f, "technician_id", None) != found.listed[0][0]:
                problems.append("technician_not_the_one_named")
            elif getattr(f, "technician_name", None) != found.listed[0][1]:
                problems.append("technician_name_differs")
            else:
                ids["technician_id"] = found.listed[0][0]
        if req.account_name is not None:
            found = names.match(req.account_name, self.src.accounts())
            if found.total != 1 or getattr(f, "account_id", None) != found.listed[0][0]:
                problems.append("account_not_the_one_named")
            elif getattr(f, "account_name", None) != found.listed[0][1]:
                problems.append("account_name_differs")
            else:
                ids["account_id"] = found.listed[0][0]
        if getattr(f, "region", None) != req.region:
            problems.append("region_differs")
        expected_group = req.group_by
        if req.metric == "repeat_visit_drivers" and expected_group is None:
            expected_group = "incident_type"  # the default breakdown (ADR-073)
        if getattr(f, "group_by", None) != expected_group:
            problems.append("breakdown_differs")
        if f.metric != req.metric:
            problems.append("metric_differs")
        return result("filters_match_request", problems), ids

    def _check_figures(self, answer: ReportingAnswer, ids: dict[str, Any]) -> CheckResult:
        f = answer.figures
        lo, hi = utc_bounds(answer.start, answer.end)
        region = getattr(f, "region", None)
        account_id, tech_id = ids["account_id"], ids["technician_id"]
        if isinstance(f, IncidentSummary):
            problems = self._incident_count(f, lo, hi, region, account_id, tech_id)
        elif isinstance(f, RepeatDriversResult):
            problems = self._repeat(f, lo, hi)
        else:
            problems = self._rate(f, lo, hi, region, account_id, tech_id)
        return result("figures_match_database", problems)

    def _incident_count(self, f, lo, hi, region, account_id, tech_id) -> list[str]:
        problems = []
        counts = self.src.severity_counts(lo, hi, region, account_id, tech_id)
        if f.incident_count != sum(counts.values()):
            problems.append("incident_count")
        if (f.by_severity.low, f.by_severity.medium, f.by_severity.high) != (
            counts["low"],
            counts["medium"],
            counts["high"],
        ):
            problems.append("by_severity")
        if f.group_by is not None:
            rows = self.src.count_groups(lo, hi, f.group_by, region, account_id)
            expected = sorted(rows, key=lambda r: (-r.numerator, r.label))
            want = [(r.label, r.group_id, r.numerator) for r in expected[:MAX_GROUPS]]
            got = [(g.group, g.group_id, g.count) for g in (f.groups or [])]
            if got != want:
                problems.append("groups")
            if f.group_count != len(expected):
                problems.append("group_count")
            if f.truncated != (len(expected) > MAX_GROUPS):
                problems.append("truncated_flag")
            if sum(r.numerator for r in expected) != sum(counts.values()):
                problems.append("groups_do_not_sum_to_total")
        return problems

    def _rate(self, f, lo, hi, region, account_id, tech_id) -> list[str]:
        metric = f.metric
        scale = 100 if metric == "incident_rate" else 1
        higher = metric == "incident_rate"
        num, den = self.src.metric_counts(metric, lo, hi, region, account_id, tech_id)
        problems = []
        if (f.numerator, f.denominator) != (num, den):
            problems.append("totals")
        if f.rate != rate_string(num, den, scale):
            problems.append("rate")
        if f.group_by is not None:
            rows = self.src.metric_groups(metric, lo, hi, f.group_by, region, account_id)
            problems += _compare_rate_groups(rows, f, scale, higher)
        return problems

    def _repeat(self, f: RepeatDriversResult, lo, hi) -> list[str]:
        jobs, types = self.src.repeat_jobs(lo, hi)
        want = compute(jobs, types, f.group_by)
        problems = []

        def tally(t, expected) -> bool:
            return (t.jobs, t.repeated, t.rate) == (expected.jobs, expected.repeated, expected.rate)

        if not tally(f.overall, want.overall):
            problems.append("overall")
        # §6 compares a group with "the rest"; a group that is every job leaves no rest, and whether
        # it counts as compared (and so what Bonferroni multiplies by) is not defined (L-72). Then
        # the significance fields are not checked, only the counts, rates and order.
        no_rest = any(g.rest.jobs == 0 and g.this.jobs >= MIN_JOBS for g in want.groups)
        if not no_rest and f.groups_compared != want.groups_compared:
            problems.append("groups_compared")
        by_label = {(g.label, g.group_id): g for g in want.groups}
        shown = list(f.groups)
        zero_job = 0
        for g in shown:
            exp = by_label.get((g.group, g.group_id))
            if exp is None:
                if f.group_by == "incident_type" and g.this.jobs == 0:
                    zero_job += 1  # a type with no job in range, listed with zero jobs
                    continue
                problems.append("group_not_in_database")
                continue
            if not (tally(g.this, exp.this) and tally(g.rest, exp.rest)):
                problems.append("group_counts")
            if no_rest:
                continue
            if g.compared != exp.compared:
                problems.append("compared_flag")
            elif g.compared and exp.p_value is not None:
                if g.p_value is None or not _close(g.p_value, exp.p_value):
                    problems.append("p_value")
                if not _close(g.p_adjusted, exp.p_adjusted):
                    problems.append("p_adjusted")
            if g.stands_out != exp.stands_out:
                problems.append("stands_out")
        # Listing order: repeat rate (highest first), then more jobs, then name (§6).
        kept = [g for g in shown if g.this.jobs > 0 or f.group_by != "incident_type"]
        order = [(-_fraction(g.this), -g.this.jobs, g.group) for g in kept]
        if order != sorted(order):
            problems.append("group_order")
        if f.group_count - zero_job != len(want.groups):
            problems.append("group_count")
        if f.truncated != (f.group_count > len(f.groups)):
            problems.append("truncated_flag")
        if len(kept) != min(MAX_GROUPS, len(want.groups)):
            problems.append("groups_shown")
        if len(want.groups) > MAX_GROUPS:
            expected_ids = {(g.label, g.group_id) for g in want.groups[:MAX_GROUPS]}
            if {(g.group, g.group_id) for g in kept} != expected_ids:
                problems.append("cutoff_groups")
        if f.group_by == "incident_type":
            a, b, compared, p, higher = want.other
            if not (
                f.any_other_incident
                and tally(f.any_other_incident, a)
                and f.no_other_incident
                and tally(f.no_other_incident, b)
            ):
                problems.append("any_other_incident")
            if f.other_incident_compared != compared:
                problems.append("other_incident_compared")
            elif compared and (
                f.other_incident_p_value is None or not _close(f.other_incident_p_value, p)
            ):
                problems.append("other_incident_p_value")
            if f.other_incident_higher != higher:
                problems.append("other_incident_higher")
        return problems

    # ------------------------------------------------------------------ text

    def _check_text(self, answer: ReportingAnswer, text: str) -> CheckResult:
        f = answer.figures
        allowed: set[str] = {"100", str(self.settings.min_group_denominator), "20"}
        required: list[set[str]] = []
        labels: list[str] = []

        def add_int(*values: int) -> None:
            for v in values:
                allowed.update(textcheck.int_forms(v))

        def add_rate(rate: str | None, share: bool) -> set[str]:
            forms: set[str] = set()
            if rate is not None:
                forms = {textcheck.percent(rate)} if share else {rate}
                allowed.update(forms)
            return forms

        labels += [
            getattr(f, "technician_name", None) or "",
            getattr(f, "account_name", None) or "",
        ]
        if isinstance(f, IncidentSummary):
            add_int(f.incident_count, f.by_severity.low, f.by_severity.medium, f.by_severity.high)
            required.append(textcheck.int_forms(f.incident_count))
            if f.groups is not None:
                add_int(f.group_count, len(f.groups), max(0, f.group_count - TEXT_GROUPS))
                for g in f.groups:
                    add_int(g.count)
                    labels.append(g.group)
        elif isinstance(f, RepeatDriversResult):
            add_int(f.overall.jobs, f.overall.repeated, f.group_count, len(f.groups))
            add_int(max(0, f.group_count - TEXT_GROUPS), 5)
            add_rate(f.overall.rate, True)
            if f.overall.jobs:
                required.append(textcheck.int_forms(f.overall.repeated))
                required.append(add_rate(f.overall.rate, True))
            left_out = 0
            for g in f.groups:
                labels.append(g.group)
                add_int(g.this.jobs, g.this.repeated, g.rest.jobs, g.rest.repeated)
                add_rate(g.this.rate, True)
                add_rate(g.rest.rate, True)
                left_out += g.this.jobs < self.settings.min_group_denominator
            add_int(left_out)
            for t in (f.any_other_incident, f.no_other_incident):
                if t is not None:
                    add_int(t.jobs, t.repeated)
                    add_rate(t.rate, True)
        else:
            share = not isinstance(f, IncidentRateResult)
            add_int(f.numerator, f.denominator)
            required.append(textcheck.int_forms(f.numerator))
            if f.rate is not None:
                required.append(add_rate(f.rate, share))
            if f.groups is not None:
                add_int(f.group_count, len(f.groups))
                left_out = 0
                for g in f.groups:
                    labels.append(g.group)
                    add_int(g.numerator, g.denominator)
                    add_rate(g.rate, share)
                    left_out += g.denominator < self.settings.min_group_denominator
                add_int(left_out)
        problems = textcheck.compare(text, allowed, required, labels)
        dates = set(re.findall(r"\b\d{4}-\d{2}-\d{2}\b", text))
        if not dates <= {d.isoformat() for d in (answer.start, answer.end, answer.as_of)}:
            problems.append("text_states_another_date")
        return result("text_matches_data", problems)

    # ------------------------------------------------------------------ declines

    def check_decline(
        self, request: ReportingRequest, error_code: str, text: str
    ) -> list[CheckResult]:
        """A decline carries no figures and says a true reason."""
        problems: list[str] = []
        reasons = decline_reasons(request)
        if error_code not in DECLINE_CODES:
            return [bad("decline_matches_reason", "not a decline code QA knows")]
        if error_code == "not_supported":
            stated = {c for c, phrase in DECLINE_PHRASES.items() if phrase in text}
            if not stated:
                problems.append("reason_not_recognised_in_text")
            elif not (stated & reasons):
                problems.append("reason_in_text_does_not_apply")
        elif error_code.startswith("technician"):
            problems += self._name_decline(
                error_code, "technician", request.technician_name, self.src.technicians(), text
            )
        else:
            problems += self._name_decline(
                error_code, "account", request.account_name, self.src.accounts(), text
            )
        sanctioned = re.sub(r"\b\d+ (?:technicians|accounts) match\b|\band \d+ more\b", " ", text)
        own = [request.technician_name or "", request.account_name or ""]
        problems_text = ["text_carries_a_number"] if textcheck.numbers_in(sanctioned, own) else []
        return [
            result("decline_matches_reason", problems),
            result("decline_no_figures", problems_text),
        ]

    def _name_decline(self, code, kind, typed, candidates, text) -> list[str]:
        if typed is None:
            return ["no_name_was_parsed"]
        found = names.match(typed, candidates)
        if code.endswith("not_found"):
            return [] if found.total == 0 else ["a_match_exists"]
        problems = []
        if found.total < 2:
            return ["fewer_than_two_matches"]
        m = re.search(r"\b(\d+) (?:technicians|accounts) match\b", text)
        if m is None or int(m.group(1)) != found.total:
            problems.append("match_count_differs")
        for _, name in found.listed:
            if name not in text:
                problems.append("a_match_is_not_listed")
                break
        return problems


def _fraction(t) -> Fraction:
    return Fraction(t.repeated, t.jobs)


def _close(a: float | None, b: float | None) -> bool:
    return a is not None and b is not None and math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-12)


__all__ = ["Checker", "decline_reasons", "last_full_month", "UNATTRIBUTED", "Drivers"]
