"""The daily tracker dispatch. Vercel Cron calls this route once a day, and it starts the
tracker workflow on GitHub at most once per UTC day. No user can reach it: a request without
the cron secret gets the same 404 as an unknown path, and the route isn't in the OpenAPI
document."""

import logging
import secrets
import time
from datetime import UTC, date, datetime
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

WORKFLOW_URL = (
    "https://api.github.com/repos/Kildrese/mobile-systems-assignment/actions/workflows/tracker.yml"
)
DISPATCH_URL = f"{WORKFLOW_URL}/dispatches"
RUNS_URL = f"{WORKFLOW_URL}/runs"
# A failed dispatch is retried once in the same request, after a pause that also gives a
# dispatch GitHub did accept (a timeout proves nothing) time to show up as a run. Worst case
# 10 s + 5 s + 10 s + 20 s, well inside the function timeout and the 5-minute claim.
RETRY_WAIT = 5

# One statement, so the lock on the primary key decides which call owns the day: a new day,
# a failed one, or a claim left by a call that died more than 5 minutes ago (the GitHub call
# calls take under a minute, so a live claim is never taken over). No row back: someone has it.
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


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _dispatch(token: str, timeout: float) -> str | None:
    """Start the workflow on GitHub. None on success, else what went wrong (never the token)."""
    try:
        response = httpx.post(
            DISPATCH_URL, json={"ref": "master"}, headers=_headers(token), timeout=timeout
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


def _ran_on(token: str, day: date) -> bool | None:
    """Whether a dispatched tracker run exists for the UTC day; None if GitHub can't say."""
    try:
        response = httpx.get(
            RUNS_URL,
            params={
                "event": "workflow_dispatch",
                "created": f">={day.isoformat()}T00:00:00Z",
                "per_page": 1,
            },
            headers=_headers(token),
            timeout=10,
        )
        response.raise_for_status()
        return response.json()["total_count"] > 0
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return None


@router.get("/tracker-dispatch")
def tracker_dispatch(db: Db, authorization: Annotated[str | None, Header()] = None) -> JSONResponse:
    if not _is_cron(authorization):
        raise NOT_FOUND
    day = datetime.now(UTC).date()
    claimed = db.execute(CLAIM, {"day": day}).first()
    db.commit()
    if claimed is None:
        return JSONResponse({"status": "already_dispatched"})

    dispatch = db.get_one(models.TrackerDispatch, day)
    token = get_settings().github_dispatch_token
    error = _dispatch(token, timeout=10) if token else "GITHUB_DISPATCH_TOKEN is not set"
    if error and token:
        # Retry once, but only once GitHub confirms no run started today: a timed-out
        # dispatch may still have been accepted, and a second run spends twice on paid APIs.
        logger.warning("Tracker dispatch for %s failed, retrying: %s", day, error)
        time.sleep(RETRY_WAIT)
        ran = _ran_on(token, day)
        if ran:
            error = None
        elif ran is None:
            error = f"{error} (not retried: could not list today's runs)"
        else:
            dispatch.attempts += 1
            error = _dispatch(token, timeout=20)
    dispatch.status = "failed" if error else "dispatched"
    dispatch.error = error
    db.commit()
    if error:
        logger.error("Tracker dispatch for %s failed: %s", day, error)
        return JSONResponse({"status": "failed"}, status_code=502)
    return JSONResponse({"status": "dispatched"}, status_code=202)
