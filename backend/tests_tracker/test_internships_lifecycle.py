"""opportunity-lifecycle: closing from boards, unreadable boards, reopening."""

import pytest

from tests_tracker.internships_helpers import RUN1, RUN2, add_board, open_store, posting, record
from tracker.usecases.internships.curation import save_record
from tracker.usecases.internships.lifecycle import run_liveness

RUN3 = "20261003T120000Z-cccc"


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
    counts = run_liveness(store, RUN2)
    opp = store.opportunity(oid)
    assert opp["status"] == "closed"
    assert opp["closed_run"] == RUN2
    assert "Acme board" in opp["status_evidence"]
    assert counts.closed == 1


def test_still_listed_after_304(store):
    source_id, oid = board_opportunity(store)
    read_board(store, source_id, RUN2, listed=True, status="not_modified")
    run_liveness(store, RUN2)
    opp = store.opportunity(oid)
    assert opp["status"] == "open"
    assert opp["checked_run"] == RUN2


def test_board_unreachable_leaves_status(store):
    source_id, oid = board_opportunity(store)
    read_board(store, source_id, RUN2, listed=False, status="unreadable")
    counts = run_liveness(store, RUN2)
    opp = store.opportunity(oid)
    assert opp["status"] == "open"
    assert opp["checked_run"] == RUN1  # not verified in RUN2
    assert "not readable" in opp["status_evidence"]
    assert counts.unchanged == 1


def test_one_of_two_boards_unreadable_does_not_close(store):
    source_id, oid = board_opportunity(store)
    other, _ = store.add_source(
        company="Acme", kind="lever", board="acme", added_by="config", run_id=RUN1
    )
    [pid2] = store.upsert_postings(other, [posting("L1")], RUN1)
    store.link(oid, pid2, "curator", "same role")
    read_board(store, source_id, RUN2, listed=False)
    store.mark_source_read(other, RUN2, "unreadable")
    run_liveness(store, RUN2)
    assert store.opportunity(oid)["status"] == "open"


def test_reposted_reopens_without_becoming_new(store):
    source_id, oid = board_opportunity(store)
    read_board(store, source_id, RUN2, listed=False)
    run_liveness(store, RUN2)
    read_board(store, source_id, RUN3, listed=True)
    counts = run_liveness(store, RUN3)
    opp = store.opportunity(oid)
    assert opp["status"] == "open"
    assert opp["first_seen_run"] == RUN1
    assert opp["closed_run"] is None
    assert counts.reopened == 1


def test_closed_run_kept_on_later_runs(store):
    source_id, oid = board_opportunity(store)
    read_board(store, source_id, RUN2, listed=False)
    run_liveness(store, RUN2)
    read_board(store, source_id, RUN3, listed=False)
    run_liveness(store, RUN3)
    assert store.opportunity(oid)["closed_run"] == RUN2


def test_new_opportunity_stays_open(store):
    _, oid = board_opportunity(store)
    run_liveness(store, RUN1)
    assert store.opportunity(oid)["status"] == "open"


def test_closed_and_then_unreadable_is_not_closed_again(store):
    # It closed in RUN2. Its board is unreadable in RUN3: it must not count as closed in
    # RUN3 too, or the report lists it under "Closed since last run" twice.
    source_id, oid = board_opportunity(store)
    read_board(store, source_id, RUN2, listed=False)
    run_liveness(store, RUN2)
    read_board(store, source_id, RUN3, listed=False, status="unreadable")
    run_liveness(store, RUN3)
    opp = store.opportunity(oid)
    assert (opp["status"], opp["closed_run"]) == ("closed", RUN2)
