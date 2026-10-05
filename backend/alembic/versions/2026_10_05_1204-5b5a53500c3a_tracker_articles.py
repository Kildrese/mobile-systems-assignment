"""Tracker articles: every document a run tried to read

Revision ID: 5b5a53500c3a
Revises: c628931fe75c
Create Date: 2026-10-05 12:04:02.628593

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5b5a53500c3a"
down_revision: str | Sequence[str] | None = "c628931fe75c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tracker_articles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("stage", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["tracker_runs.id"],
            name=op.f("tracker_articles_run_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("tracker_articles_pkey")),
    )
    op.create_index(
        op.f("tracker_articles_run_id_idx"), "tracker_articles", ["run_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("tracker_articles_run_id_idx"), table_name="tracker_articles")
    op.drop_table("tracker_articles")
