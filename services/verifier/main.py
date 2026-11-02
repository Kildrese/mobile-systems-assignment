"""The verifier service: `GET /healthz` and `POST /verify`.

Order on every request: the token, then the body, then the idempotency store, then the
work. A repeated `request_id` with the same body gets the stored answer and costs
nothing; with another body it gets 409; while the first copy runs it gets 503.
"""

import hmac
import json
import os
import threading
import time
from collections import OrderedDict
from typing import Any

from agentkit.contract import VerifyRequest, body_hash
from agentkit.fetch import fetch_page
from agentkit.wire_log import log_line
from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import ValidationError

import verify as worker

TOKEN = os.environ.get("VERIFIER_TOKEN", "")
if not TOKEN:
    raise RuntimeError("VERIFIER_TOKEN is not set; refusing to start")
MODEL = os.environ.get("VERIFIER_MODEL", "openai/gpt-oss-20b")
RUNNING_RETRY_AFTER = 5
MAX_STORED = 1000

app = FastAPI(title="verifier", docs_url=None, redoc_url=None, openapi_url=None)


class Store:
    """request_id -> (body hash, stored response or None while running).

    In process memory only: a new instance starts empty, and a retry that lands there
    does the work again.
    """

    # ponytail: per-instance LRU of 1,000, a shared store (Redis) if duplicates cross instances

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: OrderedDict[str, tuple[str, dict | None]] = OrderedDict()

    def claim(self, request_id: str, digest: str) -> tuple[str, dict | None]:
        """`new` (caller does the work), `done` (stored answer), `running` or `conflict`."""
        with self._lock:
            if request_id not in self._items:
                self._items[request_id] = (digest, None)
                while len(self._items) > MAX_STORED:
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


store = Store()


_fetch = fetch_page


def _asker():
    return worker.groq_asker(os.environ.get("GROQ_API_KEY", ""), MODEL)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.post("/verify")
async def verify_endpoint(request: Request) -> JSONResponse:
    began = time.monotonic()
    ids: dict[str, Any] = {}

    def reply(status: int, body: dict, headers: dict | None = None) -> JSONResponse:
        log_line(
            service="verifier",
            direction="in",
            endpoint_or_tool="/verify",
            status=status,
            latency_ms=round((time.monotonic() - began) * 1000),
            **ids,
        )
        return JSONResponse(body, status_code=status, headers=headers)

    auth = request.headers.get("authorization", "")
    if not hmac.compare_digest(auth.encode(), f"Bearer {TOKEN}".encode()):
        return reply(
            401,
            {
                "error": {
                    "code": "unauthorized",
                    "message": "missing or wrong token",
                    "retryable": False,
                }
            },
        )

    try:
        raw = json.loads(await request.body())
        req = VerifyRequest.model_validate(raw)
    except (ValueError, ValidationError) as err:
        fields = (
            [".".join(map(str, e["loc"])) for e in err.errors()]
            if isinstance(err, ValidationError)
            else []
        )
        message = f"invalid fields: {', '.join(fields)}" if fields else "body is not valid JSON"
        return reply(
            400, {"error": {"code": "invalid_request", "message": message, "retryable": False}}
        )

    ids = {"run_id": str(req.run_id), "request_id": str(req.request_id)}
    state, stored = store.claim(str(req.request_id), body_hash(raw))
    if state == "done":
        return reply(200, stored)
    if state == "conflict":
        return reply(
            409,
            {
                "error": {
                    "code": "request_id_reused",
                    "message": "this request_id was sent with another body",
                    "retryable": False,
                }
            },
        )
    if state == "running":
        return reply(
            503,
            {
                "error": {
                    "code": "in_progress",
                    "message": "this request_id is still being processed",
                    "retryable": True,
                }
            },
            {"Retry-After": str(RUNNING_RETRY_AFTER)},
        )

    def out(**fields: Any) -> None:
        log_line(service="verifier", **ids, **fields)

    try:
        response = await run_in_threadpool(
            worker.verify, req, fetch=_fetch, ask_model=_asker(), log=out
        )
    except worker.ProviderBusy as err:
        store.forget(str(req.request_id))
        retry = max(1, round(err.retry_after))
        return reply(
            503,
            {
                "error": {
                    "code": "rate_limited",
                    "message": "the model provider is rate limiting",
                    "retryable": True,
                }
            },
            {"Retry-After": str(retry)},
        )
    except worker.ProviderFailed as err:
        store.forget(str(req.request_id))
        return reply(
            500,
            {
                **ids,
                "status": "failed",
                "result": {"verdicts": []},
                "usage": {"steps": 0, "fetches": 0, "tokens": 0},
                "error": {"code": "provider_failed", "message": str(err), "retryable": False},
            },
        )
    except Exception:
        store.forget(str(req.request_id))
        raise
    body = response.model_dump(mode="json")
    store.finish(str(req.request_id), body)
    return reply(200, body)
