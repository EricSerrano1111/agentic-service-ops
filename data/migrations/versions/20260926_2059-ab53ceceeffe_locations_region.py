"""locations.region: the customer site's region (ADR-051)

Adds `locations.region` with a CHECK on the four region names. The column is nullable
and this migration fills nothing. The state-to-region mapping lives once, in
`data/generator/parameters.py`: filling from a literal copy here would be a second copy,
and filling from `generation_parameters` would make the migration read live data
(ADR-027). The generator writes `region` on every row. On a database loaded before this
migration, rerun `data/generator/load.py`; `validate.py` checks every location's region.

**Frozen.** Carries its value set as literal data rather than importing `db_models`
(ADR-027).

Revision ID: ab53ceceeffe
Revises: 9135d8de9f27
Create Date: 2026-09-26 20:59

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ab53ceceeffe"
down_revision: str | None = "9135d8de9f27"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# --------------------------------------------------------------------------- #
# Frozen — do not edit. The value set this migration applies, as literal data.
# --------------------------------------------------------------------------- #

_TABLE = "locations"
_CHECK = "ck_locations_region"
_REGIONS: tuple[str, ...] = ("northeast", "southeast", "central", "west")


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column("region", sa.String(length=32), nullable=True))
    op.create_check_constraint(
        _CHECK, _TABLE, "region IN (" + ", ".join(f"'{r}'" for r in _REGIONS) + ")"
    )


def downgrade() -> None:
    op.drop_constraint(_CHECK, _TABLE, type_="check")
    op.drop_column(_TABLE, "region")
