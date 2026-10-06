"""The daily tracker dispatch. Vercel Cron calls this route once a day, and it starts the
tracker workflow on GitHub at most once per UTC day. No user can reach it: a request without
the cron secret gets the same 404 as an unknown path, and the route isn't in the OpenAPI
document."""

import logging
import secrets
from datetime import UTC, datetime
from typing import Annotated

import httpx
from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import models
from app.config import get_settings
from app.deps import Db
from app.errors import NOT_FOUND

logger = logging.getLogger("app")

router = APIRouter(prefix="/api/internal", include_in_schema=False)

DISPATCH_URL = (
    "https://api.github.com/repos/Kildrese/mobile-systems-assignment"
    "/actions/workflows/tracker.yml/dispatches"
)

# One statement, so the lock on the primary key decides which call owns the day: a new day,
# a failed one, or a claim left by a call that died more than 5 minutes ago (the GitHub call
# times out after 10 s, so a live claim is never taken over). No row back: someone has it.
CLAIM = text("""
    insert into tracker_dispatches (day, status, claimed_at, attempts)
    values (:day, 'claimed', now(), 1)
    on conflict (day) do update
       set status = 'claimed', claimed_at = now(),
           attempts = tracker_dispatches.attempts + 1, error = null
     where tracker_dispatches.status = 'failed'
        or (tracker_dispatches.status = 'claimed'
            and tracker_dispatches.claimed_at < now() - interval '5 minutes')
    returning attempts
""")


def _is_cron(authorization: str | None) -> bool:
    secret = get_settings().cron_secret
    if not secret or not authorization:
        return False
    return secrets.compare_digest(authorization.encode(), f"Bearer {secret}".encode())


def _dispatch() -> str | None:
    """Start the workflow on GitHub. None on success, else what went wrong (never the token)."""
    token = get_settings().github_dispatch_token
    if not token:
        return "GITHUB_DISPATCH_TOKEN is not set"
    try:
        response = httpx.post(
            DISPATCH_URL,
            json={"ref": "master"},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=10,
        )
    except httpx.HTTPError as err:
        return f"{type(err).__name__}: {err}"
    if response.status_code == 204:
        return None
    try:
        message = response.json().get("message", "")
    except ValueError:
        message = response.text[:200]
    return f"{response.status_code}: {message}"


@router.get("/tracker-dispatch")
def tracker_dispatch(db: Db, authorization: Annotated[str | None, Header()] = None) -> JSONResponse:
    if not _is_cron(authorization):
        raise NOT_FOUND
    day = datetime.now(UTC).date()
    claimed = db.execute(CLAIM, {"day": day}).first()
    db.commit()
    if claimed is None:
        return JSONResponse({"status": "already_dispatched"})

    error = _dispatch()
    dispatch = db.get_one(models.TrackerDispatch, day)
    dispatch.status = "failed" if error else "dispatched"
    dispatch.error = error
    db.commit()
    if error:
        logger.error("Tracker dispatch for %s failed: %s", day, error)
        return JSONResponse({"status": "failed"}, status_code=502)
    return JSONResponse({"status": "dispatched"}, status_code=202)
