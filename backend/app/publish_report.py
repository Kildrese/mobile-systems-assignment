"""Copy the latest internship tracker run from the tracker's state file into Postgres:

    uv run python -m app.publish_report

The daily tracker workflow (`.github/workflows/tracker.yml`) runs this right after
`python -m tracker run`. It is the only writer of `tracker_runs`, `internship_offers` and
`tracker_articles`:
the API only reads them and can never start the tracker. Publishing a run again replaces
its rows, so a retried job is safe.
"""

import sys
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app import models
from app.db import get_sessionmaker
from tracker.config import load_policy
from tracker.errors import PolicyError
from tracker.state import StateStore
from tracker.usecases.internships.report import _quote, _value, sections
from tracker.usecases.internships.store import OpportunityStore


def _known(opp: dict[str, Any], name: str) -> str | None:
    value = _value(opp, name)
    return None if value == "unknown" else value


def offers(store: OpportunityStore, run_id: str) -> list[dict[str, Any]]:
    """One row per opportunity in the run's report, with its report section."""
    s = sections(store, run_id)
    # Run ids start with their UTC time, so they sort by age. An offer keeps the last
    # summary that passed the Editor's checks, even from an earlier run.
    summaries = {
        r["opportunity_id"]: r["text"]
        for r in store.db.execute(
            "SELECT opportunity_id, text FROM summaries WHERE run_id <= ? ORDER BY run_id",
            (run_id,),
        )
    }
    return [
        {
            "opportunity_id": opp["id"],
            "section": section,
            "rank": opp["rank"],
            "top_k": opp["top_k"],
            "previous_rank": opp["previous_rank"],
            "drop_reason": opp["drop_reason"],
            "company": opp["company"],
            "title": opp["title"],
            "role_type": opp["role_type"],
            "term": opp["term"],
            "locations": opp["locations"],
            "remote": opp["remote"],
            "url": opp["url"],
            "compensation": _known(opp, "compensation"),
            "deadline": _known(opp, "deadline"),
            "work_authorization_quote": _quote(opp, "work_authorization"),
            "summary": summaries.get(opp["id"]),
            "status": opp["status"],
            "status_evidence": opp["status_evidence"],
            "verified": opp["verified"],
            "first_seen_at": datetime.fromisoformat(opp["first_seen_at"]),
        }
        for section, opps in (
            ("new", s.new),
            ("top_k", s.top_k),
            ("dropped", s.dropped),
            ("open", s.also_open),
        )
        for opp in opps
    ]


def articles(state: StateStore, run_id: str) -> list[dict[str, Any]]:
    """The run's fetch log, in fetch order."""
    return [
        {**dict(r), "fetched_at": datetime.fromisoformat(r["fetched_at"])}
        for r in state.db.execute(
            "SELECT stage, kind, url, title, status, reason, at AS fetched_at FROM fetch_log "
            "WHERE run_id = ? ORDER BY id",
            (run_id,),
        )
    ]


def publish(
    db: Session,
    run: dict[str, Any],
    rows: list[dict[str, Any]],
    markdown: str,
    fetched: Sequence[dict[str, Any]] = (),
) -> None:
    """Replace the run and everything under it (offers, articles) in one transaction."""
    db.execute(delete(models.TrackerRun).where(models.TrackerRun.id == run["id"]))
    db.add(
        models.TrackerRun(
            id=run["id"],
            topic=run["topic"],
            status=run["status"],
            stop_reason=run["stop_reason"],
            started_at=datetime.fromisoformat(run["started_at"]),
            ended_at=datetime.fromisoformat(run["ended_at"]) if run["ended_at"] else None,
            report_markdown=markdown,
        )
    )
    db.flush()
    db.add_all(models.InternshipOffer(run_id=run["id"], **row) for row in rows)
    db.add_all(models.TrackerArticle(run_id=run["id"], **article) for article in fetched)
    db.commit()


def main() -> int:
    try:
        policy = load_policy()
    except PolicyError as err:
        print(err, file=sys.stderr)
        return 1

    with StateStore(policy.state_file) as state:
        # A run without `ended_at` is still going or was killed mid-run.
        run = state.db.execute(
            "SELECT * FROM runs WHERE ended_at IS NOT NULL ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if run is None:
            print("The state file has no finished run: nothing to publish.", file=sys.stderr)
            return 1
        run = dict(run)
        rows = offers(OpportunityStore(state), run["id"])
        fetched = articles(state, run["id"])

    report = policy.reports_path / f"{run['id']}.md"
    markdown = report.read_text() if report.exists() else ""
    with get_sessionmaker()() as db:
        publish(db, run, rows, markdown, fetched)
    print(
        f"Published run {run['id']} ({run['status']}) with {len(rows)} offers "
        f"and {len(fetched)} articles."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
