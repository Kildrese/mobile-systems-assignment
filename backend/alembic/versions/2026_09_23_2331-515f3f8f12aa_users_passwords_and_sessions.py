"""Drop the Better Auth tables; create users, passwords and sessions

Revision ID: 515f3f8f12aa
Revises:
Create Date: 2026-09-23 23:31:21.432845

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "515f3f8f12aa"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The Better Auth and Drizzle schema this replaces. Its data is dropped on
    # purpose (see the split-fastapi-vite change); on a fresh database these
    # are no-ops.
    for table in ("verification", "account", "session", "user", "notes"):
        op.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
    op.execute("DROP SCHEMA IF EXISTS drizzle CASCADE")

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("first_name", sa.String(), nullable=False),
        sa.Column("last_name", sa.String(), server_default="", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("users_pkey")),
        sa.UniqueConstraint("email", name=op.f("users_email_key")),
        sa.UniqueConstraint("username", name=op.f("users_username_key")),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("sessions_user_id_fkey"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("sessions_pkey")),
        sa.UniqueConstraint("token_hash", name=op.f("sessions_token_hash_key")),
    )
    op.create_index(op.f("sessions_user_id_idx"), "sessions", ["user_id"], unique=False)
    op.create_table(
        "user_passwords",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("hash", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("user_passwords_user_id_fkey"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("user_passwords_pkey")),
    )


def downgrade() -> None:
    # One-way for the old schema: this only removes the new tables. Rolling
    # back means restoring the database from a snapshot.
    op.drop_table("user_passwords")
    op.drop_index(op.f("sessions_user_id_idx"), table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("users")
