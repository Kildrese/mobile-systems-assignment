"""Tracker dispatches: one cron dispatch per UTC day

Revision ID: 2b865387575a
Revises: 3f1d2a9b7c4e
Create Date: 2026-10-06 10:54:17.959382

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2b865387575a"
down_revision: str | Sequence[str] | None = "3f1d2a9b7c4e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tracker_dispatches",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status in ('claimed', 'dispatched', 'failed')",
            name=op.f("tracker_dispatches_status_check"),
        ),
        sa.PrimaryKeyConstraint("day", name=op.f("tracker_dispatches_pkey")),
    )


def downgrade() -> None:
    op.drop_table("tracker_dispatches")
