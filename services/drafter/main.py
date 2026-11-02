"""The drafter service: `GET /healthz` and `POST /draft`.

The token, body, idempotency and log rules are shared with the verifier
(`agentkit.service.serve`). The drafter has no database: the profile comes in each request,
and no file contents reach a log.
"""

import os

from agentkit.contract import DraftRequest
from agentkit.fetch import fetch_page
from agentkit.service import Store, serve
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

import draft as worker
import plan

TOKEN = os.environ.get("DRAFTER_TOKEN", "")
if not TOKEN:
    raise RuntimeError("DRAFTER_TOKEN is not set; refusing to start")

app = FastAPI(title="drafter", docs_url=None, redoc_url=None, openapi_url=None)
store = Store(max_items=100)  # responses carry a .docx, so keep fewer
_fetch = fetch_page


def _caller() -> plan.Call:
    return plan.anthropic_caller(os.environ.get("ANTHROPIC_API_KEY", ""))


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.post("/draft")
async def draft_endpoint(request: Request) -> JSONResponse:
    return await serve(
        request,
        service="drafter",
        path="/draft",
        token=TOKEN,
        model=DraftRequest,
        store=store,
        work=lambda req, log: worker.draft(req, fetch=_fetch, call=_caller(), log=log),
        empty_result={
            "role_type": None,
            "cv_docx_b64": None,
            "cover_letter_docx_b64": None,
            "cover_letter_text": None,
            "checks": [],
        },
    )
