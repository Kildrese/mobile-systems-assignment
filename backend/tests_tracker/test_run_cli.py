"""`python -m tracker run` end to end, against a local fake provider server."""

import json
import os
import socket
import subprocess
import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from tests_tracker.conftest import (
    MODEL_KEY,
    SEARCH_KEY,
    chat_body,
    read_trace,
    search_body,
    tool_call,
)

BACKEND = Path(__file__).resolve().parents[1]
SOURCE = "https://news.example.com/robots"


class FakeProviders(ThreadingHTTPServer):
    """Serves scripted chat completions at /v1/chat/completions and search at /search."""

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), Handler)
        self.chat_replies: list[tuple[int, dict]] = []
        self.chat_calls = 0

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"


class Handler(BaseHTTPRequestHandler):
    server: FakeProviders

    def log_message(self, *args) -> None:
        pass

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("content-length", 0)))
        if self.path == "/v1/chat/completions":
            self.server.chat_calls += 1
            replies = self.server.chat_replies
            status, body = replies.pop(0) if len(replies) > 1 else replies[0]
        elif self.path == "/search":
            status, body = 200, search_body(SOURCE)
        else:
            status, body = 404, {}
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@pytest.fixture
def providers() -> Iterator[FakeProviders]:
    server = FakeProviders()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def closed_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_tracker(config: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k.lower() not in ("http_proxy", "https_proxy")}
    env.update(FAKE_LLM_KEY=MODEL_KEY, FAKE_SEARCH_KEY=SEARCH_KEY, NO_PROXY="*")
    return subprocess.run(
        [sys.executable, "-m", "tracker", "run", "--config", str(config)],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )


def config_for(write_config, base_url: str) -> Path:
    return write_config(
        providers={"fake": {"base_url": f"{base_url}/v1"}},
        search={"base_url": base_url},
    )


def report_and_trace(result: subprocess.CompletedProcess) -> tuple[str, list[dict]]:
    lines = dict(line.split(":", 1) for line in result.stdout.splitlines() if ":" in line)
    report = Path(lines["Report"].strip()).read_text()
    trace = read_trace(Path(lines["Trace"].strip()))
    return report, trace


def test_complete_run_exits_0(providers, write_config):
    items = [{"title": "Open model", "summary": "Released.", "sources": [SOURCE]}]
    providers.chat_replies = [
        (200, chat_body(tool_call("search_web", {"query": "robots"}))),
        (200, chat_body(tool_call("finish", {"items": items}, "c2"))),
    ]
    result = run_tracker(config_for(write_config, providers.url))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "complete: 1 items" in result.stdout
    report, trace = report_and_trace(result)
    assert "### 1. Open model" in report
    assert trace[-1]["outcome"] == "complete"


def test_bogus_key_exits_3_with_one_line(providers, write_config):
    providers.chat_replies = [(401, {"error": {"message": "Invalid API Key"}})]
    result = run_tracker(config_for(write_config, providers.url))
    assert result.returncode == 3
    assert "Traceback" not in result.stderr
    (message,) = result.stderr.strip().splitlines()
    assert message.startswith("Terminal failure (auth) from fake: fake rejected the API key")
    assert "FAKE_LLM_KEY" in message
    assert providers.chat_calls == 1
    report, trace = report_and_trace(result)
    assert "**Status:** partial" in report
    assert MODEL_KEY not in json.dumps(trace)


def test_network_cut_exits_3_after_capped_retries(write_config):
    config = config_for(write_config, f"http://127.0.0.1:{closed_port()}")
    result = run_tracker(config)
    assert result.returncode == 3
    assert "Traceback" not in result.stderr
    assert "unreachable" in result.stderr
    report, trace = report_and_trace(result)
    assert "**Status:** partial" in report
    model_events = [e for e in trace if e["kind"] == "model"]
    assert [e["status"] for e in model_events] == ["retry", "retry", "error"]
    assert trace[-1]["stop_reason"] == "terminal:unreachable"


def test_invalid_policy_exits_before_network(write_config):
    result = run_tracker(write_config(k=12))
    assert result.returncode == 1
    assert "k must be between 3 and 10" in result.stderr
    assert "Traceback" not in result.stderr


def test_missing_key_exits_before_network(write_config, tmp_path):
    env = {**os.environ, "FAKE_LLM_KEY": "x", "FAKE_SEARCH_KEY": ""}
    result = subprocess.run(
        [sys.executable, "-m", "tracker", "run", "--config", str(write_config())],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    assert result.returncode == 1
    assert "FAKE_SEARCH_KEY is not set" in result.stderr
    assert "backend/.env.example" in result.stderr
