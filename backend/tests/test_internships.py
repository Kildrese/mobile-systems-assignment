"""The daily report: published from the tracker's state file, read (only) over the API."""

from app.db import get_sessionmaker
from app.publish_report import offers, publish
from tests_tracker.internships_helpers import RUN1, RUN2, add_board, open_store, posting, record


def _state(tmp_path):
    """Two runs: Acme first seen in RUN1 (summarized then), Beta new in RUN2 and top K."""
    state, store = open_store(tmp_path / "s.sqlite")
    for run_id in (RUN1, RUN2):
        state.start_run(run_id, "internships", 5)
        state.end_run(run_id, "complete", None, {})
    (acme_posting,) = store.upsert_postings(add_board(store), [posting("1")], RUN1)
    (beta_posting,) = store.upsert_postings(add_board(store, "beta", "Beta"), [posting("2")], RUN2)
    acme = store.create_opportunity(
        company="Acme",
        url="https://a.example/1",
        record=record(),
        run_id=RUN1,
        posting_id=acme_posting,
        linked_by="record",
    )
    beta = store.create_opportunity(
        company="Beta",
        url="https://b.example/1",
        record=record(),
        run_id=RUN2,
        posting_id=beta_posting,
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
    document = client.get("/api/openapi.json").json()["paths"]
    assert paths == ["/api/internships/latest", "/api/internships/runs/{id}/report.md"]
    assert all(list(document[p]) == ["get"] for p in paths)
    for path in ("/api/internships/latest", f"/api/internships/runs/{RUN2}/report.md"):
        for method in ("post", "put", "patch", "delete"):
            assert getattr(client, method)(path, headers=ada.headers).status_code == 405


def test_export_serves_the_stored_report(tmp_path, client, ada):
    state, store = _state(tmp_path)
    run = dict(state.db.execute("SELECT * FROM runs WHERE id = ?", (RUN2,)).fetchone())
    rows = offers(store, RUN2)
    state.close()
    with get_sessionmaker()() as db:
        publish(db, run, rows, "# Internship report\n")

    url = f"/api/internships/runs/{RUN2}/report.md"
    response = client.get(url, headers=ada.headers)
    assert response.status_code == 200
    assert response.text == "# Internship report\n"
    assert response.headers["content-type"] == "text/markdown; charset=utf-8"
    assert f'filename="internships-{RUN2}.md"' in response.headers["content-disposition"]
    assert client.get(url).status_code == 401
    unknown = client.get("/api/internships/runs/nope/report.md", headers=ada.headers)
    assert unknown.status_code == 404

    with get_sessionmaker()() as db:
        publish(db, run, rows, "")  # published without a report
    assert client.get(url, headers=ada.headers).status_code == 404
