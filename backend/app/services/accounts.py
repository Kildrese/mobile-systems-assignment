"""Account rules. Plain functions over a database session: no HTTP. Failures
raise the `ApiError`s from `app.errors`. Input is already validated by the
request models in `app.schemas`."""

import uuid
from datetime import UTC, datetime, timedelta

from psycopg.errors import UniqueViolation
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app import models, schemas
from app.config import get_settings
from app.errors import (
    INVALID_CREDENTIALS,
    INVALID_PASSWORD,
    NOT_FOUND,
    UNAUTHORIZED,
    USERNAME_TAKEN,
    ApiError,
)
from app.security import dummy_verify, hash_password, new_token, token_hash, verify_password

# Unique constraint name → the error it means (see NAMING_CONVENTION).
_TAKEN = {"users_username_key": USERNAME_TAKEN}


def _taken_error(err: IntegrityError) -> ApiError | None:
    if isinstance(err.orig, UniqueViolation):
        return _TAKEN.get(err.orig.diag.constraint_name or "")
    return None


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


def register(db: DbSession, body: schemas.RegisterBody) -> models.User:
    # The request model lowercases the username.
    username = body.username
    first_name = body.first_name if body.first_name is not None else username
    last_name = body.last_name if body.last_name is not None else ""

    user = models.User(username=username, first_name=first_name, last_name=last_name)
    db.add(user)
    try:
        # Flushed before hashing, so a taken username costs no argon2 work.
        db.flush()
        db.add(models.UserPassword(user_id=user.id, hash=hash_password(body.password)))
        db.commit()
    except IntegrityError as err:
        # The unique constraint decides, so there's no check-then-write race.
        db.rollback()
        raise (_taken_error(err) or err) from None
    db.refresh(user)
    return user


def login(db: DbSession, body: schemas.LoginBody) -> tuple[str, models.User]:
    row = db.execute(
        select(models.User, models.UserPassword.hash)
        .join(models.UserPassword, models.UserPassword.user_id == models.User.id)
        .where(models.User.username == body.username.lower())
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
