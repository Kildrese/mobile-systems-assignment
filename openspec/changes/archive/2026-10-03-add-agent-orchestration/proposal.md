# Proposal

## Why

The tracker core (archived as `add-agentic-tracker-core`, now on `master`) runs one agent: one model, one tool list, one budget. Some use cases are better served by several narrow agents, where each agent gets only the model, tools, hosts and budget its job needs. Splitting work this way separates privileges (an agent that reads the open web need not be able to write records) and spreads load across per-model provider quotas. This change adds multi-agent support to the runtime without tying it to any use case. A use case defines its agents in `config.yaml` and its stages in code, and the runtime enforces budgets, privileges and outcomes the same way for all of them.

## What Changes

- **Agent profiles in policy.** An optional `agents` section in `config.yaml` maps agent names to profiles. A profile has its own model (inheriting unset fields from the top-level `model`), a selection of the tools registered in code, its own limits, its own instructions and an optional `fetch_hosts` allowlist narrower than the run's. A policy without `agents` runs the single-agent tracker exactly as today.
- **Budgets at two levels.** Each agent has limits that must fit within the run's global limits (validated before any call). At runtime, both levels are checked before every model call and every tool call, and both are charged. Stop reasons say which level ran out (`scout.max_steps` versus `max_tokens`).
- **A reusable agent loop.** The loop in `loop.py` is extracted into an `AgentLoop` that takes a profile, a toolset, a budget and a finish handler. The single-agent `Runner` becomes one use of it, with unchanged behavior.
- **A tool registry with per-agent visibility.** Tools are registered in code with their argument model, schema, handler and CLI command. Policy still cannot add tools; a profile only selects from the registry. Each agent sees only its profile's tools, and use cases register their own tools in code.
- **A conductor written in code.** It runs a use case's ordered list of stages. A stage is either an agent stage (one `AgentLoop`) or a code stage. The conductor opens state, trace and the global budget once, gives each stage only the state store and its own profile (never another agent's conversation), records a per-stage outcome, and works out the run outcome. After a terminal provider failure, it skips the later stages that need that provider, and still runs code stages.
- **Trace attribution.** Every trace event carries `stage` and, for agent stages, `agent`. The summary event lists the outcome and usage per stage.

Out of scope: any concrete use case, its stages, tools and state tables (the internship tracker is the first, in `add-internship-tracker`); running stages in parallel; a supervising model; agents messaging each other.

## Capabilities

### New Capabilities
- `agent-orchestration`: agent profiles, two-level budgets, per-agent tool and host privileges, the stage conductor and its outcome rules, handoffs between stages limited to state, and trace attribution.

### Modified Capabilities
- `tracker-config`: the policy file may also define `agents` and `use_case`, and agent profiles may select tools registered in code (a top-level `tools` key is still rejected).

## Impact

- **Code**:
  - `backend/tracker/loop.py`: the loop is extracted into the new `agents.py`, and `Runner` keeps the single-agent path.
  - `budget.py`: gains a parent budget.
  - `tools.py`: becomes a registry.
  - `config.py`: gains `agents` and profile validation.
  - `trace.py`: gains the `stage` and `agent` fields.
  - New: `conductor.py` (stage protocol, outcomes).
- **Tests**: every existing `tests_tracker` test must pass unchanged. New tests use scripted fake models and toy stages.
- **Merge risk**: the core branch is still being finished, so expect small conflicts in `loop.py`, `tools.py` and `config.py`.
- **Docs**: a "Multiple agents" section in `docs/tracker.md`.
