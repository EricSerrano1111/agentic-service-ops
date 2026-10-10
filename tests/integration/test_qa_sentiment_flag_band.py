"""The flag check's tolerance band, on both sides (data dictionary §6, "Sentiment answers", rule 5).

A prediction's flag must equal `confidence < τ` on the stored 4-place confidence, strictly, except
within half a rounding step (0.00005) of τ, where either flag is accepted because the flag was
decided before rounding (L-77). The rows are written under a throwaway `model_version` as the
admin role and removed afterwards; needs only the loaded `service_feedback`, so it runs in CI too.
"""

from __future__ import annotations

import os
import uuid

import psycopg
import pytest
from agent_qa.db import FLAG_BAND, PostgresSource, utc_bounds
from schemas import DATASET_WINDOW_END, DATASET_WINDOW_START
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool

pytestmark = [pytest.mark.integration]

TAU = 0.840840745682907  # the committed manifest's threshold


@pytest.fixture
def admin(loaded_database):
    conn = psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_ADMIN_USER"],
        password=os.environ["POSTGRES_ADMIN_PASSWORD"],
        autocommit=True,
    )
    yield conn
    conn.close()


@pytest.fixture
def source(loaded_database):
    engine = create_engine(
        URL.create(
            "postgresql+psycopg",
            username=os.environ["DB_ROLE_QA_USER"],
            password=os.environ["DB_ROLE_QA_PASSWORD"],
            host=os.environ["POSTGRES_HOST"],
            port=int(os.environ["POSTGRES_PORT"]),
            database=os.environ["POSTGRES_DB"],
        ),
        poolclass=NullPool,
    )
    yield PostgresSource(engine)
    engine.dispose()


def inconsistent(admin, source, confidence: str, flagged: bool, tau: float = TAU) -> int:
    version = f"itest-band-{uuid.uuid4().hex}"
    (fid,) = admin.execute("SELECT min(feedback_id) FROM service_feedback").fetchone()
    admin.execute(
        "INSERT INTO sentiment_predictions (feedback_id, model_version, predicted_label,"
        " confidence, flagged) VALUES (%s, %s, 'negative', %s, %s)",
        (fid, version, confidence, flagged),
    )
    try:
        lo, hi = utc_bounds(DATASET_WINDOW_START, DATASET_WINDOW_END)
        return source.sentiment_inconsistent_flags(version, lo, hi, None, tau)
    finally:
        admin.execute("DELETE FROM sentiment_predictions WHERE model_version = %s", (version,))


def test_the_band_is_half_a_rounding_step():
    assert FLAG_BAND == 0.00005


@pytest.mark.parametrize(
    ("confidence", "flagged", "bad"),
    [
        # well below τ: flagged is right, unflagged is wrong
        ("0.8407", True, 0),
        ("0.8407", False, 1),
        # inside the band (|c - τ| = 0.0000407): either flag is accepted
        ("0.8408", True, 0),
        ("0.8408", False, 0),
        # just outside the band above τ (0.0000593): unflagged is right, flagged is wrong
        ("0.8409", False, 0),
        ("0.8409", True, 1),
        # far above τ
        ("0.9999", False, 0),
        ("0.9999", True, 1),
        ("0.5000", True, 0),
        ("0.5000", False, 1),
    ],
)
def test_strict_outside_the_band_and_either_flag_inside_it(admin, source, confidence, flagged, bad):
    assert inconsistent(admin, source, confidence, flagged) == bad


@pytest.mark.parametrize(
    ("tau", "confidence", "flagged", "bad"),
    [
        # exactly half a step away (0.84085 - 0.8408 = 0.00005): inside, either flag accepted
        (0.84085, "0.8408", True, 0),
        (0.84085, "0.8408", False, 0),
        (0.84085, "0.8410", False, 0),
        (0.84085, "0.8410", True, 1),  # 0.00015 above: strict
        # a hair further (0.8407 is 0.00015 below 0.84085): strict
        (0.84085, "0.8407", False, 1),
        (0.84085, "0.8407", True, 0),
        # the other edge, exactly 0.00005 above τ
        (0.84075, "0.8408", False, 0),
        (0.84075, "0.8408", True, 0),
    ],
)
def test_the_band_edge_itself_is_inside(admin, source, tau, confidence, flagged, bad):
    assert inconsistent(admin, source, confidence, flagged, tau) == bad
