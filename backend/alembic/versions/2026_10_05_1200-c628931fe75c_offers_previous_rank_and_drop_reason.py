"""Offers: previous rank and drop reason; closed rows become dropped

Revision ID: c628931fe75c
Revises: 7cd884a0e6f6
Create Date: 2026-10-05 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c628931fe75c"
down_revision: str | Sequence[str] | None = "7cd884a0e6f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("internship_offers", sa.Column("previous_rank", sa.Integer(), nullable=True))
    op.add_column("internship_offers", sa.Column("drop_reason", sa.String(), nullable=True))
    # So /latest never returns a section the page doesn't know.
    op.execute(
        "UPDATE internship_offers SET section = 'dropped', drop_reason = 'closed' "
        "WHERE section = 'closed'"
    )


def downgrade() -> None:
    # Outranked rows were open; top_k rows were still open.
    op.execute(
        "UPDATE internship_offers SET section = CASE WHEN drop_reason = 'closed' "
        "THEN 'closed' ELSE 'open' END WHERE section IN ('dropped', 'top_k')"
    )
    op.drop_column("internship_offers", "drop_reason")
    op.drop_column("internship_offers", "previous_rank")
