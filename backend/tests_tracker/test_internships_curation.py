"""opportunity-curation: quote verification, the Curator's tools, and same-role matching."""

import pytest
import respx

from tests_tracker.conftest import PUBLIC_IP, resolver_for
from tests_tracker.internships_helpers import RUN1, add_board, open_store, posting, record
from tracker.usecases.internships.curation import (
    candidates,
    fetch_posting_detail,
    flag_unclear,
    get_posting,
    link_exact,
    mark_same,
    normalize_company,
    quote_found,
    save_record,
    title_similarity,
)
from tracker.usecases.internships.http import GuardedHttp
from tracker.usecases.internships.sources import POSTING_HOSTS


@pytest.fixture
def store(tmp_path):
    state, store = open_store(tmp_path / "s.sqlite")
    yield store
    state.close()


def _one_posting(store, external_id="1", board="acme", company="Acme", **overrides):
    source_id = add_board(store, board=board, company=company)
    [pid] = store.upsert_postings(source_id, [posting(external_id, **overrides)], RUN1)
    return pid


# Quote verification


@pytest.mark.parametrize(
    "quote",
    [
        "Software Engineering Intern, Summer 2027",
        "software   engineering intern,\nsummer 2027",  # whitespace and case
        "Pay: $45/hour",
    ],
)
def test_quote_found(quote):
    assert quote_found(quote, posting().text)


def test_curly_quotes_and_dashes_match():
    text = "We\u2019re hiring \u2014 \u201cSummer 2027\u201d interns"
    assert quote_found('We\'re hiring - "Summer 2027" interns', text)


def test_short_or_invented_quote_fails():
    assert not quote_found("NY", posting().text)
    assert not quote_found("Apply by Nov 1", posting().text)


def test_save_record_ok(store):
    pid = _one_posting(store)
    outcome = save_record(store, pid, record(), RUN1)
    assert outcome.ok, outcome.data
    opp = store.opportunity(outcome.data["opportunity_id"])
    assert opp["company"] == "Acme"  # from the source, not the model
    assert opp["url"] == "https://boards.greenhouse.io/acme/jobs/1"
    assert opp["term"] == "Summer 2027"
    assert opp["fields"]["deadline"] == {"value": "unknown"}
    assert store.posting(pid)["curation"] == "saved"


def test_invented_deadline_rejected(store):
    pid = _one_posting(store)
    bad = record(deadline={"value": "Nov 1", "quote": "Apply by Nov 1"})
    outcome = save_record(store, pid, bad, RUN1)
    assert outcome.reason == "quote_not_found"
    assert "deadline" in outcome.data["detail"]
    assert store.opportunities() == []
    assert store.posting(pid)["curation"] == "pending"


def test_known_field_without_quote_rejected(store):
    pid = _one_posting(store)
    outcome = save_record(store, pid, record(term={"value": "Summer 2027"}), RUN1)
    assert outcome.reason == "quote_not_found"


def test_term_unknown_needs_no_quote(store):
    pid = _one_posting(store, text="An internship in New York.")
    rec = record(
        title={"value": "Software Engineering Intern", "quote": "Software Engineering Intern"},
        role_type={"value": "internship", "quote": "An internship"},
        term={"value": "unknown"},
        locations={"value": ["New York"], "quote": "in New York"},
        compensation={"value": "unknown"},
        work_authorization={"value": "unknown"},
    )
    outcome = save_record(store, pid, rec, RUN1)
    assert outcome.ok, outcome.data
    assert store.opportunity(outcome.data["opportunity_id"])["term"] == "unknown"


def test_invalid_record_shape(store):
    pid = _one_posting(store)
    outcome = save_record(store, pid, record(role_type={"value": "contractor"}), RUN1)
    assert outcome.reason == "invalid_arguments"
    outcome = save_record(store, pid, {"title": {"value": "x", "quote": "x"}, "extra": 1}, RUN1)
    assert outcome.reason == "invalid_arguments"


def test_work_authorization_stored_as_quote(store):
    pid = _one_posting(store)
    outcome = save_record(store, pid, record(), RUN1)
    stored = store.opportunity(outcome.data["opportunity_id"])["fields"]["work_authorization"]
    assert stored["quote"] == "must be authorized to work in the US"


def test_already_processed(store):
    pid = _one_posting(store)
    assert save_record(store, pid, record(), RUN1).ok
    assert save_record(store, pid, record(), RUN1).reason == "already_processed"
    assert flag_unclear(store, 999, "x").reason == "unknown_posting"


# Detail pages


@respx.mock
def test_detail_page_supplies_a_quote(store, policy):
    pid = _one_posting(store, location="", text="Software Engineering Intern, Summer 2027.")
    respx.get(f"https://{PUBLIC_IP}/acme/jobs/1").respond(
        200,
        headers={"content-type": "text/html"},
        content=b"<html><body><p>Office: Brooklyn, NY</p></body></html>",
    )
    http = GuardedHttp(policy.fetch, policy.retry, resolver=resolver_for(PUBLIC_IP))
    outcome = fetch_posting_detail(
        store, pid, "https://boards.greenhouse.io/acme/jobs/1", hosts=POSTING_HOSTS, http=http
    )
    assert outcome.ok
    assert "Brooklyn" in outcome.untrusted
    rec = record(
        role_type={"value": "unknown"},
        locations={"value": ["Brooklyn, NY"], "quote": "Office: Brooklyn, NY"},
        compensation={"value": "unknown"},
        work_authorization={"value": "unknown"},
    )
    assert save_record(store, pid, rec, RUN1).ok


def test_detail_fetch_off_list_host(store, policy):
    pid = _one_posting(store)
    calls = []

    class Recorder:
        def get(self, url, **_):
            calls.append(url)
            raise AssertionError("no request should be made")

    outcome = fetch_posting_detail(
        store, pid, "https://evil.example.org/jobs/1", hosts=POSTING_HOSTS, http=Recorder()
    )
    assert outcome.reason == "host_not_allowed"
    assert calls == []


def test_detail_fetch_of_another_posting(store):
    # Quotes are checked against the detail text, so it must be this posting's own page.
    pid = _one_posting(store)

    class Refuse:
        def get(self, url, **_):
            raise AssertionError("no request should be made")

    outcome = fetch_posting_detail(
        store, pid, "https://boards.greenhouse.io/acme/jobs/2", hosts=POSTING_HOSTS, http=Refuse()
    )
    assert outcome.reason == "url_mismatch"


def test_get_posting_wraps_text_as_untrusted(store):
    pid = _one_posting(store)
    outcome = get_posting(store, pid)
    assert outcome.ok
    assert outcome.untrusted.startswith("Software Engineering Intern")
    assert outcome.data["company"] == "Acme"


# Matching


def test_exact_url_linked_by_code(store):
    first = _one_posting(store, "1")
    oid = save_record(store, first, record(), RUN1).data["opportunity_id"]
    # Same posting URL listed by a second source (another board name).
    second = _one_posting(
        store,
        "x9",
        board="acme-careers",
        url="https://boards.greenhouse.io/acme/jobs/1?utm_source=x",
    )
    assert link_exact(store, second) == oid
    assert store.posting(second)["curation"] == "linked"
    assert len(store.linked_postings(oid)) == 2


def test_candidates_same_company_only(store):
    first = _one_posting(store, "1")
    oid = save_record(store, first, record(), RUN1).data["opportunity_id"]
    same = _one_posting(store, "2", board="acme2", title="Software Engineer Intern (Summer 2027)")
    other = _one_posting(
        store, "3", board="beta", company="Beta Inc.", title="Software Engineering Intern"
    )
    assert [c["opportunity_id"] for c in candidates(store, store.posting(same))] == [oid]
    assert candidates(store, store.posting(other)) == []
    # The model sees only the untrusted block, so the candidates must be in it.
    assert f'"opportunity_id": {oid}' in get_posting(store, same).untrusted


def test_mark_same_and_company_mismatch(store):
    first = _one_posting(store, "1")
    oid = save_record(store, first, record(), RUN1).data["opportunity_id"]
    same = _one_posting(store, "2", board="acme2", company="ACME, Inc.")
    other = _one_posting(store, "3", board="beta", company="Beta")

    mismatch = mark_same(store, other, oid, "looks similar")
    assert mismatch.reason == "company_mismatch"
    assert store.posting(other)["curation"] == "pending"

    assert mark_same(store, same, oid, "same title and city").ok
    assert store.posting(same)["curation"] == "linked"


def test_flag_unclear(store):
    pid = _one_posting(store)
    assert flag_unclear(store, pid, "no term or location").ok
    row = store.posting(pid)
    assert row["curation"] == "unclear"
    assert row["unclear_reason"] == "no term or location"


def test_company_and_title_normalization():
    assert normalize_company("ACME, Inc.") == normalize_company("Acme")
    assert title_similarity(
        "Software Engineering Intern, Summer 2027", "Software Engineering Intern (Fall 2026)"
    ) == pytest.approx(1.0)
    assert title_similarity("Design Intern", "Software Engineering Intern") == 0.0
