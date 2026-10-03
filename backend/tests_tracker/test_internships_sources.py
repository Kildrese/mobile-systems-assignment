"""opportunity-sources: watchlist, board collectors, conditional requests, pre-filter,
and Scout proposals. Boards are faked with respx at the pinned public address."""

import httpx
import pytest
import respx

from tests_tracker.conftest import PUBLIC_IP, read_trace, resolver_for
from tests_tracker.internships_helpers import RUN1, RUN2, open_store, posting
from tracker.trace import Trace
from tracker.usecases.internships.http import GuardedHttp, HttpFailure
from tracker.usecases.internships.sources import (
    Filters,
    SourceError,
    WatchlistEntry,
    board_url,
    collect_all,
    collect_source,
    load_watchlist,
    parse_ashby,
    parse_greenhouse,
    parse_lever,
    prefilter,
    propose_source,
    read_watchlist,
)

GREENHOUSE = {
    "jobs": [
        {
            "id": 4012,
            "title": "Software Engineering Intern (Summer 2027)",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/4012",
            "location": {"name": "New York, NY"},
            "updated_at": "2026-09-20T10:00:00-04:00",
            "content": "&lt;p&gt;Join us for &lt;b&gt;Summer 2027&lt;/b&gt;.&lt;/p&gt;",
        },
        {
            "id": 4013,
            "title": "Senior Backend Engineer",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/4013",
            "location": {"name": "New York, NY"},
            "content": "",
        },
    ]
}

LEVER = [
    {
        "id": "a1b2-c3",
        "text": "Machine Learning Intern",
        "hostedUrl": "https://jobs.lever.co/beta/a1b2-c3",
        "categories": {"location": "Brooklyn, NY", "commitment": "Intern"},
        "descriptionPlain": "A summer internship on our ML team.",
        "lists": [{"text": "What you'll do", "content": "<li>Train models</li>"}],
        "additionalPlain": "Must be enrolled in a degree program.",
        "workplaceType": "hybrid",
        "createdAt": 1790000000000,
    }
]

ASHBY = {
    "jobs": [
        {
            "id": "f00d",
            "title": "Product Engineering Intern",
            "jobUrl": "https://jobs.ashbyhq.com/gamma/f00d",
            "location": "",
            "isRemote": True,
            "descriptionPlain": "Remote-friendly internship, Summer 2027.",
            "publishedAt": "2026-09-25T00:00:00Z",
        },
        {
            "id": "dead",
            "title": "Unlisted Intern",
            "jobUrl": "https://jobs.ashbyhq.com/gamma/dead",
            "isListed": False,
        },
    ]
}

JSON = {"content-type": "application/json"}


@pytest.fixture
def http(policy):
    return GuardedHttp(
        policy.fetch, policy.retry, resolver=resolver_for(PUBLIC_IP), sleep=lambda _: None
    )


@pytest.fixture
def store(tmp_path):
    state, store = open_store(tmp_path / "s.sqlite")
    yield store
    state.close()


@pytest.fixture
def trace(tmp_path):
    t = Trace(tmp_path / "trace.jsonl", RUN1)
    yield t
    t.close()


def pinned(url: str) -> str:
    return url.replace(httpx.URL(url).host, PUBLIC_IP)


# Watchlist


def test_watchlist_seeded_from_config(store):
    entries = [
        WatchlistEntry(company="Acme", kind="greenhouse", board="acme"),
        WatchlistEntry(company="Beta", kind="lever", board="beta"),
    ]
    load_watchlist(store, entries, RUN1)
    load_watchlist(store, entries, RUN2)  # idempotent
    sources = store.sources()
    assert [s["added_by"] for s in sources] == ["config", "config"]
    assert [s["added_run"] for s in sources] == [RUN1, RUN1]


def test_shipped_watchlist_is_valid():
    entries = read_watchlist()
    assert len(entries) >= 9
    assert len({(e.kind, e.board.lower()) for e in entries}) == len(entries)
    for entry in entries:
        assert board_url(entry.kind, entry.board).startswith("https://")


@pytest.mark.parametrize("board", ["../admin", "acme/jobs", "a b", "", "x" * 90, "acme?x=1"])
def test_invalid_board_rejected_before_url(board):
    with pytest.raises(ValueError):
        WatchlistEntry(company="Acme", kind="greenhouse", board=board)
    with pytest.raises(SourceError):
        board_url("greenhouse", board)


def test_board_urls():
    assert board_url("greenhouse", "acme").startswith("https://boards-api.greenhouse.io/v1/boards/")
    assert board_url("lever", "beta") == "https://api.lever.co/v0/postings/beta?mode=json"
    assert board_url("ashby", "Gamma").startswith("https://api.ashbyhq.com/posting-api/job-board/")


# Parsers


def test_parse_greenhouse_unescapes_content():
    jobs = parse_greenhouse(GREENHOUSE)
    assert jobs[0].external_id == "4012"
    assert jobs[0].location == "New York, NY"
    assert "Summer 2027" in jobs[0].text
    assert "<b>" not in jobs[0].text


def test_parse_lever_joins_lists():
    [job] = parse_lever(LEVER)
    assert job.title == "Machine Learning Intern"
    assert "Train models" in job.text
    assert "enrolled" in job.text
    assert job.location == "Brooklyn, NY"


def test_parse_ashby_skips_unlisted_and_marks_remote():
    [job] = parse_ashby(ASHBY)
    assert job.external_id == "f00d"
    assert job.location == "Remote"


# Collectors


@respx.mock
def test_collect_all_one_board_down(store, http, trace, tmp_path):
    load_watchlist(
        store,
        [
            WatchlistEntry(company="Acme", kind="greenhouse", board="acme"),
            WatchlistEntry(company="Beta", kind="lever", board="beta"),
            WatchlistEntry(company="Gamma", kind="ashby", board="gamma"),
        ],
        RUN1,
    )
    respx.get(pinned(board_url("greenhouse", "acme"))).respond(200, headers=JSON, json=GREENHOUSE)
    lever = respx.get(pinned(board_url("lever", "beta"))).respond(503)
    respx.get(pinned(board_url("ashby", "gamma"))).respond(200, headers=JSON, json=ASHBY)

    results = collect_all(store, http, trace, RUN1, Filters())

    assert [r.status for r in results] == ["ok", "unreadable", "ok"]
    assert lever.call_count == 3  # retried up to retry.max_attempts
    titles = sorted(p["title"] for p in store.pending_postings(RUN1))
    assert titles == ["Product Engineering Intern", "Software Engineering Intern (Summer 2027)"]
    beta = store.sources()[1]
    assert beta["last_read_status"] == "unreadable"
    events = read_trace(tmp_path / "trace.jsonl")
    prefilter_events = [e for e in events if e.get("tool") == "prefilter"]
    assert prefilter_events[0]["filtered"] == 1  # the senior role


@respx.mock
def test_conditional_request_and_304(store, http, trace, tmp_path):
    source_id, _ = store.add_source(
        company="Acme", kind="greenhouse", board="acme", url=None, added_by="config", run_id=RUN1
    )
    source = store.source(source_id)
    route = respx.get(pinned(board_url("greenhouse", "acme")))
    route.side_effect = [
        httpx.Response(200, headers={**JSON, "etag": '"v1"'}, json=GREENHOUSE),
        httpx.Response(304, headers={"etag": '"v1"'}),
    ]
    first = collect_source(store, source, http, trace, RUN1)
    second = collect_source(store, source, http, trace, RUN2)

    assert first.status == "ok"
    assert route.calls[1].request.headers["if-none-match"] == '"v1"'
    assert second.status == "not_modified"
    assert [p.external_id for p in second.postings] == ["4012", "4013"]  # re-parsed from cache
    statuses = [e["status"] for e in read_trace(tmp_path / "trace.jsonl")]
    assert statuses == ["ok", "not_modified"]


@respx.mock
def test_bad_json_is_unreadable(store, http, trace):
    source_id, _ = store.add_source(
        company="Acme", kind="greenhouse", board="acme", url=None, added_by="config", run_id=RUN1
    )
    respx.get(pinned(board_url("greenhouse", "acme"))).respond(200, headers=JSON, text="{nope")
    result = collect_source(store, store.source(source_id), http, trace, RUN1)
    assert result.status == "unreadable"
    assert result.reason == "bad_response"


def test_collect_respects_guardrails(store, policy, trace):
    # The board host resolves to a private address: blocked, no connection, no crash.
    http = GuardedHttp(policy.fetch, policy.retry, resolver=resolver_for("10.0.0.5"))
    source_id, _ = store.add_source(
        company="Acme", kind="lever", board="acme", url=None, added_by="config", run_id=RUN1
    )
    result = collect_source(store, store.source(source_id), http, trace, RUN1)
    assert result.status == "unreadable"
    assert result.reason == "blocked_address"


@respx.mock
def test_retry_after_and_run_deadline(policy):
    url = board_url("lever", "beta")
    limited = httpx.Response(429, headers={"retry-after": "3"})
    route = respx.get(pinned(url)).mock(
        side_effect=[limited, httpx.Response(200, headers=JSON, json=[])]
    )
    waits = []
    http = GuardedHttp(
        policy.fetch, policy.retry, resolver=resolver_for(PUBLIC_IP), sleep=waits.append
    )
    assert http.get(url).status == 200
    assert waits == [3.0]  # the server's Retry-After, not the backoff

    # A wait that would pass the run's deadline is not taken.
    route.side_effect = [limited]
    late = GuardedHttp(
        policy.fetch,
        policy.retry,
        resolver=resolver_for(PUBLIC_IP),
        sleep=waits.append,
        clock=lambda: 0.0,
        deadline=2.0,
    )
    with pytest.raises(HttpFailure) as err:
        late.get(url)
    assert err.value.reason == "max_wall_seconds"
    assert waits == [3.0]


# Pre-filter


def test_prefilter_titles_and_locations():
    postings = [
        posting("1", title="Senior Backend Engineer", location="New York, NY"),
        posting("2", title="Software Engineering Intern, Summer 2027", location="New York, NY"),
        posting("3", title="Data Science Intern", location=""),
        posting("4", title="Design Intern", location="London, UK"),
        posting("5", title="Internal Tools Engineer", location="New York, NY"),
    ]
    kept, filtered = prefilter(postings, Filters())
    assert [p.external_id for p in kept] == ["2", "3"]
    assert filtered == 3


# Scout proposals


def _propose(store, seen, **overrides):
    args = {
        "company": "Delta",
        "kind": "lever",
        "board_or_url": "delta",
        "evidence_url": "https://news.example.com/delta-hiring",
    }
    args.update(overrides)
    return propose_source(
        store,
        run_id=RUN1,
        seen_urls=seen,
        cap=2,
        **args,
    )


SEEN = {"https://news.example.com/delta-hiring"}


def test_proposal_accepted(store):
    outcome = _propose(store, SEEN)
    assert outcome.ok
    [source] = store.sources()
    assert source["added_by"] == "scout"
    assert source["evidence_url"] == "https://news.example.com/delta-hiring"


def test_proposal_with_unseen_evidence(store):
    outcome = _propose(store, SEEN, evidence_url="https://elsewhere.example.com/")
    assert outcome.reason == "unseen_evidence"
    assert store.sources() == []


def test_proposal_duplicate(store):
    _propose(store, SEEN)
    assert _propose(store, SEEN, board_or_url="DELTA").reason == "duplicate_source"


def test_proposal_cap(store):
    assert _propose(store, SEEN, board_or_url="one").ok
    assert _propose(store, SEEN, board_or_url="two").ok
    assert _propose(store, SEEN, board_or_url="three").reason == "source_cap_reached"


def test_proposal_bad_identifier_and_kind(store):
    assert _propose(store, SEEN, board_or_url="../x").reason == "invalid_board"
    assert _propose(store, SEEN, kind="workday").reason == "unknown_kind"


def test_scout_cannot_propose_a_page(store):
    # A page the Scout read could otherwise put itself on the watchlist for every run.
    outcome = _propose(store, SEEN, kind="page", board_or_url="https://evil.example.com/careers")
    assert outcome.reason == "unknown_kind"
    assert store.sources() == []
