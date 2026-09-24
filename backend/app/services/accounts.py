"""Account rules. Plain functions over a database session: no HTTP. Failures
raise the `ApiError`s from `app.errors`. Input is already validated by the
request models in `app.schemas`."""

import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from psycopg.errors import UniqueViolation
from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app import models, schemas
from app.config import get_settings
from app.errors import (
    EMAIL_TAKEN,
    INVALID_CREDENTIALS,
    INVALID_PASSWORD,
    NOT_FOUND,
    UNAUTHORIZED,
    USERNAME_TAKEN,
    ApiError,
)
from app.security import dummy_verify, hash_password, new_token, token_hash, verify_password

# Unique constraint name → the error it means (see NAMING_CONVENTION).
_TAKEN = {"users_email_key": EMAIL_TAKEN, "users_username_key": USERNAME_TAKEN}


def _taken_error(err: IntegrityError) -> ApiError | None:
    if isinstance(err.orig, UniqueViolation):
        return _TAKEN.get(err.orig.diag.constraint_name or "")
    return None


def _username_from_email(email: str) -> str:
    """The local part, reduced to the allowed characters, plus a random
    suffix so it is (almost surely) unique. At most 21 + 1 + 8 = 30 characters."""
    local = re.sub(r"[^a-z0-9_.]", "", email.split("@")[0].lower())[:21]
    return f"{local}_{secrets.token_hex(4)}"


def _create_session(db: DbSession, user_id: uuid.UUID) -> str:
    """Adds a session (committed by the caller) and returns its token."""
    token = new_token()
    ttl = timedelta(days=get_settings().session_ttl_days)
    db.add(
        models.Session(
            token_hash=token_hash(token), user_id=user_id, expires_at=datetime.now(UTC) + ttl
        )
    )
    return token


def _password_hash(db: DbSession, user_id: uuid.UUID) -> str | None:
    return db.scalar(select(models.UserPassword.hash).where(models.UserPassword.user_id == user_id))


def register(db: DbSession, body: schemas.RegisterBody) -> models.User:
    # The request model guarantees a username or an email, and lowercases
    # the username.
    email = body.email.lower() if body.email is not None else None
    username = body.username or _username_from_email(email or "")
    first_name = body.first_name if body.first_name is not None else username
    last_name = body.last_name if body.last_name is not None else ""

    # Checked first so a taken email is reported before a taken username.
    # Without an email, only the username is checked: `email == None` would
    # become `email IS NULL` and match every user without one.
    clash = models.User.username == username
    if email is not None:
        clash = or_(models.User.email == email, clash)
    taken = db.execute(select(models.User.email, models.User.username).where(clash)).all()
    if any(row.email is not None and row.email == email for row in taken):
        raise EMAIL_TAKEN
    if taken:
        raise USERNAME_TAKEN

    user = models.User(email=email, username=username, first_name=first_name, last_name=last_name)
    db.add(user)
    try:
        db.flush()
        db.add(models.UserPassword(user_id=user.id, hash=hash_password(body.password)))
        db.commit()
    except IntegrityError as err:
        # Lost a race with a concurrent registration.
        db.rollback()
        raise (_taken_error(err) or err) from None
    db.refresh(user)
    return user


def login(db: DbSession, body: schemas.LoginBody) -> tuple[str, models.User]:
    identifier = (body.login_identifier or "").lower()
    # Usernames can't contain `@`, so anything with one is an email.
    column = models.User.email if "@" in identifier else models.User.username
    row = db.execute(
        select(models.User, models.UserPassword.hash)
        .join(models.UserPassword, models.UserPassword.user_id == models.User.id)
        .where(column == identifier)
    ).one_or_none()
    if row is None:
        # Same work (one argon2 verify) and the same error as a wrong password.
        dummy_verify(body.password)
        raise INVALID_CREDENTIALS
    user, hash = row
    if not verify_password(body.password, hash):
        raise INVALID_CREDENTIALS

    token = _create_session(db, user.id)
    db.commit()
    return token, user


def logout(db: DbSession, session: models.Session) -> None:
    """Revokes only this session."""
    db.execute(delete(models.Session).where(models.Session.id == session.id))
    db.commit()


def change_password(db: DbSession, user_id: uuid.UUID, body: schemas.ChangePasswordBody) -> str:
    """Revokes every session of the user (this one included) and returns a
    new token."""
    password = db.get(models.UserPassword, user_id)
    if password is None:
        raise UNAUTHORIZED
    if not verify_password(body.current_password, password.hash):
        raise INVALID_PASSWORD

    password.hash = hash_password(body.new_password)
    db.execute(delete(models.Session).where(models.Session.user_id == user_id))
    token = _create_session(db, user_id)
    db.commit()
    return token


def change_email(db: DbSession, user: models.User, body: schemas.ChangeEmailBody) -> models.User:
    """Order: password (INVALID_PASSWORD), then same email (no-op), then
    uniqueness (EMAIL_TAKEN), so a wrong password can't probe which emails
    exist. Sessions stay valid."""
    hash = _password_hash(db, user.id)
    if hash is None or not verify_password(body.current_password, hash):
        raise INVALID_PASSWORD

    email = body.new_email.lower()
    if email == user.email:
        return user

    user.email = email
    try:
        db.commit()
    except IntegrityError as err:
        # The unique constraint decides, so there's no check-then-write race.
        db.rollback()
        raise (_taken_error(err) or err) from None
    db.refresh(user)
    return user


def update_profile(db: DbSession, user_id: uuid.UUID, body: schemas.UpdateUserBody) -> models.User:
    user = db.get(models.User, user_id)
    if user is None:
        raise NOT_FOUND
    for field in body.model_fields_set:
        setattr(user, field, getattr(body, field))
    try:
        db.commit()
    except IntegrityError as err:
        # `username` is the only unique column set here; the constraint decides.
        db.rollback()
        raise (_taken_error(err) or err) from None
    db.refresh(user)
    return user


def delete_account(db: DbSession, user_id: uuid.UUID) -> None:
    """Cascades to the password and every session, revoking all tokens."""
    result = db.execute(delete(models.User).where(models.User.id == user_id))
    if result.rowcount == 0:
        raise NOT_FOUND
    db.commit()
