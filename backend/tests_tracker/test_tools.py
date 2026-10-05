"""tracker-tools: tool functions, argument validation and finish."""

import pytest
import respx
from pydantic import ValidationError

from tests_tracker.conftest import PUBLIC_IP, SEARCH_KEY, SEARCH_URL, read_trace, search_body
from tests_tracker.test_fetch import HTML, PAGE
from tracker.search import SearchClient
from tracker.state import StateStore
from tracker.tools import Toolbox, validate_finish
from tracker.trace import Trace


@pytest.fixture
def toolbox(policy, public_resolver, tmp_path):
    trace = Trace(tmp_path / "trace.jsonl", "r1")
    state = StateStore(tmp_path / "state.sqlite")
    search = SearchClient(policy, SEARCH_KEY, trace, sleep=lambda _: None)
    yield Toolbox(policy, trace, "r1", state=state, search_client=search, resolver=public_resolver)
    state.close()
    trace.close()


@respx.mock
def test_search_web_returns_results(toolbox):
    respx.post(SEARCH_URL).respond(json=search_body("https://a.example.com/1"))
    outcome = toolbox.search_web("open-source robotics foundation model release")
    assert outcome.ok
    (result,) = outcome.data["results"]
    assert set(result) == {"title", "url", "snippet"}
    assert "https://a.example.com/1" in toolbox.seen
    event = read_trace(toolbox.trace.path)[-1]
    assert event["tool"] == "search_web"
    assert event["credits"] == 1


@pytest.mark.parametrize("query", ["", "   ", "x" * 401])
def test_search_web_rejects_bad_query_without_request(toolbox, query):
    with respx.mock(assert_all_called=False) as mock:
        route = mock.post(SEARCH_URL)
        outcome = toolbox.search_web(query)
    assert outcome.status == "error"
    assert outcome.reason == "invalid_arguments"
    assert not route.called


@respx.mock
def test_fetch_fresh_then_cached(toolbox):
    route = respx.get(f"https://{PUBLIC_IP}/news/1").respond(200, headers=HTML, content=PAGE)
    first = toolbox.fetch_article("https://news.example.com/news/1?utm_source=x")
    assert first.status == "ok"
    assert first.data["cached"] is False
    assert first.data["url"] == "https://news.example.com/news/1"
    assert toolbox.is_cached("https://news.example.com/news/1")

    second = toolbox.fetch_article("https://NEWS.example.com/news/1#frag")
    assert second.status == "cached"
    assert second.data["cached"] is True
    assert second.data["text"] == first.data["text"]
    assert route.call_count == 1


@respx.mock
def test_fetch_truncates_text_for_model(toolbox, policy):
    long_page = b"<html><body><p>" + b"word " * 2000 + b"</p></body></html>"
    respx.get(f"https://{PUBLIC_IP}/long").respond(200, headers=HTML, content=long_page)
    outcome = toolbox.fetch_article("https://news.example.com/long")
    assert len(outcome.data["text"]) == policy.fetch.max_chars_for_model
    assert outcome.data["truncated"] is True
    stored = toolbox.state.get_article("https://news.example.com/long")
    assert len(stored["text"]) > policy.fetch.max_chars_for_model


def test_fetch_guardrail_is_a_result(toolbox):
    outcome = toolbox.fetch_article("http://127.0.0.1:8000/")
    assert outcome.status == "blocked"
    assert outcome.data == {"error": "blocked_address", "detail": outcome.data["detail"]}
    assert read_trace(toolbox.trace.path)[-1]["status"] == "blocked"


@respx.mock
def test_fetch_log_records_every_status(policy, public_resolver, tmp_path):
    respx.get(f"https://{PUBLIC_IP}/news/1").respond(200, headers=HTML, content=PAGE)
    respx.get(f"https://{PUBLIC_IP}/gone").respond(404)
    state = StateStore(tmp_path / "state.sqlite")
    trace = Trace(None, "r1").bind(stage="scout")
    toolbox = Toolbox(policy, trace, "r1", state=state, resolver=public_resolver)
    for url in (
        "https://news.example.com/news/1",
        "https://news.example.com/news/1",  # served from state
        "http://169.254.169.254/latest/meta-data/",
        "javascript:alert(1)",
        "https://news.example.com/gone",
    ):
        toolbox.fetch_article(url)
    rows = [
        tuple(r)
        for r in state.db.execute(
            "SELECT run_id, stage, kind, url, title, status, reason FROM fetch_log ORDER BY id"
        )
    ]
    state.close()
    assert rows == [
        ("r1", "scout", "page", "https://news.example.com/news/1", "Robot Model Released",
         "fetched", None),
        ("r1", "scout", "page", "https://news.example.com/news/1", "Robot Model Released",
         "skipped", None),
        ("r1", "scout", "page", "http://169.254.169.254/latest/meta-data/", "", "rejected",
         "blocked_address"),
        ("r1", "scout", "page", "javascript:alert(1)", "", "rejected", "scheme_not_allowed"),
        ("r1", "scout", "page", "https://news.example.com/gone", "", "failed", "http_error"),
    ]  # fmt: skip


def test_fetch_host_not_allowed(make_policy, tmp_path):
    policy = make_policy(fetch={"allowed_hosts": ["*.example.com"]})
    toolbox = Toolbox(policy, Trace(None, "r"), "r", state=None)
    assert toolbox.fetch_article("https://example.org/").reason == "host_not_allowed"


# finish

ITEMS = [
    {"title": f"Item {i}", "summary": f"Summary {i}", "sources": [f"https://e.com/{i}"]}
    for i in range(1, 6)
]


def test_finish_keeps_top_k():
    result = validate_finish({"items": ITEMS}, k=3)
    assert [i["title"] for i in result.items] == ["Item 1", "Item 2", "Item 3"]
    assert result.truncated == 2


def test_finish_orders_by_rank():
    items = [{**ITEMS[0], "rank": 2}, {**ITEMS[1], "rank": 1}]
    assert [i["title"] for i in validate_finish({"items": items}, k=3).items] == [
        "Item 2",
        "Item 1",
    ]


def test_finish_drops_unseen_sources():
    seen = {"https://e.com/1", "https://e.com/3"}
    items = [
        {**ITEMS[0], "sources": ["https://e.com/1?utm_source=x", "https://evil.test/"]},
        ITEMS[1],
        ITEMS[2],
    ]
    result = validate_finish({"items": items}, k=3, seen=seen)
    assert [i["title"] for i in result.items] == ["Item 1", "Item 3"]
    assert result.items[0]["sources"] == ["https://e.com/1?utm_source=x"]
    assert result.dropped == [
        {"title": "Item 2", "sources": ["https://e.com/2"], "reason": "unseen_source"}
    ]


@pytest.mark.parametrize(
    "raw",
    [
        {},
        {"items": []},
        {"items": [{"title": "t", "summary": "s", "sources": []}]},
        {"items": [{"title": "", "summary": "s", "sources": ["https://e.com"]}]},
    ],
)
def test_finish_validation(raw):
    with pytest.raises(ValidationError):
        validate_finish(raw, k=3)
