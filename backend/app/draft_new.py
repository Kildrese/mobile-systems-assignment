"""Draft applications for the latest run's new top-K offers:

    uv run python -m app.draft_new

The daily tracker workflow runs this after `python -m app.publish_report`, next to the
tracker's state file. For each user in `DRAFTING_USERS` with a profile, each offer new in
this run's top K gets a CV draft, unless the user already has one for it or its deadline
has passed. A cover letter is asked for only when the posting's text mentions one.
Requests go one after another; a failure is stored on the draft row and never fails the
job (exit 0), so the workflow step can't break a published run.
"""

import sys
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.config import get_settings
from app.db import get_sessionmaker
from app.drafts import DrafterClient, Offer, drafter_client, run_draft
from app.errors import ApiError
from app.publish_report import offers
from app.schemas import ErrorCode
from tracker.config import load_policy
from tracker.errors import PolicyError
from tracker.state import StateStore
from tracker.usecases.internships.store import OpportunityStore


def asks_for_letter(store: OpportunityStore, opportunity_id: int) -> bool:
    texts = [
        f"{p['text']} {p.get('detail_text') or ''}" for p in store.linked_postings(opportunity_id)
    ]
    return "cover letter" in " ".join(texts).lower()


def new_top_k(store: OpportunityStore, run_id: str) -> list[dict[str, Any]]:
    """The run's new top-K offers, each with whether its posting asks for a letter."""
    return [
        {**row, "letter": asks_for_letter(store, row["opportunity_id"])}
        for row in offers(store, run_id)
        if row["section"] == "new" and row["top_k"]
    ]


def draft_new(db: Session, rows: list[dict[str, Any]], client: DrafterClient) -> list[str]:
    """Draft each row for every allowlisted user with a profile; one line per decision."""
    out = []
    names = get_settings().drafting_users
    users = db.scalars(select(models.User).where(models.User.username.in_(names))).all()
    for user in users:
        profile = db.get(models.ApplicantProfile, user.id)
        if profile is None:
            out.append(f"{user.username}: no profile, skipped")
            continue
        for row in rows:
            label = f"{user.username}: {row['company']} ({row['opportunity_id']})"
            exists = db.scalar(
                select(models.ApplicationDraft.id).where(
                    models.ApplicationDraft.user_id == user.id,
                    models.ApplicationDraft.opportunity_id == row["opportunity_id"],
                )
            )
            if exists:
                out.append(f"{label}: already drafted")
                continue
            if models.deadline_passed(row["deadline"]):
                out.append(f"{label}: deadline passed ({row['deadline']}), skipped")
                continue
            offer = Offer(
                row["opportunity_id"], row["company"], row["title"], row["url"], row["deadline"]
            )
            try:
                draft = run_draft(db, user, profile, offer, row["letter"], client)
            except ApiError as err:
                out.append(f"{label}: {err.message}")
                if err.code == ErrorCode.DAILY_LIMIT:
                    break
                continue
            letter = ", with a letter" if row["letter"] else ""
            out.append(
                f"{label}: {draft.status}{letter}" + (f" ({draft.error})" if draft.error else "")
            )
    return out


def main() -> int:
    client = drafter_client(max_attempts=4)
    if client is None or not get_settings().drafting_users:
        print("DRAFTER_URL, DRAFTER_TOKEN or DRAFTING_USERS is not set: nothing to draft.")
        return 0
    try:
        policy = load_policy()
    except PolicyError as err:
        print(err, file=sys.stderr)
        return 0
    with StateStore(policy.state_file) as state:
        run = state.db.execute(
            "SELECT id FROM runs WHERE ended_at IS NOT NULL ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if run is None:
            print("The state file has no finished run: nothing to draft.")
            return 0
        rows = new_top_k(OpportunityStore(state), run["id"])
    with get_sessionmaker()() as db:
        for line in draft_new(db, rows, client):
            print(line)
    print(f"Run {run['id']}: {len(rows)} new top-K offers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
