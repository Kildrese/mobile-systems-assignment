"""The database schema. Alembic migrations are generated from these models."""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
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
    # Worker services that failed in this run (e.g. ["verifier"]); empty when none did.
    failed_services: Mapped[list[str]] = mapped_column(
        ARRAY(String), server_default=text("'{}'::text[]")
    )
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
    # The Assessor's fit with the profile, 0 to 3, and its one-sentence reason.
    fit_score: Mapped[int | None] = mapped_column(Integer)
    fit_reason: Mapped[str | None] = mapped_column(Text)
    # open, unknown or closed.
    status: Mapped[str] = mapped_column(String)
    status_evidence: Mapped[str | None] = mapped_column(Text)
    # Checked open in this run (false: its board could not be read).
    verified: Mapped[bool] = mapped_column(Boolean)
    # Top K only: [{field, text, verdict, evidence}], verdict supported, unsupported,
    # unreachable or unverified. Claim text and evidence came from the web: untrusted text.
    claims: Mapped[list[dict]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    @property
    def deadline_passed(self) -> bool:
        return deadline_passed(self.deadline)


DEADLINE_FORMATS = ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y", "%m/%d/%Y")


def deadline_passed(deadline: str | None, today: date | None = None) -> bool:
    """Whether a deadline (free text from the posting) is a date before today, UTC. Text
    that isn't one of the common date formats is never treated as passed."""
    # ponytail: a few fixed formats; add more when a real deadline goes unrecognized
    if not deadline:
        return False
    value = deadline.strip().rstrip(".")
    for fmt in DEADLINE_FORMATS:
        try:
            day = datetime.strptime(value[:10] if fmt == "%Y-%m-%d" else value, fmt).date()
        except ValueError:
            continue
        return day < (today or datetime.now(UTC).date())
    return False


class TrackerArticle(Base):
    """One document a run tried to read: a page, a job board or a posting. Published from
    the tracker's fetch log; titles and URLs came from the web and are untrusted text."""

    __tablename__ = "tracker_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey(TrackerRun.id, ondelete="CASCADE"), index=True)
    # scout, collect, curate, or agent (the single-agent loop).
    stage: Mapped[str] = mapped_column(String)
    # page, board or posting.
    kind: Mapped[str] = mapped_column(String)
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    # fetched, skipped (already seen), rejected (by a guardrail) or failed.
    status: Mapped[str] = mapped_column(String)
    reason: Mapped[str | None] = mapped_column(String)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TrackerDispatch(Base):
    """One UTC day's start of the tracker workflow by the daily cron. The day is the key, so
    claiming it is atomic: of any number of cron calls on one day, one dispatches."""

    __tablename__ = "tracker_dispatches"
    __table_args__ = (CheckConstraint("status in ('claimed', 'dispatched', 'failed')", "status"),)

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    # claimed (a call is dispatching), dispatched (GitHub accepted) or failed.
    status: Mapped[str] = mapped_column(String)
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer)
    # GitHub's status and message for the last failure; never the token.
    error: Mapped[str | None] = mapped_column(Text)


class ApplicantProfile(Base):
    """One user's applicant profile: the master CV and the three files that drive tailoring.
    Personal data: only the owner reads it, and no route or log returns its contents."""

    __tablename__ = "applicant_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(User.id, ondelete="CASCADE"), primary_key=True
    )
    cv_docx: Mapped[bytes] = mapped_column(LargeBinary)
    fact_bank: Mapped[str] = mapped_column(Text)
    rules_md: Mapped[str] = mapped_column(Text)
    checks_yaml: Mapped[str] = mapped_column(Text)
    # {file name: {"size": bytes, "sha256": hex}} for the four files.
    files: Mapped[dict] = mapped_column(JSONB)
    # Users who may read (only) this user's drafts. Set by `python -m app.share_drafts`.
    viewer_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(Uuid), server_default=text("'{}'::uuid[]")
    )
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ApplicationDraft(Base):
    """The latest tailored CV (and cover letter) of one user for one opportunity."""

    __tablename__ = "application_drafts"
    __table_args__ = (
        UniqueConstraint("user_id", "opportunity_id"),
        CheckConstraint("status in ('pending', 'ready', 'partial', 'failed')", "status"),
    )

    # In download URLs; the (user, opportunity) pair is the real key.
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(User.id, ondelete="CASCADE"))
    # The opportunity's id in the tracker's state file, as on `internship_offers`.
    opportunity_id: Mapped[int] = mapped_column(Integer)
    company: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    cover_letter: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String)
    cv_docx: Mapped[bytes | None] = mapped_column(LargeBinary)
    letter_docx: Mapped[bytes | None] = mapped_column(LargeBinary)
    letter_text: Mapped[str | None] = mapped_column(Text)
    role_type: Mapped[str | None] = mapped_column(String)
    # [{name, outcome, detail}]: what code changed or rejected in the model's plan.
    checks: Mapped[list[dict]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    # Why a draft is partial or failed (an error code and message), never file contents.
    error: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String)
    # Hash of the profile files the draft was made from (stale when the profile changes).
    profile_hash: Mapped[str] = mapped_column(String)
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Drafts started for this row on `starts_day` (UTC), for the daily cap: the row is
    # replaced on every draft, so a count of rows would undercount.
    starts_day: Mapped[date] = mapped_column(Date)
    starts: Mapped[int] = mapped_column(Integer)
