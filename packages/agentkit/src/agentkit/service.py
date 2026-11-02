"""What every worker service does around its work: the token, the body, idempotency, logs.

Order on every request: the token (constant time, before the body is read), then the
body against the schema, then the request store, then the work. A repeated `request_id`
with the same body gets the stored answer and costs nothing; with another body it gets
409; while the first copy runs it gets 503 with `Retry-After`.
"""

import hmac
import json
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from agentkit.contract import body_hash
from agentkit.wire_log import log_line

RUNNING_RETRY_AFTER = 5


class ProviderBusy(Exception):
    """Retrying later can work: a per-minute limit, an overloaded provider."""

    def __init__(self, retry_after: float) -> None:
        super().__init__(f"provider busy, retry after {retry_after}s")
        self.retry_after = retry_after


class ProviderFailed(Exception):
    """Retrying won't help: a bad key, an exhausted quota or spend cap."""


class Store:
    """request_id -> (body hash, stored response or None while running).

    In process memory only: a new instance starts empty, and a retry that lands there
    does the work again.
    """

    # ponytail: per-instance LRU, a shared store (Redis) if duplicates cross instances

    def __init__(self, max_items: int = 1000) -> None:
        self._lock = threading.Lock()
        self._items: OrderedDict[str, tuple[str, dict | None]] = OrderedDict()
        self._max = max_items

    def claim(self, request_id: str, digest: str) -> tuple[str, dict | None]:
        """`new` (caller does the work), `done` (stored answer), `running` or `conflict`."""
        with self._lock:
            if request_id not in self._items:
                self._items[request_id] = (digest, None)
                while len(self._items) > self._max:
                    self._items.popitem(last=False)
                return "new", None
            stored_digest, response = self._items[request_id]
            if stored_digest != digest:
                return "conflict", None
            return ("done", response) if response is not None else ("running", None)

    def finish(self, request_id: str, response: dict) -> None:
        with self._lock:
            self._items[request_id] = (self._items[request_id][0], response)

    def forget(self, request_id: str) -> None:
        with self._lock:
            self._items.pop(request_id, None)


def _error(code: str, message: str, retryable: bool) -> dict:
    return {"error": {"code": code, "message": message, "retryable": retryable}}


async def serve(
    request: Request,
    *,
    service: str,
    path: str,
    token: str,
    model: type[BaseModel],
    store: Store,
    work: Callable[[Any, Callable[..., Any]], BaseModel],
    empty_result: dict,
) -> JSONResponse:
    """Run `work(req, log)` for an authorized, valid, new request and answer for it."""
    began = time.monotonic()
    ids: dict[str, Any] = {}

    def reply(status: int, body: dict, headers: dict | None = None) -> JSONResponse:
        log_line(
            service=service,
            direction="in",
            endpoint_or_tool=path,
            status=status,
            latency_ms=round((time.monotonic() - began) * 1000),
            **ids,
        )
        return JSONResponse(body, status_code=status, headers=headers)

    auth = request.headers.get("authorization", "")
    if not hmac.compare_digest(auth.encode(), f"Bearer {token}".encode()):
        return reply(401, _error("unauthorized", "missing or wrong token", False))

    try:
        raw = json.loads(await request.body())
        req = model.model_validate(raw)
    except (ValueError, ValidationError) as err:
        fields = (
            [".".join(map(str, e["loc"])) for e in err.errors()]
            if isinstance(err, ValidationError)
            else []
        )
        message = f"invalid fields: {', '.join(fields)}" if fields else "body is not valid JSON"
        return reply(400, _error("invalid_request", message, False))

    ids = {"run_id": str(req.run_id), "request_id": str(req.request_id)}
    state, stored = store.claim(str(req.request_id), body_hash(raw))
    if state == "done":
        return reply(200, stored)
    if state == "conflict":
        return reply(
            409, _error("request_id_reused", "this request_id was sent with another body", False)
        )
    if state == "running":
        return reply(
            503,
            _error("in_progress", "this request_id is still being processed", True),
            {"Retry-After": str(RUNNING_RETRY_AFTER)},
        )

    def out(**fields: Any) -> None:
        log_line(service=service, **ids, **fields)

    try:
        response = await run_in_threadpool(work, req, out)
    except ProviderBusy as err:
        store.forget(str(req.request_id))
        return reply(
            503,
            _error("rate_limited", "the model provider is rate limiting", True),
            {"Retry-After": str(max(1, round(err.retry_after)))},
        )
    except ProviderFailed as err:
        store.forget(str(req.request_id))
        return reply(
            500,
            {
                **ids,
                "status": "failed",
                "result": empty_result,
                "usage": {"steps": 0, "fetches": 0, "tokens": 0},
                **_error("provider_failed", str(err), False),
            },
        )
    except Exception:
        store.forget(str(req.request_id))
        raise
    body = response.model_dump(mode="json")
    store.finish(str(req.request_id), body)
    return reply(200, body)
