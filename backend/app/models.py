"""The database schema. Alembic migrations are generated from these models."""

import uuid
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
)
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


class TrackerRun(Base):
    """One internship tracker run, published from the tracker's state file by the daily
    job (`python -m app.publish_report`). The API only reads it."""

    __tablename__ = "tracker_runs"

    # The tracker's run id, e.g. `20261004T090000Z-1a2b`.
    id: Mapped[str] = mapped_column(String, primary_key=True)
    topic: Mapped[str] = mapped_column(String)
    # complete, partial or failed.
    status: Mapped[str] = mapped_column(String)
    stop_reason: Mapped[str | None] = mapped_column(String)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    report_markdown: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class InternshipOffer(Base):
    """One opportunity as one run reported it: a snapshot, so every run keeps its own."""

    __tablename__ = "internship_offers"
    __table_args__ = (UniqueConstraint("run_id", "opportunity_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey(TrackerRun.id, ondelete="CASCADE"))
    # The opportunity's id in the tracker's state file; stable across runs.
    opportunity_id: Mapped[int] = mapped_column(Integer)
    # The report section: new (since last run), top_k (still in top K), dropped or open
    # (also open).
    section: Mapped[str] = mapped_column(String)
    rank: Mapped[int | None] = mapped_column(Integer)
    top_k: Mapped[bool] = mapped_column(Boolean)
    # The rank in the last run, if it had one.
    previous_rank: Mapped[int | None] = mapped_column(Integer)
    # Dropped rows only: closed or outranked.
    drop_reason: Mapped[str | None] = mapped_column(String)
    company: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    role_type: Mapped[str] = mapped_column(String)
    term: Mapped[str] = mapped_column(String)
    locations: Mapped[list[str]] = mapped_column(ARRAY(String))
    remote: Mapped[str] = mapped_column(String)
    url: Mapped[str] = mapped_column(String)
    compensation: Mapped[str | None] = mapped_column(String)
    deadline: Mapped[str | None] = mapped_column(String)
    # The posting's own words on work authorization, never a judgment.
    work_authorization_quote: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    # open, unknown or closed.
    status: Mapped[str] = mapped_column(String)
    status_evidence: Mapped[str | None] = mapped_column(Text)
    # Checked open in this run (false: its board could not be read).
    verified: Mapped[bool] = mapped_column(Boolean)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
