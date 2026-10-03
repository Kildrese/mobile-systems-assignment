"""Shared helpers for the internship use-case tests."""

from pathlib import Path
from typing import Any

from tracker.state import StateStore
from tracker.usecases.internships.store import OpportunityStore, RawPosting

RUN1 = "20261001T120000Z-aaaa"
RUN2 = "20261002T120000Z-bbbb"


def open_store(path: Path) -> tuple[StateStore, OpportunityStore]:
    state = StateStore(path)
    return state, OpportunityStore(state)


def posting(external_id: str = "1", **overrides: Any) -> RawPosting:
    values: dict[str, Any] = {
        "external_id": external_id,
        "title": "Software Engineering Intern, Summer 2027",
        "url": f"https://boards.greenhouse.io/acme/jobs/{external_id}",
        "text": (
            "Software Engineering Intern, Summer 2027. Location: New York, NY. "
            "This is a 12-week paid internship. Pay: $45/hour. "
            "Candidates must be authorized to work in the US."
        ),
        "location": "New York, NY",
    }
    values.update(overrides)
    return RawPosting(**values)


def record(**overrides: Any) -> dict[str, Any]:
    """A record whose quotes all appear in `posting()`'s text."""
    values: dict[str, Any] = {
        "title": {
            "value": "Software Engineering Intern",
            "quote": "Software Engineering Intern, Summer 2027",
        },
        "role_type": {"value": "internship", "quote": "12-week paid internship"},
        "term": {"value": "Summer 2027", "quote": "Summer 2027"},
        "locations": {"value": ["New York, NY"], "quote": "Location: New York, NY"},
        "remote": {"value": "unknown"},
        "compensation": {"value": "$45/hour", "quote": "Pay: $45/hour"},
        "deadline": {"value": "unknown"},
        "work_authorization": {
            "value": "authorized to work in the US",
            "quote": "must be authorized to work in the US",
        },
    }
    values.update(overrides)
    return values


def add_board(store: OpportunityStore, board: str = "acme", company: str = "Acme") -> int:
    source_id, _ = store.add_source(
        company=company, kind="greenhouse", board=board, url=None, added_by="config", run_id=RUN1
    )
    return source_id
