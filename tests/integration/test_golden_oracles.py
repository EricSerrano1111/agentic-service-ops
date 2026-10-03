"""Three golden-set oracle results checked by hand, one per agent (ADR-074).

Each check recomputes the figure a different way from the oracle: raw rows counted in
Python rather than a SQL aggregate, or the forecast's arithmetic written out term by term
rather than through `forecast_runtime`. The pinned numbers were hand-counted on
2026-10-02 against the loaded database; CI loads the same deterministic data.

The sentiment check needs the stored `bert_v1` predictions, which CI's database doesn't
hold (no model runs in CI), and the forecast check needs the `volume_v2` artifact, which is
gitignored (`/models/`, ADR-062): each skips where its input is absent, as the volume tests
do, and both run on the development machine.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "evals" / "golden"))

import oracles  # noqa: E402

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def conn(live_database):
    """`app_eval`, from the same environment variables the rest of the suite uses."""
    c = oracles.connect()
    yield c
    c.close()


def _july(ts: dt.datetime) -> bool:
    ts = ts.astimezone(dt.UTC)
    return ts.year == 2026 and ts.month == 7


def test_reporting_g14_incidents_by_severity_by_hand(conn, loaded_database):
    """G14: July 2026 incidents by severity, from every incident row, counted in Python."""
    rows = conn.execute("SELECT reported_at, severity::text FROM incidents").fetchall()
    july = [sev for ts, sev in rows if _july(ts)]
    by_hand = {s: july.count(s) for s in ("high", "medium", "low")}
    assert by_hand == {"high": 6, "medium": 12, "low": 36}  # hand count, 2026-10-02
    got = oracles.g14(conn)
    assert got["by_severity"] == by_hand and got["incident_count"] == 54 == len(july)


def test_sentiment_g05_weekend_shares_by_hand(conn, loaded_database):
    """G05: the 2026-08-29/30 weekend, every comment listed and counted."""
    stored = conn.execute(
        "SELECT count(*) FROM sentiment_predictions WHERE model_version = %s",
        (oracles.SENTIMENT_MODEL_VERSION,),
    ).fetchone()[0]
    if stored == 0:
        pytest.skip("no stored bert_v1 predictions (CI's database holds none)")
    comments = conn.execute(
        """SELECT feedback_id, submitted_at FROM service_feedback
           WHERE submitted_at >= '2026-08-29T00:00:00Z'"""
    ).fetchall()
    weekend = {fid for fid, ts in comments if ts.astimezone(dt.UTC).date() <= dt.date(2026, 8, 30)}
    labels = dict(
        conn.execute(
            "SELECT feedback_id, predicted_label::text FROM sentiment_predictions "
            "WHERE model_version = %s",
            (oracles.SENTIMENT_MODEL_VERSION,),
        ).fetchall()
    )
    listed = sorted(labels[f] for f in weekend)
    # Hand count, 2026-10-02: 7 comments, 5 positive, 1 neutral, 1 negative, 0 mixed.
    assert listed == [
        "negative",
        "neutral",
        "positive",
        "positive",
        "positive",
        "positive",
        "positive",
    ]
    got = oracles.g05(conn)["weekend_2026_08_29"]
    assert got["comments"] == 7
    assert got["counts"] == {"positive": 5, "neutral": 1, "negative": 1, "mixed": 0}
    assert got["shares"]["positive"] == "0.7143"  # 5/7 = 0.714285..., half-up to 4 places


@pytest.mark.skipif(
    not oracles.FORECAST_DIR.exists(), reason="volume_v2 artifact not present (gitignored)"
)
def test_forecast_g25_week_one_by_hand():
    """G25 week 1 (2026-08-31, t = 156): the total slice's median and 80% range written out
    from the stored coefficients, without `forecast_runtime`; and the bands' served flags
    and shown errors read straight from the manifest."""
    rec = json.loads((oracles.FORECAST_DIR / "total.json").read_text(encoding="utf-8"))
    assert (rec["k"], rec["year_end"], rec["last_t"]) == (2, True, 155)
    t, p = 156, 52.1775
    # 1, t, year-end (0: the week of 2026-08-31 holds neither Dec 25 nor Jan 1),
    # sin/cos(2*pi*j*t/p) for j = 1, 2.
    x = [1.0, float(t), 0.0]
    for j in (1, 2):
        a = 2 * math.pi * j * t / p
        x += [math.sin(a), math.cos(a)]
    mu = sum(xi * bi for xi, bi in zip(x, rec["params"], strict=True))
    v = rec["xtwx_inv"]
    h = sum(x[i] * v[i][j] * x[j] for i in range(7) for j in range(7))
    se = rec["scale"] * math.sqrt(1 + h)
    z80 = 1.2815515655446004
    week = oracles.g25()["weeks"][0]
    assert week["week_start"] == "2026-08-31" and week["horizon"] == 1
    assert week["point"] == pytest.approx(math.exp(mu), rel=1e-9)
    assert week["lo80"] == pytest.approx(math.exp(mu - z80 * se), rel=1e-9)
    assert week["hi80"] == pytest.approx(math.exp(mu + z80 * se), rel=1e-9)
    assert week["point_rounded"] == 151  # hand computation, 2026-10-02: 150.87
    serving = json.loads(oracles.FORECAST_MANIFEST.read_text(encoding="utf-8"))["serving"]
    total = serving["slices"]["total"]
    assert total["1-4"]["served"] and total["5-13"]["served"]
    assert (
        oracles.g25()["bands_shown_error_pct"]
        == {
            "1-4": round(total["1-4"]["shown_error"], 1),
            "5-13": round(total["5-13"]["shown_error"], 1),
        }
        == {"1-4": 13.6, "5-13": 5.5}
    )
