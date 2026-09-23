"""Ground-truth tables — `docs/data-dictionary.md` §4.

Generator and eval only; not part of the operational schema. Only `app_qa` (read) and
`app_generator` (write) hold grants here. In particular the sentiment agent must have
no code path — and, more importantly, no privilege — that reaches
`sentiment_labels`, or its verification becomes circular.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, tz_timestamp
from .enums import VOCAB_LEN, HardCaseType, ParamGroup, TrueSentiment, check_in

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
    __table_args__ = (
        check_in("sentiment_labels", "true_sentiment", TrueSentiment),
        check_in("sentiment_labels", "hard_case_type", HardCaseType),
    )

    feedback_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("service_feedback.feedback_id"), primary_key=True
    )
    true_sentiment: Mapped[str] = mapped_column(String(VOCAB_LEN), nullable=False)
    #: §4 leaves precision unstated and calls it optional. Numeric(4, 3) covers
    #: 0.000–1.000 exactly, and NULL means "no deliberate ambiguity assigned".
    label_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    #: Which kind of deliberately hard case this is (~15% of feedback, ADR-019), or
    #: `none`, so failure analysis can report accuracy per type (ADR-036, ADR-037).
    hard_case_type: Mapped[str] = mapped_column(String(VOCAB_LEN), nullable=False)
    #: ID of the corpus comment that supplied this row's `feedback_text`
    #: (`data/generator/corpus/feedback_text.jsonl`). UNIQUE enforces ADR-030's
    #: no-reuse rule: one comment can never back two feedback rows (ADR-037).
    #: Not a vocabulary, despite sharing VOCAB_LEN's width.
    corpus_id: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)

    feedback: Mapped[ServiceFeedback] = relationship(back_populates="sentiment_label")
