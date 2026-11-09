## ADDED Requirements

### Requirement: Orchestrator writes no code
While the `orchestrator` agent runs in the main thread, `.claude/hooks/orchestrator-writes.sh` SHALL block (exit 2) an Edit or Write to any path other than `openspec/changes/<name>/decisions.md`, with a message telling it to delegate. A call from a subagent (a hook payload with a non-empty `agent_id`) SHALL pass. A payload the hook cannot parse SHALL be blocked. `.claude/hooks/test-orchestrator-writes.sh` checks every scenario below.

#### Scenario: Decision log
- **WHEN** the orchestrator writes `.claude/worktrees/x/openspec/changes/x/decisions.md`
- **THEN** the write goes through

#### Scenario: Code or another artifact
- **WHEN** the orchestrator edits `backend/app/main.py` or `openspec/changes/x/tasks.md`
- **THEN** the hook exits 2 and the edit does not happen

#### Scenario: Subagent
- **WHEN** an implementer spawned by the orchestrator edits `backend/app/main.py` (payload with `agent_id`)
- **THEN** the hook exits 0

#### Scenario: Unreadable payload
- **WHEN** the hook receives text that is not JSON, or JSON with an `agent_id` followed by garbage
- **THEN** it exits 2

### Requirement: One decision log per change
Every change run through the orchestrator SHALL have `openspec/changes/<name>/decisions.md` (a small fix: `openspec/changes/fix-<topic>/decisions.md`), with entries in the `CLAUDE.md` format: `class` (`mine`, `expensive` or `cheap`), `source`, `status`, `question`, `options`, `built`, `decision` and `landed`. Every grilling answer SHALL appear as a `source: grilling` entry with a `landed:` line once the spec is written. A `mine` entry SHALL NOT have `status: resolved`. These are agent behaviours; the first orchestrator run checks them (task 4.1).

#### Scenario: Implementer meets a decision of the user's
- **WHEN** an implementer would change `ranking.weights.fit` in `config.yaml` to make a test pass
- **THEN** it commits the finished tasks, appends a `class: mine, status: open` entry, and reports `blocked: D<n>` without changing the weight

#### Scenario: Cheap choice
- **WHEN** an implementer picks a helper's name or file location that no entry covers
- **THEN** it appends a `class: cheap, status: resolved` entry and keeps going

### Requirement: Reviewer audits decisions
When the change has a `decisions.md`, the `reviewer` SHALL check the diff against it and list as blockers: a `mine` or `expensive` choice with no entry (`unflagged`), code that contradicts a `decided` or `resolved` entry (`ignored`), and a `cheap` entry that should be `mine` or `expensive` (`misfiled`). A `built:` line that no longer matches the code SHALL be listed as `stale`.

#### Scenario: Unflagged paid call
- **WHEN** the diff adds a route that calls Groq for any signed-in user and `decisions.md` has no entry for it
- **THEN** the reviewer lists it under Decisions as an `unflagged` blocker, class `mine`

### Requirement: Production stays with the user
The orchestrator and its subagents SHALL NOT merge, deploy, run production migrations or set secrets. The orchestrator SHALL end a feature at a draft PR against `master`; shipping is `/ship` in a main session.

#### Scenario: Feature done
- **WHEN** the last review passes
- **THEN** the orchestrator pushes `feat/<name>`, opens a draft PR and tells the user to run `/ship <n>`
