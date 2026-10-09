"""Measure the sentiment rating cross-check's baseline rate (ADR-087). No model calls.

    .venv\\Scripts\\python evals/qa_baseline/measure.py [--date 2026-10-09]

Reads as `app_eval` (the offline evaluation role) the stored `bert_v1` predictions joined to the
star rating, over the full data window, and reports:

  n   covered comments: rated, predicted `positive` or `negative`
  x   clear contradictions: `positive` on 1 to 2 stars, or `negative` on 4 to 5 stars
  p_hat = x / n, and p0 = max(p_hat, 0.01) (the floor is the owner's judgement, ADR-087)

and the same per region, for information only (the rule uses the overall rate). Neutral, mixed,
3-star and unrated comments are excluded. The measurement is made once; the rule it feeds
(`common.stats.rating_cross_check`) is fixed in ADR-087 and never changed after a result.
Writes evals/results/qa_baseline/<date>/baseline.json. Prints counts only, never comment text.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "ml" / "sentiment" / "artifacts" / "bert_v1.manifest.json"

CONTRADICTION = (
    "((p.predicted_label = 'positive' AND f.rating <= 2) "
    "OR (p.predicted_label = 'negative' AND f.rating >= 4))"
)
COVERED = "f.rating IS NOT NULL AND p.predicted_label IN ('positive', 'negative')"

OVERALL_SQL = f"""
    SELECT count(*) FILTER (WHERE {CONTRADICTION}), count(*)
    FROM sentiment_predictions p JOIN service_feedback f ON f.feedback_id = p.feedback_id
    WHERE p.model_version = %(mv)s AND {COVERED}
"""
REGION_SQL = f"""
    SELECT l.region, count(*) FILTER (WHERE {CONTRADICTION}), count(*)
    FROM sentiment_predictions p
    JOIN service_feedback f ON f.feedback_id = p.feedback_id
    JOIN service_requests r ON r.request_id = f.request_id
    JOIN locations l ON l.location_id = r.location_id
    WHERE p.model_version = %(mv)s AND {COVERED}
    GROUP BY l.region ORDER BY l.region
"""
COVERAGE_SQL = """
    SELECT (SELECT count(*) FROM service_feedback),
           (SELECT count(*) FROM sentiment_predictions WHERE model_version = %(mv)s),
           (SELECT count(*) FROM service_feedback WHERE rating IS NULL),
           (SELECT count(*) FROM sentiment_predictions p JOIN service_feedback f
              ON f.feedback_id = p.feedback_id
            WHERE p.model_version = %(mv)s AND f.rating IS NOT NULL
              AND p.predicted_label NOT IN ('positive', 'negative'))
"""


def rate(x: int, n: int) -> float | None:
    return None if n == 0 else x / n


def measure(conn, model_version: str) -> dict:
    from common.stats import ALPHA, MIN_COVERED, P0_FLOOR, p0_for

    params = {"mv": model_version}
    ((x, n),) = conn.execute(OVERALL_SQL, params).fetchall()
    comments, scored, unrated, excluded_labels = conn.execute(COVERAGE_SQL, params).fetchone()
    p_hat = rate(x, n)
    if p_hat is None:
        raise SystemExit("no covered comments: are the bert_v1 predictions stored?")
    regions = {
        region: {"n": int(rn), "x": int(rx), "p_hat": rate(rx, rn)}
        for region, rx, rn in conn.execute(REGION_SQL, params)
    }
    return {
        "evidence": "observed",
        "model_version": model_version,
        "role": os.environ.get("DB_ROLE_EVAL_USER", "app_eval"),
        "n": int(n),
        "x": int(x),
        "p_hat": p_hat,
        "p0": p0_for(p_hat),
        "rule": {"p0_floor": P0_FLOOR, "alpha": ALPHA, "min_covered": MIN_COVERED},
        "per_region": regions,
        "coverage": {
            "comments": int(comments),
            "scored_with_this_model_version": int(scored),
            "unrated": int(unrated),
            "rated_but_neutral_or_mixed": int(excluded_labels),
        },
    }


def connect():
    import psycopg
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
    needed = ("POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB")
    missing = [
        v for v in (*needed, "DB_ROLE_EVAL_USER", "DB_ROLE_EVAL_PASSWORD") if not os.environ.get(v)
    ]
    if missing:
        raise SystemExit(f"Missing environment variables: {', '.join(missing)}")
    return psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["DB_ROLE_EVAL_USER"],
        password=os.environ["DB_ROLE_EVAL_PASSWORD"],
        connect_timeout=5,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--date", default=dt.date.today().isoformat())
    args = ap.parse_args(argv)
    model_version = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    with connect() as conn:
        result = measure(conn, model_version)
    out = ROOT / "evals" / "results" / "qa_baseline" / args.date
    out.mkdir(parents=True, exist_ok=True)
    (out / "baseline.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        f"model_version {model_version[:12]}  covered n={result['n']}  "
        f"contradictions x={result['x']}"
    )
    print(f"p_hat = {result['p_hat']:.6f}  ->  p0 = max(p_hat, 0.01) = {result['p0']:.6f}")
    for region, r in result["per_region"].items():
        print(f"  {region:<10} n={r['n']:<5} x={r['x']:<3} p_hat={r['p_hat']:.6f}")
    print(f"coverage: {result['coverage']}")
    print(f"wrote {(out / 'baseline.json').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
