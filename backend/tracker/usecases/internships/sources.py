"""Where opportunities come from: the watchlist, the job-board collectors, the pre-filter.

Collectors read public board APIs (Greenhouse, Lever, Ashby) without keys and without
a model. Every request goes through `GuardedHttp`, so the core fetch guardrails apply.
Responses are cached with their validators: a `304` re-parses the stored body, so a
board that did not change still counts as read and still lists its postings.
"""

import html
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from tracker.fetch import extract
from tracker.state import canonicalize, fetch_status, log_fetch
from tracker.tools import ToolOutcome
from tracker.trace import Trace
from tracker.usecases.internships.http import GuardedHttp, HttpFailure
from tracker.usecases.internships.store import OpportunityStore, RawPosting

BOARD_KINDS = ("greenhouse", "lever", "ashby")
BOARD_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
BOARD_API_HOSTS = {
    "greenhouse": "boards-api.greenhouse.io",
    "lever": "api.lever.co",
    "ashby": "api.ashbyhq.com",
}
# Hosts where a posting's own page lives, for the Curator's detail fetches.
POSTING_HOSTS = (
    "boards.greenhouse.io",
    "job-boards.greenhouse.io",
    "jobs.lever.co",
    "jobs.ashbyhq.com",
)


class SourceError(ValueError):
    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


def check_board_id(board: str) -> str:
    """Validate a board identifier before any URL is built from it."""
    if not BOARD_ID.fullmatch(board or ""):
        raise SourceError("invalid_board", f"'{board}' is not a valid board identifier")
    return board


def board_url(kind: str, board: str) -> str:
    board = quote(check_board_id(board), safe="")
    if kind == "greenhouse":
        return f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
    if kind == "lever":
        return f"https://api.lever.co/v0/postings/{board}?mode=json"
    if kind == "ashby":
        return f"https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true"
    raise SourceError("unknown_kind", f"'{kind}' is not a job board")


# Watchlist


class WatchlistEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    company: str = Field(min_length=1, max_length=120)
    kind: Literal["greenhouse", "lever", "ashby"]
    board: str

    @field_validator("board")
    @classmethod
    def board_id(cls, board: str) -> str:
        return check_board_id(board)


WATCHLIST_FILE = Path(__file__).with_name("watchlist.yaml")


def read_watchlist(path: Path = WATCHLIST_FILE) -> list[WatchlistEntry]:
    """The seed watchlist shipped with the use case. Raises on any invalid entry."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return [WatchlistEntry.model_validate(entry) for entry in data]


def load_watchlist(store: OpportunityStore, entries: list[WatchlistEntry], run_id: str) -> None:
    """Seed the watchlist from config. Existing sources are left as they are."""
    for entry in entries:
        store.add_source(
            company=entry.company,
            kind=entry.kind,
            board=entry.board,
            added_by="config",
            run_id=run_id,
        )


# Board responses


def _text_from_html(markup: str) -> str:
    return extract(f"<html><body>{markup}</body></html>")[1]


class _Loose(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _GreenhouseLocation(_Loose):
    name: str = ""


class _GreenhouseJob(_Loose):
    id: int | str
    title: str
    absolute_url: str
    location: _GreenhouseLocation | None = None
    content: str = ""


class _GreenhouseBoard(_Loose):
    jobs: list[_GreenhouseJob]


class _LeverCategories(_Loose):
    location: str | None = None
    allLocations: list[str] = Field(default_factory=list)
    commitment: str | None = None


class _LeverList(_Loose):
    text: str = ""
    content: str = ""


class _LeverJob(_Loose):
    id: str
    text: str
    hostedUrl: str
    categories: _LeverCategories = Field(default_factory=_LeverCategories)
    descriptionPlain: str = ""
    lists: list[_LeverList] = Field(default_factory=list)
    additionalPlain: str = ""
    workplaceType: str | None = None


class _AshbyLocation(_Loose):
    location: str = ""


class _AshbyJob(_Loose):
    id: str
    title: str
    jobUrl: str
    location: str = ""
    secondaryLocations: list[_AshbyLocation] = Field(default_factory=list)
    isRemote: bool | None = None
    descriptionPlain: str = ""
    descriptionHtml: str = ""
    isListed: bool = True


class _AshbyBoard(_Loose):
    jobs: list[_AshbyJob]


def parse_greenhouse(body: Any) -> list[RawPosting]:
    board = _GreenhouseBoard.model_validate(body)
    return [
        RawPosting(
            external_id=str(job.id),
            title=job.title,
            url=job.absolute_url,
            # `content` is HTML, escaped once more by the API.
            text=_text_from_html(html.unescape(job.content)),
            location=job.location.name if job.location else "",
        )
        for job in board.jobs
    ]


def parse_lever(body: Any) -> list[RawPosting]:
    if not isinstance(body, list):
        raise ValueError("a Lever board is a JSON list")
    postings = []
    for raw in body:
        job = _LeverJob.model_validate(raw)
        parts = [job.descriptionPlain]
        for item in job.lists:
            parts += [item.text, _text_from_html(item.content)]
        parts.append(job.additionalPlain)
        locations = job.categories.allLocations or [job.categories.location or ""]
        location = "; ".join(loc for loc in locations if loc)
        if job.workplaceType == "remote" and "remote" not in location.lower():
            location = f"{location}; Remote" if location else "Remote"
        postings.append(
            RawPosting(
                external_id=job.id,
                title=job.text,
                url=job.hostedUrl,
                text="\n".join(p for p in parts if p),
                location=location,
            )
        )
    return postings


def parse_ashby(body: Any) -> list[RawPosting]:
    board = _AshbyBoard.model_validate(body)
    postings = []
    for job in board.jobs:
        if not job.isListed:
            continue
        locations = [job.location, *(s.location for s in job.secondaryLocations)]
        location = "; ".join(loc for loc in locations if loc)
        if job.isRemote and "remote" not in location.lower():
            location = f"{location}; Remote" if location else "Remote"
        text = job.descriptionPlain or _text_from_html(job.descriptionHtml)
        postings.append(
            RawPosting(
                external_id=job.id,
                title=job.title,
                url=job.jobUrl,
                text=text,
                location=location,
            )
        )
    return postings


PARSERS: dict[str, Callable[[Any], list[RawPosting]]] = {
    "greenhouse": parse_greenhouse,
    "lever": parse_lever,
    "ashby": parse_ashby,
}


# Collecting


@dataclass
class CollectResult:
    source_id: int
    status: str  # ok | not_modified | unreadable
    postings: list[RawPosting] = field(default_factory=list)
    reason: str | None = None

    @property
    def readable(self) -> bool:
        return self.status in ("ok", "not_modified")


# Failures that will not change by themselves: the board is gone, too big, or not a board.
PERMANENT_REASONS = {"too_large", "unsupported_content_type", "bad_response"}
GONE = (404, 410)


def _unreadable(
    store: OpportunityStore, source: dict[str, Any], run_id: str, reason: str, status: int | None
) -> bool:
    """Mark the source unreadable. A board the Scout added that never worked and fails
    for good is deactivated, so it does not cost a request and a warning every run;
    config sources, and boards that worked before, stay. Returns whether it was."""
    store.mark_source_read(source["id"], run_id, "unreadable")
    never_read = source["last_read_status"] not in ("ok", "not_modified")
    permanent = reason in PERMANENT_REASONS or status in GONE
    if source["added_by"] == "scout" and never_read and permanent:
        store.deactivate_source(source["id"])
        return True
    return False


def collect_source(
    store: OpportunityStore,
    source: dict[str, Any],
    http: GuardedHttp,
    trace: Trace,
    run_id: str,
) -> CollectResult:
    """Read one source. A failure marks it `unreadable` and never raises."""
    url = board_url(source["kind"], source["board"])
    cached = store.http_cache(url)
    event: dict[str, Any] = {"source": source["key"], "url": url}
    title = f"{source['company']} ({source['kind'].capitalize()} board)"

    def log(status: str, reason: str | None = None) -> None:
        log_fetch(store.db, run_id, "collect", "board", url, title, status, reason)

    try:
        result = http.get(
            url,
            etag=cached["etag"] if cached else None,
            last_modified=cached["last_modified"] if cached else None,
        )
    except HttpFailure as err:
        trace.event(
            "tool",
            tool="collect",
            args=event,
            status="error",
            reason=err.reason,
            detail=err.detail,
            http_status=err.status,
            attempt=err.attempts,
            deactivated=_unreadable(store, source, run_id, err.reason, err.status),
        )
        log(fetch_status("error", err.reason), err.reason)
        return CollectResult(source["id"], "unreadable", reason=err.reason)

    not_modified = result.status == 304 and cached is not None
    body = cached["body"] if not_modified else result.text
    try:
        postings = PARSERS[source["kind"]](json.loads(body))
    except (ValueError, ValidationError) as err:  # JSONDecodeError is a ValueError
        trace.event(
            "tool",
            tool="collect",
            args=event,
            status="error",
            reason="bad_response",
            detail=str(err)[:300],
            deactivated=_unreadable(store, source, run_id, "bad_response", None),
        )
        log("failed", "bad_response")
        return CollectResult(source["id"], "unreadable", reason="bad_response")

    if not not_modified:
        store.put_http_cache(url, result.etag, result.last_modified, body)
    status = "not_modified" if not_modified else "ok"
    store.mark_source_read(source["id"], run_id, status)
    log(fetch_status(status))
    trace.event(
        "tool",
        tool="collect",
        args=event,
        status=status,
        http_status=result.status,
        attempt=result.attempts,
        latency_ms=result.latency_ms,
        postings=len(postings),
    )
    return CollectResult(source["id"], status, postings)


# Pre-filter


class Filters(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title_keywords: tuple[str, ...] = ("intern", "internship", "co-op")
    locations: tuple[str, ...] = ("New York", "NYC", "Brooklyn", "Remote")


def keyword(word: str) -> re.Pattern[str]:
    """A case-insensitive whole-word match: "intern" matches "Intern," but not "internal"."""
    return re.compile(rf"(?<![a-z]){re.escape(word.lower())}(?![a-z])", re.IGNORECASE)


def prefilter(postings: list[RawPosting], filters: Filters) -> tuple[list[RawPosting], int]:
    """Keep postings with a matching title and a matching or missing location."""
    titles = [keyword(w) for w in filters.title_keywords]
    places = [p.lower() for p in filters.locations]
    kept = []
    for p in postings:
        if not any(k.search(p.title) for k in titles):
            continue
        if p.location.strip() and not any(place in p.location.lower() for place in places):
            continue
        kept.append(p)
    return kept, len(postings) - len(kept)


def collect_all(
    store: OpportunityStore,
    http: GuardedHttp,
    trace: Trace,
    run_id: str,
    filters: Filters,
) -> list[CollectResult]:
    """Read every active source, pre-filter, and store what is kept. The Collect stage."""
    results = []
    for source in store.sources():
        result = collect_source(store, source, http, trace, run_id)
        if result.readable:
            kept, dropped = prefilter(result.postings, filters)
            for posting_id in store.upsert_postings(source["id"], kept, run_id):
                p = store.posting(posting_id)
                assert p is not None
                status = "fetched" if p["first_seen_run"] == run_id else "skipped"
                log_fetch(store.db, run_id, "collect", "posting", p["url"], p["title"], status)
            trace.event(
                "tool",
                tool="prefilter",
                args={"source": source["key"]},
                status="ok",
                kept=len(kept),
                filtered=dropped,
            )
        results.append(result)
    return results


# Source proposals from the Scout


def propose_source(
    store: OpportunityStore,
    *,
    run_id: str,
    seen_urls: set[str],
    cap: int,
    company: str,
    kind: str,
    board: str,
    evidence_url: str,
) -> ToolOutcome:
    """Validate a Scout proposal and add the job board to the watchlist.

    `seen_urls` holds canonical URLs returned by search or fetched in this run.
    """
    company = company.strip()
    if not company or len(company) > 120:
        return ToolOutcome.failure("error", "invalid_arguments", "company is required")
    if kind not in BOARD_KINDS:
        return ToolOutcome.failure(
            "error", "unknown_kind", f"kind must be one of {', '.join(BOARD_KINDS)}"
        )
    if canonicalize(evidence_url) not in seen_urls:
        return ToolOutcome.failure(
            "error",
            "unseen_evidence",
            "evidence_url must be a URL returned by search_web or fetched in this run",
        )
    board = board.strip()
    try:
        check_board_id(board)
    except SourceError as err:
        return ToolOutcome.failure("error", err.reason, err.detail)
    if store.has_source(kind, board):
        return ToolOutcome.failure("error", "duplicate_source", "already on the watchlist")
    if store.count_sources_added(run_id, "scout") >= cap:
        return ToolOutcome.failure(
            "budget", "source_cap_reached", f"at most {cap} new sources per run"
        )
    source_id, _ = store.add_source(
        company=company,
        kind=kind,
        board=board,
        added_by="scout",
        run_id=run_id,
        evidence_url=evidence_url,
    )
    return ToolOutcome(
        "ok", {"source_id": source_id, "company": company, "kind": kind, "added": True}
    )
