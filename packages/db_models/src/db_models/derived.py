"""Derived operational tables: model output stored for reuse (ADR-067).

`sentiment_predictions` holds what the deployed sentiment model said about each comment,
one row per comment per model version. It is operational and derived, not ground truth:
`sentiment_labels` (§4) is the generator's answer key and is never read at runtime, while
these rows are the model's opinion, written by `mcp_feedback` as `app_sentiment` and read
back to answer questions. QA recomputes answers from them; `app_train` cannot read them,
so the model never trains on its own output.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, tz_timestamp
from .enums import VOCAB_LEN, TrueSentiment, check_in


class SentimentPrediction(Base):
    """One stored prediction: at most one per comment per model version (§8)."""

    __tablename__ = "sentiment_predictions"
    __table_args__ = (
        check_in("sentiment_predictions", "predicted_label", TrueSentiment),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_sentiment_predictions_confidence_range",
        ),
    )

    #: CASCADE: a prediction means nothing without its comment. A regeneration clears
    #: this table in the same TRUNCATE as `service_feedback` (`load.py`), which ON DELETE
    #: rules don't cover.
    feedback_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("service_feedback.feedback_id", ondelete="CASCADE"),
        primary_key=True,
    )
    #: SHA-256 of the committed artifact manifest (`ml/sentiment/artifacts/`), so a new
    #: model or a new T or τ is a new version, never an overwrite.
    model_version: Mapped[str] = mapped_column(String(64), primary_key=True)
    predicted_label: Mapped[str] = mapped_column(String(VOCAB_LEN), nullable=False)
    #: Calibrated probability of the predicted class: softmax(logits / T) (ADR-066).
    confidence: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    #: confidence < τ for this version: routed to human review (ADR-066).
    flagged: Mapped[bool] = mapped_column(Boolean, nullable=False)
    scored_at: Mapped[dt.datetime] = tz_timestamp(server_now=True)
