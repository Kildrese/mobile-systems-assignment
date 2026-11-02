"""The applicant profile (owner only) and application drafts (owner and shared viewers)."""

import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from sqlalchemy import select

from app import drafts, models, schemas
from app.config import get_settings
from app.deps import CurrentUser, Db
from app.errors import (
    DEADLINE_PASSED,
    DRAFTER_UNAVAILABLE,
    NOT_FOUND,
    PROFILE_MISSING,
)
from app.routers.responses import BAD_REQUEST, INTERNAL, UNAUTHORIZED, _error, not_found

profile_router = APIRouter(prefix="/api/profile", tags=["Drafts"])
router = APIRouter(prefix="/api/drafts", tags=["Drafts"])

NOT_ALLOWED = {403: _error("This account may not upload a profile or draft (`DRAFTING_USERS`).")}
NO_DRAFT = not_found("No draft with this id that you may read, or it has no such file.")


def drafting_user(user: CurrentUser) -> models.User:
    """The signed-in user, if they may spend model tokens; 403 before anything else runs."""
    drafts.may_draft(user)
    return user


DraftingUser = Annotated[models.User, Depends(drafting_user)]


def _profile_view(profile: models.ApplicantProfile | None, user: models.User) -> dict:
    return {
        "files": [{"name": n, **profile.files[n]} for n in drafts.FILES] if profile else [],
        "uploaded_at": profile.uploaded_at if profile else None,
        "can_draft": user.username.lower() in get_settings().drafting_users,
    }


@profile_router.get(
    "",
    operation_id="getProfile",
    summary="Your applicant profile",
    response_model=schemas.Profile,
    response_description="The stored files' names, sizes and hashes; never their contents.",
    responses={**UNAUTHORIZED, **INTERNAL},
)
def get_profile(db: Db, user: CurrentUser):
    return _profile_view(db.get(models.ApplicantProfile, user.id), user)


@profile_router.put(
    "",
    operation_id="uploadProfile",
    summary="Upload your applicant profile",
    response_model=schemas.Profile,
    response_description="The profile as stored. All four files replace any earlier upload.",
    responses={
        400: _error("A file is missing, too large or fails its checks; the message names it."),
        **UNAUTHORIZED,
        **NOT_ALLOWED,
        **INTERNAL,
    },
)
def upload_profile(
    db: Db,
    user: DraftingUser,
    cv_docx: Annotated[UploadFile | None, File(alias="cvDocx", description="cv.docx")] = None,
    fact_bank: Annotated[
        UploadFile | None, File(alias="factBank", description="fact_bank.yaml")
    ] = None,
    rules_md: Annotated[UploadFile | None, File(alias="rulesMd", description="rules.md")] = None,
    checks_yaml: Annotated[
        UploadFile | None, File(alias="checksYaml", description="checks.yaml")
    ] = None,
):
    uploads = zip(drafts.FILES, (cv_docx, fact_bank, rules_md, checks_yaml), strict=True)
    # Read one byte past each limit, so an oversized file is refused without reading it all.
    files = {
        name: upload.file.read(drafts.MAX_CV_BYTES + 1) if upload else None
        for name, upload in uploads
    }
    drafts.save_profile(db, user.id, files)
    return _profile_view(db.get(models.ApplicantProfile, user.id), user)


def _view(
    draft: models.ApplicationDraft,
    owner: str,
    me: uuid.UUID,
    current_hash: str | None,
    has_cv: bool,
    has_letter: bool,
) -> dict:
    # The files are deferred columns: callers pass whether they exist, never load them.
    return {
        "id": draft.id,
        "opportunity_id": draft.opportunity_id,
        "owner": owner,
        "mine": draft.user_id == me,
        "status": draft.status,
        "cover_letter": draft.cover_letter,
        "has_cv": has_cv,
        "has_letter": has_letter,
        "letter_text": draft.letter_text,
        "role_type": draft.role_type,
        "checks": draft.checks,
        "error": draft.error,
        "profile_outdated": current_hash is not None and current_hash != draft.profile_hash,
        "created_at": draft.created_at,
    }


@router.post(
    "",
    operation_id="createDraft",
    summary="Draft an application for an offer",
    response_model=schemas.Draft,
    response_description="The stored draft: ready, partial (with the reason) or failed.",
    responses={
        **BAD_REQUEST,
        **UNAUTHORIZED,
        **NOT_ALLOWED,
        **not_found("No published offer with this opportunity id."),
        409: _error(
            "No profile yet, a draft for this offer is in progress, or its deadline passed."
        ),
        429: _error("You started 20 drafts today (UTC)."),
        503: _error("The drafter is not configured."),
        **INTERNAL,
    },
)
def create_draft(db: Db, user: DraftingUser, body: schemas.CreateDraftBody):
    client = drafts.drafter_client(max_attempts=2)
    if client is None:
        raise DRAFTER_UNAVAILABLE
    profile = db.get(models.ApplicantProfile, user.id)
    if profile is None:
        raise PROFILE_MISSING
    offer = drafts.latest_offer(db, body.opportunity_id)
    if offer is None:
        raise NOT_FOUND
    if models.deadline_passed(offer.deadline):
        raise DEADLINE_PASSED
    draft = drafts.run_draft(db, user, profile, offer, body.cover_letter, client)
    # run_draft just set the files, so reading them costs no query.
    has_cv, has_letter = draft.cv_docx is not None, draft.letter_docx is not None
    return _view(draft, user.username, user.id, drafts.profile_hash(profile), has_cv, has_letter)


@router.get(
    "",
    operation_id="listDrafts",
    summary="Drafts you may read",
    response_model=schemas.DraftList,
    response_description="Your drafts and those shared with you, newest first.",
    responses={**BAD_REQUEST, **UNAUTHORIZED, **INTERNAL},
)
def list_drafts(
    db: Db,
    user: CurrentUser,
    opportunity_id: Annotated[
        int | None, Query(alias="opportunityId", description="Only this offer's drafts.")
    ] = None,
):
    owners = drafts.owners_visible_to(db, user.id)
    query = (
        select(
            models.ApplicationDraft,
            models.User.username,
            models.ApplicationDraft.cv_docx.is_not(None),
            models.ApplicationDraft.letter_docx.is_not(None),
        )
        .join(models.User, models.User.id == models.ApplicationDraft.user_id)
        .where(models.ApplicationDraft.user_id.in_(owners))
        .order_by(models.ApplicationDraft.created_at.desc())
    )
    if opportunity_id is not None:
        query = query.where(models.ApplicationDraft.opportunity_id == opportunity_id)
    hashes = {
        p.user_id: drafts.profile_hash(p)
        for p in db.scalars(
            select(models.ApplicantProfile).where(models.ApplicantProfile.user_id.in_(owners))
        )
    }
    return {
        "drafts": [
            _view(d, owner, user.id, hashes.get(d.user_id), has_cv, has_letter)
            for d, owner, has_cv, has_letter in db.execute(query)
        ]
    }


def _readable(db: Db, user: models.User, id: str) -> models.ApplicationDraft:
    try:
        draft = db.get(models.ApplicationDraft, uuid.UUID(id))
    except ValueError:
        draft = None
    if draft is None or draft.user_id not in drafts.owners_visible_to(db, user.id):
        raise NOT_FOUND
    return draft


def _name(draft: models.ApplicationDraft, suffix: str) -> str:
    safe = [re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_") for s in (draft.company, draft.title)]
    return "_".join([*filter(None, safe), suffix])


DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _file(content: bytes | None, media_type: str, filename: str) -> Response:
    if content is None:
        raise NOT_FOUND
    return Response(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _download_responses(media_type: str) -> dict:
    return {
        200: {"content": {media_type: {"schema": {"type": "string", "format": "binary"}}}},
        **UNAUTHORIZED,
        **NO_DRAFT,
        **INTERNAL,
    }


@router.get(
    "/{id}/cv.docx",
    operation_id="downloadDraftCv",
    summary="Download a draft's CV",
    response_class=Response,
    responses=_download_responses(DOCX),
)
def download_cv(db: Db, user: CurrentUser, id: str) -> Response:
    draft = _readable(db, user, id)
    return _file(draft.cv_docx, DOCX, _name(draft, "CV.docx"))


@router.get(
    "/{id}/cover-letter.docx",
    operation_id="downloadDraftLetter",
    summary="Download a draft's cover letter",
    response_class=Response,
    responses=_download_responses(DOCX),
)
def download_letter(db: Db, user: CurrentUser, id: str) -> Response:
    draft = _readable(db, user, id)
    return _file(draft.letter_docx, DOCX, _name(draft, "Cover_Letter.docx"))


@router.get(
    "/{id}/cover-letter.txt",
    operation_id="downloadDraftLetterText",
    summary="Download a draft's cover letter as text",
    response_class=Response,
    responses=_download_responses("text/plain"),
)
def download_letter_text(db: Db, user: CurrentUser, id: str) -> Response:
    draft = _readable(db, user, id)
    text = draft.letter_text.encode() if draft.letter_text else None
    return _file(text, "text/plain; charset=utf-8", _name(draft, "Cover_Letter.txt"))
