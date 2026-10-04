"""The internship tables, kept in the core state file.

The use case versions its own schema in `component_versions`, separate from the core's
`PRAGMA user_version`, so the core never needs to know about these tables and a state
file from the core upgrades in place.
"""

import hashlib
import json
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from tracker.state import StateStore, canonicalize

COMPONENT = "internships"

MIGRATIONS: list[str] = [
    """
    CREATE TABLE sources (
        id INTEGER PRIMARY KEY,
        key TEXT NOT NULL UNIQUE,
        company TEXT NOT NULL,
        kind TEXT NOT NULL,
        board TEXT,
        url TEXT,
        added_by TEXT NOT NULL,
        added_run TEXT NOT NULL,
        evidence_url TEXT,
        active INTEGER NOT NULL DEFAULT 1,
        last_read_run TEXT,
        last_read_status TEXT
    );
    CREATE TABLE raw_postings (
        id INTEGER PRIMARY KEY,
        source_id INTEGER NOT NULL REFERENCES sources(id),
        external_id TEXT NOT NULL,
        url TEXT NOT NULL,
        canonical_url TEXT NOT NULL,
        title TEXT NOT NULL,
        location TEXT NOT NULL DEFAULT '',
        text TEXT NOT NULL,
        detail_text TEXT,
        updated_at TEXT,
        content_hash TEXT NOT NULL,
        first_seen_run TEXT NOT NULL,
        seen_run TEXT NOT NULL,
        curation TEXT NOT NULL DEFAULT 'pending',
        failures INTEGER NOT NULL DEFAULT 0,
        unclear_reason TEXT,
        opportunity_id INTEGER REFERENCES opportunities(id),
        UNIQUE (source_id, external_id)
    );
    CREATE INDEX raw_postings_canonical ON raw_postings(canonical_url);
    CREATE TABLE opportunities (
        id INTEGER PRIMARY KEY,
        company TEXT NOT NULL,
        title TEXT NOT NULL,
        role_type TEXT NOT NULL,
        term TEXT NOT NULL,
        locations_json TEXT NOT NULL,
        remote TEXT NOT NULL,
        url TEXT NOT NULL,
        fields_json TEXT NOT NULL,
        status TEXT NOT NULL,
        status_evidence TEXT,
        checked_run TEXT,
        first_seen_run TEXT NOT NULL,
        first_seen_at TEXT NOT NULL,
        last_seen_open_run TEXT,
        closed_run TEXT
    );
    CREATE TABLE opportunity_links (
        opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),
        raw_posting_id INTEGER NOT NULL REFERENCES raw_postings(id),
        linked_by TEXT NOT NULL,
        reason TEXT,
        PRIMARY KEY (opportunity_id, raw_posting_id)
    );
    CREATE TABLE ranks (
        run_id TEXT NOT NULL,
        opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),
        rank INTEGER NOT NULL,
        score REAL NOT NULL,
        top_k INTEGER NOT NULL,
        PRIMARY KEY (run_id, opportunity_id)
    );
    CREATE TABLE summaries (
        run_id TEXT NOT NULL,
        opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),
        text TEXT NOT NULL,
        PRIMARY KEY (run_id, opportunity_id)
    );
    CREATE TABLE http_cache (
        url TEXT PRIMARY KEY,
        etag TEXT,
        last_modified TEXT,
        body TEXT NOT NULL,
        at TEXT NOT NULL
    );
    """,
]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def source_key(kind: str, board: str | None, url: str | None) -> str:
    if kind == "page":
        return f"page:{canonicalize(url or '')}"
    return f"{kind}:{(board or '').lower()}"


@dataclass(frozen=True)
class RawPosting:
    """One job as a source lists it, before curation."""

    external_id: str
    title: str
    url: str
    text: str
    location: str = ""
    updated_at: str | None = None


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


class OpportunityStore:
    """The internship tables over the core state connection."""

    def __init__(self, state: StateStore) -> None:
        self.db = state.db
        self._migrate()

    def _migrate(self) -> None:
        with self.db:
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS component_versions "
                "(name TEXT PRIMARY KEY, version INTEGER NOT NULL)"
            )
        row = self.db.execute(
            "SELECT version FROM component_versions WHERE name = ?", (COMPONENT,)
        ).fetchone()
        version = row[0] if row else 0
        for number, script in enumerate(MIGRATIONS[version:], start=version + 1):
            # executescript commits first, so the version is recorded right after it.
            self.db.executescript(script)
            with self.db:
                self.db.execute(
                    "INSERT INTO component_versions (name, version) VALUES (?, ?) "
                    "ON CONFLICT (name) DO UPDATE SET version = excluded.version",
                    (COMPONENT, number),
                )

    # Sources

    def add_source(
        self,
        *,
        company: str,
        kind: str,
        board: str | None,
        url: str | None,
        added_by: str,
        run_id: str,
        evidence_url: str | None = None,
    ) -> tuple[int, bool]:
        """Insert a source unless its key exists. Returns its id and whether it is new."""
        key = source_key(kind, board, url)
        existing = self.db.execute("SELECT id FROM sources WHERE key = ?", (key,)).fetchone()
        if existing:
            return existing["id"], False
        with self.db:
            cursor = self.db.execute(
                "INSERT INTO sources (key, company, kind, board, url, added_by, added_run, "
                "evidence_url) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (key, company, kind, board, url, added_by, run_id, evidence_url),
            )
        return int(cursor.lastrowid or 0), True

    def has_source(self, kind: str, board: str | None, url: str | None) -> bool:
        key = source_key(kind, board, url)
        return self.db.execute("SELECT 1 FROM sources WHERE key = ?", (key,)).fetchone() is not None

    def sources(self) -> list[dict[str, Any]]:
        """Active sources. A deactivated one stays in the table, so it is never re-added."""
        sql = "SELECT * FROM sources WHERE active = 1 ORDER BY id"
        return [dict(r) for r in self.db.execute(sql)]

    def deactivate_source(self, source_id: int) -> None:
        with self.db:
            self.db.execute("UPDATE sources SET active = 0 WHERE id = ?", (source_id,))

    def source(self, source_id: int) -> dict[str, Any] | None:
        return _row(self.db.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone())

    def count_sources_added(self, run_id: str, added_by: str) -> int:
        return self.db.execute(
            "SELECT COUNT(*) FROM sources WHERE added_run = ? AND added_by = ?",
            (run_id, added_by),
        ).fetchone()[0]

    def mark_source_read(self, source_id: int, run_id: str, status: str) -> None:
        with self.db:
            self.db.execute(
                "UPDATE sources SET last_read_run = ?, last_read_status = ? WHERE id = ?",
                (run_id, status, source_id),
            )

    # HTTP validators

    def http_cache(self, url: str) -> dict[str, Any] | None:
        return _row(self.db.execute("SELECT * FROM http_cache WHERE url = ?", (url,)).fetchone())

    def put_http_cache(
        self, url: str, etag: str | None, last_modified: str | None, body: str
    ) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO http_cache (url, etag, last_modified, body, at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT (url) DO UPDATE SET etag = excluded.etag, "
                "last_modified = excluded.last_modified, body = excluded.body, at = excluded.at",
                (url, etag, last_modified, body, _now()),
            )

    # Raw postings

    def upsert_postings(
        self, source_id: int, postings: Iterable[RawPosting], run_id: str
    ) -> list[int]:
        """Store postings seen in this run. New ones start `pending`. Returns their ids."""
        ids = []
        with self.db:
            for p in postings:
                digest = content_hash(f"{p.title}\n{p.location}\n{p.text}")
                self.db.execute(
                    "INSERT INTO raw_postings (source_id, external_id, url, canonical_url, "
                    "title, location, text, updated_at, content_hash, first_seen_run, seen_run) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT (source_id, external_id) DO UPDATE SET url = excluded.url, "
                    "canonical_url = excluded.canonical_url, title = excluded.title, "
                    "location = excluded.location, text = excluded.text, "
                    "updated_at = excluded.updated_at, content_hash = excluded.content_hash, "
                    "seen_run = excluded.seen_run",
                    (
                        source_id,
                        p.external_id,
                        p.url,
                        canonicalize(p.url),
                        p.title,
                        p.location,
                        p.text,
                        p.updated_at,
                        digest,
                        run_id,
                        run_id,
                    ),
                )
                ids.append(
                    self.db.execute(
                        "SELECT id FROM raw_postings WHERE source_id = ? AND external_id = ?",
                        (source_id, p.external_id),
                    ).fetchone()[0]
                )
        return ids

    def posting(self, posting_id: int) -> dict[str, Any] | None:
        return _row(
            self.db.execute(
                "SELECT p.*, s.company, s.kind AS source_kind FROM raw_postings p "
                "JOIN sources s ON s.id = p.source_id WHERE p.id = ?",
                (posting_id,),
            ).fetchone()
        )

    def pending_postings(self, run_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        """Pending postings listed in `run_id`. One no longer listed is not worth curating."""
        sql = (
            "SELECT p.*, s.company FROM raw_postings p JOIN sources s ON s.id = p.source_id "
            "WHERE p.curation = 'pending' AND p.seen_run = ? ORDER BY p.id"
        )
        rows = self.db.execute(sql + (f" LIMIT {int(limit)}" if limit else ""), (run_id,))
        return [dict(r) for r in rows]

    def postings_with_canonical_url(self, canonical_url: str) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in self.db.execute(
                "SELECT * FROM raw_postings WHERE canonical_url = ? ORDER BY id", (canonical_url,)
            )
        ]

    def set_detail_text(self, posting_id: int, text: str) -> None:
        with self.db:
            self.db.execute(
                "UPDATE raw_postings SET detail_text = ? WHERE id = ?", (text, posting_id)
            )

    def set_curation(
        self,
        posting_id: int,
        curation: str,
        *,
        opportunity_id: int | None = None,
        unclear_reason: str | None = None,
    ) -> None:
        with self.db:
            self.db.execute(
                "UPDATE raw_postings SET curation = ?, opportunity_id = COALESCE(?, "
                "opportunity_id), unclear_reason = ? WHERE id = ?",
                (curation, opportunity_id, unclear_reason, posting_id),
            )

    def add_failure(self, posting_id: int) -> int:
        with self.db:
            self.db.execute(
                "UPDATE raw_postings SET failures = failures + 1 WHERE id = ?", (posting_id,)
            )
        return self.db.execute(
            "SELECT failures FROM raw_postings WHERE id = ?", (posting_id,)
        ).fetchone()[0]

    # Opportunities

    def create_opportunity(
        self,
        *,
        company: str,
        url: str,
        record: dict[str, Any],
        run_id: str,
        posting_id: int,
        linked_by: str,
    ) -> int:
        """Create an open opportunity from a verified record and link its posting."""

        def value(name: str, default: Any = "unknown") -> Any:
            field = record.get(name) or {}
            return field.get("value", default) if isinstance(field, dict) else default

        with self.db:
            cursor = self.db.execute(
                "INSERT INTO opportunities (company, title, role_type, term, locations_json, "
                "remote, url, fields_json, status, first_seen_run, first_seen_at, "
                "last_seen_open_run, checked_run) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?)",
                (
                    company,
                    value("title"),
                    value("role_type"),
                    value("term"),
                    json.dumps(value("locations", [])),
                    value("remote"),
                    url,
                    json.dumps(record),
                    run_id,
                    _now(),
                    run_id,
                    run_id,
                ),
            )
            opportunity_id = int(cursor.lastrowid or 0)
            self._link(opportunity_id, posting_id, linked_by, None)
        return opportunity_id

    def link(
        self, opportunity_id: int, posting_id: int, linked_by: str, reason: str | None
    ) -> None:
        with self.db:
            self._link(opportunity_id, posting_id, linked_by, reason)

    def _link(
        self, opportunity_id: int, posting_id: int, linked_by: str, reason: str | None
    ) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO opportunity_links (opportunity_id, raw_posting_id, linked_by, "
            "reason) VALUES (?, ?, ?, ?)",
            (opportunity_id, posting_id, linked_by, reason),
        )
        self.db.execute(
            "UPDATE raw_postings SET curation = ?, opportunity_id = ? WHERE id = ?",
            ("saved" if linked_by == "record" else "linked", opportunity_id, posting_id),
        )

    def opportunity(self, opportunity_id: int) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT * FROM opportunities WHERE id = ?", (opportunity_id,)
        ).fetchone()
        return _decode_opportunity(row) if row else None

    def opportunities(self, statuses: Sequence[str] | None = None) -> list[dict[str, Any]]:
        if statuses:
            marks = ",".join("?" * len(statuses))
            rows = self.db.execute(
                f"SELECT * FROM opportunities WHERE status IN ({marks}) ORDER BY id",
                tuple(statuses),
            )
        else:
            rows = self.db.execute("SELECT * FROM opportunities ORDER BY id")
        return [_decode_opportunity(r) for r in rows]

    def linked_postings(self, opportunity_id: int) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in self.db.execute(
                "SELECT p.*, s.kind AS source_kind, s.last_read_run, s.last_read_status, "
                "s.company FROM opportunity_links l "
                "JOIN raw_postings p ON p.id = l.raw_posting_id "
                "JOIN sources s ON s.id = p.source_id WHERE l.opportunity_id = ? ORDER BY p.id",
                (opportunity_id,),
            )
        ]

    def set_status(
        self,
        opportunity_id: int,
        status: str,
        run_id: str,
        evidence: str,
        *,
        checked: bool = True,
    ) -> None:
        """Record a lifecycle decision. Reopening keeps `first_seen_run`."""
        with self.db:
            self.db.execute(
                "UPDATE opportunities SET status = ?, status_evidence = ?, "
                "checked_run = CASE WHEN ? THEN ? ELSE checked_run END, "
                "last_seen_open_run = CASE WHEN ? = 'open' THEN ? ELSE last_seen_open_run END, "
                "closed_run = CASE WHEN ? = 'closed' THEN ? WHEN ? = 'open' THEN NULL "
                "ELSE closed_run END WHERE id = ?",
                (
                    status,
                    evidence,
                    checked,
                    run_id,
                    status,
                    run_id,
                    status,
                    run_id,
                    status,
                    opportunity_id,
                ),
            )

    # Ranks and summaries

    def put_ranks(self, run_id: str, ranked: Sequence[tuple[int, float, bool]]) -> None:
        with self.db:
            self.db.execute("DELETE FROM ranks WHERE run_id = ?", (run_id,))
            for rank, (opportunity_id, score, top_k) in enumerate(ranked, start=1):
                self.db.execute(
                    "INSERT INTO ranks (run_id, opportunity_id, rank, score, top_k) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (run_id, opportunity_id, rank, score, int(top_k)),
                )

    def ranks(self, run_id: str) -> dict[int, dict[str, Any]]:
        return {
            r["opportunity_id"]: dict(r)
            for r in self.db.execute("SELECT * FROM ranks WHERE run_id = ?", (run_id,))
        }

    def put_summary(self, run_id: str, opportunity_id: int, text: str) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO summaries (run_id, opportunity_id, text) VALUES (?, ?, ?) "
                "ON CONFLICT (run_id, opportunity_id) DO UPDATE SET text = excluded.text",
                (run_id, opportunity_id, text),
            )

    def summaries(self, run_id: str) -> dict[int, str]:
        return {
            r["opportunity_id"]: r["text"]
            for r in self.db.execute("SELECT * FROM summaries WHERE run_id = ?", (run_id,))
        }


def _decode_opportunity(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["locations"] = json.loads(data.pop("locations_json"))
    data["fields"] = json.loads(data.pop("fields_json"))
    return data
