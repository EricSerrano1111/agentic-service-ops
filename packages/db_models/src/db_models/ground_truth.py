"""Ground-truth tables — `docs/data-dictionary.md` §4.

Generator and eval only; not part of the operational schema. Only `app_qa` (read) and
`app_generator` (write) hold grants here. In particular the sentiment agent must have
no code path — and, more importantly, no privilege — that reaches
`sentiment_labels`, or its verification becomes circular.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, ForeignKey, Numeric, String, Text, false
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, tz_timestamp
from .enums import VOCAB_LEN, ParamGroup, TrueSentiment, check_in

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .operational import ServiceFeedback


class GenerationParameter(Base):
    """The true parameters used to generate the synthetic dataset.

    Key-value shaped so a new parameter never needs a migration. The random seed is
    persisted here too — without it the dataset is not reproducible, and "can you
    regenerate this?" needs to be answerable with yes.
    """

    __tablename__ = "generation_parameters"
    __table_args__ = (check_in("generation_parameters", "param_group", ParamGroup),)

    param_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    #: §4 offers "JSONB or NUMERIC". JSONB throughout: it holds scalars as well as
    #: the windowed/array cases (e.g. anomaly windows), so one column type covers
    #: every parameter and callers have one decode path instead of two.
    param_value: Mapped[dict | list | float | str | None] = mapped_column(JSONB, nullable=False)
    param_group: Mapped[str] = mapped_column(String(VOCAB_LEN), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[dt.datetime] = tz_timestamp(server_now=True)


class SentimentLabel(Base):
    """Sentiment ground truth, keyed to `service_feedback`.

    Assigned at generation time, before any model sees the text. Exists solely for
    the QA agent and the eval harness.
    """

    __tablename__ = "sentiment_labels"
    __table_args__ = (check_in("sentiment_labels", "true_sentiment", TrueSentiment),)

    feedback_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("service_feedback.feedback_id"), primary_key=True
    )
    true_sentiment: Mapped[str] = mapped_column(String(VOCAB_LEN), nullable=False)
    #: §4 leaves precision unstated and calls it optional. Numeric(4, 3) covers
    #: 0.000–1.000 exactly, and NULL means "no deliberate ambiguity assigned".
    label_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    #: Flags deliberately hard cases (~15% of feedback, ADR-019) so failure analysis
    #: can report easy vs. hard subset accuracy separately.
    is_sarcastic: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())

    feedback: Mapped[ServiceFeedback] = relationship(back_populates="sentiment_label")
