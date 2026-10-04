"""The daily report: published from the tracker's state file, read (only) over the API."""

from app.db import get_sessionmaker
from app.publish_report import offers, publish
from tests_tracker.internships_helpers import RUN1, RUN2, open_store, record


def _state(tmp_path):
    """Two runs: Acme first seen in RUN1 (summarized then), Beta new in RUN2 and top K."""
    state, store = open_store(tmp_path / "s.sqlite")
    for run_id in (RUN1, RUN2):
        state.start_run(run_id, "internships", 5)
        state.end_run(run_id, "complete", None, {})
    with state.db:
        for pid in (1, 2):
            state.db.execute(
                "INSERT INTO sources (id, key, company, kind, added_by, added_run) "
                "VALUES (?, ?, 'x', 'greenhouse', 'config', ?)",
                (pid, f"greenhouse:{pid}", RUN1),
            )
            state.db.execute(
                "INSERT INTO raw_postings (id, source_id, external_id, url, canonical_url, "
                "title, text, content_hash, first_seen_run, seen_run) "
                "VALUES (?, ?, '1', 'u', 'u', 't', 't', 'h', ?, ?)",
                (pid, pid, RUN1, RUN2),
            )
    acme = store.create_opportunity(
        company="Acme",
        url="https://a.example/1",
        record=record(),
        run_id=RUN1,
        posting_id=1,
        linked_by="record",
    )
    beta = store.create_opportunity(
        company="Beta",
        url="https://b.example/1",
        record=record(),
        run_id=RUN2,
        posting_id=2,
        linked_by="record",
    )
    store.put_summary(RUN1, acme, "Acme summary.")
    store.put_ranks(RUN2, [(beta, 9.0, True), (acme, 8.0, False)])
    return state, store


def test_publish_and_read(tmp_path, client, ada, sql):
    state, store = _state(tmp_path)
    rows = offers(store, RUN2)
    run = dict(state.db.execute("SELECT * FROM runs WHERE id = ?", (RUN2,)).fetchone())
    state.close()

    assert [(r["company"], r["section"]) for r in rows] == [("Beta", "new"), ("Acme", "open")]
    acme_row = rows[1]
    # The summary from an earlier run carries over; unknown fields become null.
    assert acme_row["summary"] == "Acme summary."
    assert acme_row["compensation"] == "$45/hour"
    assert acme_row["deadline"] is None
    assert acme_row["work_authorization_quote"] == "must be authorized to work in the US"

    with get_sessionmaker()() as db:
        publish(db, run, rows, "# report")
        publish(db, run, rows, "# report")  # a retried job replaces, never duplicates
    assert sql.scalar("select count(*) from internship_offers") == 2

    body = client.get("/api/internships/latest", headers=ada.headers).json()
    assert body["run"]["id"] == RUN2
    assert body["run"]["reportMarkdown"] == "# report"
    assert [(o["company"], o["rank"], o["topK"]) for o in body["offers"]] == [
        ("Beta", 1, True),
        ("Acme", 2, False),
    ]


def test_empty_before_first_run(client, ada):
    response = client.get("/api/internships/latest", headers=ada.headers)
    assert response.status_code == 200
    assert response.json() == {"run": None, "offers": []}


def test_requires_login(client):
    assert client.get("/api/internships/latest").status_code == 401


def test_cannot_start_the_tracker(client, ada):
    paths = [p for p in client.get("/api/openapi.json").json()["paths"] if "internship" in p]
    assert paths == ["/api/internships/latest"]
    for method in ("post", "put", "patch", "delete"):
        response = getattr(client, method)("/api/internships/latest", headers=ada.headers)
        assert response.status_code == 405
