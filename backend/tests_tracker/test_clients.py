"""ChatClient and SearchClient against faked providers (respx)."""

import json

import httpx
import pytest
import respx

from tests_tracker.conftest import (
    LLM_URL,
    MODEL_KEY,
    SEARCH_KEY,
    SEARCH_URL,
    chat_body,
    read_trace,
    search_body,
    tool_call,
)
from tracker.errors import TerminalError
from tracker.llm import ChatClient, ModelOutputError
from tracker.search import SearchClient
from tracker.trace import Trace

RPD_BODY = '{"error":{"message":"Rate limit reached on requests per day (RPD): Limit 1000"}}'
TPM_BODY = '{"error":{"message":"Rate limit reached on tokens per minute (TPM): Limit 8000"}}'


@pytest.fixture
def trace(tmp_path):
    t = Trace(tmp_path / "trace.jsonl", "run", [MODEL_KEY, SEARCH_KEY])
    yield t
    t.close()


def chat_client(policy, trace, waits=None):
    return ChatClient(
        policy, MODEL_KEY, trace, sleep=(waits if waits is not None else []).append, rng=lambda: 1.0
    )


@respx.mock
def test_chat_success_parses_tool_calls_and_usage(policy, trace):
    route = respx.post(LLM_URL).respond(
        json=chat_body(tool_call("search_web", {"query": "robots"}), prompt=120, completion=30)
    )
    reply = chat_client(policy, trace).chat([{"role": "user", "content": "hi"}], [], step=1)
    assert reply.tool_calls[0].name == "search_web"
    assert reply.tool_calls[0].arguments == {"query": "robots"}
    assert reply.usage.total_tokens == 150
    sent = route.calls.last.request
    assert sent.headers["authorization"] == f"Bearer {MODEL_KEY}"
    (event,) = read_trace(trace.path)
    assert event["kind"] == "model"
    assert event["status"] == "ok"
    assert (event["prompt_tokens"], event["completion_tokens"], event["total_tokens"]) == (
        120,
        30,
        150,
    )
    assert MODEL_KEY not in trace.path.read_text()


@respx.mock
def test_chat_retry_then_success(policy, trace):
    respx.post(LLM_URL).mock(
        side_effect=[
            httpx.Response(429, text=TPM_BODY, headers={"retry-after": "3"}),
            httpx.Response(200, json=chat_body(content="done")),
        ]
    )
    waits = []
    reply = chat_client(policy, trace, waits).chat([], None, step=4)
    assert reply.content == "done"
    assert waits == [3.0]
    events = read_trace(trace.path)
    assert [(e["status"], e["step"]) for e in events] == [("retry", 4), ("ok", 4)]
    assert events[0]["http_status"] == 429
    assert events[0]["failure_class"] == "transient"


@respx.mock
def test_chat_daily_429_is_terminal_without_retry(policy, trace):
    route = respx.post(LLM_URL).respond(429, text=RPD_BODY)
    with pytest.raises(TerminalError) as err:
        chat_client(policy, trace).chat([], None, step=1)
    assert err.value.kind == "quota"
    assert route.call_count == 1
    # The trace says what ran out, not only that something did (AGENT.md quotes it).
    (event,) = read_trace(trace.path)
    assert event["reason"] == "quota"
    assert event["detail"] == err.value.message


@respx.mock
def test_chat_bad_key_is_clean_terminal(policy, trace):
    respx.post(LLM_URL).respond(401, json={"error": {"message": "Invalid API Key"}})
    with pytest.raises(TerminalError) as err:
        chat_client(policy, trace).chat([], None, step=1)
    assert err.value.kind == "auth"
    assert err.value.message.startswith("fake rejected the API key (HTTP 401)")
    (event,) = read_trace(trace.path)
    assert event["status"] == "error"
    assert event["failure_class"] == "terminal"


@respx.mock
@pytest.mark.parametrize("code", ["tool_use_failed", "output_parse_failed"])
def test_chat_malformed_output_is_model_error(policy, trace, code):
    # Both are the model's mistake (seen from gpt-oss on Groq): retried, never terminal.
    respx.post(LLM_URL).respond(400, json={"error": {"code": code}})
    with pytest.raises(ModelOutputError):
        chat_client(policy, trace).chat([], None, step=1)


@respx.mock
def test_chat_requires_a_tool_call_when_tools_are_offered(policy, trace):
    route = respx.post(LLM_URL).respond(json=chat_body(tool_call("finish", {})))
    tools = [{"type": "function", "function": {"name": "finish", "parameters": {}}}]
    chat_client(policy, trace).chat([], tools, step=1)
    assert json.loads(route.calls[0].request.content)["tool_choice"] == "required"


@respx.mock
def test_chat_invalid_tool_arguments_are_reported(policy, trace):
    respx.post(LLM_URL).respond(json=chat_body(tool_call("fetch_article", "{not json")))
    (call,) = chat_client(policy, trace).chat([], None, step=1).tool_calls
    assert call.arguments is None
    assert "not valid JSON" in call.parse_error


# Search


def search_client(policy, trace):
    return SearchClient(policy, SEARCH_KEY, trace, sleep=lambda _: None, rng=lambda: 1.0)


@respx.mock
def test_search_caps_results_and_counts_credits(policy, trace):
    urls = [f"https://news.example.com/{i}" for i in range(6)]
    route = respx.post(SEARCH_URL).respond(json=search_body(*urls))
    response = search_client(policy, trace).search("robots", step=2)
    assert len(response.results) == policy.search.max_results
    assert response.results[0].snippet == "Snippet 1"
    assert response.credits == 1
    assert route.calls.last.request.headers["authorization"] == f"Bearer {SEARCH_KEY}"


@respx.mock
def test_search_432_is_terminal(policy, trace):
    route = respx.post(SEARCH_URL).respond(432, json={"detail": {"error": "plan limit"}})
    with pytest.raises(TerminalError) as err:
        search_client(policy, trace).search("robots", step=1)
    assert err.value.kind == "quota"
    assert route.call_count == 1


@respx.mock
def test_search_429_and_503_are_retried(policy, trace):
    route = respx.post(SEARCH_URL).mock(
        side_effect=[
            httpx.Response(429, text="too many requests"),
            httpx.Response(503),
            httpx.Response(200, json=search_body("https://a.example.com/")),
        ]
    )
    response = search_client(policy, trace).search("robots", step=1)
    assert route.call_count == 3
    assert response.attempt == 3
    assert [e["status"] for e in read_trace(trace.path)] == ["retry", "retry"]
