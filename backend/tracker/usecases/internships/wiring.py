"""The internship use case wired to the orchestration layer.

The only module of the use case that knows about agents, stages and the tool
registry. It registers the use case's tools, validates its `options`, and builds the
fixed pipeline: Scout (agent), Collect (code, required), Curate (agent), Liveness
(code), Rank (code, required), Edit (agent). The conductor writes the report with
`report_writer` once every stage has run.
"""

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from tracker import conductor
from tracker.agents import Stop
from tracker.conductor import StageContext, StageOutcome
from tracker.config import Policy
from tracker.errors import PolicyError
from tracker.guard import host_allowed
from tracker.report import ReportMeta
from tracker.tools import Toolbox, ToolOutcome, ToolSpec, register, validation_message
from tracker.trace import Trace
from tracker.untrusted import injection_suspected, wrap
from tracker.usecases.internships import curation, editing, lifecycle, ranking, sources
from tracker.usecases.internships import report as internship_report
from tracker.usecases.internships.http import GuardedHttp
from tracker.usecases.internships.ranking import RankingSettings
from tracker.usecases.internships.store import OpportunityStore

AGENTS = ("scout", "curator", "editor")
DEFAULT_MAX_NEW_SOURCES = 5


# Options


class InternshipOptions(BaseModel):
    """`options` in config.yaml for `use_case: internships`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # None means the watchlist shipped with the use case (watchlist.yaml).
    watchlist: list[sources.WatchlistEntry] | None = None
    filters: sources.Filters = sources.Filters()
    ranking: RankingSettings = RankingSettings()
    # Job boards can be large JSON documents; pages keep fetch.max_bytes.
    board_max_bytes: int = Field(default=8_000_000, gt=0)


def options(policy: Policy) -> InternshipOptions:
    try:
        return InternshipOptions.model_validate(policy.options)
    except ValidationError as err:
        raise PolicyError(f"Invalid policy:\n  options: {validation_message(err)}") from None


def watchlist(opts: InternshipOptions) -> list[sources.WatchlistEntry]:
    return opts.watchlist if opts.watchlist is not None else sources.read_watchlist()


def _agent_option(policy: Policy, agent: str, name: str, default: int) -> int:
    value = policy.agents[agent].options.get(name, default)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise PolicyError(f"Invalid policy:\n  agents.{agent}.options.{name}: a positive integer")
    return value


def validate(policy: Policy) -> InternshipOptions:
    """Everything this use case needs from the policy, checked before any network call."""
    missing = [a for a in AGENTS if a not in policy.agents]
    if missing:
        raise PolicyError(
            "Invalid policy: use_case internships needs agent profiles "
            + ", ".join(f"agents.{a}" for a in missing)
        )
    opts = options(policy)
    blocked = [
        host
        for host in sources.BOARD_API_HOSTS.values()
        if not host_allowed(host, policy.fetch.allowed_hosts)
    ]
    if blocked:
        raise PolicyError(
            "Invalid policy:\n  fetch.allowed_hosts must allow the job-board APIs: "
            + ", ".join(blocked)
        )
    _agent_option(policy, "scout", "max_new_sources", DEFAULT_MAX_NEW_SOURCES)
    return opts


# HTTP


def board_http(ctx: StageContext, opts: InternshipOptions) -> GuardedHttp:
    cfg = ctx.policy.fetch.model_copy(update={"max_bytes": opts.board_max_bytes})
    return GuardedHttp(
        cfg,
        ctx.policy.retry,
        resolver=ctx.clients.resolver,
        transport=ctx.clients.fetch_transport,
        sleep=ctx.clients.sleep,
        clock=ctx.budget.clock,
        deadline=ctx.budget.deadline,
    )


def _toolbox_http(toolbox: Toolbox) -> GuardedHttp:
    return GuardedHttp(
        toolbox.policy.fetch,
        toolbox.policy.retry,
        resolver=toolbox.resolver,
        transport=toolbox.transport,
        allowed_hosts=toolbox.fetch_hosts or sources.POSTING_HOSTS,
    )


# Tools


def _needs_store(handler):
    def run(toolbox: Toolbox, args: Any, step: int) -> ToolOutcome:
        if toolbox.state is None:
            return ToolOutcome.failure("error", "no_state", "the state file is not available")
        outcome = handler(OpportunityStore(toolbox.state), toolbox, args)
        extra = {}
        if outcome.untrusted is not None:
            extra["injection_suspected"] = injection_suspected(outcome.untrusted)
        if not outcome.ok:
            extra["detail"] = outcome.data.get("detail")
        toolbox.trace.event(
            "tool",
            step=step,
            tool=handler.__name__.removeprefix("_"),
            args=args.model_dump(),
            status=outcome.status,
            reason=outcome.reason,
            **extra,
        )
        return outcome

    return run


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProposeSourceArgs(_Args):
    company: str = Field(min_length=1, max_length=120)
    kind: str = Field(min_length=1, max_length=20)
    board: str = Field(min_length=1, max_length=100)
    evidence_url: str = Field(min_length=1, max_length=2048)


class PostingArgs(_Args):
    posting_id: int


class DetailArgs(_Args):
    posting_id: int
    url: str = Field(min_length=1, max_length=2048)


class SaveRecordArgs(_Args):
    posting_id: int
    record: dict[str, Any]

    @field_validator("record", mode="before")
    @classmethod
    def json_text(cls, value: Any) -> Any:
        # The command line passes the record as a JSON string.
        return json.loads(value) if isinstance(value, str) else value


class MarkSameArgs(_Args):
    posting_id: int
    opportunity_id: int
    reason: str = Field(min_length=1, max_length=300)


class FlagUnclearArgs(_Args):
    posting_id: int
    reason: str = Field(min_length=1, max_length=300)


def _propose_source(store: OpportunityStore, toolbox: Toolbox, args: ProposeSourceArgs):
    policy = toolbox.policy
    cap = (
        _agent_option(policy, "scout", "max_new_sources", DEFAULT_MAX_NEW_SOURCES)
        if "scout" in policy.agents
        else DEFAULT_MAX_NEW_SOURCES
    )
    return sources.propose_source(
        store,
        run_id=toolbox.run_id,
        seen_urls=toolbox.seen,
        cap=cap,
        company=args.company,
        kind=args.kind,
        board=args.board,
        evidence_url=args.evidence_url,
    )


def _get_posting(store: OpportunityStore, toolbox: Toolbox, args: PostingArgs):
    return curation.get_posting(store, args.posting_id, toolbox.policy.fetch.max_chars_for_model)


def _fetch_posting_detail(store: OpportunityStore, toolbox: Toolbox, args: DetailArgs):
    return curation.fetch_posting_detail(
        store,
        args.posting_id,
        args.url,
        http=_toolbox_http(toolbox),
        max_chars=toolbox.policy.fetch.max_chars_for_model,
    )


# Quote misses per (run, posting). ponytail: process-wide, fine for one run per process.
_quote_misses: Counter[tuple[str, int]] = Counter()


def _save_record(store: OpportunityStore, toolbox: Toolbox, args: SaveRecordArgs):
    # A model that repeats a wrong quote does not get to retry forever: on its second try,
    # fields whose quote is not in the posting are saved as unknown.
    key = (toolbox.run_id, args.posting_id)
    outcome = curation.save_record(
        store,
        args.posting_id,
        args.record,
        toolbox.run_id,
        drop_unverified=_quote_misses[key] > 0,
    )
    if outcome.reason == "quote_not_found":
        _quote_misses[key] += 1
    return outcome


def _mark_same(store: OpportunityStore, toolbox: Toolbox, args: MarkSameArgs):
    return curation.mark_same(store, args.posting_id, args.opportunity_id, args.reason)


def _flag_unclear(store: OpportunityStore, toolbox: Toolbox, args: FlagUnclearArgs):
    return curation.flag_unclear(store, args.posting_id, args.reason)


def _get_opportunities(store: OpportunityStore, toolbox: Toolbox, args: _Args):
    return editing.get_opportunities(store, toolbox.run_id, toolbox.policy.k)


def _schema(name: str, description: str, properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": list(properties),
                "additionalProperties": False,
            },
        },
    }


_FIELD = {
    "type": "object",
    "properties": {
        "value": {"description": "The value, or the string 'unknown'"},
        "quote": {"type": "string", "description": "Verbatim text from the posting"},
    },
    "required": ["value"],
}


def _choice_field(allowed: tuple[str, ...]) -> dict[str, Any]:
    """A field whose value is one of `allowed`, listed in the schema the model sees."""
    value = {"type": "string", "enum": list(allowed)}
    return {**_FIELD, "properties": {**_FIELD["properties"], "value": value}}


_RECORD = {
    "type": "object",
    "description": (
        "Every field except title may be {'value': 'unknown'}. Every known field needs a "
        "quote copied word for word from the posting."
    ),
    "properties": {
        "title": _FIELD,
        "role_type": _choice_field(curation.ROLE_TYPES),
        "term": {**_FIELD, "description": "e.g. 'Summer 2027', or unknown"},
        "locations": {**_FIELD, "description": "value is a list of places"},
        "remote": _choice_field(curation.REMOTE),
        "compensation": _FIELD,
        "deadline": {
            **_FIELD,
            "description": (
                "The date applications close. Not the internship's start or end dates; "
                "unknown if the posting names no application deadline"
            ),
        },
        "work_authorization": {
            **_FIELD,
            "description": "Any work-authorization or sponsorship sentence, quoted",
        },
    },
    "required": ["title"],
}
_INT = {"type": "integer"}
_STR = {"type": "string"}

TOOLS = [
    ToolSpec(
        "propose_source",
        ProposeSourceArgs,
        _schema(
            "propose_source",
            "Add a company's public job board to the watchlist. kind is greenhouse, lever or "
            "ashby; board is the board identifier. evidence_url must be a page you found in "
            "this run.",
            {"company": _STR, "kind": _STR, "board": _STR, "evidence_url": _STR},
        ),
        _needs_store(_propose_source),
        cli=True,
    ),
    ToolSpec(
        "get_posting",
        PostingArgs,
        _schema(
            "get_posting",
            "Read a stored posting's text, with same-company candidates it may duplicate.",
            {"posting_id": _INT},
        ),
        _needs_store(_get_posting),
        cli=True,
    ),
    ToolSpec(
        "fetch_posting_detail",
        DetailArgs,
        _schema(
            "fetch_posting_detail",
            "Fetch a posting's own page when the stored text lacks a field. Only job-board "
            "posting hosts are allowed. Its text then counts as the posting's text for quotes.",
            {"posting_id": _INT, "url": _STR},
        ),
        _needs_store(_fetch_posting_detail),
        cli=True,
        budget="fetch_article",
    ),
    ToolSpec(
        "save_record",
        SaveRecordArgs,
        _schema(
            "save_record",
            "Save a posting as a new opportunity record. Rejected when a quote is not in the "
            "posting.",
            {"posting_id": _INT, "record": _RECORD},
        ),
        _needs_store(_save_record),
        cli=True,
    ),
    ToolSpec(
        "mark_same",
        MarkSameArgs,
        _schema(
            "mark_same",
            "Link a posting to an existing opportunity of the same company that is the same role.",
            {"posting_id": _INT, "opportunity_id": _INT, "reason": _STR},
        ),
        _needs_store(_mark_same),
        cli=True,
    ),
    ToolSpec(
        "flag_unclear",
        FlagUnclearArgs,
        _schema(
            "flag_unclear",
            "Park a posting you cannot turn into a record, with the reason.",
            {"posting_id": _INT, "reason": _STR},
        ),
        _needs_store(_flag_unclear),
        cli=True,
    ),
    ToolSpec(
        "get_opportunities",
        _Args,
        _schema(
            "get_opportunities",
            "List this run's opportunities to summarize: the new ones and the top K.",
            {},
        ),
        _needs_store(_get_opportunities),
        cli=True,
    ),
]
for _spec in TOOLS:
    register(_spec)


# Finish handlers


def _note_finish(arguments: dict[str, Any], step: int, toolbox: Toolbox, trace: Trace):
    trace.event("tool", step=step, tool="finish", args=arguments, status="ok")
    return "", {"note": str(arguments.get("note", ""))[:2000]}


NOTE_SCHEMA = _schema("finish", "End your work, with an optional short note.", {"note": _STR})
NOTE_SCHEMA["function"]["parameters"]["required"] = []

SUMMARIES_SCHEMA = _schema(
    "finish",
    "Submit your summaries and end. At most 3 sentences each, only facts in the record.",
    {
        "summaries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"opportunity_id": _INT, "text": _STR},
                "required": ["opportunity_id", "text"],
            },
        }
    },
)


# Stages


def scout_outcome(stop: Stop, searches: int, max_searches: int, agent: str) -> StageOutcome:
    """The Scout's work is searching: once its searches are spent, its own step or token
    budget ending the stage is the end of its work, not a shortfall. A stop with searches
    left, on the run's budgets or the wall clock, or after a provider failure is partial."""
    if isinstance(stop.finish, dict) and (reason := stop.finish.get("reason")):
        return StageOutcome("complete", reason)
    spent = searches >= max_searches
    if spent and stop.reason in (f"{agent}.max_steps", f"{agent}.max_tokens"):
        return StageOutcome("complete", "searches_spent")
    return StageOutcome.from_stop(stop)


@dataclass
class ScoutStage:
    name: str = "scout"
    agent: str = "scout"
    required: bool = False
    kind: str = "agent"
    providers: frozenset = field(default_factory=frozenset)

    def run(self, ctx: StageContext) -> StageOutcome:
        store = OpportunityStore(ctx.state)
        sources.load_watchlist(store, watchlist(options(ctx.policy)), ctx.run_id)
        known = ", ".join(sorted({s["company"] for s in store.sources()})) or "none yet"
        cap = _agent_option(ctx.policy, "scout", "max_new_sources", DEFAULT_MAX_NEW_SOURCES)
        assert ctx.profile is not None
        limits = ctx.profile.limits
        budget = (
            f"You have {limits.max_steps} steps and {limits.max_searches} searches in all; "
            "every tool call takes a step, so keep one for finish. "
        )
        task = (
            f"Find companies hiring for: {ctx.policy.topic}. Search the web, read promising "
            "pages, and for each company with a public Greenhouse, Lever or Ashby job board "
            f"call propose_source. Add at most {cap} new sources. "
            f"Already on the watchlist: {known}. {budget}Call finish when done."
        )
        # Every further proposal would be rejected once the cap is reached.
        stop, _ = ctx.run_agent(
            task,
            finish=_note_finish,
            finish_schema=NOTE_SCHEMA,
            done=lambda: (
                {"reason": "max_new_sources"}
                if store.count_sources_added(ctx.run_id, "scout") >= cap
                else None
            ),
        )
        return scout_outcome(stop, ctx.budget.searches, limits.max_searches or 0, ctx.budget.name)


@dataclass
class CollectStage:
    name: str = "collect"
    agent: None = None
    required: bool = True
    kind: str = "code"
    providers: frozenset = field(default_factory=frozenset)

    def run(self, ctx: StageContext) -> StageOutcome:
        opts = options(ctx.policy)
        store = OpportunityStore(ctx.state)
        sources.load_watchlist(store, watchlist(opts), ctx.run_id)
        results = sources.collect_all(
            store, board_http(ctx, opts), ctx.trace, ctx.run_id, opts.filters
        )
        readable = [r for r in results if r.readable]
        usage = {"requests": len(results), "readable": len(readable)}
        if not readable:
            # Without earlier opportunities there is nothing to report: the run fails.
            outcome = "partial" if store.opportunities() else "failed"
            return StageOutcome(
                outcome, "no_source_readable", "no source could be read", usage=usage
            )
        unreadable = len(results) - len(readable)
        reason = f"{unreadable} of {len(results)} sources unreadable" if unreadable else None
        return StageOutcome("complete", reason, usage=usage)


def _task(store: OpportunityStore, posting_id: int, max_chars: int, trace: Trace) -> str:
    # The posting comes with the task, wrapped as untrusted data exactly as get_posting
    # returns it, so handling it usually takes one model call instead of two.
    outcome = curation.get_posting(store, posting_id, max_chars)
    assert outcome.untrusted is not None
    trace.event(
        "tool",
        tool="get_posting",
        args={"posting_id": posting_id},
        status="ok",
        given_with_task=True,
        injection_suspected=injection_suspected(outcome.untrusted),
    )
    return (
        "Turn the posting below into an opportunity record: do exactly one of save_record "
        "(a new role), mark_same (the same role as a same-company candidate listed with the "
        "posting), or flag_unclear (not a usable internship posting). Quote the posting word "
        "for word for every field you fill in; use 'unknown' otherwise. Your work ends as "
        "soon as the posting is handled.\n\n"
        + wrap("get_posting", outcome.untrusted, **outcome.attributes)
    )


def next_posting(
    store: OpportunityStore, run_id: str, settings: RankingSettings
) -> dict[str, Any] | None:
    """The most relevant pending posting: when the budget runs out, what is left over is
    what matters least, and it waits for the next run."""
    pending = store.pending_postings(run_id)
    return min(pending, key=lambda p: (-ranking.focus(p["title"], settings), p["id"]), default=None)


@dataclass
class CurateStage:
    name: str = "curate"
    agent: str = "curator"
    required: bool = False
    kind: str = "agent"
    providers: frozenset = field(default_factory=frozenset)

    def run(self, ctx: StageContext) -> StageOutcome:
        """One posting per fresh conversation, so each prompt stays a few thousand tokens."""
        store = OpportunityStore(ctx.state)
        linked = sum(
            1
            for p in store.pending_postings(ctx.run_id)
            if curation.link_exact(store, p["id"]) is not None
        )
        settings = options(ctx.policy).ranking
        postings = 0
        while posting := next_posting(store, ctx.run_id, settings):
            postings += 1
            stop = self._curate(ctx, store, posting["id"])
            if stop.finish is None:  # budget or provider stop: leftovers stay pending
                outcome = StageOutcome.from_stop(stop)
                outcome.usage = {"postings": postings, "linked_by_code": linked}
                return outcome
            self._settle(ctx, store, posting["id"])
        return StageOutcome("complete", usage={"postings": postings, "linked_by_code": linked})

    def _curate(self, ctx: StageContext, store: OpportunityStore, posting_id: int) -> Stop:
        finishes = 0

        def pending() -> bool:
            return store.posting(posting_id)["curation"] == "pending"

        def finish(arguments: dict[str, Any], step: int, toolbox: Toolbox, trace: Trace):
            nonlocal finishes
            finishes += 1
            left = pending()
            trace.event("tool", step=step, tool="finish", args=arguments, status="ok", pending=left)
            if left and finishes < 2:
                return json.dumps(
                    {"error": "posting_pending", "detail": f"posting {posting_id} is unhandled"}
                ), None
            return "", {"pending": left}

        max_chars = ctx.policy.fetch.max_chars_for_model
        stop, _ = ctx.run_agent(
            _task(store, posting_id, max_chars, ctx.trace),
            finish=finish,
            finish_schema=NOTE_SCHEMA,
            done=lambda: None if pending() else {"pending": False},
        )
        return stop

    def _settle(self, ctx: StageContext, store: OpportunityStore, posting_id: int) -> None:
        """A posting left pending after a finished conversation counts a failure; two park it."""
        if store.posting(posting_id)["curation"] != "pending":
            return
        if store.add_failure(posting_id) >= 2:
            store.set_curation(
                posting_id, "unclear", unclear_reason="curator left it unresolved twice"
            )
            ctx.trace.event(
                "tool",
                tool="flag_unclear",
                args={"posting_id": posting_id},
                status="ok",
                reason="unresolved_twice",
            )


@dataclass
class LivenessStage:
    name: str = "liveness"
    agent: None = None
    required: bool = False
    kind: str = "code"
    providers: frozenset = field(default_factory=frozenset)

    def run(self, ctx: StageContext) -> StageOutcome:
        counts = lifecycle.run_liveness(OpportunityStore(ctx.state), ctx.run_id)
        return StageOutcome("complete", usage=asdict(counts))


@dataclass
class RankStage:
    name: str = "rank"
    agent: None = None
    required: bool = True
    kind: str = "code"
    providers: frozenset = field(default_factory=frozenset)

    def run(self, ctx: StageContext) -> StageOutcome:
        ranked = ranking.rank_open(
            OpportunityStore(ctx.state), ctx.run_id, options(ctx.policy).ranking, ctx.policy.k
        )
        return StageOutcome("complete", usage={"ranked": len(ranked)})


@dataclass
class EditStage:
    name: str = "edit"
    agent: str = "editor"
    required: bool = False
    kind: str = "agent"
    providers: frozenset = field(default_factory=frozenset)

    def run(self, ctx: StageContext) -> StageOutcome:
        store = OpportunityStore(ctx.state)
        allowed = {o["id"] for o in editing.wanted(store, ctx.run_id, ctx.policy.k)}
        if not allowed:
            return StageOutcome("complete", "nothing to summarize")

        def finish(arguments: dict[str, Any], step: int, toolbox: Toolbox, trace: Trace):
            outcome = editing.finish_summaries(store, ctx.run_id, arguments, allowed)
            trace.event(
                "tool",
                step=step,
                tool="finish",
                args=arguments,
                status=outcome.status,
                reason=outcome.reason,
                accepted=outcome.data.get("accepted"),
                rejected=outcome.data.get("rejected"),
            )
            if outcome.ok:
                return "", outcome.data
            return json.dumps(outcome.data), None

        task = (
            "Call get_opportunities, then write a summary of at most 3 sentences for each "
            "listed opportunity: what the role is and why it matches the search. Use only facts "
            "in the record; do not add numbers, pay or dates that are not there. Submit them "
            f"with finish. Opportunity ids: {sorted(allowed)}."
        )
        stop, _ = ctx.run_agent(task, finish=finish, finish_schema=SUMMARIES_SCHEMA)
        return StageOutcome.from_stop(stop)


def stages(policy: Policy) -> list[conductor.Stage]:
    """The fixed pipeline. Raises `PolicyError` when the policy does not fit it."""
    validate(policy)
    return [ScoutStage(), CollectStage(), CurateStage(), LivenessStage(), RankStage(), EditStage()]


def report_writer(ctx: StageContext, outcomes: list[StageOutcome], meta: ReportMeta) -> str:
    stage_rows = [
        {"name": o.stage, "outcome": o.outcome, "reason": o.detail or o.reason} for o in outcomes
    ]
    note = None
    if any(o.stage == "scout" and o.outcome == "skipped" for o in outcomes):
        note = "Discovery (the Scout stage) was skipped in this run."
    return internship_report.render(
        meta, OpportunityStore(ctx.state), ctx.policy.k, stages=stage_rows, note=note
    )
