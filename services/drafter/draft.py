"""One draft: fetch the posting, ask for a plan, check it, build the CV, fit it on one page,
and, when asked, write and check a cover letter. Within the request's budgets throughout.
"""

import base64
import binascii
import io
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from agentkit.contract import (
    CheckRecord,
    DraftRequest,
    DraftResponse,
    DraftResult,
    Usage,
    WorkerError,
)
from agentkit.cv.layout import LayoutError, Master
from agentkit.cv.profile import ProfileError, parse_checks, parse_fact_bank
from agentkit.fetch import FetchError, Page
from agentkit.guard import Blocked
from agentkit.settings import FetchSettings
from docx import Document
from pydantic import ValidationError

import plan as model
from budget import fit
from checks import ModelLetter, ModelPlan, apply_plan, letter_problems

FETCH = FetchSettings(
    allowed_schemes=("https", "http"),
    allowed_hosts=("*",),
    connect_timeout=5,
    read_timeout=10,
    deadline_seconds=20,
    max_bytes=2_000_000,
    max_redirects=5,
    max_chars_for_model=12000,
)
MIN_CALL_SECONDS = 5.0  # don't start a model call with less time left
MODEL_TIMEOUT = 90.0

Fetcher = Callable[[str, FetchSettings], Page]
Log = Callable[..., Any]


@dataclass
class _Spend:
    steps: int = 0
    fetches: int = 0
    tokens: int = 0


def draft(
    req: DraftRequest,
    *,
    fetch: Fetcher,
    call: model.Call,
    log: Log,
    clock: Callable[[], float] = time.monotonic,
    today: Callable[[], date] = date.today,
) -> DraftResponse:
    deadline = clock() + req.time_budget_ms / 1000
    p = req.payload
    spend = _Spend()
    records: list[CheckRecord] = []
    result: dict[str, Any] = {
        "role_type": None,
        "cv_docx_b64": None,
        "cover_letter_docx_b64": None,
        "cover_letter_text": None,
        "model": None,
    }

    def finish(code: str | None = None, message: str = "") -> DraftResponse:
        return DraftResponse(
            request_id=req.request_id,
            run_id=req.run_id,
            status="partial" if code else "complete",
            result=DraftResult(**result, checks=records),
            usage=Usage(steps=spend.steps, fetches=spend.fetches, tokens=spend.tokens),
            error=WorkerError(code=code, message=message, retryable=False) if code else None,
        )

    try:
        master = Master(base64.b64decode(p.profile.cv_docx_b64, validate=True))
        facts = parse_fact_bank(p.profile.fact_bank_yaml)
        checks = parse_checks(p.profile.checks_yaml, facts)
    except (LayoutError, ProfileError, binascii.Error) as err:
        return finish("invalid_profile", str(err)[:300])

    if spend.fetches >= req.budget.max_fetches or deadline - clock() < MIN_CALL_SECONDS:
        return finish("time_budget_exhausted", "no time or fetches left for the posting")
    cfg = FETCH.model_copy(
        update={
            "max_redirects": min(FETCH.max_redirects, req.budget.max_fetches - 1),
            "deadline_seconds": min(FETCH.deadline_seconds, deadline - clock()),
        }
    )
    page = _fetch(p.posting_url, cfg, fetch, spend, log)
    if page is None:
        return finish("posting_unreachable", "the posting could not be fetched or has no text")
    posting = page.text[: FETCH.max_chars_for_model]
    prefix = model.profile_prefix(p.profile.rules_md, facts, checks, master)

    def ask(instructions: str, user: str, schema: dict, max_tokens: int, what: str) -> tuple[str | None, str]:
        if spend.steps >= req.budget.max_steps:
            return None, "step_budget_exhausted"
        if spend.tokens >= req.budget.max_tokens:
            return None, "token_budget_exhausted"
        left = deadline - clock()
        if left < MIN_CALL_SECONDS:
            return None, "time_budget_exhausted"
        began = time.monotonic()
        try:
            raw, tokens = call(
                instructions,
                prefix,
                user,
                schema,
                min(max_tokens, req.budget.max_tokens - spend.tokens),
                min(MODEL_TIMEOUT, left),
            )
        except Exception as err:
            log(
                direction="out",
                endpoint_or_tool=f"anthropic:{what}",
                status=type(err).__name__,
                attempt=spend.steps + 1,
            )
            raise
        spend.steps += 1
        spend.tokens += tokens
        log(
            direction="out",
            endpoint_or_tool=f"anthropic:{what}",
            status="ok" if raw is not None else "no_output",
            latency_ms=round((time.monotonic() - began) * 1000),
            attempt=spend.steps,
            tokens=tokens,
            step=spend.steps,
        )
        return raw, ""

    raw, code = ask(
        model.PLAN_INSTRUCTIONS,
        model.posting_message(posting, p.company, p.title, "Return the CV plan."),
        model.PLAN_SCHEMA,
        model.PLAN_MAX_TOKENS,
        "plan",
    )
    if raw is None:
        return finish(code or "model_output_invalid", "no CV plan")
    result["model"] = model.MODEL
    try:
        proposed = ModelPlan.model_validate_json(raw)
    except ValidationError:
        return finish("model_output_invalid", "the CV plan did not match the schema")

    cv_plan, role = apply_plan(proposed, master, facts, checks, records.append)
    result["role_type"] = role
    doc = fit(master, cv_plan, checks, role, facts, records.append)
    if doc is None:
        return finish("does_not_fit", "the CV is over one page after the whole cut order")
    buf = io.BytesIO()
    doc.save(buf)
    result["cv_docx_b64"] = base64.b64encode(buf.getvalue()).decode()

    if not p.cover_letter:
        return finish()
    known = "\n".join(
        [posting, p.company, p.title, master.name, master.contact]
        + [f"{f.entry} {f.text}" for f in facts.values() if f.approved and f.id not in checks.never_on_cv]
    )
    task = "Write the cover letter."
    for attempt in (1, 2):
        raw, code = ask(
            model.LETTER_INSTRUCTIONS,
            model.posting_message(posting, p.company, p.title, task),
            model.LETTER_SCHEMA,
            model.LETTER_MAX_TOKENS,
            "letter",
        )
        if raw is None and code:
            records.append(CheckRecord(name="letter_skipped", outcome="note", detail=code))
            return finish(code, "no budget left for the cover letter")
        try:
            paragraphs = [" ".join(x.split()) for x in ModelLetter.model_validate_json(raw or "").paragraphs]
            problems = letter_problems(paragraphs, known, checks)
        except ValidationError:
            paragraphs, problems = [], ["the reply did not match the schema"]
        if not problems:
            docx_bytes, text = letter(master, p.company, p.title, paragraphs, today())
            result["cover_letter_docx_b64"] = base64.b64encode(docx_bytes).decode()
            result["cover_letter_text"] = text
            return finish()
        records.append(
            CheckRecord(
                name="letter_rejected",
                outcome="rejected" if attempt == 2 else "note",
                detail="; ".join(problems)[:500],
            )
        )
        task = (
            "Write the cover letter. Your last draft was rejected because: "
            + "; ".join(problems)
            + ". Fix every one."
        )
    return finish()


def letter(master: Master, company: str, title: str, paragraphs: list[str], day: date) -> tuple[bytes, str]:
    """The letter as a .docx and as plain text: header and sign-off from the applicant's CV,
    in the shape rules.md describes."""
    lines = [
        master.name,
        master.contact,
        "",
        day.strftime("%B %-d, %Y"),
        company,
        "",
        f"Re: {title}",
        "",
        "Dear Hiring Team,",
        "",
    ]
    for para in paragraphs:
        lines += [para, ""]
    lines += ["Best regards,", master.name]
    doc = Document()
    for line in lines:
        doc.add_paragraph(line)
    doc.paragraphs[0].runs[0].bold = True
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue(), "\n".join(lines) + "\n"


def _fetch(url: str, cfg: FetchSettings, fetch: Fetcher, spend: _Spend, log: Log) -> Page | None:
    began = time.monotonic()
    status: Any
    try:
        page = fetch(url, cfg)
    except Blocked as err:
        log(direction="out", endpoint_or_tool="fetch", status=f"blocked:{err.reason}", latency_ms=0)
        return None
    except FetchError as err:
        spend.fetches += 1
        status, page = err.status or err.reason, None
    else:
        spend.fetches += 1 + page.redirects
        status = page.status
    log(
        direction="out",
        endpoint_or_tool="fetch",
        status=status,
        latency_ms=round((time.monotonic() - began) * 1000),
        step=spend.fetches,
    )
    return page if page is not None and page.text.strip() else None
