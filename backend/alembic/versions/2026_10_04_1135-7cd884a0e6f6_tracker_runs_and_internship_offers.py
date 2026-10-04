"""Tracker runs and internship offers

Revision ID: 7cd884a0e6f6
Revises: 67ef80013e69
Create Date: 2026-10-04 11:35:35.323998

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7cd884a0e6f6"
down_revision: str | Sequence[str] | None = "67ef80013e69"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tracker_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("topic", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("stop_reason", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("report_markdown", sa.Text(), nullable=False),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("tracker_runs_pkey")),
    )
    op.create_index(
        op.f("tracker_runs_started_at_idx"), "tracker_runs", ["started_at"], unique=False
    )
    op.create_table(
        "internship_offers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("opportunity_id", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("top_k", sa.Boolean(), nullable=False),
        sa.Column("company", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("role_type", sa.String(), nullable=False),
        sa.Column("term", sa.String(), nullable=False),
        sa.Column("locations", sa.ARRAY(sa.String()), nullable=False),
        sa.Column("remote", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("compensation", sa.String(), nullable=True),
        sa.Column("deadline", sa.String(), nullable=True),
        sa.Column("work_authorization_quote", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("status_evidence", sa.Text(), nullable=True),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["tracker_runs.id"],
            name=op.f("internship_offers_run_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("internship_offers_pkey")),
        sa.UniqueConstraint("run_id", "opportunity_id", name=op.f("internship_offers_run_id_key")),
    )


def downgrade() -> None:
    op.drop_table("internship_offers")
    op.drop_index(op.f("tracker_runs_started_at_idx"), table_name="tracker_runs")
    op.drop_table("tracker_runs")
