"""generation_parameters.param_group gains world and feedback

The five original groups (`volume`, `incidents`, `sentiment`, `billing`, `anomalies`)
had no home for global parameters (seed, window, reference counts, regions, request
lifecycle) or for feedback parameters (response rates, channels, corpus sizing), which
were being mislabeled. ADR-038 adds `world` and `feedback`, so the CHECK constraint is
dropped and recreated with seven values.

**Frozen.** Like every migration from here on (ADR-027), this carries its value sets as
literals rather than importing `db_models`.

**Downgrade fails if any row uses `world` or `feedback`.** Recreating the five-value
CHECK validates existing rows, so a downgrade with such rows present errors out instead
of silently leaving rows that violate the restored constraint. That is intended: the
table is empty today, and a downgrade after generation should force a deliberate
decision about those rows.

Revision ID: 9135d8de9f27
Revises: 4c6589542b27
Create Date: 2026-09-23 22:11

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "9135d8de9f27"
down_revision: str | None = "4c6589542b27"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# --------------------------------------------------------------------------- #
# Frozen — do not edit. The value sets this migration applies, as literal data.
# --------------------------------------------------------------------------- #

_TABLE = "generation_parameters"
_CHECK = "ck_generation_parameters_param_group"
_ORIGINAL: tuple[str, ...] = ("volume", "incidents", "sentiment", "billing", "anomalies")
_NEW: tuple[str, ...] = (*_ORIGINAL, "world", "feedback")


def _condition(values: tuple[str, ...]) -> str:
    return "param_group IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.drop_constraint(_CHECK, _TABLE, type_="check")
    op.create_check_constraint(_CHECK, _TABLE, _condition(_NEW))


def downgrade() -> None:
    op.drop_constraint(_CHECK, _TABLE, type_="check")
    op.create_check_constraint(_CHECK, _TABLE, _condition(_ORIGINAL))
