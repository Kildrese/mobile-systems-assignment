"""The orchestrate command's database side: refusing to start, run history, and the
last-top-K lookup. Workers are never reached here."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from app.publish_report import publish
from tracker import config, orchestrate
from tracker.orchestrate import Outcome, find_last_top_k

ROOT_CONFIG = Path(__file__).resolve().parents[2] / "config.yaml"
WORKER_ENV = {
    "RESEARCHER_URL": "http://127.0.0.1:9",
    "RESEARCHER_TOKEN": "r-token",
    "VERIFIER_URL": "http://127.0.0.1:9",
    "VERIFIER_TOKEN": "v-token",
}


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "no.env")  # ignore backend/.env
    for name, value in WORKER_ENV.items():
        monkeypatch.setenv(name, value)
    # Any request would fail the test.
    monkeypatch.setattr(orchestrate, "orchestrate", lambda *a, **k: pytest.fail("ran"))
    return monkeypatch


def test_missing_researcher_url_refuses_to_start(env, capsys):
    env.delenv("RESEARCHER_URL")
    assert orchestrate.main(["--config", str(ROOT_CONFIG)]) == 1
    assert "RESEARCHER_URL is not set" in capsys.readouterr().err


def test_non_local_database_refuses_to_start(env, capsys):
    env.setenv("DATABASE_URL", "postgresql://u:p@ep-x.neon.tech/db")
    get_settings.cache_clear()
    try:
        assert orchestrate.main(["--config", str(ROOT_CONFIG)]) == 1
    finally:
        env.undo()
        get_settings.cache_clear()
    assert "refusing to write to a non-local database" in capsys.readouterr().err


def test_host_override_in_the_url_refuses_to_start(env, capsys):
    # D41: `?host=` replaces the URL's host. The real case is
    # postgresql://u:p@localhost/db?host=ep-x.neon.tech; 0.0.0.0 reaches the local test
    # database without any network, and is not one of the allowed hosts.
    url = make_url(get_settings().database_url).update_query_dict({"host": "0.0.0.0"})
    env.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
    for cached in (get_settings, get_engine, get_sessionmaker):
        cached.cache_clear()
    try:
        assert orchestrate.main(["--config", str(ROOT_CONFIG)]) == 1
    finally:
        env.undo()
        for cached in (get_settings, get_engine, get_sessionmaker):
            cached.cache_clear()
    assert "refusing to write to a non-local database" in capsys.readouterr().err


def outcome(run_id, started, offers):
    run = {
        "id": run_id,
        "topic": "t",
        "status": "complete" if offers else "partial",
        "stop_reason": None if offers else "service:researcher",
        "started_at": started.isoformat(),
        "ended_at": started.isoformat(),
        "failed_services": [] if offers else ["researcher"],
    }
    rows = [
        {
            "opportunity_id": rank,
            "section": "top_k",
            "rank": rank,
            "top_k": True,
            "company": "",
            "title": f"Role {rank}",
            "url": f"https://jobs.test/{rank}",
            "summary": "",
            "role_type": "unknown",
            "term": "unknown",
            "remote": "unknown",
            "status": "unknown",
            "locations": [],
            "verified": False,
            "first_seen_at": started,
            "claims": [{"field": "term", "text": "T", "verdict": "unverified", "evidence": None}],
        }
        for rank in range(1, offers + 1)
    ]
    return Outcome(run, rows, "# report", 0 if offers else 2)


def test_history_and_last_top_k(sql):
    first = outcome(
        "11111111-1111-1111-1111-111111111111", datetime(2026, 11, 15, 9, tzinfo=UTC), 2
    )
    with get_sessionmaker()() as db:
        assert find_last_top_k(db) is None
        publish(db, first.run, first.offers, first.markdown)
    assert sql.scalar("select count(*) from tracker_runs") == 1
    assert [r.rank for r in sql.rows("select rank from internship_offers order by rank")] == [1, 2]

    stale = outcome(
        "22222222-2222-2222-2222-222222222222", datetime(2026, 11, 15, 10, tzinfo=UTC), 0
    )
    with get_sessionmaker()() as db:
        publish(db, stale.run, stale.offers, stale.markdown)
        last = find_last_top_k(db)
    assert last["run_id"] == first.run["id"]
    assert [(o["rank"], o["title"]) for o in last["offers"]] == [(1, "Role 1"), (2, "Role 2")]
    assert last["offers"][0]["claims"][0]["verdict"] == "unverified"
