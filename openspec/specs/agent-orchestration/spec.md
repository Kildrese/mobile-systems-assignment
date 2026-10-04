# agent-orchestration Specification

## Purpose
Lets the tracker runtime run several narrowly scoped agents under a conductor written in code. Each agent has its own model, tools, hosts, budget and instructions, while the run keeps one set of global budgets, one state file and one trace. Use cases build on this; it contains no use-case logic.
## Requirements
### Requirement: Agent profiles
The policy MAY define an `agents` mapping from agent name to profile. A profile SHALL define `tools` (a selection from the tools registered in code by the core and the configured use case; policy cannot add tools), `limits` (`max_steps` and `max_tokens`, plus `max_searches` and `max_fetches` when it has those tools) and `instructions`. It MAY define `model` fields (any field left out is inherited from the top-level `model`), `fetch_hosts`, `enabled` (default true) and use-case settings under `options`. Agent names SHALL be lowercase identifiers.

#### Scenario: Inherited model settings
- **WHEN** a profile sets only `model.name`
- **THEN** it uses the top-level `model`'s provider, temperature and other settings with that name

#### Scenario: Tool outside the run
- **WHEN** a profile lists a tool that is not registered in code
- **THEN** validation fails before any network call, naming `agents.<name>.tools` and the tool

### Requirement: Single-agent policies are unchanged
When the policy has no `agents` section, the tracker SHALL behave exactly as the core tracker specifies. That includes its report, exit codes and trace fields; only extra trace keys may appear.

#### Scenario: Core config
- **WHEN** the core's example `config.yaml` is run
- **THEN** the run behaves as before, and every core test passes unchanged

### Requirement: Agent budgets fit the global caps
For each of `max_steps`, `max_tokens`, `max_searches` and `max_fetches`, the sum across enabled agents SHALL NOT exceed the run's global limit, or validation fails, naming the limit and the total. Wall-clock time and cost SHALL be global only.

#### Scenario: Over-allocated tokens
- **WHEN** enabled agents' `max_tokens` add up to 70,000 and the global `max_tokens` is 60,000
- **THEN** validation fails with a message naming `limits.max_tokens` and the total 70,000

### Requirement: Budgets are enforced at both levels
Before every model call and tool call of an agent, the runtime SHALL check the agent's limits and the global limits. It SHALL charge usage to both. The stop reason SHALL say which level ran out: the agent level as `<agent>.<limit>`, the global level as `<limit>`.

#### Scenario: Agent limit first
- **WHEN** an agent reaches its own `max_steps` while global steps remain
- **THEN** that agent's stage ends with reason `<agent>.max_steps`, and later stages still run

#### Scenario: Global limit first
- **WHEN** the global `max_tokens` (less its reserve) is reached during an agent's stage
- **THEN** that stage ends with reason `max_tokens`, and no later agent stage makes a model call

### Requirement: Per-agent tool and host privileges
An agent SHALL be offered only its profile's tools. A call to any other tool SHALL return an `unknown_tool` result and count as a step. When a profile sets `fetch_hosts`, every fetch the agent causes SHALL be limited to those hosts, checked before the core fetch guardrails, which still apply in full.

#### Scenario: Tool not in profile
- **WHEN** an agent without `search_web` calls `search_web`
- **THEN** it gets `unknown_tool`, listing its own tools, and no search is made

#### Scenario: Host outside an agent's list
- **WHEN** an agent whose `fetch_hosts` is `[jobs.example.com]` fetches `https://other.example.org/`
- **THEN** it gets reason `host_not_allowed`, and no request is made

### Requirement: Conductor runs stages in code order
The conductor SHALL run the stages a use case registers, in the order the use case's code defines. Model output SHALL NOT change the order. A stage is an agent stage (one agent loop for a named profile) or a code stage. A stage whose agent profile has `enabled: false` SHALL be skipped with outcome `skipped` and reason `disabled`. A stage the use case marks `required` cannot be disabled.

#### Scenario: Disabled agent stage
- **WHEN** a use case has stages A (agent), B (code), C (agent) and policy disables C's agent
- **THEN** A and B run, C is recorded `skipped` with reason `disabled`, and the run can still be complete

### Requirement: Stages hand off only through state
A stage SHALL receive the policy, its own profile, the state store, the trace and its budget. It SHALL NOT receive another agent's messages or raw model output. Data passed between stages SHALL be records written to and read from the state store, and the stage that writes them validates them.

#### Scenario: No transcript leakage
- **WHEN** a later agent stage starts
- **THEN** its first model call contains only its own instructions and task, plus data it reads through its tools, and nothing from an earlier agent's conversation

### Requirement: Stage and run outcomes
Each stage SHALL end as `complete`, `partial` (stopped by a budget, or ended early with work left over), `skipped` (disabled, or skipped after a terminal failure), or `failed`. After a terminal failure, later agent stages that need what failed SHALL be skipped: for a daily quota from the stage's own model provider, the stages using that same model, because providers such as Groq count daily quotas per model; for any other terminal failure (bad key, payment, a rejected request, unreachable), every stage using that provider. The run SHALL be:
- `failed` when a stage marked `required` failed;
- `partial` when any stage is partial, failed without being marked `required`, or was skipped after a terminal failure;
- `complete` otherwise.

The run's stop reason SHALL be that of the first stage with a terminal failure, if any, and otherwise that of the first stage that was not complete. Exit codes SHALL follow the core: `0` complete, `2` partial, `3` failed. A report SHALL be written in every outcome.

#### Scenario: Daily quota mid-run
- **WHEN** an agent stage gets a daily-quota failure from its model provider
- **THEN** that stage is partial, later agent stages using the same model are `skipped` with reason `terminal:quota`, stages using another model of that provider still run, later code stages still run, the report is written, and the command exits `2`

#### Scenario: Rejected key mid-run
- **WHEN** an agent stage gets an authentication failure from its model provider
- **THEN** later agent stages using that provider are `skipped` with reason `terminal:auth`, whatever their model

#### Scenario: Required stage fails
- **WHEN** a code stage marked `required` raises a terminal error
- **THEN** the run is `failed`, a report naming the stage and error is written, and the command exits `3`

### Requirement: Trace attribution
Every trace event written during a stage SHALL include `stage`, and events from agent stages SHALL include `agent`. The summary event SHALL include, per stage, the outcome, the reason and usage (steps, tokens, searches, fetches and credits for agent stages; requests for code stages).

#### Scenario: Per-stage summary
- **WHEN** a run with two agent stages and one code stage ends
- **THEN** the summary event has three stage entries, each with outcome and usage, and every model and tool event names its stage and agent

