"""api-failure-handling: classification table and the retry helper."""

import httpx
import pytest

from tracker.errors import (
    Provider,
    RetrySettings,
    TerminalError,
    Transient,
    WallClockExceeded,
    backoff,
    classify,
    send_with_retries,
)

GROQ = Provider("groq", "GROQ_API_KEY", ("per day", r"\(RPD\)", r"\(TPD\)"))
TAVILY = Provider("tavily", "TAVILY_API_KEY", ("plan", "credit"))
RETRY = RetrySettings(max_attempts=4, base_seconds=1.0, max_wait_seconds=60)
TPM_BODY = (
    '{"error":{"message":"Rate limit reached for model `openai/gpt-oss-120b` on tokens per '
    'minute (TPM): Limit 8000, Used 7000, Requested 1500. Please try again in 7.5s."}}'
)
RPD_BODY = (
    '{"error":{"message":"Rate limit reached for model `openai/gpt-oss-120b` on requests per '
    'day (RPD): Limit 1000, Used 1000, Requested 1. Please try again in 1m26.4s."}}'
)


def no_jitter() -> float:
    return 1.0


@pytest.mark.parametrize(
    ("kwargs", "provider", "expected"),
    [
        ({"exception": httpx.ConnectTimeout("t")}, GROQ, "transient"),
        ({"exception": httpx.ReadTimeout("t")}, GROQ, "transient"),
        ({"exception": httpx.ConnectError("refused")}, GROQ, "transient"),
        ({"status": 401}, GROQ, "auth"),
        ({"status": 403}, GROQ, "auth"),
        ({"status": 402}, GROQ, "payment"),
        ({"status": 408}, GROQ, "transient"),
        ({"status": 432, "body": "plan limit exceeded"}, TAVILY, "quota"),
        ({"status": 429, "body": TPM_BODY, "headers": {"retry-after": "7"}}, GROQ, "transient"),
        ({"status": 429, "body": RPD_BODY}, GROQ, "quota"),
        ({"status": 429, "body": "slow down", "headers": {"retry-after": "3600"}}, GROQ, "quota"),
        ({"status": 429, "body": "too many requests"}, TAVILY, "transient"),
        ({"status": 500}, TAVILY, "transient"),
        ({"status": 502}, GROQ, "transient"),
        ({"status": 503}, TAVILY, "transient"),
        ({"status": 504}, GROQ, "transient"),
        ({"status": 400, "body": "bad request"}, GROQ, "request"),
        ({"status": 404}, GROQ, "request"),
        ({"status": 413}, GROQ, "request"),
    ],
)
def test_classification(kwargs, provider, expected):
    outcome = classify(provider, RETRY, 0, rng=no_jitter, **kwargs)
    kind = "transient" if isinstance(outcome, Transient) else outcome.kind
    assert kind == expected


def test_per_minute_429_honors_retry_after():
    outcome = classify(GROQ, RETRY, 0, status=429, headers={"retry-after": "7"}, body=TPM_BODY)
    assert outcome == Transient(7.0, "rate_limit")


def test_daily_cap_message_says_when_it_resets():
    outcome = classify(GROQ, RETRY, 0, status=429, body=RPD_BODY)
    assert "quota is exhausted" in outcome.message
    assert "try again in 1m26.4s" in outcome.message


def test_auth_message_names_key():
    outcome = classify(GROQ, RETRY, 0, status=401)
    assert "rejected the API key" in outcome.message
    assert "GROQ_API_KEY" in outcome.message


def test_backoff_is_capped_and_jittered():
    assert backoff(0, RETRY, no_jitter) == 1.0
    assert backoff(3, RETRY, no_jitter) == 8.0
    assert backoff(10, RETRY, no_jitter) == 60.0
    assert backoff(3, RETRY, lambda: 0.0) == 4.0


class Script:
    """Returns (or raises) scripted results, one per call."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls = 0

    def __call__(self) -> httpx.Response:
        self.calls += 1
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def run(script, retry=RETRY, provider=GROQ, **kwargs):
    events, waits = [], []
    response = send_with_retries(
        script,
        provider=provider,
        retry=retry,
        on_attempt=events.append,
        sleep=waits.append,
        rng=no_jitter,
        **kwargs,
    )
    return response, events, waits


def test_retry_then_success():
    script = Script(httpx.ReadTimeout("slow"), httpx.Response(200, json={}))
    (response, attempt, _), events, waits = run(script)
    assert response.status_code == 200
    assert attempt == 2
    assert [e["status"] for e in events] == ["retry"]
    assert events[0]["failure_class"] == "transient"
    assert waits == [1.0]


def test_daily_429_is_never_retried():
    script = Script(httpx.Response(429, text=RPD_BODY))
    with pytest.raises(TerminalError) as err:
        run(script)
    assert err.value.kind == "quota"
    assert script.calls == 1


def test_attempts_run_out_as_unreachable():
    script = Script(*[httpx.ConnectError("refused")] * 4)
    with pytest.raises(TerminalError) as err:
        run(script)
    assert err.value.kind == "unreachable"
    assert "unreachable" in err.value.message
    assert script.calls == RETRY.max_attempts


def test_wait_past_deadline_stops():
    script = Script(httpx.Response(503), httpx.Response(200))
    with pytest.raises(WallClockExceeded):
        run(script, deadline=0.5, clock=lambda: 0.0)


def test_accept_hook_returns_4xx_unclassified():
    script = Script(httpx.Response(400, text="tool_use_failed"))
    (response, _, _), events, _ = run(script, accept=lambda r: "tool_use_failed" in r.text)
    assert response.status_code == 400
    assert events == []
