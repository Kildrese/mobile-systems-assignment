"""Applicant profiles and application drafts: who may draft, checking an upload, the
drafter client, and one draft from claim to stored row.

Used by the API (`app/routers/drafts.py`) and the daily step (`python -m app.draft_new`).
Only users in `DRAFTING_USERS` reach the drafter, and only within `DAILY_CAP` drafts per
UTC day: both are checked before any call that spends model tokens.
"""

import base64
import hashlib
import json
import random
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from agentkit.contract import (
    MAX_CV_BYTES,
    MAX_TEXT_BYTES,
    DraftRequest,
    DraftResponse,
)
from agentkit.cv.layout import LayoutError, Master
from agentkit.cv.profile import ProfileError, parse_checks, parse_fact_bank
from agentkit.fetch import parse_retry_after
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.config import get_settings
from app.errors import DAILY_LIMIT, DRAFT_IN_PROGRESS, NOT_ALLOWED, ApiError
from app.schemas import ErrorCode

FILES = ("cv.docx", "fact_bank.yaml", "rules.md", "checks.yaml")
DAILY_CAP = 20
# A pending draft older than this was cut off (a killed function) and may be redone.
PENDING_STALE = timedelta(minutes=10)
TIME_BUDGET_MS = 120_000
COLD_START_MS = 15_000
BUDGET = {"max_steps": 3, "max_fetches": 6, "max_tokens": 60_000}


# Who may draft


def may_draft(user: models.User) -> None:
    if user.username.lower() not in get_settings().drafting_users:
        raise NOT_ALLOWED


def drafts_today(db: Session, user_id: uuid.UUID) -> int:
    today = datetime.now(UTC).date()
    return db.scalar(
        select(func.coalesce(func.sum(models.ApplicationDraft.starts), 0)).where(
            models.ApplicationDraft.user_id == user_id,
            models.ApplicationDraft.starts_day == today,
        )
    )


# The profile


def invalid(file: str, reason: str) -> ApiError:
    return ApiError(400, ErrorCode.INVALID_PROFILE, f"{file}: {reason}")


def check_profile(files: dict[str, bytes | None]) -> dict[str, str]:
    """The three text files, decoded, once all four pass the same checks the drafter
    runs. Raises a 400 naming the file and the reason."""
    for name in FILES:
        if not files.get(name):
            raise invalid(name, "missing; upload all four files together")
    if len(files["cv.docx"]) > MAX_CV_BYTES:
        raise invalid("cv.docx", f"larger than {MAX_CV_BYTES // (1024 * 1024)} MB")
    texts = {}
    for name in FILES[1:]:
        if len(files[name]) > MAX_TEXT_BYTES:
            raise invalid(name, f"larger than {MAX_TEXT_BYTES // 1024} KB")
        try:
            texts[name] = files[name].decode("utf-8")
        except UnicodeDecodeError:
            raise invalid(name, "not UTF-8 text") from None
    try:
        Master(files["cv.docx"])
    except LayoutError as err:
        raise invalid("cv.docx", str(err)) from None
    try:
        facts = parse_fact_bank(texts["fact_bank.yaml"])
        parse_checks(texts["checks.yaml"], facts)
    except ProfileError as err:
        raise invalid(err.file, err.reason) from None
    return texts


def file_info(files: dict[str, bytes]) -> dict[str, dict]:
    return {
        name: {"size": len(files[name]), "sha256": hashlib.sha256(files[name]).hexdigest()}
        for name in FILES
    }


def profile_hash(profile: models.ApplicantProfile) -> str:
    joined = "".join(profile.files[name]["sha256"] for name in FILES)
    return hashlib.sha256(joined.encode()).hexdigest()


def save_profile(db: Session, user_id: uuid.UUID, files: dict[str, bytes | None]) -> None:
    texts = check_profile(files)
    profile = db.get(models.ApplicantProfile, user_id) or models.ApplicantProfile(user_id=user_id)
    profile.cv_docx = files["cv.docx"]
    profile.fact_bank = texts["fact_bank.yaml"]
    profile.rules_md = texts["rules.md"]
    profile.checks_yaml = texts["checks.yaml"]
    profile.files = file_info(files)  # type: ignore[arg-type]
    profile.uploaded_at = datetime.now(UTC)
    db.add(profile)
    db.commit()


def owners_visible_to(db: Session, user_id: uuid.UUID) -> list[uuid.UUID]:
    """The user and every owner who shared their drafts with them."""
    shared = db.scalars(
        select(models.ApplicantProfile.user_id).where(
            models.ApplicantProfile.viewer_ids.any(user_id)
        )
    ).all()
    return [user_id, *shared]


# The drafter client


class DrafterFailed(Exception):
    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


@dataclass
class DrafterClient:
    """POST /draft until a valid answer or a terminal failure, retrying 502/503/504,
    timeouts and connection errors with backoff (at least the `Retry-After`). Every
    attempt sends the same bytes with the same `request_id`, so a retry costs nothing
    once the drafter has the answer."""

    url: str
    token: str
    max_attempts: int = 2
    transport: httpx.BaseTransport | None = None
    sleep: Callable[[float], None] = time.sleep

    def send(self, request: DraftRequest) -> DraftResponse:
        content = json.dumps(request.model_dump(mode="json"), separators=(",", ":")).encode()
        timeout = (request.time_budget_ms + COLD_START_MS) / 1000
        with httpx.Client(transport=self.transport, trust_env=False) as http:
            for attempt in range(1, self.max_attempts + 1):
                wait = None
                try:
                    r = http.post(
                        f"{self.url.rstrip('/')}/draft",
                        content=content,
                        headers={
                            "Authorization": f"Bearer {self.token}",
                            "Content-Type": "application/json",
                        },
                        timeout=timeout,
                    )
                except httpx.TimeoutException:
                    status: object = "timeout"
                except httpx.HTTPError:
                    status = "connection_error"
                else:
                    status = r.status_code
                    wait = parse_retry_after(r.headers)
                    if status in (200, 500):
                        try:
                            response = DraftResponse.model_validate_json(r.content)
                            response.check_against(request)
                            return response
                        except (ValidationError, ValueError) as err:
                            if status == 200:
                                raise DrafterFailed("invalid_response", str(err)[:200]) from None
                    if status == 401:
                        raise DrafterFailed("unauthorized", "the drafter refused the token")
                    if status not in (502, 503, 504):
                        raise DrafterFailed(f"http_{status}", r.text[:200])
                if attempt < self.max_attempts:
                    self.sleep(max(min(2**attempt, 30) * (0.8 + 0.4 * random.random()), wait or 0))
        raise DrafterFailed(
            "no_answer", f"no answer after {self.max_attempts} attempts (last: {status})"
        )


def drafter_client(max_attempts: int) -> DrafterClient | None:
    s = get_settings()
    if not s.drafter_url or not s.drafter_token:
        return None
    return DrafterClient(s.drafter_url, s.drafter_token, max_attempts)


# One draft


@dataclass(frozen=True)
class Offer:
    opportunity_id: int
    company: str
    title: str
    url: str
    deadline: str | None


def latest_offer(db: Session, opportunity_id: int) -> Offer | None:
    row = db.execute(
        select(models.InternshipOffer)
        .join(models.TrackerRun)
        .where(models.InternshipOffer.opportunity_id == opportunity_id)
        .order_by(models.TrackerRun.started_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        return None
    return Offer(row.opportunity_id, row.company, row.title, row.url, row.deadline)


def claim(
    db: Session, user: models.User, profile: models.ApplicantProfile, offer: Offer, letter: bool
) -> models.ApplicationDraft:
    """Mark the user's draft for this offer pending (replacing any earlier one) and count
    it toward today's cap. 409 while another draft for it runs; 429 over the cap."""
    now = datetime.now(UTC)
    # One claim per user at a time, so two drafts of different offers can't both pass the cap.
    db.execute(text("select pg_advisory_xact_lock(hashtext(:u))"), {"u": str(user.id)})
    row = db.scalars(
        select(models.ApplicationDraft)
        .where(
            models.ApplicationDraft.user_id == user.id,
            models.ApplicationDraft.opportunity_id == offer.opportunity_id,
        )
        .with_for_update()
    ).one_or_none()
    if row is not None and row.status == "pending" and now - row.created_at < PENDING_STALE:
        db.rollback()
        raise DRAFT_IN_PROGRESS
    if drafts_today(db, user.id) >= DAILY_CAP:
        db.rollback()
        raise DAILY_LIMIT
    if row is None:
        row = models.ApplicationDraft(
            id=uuid.uuid4(),
            user_id=user.id,
            opportunity_id=offer.opportunity_id,
            starts=0,
            starts_day=now.date(),
        )
        db.add(row)
    row.starts = row.starts + 1 if row.starts_day == now.date() else 1
    row.starts_day = now.date()
    row.company, row.title, row.cover_letter = offer.company, offer.title, letter
    row.status, row.created_at, row.request_id = "pending", now, uuid.uuid4()
    row.cv_docx = row.letter_docx = row.letter_text = row.role_type = row.model = row.error = None
    row.checks = []
    row.profile_hash = profile_hash(profile)
    try:
        db.commit()
    except IntegrityError:  # two first clicks at once: the other one inserted the row
        db.rollback()
        raise DRAFT_IN_PROGRESS from None
    return row


def run_draft(
    db: Session,
    user: models.User,
    profile: models.ApplicantProfile,
    offer: Offer,
    letter: bool,
    client: DrafterClient,
) -> models.ApplicationDraft:
    """Claim, call the drafter, store the result. A failure is stored on the row."""
    row = claim(db, user, profile, offer, letter)
    request = DraftRequest(
        request_id=row.request_id,
        run_id=uuid.uuid4(),
        time_budget_ms=TIME_BUDGET_MS,
        budget=BUDGET,  # type: ignore[arg-type]
        payload={  # type: ignore[arg-type]
            "posting_url": offer.url,
            "company": offer.company,
            "title": offer.title,
            "cover_letter": letter,
            "profile": {
                "cv_docx_b64": base64.b64encode(profile.cv_docx).decode(),
                "fact_bank_yaml": profile.fact_bank,
                "rules_md": profile.rules_md,
                "checks_yaml": profile.checks_yaml,
            },
        },
    )
    try:
        response = client.send(request)
    except DrafterFailed as err:
        row.status, row.error = "failed", f"{err.reason}: {err.detail}"[:500]
    except Exception:
        row.status, row.error = "failed", "internal error"
        db.commit()
        raise
    else:
        res = response.result
        row.status = {"complete": "ready", "partial": "partial"}.get(response.status, "failed")
        if response.error:
            row.error = f"{response.error.code}: {response.error.message}"[:500]
        row.role_type, row.model = res.role_type, res.model
        row.checks = [c.model_dump() for c in res.checks]
        row.cv_docx = base64.b64decode(res.cv_docx_b64) if res.cv_docx_b64 else None
        if res.cover_letter_docx_b64:
            row.letter_docx = base64.b64decode(res.cover_letter_docx_b64)
        row.letter_text = res.cover_letter_text
    db.commit()
    return row
