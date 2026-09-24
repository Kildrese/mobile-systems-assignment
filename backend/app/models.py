"""The database schema. Alembic migrations are generated from these models."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, MetaData, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Postgres's own default names, so constraint names are predictable (the
# account service maps unique violations to error codes by name).
NAMING_CONVENTION = {
    "pk": "%(table_name)s_pkey",
    "fk": "%(table_name)s_%(column_0_name)s_fkey",
    "uq": "%(table_name)s_%(column_0_name)s_key",
    "ix": "%(table_name)s_%(column_0_name)s_idx",
    "ck": "%(table_name)s_%(constraint_name)s_check",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(Timestamps, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Lowercased. NULL for users who registered with only a username; unique
    # indexes allow any number of NULLs.
    email: Mapped[str | None] = mapped_column(String, unique=True)
    # Lowercased.
    username: Mapped[str] = mapped_column(String, unique=True)
    first_name: Mapped[str] = mapped_column(String)
    last_name: Mapped[str] = mapped_column(String, server_default="")


class UserPassword(Timestamps, Base):
    """The password hash, kept off `users` so a user query can't select it."""

    __tablename__ = "user_passwords"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(User.id, ondelete="CASCADE"), primary_key=True
    )
    # argon2id, PHC string format.
    hash: Mapped[str] = mapped_column(String)


class Session(Timestamps, Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # SHA-256 (hex) of the bearer token. The token itself is never stored.
    token_hash: Mapped[str] = mapped_column(String, unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(User.id, ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
