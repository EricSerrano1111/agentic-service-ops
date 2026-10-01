"""The SQL behind `Store`, as `app_sentiment`: fixed statements, bound parameters only.

SQLAlchemy Core over the `db_models` tables. It reads only columns inside
`app_sentiment`'s grants (data dictionary §7): `service_feedback` (`feedback_id`,
`request_id`, `submitted_at`, `feedback_text`), `service_requests` (`request_id`,
`location_id`), `locations` (`location_id`, `region`), and `sentiment_predictions`; and
it writes only `INSERT ... ON CONFLICT DO NOTHING` into `sentiment_predictions`.

A comment is a `service_feedback` row with text, dated by `submitted_at` in UTC days.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

from db_models import Location, SentimentPrediction, ServiceFeedback, ServiceRequest
from sqlalchemy import Engine, and_, create_engine, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import URL

from .classifier import Prediction
from .config import Settings
from .scoring import CountRow, ExampleRow, Scope

_f = ServiceFeedback.__table__
_r = ServiceRequest.__table__
_l = Location.__table__
_p = SentimentPrediction.__table__
_PLACES = Decimal("0.0001")
_BUCKET_FORMAT = {"month": "YYYY-MM", "quarter": 'YYYY-"Q"Q'}


def make_engine(settings: Settings) -> Engine:
    url = URL.create(
        "postgresql+psycopg",
        username=settings.db_user,
        password=settings.db_password,
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
    )
    return create_engine(
        url,
        pool_size=2,
        max_overflow=2,
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": settings.connect_timeout_s,
            "options": f"-c statement_timeout={settings.statement_timeout_ms}",
            "application_name": "mcp_feedback",
        },
    )


def _in_scope(scope: Scope):
    conditions = [
        _f.c.submitted_at >= scope.lo,
        _f.c.submitted_at < scope.hi,
        _f.c.feedback_text.is_not(None),
    ]
    if scope.region is not None:
        conditions.append(_l.c.region == scope.region)
    return and_(*conditions)


def _feedback_with_region():
    return _f.join(_r, _r.c.request_id == _f.c.request_id).join(
        _l, _l.c.location_id == _r.c.location_id
    )


def _with_prediction(version: str):
    return _feedback_with_region().join(
        _p, and_(_p.c.feedback_id == _f.c.feedback_id, _p.c.model_version == version)
    )


def _confidence(value: float) -> Decimal:
    return Decimal(repr(value)).quantize(_PLACES, rounding=ROUND_HALF_UP)


class SqlStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def ping(self) -> None:
        with self.engine.connect() as conn:
            conn.execute(select(1))

    def count_comments(self, scope: Scope) -> int:
        q = select(func.count()).select_from(_feedback_with_region()).where(_in_scope(scope))
        with self.engine.connect() as conn:
            return int(conn.execute(q).scalar_one())

    def count_scored(self, version: str, scope: Scope) -> int:
        q = select(func.count()).select_from(_with_prediction(version)).where(_in_scope(scope))
        with self.engine.connect() as conn:
            return int(conn.execute(q).scalar_one())

    def unscored(self, version: str, scope: Scope, limit: int) -> list[tuple[int, str]]:
        has_prediction = (
            select(_p.c.feedback_id)
            .where(_p.c.feedback_id == _f.c.feedback_id, _p.c.model_version == version)
            .exists()
        )
        q = (
            select(_f.c.feedback_id, _f.c.feedback_text)
            .select_from(_feedback_with_region())
            .where(_in_scope(scope), ~has_prediction)
            .order_by(_f.c.submitted_at, _f.c.feedback_id)
            .limit(limit)
        )
        with self.engine.connect() as conn:
            return [(int(fid), text) for fid, text in conn.execute(q)]

    def insert(self, version: str, rows: Sequence[tuple[int, Prediction]]) -> int:
        if not rows:
            return 0
        stmt = (
            insert(_p)
            .values(
                [
                    {
                        "feedback_id": fid,
                        "model_version": version,
                        "predicted_label": p.label,
                        "confidence": _confidence(p.confidence),
                        "flagged": p.flagged,
                    }
                    for fid, p in rows
                ]
            )
            .on_conflict_do_nothing(index_elements=["feedback_id", "model_version"])
            # Count what was inserted from the returned rows: a multi-row INSERT's
            # rowcount comes back as -1 through SQLAlchemy and psycopg.
            .returning(_p.c.feedback_id)
        )
        with self.engine.begin() as conn:
            return len(conn.execute(stmt).fetchall())

    def label_bucket_counts(self, version: str, scope: Scope, bucket: str) -> list[CountRow]:
        b = func.to_char(func.timezone("UTC", _f.c.submitted_at), _BUCKET_FORMAT[bucket])
        q = (
            select(
                _p.c.predicted_label,
                b.label("bucket"),
                func.count().label("n"),
                func.count().filter(_p.c.flagged).label("flagged"),
            )
            .select_from(_with_prediction(version))
            .where(_in_scope(scope))
            .group_by(_p.c.predicted_label, b)
        )
        with self.engine.connect() as conn:
            return [CountRow(lab, bk, int(n), int(fl)) for lab, bk, n, fl in conn.execute(q)]

    def examples(
        self, version: str, scope: Scope, label: str | None, flagged_only: bool, limit: int
    ) -> list[ExampleRow]:
        conditions = [_in_scope(scope)]
        if label is not None:
            conditions.append(_p.c.predicted_label == label)
        if flagged_only:
            conditions.append(_p.c.flagged.is_(True))
            order = (_p.c.confidence.asc(), _f.c.feedback_id.asc())
        else:
            order = (_p.c.confidence.desc(), _f.c.feedback_id.asc())
        q = (
            select(
                _f.c.feedback_id,
                _f.c.submitted_at,
                _l.c.region,
                _p.c.predicted_label,
                _p.c.confidence,
                _p.c.flagged,
                _f.c.feedback_text,
            )
            .select_from(_with_prediction(version))
            .where(*conditions)
            .order_by(*order)
            .limit(limit)
        )
        with self.engine.connect() as conn:
            return [
                ExampleRow(int(fid), at, region, lab, float(conf), bool(fl), text)
                for fid, at, region, lab, conf, fl, text in conn.execute(q)
            ]
