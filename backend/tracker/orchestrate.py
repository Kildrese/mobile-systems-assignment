"""One orchestrated run in plain code: the researcher and the verifier as remote workers.

    uv run python -m tracker.orchestrate [--config PATH]

Started only by hand, locally (no route, cron or workflow starts it): it spends Groq
through the verifier. It sends one POST /research, then one POST /verify per development,
through the Verify stage's client (same retries, deadline and charging), checks every
answer against the contract, and writes a report, a trace and the run's history to the
local database. Worker text is data: it never changes the topic, k, the budgets, or which
worker is called. The daily tracker does not use this module.
"""

import argparse
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from agentkit.contract import ResearchRequest, ResearchResponse, VerifyRequest

from tracker import config
from tracker.budget import Budget
from tracker.config import Policy, TrackerSecrets, load_policy
from tracker.errors import PolicyError
from tracker.trace import Trace
from tracker.usecases.internships import verifying, wiring
from tracker.usecases.internships.verifying import VerifierFailed, VerifierSettings

WORKERS = ("researcher", "verifier")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


@dataclass
class Outcome:
    run: dict[str, Any]  # what `app.publish_report.publish` takes as `run`
    offers: list[dict[str, Any]]  # `internship_offers` rows; empty when the researcher was down
    markdown: str
    exit_code: int


def _one(value: Any) -> str:
    """Worker text on one line."""
    return " ".join(str(value).split())


def settings(policy: Policy) -> tuple[VerifierSettings, VerifierSettings]:
    """`options.researcher` and `options.verifier`, checked against `limits`. Raises
    `PolicyError` when one is missing or the shares don't fit."""
    opts = wiring.options(policy)
    if opts.researcher is None or opts.verifier is None:
        missing = [n for n in WORKERS if getattr(opts, n) is None]
        raise PolicyError(
            "Invalid policy: " + ", ".join(f"options.{n}" for n in missing) + " is required"
        )
    r, v = opts.researcher, opts.verifier
    limits = policy.limits
    over = []
    for name, cap in (
        ("max_steps", limits.max_steps),
        ("max_fetches", limits.max_fetches),
        # What `verifying.fits` really allows: the reserve is never handed out.
        ("max_tokens", limits.max_tokens - limits.reserve_tokens),
    ):
        total = getattr(r, name) + v.max_requests * getattr(v, name)
        if total > cap:
            over.append(
                f"limits.{name}: researcher and verifier add up to {total:,}, more than {cap:,}"
            )
    if over:
        raise PolicyError("Invalid policy:\n  " + "\n  ".join(over))
    return r, v


def orchestrate(
    policy: Policy,
    secrets: TrackerSecrets,
    last_top_k: dict[str, Any] | None,
    *,
    transport: httpx.BaseTransport | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> Outcome:
    """Run once. No database access: `last_top_k` is read by the caller."""
    rs, vs = settings(policy)
    run_id = str(uuid.uuid4())
    started = datetime.now(UTC)
    budget = Budget(policy, clock)
    trace = Trace(policy.traces_path / f"orchestrate-{run_id}.jsonl", run_id, secrets.values())
    common = {
        "trace": trace,
        "transport": transport,
        "sleep": sleep,
        "clock": clock,
        "deadline": budget.deadline,
        "caller": "orchestrator",
    }
    researcher = verifying.Client(
        secrets.researcher_url or "",
        secrets.researcher_token or "",
        rs,
        path="/research",
        worker="researcher",
        response_model=ResearchResponse,
        **common,
    )
    verifier = verifying.Client(
        secrets.verifier_url or "", secrets.verifier_token or "", vs, **common
    )
    failed: dict[str, str] = {}  # worker -> "reason: detail", first failure only
    try:
        developments = []
        request = ResearchRequest.model_validate(
            {
                "request_id": str(uuid.uuid4()),
                "run_id": run_id,
                "time_budget_ms": rs.time_budget_ms,
                "budget": rs.budget(),
                "payload": {"topic": policy.topic, "k": policy.k},
            }
        )
        try:
            answer = researcher.send(request, step=1, budget=budget)
        except VerifierFailed as err:
            failed["researcher"] = f"{err.reason}: {err.detail}"
        else:
            verifying.charge(budget, answer.usage.steps, answer.usage.fetches, answer.usage.tokens)
            developments = answer.result.developments
            if answer.status != "complete":
                failed["researcher"] = _worker_error(answer)
        down = "researcher" in failed and not developments

        verdicts: dict[str, Any] = {}  # claim_id -> VerdictItem
        requests = 0
        left_unverified = False
        for development in developments:
            if requests >= vs.max_requests or not verifying.fits(budget, vs):
                left_unverified = True
                break
            request = VerifyRequest.model_validate(
                {
                    "request_id": str(uuid.uuid4()),
                    "run_id": run_id,
                    "time_budget_ms": vs.time_budget_ms,
                    "budget": vs.budget(),
                    "payload": {"claims": [c.model_dump() for c in development.claims]},
                }
            )
            requests += 1
            try:
                answer = verifier.send(request, step=1 + requests, budget=budget)
            except VerifierFailed as err:
                failed.setdefault("verifier", f"{err.reason}: {err.detail}")
                if err.stop_all:
                    break  # the rest stay unverified; `verifier` is already named
                continue
            verifying.charge(budget, answer.usage.steps, answer.usage.fetches, answer.usage.tokens)
            verdicts.update((v.claim_id, v) for v in answer.result.verdicts)
            if answer.status != "complete":
                failed.setdefault("verifier", _worker_error(answer))
    finally:
        trace.close()

    names = [w for w in WORKERS if w in failed]
    if names:
        stop_reason: str | None = f"service:{names[0]}"
    elif left_unverified:
        stop_reason = "verifier.max_requests"
    else:
        stop_reason = None
    status = "partial" if stop_reason else "complete"
    run = {
        "id": run_id,
        "topic": policy.topic,
        "status": status,
        "stop_reason": stop_reason,
        "started_at": started.isoformat(),
        "ended_at": datetime.now(UTC).isoformat(),
        "failed_services": names,
    }
    offers = [] if down else _offers(developments, verdicts, started)
    urls = [[c.source_url for c in d.claims] for d in developments]
    markdown = _report(run, failed, budget, offers, urls, down, last_top_k)
    return Outcome(run, offers, markdown, 0 if status == "complete" else 2)


def _worker_error(answer: Any) -> str:
    if answer.error is None:
        return f"{answer.status}: no error given"
    return f"{answer.error.code}: {answer.error.message}"


def _offers(
    developments: list[Any], verdicts: dict[str, Any], started: datetime
) -> list[dict[str, Any]]:
    rows = []
    for rank, d in enumerate(developments, 1):
        claims = []
        for c in d.claims:
            v = verdicts.get(c.claim_id)
            claims.append(
                {
                    "field": c.claim_id.split(":", 1)[-1],
                    "text": _one(c.text),
                    "verdict": v.verdict if v else "unverified",
                    "evidence": _one(v.evidence) if v and v.evidence else None,
                }
            )
        rows.append(
            {
                "opportunity_id": rank,
                "section": "top_k",
                "rank": rank,
                "top_k": True,
                "company": "",
                "title": _one(d.title),
                "url": d.claims[0].source_url,
                "summary": _one(d.summary),
                "role_type": "unknown",
                "term": "unknown",
                "remote": "unknown",
                "status": "unknown",
                "locations": [],
                "verified": False,
                "first_seen_at": started,
                "claims": claims,
            }
        )
    return rows


def _claim_lines(claims: list[dict[str, Any]], urls: list[str | None]) -> list[str]:
    lines = []
    for c, source in zip(claims, urls, strict=True):
        lines.append(
            f"- **{c['verdict']}:** {_one(c['text'])}" + (f" ({_one(source)})" if source else "")
        )
        if c["verdict"] == "supported" and c.get("evidence"):
            lines.append(f"  > {_one(c['evidence'])}")
    return lines


def _report(
    run: dict[str, Any],
    failed: dict[str, str],
    budget: Budget,
    offers: list[dict[str, Any]],
    urls: list[list[str]],
    down: bool,
    last_top_k: dict[str, Any] | None,
) -> str:
    u = budget.usage()
    workers = ", ".join(f"{w} ({_one(failed[w])})" for w in run["failed_services"]) or "none"
    lines = [
        f"# Orchestrated run: {run['topic']}",
        "",
        f"- Run: {run['id']}",
        f"- Time: {run['started_at']} to {run['ended_at']}",
        f"- Status: {run['status']}" + (f" ({run['stop_reason']})" if run["stop_reason"] else ""),
        f"- Failed workers: {workers}",
        f"- Budget used: {u['steps']} steps, {u['fetches']} fetches, "
        f"{u['total_tokens']} tokens, {u['wall_seconds']} s",
        "",
    ]
    if not down:
        lines += ["## Top K", ""]
        for o, sources in zip(offers, urls, strict=True):
            lines += [f"### {o['rank']}. {o['title']}", ""]
            if o["summary"]:
                lines += [o["summary"], ""]
            lines += [*_claim_lines(o["claims"], sources), ""]
        return "\n".join(lines)
    lines += ["## No new results", "", "The researcher gave no developments in this run.", ""]
    if last_top_k is None:
        return "\n".join([*lines, "No earlier run to show.", ""])
    lines += [
        f"## Last run's top K (stale, run {last_top_k['run_id']}, {last_top_k['started_at']})",
        "",
    ]
    for o in last_top_k["offers"]:
        lines += [f"### {o['rank']}. {_one(o['title'])} (stale)", ""]
        lines += [*_claim_lines(o["claims"], [o.get("url")] * len(o["claims"])), ""]
    return "\n".join(lines)


def find_last_top_k(db: Any) -> dict[str, Any] | None:
    """The newest run in the database with top-K offers, and those offers by rank."""
    from sqlalchemy import select

    from app.models import InternshipOffer, TrackerRun

    run = db.scalar(
        select(TrackerRun)
        .where(
            select(InternshipOffer.id)
            .where(InternshipOffer.run_id == TrackerRun.id, InternshipOffer.top_k)
            .exists()
        )
        .order_by(TrackerRun.started_at.desc())
        .limit(1)
    )
    if run is None:
        return None
    offers = db.scalars(
        select(InternshipOffer)
        .where(InternshipOffer.run_id == run.id, InternshipOffer.top_k)
        .order_by(InternshipOffer.rank)
    )
    return {
        "run_id": run.id,
        "started_at": run.started_at.isoformat(),
        "offers": [
            {"rank": o.rank, "title": o.title, "url": o.url, "claims": o.claims} for o in offers
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tracker.orchestrate")
    parser.add_argument("--config", help="the policy file (default: config.yaml at the root)")
    args = parser.parse_args(argv)
    try:
        policy = load_policy(args.config)
        settings(policy)
        secrets = TrackerSecrets.load(policy, model=False, search=False, env_file=config.ENV_FILE)
    except PolicyError as err:
        print(err, file=sys.stderr)
        return 1
    missing = [
        name
        for name, value in (
            ("RESEARCHER_URL", secrets.researcher_url),
            ("RESEARCHER_TOKEN", secrets.researcher_token),
            ("VERIFIER_URL", secrets.verifier_url),
            ("VERIFIER_TOKEN", secrets.verifier_token),
        )
        if not value
    ]
    if missing:
        print(f"{', '.join(missing)} is not set", file=sys.stderr)
        return 1

    from sqlalchemy.engine import make_url

    from app.config import get_settings
    from app.db import get_sessionmaker, sqlalchemy_url
    from app.publish_report import publish

    if make_url(sqlalchemy_url(get_settings().database_url)).host not in LOCAL_HOSTS:
        print("refusing to write to a non-local database", file=sys.stderr)
        return 1
    with get_sessionmaker()() as db:
        outcome = orchestrate(policy, secrets, find_last_top_k(db))
        report = policy.reports_path / f"orchestrate-{outcome.run['id']}.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(outcome.markdown, encoding="utf-8")
        publish(db, outcome.run, outcome.offers, outcome.markdown)
    trace = policy.traces_path / f"orchestrate-{outcome.run['id']}.jsonl"
    print(f"Run {outcome.run['id']}: {outcome.run['status']}")
    print(f"Report: {report}")
    print(f"Trace: {trace}")
    return outcome.exit_code


if __name__ == "__main__":
    sys.exit(main())
