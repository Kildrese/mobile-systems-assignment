"""The single-agent tracker run: one `AgentLoop` with the core tools, then a report.

Every outcome ends in a report: complete when the model calls `finish`, partial when a
budget runs out or a provider fails for good.
"""

import json
import re
import secrets
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from tracker import report
from tracker.agents import AgentLoop, Stop
from tracker.budget import Budget
from tracker.config import AgentProfile, Policy, TrackerSecrets
from tracker.errors import TerminalError, WallClockExceeded
from tracker.guard import Resolver
from tracker.llm import ChatClient, ModelOutputError
from tracker.search import SearchClient
from tracker.state import StateStore
from tracker.tools import Toolbox, validate_finish
from tracker.trace import Trace
from tracker.untrusted import DATA_RULES, wrap

NUDGE = (
    "You did not call a tool. Call search_web or fetch_article to gather evidence, "
    "or call finish with your ranked report."
)

EXIT_CODES = {"complete": 0, "partial": 2, "failed": 3}


def new_run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(2)


def task_prompt(policy: Policy) -> str:
    limits = policy.limits
    return (
        f"Find the top {policy.k} most important recent developments on: {policy.topic}\n\n"
        "Use search_web to find candidates and fetch_article to read the most promising "
        f"sources. Rank them, then call finish with at most {policy.k} items, each with a "
        "title, a 2-4 sentence summary and the source URLs you used. You have at most "
        f"{limits.max_steps} steps, {limits.max_searches} searches and {limits.max_fetches} "
        "fetches."
    )


@dataclass
class RunResult:
    run_id: str
    status: str  # complete | partial | failed
    stop_reason: str | None
    report_path: Path
    trace_path: Path
    message: str
    items: list[dict[str, Any]] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return EXIT_CODES[self.status]


class Runner:
    def __init__(
        self,
        policy: Policy,
        keys: TrackerSecrets,
        *,
        run_id: str | None = None,
        out: Path | str | None = None,
        chat_transport: httpx.BaseTransport | None = None,
        search_transport: httpx.BaseTransport | None = None,
        fetch_transport: httpx.BaseTransport | None = None,
        resolver: Resolver = socket.getaddrinfo,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.policy = policy
        self.keys = keys
        self.run_id = run_id or new_run_id()
        self.report_path = Path(out) if out else policy.reports_path / f"{self.run_id}.md"
        self.trace_path = policy.traces_path / f"{self.run_id}.jsonl"
        self._chat_transport = chat_transport
        self._search_transport = search_transport
        self._fetch_transport = fetch_transport
        self._resolver = resolver
        self._sleep = sleep
        self._clock = clock

    def run(self) -> RunResult:
        """Run once. Raises `StateLocked` when another run holds the state file."""
        policy = self.policy
        state = StateStore(policy.state_file)
        trace = Trace(self.trace_path, self.run_id, self.keys.values())
        budget = Budget(policy, self._clock)
        try:
            state.start_run(self.run_id, policy.topic, policy.k)
            chat = ChatClient(
                policy,
                self.keys.model_key,
                trace,
                client=httpx.Client(
                    transport=self._chat_transport, timeout=policy.model.timeout_seconds
                ),
                sleep=self._sleep,
                deadline=budget.deadline,
            )
            search = SearchClient(
                policy,
                self.keys.search_key,
                trace,
                client=httpx.Client(
                    transport=self._search_transport, timeout=policy.search.timeout_seconds
                ),
                sleep=self._sleep,
                deadline=budget.deadline,
            )
            toolbox = Toolbox(
                policy,
                trace,
                self.run_id,
                state=state,
                search_client=search,
                resolver=self._resolver,
                transport=self._fetch_transport,
            )
            stop = AgentLoop(
                policy,
                AgentProfile.from_policy(policy),
                toolbox,
                budget,
                trace,
                chat,
                task_prompt(policy),
                nudge=NUDGE,
            ).run()
            result = self._finish_run(stop, chat, toolbox, budget, trace, state)
        except KeyboardInterrupt:
            state.end_run(self.run_id, "failed", "interrupted", budget.usage())
            trace.event("summary", outcome="failed", stop_reason="interrupted", **budget.usage())
            raise
        finally:
            state.close()
            trace.close()
        return result

    # Ending the run

    def _finish_run(
        self,
        stop: Stop,
        chat: ChatClient,
        toolbox: Toolbox,
        budget: Budget,
        trace: Trace,
        state: StateStore,
    ) -> RunResult:
        policy = self.policy
        if stop.finish is not None:
            status, reason, detail = "complete", None, None
            body = report.ReportBody(stop.finish.items, stop.finish.note)
        else:
            terminal = stop.terminal
            reason = f"terminal:{terminal.kind}" if terminal else stop.reason
            detail = terminal.message if terminal else None
            status = "failed" if terminal else "partial"
            body = None
            # After a model-provider failure no further model call is made.
            if (terminal is None or terminal.provider != chat.provider.name) and (
                budget.can_synthesize()
            ):
                body = self._synthesize(chat, toolbox, budget, trace, reason, detail)
            if body is None:
                body = _fallback_body(toolbox)

        meta = report.ReportMeta(
            topic=policy.topic,
            run_id=self.run_id,
            timestamp=datetime.now(UTC).isoformat(timespec="seconds"),
            status="complete" if status == "complete" else "partial",
            stop_reason=reason,
            stop_detail=detail,
            usage=budget.usage(),
        )
        report.write(self.report_path, report.render(meta, body))
        if body.items:
            state.put_items(self.run_id, body.items)
        state.end_run(self.run_id, status, reason, budget.usage())
        trace.event(
            "summary",
            outcome=status,
            stop_reason=reason,
            report=str(self.report_path),
            items=len(body.items),
            **budget.usage(),
        )

        if status == "complete":
            message = f"Run {self.run_id} complete: {len(body.items)} items."
        elif stop.terminal is not None:
            t = stop.terminal
            message = f"Terminal failure ({t.kind}) from {t.provider}: {t.message}"
        else:
            message = f"Run {self.run_id} partial: stopped because {report.describe_stop(reason)}."
        return RunResult(
            self.run_id, status, reason, self.report_path, self.trace_path, message, body.items
        )

    def _synthesize(
        self,
        chat: ChatClient,
        toolbox: Toolbox,
        budget: Budget,
        trace: Trace,
        reason: str | None,
        detail: str | None,
    ) -> report.ReportBody | None:
        """One final no-tools model call that turns the evidence into a partial report."""
        policy = self.policy
        evidence = _evidence(toolbox)
        if not evidence:
            return None
        spare_tokens = budget.remaining_tokens() - policy.model.max_output_tokens - 800
        max_chars = min(24_000, spare_tokens * 3)
        if max_chars < 1_000:
            return None
        per_item = max_chars // len(evidence)
        blocks = "\n\n".join(
            wrap(source, text[:per_item], **attrs) for source, text, attrs in evidence
        )
        prompt = (
            f"The run stopped early because {report.describe_stop(reason, detail)}. "
            "No tools are available now. Using only the evidence below, reply with one JSON "
            'object and nothing else: {"items": [{"title": "...", "summary": "...", '
            f'"sources": ["url"]}}], "note": "..."}}. At most {policy.k} items, most '
            "important first, and cite only URLs that appear in the evidence.\n\n" + blocks
        )
        messages = [
            {"role": "system", "content": f"{policy.system_prompt()}\n\n{DATA_RULES}"},
            {"role": "user", "content": prompt},
        ]
        try:
            reply = chat.chat(messages, None, budget.steps + 1, purpose="synthesis")
            budget.charge_tokens(reply.usage.prompt_tokens, reply.usage.completion_tokens)
            result = validate_finish(_json_object(reply.content or ""), policy.k, toolbox.seen)
        except (TerminalError, WallClockExceeded, ModelOutputError, ValueError) as err:
            # ValidationError is a ValueError.
            trace.event(
                "synthesis", status="error", reason=type(err).__name__, detail=str(err)[:500]
            )
            return None
        trace.event("synthesis", status="ok", kept=len(result.items), dropped=result.dropped)
        if not result.items:
            return None
        return report.ReportBody(result.items, result.note)


def _evidence(toolbox: Toolbox) -> list[tuple[str, str, dict[str, str]]]:
    if toolbox.articles:
        return [
            ("fetch_article", f"Title: {a.title}\nURL: {a.url}\n\n{a.text}", {"url": a.url})
            for a in toolbox.articles
        ]
    return [
        ("search_web", f"Title: {r.title}\nURL: {r.url}\n\n{r.snippet}", {"url": r.url})
        for r in toolbox.search_results
    ]


def _fallback_body(toolbox: Toolbox) -> report.ReportBody:
    """A report built by code alone: the sources gathered, with titles and URLs."""
    if toolbox.articles:
        sources = [report.Source(a.title, a.url) for a in toolbox.articles]
    else:
        sources = list(
            {r.url: report.Source(r.title, r.url) for r in toolbox.search_results}.values()
        )
    return report.ReportBody(sources=sources)


def _json_object(text: str) -> Any:
    """The JSON object in a model reply, tolerating code fences and surrounding prose."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError("reply contains no JSON object")
    return json.loads(text[start : end + 1])
