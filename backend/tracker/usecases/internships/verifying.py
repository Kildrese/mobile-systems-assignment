"""The Verify stage: the tracker as orchestrator, the verifier as a remote worker.

Each known field of a top-K opportunity becomes one claim, a sentence written by code
from the field's value. The quote the Curator found stays here: the verifier gets only
the claim and the posting URL, and fetches the page itself. One request per
opportunity, retried with the same `request_id` and the same bytes; every response is
checked against the contract before anything is stored.
"""

import json
import random
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
from agentkit.contract import VerifyRequest, VerifyResponse
from agentkit.fetch import parse_retry_after
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tracker.budget import Budget
from tracker.trace import Trace
from tracker.usecases.internships.curation import UNKNOWN
from tracker.usecases.internships.store import OpportunityStore

SERVICE = "verifier"
# Fields that become claims, in the order they are sent.
FIELDS = (
    "title",
    "role_type",
    "term",
    "locations",
    "remote",
    "compensation",
    "deadline",
    "work_authorization",
)
ROLE_WORDS = {
    "internship": "an internship",
    "new_grad": "a new-graduate role",
    "other": "not an internship",
}
REMOTE_WORDS = {"onsite": "on site", "hybrid": "hybrid", "remote": "fully remote"}


class VerifierSettings(BaseModel):
    """`options.verifier` in config.yaml."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_requests: int = Field(default=5, gt=0)
    time_budget_ms: int = Field(default=60_000, gt=0)
    max_steps: int = Field(default=2, gt=0)
    max_fetches: int = Field(default=6, gt=0)
    max_tokens: int = Field(default=12_000, gt=0)
    cold_start_ms: int = Field(default=15_000, ge=0)
    max_attempts: int = Field(default=4, gt=0, le=10)

    def budget(self) -> dict[str, int]:
        return self.model_dump(include={"max_steps", "max_fetches", "max_tokens"})


# Claims


def _value(opp: dict[str, Any], name: str) -> Any:
    entry = opp["fields"].get(name) or {}
    return entry.get("value", UNKNOWN) if isinstance(entry, dict) else UNKNOWN


def claim_text(name: str, value: Any, company: str, title: str) -> str:
    """The claim for one field, from a fixed sentence per field: never model text."""
    posting = f'{company}\'s "{title}" posting'
    if name == "title":
        return f'{company} has posted a job titled "{value}".'
    if name == "role_type":
        return f"{posting} is for {ROLE_WORDS.get(value, value)}."
    if name == "term":
        return f"{posting} is for {value}."
    if name == "locations":
        places = value if isinstance(value, list) else [value]
        return f"{posting} lists the location {' or '.join(places)}."
    if name == "remote":
        return f"{posting} says the work is {REMOTE_WORDS.get(value, value)}."
    if name == "compensation":
        return f"{posting} lists pay of {value}."
    if name == "deadline":
        return f"{posting} gives an application deadline of {value}."
    return f"{posting} says this about work authorization: {value}."


def claims_for(opp: dict[str, Any]) -> list[dict[str, str]]:
    """One claim per known field. Unknown fields, and the Curator's quotes, are not sent."""
    claims = []
    for name in FIELDS:
        value = _value(opp, name)
        if value in (UNKNOWN, []):
            continue
        claims.append(
            {
                "claim_id": f"{opp['id']}:{name}",
                "text": claim_text(name, value, opp["company"], opp["title"])[:500],
                "source_url": opp["url"],
            }
        )
    return claims


# Client


class VerifierFailed(Exception):
    """No valid answer for a request. `stop_all` when later requests would fail the same way.
    `attempts` is how many copies were sent; 0 means the request never left the tracker."""

    def __init__(
        self, reason: str, detail: str, *, stop_all: bool = False, attempts: int = 1
    ) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail
        self.stop_all = stop_all
        self.attempts = attempts


# Statuses that come back before the verifier does any paid work.
FREE_STATUSES = (400, 401, 409)


@dataclass
class Client:
    url: str
    token: str
    settings: VerifierSettings
    trace: Trace
    transport: httpx.BaseTransport | None = None
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    deadline: float | None = None  # the run's wall-time deadline, on `clock`
    # The worker this client calls. The defaults are the tracker's Verify stage;
    # `python -m tracker.orchestrate` also calls the researcher through this client.
    path: str = "/verify"
    worker: str = SERVICE
    response_model: type = VerifyResponse
    caller: str = "tracker"  # the trace's `service`

    def send(self, request: Any, step: int, budget: Budget) -> Any:
        """POST one request until it gets a valid answer or a terminal failure. Every
        attempt sends the same bytes with the same `request_id`. Each attempt that reached
        the verifier and got no valid answer is charged a full share to `budget`, since its
        copy may have spent; a retry is sent only if another full share still fits."""
        body = request.model_dump(mode="json")
        content = json.dumps(body, separators=(",", ":")).encode()
        # The verifier's logs carry the wire run id; the trace keeps both.
        ids = {
            "request_id": str(request.request_id),
            "wire_run_id": str(request.run_id),
            "step": step,
        }
        with httpx.Client(transport=self.transport, trust_env=False) as http:
            return self._send(http, request, content, ids, budget)

    def _send(
        self,
        http: httpx.Client,
        request: Any,
        content: bytes,
        ids: dict[str, Any],
        budget: Budget,
    ) -> Any:
        s = self.settings
        timeout = (s.time_budget_ms + s.cold_start_ms) / 1000
        pause = 0.0  # the wait before this attempt: backoff or Retry-After
        for attempt in range(1, s.max_attempts + 1):
            if attempt > 1 and not fits(budget, s):
                raise VerifierFailed(
                    "no_budget_share",
                    "another full share would not fit the run's budget",
                    stop_all=True,
                    attempts=attempt - 1,
                )
            if self.deadline is not None and self.clock() + pause + timeout > self.deadline:
                # Stop before the wait: sleeping and then giving up would waste it.
                raise VerifierFailed(
                    "max_wall_seconds",
                    f"waiting {pause:.0f} s plus the {timeout:.0f} s timeout"
                    " would pass the run's deadline",
                    stop_all=True,
                    attempts=attempt - 1,
                )
            if pause:
                self.sleep(pause)
            began = time.monotonic()
            wait: float | None = None
            reached = True  # whether the attempt got to the verifier
            r: httpx.Response | None = None
            try:
                r = http.post(
                    f"{self.url.rstrip('/')}{self.path}",
                    content=content,
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Content-Type": "application/json",
                    },
                    timeout=timeout,
                )
            except httpx.TimeoutException:
                status: Any = "timeout"
            except httpx.ConnectError:
                status, reached = "connection_error", False
            except httpx.HTTPError:
                status = "connection_error"  # dropped after the request went out
            else:
                status = r.status_code
                wait = parse_retry_after(r.headers)
            latency = round((time.monotonic() - began) * 1000)
            if status == 200:
                try:
                    response = self.response_model.model_validate_json(r.content)
                    response.check_against(request)
                except (ValidationError, ValueError) as err:
                    self._event(ids, attempt, "invalid_response", latency, None)
                    charge(budget, s.max_steps, s.max_fetches, s.max_tokens)
                    raise VerifierFailed(
                        "invalid_response", str(err)[:300], attempts=attempt
                    ) from None
                self._event(ids, attempt, status, latency, response.usage.tokens)
                return response
            self._event(ids, attempt, status, latency, None)
            if reached and status not in FREE_STATUSES and _error_code(r) != "in_progress":
                # No valid answer, but the copy may have made its paid model call.
                charge(budget, s.max_steps, s.max_fetches, s.max_tokens)
            if status == 401:
                raise VerifierFailed(
                    "unauthorized",
                    f"the {self.worker} refused the token",
                    stop_all=True,
                    attempts=attempt,
                )
            if isinstance(status, int) and status not in (502, 503, 504):
                raise VerifierFailed(f"http_{status}", _error_message(r), attempts=attempt)
            backoff = min(2**attempt, 30) * (0.8 + 0.4 * random.random())
            pause = max(backoff, wait or 0)
        raise VerifierFailed(
            "no_answer",
            f"no valid answer after {s.max_attempts} attempts",
            attempts=s.max_attempts,
        )

    def _event(
        self, ids: dict[str, Any], attempt: int, status: Any, latency: int, tokens: Any
    ) -> None:
        self.trace.event(
            "service",
            service=self.caller,
            direction="out",
            endpoint_or_tool=f"{self.worker}:{self.path}",
            status=status,
            latency_ms=latency,
            attempt=attempt,
            tokens=tokens,
            **ids,
        )


def _error_code(r: httpx.Response | None) -> str | None:
    """The verifier's error code; `in_progress` means another copy is doing the work."""
    if r is None or r.status_code != 503:
        return None
    try:
        return str(r.json()["error"]["code"])
    except (ValueError, KeyError, TypeError):
        return None


def _error_message(r: httpx.Response) -> str:
    try:
        return str(r.json()["error"]["message"])[:300]
    except (ValueError, KeyError, TypeError):
        return f"HTTP {r.status_code}"


# Stage


@dataclass
class VerifyResult:
    requests: int = 0
    verdicts: int = 0
    skipped_for_budget: int = 0
    failure: VerifierFailed | None = None


def verify_top_k(
    store: OpportunityStore,
    run_id: str,
    top_k: list[dict[str, Any]],
    client: Client,
    settings: VerifierSettings,
    budget: Budget,
) -> VerifyResult:
    """Verify each top-K opportunity whose current record has claims without a verdict."""
    result = VerifyResult()
    for opp in top_k:
        record_hash = store.record_hash(opp)
        stored = store.verdicts(opp["id"], record_hash)
        claims = [
            c
            for c in claims_for(opp)
            if (v := stored.get(c["claim_id"].split(":", 1)[1])) is None
            or v["verdict"] == "unreachable"
        ]
        if not claims:
            continue
        if result.requests >= settings.max_requests or not fits(budget, settings):
            result.skipped_for_budget += 1
            continue
        request = VerifyRequest.model_validate(
            {
                "request_id": str(uuid.uuid4()),
                "run_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"tracker-run:{run_id}")),
                "time_budget_ms": settings.time_budget_ms,
                "budget": settings.budget(),
                "payload": {"claims": claims},
            }
        )
        result.requests += 1
        try:
            response = client.send(request, step=result.requests, budget=budget)
        except VerifierFailed as err:
            if err.attempts == 0:
                result.requests -= 1  # never sent: not counted, not charged
            # The client charged a full share for each attempt that may have spent.
            result.failure = err
            if err.stop_all:
                break
            continue
        usage = response.usage  # the answer, counted once, on top of any failed attempts
        charge(budget, usage.steps, usage.fetches, usage.tokens)
        texts = {c["claim_id"]: c["text"] for c in claims}
        rows = [
            {
                "opportunity_id": opp["id"],
                "field": v.claim_id.split(":", 1)[1],
                "record_hash": record_hash,
                "text": texts[v.claim_id],
                "verdict": v.verdict,
                "evidence": v.evidence,
                "run_id": run_id,
                "request_id": str(request.request_id),
            }
            for v in response.result.verdicts
        ]
        store.put_verdicts(rows)
        result.verdicts += len(rows)
        if response.status != "complete" and result.failure is None:
            code = response.error.code if response.error else "partial"
            result.failure = VerifierFailed(code, response.error.message if response.error else "")
    return result


def fits(budget: Budget, s: VerifierSettings) -> bool:
    """Whether a request's full share still fits the run's budget."""
    limits = budget.policy.limits
    return (
        budget.steps_left() >= s.max_steps
        and budget.tokens_left() >= s.max_tokens
        and limits.max_fetches - budget.fetches >= s.max_fetches
    )


def charge(budget: Budget, steps: int, fetches: int, tokens: int) -> None:
    budget.count(steps=steps, fetches=fetches)
    budget.charge_tokens(tokens, 0)


def claims_view(store: OpportunityStore, opp: dict[str, Any]) -> list[dict[str, Any]]:
    """What the report and the published row show: every claim with its label."""
    stored = store.verdicts(opp["id"], store.record_hash(opp))
    view = []
    for claim in claims_for(opp):
        name = claim["claim_id"].split(":", 1)[1]
        v = stored.get(name)
        view.append(
            {
                "field": name,
                "text": claim["text"],
                "verdict": v["verdict"] if v else "unverified",
                "evidence": v["evidence"] if v else None,
            }
        )
    return view
