"""Runs a use case's stages in code order, each with only what it needs.

The conductor opens the state store, the trace and the global budget once. Each stage
gets the policy, its own profile, the state store, a trace bound to the stage and agent,
and its budget: an agent's share of the run for agent stages, the run's for code stages.
Stages hand data on only through the state store, never through a conversation.
"""

import socket
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

import httpx

from tracker import report
from tracker.agents import AgentLoop, DoneCheck, FinishHandler, Stop
from tracker.budget import Budget
from tracker.config import AgentProfile, ModelSettings, Policy, TrackerSecrets
from tracker.errors import PolicyError, TerminalError
from tracker.guard import Resolver
from tracker.llm import ChatClient
from tracker.loop import RunResult, new_run_id
from tracker.search import SearchClient
from tracker.state import StateStore
from tracker.tools import Toolbox
from tracker.trace import Trace

Outcome = Literal["complete", "partial", "skipped", "failed"]


@dataclass
class StageOutcome:
    outcome: Outcome
    reason: str | None = None
    detail: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    # Set when a provider failed for good: later stages needing it are skipped.
    terminal: TerminalError | None = None
    # Filled in by the conductor.
    stage: str = ""
    agent: str | None = None

    @classmethod
    def from_stop(cls, stop: Stop) -> "StageOutcome":
        """An agent stage's outcome from how its loop ended."""
        if stop.finish is not None:
            return cls("complete")
        if (t := stop.terminal) is not None:
            return cls("partial", f"terminal:{t.kind}", t.message, terminal=t)
        return cls("partial", stop.reason)

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.stage,
            "agent": self.agent,
            "outcome": self.outcome,
            "reason": self.reason,
            "usage": self.usage,
        }


class Clients:
    """Provider clients for the run: one HTTP connection pool per provider, shared."""

    def __init__(
        self,
        policy: Policy,
        keys: TrackerSecrets,
        deadline: float,
        *,
        chat_transport: httpx.BaseTransport | None = None,
        search_transport: httpx.BaseTransport | None = None,
        fetch_transport: httpx.BaseTransport | None = None,
        resolver: Resolver = socket.getaddrinfo,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.policy = policy
        self.keys = keys
        self.deadline = deadline
        self.chat_transport = chat_transport
        self.search_transport = search_transport
        self.fetch_transport = fetch_transport
        self.resolver = resolver
        self.sleep = sleep
        self._http: dict[str, httpx.Client] = {}

    def _pool(self, name: str, transport: httpx.BaseTransport | None, timeout: float):
        # ponytail: the first caller's timeout wins for a provider shared by several models.
        if name not in self._http:
            self._http[name] = httpx.Client(transport=transport, timeout=timeout)
        return self._http[name]

    def chat(self, model: ModelSettings, trace: Trace) -> ChatClient:
        return ChatClient(
            self.policy,
            self.keys.key_for(model.provider),
            trace,
            client=self._pool(
                f"model:{model.provider}", self.chat_transport, model.timeout_seconds
            ),
            sleep=self.sleep,
            deadline=self.deadline,
            model=model,
        )

    def search(self, trace: Trace) -> SearchClient:
        search = self.policy.search
        return SearchClient(
            self.policy,
            self.keys.search_key,
            trace,
            client=self._pool("search", self.search_transport, search.timeout_seconds),
            sleep=self.sleep,
            deadline=self.deadline,
        )

    def close(self) -> None:
        for client in self._http.values():
            client.close()


@dataclass
class StageContext:
    policy: Policy
    profile: AgentProfile | None
    state: StateStore
    trace: Trace
    budget: Budget
    clients: Clients
    run_id: str

    def toolbox(self) -> Toolbox:
        tools = self.profile.tools if self.profile else ()
        return Toolbox(
            self.policy,
            self.trace,
            self.run_id,
            state=self.state,
            search_client=self.clients.search(self.trace) if "search_web" in tools else None,
            resolver=self.clients.resolver,
            transport=self.clients.fetch_transport,
            fetch_hosts=self.profile.fetch_hosts if self.profile else None,
        )

    def run_agent(
        self,
        task_prompt: str,
        *,
        finish: FinishHandler | None = None,
        finish_schema: dict[str, Any] | None = None,
        done: DoneCheck | None = None,
    ) -> tuple[Stop, Toolbox]:
        """Run this stage's agent once, from a fresh conversation."""
        assert self.profile is not None, "run_agent needs an agent stage"
        toolbox = self.toolbox()
        stop = AgentLoop(
            self.policy,
            self.profile,
            toolbox,
            self.budget,
            self.trace,
            self.clients.chat(self.profile.model, self.trace),
            task_prompt,
            finish=finish,
            finish_schema=finish_schema,
            done=done,
        ).run()
        return stop, toolbox


class Stage(Protocol):
    name: str
    kind: Literal["agent", "code"]
    agent: str | None  # profile name for agent stages
    required: bool
    providers: set[str]  # extra providers the stage needs; an agent's own is implied

    def run(self, ctx: StageContext) -> StageOutcome: ...


# (run context, stage outcomes, report metadata) -> report Markdown.
ReportWriter = Callable[[StageContext, list[StageOutcome], report.ReportMeta], str]


def stage_report(ctx: StageContext, outcomes: list[StageOutcome], meta: report.ReportMeta) -> str:
    """The default report: the run's status and each stage's outcome."""
    status = meta.status
    if meta.stop_reason:
        status += f" ({report.describe_stop(meta.stop_reason, meta.stop_detail)})"
    lines = [
        f"# Tracker report: {' '.join(meta.topic.split())}",
        "",
        f"- **Run:** `{meta.run_id}`",
        f"- **Time:** {meta.timestamp}",
        f"- **Status:** {status}",
        "",
        "## Stages",
        "",
        "| Stage | Agent | Outcome | Reason |",
        "| --- | --- | --- | --- |",
    ]
    for o in outcomes:
        reason = report.describe_stop(o.reason, o.detail) if o.reason else ""
        lines.append(f"| {o.stage} | {o.agent or ''} | {o.outcome} | {reason.replace('|', '/')} |")
    return "\n".join(lines) + "\n"


def run_status(
    stages: Sequence[Stage], outcomes: list[StageOutcome]
) -> tuple[str, StageOutcome | None]:
    """The run's status and the stage outcome that decided it."""
    required = {s.name for s in stages if s.required}
    for o in outcomes:
        if o.outcome == "failed" and o.stage in required:
            return "failed", o
    problems = [
        o
        for o in outcomes
        if o.outcome in ("partial", "failed") or (o.outcome == "skipped" and o.reason != "disabled")
    ]
    if not problems:
        return "complete", None
    # A provider failure says more than a budget stop in an earlier stage.
    return "partial", next((o for o in problems if o.terminal is not None), problems[0])


def run(
    policy: Policy,
    keys: TrackerSecrets,
    stages: Sequence[Stage],
    report_writer: ReportWriter | None = None,
    *,
    run_id: str | None = None,
    out: Path | str | None = None,
    chat_transport: httpx.BaseTransport | None = None,
    search_transport: httpx.BaseTransport | None = None,
    fetch_transport: httpx.BaseTransport | None = None,
    resolver: Resolver = socket.getaddrinfo,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> RunResult:
    """Run the stages once. Raises `PolicyError` before any call when they don't fit the
    policy, and `StateLocked` when another run holds the state file."""
    for stage in stages:
        if stage.agent is not None and stage.agent not in policy.agents:
            raise PolicyError(f"Stage {stage.name} needs agent '{stage.agent}' under agents.")
        if stage.required and stage.agent and not policy.agents[stage.agent].enabled:
            raise PolicyError(f"agents.{stage.agent} runs required stage {stage.name}.")

    run_id = run_id or new_run_id()
    report_path = Path(out) if out else policy.reports_path / f"{run_id}.md"
    trace_path = policy.traces_path / f"{run_id}.jsonl"
    state = StateStore(policy.state_file)
    trace = Trace(trace_path, run_id, keys.values())
    budget = Budget(policy, clock)
    clients = Clients(
        policy,
        keys,
        budget.deadline,
        chat_transport=chat_transport,
        search_transport=search_transport,
        fetch_transport=fetch_transport,
        resolver=resolver,
        sleep=sleep,
    )
    run_ctx = StageContext(policy, None, state, trace, budget, clients, run_id)
    outcomes: list[StageOutcome] = []
    # Who failed for good -> terminal kind: a provider, or one model for a daily quota.
    dead: dict[str, str] = {}
    try:
        state.start_run(run_id, policy.topic, policy.k)
        for stage in stages:
            profile = policy.agents[stage.agent] if stage.agent else None
            needs = set(stage.providers)
            if profile is not None:
                needs |= {profile.model.provider, _model_key(profile)}
            if profile is not None and not profile.enabled:
                outcome = StageOutcome("skipped", "disabled")
            elif hit := sorted(needs & dead.keys()):
                outcome = StageOutcome("skipped", f"terminal:{dead[hit[0]]}")
            else:
                outcome = _run_stage(stage, profile, run_ctx)
            if (t := outcome.terminal) is not None:
                # Groq counts daily quotas per model: another model may still have some.
                own_quota = profile is not None and (
                    t.kind == "quota" and t.provider == profile.model.provider
                )
                dead[_model_key(profile) if own_quota else t.provider] = t.kind
            outcome.stage, outcome.agent = stage.name, stage.agent
            outcomes.append(outcome)

        status, decider = run_status(stages, outcomes)
        reason = decider.reason if decider else None
        meta = report.ReportMeta(
            topic=policy.topic,
            run_id=run_id,
            timestamp=datetime.now(UTC).isoformat(timespec="seconds"),
            status=status,
            stop_reason=reason,
            stop_detail=decider.detail if decider else None,
            usage=budget.usage(),
        )
        try:
            markdown = (report_writer or stage_report)(run_ctx, outcomes, meta)
        except Exception as err:  # the use case's writer failed: still write a report
            trace.event("report", status="error", reason=type(err).__name__, detail=str(err))
            markdown = stage_report(run_ctx, outcomes, meta)
        report.write(report_path, markdown)
        state.end_run(run_id, status, reason, budget.usage())
        trace.event(
            "summary",
            outcome=status,
            stop_reason=reason,
            report=str(report_path),
            stages=[o.summary() for o in outcomes],
            **budget.usage(),
        )
    except KeyboardInterrupt:
        state.end_run(run_id, "failed", "interrupted", budget.usage())
        trace.event("summary", outcome="failed", stop_reason="interrupted", **budget.usage())
        raise
    finally:
        clients.close()
        state.close()
        trace.close()

    if decider is None:
        message = f"Run {run_id} complete: {len(outcomes)} stages."
    else:
        why = decider.detail or report.describe_stop(decider.reason)
        message = f"Run {run_id} {status}: stage {decider.stage} {decider.outcome}, {why}."
    return RunResult(run_id, status, reason, report_path, trace_path, message)


def _model_key(profile: AgentProfile) -> str:
    return f"{profile.model.provider} model {profile.model.name}"


def _run_stage(stage: Stage, profile: AgentProfile | None, run_ctx: StageContext) -> StageOutcome:
    bound = {"stage": stage.name} | ({"agent": stage.agent} if stage.agent else {})
    budget = run_ctx.budget.child(stage.agent, profile.limits) if profile else run_ctx.budget
    ctx = StageContext(
        run_ctx.policy,
        profile,
        run_ctx.state,
        run_ctx.trace.bind(**bound),
        budget,
        run_ctx.clients,
        run_ctx.run_id,
    )
    try:
        outcome = stage.run(ctx)
    except TerminalError as err:
        outcome = StageOutcome("failed", f"terminal:{err.kind}", err.message, terminal=err)
    except Exception as err:
        ctx.trace.event("stage", status="error", reason=type(err).__name__, detail=str(err))
        outcome = StageOutcome("failed", type(err).__name__, str(err)[:500])
    if profile is not None:
        outcome.usage = {**budget.usage(), **outcome.usage}
    return outcome
