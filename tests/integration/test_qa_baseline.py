"""The baseline measurement (ADR-087) equals a plain count over the stored predictions.

The measurement script counts in SQL; this recounts in Python from the same rows, so the SQL's
reading of "clear contradiction" and "covered" is checked independently.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest
from db_models.access_matrix import ROLE_EVAL

pytestmark = pytest.mark.integration

MEASURE = Path(__file__).resolve().parents[2] / "evals" / "qa_baseline" / "measure.py"


def _load():
    spec = importlib.util.spec_from_file_location("qa_baseline_measure", MEASURE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_measurement_equals_a_python_recount(loaded_database, connect_as):
    measure = _load()
    version = hashlib.sha256(measure.MANIFEST.read_bytes()).hexdigest()
    conn = connect_as(ROLE_EVAL)
    scored = conn.execute(
        "SELECT count(*) FROM sentiment_predictions WHERE model_version = %s", (version,)
    ).fetchone()[0]
    if scored == 0:
        pytest.skip("no stored bert_v1 predictions (CI's database holds none)")
    rows = conn.execute(
        """SELECT p.predicted_label, f.rating, l.region
           FROM sentiment_predictions p
           JOIN service_feedback f ON f.feedback_id = p.feedback_id
           JOIN service_requests r ON r.request_id = f.request_id
           JOIN locations l ON l.location_id = r.location_id
           WHERE p.model_version = %s""",
        (version,),
    ).fetchall()
    covered = [
        (label, stars, region)
        for label, stars, region in rows
        if stars is not None and label in ("positive", "negative")
    ]

    def contradicts(label, stars):
        return (label == "positive" and stars <= 2) or (label == "negative" and stars >= 4)

    result = measure.measure(conn, version)
    assert result["n"] == len(covered)
    assert result["x"] == sum(contradicts(label, stars) for label, stars, _ in covered)
    assert result["p0"] == max(result["p_hat"], 0.01)
    for region, entry in result["per_region"].items():
        sub = [(label, stars) for label, stars, r in covered if r == region]
        assert (entry["n"], entry["x"]) == (len(sub), sum(contradicts(*s) for s in sub))
