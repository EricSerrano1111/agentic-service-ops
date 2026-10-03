"""Independent oracles for golden set v1 (ADR-074): the expected figures per item.

Reporting and sentiment figures are fresh SQL run as `app_eval`, written from
`docs/data-dictionary.md` §6 and ADR-068 directly; nothing here imports or calls the
system's services or its LLM package (a unit test guards that). Statistical tests use
scipy (Fisher's exact) and statsmodels (the two-proportion z-test). The forecast oracle is
ADR-074's documented exception: it uses `packages/forecast_runtime` with the `volume_v2`
manifest, because the golden set checks that the agent presents the model's served
numbers and errors, not the model's accuracy.

Conventions (§6): inclusive UTC days as a half-open timestamp range; rates are strings
rounded half-up to 4 places; a zero denominator gives a null rate.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[2]
AS_OF = dt.date(2026, 8, 30)
SENTIMENT_MODEL_VERSION = "0fa27f641d95260d84b4742501dd47cade23f1f8ae0ff336d8cbf927f70333ad"
LABELS = ("positive", "neutral", "negative", "mixed")
MIN_CASES = 20  # §6 / ADR-068 / ADR-073: groups and trend sides need at least 20 cases
ALPHA = 0.05
FORECAST_MANIFEST = ROOT / "ml" / "forecast" / "artifacts" / "volume_v2.manifest.json"
FORECAST_DIR = ROOT / "models" / "forecast" / "volume_v2"

Conn = psycopg.Connection


def connect() -> Conn:
    """A read-only `app_eval` connection from the environment (`.env` when present)."""
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env", override=False)
    except ImportError:
        pass
    return psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["DB_ROLE_EVAL_USER"],
        password=os.environ["DB_ROLE_EVAL_PASSWORD"],
        autocommit=True,
    )


def D(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def _params(start: dt.date, end: dt.date) -> dict:
    lo = dt.datetime.combine(start, dt.time.min, dt.UTC)
    return {"lo": lo, "hi": lo + dt.timedelta(days=(end - start).days + 1)}


def rate(num: int, den: int, scale: int = 1) -> str | None:
    if den == 0:
        return None
    return str((Decimal(num * scale) / Decimal(den)).quantize(Decimal("0.0001"), ROUND_HALF_UP))


def _range(start: dt.date, end: dt.date) -> dict:
    return {"start": start.isoformat(), "end": end.isoformat()}


# =========================================================================== reporting (§6)

# The three request-level metrics as (numerator, denominator) per group key. Group keys:
# region (the site's, ADR-051), service type, account, or the technician who did the work
# (archived_requests.technician_id). Incidents by technician use attributed_technician_id.
_GROUP = {
    None: ("'all'", ""),
    "region": ("l.region", "JOIN locations l ON l.location_id = r.location_id"),
    "service_type": ("r.service_type::text", ""),
    "account": ("ac.account_name", "JOIN accounts ac ON ac.account_id = r.account_id"),
}


def sla_compliance(conn: Conn, start, end, group_by=None, technician_id=None) -> dict:
    """§6: requests dispatched in range; sla_met = completed_at <= dispatched_at + window;
    requests not completed (no archived row) have no SLA outcome and are left out."""
    key, join = _GROUP[group_by]
    where = "AND a.technician_id = %(tid)s" if technician_id is not None else ""
    rows = conn.execute(
        f"""SELECT {key},
                   count(*) FILTER (WHERE a.completed_at
                       <= r.dispatched_at + make_interval(mins => r.sla_window_minutes)),
                   count(*)
            FROM service_requests r
            JOIN archived_requests a ON a.request_id = r.request_id
            {join}
            WHERE r.dispatched_at >= %(lo)s AND r.dispatched_at < %(hi)s {where}
            GROUP BY 1""",
        _params(start, end) | {"tid": technician_id},
    ).fetchall()
    return {k: (int(n), int(d)) for k, n, d in rows}


def first_time_fix(conn: Conn, start, end, group_by=None) -> dict:
    """§6: requests completed in range with no non-cancelled child, any child date."""
    key, join = _GROUP[group_by]
    rows = conn.execute(
        f"""SELECT {key},
                   count(*) FILTER (WHERE NOT EXISTS (
                       SELECT 1 FROM service_requests c
                       WHERE c.parent_request_id = r.request_id
                         AND c.request_status <> 'cancelled')),
                   count(*)
            FROM archived_requests a
            JOIN service_requests r ON r.request_id = a.request_id
            {join}
            WHERE a.completed_at >= %(lo)s AND a.completed_at < %(hi)s
            GROUP BY 1""",
        _params(start, end),
    ).fetchall()
    return {k: (int(n), int(d)) for k, n, d in rows}


def incident_rate(conn: Conn, start, end, group_by=None) -> dict:
    """§6: incidents reported in range per 100 requests completed in range."""
    key, join = _GROUP[group_by]
    p = _params(start, end)
    num = dict(
        conn.execute(
            f"""SELECT {key}, count(*) FROM incidents i
                JOIN service_requests r ON r.request_id = i.request_id {join}
                WHERE i.reported_at >= %(lo)s AND i.reported_at < %(hi)s GROUP BY 1""",
            p,
        ).fetchall()
    )
    den = dict(
        conn.execute(
            f"""SELECT {key}, count(*) FROM archived_requests a
                JOIN service_requests r ON r.request_id = a.request_id {join}
                WHERE a.completed_at >= %(lo)s AND a.completed_at < %(hi)s GROUP BY 1""",
            p,
        ).fetchall()
    )
    return {k: (int(num.get(k, 0)), int(den.get(k, 0))) for k in set(num) | set(den)}


def _ranked(groups: dict, scale: int, higher_is_worse: bool) -> list[dict]:
    """Worst first; null rates last; ties by name. `in_text` marks the 20-case rule."""
    out = [
        {
            "group": str(k),
            "numerator": n,
            "denominator": d,
            "rate": rate(n, d, scale),
            "in_text": d >= MIN_CASES,
        }
        for k, (n, d) in groups.items()
    ]
    sign = -1 if higher_is_worse else 1
    out.sort(key=lambda g: (g["rate"] is None, sign * Decimal(g["rate"] or 0), g["group"]))
    return out


def _overall(groups: dict, scale: int) -> dict:
    n = sum(v[0] for v in groups.values())
    d = sum(v[1] for v in groups.values())
    return {"numerator": n, "denominator": d, "rate": rate(n, d, scale)}


def incident_counts(conn: Conn, start, end) -> dict:
    """§6 (ADR-073): incidents reported in range, by severity."""
    p = _params(start, end)
    sev = dict(
        conn.execute(
            """SELECT severity::text, count(*) FROM incidents
               WHERE reported_at >= %(lo)s AND reported_at < %(hi)s GROUP BY 1""",
            p,
        ).fetchall()
    )
    by_severity = {s: int(sev.get(s, 0)) for s in ("high", "medium", "low")}
    return {"incident_count": sum(by_severity.values()), "by_severity": by_severity}


def _jobs(conn: Conn, start, end) -> list[tuple]:
    """Requests completed in range: (region, repeated). A job repeated if it has a
    non-cancelled child, whatever the child's date (§6 repeat-visit drivers)."""
    return conn.execute(
        """SELECT l.region,
                  EXISTS (SELECT 1 FROM service_requests c
                          WHERE c.parent_request_id = r.request_id
                            AND c.request_status <> 'cancelled')
           FROM archived_requests a
           JOIN service_requests r ON r.request_id = a.request_id
           JOIN locations l ON l.location_id = r.location_id
           WHERE a.completed_at >= %(lo)s AND a.completed_at < %(hi)s""",
        _params(start, end),
    ).fetchall()


def repeat_by_region(conn: Conn, start, end) -> dict:
    """§6 repeat-visit drivers by region: each region against all other jobs; stands out
    if at least 20 jobs, a higher rate than the rest, and Fisher two-sided p < 0.05 after
    Bonferroni over the regions compared. Listed by rate, highest first."""
    from scipy.stats import fisher_exact

    rows = _jobs(conn, start, end)
    n, rep = len(rows), sum(1 for _, r in rows if r)
    regions: dict[str, list[int]] = {}
    for region, repeated in rows:
        g = regions.setdefault(region, [0, 0])
        g[0] += 1
        g[1] += int(repeated)
    compared = [k for k, (j, _) in regions.items() if j >= MIN_CASES and n - j > 0]
    groups = []
    for k, (j, r) in regions.items():
        rj, rr = n - j, rep - r
        entry = {
            "group": k,
            "jobs": j,
            "repeated": r,
            "rate": rate(r, j),
            "rest_jobs": rj,
            "rest_repeated": rr,
            "rest_rate": rate(rr, rj),
            "compared": k in compared,
            "p_value": None,
            "p_adjusted": None,
            "stands_out": False,
        }
        if k in compared:
            p = float(fisher_exact([[r, j - r], [rr, rj - rr]], alternative="two-sided").pvalue)
            entry |= {
                "p_value": p,
                "p_adjusted": min(1.0, p * len(compared)),
                "stands_out": r * rj > rr * j and min(1.0, p * len(compared)) < ALPHA,
            }
        groups.append(entry)
    groups.sort(key=lambda g: (-Decimal(g["repeated"]) / g["jobs"], -g["jobs"], g["group"]))
    return {
        "overall": {"jobs": n, "repeated": rep, "rate": rate(rep, n)},
        "groups": groups,
        "groups_compared": len(compared),
        "any_stands_out": any(g["stands_out"] for g in groups),
    }


def technicians_named(conn: Conn, name: str) -> list[str]:
    """Display names in which every word of `name` is a whole word (ADR-073's rule)."""
    words = name.casefold().split()
    names = [r[0] for r in conn.execute("SELECT full_name FROM technicians ORDER BY 1")]
    return [n for n in names if all(w in n.casefold().split() for w in words)]


# --------------------------------------------------------------------------- per item


def g01(conn: Conn) -> dict:
    return {"technician_matches": technicians_named(conn, "Dave Miller")}


def g02(conn: Conn) -> dict:
    """Reference only: repeat visits for all regions and for Central; Chicago is a city,
    which the data doesn't hold, so neither figure is a Chicago figure."""
    s, e = D("2026-07-31"), D("2026-08-30")
    rows = _jobs(conn, s, e)
    central = [r for g, r in rows if g == "central"]
    n, rep = len(rows), sum(1 for _, r in rows if r)
    return _range(s, e) | {
        "all_regions": {"jobs": n, "repeated": rep, "rate": rate(rep, n)},
        "central": {
            "jobs": len(central),
            "repeated": sum(central),
            "rate": rate(sum(central), len(central)),
        },
    }


def g03(conn: Conn) -> dict:
    s, e = D("2026-06-01"), D("2026-08-30")
    g = sla_compliance(conn, s, e, "region")
    return _range(s, e) | {"overall": _overall(g, 1), "worst_first": _ranked(g, 1, False)}


def g11(conn: Conn) -> dict:
    s, e = D("2026-04-01"), D("2026-06-30")
    return _range(s, e) | {"overall": _overall(sla_compliance(conn, s, e), 1)}


def g12(conn: Conn) -> dict:
    s, e = D("2025-01-01"), D("2025-12-31")
    g = incident_rate(conn, s, e, "account")
    ranked = _ranked(g, 100, True)
    return _range(s, e) | {
        "overall": _overall(g, 100),
        "worst_first_in_text": [x for x in ranked if x["in_text"]][:5],
        "left_out_under_20": sum(not x["in_text"] for x in ranked),
        "group_count": len(ranked),
    }


def g13(conn: Conn) -> dict:
    s, e = D("2026-07-01"), D("2026-07-31")
    g = first_time_fix(conn, s, e, "service_type")
    return _range(s, e) | {"overall": _overall(g, 1), "worst_first": _ranked(g, 1, False)}


def g14(conn: Conn) -> dict:
    s, e = D("2026-07-01"), D("2026-07-31")
    return _range(s, e) | incident_counts(conn, s, e)


def g15(conn: Conn) -> dict:
    s, e = D("2026-01-01"), D("2026-08-30")
    [(tid,)] = conn.execute(
        "SELECT technician_id FROM technicians WHERE full_name = 'Priya Kim'"
    ).fetchall()
    g = sla_compliance(conn, s, e, technician_id=tid)
    o = _overall(g, 1)
    return _range(s, e) | {
        "technician": "Priya Kim",
        **o,
        "based_on": f"{o['denominator']} dispatched requests",
        "too_few": o["denominator"] < MIN_CASES,
    }


def g16(conn: Conn) -> dict:
    return {"technician_matches": technicians_named(conn, "Lina")}


def g17(conn: Conn) -> dict:
    s, e = D("2026-08-17"), D("2026-08-30")
    return _range(s, e) | {"overall": _overall(incident_rate(conn, s, e), 100)}


def g18(conn: Conn) -> dict:
    s, e = D("2026-01-01"), D("2026-08-30")
    return _range(s, e) | repeat_by_region(conn, s, e)


def g35(conn: Conn) -> dict:
    """Reference figures for the Southeast over the dateless default (July 2026): the
    reporting metrics' Southeast group and the Southeast sentiment shares."""
    s, e = D("2026-07-01"), D("2026-07-31")

    def southeast(groups, scale):
        n, d = groups.get("southeast", (0, 0))
        return {"numerator": n, "denominator": d, "rate": rate(n, d, scale)}

    return _range(s, e) | {
        "reporting": {
            "incident_rate": southeast(incident_rate(conn, s, e, "region"), 100),
            "sla_compliance": southeast(sla_compliance(conn, s, e, "region"), 1),
            "first_time_fix_rate": southeast(first_time_fix(conn, s, e, "region"), 1),
        },
        "sentiment": sentiment_shares(conn, s, e, "southeast"),
    }


# =========================================================================== sentiment


def _labels(conn: Conn, start, end, region=None) -> list[tuple]:
    """(submitted_at, predicted_label, flagged, feedback_id) for comments submitted in
    range, from stored predictions at the pinned model_version. Region is the comment's
    site region (service_requests.location_id -> locations.region; ADR-067)."""
    where = "AND l.region = %(region)s" if region else ""
    return conn.execute(
        f"""SELECT f.submitted_at, p.predicted_label::text, p.flagged, f.feedback_id
            FROM service_feedback f
            JOIN sentiment_predictions p
              ON p.feedback_id = f.feedback_id AND p.model_version = %(mv)s
            JOIN service_requests r ON r.request_id = f.request_id
            JOIN locations l ON l.location_id = r.location_id
            WHERE f.submitted_at >= %(lo)s AND f.submitted_at < %(hi)s {where}""",
        _params(start, end) | {"mv": SENTIMENT_MODEL_VERSION, "region": region},
    ).fetchall()


def _unscored(conn: Conn, start, end) -> int:
    return conn.execute(
        """SELECT count(*) FROM service_feedback f
           WHERE f.submitted_at >= %(lo)s AND f.submitted_at < %(hi)s
             AND NOT EXISTS (SELECT 1 FROM sentiment_predictions p
                             WHERE p.feedback_id = f.feedback_id AND p.model_version = %(mv)s)""",
        _params(start, end) | {"mv": SENTIMENT_MODEL_VERSION},
    ).fetchone()[0]


def _shares(rows) -> dict:
    n = len(rows)
    counts = {lab: sum(1 for r in rows if r[1] == lab) for lab in LABELS}
    return {
        "comments": n,
        "counts": counts,
        "shares": {lab: rate(c, n) for lab, c in counts.items()},
        "flagged": sum(1 for r in rows if r[2]),
    }


def sentiment_shares(conn: Conn, start, end, region=None) -> dict:
    return (
        _range(start, end)
        | {"region": region, "unscored_in_range": _unscored(conn, start, end)}
        | _shares(_labels(conn, start, end, region))
    )


def sentiment_trend(conn: Conn, start, end, region=None) -> dict:
    """ADR-068: monthly buckets; the latest bucket's negative share against the pooled
    negative share of all earlier buckets; "rose"/"fell" only if both sides have at least
    20 comments and a two-sided two-proportion z-test gives p < 0.05."""
    from statsmodels.stats.proportion import proportions_ztest

    rows = _labels(conn, start, end, region)
    buckets: dict[str, list] = {}
    for r in rows:
        buckets.setdefault(r[0].astimezone(dt.UTC).strftime("%Y-%m"), []).append(r)
    months = sorted(buckets)
    latest, earlier = months[-1], months[:-1]
    l_rows = buckets[latest]
    e_rows = [r for m in earlier for r in buckets[m]]
    ln, lneg = len(l_rows), sum(1 for r in l_rows if r[1] == "negative")
    en, eneg = len(e_rows), sum(1 for r in e_rows if r[1] == "negative")
    p = None
    verdict = "no clear change"
    if ln >= MIN_CASES and en >= MIN_CASES:
        _, p = proportions_ztest([lneg, eneg], [ln, en], alternative="two-sided")
        p = float(p)
        if p < ALPHA:
            verdict = "rose" if lneg * en > eneg * ln else "fell"
    return sentiment_shares(conn, start, end, region) | {
        "buckets": {m: _shares(buckets[m]) for m in months},
        "latest": {"month": latest, "comments": ln, "negative": lneg, "share": rate(lneg, ln)},
        "earlier": {
            "months": [earlier[0], earlier[-1]] if earlier else [],
            "comments": en,
            "negative": eneg,
            "share": rate(eneg, en),
        },
        "p_value": p,
        "verdict": verdict,
    }


def g04(conn: Conn) -> dict:
    return {
        "dateless_default": sentiment_shares(conn, D("2026-07-01"), D("2026-07-31"), "southeast"),
        "six_month_window": sentiment_shares(conn, D("2026-03-01"), D("2026-08-30"), "southeast"),
    }


def g05(conn: Conn) -> dict:
    return {
        "weekend_2026_08_22": sentiment_shares(conn, D("2026-08-22"), D("2026-08-23")),
        "weekend_2026_08_29": sentiment_shares(conn, D("2026-08-29"), D("2026-08-30")),
    }


def g20(conn: Conn) -> dict:
    return sentiment_shares(conn, D("2026-04-01"), D("2026-06-30"), "southeast")


def g21(conn: Conn) -> dict:
    return sentiment_trend(conn, D("2026-03-01"), D("2026-08-30"), "northeast")


def g22(conn: Conn) -> dict:
    """June 2026, all regions: the mixed comments any of which may be quoted (at most 3)."""
    rows = _labels(conn, D("2026-06-01"), D("2026-06-30"))
    mixed = sorted(r[3] for r in rows if r[1] == "mixed")
    return _range(D("2026-06-01"), D("2026-06-30")) | {
        "mixed_comments": len(mixed),
        "examples_expected": min(3, len(mixed)),
        "eligible_feedback_ids": mixed,
    }


# =========================================================================== forecast


def _manifest() -> tuple[dict, str]:
    raw = FORECAST_MANIFEST.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def _band(h: int) -> str:
    return "1-4" if h <= 4 else "5-13" if h <= 13 else "14-26"


def forecast_weeks(slice_: str, h_from: int, h_to: int) -> dict:
    """Weeks `h_from`..`h_to` after the last training week (week 1 starts 2026-08-31).
    Numbers only for served slice-bands (ADR-071); every band with its shown error."""
    import numpy as np
    from forecast_runtime import N_WEEKS, forecast_record, load, week_start, year_end_indicator

    manifest, sha = _manifest()
    record = load(FORECAST_DIR, manifest)[slice_]
    serving = manifest["serving"]["slices"][slice_]
    t = np.arange(N_WEEKS + h_from - 1, N_WEEKS + h_to)
    fc = forecast_record(record, t)
    year_end = year_end_indicator(t)
    weeks = []
    for i, w in enumerate(t):
        h = int(w - N_WEEKS + 1)
        band = serving[_band(h)]
        entry = {
            "week_start": week_start(int(w)).isoformat(),
            "horizon": h,
            "band": _band(h),
            "served": band["served"],
            "shown_error_pct": round(band["shown_error"], 1),
            "year_end": bool(year_end[i]),
        }
        if band["served"]:
            entry |= {
                "point": float(fc["median"][i]),
                "lo80": float(fc["lo80"][i]),
                "hi80": float(fc["hi80"][i]),
                "point_rounded": round(float(fc["median"][i])),
            }
        weeks.append(entry)
    served = [w for w in weeks if w["served"]]
    return {
        "slice": slice_,
        "horizons": [h_from, h_to],
        "manifest_sha256": sha,
        "weeks": weeks,
        "served_weeks": len(served),
        "withheld_weeks": len(weeks) - len(served),
        "served_total": sum(w["point"] for w in served) if served else None,
        "served_total_rounded": round(sum(w["point"] for w in served)) if served else None,
        "bands_shown_error_pct": {
            b: round(serving[b]["shown_error"], 1) for b in sorted({w["band"] for w in weeks})
        },
    }


def g07(conn: Conn | None = None) -> dict:
    return forecast_weeks("total", 1, 26)


def g10(conn: Conn | None = None) -> dict:
    return forecast_weeks("install", 2, 5)  # September 2026: Mondays 09-07 to 09-28


def g25(conn: Conn | None = None) -> dict:
    return forecast_weeks("total", 1, 6)


def g26(conn: Conn | None = None) -> dict:
    return forecast_weeks("repair", 6, 9)  # October 2026: Mondays 10-05 to 10-26


def g27(conn: Conn | None = None) -> dict:
    return forecast_weeks("maintenance", 2, 5)


ORACLES: dict[str, Callable[..., dict]] = {
    f.__name__: f
    for f in (
        g01, g02, g03, g04, g05, g07, g10, g11, g12, g13, g14, g15, g16, g17, g18,
        g20, g21, g22, g25, g26, g27, g35,
    )
}  # fmt: skip
