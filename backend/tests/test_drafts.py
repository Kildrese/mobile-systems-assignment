"""Applicant profiles and application drafts: allowlist, upload checks, drafting through a
fake drafter, sharing, downloads, and the daily step."""

import base64
import io
import json
import re
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
from docx import Document
from sqlalchemy import event

from app import drafts
from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from app.draft_new import draft_new, top_k_rows
from app.publish_report import publish
from app.share_drafts import share
from tests.conftest import Account, assert_error
from tests_tracker.internships_helpers import RUN1, add_board, open_store, posting, record

FIXTURES = Path(__file__).resolve().parents[2] / "services" / "drafter" / "tests" / "fixtures"
FILES = {
    "cvDocx": ("cv.docx", (FIXTURES / "cv.docx").read_bytes()),
    "factBank": ("fact_bank.yaml", (FIXTURES / "fact_bank.yaml").read_bytes()),
    "rulesMd": ("rules.md", (FIXTURES / "rules.md").read_bytes()),
    "checksYaml": ("checks.yaml", (FIXTURES / "checks.yaml").read_bytes()),
}


@pytest.fixture
def allow(monkeypatch):
    def set_users(users: str | None) -> None:
        if users is None:
            monkeypatch.delenv("DRAFTING_USERS", raising=False)
        else:
            monkeypatch.setenv("DRAFTING_USERS", users)
        get_settings.cache_clear()

    yield set_users
    get_settings.cache_clear()


class FakeDrafter:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.down = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.calls.append(body)
        if self.down:
            return httpx.Response(503, headers={"retry-after": "0"})
        letter = body["payload"]["cover_letter"]
        return httpx.Response(
            200,
            json={
                "request_id": body["request_id"],
                "run_id": body["run_id"],
                "status": "complete",
                "result": {
                    "role_type": "swe",
                    "cv_docx_b64": base64.b64encode(b"CV BYTES").decode(),
                    "cover_letter_docx_b64": base64.b64encode(b"LETTER").decode()
                    if letter
                    else None,
                    "cover_letter_text": "Dear Hiring Team,\n..." if letter else None,
                    "checks": [{"name": "scope_word", "outcome": "fallback", "detail": "led"}],
                    "model": "claude-sonnet-5-5",
                },
                "usage": {"steps": 1, "fetches": 1, "tokens": 9000},
                "error": None,
            },
        )


@pytest.fixture
def drafter(monkeypatch):
    fake = FakeDrafter()
    client = drafts.DrafterClient(
        "https://drafter.test", "t", 2, httpx.MockTransport(fake.handler), lambda s: None
    )
    monkeypatch.setattr(drafts, "drafter_client", lambda max_attempts: client)
    return fake


def offer(opportunity_id=7, company="Ramp", title="Software Engineer Intern", deadline=None):
    run = {
        "id": RUN1,
        "topic": "internships",
        "status": "complete",
        "stop_reason": None,
        "started_at": "2026-11-01T09:00:00+00:00",
        "ended_at": "2026-11-01T09:20:00+00:00",
    }
    row = {
        "opportunity_id": opportunity_id,
        "section": "new",
        "rank": 1,
        "top_k": True,
        "previous_rank": None,
        "drop_reason": None,
        "company": company,
        "title": title,
        "role_type": "internship",
        "term": "Summer 2027",
        "locations": ["New York, NY"],
        "remote": "onsite",
        "url": "https://jobs.example.com/ramp/1",
        "compensation": None,
        "deadline": deadline,
        "work_authorization_quote": None,
        "summary": None,
        "fit_score": None,
        "fit_reason": None,
        "status": "open",
        "status_evidence": None,
        "verified": True,
        "claims": [],
        "first_seen_at": datetime(2026, 11, 1, tzinfo=UTC),
    }
    with get_sessionmaker()() as db:
        publish(db, run, [row], "# report")


def upload(client, account, files=FILES):
    return client.put("/api/profile", files=files, headers=account.headers)


@pytest.fixture
def kilian(client, allow, drafter) -> Account:
    allow("kiliandresse")
    account = Account(client, "kiliandresse", "a-long-password")
    assert upload(client, account).status_code == 200
    offer()
    return account


# 4.2 who may draft


def test_not_allowlisted(client, allow, drafter, bob):
    allow("kiliandresse")
    assert_error(upload(client, bob), 403, "NOT_ALLOWED")
    offer()
    r = client.post("/api/drafts", json={"opportunityId": 7}, headers=bob.headers)
    assert_error(r, 403, "NOT_ALLOWED")
    assert drafter.calls == []


def test_unset_allowlist(client, allow, drafter, ada):
    allow(None)
    assert_error(upload(client, ada), 403, "NOT_ALLOWED")
    assert_error(
        client.post("/api/drafts", json={"opportunityId": 7}, headers=ada.headers),
        403,
        "NOT_ALLOWED",
    )
    assert client.get("/api/profile", headers=ada.headers).json()["canDraft"] is False


def test_daily_cap(client, kilian, drafter, sql):
    sql.run(
        "insert into application_drafts (id, user_id, opportunity_id, company, title, cover_letter,"
        " status, profile_hash, request_id, created_at, starts_day, starts) values"
        " (gen_random_uuid(), :u, 99, 'X', 'Y', false, 'ready', 'h', gen_random_uuid(), now(),"
        " :day, 20)",
        u=kilian.id,
        day=datetime.now(UTC).date(),
    )
    assert_error(
        client.post("/api/drafts", json={"opportunityId": 7}, headers=kilian.headers),
        429,
        "DAILY_LIMIT",
    )
    assert drafter.calls == []


# 4.3 the profile


def test_first_upload(client, kilian):
    body = client.get("/api/profile", headers=kilian.headers).json()
    assert [f["name"] for f in body["files"]] == [
        "cv.docx",
        "fact_bank.yaml",
        "rules.md",
        "checks.yaml",
    ]
    assert (
        body["files"][0]["size"] == len(FILES["cvDocx"][1])
        and len(body["files"][0]["sha256"]) == 64
    )
    assert body["uploadedAt"] and body["canDraft"] is True
    assert "Northwind" not in json.dumps(body)


def test_partial_upload_changes_nothing(client, kilian, sql):
    before = sql.scalar("select uploaded_at from applicant_profiles")
    partial = {k: v for k, v in FILES.items() if k != "checksYaml"}
    body = assert_error(upload(client, kilian, partial), 400, "INVALID_PROFILE")
    assert body["error"]["message"].startswith("checks.yaml")
    assert sql.scalar("select uploaded_at from applicant_profiles") == before


def test_duplicate_fact_id(client, kilian):
    bank = FILES["factBank"][1].decode()
    first = bank[bank.index("- id: exp.nws.1\n") : bank.index("- id: exp.nws.2\n")]
    files = {**FILES, "factBank": ("fact_bank.yaml", (bank + "\n" + first).encode())}
    body = assert_error(upload(client, kilian, files), 400, "INVALID_PROFILE")
    assert body["error"]["message"] == "fact_bank.yaml: duplicate id exp.nws.1"


def test_unknown_cv_layout(client, kilian):
    doc = Document(io.BytesIO(FILES["cvDocx"][1]))
    for p in doc.paragraphs:
        if p.text == "EXPERIENCE":
            p.runs[0].text = "WORK"
    buf = io.BytesIO()
    doc.save(buf)
    body = assert_error(
        upload(client, kilian, {**FILES, "cvDocx": ("cv.docx", buf.getvalue())}),
        400,
        "INVALID_PROFILE",
    )
    assert body["error"]["message"] == "cv.docx: no EXPERIENCE heading"


def test_another_user_sees_only_their_own_profile(client, kilian, bob):
    assert client.get("/api/profile", headers=bob.headers).json() == {
        "files": [],
        "uploadedAt": None,
        "canDraft": False,
    }


# 4.4 drafts


def test_draft_and_draft_again(client, kilian, drafter, sql):
    r = client.post("/api/drafts", json={"opportunityId": 7}, headers=kilian.headers)
    assert r.status_code == 200, r.text
    assert (r.json()["status"], r.json()["hasCv"], r.json()["hasLetter"]) == ("ready", True, False)
    sent = drafter.calls[0]["payload"]
    assert (
        sent["posting_url"] == "https://jobs.example.com/ramp/1" and sent["cover_letter"] is False
    )
    r = client.post(
        "/api/drafts", json={"opportunityId": 7, "coverLetter": True}, headers=kilian.headers
    )
    assert (r.json()["hasCv"], r.json()["hasLetter"], r.json()["letterText"]) == (
        True,
        True,
        "Dear Hiring Team,\n...",
    )
    assert sql.scalar("select count(*) from application_drafts") == 1
    assert sql.scalar("select starts from application_drafts") == 2
    assert sql.scalar("select model from application_drafts") == "claude-sonnet-5-5"


def test_no_profile(client, allow, drafter):
    allow("cara")
    cara = Account(client, "cara", "a-long-password")
    offer()
    body = assert_error(
        client.post("/api/drafts", json={"opportunityId": 7}, headers=cara.headers),
        409,
        "PROFILE_MISSING",
    )
    assert body["error"]["message"] == "Upload your profile first"


def test_concurrent_click_gets_409(client, kilian, drafter, sql):
    client.post("/api/drafts", json={"opportunityId": 7}, headers=kilian.headers)
    sql.run("update application_drafts set status = 'pending', created_at = now()")
    r = client.post("/api/drafts", json={"opportunityId": 7}, headers=kilian.headers)
    assert_error(r, 409, "DRAFT_IN_PROGRESS")
    assert len(drafter.calls) == 1


def test_deadline_passed_and_unknown_offer(client, kilian, drafter):
    offer(8, deadline="2026-10-23")
    assert_error(
        client.post("/api/drafts", json={"opportunityId": 8}, headers=kilian.headers),
        409,
        "DEADLINE_PASSED",
    )
    assert_error(
        client.post("/api/drafts", json={"opportunityId": 404}, headers=kilian.headers),
        404,
        "NOT_FOUND",
    )
    report = client.get("/api/internships/latest", headers=kilian.headers).json()
    assert [o["deadlinePassed"] for o in report["offers"]] == [True]
    assert drafter.calls == []


def test_drafter_down_is_stored_as_failed(client, kilian, drafter):
    drafter.down = True
    r = client.post("/api/drafts", json={"opportunityId": 7}, headers=kilian.headers)
    assert r.json()["status"] == "failed" and r.json()["error"].startswith("no_answer")
    assert len(drafter.calls) == 2  # retried once


def test_drafter_not_configured(client, kilian, monkeypatch):
    monkeypatch.setattr(drafts, "drafter_client", lambda max_attempts: None)
    assert_error(
        client.post("/api/drafts", json={"opportunityId": 7}, headers=kilian.headers),
        503,
        "DRAFTER_UNAVAILABLE",
    )


def test_owner_downloads(client, kilian):
    draft = client.post(
        "/api/drafts", json={"opportunityId": 7, "coverLetter": True}, headers=kilian.headers
    ).json()
    r = client.get(f"/api/drafts/{draft['id']}/cv.docx", headers=kilian.headers)
    assert r.status_code == 200 and r.content == b"CV BYTES"
    assert (
        r.headers["content-disposition"]
        == 'attachment; filename="Ramp_Software_Engineer_Intern_CV.docx"'
    )
    r = client.get(f"/api/drafts/{draft['id']}/cover-letter.txt", headers=kilian.headers)
    assert r.text.startswith("Dear") and "Cover_Letter.txt" in r.headers["content-disposition"]


def test_stranger_gets_404(client, kilian, bob):
    draft = client.post("/api/drafts", json={"opportunityId": 7}, headers=kilian.headers).json()
    for path in ("cv.docx", "cover-letter.docx", "cover-letter.txt"):
        assert_error(
            client.get(f"/api/drafts/{draft['id']}/{path}", headers=bob.headers), 404, "NOT_FOUND"
        )
    assert_error(
        client.get("/api/drafts/not-a-uuid/cv.docx", headers=bob.headers), 404, "NOT_FOUND"
    )
    assert client.get("/api/drafts", headers=bob.headers).json() == {"drafts": []}


def test_nyugrader_reads_a_shared_draft(client, kilian, allow):
    nyu = Account(client, "nyugrader", "a-long-password")
    draft = client.post("/api/drafts", json={"opportunityId": 7}, headers=kilian.headers).json()
    with get_sessionmaker()() as db:
        assert (
            share(db, "kiliandresse", "nyugrader")
            == "kiliandresse's drafts are readable by: nyugrader."
        )
    listed = client.get("/api/drafts?opportunityId=7", headers=nyu.headers).json()["drafts"]
    assert [(d["owner"], d["mine"]) for d in listed] == [("kiliandresse", False)]
    assert client.get(f"/api/drafts/{draft['id']}/cv.docx", headers=nyu.headers).status_code == 200
    # A viewer never sees the owner's profile and can't draft.
    assert client.get("/api/profile", headers=nyu.headers).json()["files"] == []
    assert_error(
        client.post("/api/drafts", json={"opportunityId": 7}, headers=nyu.headers),
        403,
        "NOT_ALLOWED",
    )
    with get_sessionmaker()() as db:
        share(db, "kiliandresse", "nyugrader", remove=True)
    assert client.get("/api/drafts", headers=nyu.headers).json() == {"drafts": []}


def test_profile_change_marks_draft_outdated(client, kilian):
    client.post("/api/drafts", json={"opportunityId": 7}, headers=kilian.headers)
    rules = FILES["rulesMd"][1] + b"\n- One more rule.\n"
    assert upload(client, kilian, {**FILES, "rulesMd": ("rules.md", rules)}).status_code == 200
    assert (
        client.get("/api/drafts", headers=kilian.headers).json()["drafts"][0]["profileOutdated"]
        is True
    )


# 4.5 the daily step


def _tracker(tmp_path, texts, deadlines):
    state, store = open_store(tmp_path / "s.sqlite")
    state.start_run(RUN1, "internships", 5)
    state.end_run(RUN1, "complete", None, {})
    board = add_board(store)
    ranked = []
    for n, (text, deadline) in enumerate(zip(texts, deadlines, strict=True), 1):
        (pid,) = store.upsert_postings(board, [posting(str(n), text=text)], RUN1)
        opp = store.create_opportunity(
            company=f"Co{n}",
            url=f"https://a.example/{n}",
            record=record(deadline={"value": deadline} if deadline else {"value": "unknown"}),
            run_id=RUN1,
            posting_id=pid,
            linked_by="record",
        )
        ranked.append((opp, 10.0 - n, True))
    store.put_ranks(RUN1, ranked)
    rows = top_k_rows(store, RUN1)
    state.close()
    return rows


def test_new_top_k_offers_are_drafted(tmp_path, client, kilian, drafter):
    rows = _tracker(tmp_path, ["A posting.", "Please attach a Cover Letter."], [None, None])
    assert [r["letter"] for r in rows] == [False, True]
    with get_sessionmaker()() as db:
        lines = draft_new(db, rows, drafts.drafter_client(4))
    assert len(drafter.calls) == 2 and [c["payload"]["cover_letter"] for c in drafter.calls] == [
        False,
        True,
    ]
    assert lines[1].endswith("ready, with a letter")
    with get_sessionmaker()() as db:  # a second run drafts nothing again
        assert all(
            "already drafted" in line for line in draft_new(db, rows, drafts.drafter_client(4))
        )
    assert len(drafter.calls) == 2


def test_past_deadline_is_not_drafted(tmp_path, client, kilian, drafter):
    rows = _tracker(tmp_path, ["A posting."], ["2026-10-23"])
    with get_sessionmaker()() as db:
        lines = draft_new(db, rows, drafts.drafter_client(4))
    assert drafter.calls == [] and "deadline passed" in lines[0]
    assert drafts.models.deadline_passed("2026-10-23", date(2026, 11, 2))
    assert not drafts.models.deadline_passed("rolling", date(2026, 11, 2))
    assert drafts.models.deadline_passed("October 23, 2026", date(2026, 11, 2))


def test_listing_never_loads_the_files(client, kilian):
    client.post(
        "/api/drafts", json={"opportunityId": 7, "coverLetter": True}, headers=kilian.headers
    )
    statements: list[str] = []

    def record(conn, cursor, statement, *args):
        statements.append(statement)

    event.listen(get_engine(), "before_cursor_execute", record)
    try:
        listed = client.get("/api/drafts", headers=kilian.headers).json()["drafts"]
        client.get("/api/profile", headers=kilian.headers)
    finally:
        event.remove(get_engine(), "before_cursor_execute", record)
    assert (listed[0]["hasCv"], listed[0]["hasLetter"]) == (True, True)
    loaded = re.compile(
        r"application_drafts\.(cv_docx|letter_docx)(?! IS NOT NULL)"
        r"|applicant_profiles\.(cv_docx|fact_bank|rules_md|checks_yaml)"
    )
    assert not [s for s in statements if loaded.search(s)]


def test_drafter_down_fails_rows_not_the_job(tmp_path, client, kilian, drafter, sql):
    drafter.down = True
    rows = _tracker(tmp_path, ["One.", "Two."], [None, None])
    with get_sessionmaker()() as db:
        draft_new(db, rows, drafts.drafter_client(4))
    statuses = sql.rows("select status, error from application_drafts order by company")
    assert [s for s, _ in statuses] == ["failed", "failed"]
    assert all(e.startswith("no_answer") for _, e in statuses)


def test_failed_drafts_are_retried_on_the_next_run(tmp_path, client, kilian, drafter, sql):
    drafter.down = True
    rows = _tracker(tmp_path, ["One.", "Two.", "Three."], [None, None, None])
    with get_sessionmaker()() as db:
        draft_new(db, rows[:2], drafts.drafter_client(4))
    drafter.down = False
    drafter.calls.clear()
    # The next run: the two offers are still in the top K but no longer new, and a third
    # top-K offer that was never drafted isn't new either (it predates drafting).
    later = [{**row, "section": "top_k"} for row in rows]
    with get_sessionmaker()() as db:
        draft_new(db, later, drafts.drafter_client(4))
    assert len(drafter.calls) == 2
    assert [s for (s,) in sql.rows("select status from application_drafts")] == ["ready", "ready"]
