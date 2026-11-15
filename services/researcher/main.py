"""The stub researcher service: `GET /healthz` and `POST /research`.

It serves the developments in `developments.json` (no database, no model, no fetches).
The token, body, idempotency and log rules are shared with the verifier
(`agentkit.service.serve`); this file only says what the work is.
"""

import json
import os
import time
from pathlib import Path

from agentkit.contract import Development, ResearchRequest, ResearchResponse
from agentkit.service import Store, serve
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter

TOKEN = os.environ.get("RESEARCHER_TOKEN", "")
if not TOKEN:
    raise RuntimeError("RESEARCHER_TOKEN is not set; refusing to start")

DELAY_MS = 100  # stands in for research work; tests patch it
DEVELOPMENTS = TypeAdapter(list[Development]).validate_python(
    json.loads((Path(__file__).parent / "developments.json").read_text(encoding="utf-8"))
)
if not DEVELOPMENTS:
    raise RuntimeError("developments.json is empty; refusing to start")

_sleep = time.sleep
_clock = time.monotonic

app = FastAPI(title="researcher", docs_url=None, redoc_url=None, openapi_url=None)
store = Store()


def research(req: ResearchRequest, log) -> ResearchResponse:
    start = _clock()
    n = min(req.payload.k, len(DEVELOPMENTS))
    taken: list[Development] = []
    error = None
    status = "complete"
    for i in range(n):
        if (_clock() - start) * 1000 + DELAY_MS > req.time_budget_ms:
            status = "partial"
            error = {
                "code": "time_budget_exhausted",
                "message": f"stopped after {i} of {n} developments",
                "retryable": False,
            }
            break
        _sleep(DELAY_MS / 1000)
        taken.append(DEVELOPMENTS[i])
    return ResearchResponse.model_validate(
        {
            "request_id": req.request_id,
            "run_id": req.run_id,
            "status": status,
            "result": {"developments": taken},
            "usage": {"steps": 0, "fetches": 0, "tokens": 0},
            "error": error,
        }
    )


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.post("/research")
async def research_endpoint(request: Request) -> JSONResponse:
    return await serve(
        request,
        service="researcher",
        path="/research",
        token=TOKEN,
        model=ResearchRequest,
        store=store,
        work=lambda req, log: research(req, log),
        empty_result={"developments": []},
    )
