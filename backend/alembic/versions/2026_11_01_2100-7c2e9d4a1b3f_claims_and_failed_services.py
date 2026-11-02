"""Offers: claims and verdicts; runs: failed services

Revision ID: 7c2e9d4a1b3f
Revises: 2b865387575a
Create Date: 2026-11-01 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "7c2e9d4a1b3f"
down_revision: str | Sequence[str] | None = "2b865387575a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "internship_offers",
        sa.Column(
            "claims",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "tracker_runs",
        sa.Column(
            "failed_services",
            sa.ARRAY(sa.String()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("tracker_runs", "failed_services")
    op.drop_column("internship_offers", "claims")
