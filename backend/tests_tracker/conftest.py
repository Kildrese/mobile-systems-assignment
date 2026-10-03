"""Shared fixtures for the tracker tests.

Nothing here touches Postgres or the network: providers are faked with respx or a
local HTTP server, and DNS with a stub resolver.
"""

import copy
import json
import socket
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from tracker.config import Policy, TrackerSecrets, policy_from_dict

LLM_URL = "https://llm.test/v1/chat/completions"
SEARCH_URL = "https://search.test/search"
PUBLIC_IP = "93.184.215.14"
MODEL_KEY = "sk-test-model-key-0123456789"
SEARCH_KEY = "tvly-test-search-key-9876543210"

BASE_POLICY: dict[str, Any] = {
    "topic": "Open-source robotics foundation models",
    "k": 3,
    "model": {"provider": "fake", "name": "fake-model", "max_output_tokens": 256},
    "providers": {
        "fake": {
            "base_url": "https://llm.test/v1",
            "key_env": "FAKE_LLM_KEY",
            "price_per_mtok_in": 0,
            "price_per_mtok_out": 0,
            "quota_patterns": ["per day", "\\(RPD\\)", "\\(TPD\\)"],
        }
    },
    "search": {
        "provider": "tavily",
        "key_env": "FAKE_SEARCH_KEY",
        "base_url": "https://search.test",
        "max_results": 3,
        "depth": "basic",
        "quota_patterns": ["plan", "credit"],
    },
    "tools": ["search_web", "fetch_article", "finish"],
    "limits": {
        "max_steps": 8,
        "max_searches": 3,
        "max_fetches": 4,
        "max_tokens": 20000,
        "reserve_tokens": 3000,
        "max_cost_usd": 0.5,
        "max_wall_seconds": 120,
    },
    "retry": {"max_attempts": 3, "base_seconds": 0.01, "max_wait_seconds": 5},
    "fetch": {
        "allowed_schemes": ["https", "http"],
        "allowed_hosts": ["*"],
        "connect_timeout": 2,
        "read_timeout": 2,
        "deadline_seconds": 5,
        "max_bytes": 50000,
        "max_redirects": 3,
        "max_chars_for_model": 2000,
    },
    "instructions": "You track {topic}. Report the top {k} developments.",
}


def deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


@pytest.fixture
def make_policy(tmp_path: Path) -> Callable[..., Policy]:
    def make(**overrides: Any) -> Policy:
        return policy_from_dict(deep_merge(BASE_POLICY, overrides), tmp_path)

    return make


@pytest.fixture
def policy(make_policy: Callable[..., Policy]) -> Policy:
    return make_policy()


@pytest.fixture
def write_config(tmp_path: Path) -> Callable[..., Path]:
    def write(data: dict[str, Any] | None = None, **overrides: Any) -> Path:
        path = tmp_path / "config.yaml"
        path.write_text(yaml.safe_dump(deep_merge(data or BASE_POLICY, overrides)))
        return path

    return write


@pytest.fixture
def keys() -> TrackerSecrets:
    return TrackerSecrets(MODEL_KEY, SEARCH_KEY)


def resolver_for(*ips: str) -> Callable[..., list]:
    """A stub for `socket.getaddrinfo` that returns the given addresses in order per call."""
    answers = list(ips)

    def resolve(host: str, port: int, type: int = 0, **_: Any) -> list:
        ip = answers.pop(0) if len(answers) > 1 else answers[0]
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, "", (ip, port))]

    return resolve


@pytest.fixture
def public_resolver() -> Callable[..., list]:
    return resolver_for(PUBLIC_IP)


def tool_call(name: str, args: dict[str, Any] | str, call_id: str = "call_1") -> dict[str, Any]:
    raw = args if isinstance(args, str) else json.dumps(args)
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": raw}}


def chat_body(
    *calls: dict[str, Any], content: str | None = None, prompt: int = 100, completion: int = 20
) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if calls:
        message["tool_calls"] = list(calls)
    return {
        "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls"}],
        "usage": {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
        },
    }


def search_body(*urls: str) -> dict[str, Any]:
    return {
        "query": "q",
        "results": [
            {"title": f"Result {i}", "url": url, "content": f"Snippet {i}", "score": 0.9}
            for i, url in enumerate(urls, start=1)
        ],
        "usage": {"credits": 1},
    }


def read_trace(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines()]
