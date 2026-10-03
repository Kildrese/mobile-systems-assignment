"""HTTP for job boards and posting pages, through the core fetch guardrails.

`BoardHttp` is the seam the collectors and liveness checks depend on, so tests can
swap the transport. `GuardedHttp` sends every request through `fetch.fetch_page` (scheme,
host and address checks, pinned connection, size and time limits), adds conditional
request headers, and retries transient failures with the core's capped backoff.
"""

import socket
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import httpx

from tracker.config import FetchSettings, RetryPolicy
from tracker.errors import backoff
from tracker.fetch import FetchError, fetch_page
from tracker.guard import Blocked, Resolver

TRANSIENT_REASONS = {"timeout", "connection_error"}
TRANSIENT_STATUS = {408, 429, 500, 502, 503, 504}


@dataclass(frozen=True)
class HttpResult:
    url: str
    status: int  # 200 or 304
    text: str
    etag: str | None
    last_modified: str | None
    attempts: int
    latency_ms: float


class HttpFailure(Exception):
    """A request that failed for good. `reason` is machine-readable, `status` the HTTP code."""

    def __init__(self, reason: str, detail: str, status: int | None = None, attempts: int = 1):
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail
        self.status = status
        self.attempts = attempts


class BoardHttp(Protocol):
    def get(
        self, url: str, *, etag: str | None = None, last_modified: str | None = None
    ) -> HttpResult: ...


def is_transient(err: FetchError) -> bool:
    return err.reason in TRANSIENT_REASONS or (err.status in TRANSIENT_STATUS)


class GuardedHttp:
    def __init__(
        self,
        fetch: FetchSettings,
        retry: RetryPolicy,
        *,
        resolver: Resolver = socket.getaddrinfo,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        allowed_hosts: tuple[str, ...] | None = None,
    ) -> None:
        self.allowed_hosts = allowed_hosts  # narrower than fetch.allowed_hosts, if set
        self.fetch = fetch
        self.retry = retry
        self.resolver = resolver
        self.transport = transport
        self.sleep = sleep
        self.clock = clock

    def get(
        self, url: str, *, etag: str | None = None, last_modified: str | None = None
    ) -> HttpResult:
        headers = {"Accept": "application/json, text/html;q=0.9, text/plain;q=0.8"}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        last: FetchError | None = None
        for attempt in range(self.retry.max_attempts):
            started = self.clock()
            try:
                page = fetch_page(
                    url,
                    self.fetch,
                    resolver=self.resolver,
                    transport=self.transport,
                    clock=self.clock,
                    headers=headers,
                    allowed_hosts=self.allowed_hosts,
                )
            except Blocked as err:
                raise HttpFailure(err.reason, err.detail, attempts=attempt + 1) from None
            except FetchError as err:
                last = err
                if not is_transient(err):
                    raise HttpFailure(
                        err.reason, err.detail, err.status, attempts=attempt + 1
                    ) from None
                if attempt + 1 < self.retry.max_attempts:
                    self.sleep(backoff(attempt, self.retry))
                continue
            latency = round((self.clock() - started) * 1000, 1)
            return HttpResult(
                url, page.status, page.text, page.etag, page.last_modified, attempt + 1, latency
            )
        assert last is not None
        raise HttpFailure(
            "unreachable",
            f"{self.retry.max_attempts} attempts failed (last: {last.reason})",
            last.status,
            attempts=self.retry.max_attempts,
        )
