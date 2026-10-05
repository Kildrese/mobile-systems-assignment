from typing import Annotated

from fastapi import APIRouter, Query, Response
from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session, defer

from app import models, schemas
from app.deps import CurrentSession, Db
from app.errors import NOT_FOUND as NOT_FOUND_ERROR
from app.routers.responses import BAD_REQUEST, INTERNAL, UNAUTHORIZED, not_found

# Read-only on purpose: the tracker runs once a day from the scheduled workflow, and
# no route can start it or change what it published.
router = APIRouter(prefix="/api/internships", tags=["Internships"])

UNKNOWN_RUN = not_found("No published run with this id.")


def _report(db: Session, run: models.TrackerRun | None) -> dict:
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


def _published_run(db: Session, id: str) -> models.TrackerRun:
    run = db.get(models.TrackerRun, id)
    if run is None:
        raise NOT_FOUND_ERROR
    return run


def _counts(db: Session, column, run_ids: list[str]) -> dict[str, dict[str, int]]:
    """`{run id: {value: count}}` for one column of a table keyed by `run_id`."""
    table = column.class_
    counts: dict[str, dict[str, int]] = {run_id: {} for run_id in run_ids}
    rows = db.execute(
        select(table.run_id, column, func.count())
        .where(table.run_id.in_(run_ids))
        .group_by(table.run_id, column)
    )
    for run_id, value, count in rows:
        counts[run_id][value] = count
    return counts


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
    return _report(db, run)


@router.get(
    "/runs",
    operation_id="listInternshipRuns",
    summary="Run history",
    response_model=schemas.TrackerRunList,
    response_description="Published runs, newest first, with what changed in each.",
    responses={**BAD_REQUEST, **UNAUTHORIZED, **INTERNAL},
)
def list_runs(
    db: Db,
    _: CurrentSession,
    limit: Annotated[int, Query(ge=1, le=100, description="At most this many runs.")] = 30,
    before: Annotated[
        str | None, Query(description="A run id: only runs that started before it.")
    ] = None,
):
    query = (
        select(models.TrackerRun)
        .options(defer(models.TrackerRun.report_markdown))  # history never shows the report
        .order_by(models.TrackerRun.started_at.desc(), models.TrackerRun.id.desc())
        .limit(limit)
    )
    if before is not None:
        # Keyset paging on (started_at, id): the id breaks ties between equal start times.
        started = select(models.TrackerRun.started_at).where(models.TrackerRun.id == before)
        key = tuple_(models.TrackerRun.started_at, models.TrackerRun.id)
        query = query.where(key < tuple_(started.scalar_subquery(), before))
    runs = db.scalars(query).all()
    ids = [run.id for run in runs]
    sections = _counts(db, models.InternshipOffer.section, ids)
    articles = _counts(db, models.TrackerArticle.status, ids)
    return {
        "runs": [
            {
                "id": run.id,
                "topic": run.topic,
                "status": run.status,
                "stop_reason": run.stop_reason,
                "started_at": run.started_at,
                "ended_at": run.ended_at,
                "sections": sections[run.id],
                "articles": articles[run.id],
            }
            for run in runs
        ]
    }


@router.get(
    "/runs/{id}",
    operation_id="getInternshipRun",
    summary="A run's report",
    response_model=schemas.InternshipReport,
    response_description="The run and its offers, best rank first.",
    responses={**UNAUTHORIZED, **UNKNOWN_RUN, **INTERNAL},
)
def get_run(db: Db, _: CurrentSession, id: str):
    return _report(db, _published_run(db, id))


@router.get(
    "/runs/{id}/articles",
    operation_id="listInternshipRunArticles",
    summary="The documents a run tried to read",
    response_model=schemas.TrackerArticleList,
    response_description="Pages, job boards and postings, in fetch order, with their status.",
    responses={**UNAUTHORIZED, **UNKNOWN_RUN, **INTERNAL},
)
def list_run_articles(db: Db, _: CurrentSession, id: str):
    run = _published_run(db, id)
    articles = db.scalars(
        select(models.TrackerArticle)
        .where(models.TrackerArticle.run_id == run.id)
        .order_by(models.TrackerArticle.id)
    ).all()
    return {"articles": articles}


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
