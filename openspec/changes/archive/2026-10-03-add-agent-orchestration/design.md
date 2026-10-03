# Design

## Context

This change builds on the core as merged to `master` (`8938090`). The relevant shape:
- **`loop.py`**: `Runner` owns the run lifecycle: it opens `StateStore`, `Trace`, `Budget` and the clients, runs `_loop()`, and in `_finish_run()` writes the report, the run row and the summary. `_loop`, `_dispatch` and `_finish_call` are methods that read `self.policy` directly.
- **`budget.py`**: one `Budget(policy)`. `check_model_call()` and `check_tool()` read `policy.limits`.
- **`tools.py`**: `ARG_MODELS` and `TOOL_SCHEMAS` are module constants for the three fixed tools. `Toolbox` holds `search_web` and `fetch_article`. `validate_finish` is the single finish handler.
- **`config.py`**: a frozen `Policy` with no tool settings: a `tools` key is rejected (`extra="forbid"`), because tools are fixed in code.
- **`trace.py`**: `Trace.event(kind, **fields)` accepts arbitrary fields.

## Goals / Non-Goals

**Goals:**
- Running multiple agents is an additive layer. The single-agent path and every existing test stay as they are.
- A use case plugs in by registering tools and stages. The runtime has no use-case knowledge.

**Non-Goals:**
- Running stages in parallel, a supervising model, or agents talking to each other.
- Any use-case stage, tool or state table.

## Decisions

### D1. `AgentLoop` extracted from `Runner`
`agents.AgentLoop(profile, registry, toolbox, budget, trace, chat, finish_handler, task_prompt)` contains the current `_loop`, `_dispatch` and `_finish_call` logic. It reads its model, tools and instructions from an `AgentProfile` instead of `Policy`. `Runner` builds a default profile from the top-level policy (`AgentProfile.from_policy`) and calls `AgentLoop.run()`. Synthesis and the fallback report stay in `Runner`, because they belong to the single-agent report. The extraction is a move with a parameter change: the existing loop tests must pass unchanged.
- *Alternative:* subclass `Runner` per agent. Rejected: the lifecycle (state, trace, report, run row) belongs to the run, not to each agent.

### D2. Profiles in `Policy`
`AgentProfile(_Strict)`: `model: ModelOverride` (all fields optional, merged over the top-level `model`), `tools: tuple[str, ...]`, `limits: AgentLimits` (`max_steps`, `max_tokens`, optional `max_searches`/`max_fetches`), `instructions: str`, `fetch_hosts: tuple[str, ...] | None`, `enabled: bool = True`, `options: dict[str, Any] = {}`. `Policy.agents: dict[str, AgentProfile] = {}`. Validators check: names match `^[a-z][a-z0-9_]*$`; tools are registered in the code registry (a top-level `tools` key stays forbidden); `fetch_hosts` patterns use the same rules as `fetch.allowed_hosts`, and each one must be covered by the run's allowlist; the sums over enabled agents fit the global limits; and every provider an agent uses exists. `{topic}` and `{k}` are filled into each agent's instructions the same way.

### D3. Two-level `Budget`
`Budget(policy, clock, parent=None, limits=None, name=None)`. With a `parent`, `check_model_call()` checks its own `limits` first (reasons prefixed `"{name}."`), then calls `parent.check_model_call()`. `charge_tokens` and the counters update both levels. Wall time, cost and the synthesis reserve are global only, so a child delegates those to its parent. Stage usage comes from the child's counters.

### D4. Tool registry
`tools.REGISTRY: dict[str, ToolSpec]`, where `ToolSpec(name, args_model, schema, handler, cli)`. Each core tool registers itself. Use cases call `register(spec)` at import time, and only use cases in the fixed known-use-case map are imported. `Policy` validation reads the registry for agent profiles. The single-agent path always offers exactly the three core tools. `AgentLoop` builds its schemas from `profile.tools`, and `_dispatch` routes by spec. A tool not in the profile returns `unknown_tool`, as now. The finish handler is passed in (`validate_finish` by default), so an agent can end with a different payload. `python -m tracker.tools` lists every registered tool that has a CLI command.

### D5. Per-agent hosts
`Toolbox` gets an optional `fetch_hosts` restriction for each agent. `guard.check()` takes an extra `allowed_hosts` argument: the agent's patterns are checked first, then the policy's (both must match), and all address checks run unchanged.

### D6. Conductor
```python
class Stage(Protocol):
    name: str
    kind: Literal["agent", "code"]
    agent: str | None         # profile name for agent stages
    required: bool
    providers: set[str]       # providers the stage needs, for skipping after a terminal failure
    def run(self, ctx: StageContext) -> StageOutcome: ...

@dataclass
class StageContext:
    policy: Policy
    profile: AgentProfile | None
    state: StateStore
    trace: Trace          # bound to stage/agent, see D7
    budget: Budget        # child budget for agent stages, global for code stages
    clients: Clients      # chat clients per (provider, model), search, fetch
```
`conductor.run(policy, stages, report_writer)` opens state, trace and the global budget once. It records the run row, runs each stage in a `try`, and applies the skip and outcome rules from the spec. It then calls the use case's `report_writer(ctx, outcomes)` and writes the summary event. `python -m tracker run` uses the conductor when `policy.agents` is not empty and a use case is named (`use_case: <module>` in policy, resolved from a fixed list of known modules, never from a free-form import path).

### D7. Trace binding
`Trace.bind(**fields) -> BoundTrace` returns a view that adds `stage` and `agent` to every event it writes, through the same file and redaction. `ChatClient`, `SearchClient` and `Toolbox` already receive a trace, so they receive the bound view. The summary event gains a `stages` list of `{name, agent, outcome, reason, usage}`.

### D8. One chat client per model
The conductor keeps a `ChatClient` per `(provider, model name)`, sharing one `httpx.Client` per provider, so connections are reused. Retry classification is unchanged. Because the core's `TerminalError` carries the provider, the conductor can skip later stages that list that provider.

## Risks / Trade-offs

- [Refactoring `loop.py` while the core branch is still moving] → Do the extraction first and keep it mechanical, then merge core into this branch before adding features.
- [The sum rule for limits is conservative] → It's simple and easy to explain in AGENT.md. A use case that wants to borrow unused budget can be supported later with an explicit `pool` option.
- [`use_case` resolution could become an import gadget] → Only names from a fixed mapping in code are accepted. An unknown name fails validation.

## Migration Plan

Additive. The core is already archived; archive this change before `add-internship-tracker`. Rollback means reverting it, and single-agent configs are unaffected.
