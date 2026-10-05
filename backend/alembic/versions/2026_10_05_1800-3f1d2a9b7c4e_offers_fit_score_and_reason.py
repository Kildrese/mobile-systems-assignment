"""Offers: fit score and reason

Revision ID: 3f1d2a9b7c4e
Revises: 5b5a53500c3a
Create Date: 2026-10-05 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3f1d2a9b7c4e"
down_revision: str | Sequence[str] | None = "5b5a53500c3a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("internship_offers", sa.Column("fit_score", sa.Integer(), nullable=True))
    op.add_column("internship_offers", sa.Column("fit_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("internship_offers", "fit_reason")
    op.drop_column("internship_offers", "fit_score")
