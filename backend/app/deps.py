"""Request dependencies: the database session and the bearer-token session."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Path
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app import models
from app.config import get_settings
from app.db import get_db
from app.errors import NOT_FOUND, UNAUTHORIZED
from app.security import token_hash

Db = Annotated[DbSession, Depends(get_db)]

# auto_error=False: a missing or non-Bearer header reaches `current_session`
# as None and becomes our 401, instead of FastAPI's 403.
bearer = HTTPBearer(
    scheme_name="bearerAuth",
    description="The `token` returned by `POST /api/auth/login`.",
    auto_error=False,
)

# `expires_at` moves forward at most once a day per session.
EXTEND_AFTER = timedelta(days=1)


def current_session(
    db: Db,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> models.Session:
    """The session for the bearer token, or 401. Cookies are ignored."""
    if credentials is None or not credentials.credentials.strip():
        raise UNAUTHORIZED
    now = datetime.now(UTC)
    session = db.scalars(
        select(models.Session).where(
            models.Session.token_hash == token_hash(credentials.credentials),
            models.Session.expires_at > now,
        )
    ).one_or_none()
    if session is None:
        raise UNAUTHORIZED

    # Sliding expiry: the session was last extended at `expires_at - ttl`.
    ttl = timedelta(days=get_settings().session_ttl_days)
    if session.expires_at - ttl < now - EXTEND_AFTER:
        session.expires_at = now + ttl
        db.commit()
    return session


CurrentSession = Annotated[models.Session, Depends(current_session)]


def current_user(db: Db, session: CurrentSession) -> models.User:
    user = db.get(models.User, session.user_id)
    if user is None:
        # Deleted between the session lookup and now.
        raise UNAUTHORIZED
    return user


CurrentUser = Annotated[models.User, Depends(current_user)]


def own_user_id(
    session: CurrentSession,
    id: Annotated[
        str,
        Path(
            description="The user's id (must be your own).",
            json_schema_extra={"format": "uuid"},
        ),
    ],
) -> uuid.UUID:
    """The path id if it is the caller's own, else 404. Anyone else's id gets
    the same 404 as an id that doesn't exist or isn't a UUID, and the check
    runs before any user lookup so the cases can't be told apart."""
    try:
        requested = uuid.UUID(id)
    except ValueError:
        raise NOT_FOUND from None
    if requested != session.user_id:
        raise NOT_FOUND
    return requested


OwnUserId = Annotated[uuid.UUID, Depends(own_user_id)]
