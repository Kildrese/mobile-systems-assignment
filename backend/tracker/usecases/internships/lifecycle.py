"""Open or closed: decided by code from what the job boards say, never by a model.

An opportunity closes only when every board it is listed on was read in this run and
none of them lists the job any more; a board that could not be read changes nothing.
An opportunity seen again reopens and keeps its first-seen run, so it is never new twice.
"""

from dataclasses import dataclass
from typing import Any

from tracker.usecases.internships.store import OpportunityStore

READ_OK = ("ok", "not_modified")


@dataclass
class LivenessCounts:
    reopened: int = 0
    closed: int = 0
    unchanged: int = 0


def _change(
    store: OpportunityStore,
    counts: LivenessCounts,
    opp: dict[str, Any],
    status: str,
    run_id: str,
    evidence: str,
) -> None:
    previous = opp["status"]
    if status == "closed" and previous == "closed":
        return  # still closed: keep the run it closed in and its evidence
    store.set_status(opp["id"], status, run_id, evidence)
    if status == "closed":
        counts.closed += 1
    else:
        counts.reopened += previous != "open"


def run_liveness(store: OpportunityStore, run_id: str) -> LivenessCounts:
    """The Liveness stage. Makes no requests: Collect has read the boards."""
    counts = LivenessCounts()
    for opp in store.opportunities():
        links = store.linked_postings(opp["id"])
        if not links:
            continue
        read = [
            p for p in links if p["last_read_run"] == run_id and p["last_read_status"] in READ_OK
        ]
        listed = [p for p in read if p["seen_run"] == run_id]
        if listed:
            _change(store, counts, opp, "open", run_id, f"listed on {listed[0]['url']}")
        elif read and len(read) == len(links):
            boards = ", ".join(sorted({p["company"] + " board" for p in read}))
            _change(store, counts, opp, "closed", run_id, f"absent from {boards} read in {run_id}")
        else:
            counts.unchanged += 1
            store.set_status(
                opp["id"],
                opp["status"],
                run_id,
                "board not readable in this run; status unchanged",
                checked=False,
            )
    return counts
