"""opportunity-lifecycle: closing from boards and pages, unreadable sources, reopening."""

import httpx
import pytest
import respx

from tests_tracker.conftest import PUBLIC_IP, resolver_for
from tests_tracker.internships_helpers import RUN1, RUN2, add_board, open_store, posting, record
from tracker.usecases.internships.curation import save_record
from tracker.usecases.internships.http import GuardedHttp
from tracker.usecases.internships.lifecycle import LifecycleSettings, run_liveness

RUN3 = "20261003T120000Z-cccc"


class NoHttp:
    def get(self, url, **_):
        raise AssertionError(f"no request expected, got {url}")


@pytest.fixture
def store(tmp_path):
    state, store = open_store(tmp_path / "s.sqlite")
    yield store
    state.close()


def board_opportunity(store):
    """An opportunity listed on one Greenhouse board, created in RUN1."""
    source_id = add_board(store)
    [pid] = store.upsert_postings(source_id, [posting("1")], RUN1)
    store.mark_source_read(source_id, RUN1, "ok")
    oid = save_record(store, pid, record(), RUN1).data["opportunity_id"]
    return source_id, oid


def read_board(store, source_id, run_id, *, listed, status="ok"):
    store.mark_source_read(source_id, run_id, status)
    if listed:
        store.upsert_postings(source_id, [posting("1")], run_id)


def test_posting_taken_down(store):
    source_id, oid = board_opportunity(store)
    read_board(store, source_id, RUN2, listed=False)
    counts = run_liveness(store, RUN2, NoHttp(), LifecycleSettings())
    opp = store.opportunity(oid)
    assert opp["status"] == "closed"
    assert opp["closed_run"] == RUN2
    assert "Acme board" in opp["status_evidence"]
    assert counts.closed == 1


def test_still_listed_after_304(store):
    source_id, oid = board_opportunity(store)
    read_board(store, source_id, RUN2, listed=True, status="not_modified")
    run_liveness(store, RUN2, NoHttp(), LifecycleSettings())
    opp = store.opportunity(oid)
    assert opp["status"] == "open"
    assert opp["last_seen_open_run"] == RUN2
    assert opp["checked_run"] == RUN2


def test_board_unreachable_leaves_status(store):
    source_id, oid = board_opportunity(store)
    read_board(store, source_id, RUN2, listed=False, status="unreadable")
    counts = run_liveness(store, RUN2, NoHttp(), LifecycleSettings())
    opp = store.opportunity(oid)
    assert opp["status"] == "open"
    assert opp["checked_run"] == RUN1  # not verified in RUN2
    assert "not readable" in opp["status_evidence"]
    assert counts.unchanged == 1


def test_one_of_two_boards_unreadable_does_not_close(store):
    source_id, oid = board_opportunity(store)
    other, _ = store.add_source(
        company="Acme", kind="lever", board="acme", url=None, added_by="config", run_id=RUN1
    )
    [pid2] = store.upsert_postings(other, [posting("L1")], RUN1)
    store.link(oid, pid2, "curator", "same role")
    read_board(store, source_id, RUN2, listed=False)
    store.mark_source_read(other, RUN2, "unreadable")
    run_liveness(store, RUN2, NoHttp(), LifecycleSettings())
    assert store.opportunity(oid)["status"] == "open"


def test_reposted_reopens_without_becoming_new(store):
    source_id, oid = board_opportunity(store)
    read_board(store, source_id, RUN2, listed=False)
    run_liveness(store, RUN2, NoHttp(), LifecycleSettings())
    read_board(store, source_id, RUN3, listed=True)
    counts = run_liveness(store, RUN3, NoHttp(), LifecycleSettings())
    opp = store.opportunity(oid)
    assert opp["status"] == "open"
    assert opp["first_seen_run"] == RUN1
    assert opp["closed_run"] is None
    assert counts.opened == 1


def test_closed_run_kept_on_later_runs(store):
    source_id, oid = board_opportunity(store)
    read_board(store, source_id, RUN2, listed=False)
    run_liveness(store, RUN2, NoHttp(), LifecycleSettings())
    read_board(store, source_id, RUN3, listed=False)
    run_liveness(store, RUN3, NoHttp(), LifecycleSettings())
    assert store.opportunity(oid)["closed_run"] == RUN2


# Page-only opportunities

PAGE_URL = "https://careers.example.com/jobs/intern"


def page_opportunity(store):
    source_id, _ = store.add_source(
        company="Delta", kind="page", board=None, url=PAGE_URL, added_by="scout", run_id=RUN1
    )
    [pid] = store.upsert_postings(
        source_id,
        [posting("p1", url=PAGE_URL, location="")],
        RUN1,
    )
    return save_record(store, pid, record(), RUN1).data["opportunity_id"]


@pytest.fixture
def http(policy):
    return GuardedHttp(
        policy.fetch, policy.retry, resolver=resolver_for(PUBLIC_IP), sleep=lambda _: None
    )


PINNED = f"https://{PUBLIC_IP}/jobs/intern"
HTML = {"content-type": "text/html"}


@respx.mock
def test_page_closing_wording(store, http):
    oid = page_opportunity(store)
    respx.get(PINNED).respond(
        200,
        headers=HTML,
        content=b"<html><body><p>This position is no longer accepting applications.</p>"
        b"</body></html>",
    )
    run_liveness(store, RUN2, http, LifecycleSettings())
    opp = store.opportunity(oid)
    assert opp["status"] == "closed"
    assert "no longer accepting applications" in opp["status_evidence"]


@respx.mock
def test_page_410_closes(store, http):
    oid = page_opportunity(store)
    respx.get(PINNED).respond(410)
    run_liveness(store, RUN2, http, LifecycleSettings())
    assert store.opportunity(oid)["status"] == "closed"


@respx.mock
def test_page_timeout_is_unknown(store, http):
    oid = page_opportunity(store)
    respx.get(PINNED).mock(side_effect=httpx.ReadTimeout("slow"))
    run_liveness(store, RUN2, http, LifecycleSettings())
    opp = store.opportunity(oid)
    assert opp["status"] == "unknown"
    assert opp["closed_run"] is None


@respx.mock
def test_page_still_up_with_conditional_request(store, http):
    oid = page_opportunity(store)
    route = respx.get(PINNED)
    route.side_effect = [
        httpx.Response(200, headers={**HTML, "etag": '"p1"'}, content=b"<p>Apply now</p>"),
        httpx.Response(304),
    ]
    run_liveness(store, RUN2, http, LifecycleSettings())
    run_liveness(store, RUN3, http, LifecycleSettings())
    assert route.calls[1].request.headers["if-none-match"] == '"p1"'
    assert store.opportunity(oid)["status"] == "open"


def test_new_opportunity_stays_open(store):
    _, oid = board_opportunity(store)
    run_liveness(store, RUN1, NoHttp(), LifecycleSettings())
    assert store.opportunity(oid)["status"] == "open"
