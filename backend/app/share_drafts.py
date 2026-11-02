"""Let one user read (only) another user's drafts, or stop it:

    uv run python -m app.share_drafts <owner> <viewer> [--remove]

Run against production like the migrations (DATABASE_URL in the environment). A viewer
can list and download the owner's drafts; never the owner's profile files, never start
a draft for the owner, and never change this list. There is no API for it on purpose.
"""

import argparse
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.db import get_sessionmaker


def share(db: Session, owner: str, viewer: str, remove: bool = False) -> str:
    users = {
        u.username: u
        for u in db.scalars(
            select(models.User).where(models.User.username.in_([owner.lower(), viewer.lower()]))
        )
    }
    if missing := [n for n in (owner.lower(), viewer.lower()) if n not in users]:
        raise SystemExit(f"No user named {missing[0]}.")
    profile = db.get(models.ApplicantProfile, users[owner.lower()].id)
    if profile is None:
        raise SystemExit(f"{owner} has no profile yet; upload it on /account first.")
    viewer_id = users[viewer.lower()].id
    ids = [i for i in profile.viewer_ids if i != viewer_id]
    profile.viewer_ids = ids if remove else [*ids, viewer_id]
    db.commit()
    names = db.scalars(select(models.User.username).where(models.User.id.in_(profile.viewer_ids)))
    return f"{owner}'s drafts are readable by: {', '.join(sorted(names)) or 'no one'}."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("owner")
    parser.add_argument("viewer")
    parser.add_argument("--remove", action="store_true", help="stop sharing")
    args = parser.parse_args(argv)
    with get_sessionmaker()() as db:
        print(share(db, args.owner, args.viewer, args.remove))
    return 0


if __name__ == "__main__":
    sys.exit(main())
