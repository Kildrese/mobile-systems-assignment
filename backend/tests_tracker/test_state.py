"""tracker-state: SQLite store, canonical URLs and the run lock."""

import json
import sqlite3

import pytest

from tracker.errors import StateLocked
from tracker.state import MIGRATIONS, StateStore, canonicalize


def test_first_run_creates_file_and_schema(tmp_path):
    path = tmp_path / "nested" / "state.sqlite"
    with StateStore(path) as store:
        store.start_run("r1", "topic", 5)
    assert path.is_file()
    db = sqlite3.connect(path)
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"runs", "articles", "items", "searches"} <= tables
    assert db.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


@pytest.mark.parametrize(
    ("url", "canonical"),
    [
        ("https://Example.com/news/1?utm_source=x#top", "https://example.com/news/1"),
        ("HTTPS://EXAMPLE.COM:443/a?b=2&gclid=z&fbclid=y&ref=hn", "https://example.com/a?b=2"),
        ("http://example.com:80", "http://example.com/"),
        ("http://example.com:8080/x", "http://example.com:8080/x"),
    ],
)
def test_canonicalize(url, canonical):
    assert canonicalize(url) == canonical


def test_tracking_parameter_url_is_same_article(tmp_path):
    with StateStore(tmp_path / "s.sqlite") as store:
        store.put_article("https://Example.com/news/1?utm_source=x#top", "T", "body", "r1")
        article = store.get_article("https://example.com/news/1")
    assert article is not None
    assert article["title"] == "T"
    assert article["first_seen_run"] == "r1"


def test_refetch_keeps_first_seen_run(tmp_path):
    with StateStore(tmp_path / "s.sqlite") as store:
        store.put_article("https://example.com/a", "T", "v1", "r1")
        store.put_article("https://example.com/a", "T", "v2", "r2")
        article = store.get_article("https://example.com/a")
    assert article["first_seen_run"] == "r1"
    assert article["text"] == "v2"


def test_partial_run_recorded(tmp_path):
    with StateStore(tmp_path / "s.sqlite") as store:
        store.start_run("r1", "topic", 5)
        store.end_run("r1", "partial", "max_steps", {"steps": 15})
        run = store.db.execute("SELECT * FROM runs").fetchone()
    assert run["status"] == "partial"
    assert run["stop_reason"] == "max_steps"
    assert run["ended_at"]


def test_items_stored_in_rank_order(tmp_path):
    items = [
        {"title": f"Item {i}", "summary": "s", "sources": [f"https://e.com/{i}"]}
        for i in range(1, 6)
    ]
    with StateStore(tmp_path / "s.sqlite") as store:
        store.start_run("r1", "topic", 5)
        store.put_items("r1", items)
        stored = store.db.execute("SELECT rank, title, sources_json FROM items").fetchall()
    assert [r["rank"] for r in stored] == [1, 2, 3, 4, 5]
    assert [r["title"] for r in stored] == [f"Item {i}" for i in range(1, 6)]
    assert json.loads(stored[0]["sources_json"]) == ["https://e.com/1"]


def test_searches_recorded(tmp_path):
    with StateStore(tmp_path / "s.sqlite") as store:
        store.add_search("r1", "robots", [{"url": "https://e.com"}])
        (row,) = store.db.execute("SELECT query FROM searches").fetchall()
    assert row[0] == "robots"


def test_second_open_while_locked_fails(tmp_path):
    path = tmp_path / "s.sqlite"
    first = StateStore(path)
    first.start_run("r1", "topic", 5)
    with pytest.raises(StateLocked, match="Another run holds the state file"):
        StateStore(path)
    first.close()
    # Released on close.
    with StateStore(path) as store:
        assert store.db.execute("SELECT status FROM runs").fetchone()[0] == "running"
