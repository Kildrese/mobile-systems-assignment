"""Drop users.email

Revision ID: 67ef80013e69
Revises: 515f3f8f12aa
Create Date: 2026-09-24 11:08:40.572340

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "67ef80013e69"
down_revision: str | Sequence[str] | None = "515f3f8f12aa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The stored addresses are deleted on purpose (see the remove-email change).
    op.drop_constraint(op.f("users_email_key"), "users", type_="unique")
    op.drop_column("users", "email")


def downgrade() -> None:
    # Restores the column only, empty: the dropped addresses can't be brought
    # back. Rolling back the data means restoring the database from a snapshot.
    op.add_column("users", sa.Column("email", sa.String(), nullable=True))
    op.create_unique_constraint(op.f("users_email_key"), "users", ["email"])
