"""The verifier service: `GET /healthz` and `POST /verify`.

The token, body, idempotency and log rules are shared with the drafter
(`agentkit.service.serve`); this file only says what the work is.
"""

import os

from agentkit.contract import VerifyRequest
from agentkit.fetch import fetch_page
from agentkit.service import Store, serve
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

import verify as worker

TOKEN = os.environ.get("VERIFIER_TOKEN", "")
if not TOKEN:
    raise RuntimeError("VERIFIER_TOKEN is not set; refusing to start")
MODEL = os.environ.get("VERIFIER_MODEL", "openai/gpt-oss-20b")

app = FastAPI(title="verifier", docs_url=None, redoc_url=None, openapi_url=None)
store = Store()
_fetch = fetch_page


def _asker():
    return worker.groq_asker(os.environ.get("GROQ_API_KEY", ""), MODEL)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.post("/verify")
async def verify_endpoint(request: Request) -> JSONResponse:
    return await serve(
        request,
        service="verifier",
        path="/verify",
        token=TOKEN,
        model=VerifyRequest,
        store=store,
        work=lambda req, log: worker.verify(req, fetch=_fetch, ask_model=_asker(), log=log),
        empty_result={"verdicts": []},
    )
