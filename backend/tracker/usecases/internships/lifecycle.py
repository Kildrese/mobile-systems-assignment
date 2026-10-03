"""Open, closed or unknown: decided by code from what the sources say, never by a model.

Board-listed opportunities close only when every board they are listed on was read in
this run and none of them lists the job any more; a board that could not be read
changes nothing. Page-only opportunities are re-checked with a conditional request:
404, 410 or closing wording closes them, any other failure makes them `unknown`.
An opportunity seen again reopens and keeps its first-seen run, so it is never new twice.
"""

import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict

from tracker.trace import Trace
from tracker.usecases.internships.http import GuardedHttp, HttpFailure
from tracker.usecases.internships.store import OpportunityStore

READ_OK = ("ok", "not_modified")
GONE = (404, 410)


class LifecycleSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    closed_patterns: tuple[str, ...] = (
        "no longer accepting applications",
        "no longer accepting",
        "position has been filled",
        "job is closed",
        "this job is no longer available",
    )


@dataclass
class LivenessCounts:
    opened: int = 0
    closed: int = 0
    unchanged: int = 0
    unknown: int = 0
    requests: int = 0


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
    if status == "open":
        counts.opened += previous != "open"
    elif status == "closed":
        counts.closed += 1
    else:
        counts.unknown += 1


def board_liveness(store: OpportunityStore, run_id: str, counts: LivenessCounts) -> None:
    for opp in store.opportunities():
        links = [p for p in store.linked_postings(opp["id"]) if p["source_kind"] != "page"]
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


def _closing_phrase(text: str, patterns: tuple[str, ...]) -> str | None:
    for pattern in patterns:
        match = re.search(re.escape(pattern), text, re.IGNORECASE)
        if match:
            start = max(0, match.start() - 40)
            return " ".join(text[start : match.end() + 40].split())
    return None


def page_liveness(
    store: OpportunityStore,
    run_id: str,
    http: GuardedHttp,
    settings: LifecycleSettings,
    counts: LivenessCounts,
    trace: Trace | None = None,
) -> None:
    for opp in store.opportunities():
        links = store.linked_postings(opp["id"])
        if not links or any(p["source_kind"] != "page" for p in links):
            continue
        url = links[0]["url"]
        cached = store.http_cache(url)
        counts.requests += 1
        try:
            result = http.get(
                url,
                etag=cached["etag"] if cached else None,
                last_modified=cached["last_modified"] if cached else None,
            )
        except HttpFailure as err:
            if trace is not None:
                trace.event(
                    "tool",
                    tool="liveness",
                    args={"url": url},
                    status="error",
                    reason=err.reason,
                    http_status=err.status,
                )
            if err.status in GONE:
                _change(store, counts, opp, "closed", run_id, f"HTTP {err.status} at {url}")
            else:
                _change(
                    store, counts, opp, "unknown", run_id, f"could not check {url}: {err.reason}"
                )
            continue
        if result.status == 304 and cached is not None:
            text = cached["body"]
        else:
            text = result.text
            store.put_http_cache(url, result.etag, result.last_modified, text)
        if trace is not None:
            trace.event(
                "tool",
                tool="liveness",
                args={"url": url},
                status="not_modified" if result.status == 304 else "ok",
                http_status=result.status,
            )
        if phrase := _closing_phrase(text, settings.closed_patterns):
            _change(store, counts, opp, "closed", run_id, f'page says "{phrase}"')
        else:
            _change(store, counts, opp, "open", run_id, f"page still up at {url}")


def run_liveness(
    store: OpportunityStore,
    run_id: str,
    http: GuardedHttp,
    settings: LifecycleSettings,
    trace: Trace | None = None,
) -> LivenessCounts:
    """The Liveness stage: boards first (no requests), then page-only opportunities."""
    counts = LivenessCounts()
    board_liveness(store, run_id, counts)
    page_liveness(store, run_id, http, settings, counts, trace)
    return counts
