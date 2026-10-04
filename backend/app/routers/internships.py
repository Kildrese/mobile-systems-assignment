from fastapi import APIRouter, Response
from sqlalchemy import select

from app import models, schemas
from app.deps import CurrentSession, Db
from app.errors import NOT_FOUND as NOT_FOUND_ERROR
from app.routers.responses import INTERNAL, UNAUTHORIZED, not_found

# Read-only on purpose: the tracker runs once a day from the scheduled workflow, and
# no route can start it or change what it published.
router = APIRouter(prefix="/api/internships", tags=["Internships"])


@router.get(
    "/latest",
    operation_id="getLatestInternshipReport",
    summary="The latest internship tracker report",
    response_model=schemas.InternshipReport,
    response_description="The latest published run and its offers, best rank first.",
    responses={**UNAUTHORIZED, **INTERNAL},
)
def get_latest_report(db: Db, _: CurrentSession):
    run = db.scalars(
        select(models.TrackerRun).order_by(models.TrackerRun.started_at.desc()).limit(1)
    ).one_or_none()
    if run is None:
        return {"run": None, "offers": []}
    offers = db.scalars(
        select(models.InternshipOffer)
        .where(models.InternshipOffer.run_id == run.id)
        .order_by(
            models.InternshipOffer.rank.asc().nulls_last(),
            models.InternshipOffer.company,
            models.InternshipOffer.id,
        )
    ).all()
    return {"run": run, "offers": offers}


@router.get(
    "/runs/{id}/report.md",
    operation_id="exportInternshipReport",
    summary="Download a run's Markdown report",
    response_class=Response,
    response_description="The tracker's own report for the run, as published.",
    responses={
        200: {"content": {"text/markdown": {"schema": {"type": "string"}}}},
        **UNAUTHORIZED,
        **not_found("No published run with this id, or it has no report."),
        **INTERNAL,
    },
)
def export_report(db: Db, _: CurrentSession, id: str) -> Response:
    run = db.get(models.TrackerRun, id)
    if run is None or not run.report_markdown:
        raise NOT_FOUND_ERROR
    return Response(
        run.report_markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="internships-{run.id}.md"'},
    )
