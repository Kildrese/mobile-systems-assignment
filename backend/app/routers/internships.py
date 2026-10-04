from fastapi import APIRouter
from sqlalchemy import select

from app import models, schemas
from app.deps import CurrentSession, Db
from app.routers.responses import INTERNAL, UNAUTHORIZED

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
