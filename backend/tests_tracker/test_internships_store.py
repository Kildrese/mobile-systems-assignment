"""The internship tables: own versioned schema over the core state file."""

import sqlite3

from tests_tracker.internships_helpers import RUN1, RUN2, add_board, open_store, posting, record
from tracker import state as core_state
from tracker.state import StateStore
from tracker.usecases.internships.store import MIGRATIONS, OpportunityStore


def test_core_state_file_upgrades_in_place(tmp_path):
    path = tmp_path / "state.sqlite"
    core = StateStore(path)
    core.start_run(RUN1, "topic", 5)
    core.put_article("https://example.com/a", "A", "text", RUN1)
    core.close()

    state, store = open_store(path)
    try:
        assert state.get_article("https://example.com/a")["title"] == "A"
        version = state.db.execute(
            "SELECT version FROM component_versions WHERE name = 'internships'"
        ).fetchone()[0]
        assert version == len(MIGRATIONS)
        assert store.sources() == []
        # The core's own schema version is untouched.
        user_version = state.db.execute("PRAGMA user_version").fetchone()[0]
        assert user_version == len(core_state.MIGRATIONS)
    finally:
        state.close()


def test_migration_runs_once(tmp_path):
    path = tmp_path / "state.sqlite"
    state, _ = open_store(path)
    state.close()
    state, store = open_store(path)  # second open: tables exist, nothing re-created
    try:
        assert store.sources() == []
    finally:
        state.close()


def test_external_id_unique_per_source(tmp_path):
    state, store = open_store(tmp_path / "s.sqlite")
    try:
        source_id = add_board(store)
        first = store.upsert_postings(source_id, [posting("1")], RUN1)
        again = store.upsert_postings(source_id, [posting("1", title="Renamed")], RUN2)
        assert first == again
        row = store.posting(first[0])
        assert row["title"] == "Renamed"
        assert row["first_seen_run"] == RUN1
        assert row["seen_run"] == RUN2
        try:
            state.db.execute(
                "INSERT INTO raw_postings (source_id, external_id, url, canonical_url, title, "
                "text, first_seen_run, seen_run) VALUES (?, '1', 'u', 'u', 't', 'x', ?, ?)",
                (source_id, RUN1, RUN1),
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("duplicate (source_id, external_id) was accepted")
    finally:
        state.close()


def test_pending_postings_survive_across_runs(tmp_path):
    path = tmp_path / "s.sqlite"
    state, store = open_store(path)
    source_id = add_board(store)
    ids = store.upsert_postings(source_id, [posting("1"), posting("2")], RUN1)
    store.set_curation(ids[0], "unclear", unclear_reason="no term")
    state.close()

    state, store = open_store(path)
    try:
        assert [p["id"] for p in store.pending_postings(RUN1)] == [ids[1]]
        # Not listed in RUN2 (yet): not worth curating in it.
        assert store.pending_postings(RUN2) == []
        store.upsert_postings(source_id, [posting("2")], RUN2)
        assert [p["id"] for p in store.pending_postings(RUN2)] == [ids[1]]
    finally:
        state.close()


def test_sources_are_unique_by_key(tmp_path):
    state, store = open_store(tmp_path / "s.sqlite")
    try:
        first, new = store.add_source(
            company="Acme", kind="lever", board="Acme", added_by="config", run_id=RUN1
        )
        second, again = store.add_source(
            company="Acme", kind="lever", board="acme", added_by="scout", run_id=RUN2
        )
        assert new and not again and first == second
        assert store.has_source("lever", "ACME")
    finally:
        state.close()


def test_opportunity_lifecycle_columns(tmp_path):
    state, store = open_store(tmp_path / "s.sqlite")
    try:
        source_id = add_board(store)
        [pid] = store.upsert_postings(source_id, [posting("1")], RUN1)
        oid = store.create_opportunity(
            company="Acme",
            url="https://boards.greenhouse.io/acme/jobs/1",
            record=record(),
            run_id=RUN1,
            posting_id=pid,
            linked_by="record",
        )
        opp = store.opportunity(oid)
        assert opp["status"] == "open"
        assert opp["first_seen_run"] == RUN1
        assert opp["locations"] == ["New York, NY"]
        assert store.posting(pid)["curation"] == "saved"

        store.set_status(oid, "closed", RUN2, "absent from board")
        assert store.opportunity(oid)["closed_run"] == RUN2
        store.set_status(oid, "open", RUN2, "listed again")
        reopened = store.opportunity(oid)
        assert reopened["closed_run"] is None
        assert reopened["first_seen_run"] == RUN1
    finally:
        state.close()


def test_store_reuses_core_connection(tmp_path):
    state = StateStore(tmp_path / "s.sqlite")
    try:
        assert OpportunityStore(state).db is state.db
    finally:
        state.close()
