"""sentiment_labels: hard_case_type replaces is_sarcastic; corpus_id added

A boolean `is_sarcastic` can represent only one kind of hard case, and ADR-036 defines
two (`sarcastic`, `implicit`). It is replaced by `hard_case_type`, a VARCHAR + CHECK
vocabulary column (`none`, `sarcastic`, `implicit`). `corpus_id` records which corpus
comment (`data/generator/corpus/feedback_text.jsonl`) supplied the row's feedback text,
and its UNIQUE constraint enforces ADR-030's no-reuse rule in the database. See ADR-037.

**Frozen.** Like every migration from here on (ADR-027), this carries its definitions as
literals rather than importing `db_models`. A later change to the vocabulary is a new
migration, not an edit to this one.

**Downgrade is lossy for `implicit`.** It restores `is_sarcastic` as
`hard_case_type = 'sarcastic'`, so `implicit` rows come back as `false`, i.e. as easy
cases. There is no boolean that can carry the distinction; that is why this migration
exists.

No grant change: `sentiment_labels` grants are table-level (`app_qa` SELECT,
`app_generator` ALL), so both new columns are covered and no agent role gains anything.

Revision ID: 4c6589542b27
Revises: fae4b8c9814c
Create Date: 2026-09-23 21:43

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4c6589542b27"
down_revision: str | None = "fae4b8c9814c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# --------------------------------------------------------------------------- #
# Frozen — do not edit. The definitions this migration applies, as literal data.
# --------------------------------------------------------------------------- #

_TABLE = "sentiment_labels"
_HARD_CASE_CHECK = "ck_sentiment_labels_hard_case_type"
_HARD_CASE_VALUES: tuple[str, ...] = ("none", "sarcastic", "implicit")
_CORPUS_ID_UNIQUE = "uq_sentiment_labels_corpus_id"
_VOCAB_LEN = 32
_CORPUS_ID_LEN = 32


def upgrade() -> None:
    # hard_case_type: add nullable, backfill from is_sarcastic, then tighten. The table
    # is empty today, but the backfill keeps the upgrade correct if it ever is not.
    op.add_column(_TABLE, sa.Column("hard_case_type", sa.String(length=_VOCAB_LEN)))
    op.execute(
        f"UPDATE {_TABLE} SET hard_case_type = "
        "CASE WHEN is_sarcastic THEN 'sarcastic' ELSE 'none' END"
    )
    op.alter_column(_TABLE, "hard_case_type", nullable=False)
    rendered = ", ".join(f"'{v}'" for v in _HARD_CASE_VALUES)
    op.create_check_constraint(_HARD_CASE_CHECK, _TABLE, f"hard_case_type IN ({rendered})")

    # corpus_id: NOT NULL with no default, added directly. That only works because the
    # table is empty (nothing is generated before the corpus exists); on a populated
    # table this step would need a backfill first, and would fail loudly without one.
    op.add_column(
        _TABLE,
        sa.Column("corpus_id", sa.String(length=_CORPUS_ID_LEN), nullable=False),
    )
    op.create_unique_constraint(_CORPUS_ID_UNIQUE, _TABLE, ["corpus_id"])

    op.drop_column(_TABLE, "is_sarcastic")


def downgrade() -> None:
    # Restore is_sarcastic exactly as the initial migration created it (BOOLEAN NOT NULL
    # DEFAULT false), then map back. Lossy: implicit -> false. See the module docstring.
    op.add_column(
        _TABLE,
        sa.Column("is_sarcastic", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.execute(f"UPDATE {_TABLE} SET is_sarcastic = (hard_case_type = 'sarcastic')")

    op.drop_constraint(_CORPUS_ID_UNIQUE, _TABLE, type_="unique")
    op.drop_column(_TABLE, "corpus_id")

    op.drop_constraint(_HARD_CASE_CHECK, _TABLE, type_="check")
    op.drop_column(_TABLE, "hard_case_type")
