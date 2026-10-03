"""agent-loop: a scripted fake model drives the real loop."""

import json
from pathlib import Path

import httpx
import respx

from tests_tracker.conftest import (
    LLM_URL,
    PUBLIC_IP,
    SEARCH_URL,
    chat_body,
    read_trace,
    search_body,
    tool_call,
)
from tests_tracker.test_fetch import HTML, PAGE
from tracker.loop import Runner
from tracker.state import StateStore
from tracker.tools import TOOL_SCHEMAS

INJECTION_PAGE = (Path(__file__).parent / "fixtures" / "injection.html").read_bytes()
URLS = [f"https://news.example.com/{i}" for i in range(1, 6)]


class FakeModel:
    """Answers chat calls from a script and records every request body."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content))
        reply = self.replies.pop(0) if self.replies else chat_body(content="thinking")
        if isinstance(reply, httpx.Response):
            return reply
        return httpx.Response(200, json=reply)


def runner(policy, keys, public_resolver, **kwargs):
    return Runner(
        policy, keys, run_id="test-run", resolver=public_resolver, sleep=lambda _: None, **kwargs
    )


def finish_call(*urls, call_id="call_f"):
    items = [
        {"title": f"Dev {i}", "summary": f"Summary {i}.", "sources": [u]}
        for i, u in enumerate(urls, start=1)
    ]
    return tool_call("finish", {"items": items, "note": "ok"}, call_id)


def mock_pages(router):
    for i in range(1, 6):
        router.get(f"https://{PUBLIC_IP}/{i}").respond(200, headers=HTML, content=PAGE)


@respx.mock
def test_complete_run(policy, keys, public_resolver):
    model = FakeModel(
        chat_body(tool_call("search_web", {"query": "robotics models"})),
        chat_body(tool_call("fetch_article", {"url": URLS[0]}, "c2")),
        chat_body(finish_call(URLS[0], URLS[1])),
    )
    respx.post(LLM_URL).mock(side_effect=model)
    respx.post(SEARCH_URL).respond(json=search_body(*URLS[:3]))
    mock_pages(respx)

    result = runner(policy, keys, public_resolver).run()

    assert result.status == "complete"
    assert result.exit_code == 0
    text = result.report_path.read_text()
    assert "**Status:** complete" in text
    assert "### 1. Dev 1" in text and "### 2. Dev 2" in text
    events = read_trace(result.trace_path)
    assert events[-1]["kind"] == "summary"
    assert events[-1]["outcome"] == "complete"
    assert events[-1]["steps"] == 3
    # Retrieved text reached the model only inside a data block.
    tool_messages = [m for m in model.requests[-1]["messages"] if m["role"] == "tool"]
    assert all("<untrusted_data" in m["content"] for m in tool_messages)
    assert model.requests[0]["tools"][0]["function"]["name"] == "search_web"
    with StateStore(policy.state_file) as state:
        assert (
            state.db.execute("SELECT * FROM runs WHERE id = ?", ("test-run",)).fetchone()["status"]
            == "complete"
        )
        assert state.db.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 2


@respx.mock
def test_fetch_budget_reached(make_policy, keys, public_resolver):
    policy = make_policy(limits={"max_fetches": 1})
    model = FakeModel(
        chat_body(tool_call("search_web", {"query": "q"})),
        chat_body(tool_call("fetch_article", {"url": URLS[0]}, "c2")),
        chat_body(tool_call("fetch_article", {"url": URLS[1]}, "c3")),
        chat_body(finish_call(URLS[0])),
    )
    respx.post(LLM_URL).mock(side_effect=model)
    respx.post(SEARCH_URL).respond(json=search_body(*URLS[:2]))
    route2 = respx.get(f"https://{PUBLIC_IP}/2").respond(200, headers=HTML, content=PAGE)
    respx.get(f"https://{PUBLIC_IP}/1").respond(200, headers=HTML, content=PAGE)

    result = runner(policy, keys, public_resolver).run()

    assert result.status == "complete"
    assert not route2.called
    budget_events = [e for e in read_trace(result.trace_path) if e.get("status") == "budget"]
    assert budget_events[0]["tool"] == "fetch_article"
    last_tool = [m for m in model.requests[3]["messages"] if m["role"] == "tool"][-1]
    assert "budget_exhausted" in last_tool["content"]


@respx.mock
def test_step_budget_gives_partial_with_synthesis(make_policy, keys, public_resolver):
    policy = make_policy(limits={"max_steps": 2})
    synthesis = json.dumps(
        {"items": [{"title": "Synth", "summary": "From evidence.", "sources": [URLS[0]]}]}
    )
    model = FakeModel(
        chat_body(tool_call("search_web", {"query": "q"})),
        chat_body(tool_call("fetch_article", {"url": URLS[0]}, "c2")),
        chat_body(content=f"```json\n{synthesis}\n```"),
    )
    respx.post(LLM_URL).mock(side_effect=model)
    respx.post(SEARCH_URL).respond(json=search_body(URLS[0]))
    mock_pages(respx)

    result = runner(policy, keys, public_resolver).run()

    assert result.status == "partial"
    assert result.exit_code == 2
    assert result.stop_reason == "max_steps"
    assert "tools" not in model.requests[-1]  # the synthesis call offers no tools
    text = result.report_path.read_text()
    assert "partial (stopped because the step budget" in text
    assert "### 1. Synth" in text
    with StateStore(policy.state_file) as state:
        run = state.db.execute("SELECT * FROM runs WHERE id = ?", ("test-run",)).fetchone()
    assert (run["status"], run["stop_reason"]) == ("partial", "max_steps")


@respx.mock
def test_token_budget_partial_cites_only_fetched(make_policy, keys, public_resolver):
    policy = make_policy(limits={"max_tokens": 9000, "reserve_tokens": 2000})
    replies = [chat_body(tool_call("search_web", {"query": "q"}), prompt=1000)]
    replies += [
        chat_body(tool_call("fetch_article", {"url": URLS[i]}, f"c{i}"), prompt=1500)
        for i in range(4)
    ]
    replies.append(chat_body(content="not json at all"))  # synthesis fails -> fallback
    model = FakeModel(*replies)
    respx.post(LLM_URL).mock(side_effect=model)
    respx.post(SEARCH_URL).respond(json=search_body(*URLS))
    mock_pages(respx)

    result = runner(policy, keys, public_resolver).run()

    assert result.status == "partial"
    assert result.stop_reason == "max_tokens"
    text = result.report_path.read_text()
    assert "## Sources gathered" in text
    for url in URLS[:4]:
        assert url in text
    assert URLS[4] not in text


@respx.mock
def test_terminal_failure_after_evidence_gives_fallback(policy, keys, public_resolver):
    model = FakeModel(
        chat_body(tool_call("search_web", {"query": "q"})),
        chat_body(tool_call("fetch_article", {"url": URLS[0]}, "c2")),
        httpx.Response(429, text="Rate limit reached on requests per day (RPD)"),
    )
    respx.post(LLM_URL).mock(side_effect=model)
    respx.post(SEARCH_URL).respond(json=search_body(URLS[0]))
    mock_pages(respx)

    result = runner(policy, keys, public_resolver).run()

    assert result.status == "failed"
    assert result.exit_code == 3
    assert result.stop_reason == "terminal:quota"
    assert len(model.requests) == 3  # no synthesis call after a model-provider failure
    text = result.report_path.read_text()
    assert "**Status:** partial" in text
    assert "Robot Model Released" in text
    assert URLS[0] in text


@respx.mock
def test_unknown_tool_and_bad_arguments(policy, keys, public_resolver):
    model = FakeModel(
        chat_body(tool_call("delete_state", {})),
        chat_body(tool_call("fetch_article", "{broken", "c2")),
        chat_body(content="I will just talk."),
    )
    respx.post(LLM_URL).mock(side_effect=model)

    result = runner(policy, keys, public_resolver).run()

    events = read_trace(result.trace_path)
    unknown = next(e for e in events if e.get("tool") == "delete_state")
    assert unknown["status"] == "error"
    assert unknown["reason"] == "unknown_tool"
    second = model.requests[1]["messages"][-1]
    assert second["role"] == "tool"
    assert "Allowed tools: search_web, fetch_article, finish" in second["content"]
    # Two model calls plus two invalid tool calls count as steps.
    assert events[-1]["steps"] >= 4
    # A reply without a tool call gets a nudge.
    assert any(
        "You did not call a tool" in m["content"]
        for m in model.requests[-1]["messages"]
        if m["role"] == "user"
    )


@respx.mock
def test_uncited_finish_item_dropped(policy, keys, public_resolver):
    model = FakeModel(
        chat_body(tool_call("search_web", {"query": "q"})),
        chat_body(finish_call(URLS[0], "https://never-seen.example.org/")),
    )
    respx.post(LLM_URL).mock(side_effect=model)
    respx.post(SEARCH_URL).respond(json=search_body(URLS[0]))

    result = runner(policy, keys, public_resolver).run()

    assert result.status == "complete"
    assert [i["title"] for i in result.items] == ["Dev 1"]
    finish = next(e for e in read_trace(result.trace_path) if e.get("tool") == "finish")
    assert finish["dropped"][0]["sources"] == ["https://never-seen.example.org/"]


@respx.mock
def test_injection_page_cannot_change_tools_or_budgets(policy, keys, public_resolver):
    """The fake model "obeys" the injected page; the runtime does not."""
    respx.get(f"https://{PUBLIC_IP}/evil").respond(200, headers=HTML, content=INJECTION_PAGE)
    respx.post(SEARCH_URL).respond(json=search_body("https://news.example.com/evil"))
    model = FakeModel(
        chat_body(tool_call("search_web", {"query": "q"})),
        chat_body(tool_call("fetch_article", {"url": "https://news.example.com/evil"}, "c2")),
        # Obeying the page: a disallowed tool, then the internal URL it asked for.
        chat_body(
            tool_call("delete_state", {"confirm": True}, "c3"),
            tool_call("fetch_article", {"url": "http://169.254.169.254/latest/meta-data/"}, "c4"),
        ),
        chat_body(finish_call("https://news.example.com/evil")),
    )
    respx.post(LLM_URL).mock(side_effect=model)
    policy_before = policy.model_dump()

    result = runner(policy, keys, public_resolver).run()

    assert result.status == "complete"
    assert policy.model_dump() == policy_before
    events = read_trace(result.trace_path)
    fetched = next(e for e in events if e.get("tool") == "fetch_article" and e["status"] == "ok")
    assert fetched["injection_suspected"] is True
    rejected = [
        (e["tool"], e["status"], e["reason"])
        for e in events
        if e.get("status") in ("error", "blocked")
    ]
    assert ("delete_state", "error", "unknown_tool") in rejected
    assert ("fetch_article", "blocked", "blocked_address") in rejected
    # Every later request offers the same tools and the same system prompt.
    for request in model.requests:
        assert [t["function"]["name"] for t in request["tools"]] == list(TOOL_SCHEMAS)
        assert request["messages"][0]["content"].startswith(policy.system_prompt())
    page_message = [m for m in model.requests[2]["messages"] if m["role"] == "tool"][-1]
    assert page_message["content"].count("</untrusted_data>") == 1
