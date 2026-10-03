"""Tavily search client, with the same failure classification as the model client."""

import random
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

import httpx

from tracker.config import Policy
from tracker.errors import send_with_retries
from tracker.trace import Trace

CREDITS_PER_SEARCH = {"basic": 1, "advanced": 2}


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class SearchResponse:
    results: list[SearchResult]
    credits: float
    attempt: int
    latency_ms: float


class SearchClient:
    def __init__(
        self,
        policy: Policy,
        api_key: str,
        trace: Trace,
        *,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        deadline: float | None = None,
        rng: Callable[[], float] = random.random,
    ) -> None:
        self.policy = policy
        self.trace = trace
        self.provider = policy.search_provider()
        self.url = policy.search.base_url.rstrip("/") + "/search"
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._client = client or httpx.Client(timeout=policy.search.timeout_seconds)
        self._sleep = sleep
        self.deadline = deadline
        self._rng = rng

    def search(self, query: str, step: int) -> SearchResponse:
        cfg = self.policy.search
        payload = {
            "query": query,
            "max_results": cfg.max_results,
            "search_depth": cfg.depth,
            "include_usage": True,
        }

        def on_attempt(event: dict[str, Any]) -> None:
            self.trace.event("tool", step=step, tool="search_web", args={"query": query}, **event)

        response, attempt, latency_ms = send_with_retries(
            lambda: self._client.post(self.url, json=payload, headers=self._headers),
            provider=self.provider,
            retry=self.policy.retry,
            on_attempt=on_attempt,
            sleep=self._sleep,
            deadline=self.deadline,
            rng=self._rng,
        )
        data = response.json()
        results = [
            SearchResult(
                title=str(item.get("title") or ""),
                url=str(item.get("url") or ""),
                snippet=str(item.get("content") or ""),
            )
            for item in (data.get("results") or [])
            if item.get("url")
        ][: cfg.max_results]
        credits = (data.get("usage") or {}).get("credits")
        if not isinstance(credits, int | float):
            credits = CREDITS_PER_SEARCH[cfg.depth]
        return SearchResponse(results, float(credits), attempt, latency_ms)
