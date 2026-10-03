"""SQLite state kept between runs: runs, fetched articles, searches and reported items.

One run at a time: opening the store takes an exclusive lock on `<state>.lock` and a
second opener fails with `StateLocked`. The schema version lives in `PRAGMA
user_version`; later changes add a step to `MIGRATIONS`.
"""

import hashlib
import json
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from tracker.errors import StateLocked

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None  # type: ignore[assignment]
    import msvcrt

TRACKING_PARAMS = {"gclid", "fbclid", "ref", "mc_cid", "mc_eid"}
DEFAULT_PORTS = {"http": 80, "https": 443}

MIGRATIONS: list[str] = [
    """
    CREATE TABLE runs (
        id TEXT PRIMARY KEY,
        started_at TEXT NOT NULL,
        ended_at TEXT,
        topic TEXT NOT NULL,
        k INTEGER NOT NULL,
        status TEXT NOT NULL,
        stop_reason TEXT,
        usage_json TEXT
    );
    CREATE TABLE articles (
        canonical_url TEXT PRIMARY KEY,
        url TEXT NOT NULL,
        title TEXT NOT NULL,
        text TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        first_seen_run TEXT NOT NULL,
        fetched_at TEXT NOT NULL
    );
    CREATE TABLE items (
        run_id TEXT NOT NULL REFERENCES runs(id),
        rank INTEGER NOT NULL,
        title TEXT NOT NULL,
        summary TEXT NOT NULL,
        sources_json TEXT NOT NULL,
        PRIMARY KEY (run_id, rank)
    );
    CREATE TABLE searches (
        run_id TEXT NOT NULL,
        query TEXT NOT NULL,
        results_json TEXT NOT NULL,
        at TEXT NOT NULL
    );
    """,
]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def canonicalize(url: str) -> str:
    """Lowercase scheme and host, drop fragment, default port and tracking parameters."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower().rstrip(".")
    if ":" in host:
        host = f"[{host}]"
    netloc = host if parts.port in (None, DEFAULT_PORTS.get(scheme)) else f"{host}:{parts.port}"
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMS
        ]
    )
    return urlunsplit((scheme, netloc, parts.path or "/", query, ""))


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = self._acquire(path.with_name(path.name + ".lock"))
        try:
            self.db = sqlite3.connect(path)
            self.db.row_factory = sqlite3.Row
            self.db.execute("PRAGMA journal_mode=WAL")
            self._migrate()
        except BaseException:
            self._release()
            raise

    @staticmethod
    def _acquire(lock_path: Path):
        handle = lock_path.open("a+")
        try:
            if fcntl is not None:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            handle.close()
            raise StateLocked(
                f"Another run holds the state file {lock_path.with_suffix('')}. "
                "Wait for it to finish."
            ) from None
        return handle

    def _release(self) -> None:
        if self._lock is not None:
            self._lock.close()  # closing the handle releases the lock
            self._lock = None

    def _migrate(self) -> None:
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        for number, script in enumerate(MIGRATIONS[version:], start=version + 1):
            with self.db:
                self.db.executescript(script)
                self.db.execute(f"PRAGMA user_version = {number}")

    def close(self) -> None:
        self.db.close()
        self._release()

    def __enter__(self) -> "StateStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # Runs

    def start_run(self, run_id: str, topic: str, k: int) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO runs (id, started_at, topic, k, status) VALUES (?, ?, ?, ?, ?)",
                (run_id, _now(), topic, k, "running"),
            )

    def end_run(
        self, run_id: str, status: str, stop_reason: str | None, usage: dict[str, Any]
    ) -> None:
        with self.db:
            self.db.execute(
                "UPDATE runs SET ended_at = ?, status = ?, stop_reason = ?, usage_json = ? "
                "WHERE id = ?",
                (_now(), status, stop_reason, json.dumps(usage), run_id),
            )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    # Articles

    def get_article(self, url: str) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT * FROM articles WHERE canonical_url = ?", (canonicalize(url),)
        ).fetchone()
        return dict(row) if row else None

    def put_article(self, url: str, title: str, text: str, run_id: str) -> str:
        canonical = canonicalize(url)
        with self.db:
            self.db.execute(
                "INSERT INTO articles (canonical_url, url, title, text, content_hash, "
                "first_seen_run, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (canonical_url) DO UPDATE SET url = excluded.url, "
                "title = excluded.title, text = excluded.text, "
                "content_hash = excluded.content_hash, fetched_at = excluded.fetched_at",
                (canonical, url, title, text, content_hash(text), run_id, _now()),
            )
        return canonical

    # Searches and items

    def add_search(self, run_id: str, query: str, results: list[dict[str, Any]]) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO searches (run_id, query, results_json, at) VALUES (?, ?, ?, ?)",
                (run_id, query, json.dumps(results), _now()),
            )

    def put_items(self, run_id: str, items: Sequence[dict[str, Any]]) -> None:
        with self.db:
            for rank, item in enumerate(items, start=1):
                self.db.execute(
                    "INSERT INTO items (run_id, rank, title, summary, sources_json) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (run_id, rank, item["title"], item["summary"], json.dumps(item["sources"])),
                )

    def items_for_run(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT rank, title, summary, sources_json FROM items WHERE run_id = ? ORDER BY rank",
            (run_id,),
        ).fetchall()
        return [
            {
                "rank": r["rank"],
                "title": r["title"],
                "summary": r["summary"],
                "sources": json.loads(r["sources_json"]),
            }
            for r in rows
        ]
