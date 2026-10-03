"""Failure classification and capped retries for the model and search providers.

`classify()` is a pure function: given a provider's response (or the exception raised
instead of one) it decides whether the failure is transient, and worth retrying after
a wait, or terminal, which stops the run with a message saying what to fix.
`send_with_retries()` applies that decision to one HTTP request.
"""

import email.utils
import random
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import httpx

if TYPE_CHECKING:
    from tracker.config import RetryPolicy

TerminalKind = Literal["auth", "payment", "quota", "request", "unreachable"]


class PolicyError(Exception):
    """The policy file or the environment is invalid. Raised before any network call."""


class StateLocked(Exception):
    """Another run holds the state file."""


class WallClockExceeded(Exception):
    """Waiting for a retry would pass the run's wall-clock budget."""


class TerminalError(Exception):
    """A failure that ends the run: retrying cannot fix it."""

    def __init__(self, provider: str, kind: TerminalKind, message: str) -> None:
        super().__init__(message)
        self.provider = provider
        self.kind = kind
        self.message = message


@dataclass(frozen=True)
class Provider:
    """What classification needs to know about a provider."""

    name: str
    key_env: str
    quota_patterns: tuple[str, ...]


@dataclass(frozen=True)
class Transient:
    wait: float
    reason: str


@dataclass(frozen=True)
class Terminal:
    kind: TerminalKind
    message: str


def backoff(attempt: int, retry: "RetryPolicy", rng: Callable[[], float] = random.random) -> float:
    """Exponential backoff for the given 0-based attempt, capped, with 50-100% jitter."""
    return min(retry.max_wait_seconds, retry.base_seconds * 2**attempt) * (0.5 + rng() / 2)


def parse_retry_after(headers: Mapping[str, str]) -> float | None:
    value = headers.get("retry-after")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, when.timestamp() - time.time())


_RESET_HINT = re.compile(r"try again in ([0-9hms.]+)", re.IGNORECASE)


def _reset_hint(headers: Mapping[str, str], body: str) -> str:
    if match := _RESET_HINT.search(body):
        return f" The provider says to try again in {match.group(1)}."
    if (wait := parse_retry_after(headers)) is not None:
        return f" The provider says to retry after {wait:.0f} seconds."
    return ""


def classify(
    provider: Provider,
    retry: "RetryPolicy",
    attempt: int,
    *,
    status: int | None = None,
    headers: Mapping[str, str] | None = None,
    body: str = "",
    exception: Exception | None = None,
    rng: Callable[[], float] = random.random,
) -> Transient | Terminal:
    """Classify one failed attempt. `attempt` is 0-based and only sets the backoff."""
    headers = headers or {}
    name = provider.name
    if exception is not None:
        if isinstance(exception, httpx.TimeoutException):
            return Transient(backoff(attempt, retry, rng), "timeout")
        if isinstance(exception, httpx.TransportError):
            return Transient(backoff(attempt, retry, rng), "connection_error")
        return Terminal("request", f"{name} call failed: {type(exception).__name__}: {exception}")

    assert status is not None
    if status in (401, 403):
        return Terminal(
            "auth",
            f"{name} rejected the API key (HTTP {status}). "
            f"Check {provider.key_env} in backend/.env or the environment.",
        )
    if status == 402:
        return Terminal(
            "payment",
            f"{name} requires payment or credit (HTTP 402). "
            "Add credit to the account or switch provider in config.yaml.",
        )
    if status == 432 or (
        status == 429 and any(re.search(p, body, re.IGNORECASE) for p in provider.quota_patterns)
    ):
        return Terminal(
            "quota",
            f"{name} quota is exhausted (HTTP {status}): a daily, monthly or plan limit "
            f"was reached.{_reset_hint(headers, body)}",
        )
    if status == 429:
        wait = parse_retry_after(headers)
        if wait is not None and wait > retry.max_wait_seconds:
            return Terminal(
                "quota",
                f"{name} asked to wait {wait:.0f} seconds (HTTP 429), longer than "
                f"retry.max_wait_seconds ({retry.max_wait_seconds:.0f}). Treating it as a "
                "quota limit; try again later.",
            )
        return Transient(wait if wait is not None else backoff(attempt, retry, rng), "rate_limit")
    if status == 408 or 500 <= status <= 599:
        return Transient(backoff(attempt, retry, rng), f"http_{status}")
    return Terminal("request", f"{name} rejected the request (HTTP {status}): {body[:300]}")


AttemptHook = Callable[[dict], None]


def send_with_retries(
    send: Callable[[], httpx.Response],
    *,
    provider: Provider,
    retry: "RetryPolicy",
    on_attempt: AttemptHook,
    sleep: Callable[[float], None] = time.sleep,
    deadline: float | None = None,
    clock: Callable[[], float] = time.monotonic,
    rng: Callable[[], float] = random.random,
    accept: Callable[[httpx.Response], bool] | None = None,
) -> tuple[httpx.Response, int, float]:
    """Send one request, retrying transient failures with capped backoff.

    Returns the successful response, its 1-based attempt number and its latency in ms.
    `on_attempt` receives one dict per failed attempt (status `retry` or `error`), so the
    caller can trace it. `accept` lets a caller take a 4xx response as its own result
    instead of classifying it. Raises `TerminalError` for a terminal failure or when
    attempts run out, and `WallClockExceeded` when a wait would pass `deadline`.
    """
    last_reason = ""
    for attempt in range(retry.max_attempts):
        started = clock()
        response: httpx.Response | None = None
        try:
            response = send()
        except httpx.HTTPError as exc:
            outcome = classify(provider, retry, attempt, exception=exc, rng=rng)
        latency_ms = round((clock() - started) * 1000, 1)
        if response is not None:
            if response.status_code < 400 or (accept is not None and accept(response)):
                return response, attempt + 1, latency_ms
            outcome = classify(
                provider,
                retry,
                attempt,
                status=response.status_code,
                headers=response.headers,
                body=response.text,
                rng=rng,
            )
        event = {
            "attempt": attempt + 1,
            "latency_ms": latency_ms,
            "http_status": response.status_code if response is not None else None,
        }
        if isinstance(outcome, Terminal):
            on_attempt(
                {**event, "status": "error", "failure_class": "terminal", "reason": outcome.kind}
            )
            raise TerminalError(provider.name, outcome.kind, outcome.message)

        last_reason = outcome.reason
        if attempt + 1 == retry.max_attempts:
            on_attempt(
                {**event, "status": "error", "failure_class": "transient", "reason": last_reason}
            )
            break
        on_attempt(
            {
                **event,
                "status": "retry",
                "failure_class": "transient",
                "reason": last_reason,
                "wait_seconds": round(outcome.wait, 2),
            }
        )
        if deadline is not None and clock() + outcome.wait > deadline:
            raise WallClockExceeded
        sleep(outcome.wait)

    raise TerminalError(
        provider.name,
        "unreachable",
        f"{provider.name} is unreachable: {retry.max_attempts} attempts failed "
        f"(last: {last_reason}). Check the network connection and the provider's status.",
    )
