# Proposal

## Why

Features here already follow grilling → OpenSpec change → implement → `checker` → `reviewer` → PR → `/ship`, but one session does all of it. The session's context fills with code, and decisions made during implementation live only in the chat: the user sees them only if they read the diff. The trademark repo runs the same steps through an orchestrator that delegates to subagents and logs every decision in one file per change. This change brings that flow over, adapted to this repo.

## What Changes

- **`orchestrator` agent** (`claude --agent orchestrator`): grills the user, creates a worktree per feature, delegates to `spec-writer`, `implementer`s, `checker`, `reviewer` and `security-reviewer`, runs a second grilling on the decisions that came up, and opens a **draft** PR. It writes no code. `/ship` stays the user's step in the main session.
- **`spec-writer` agent**: writes the OpenSpec artifacts from the grilling answers, and logs every choice it made itself.
- **`implementer` agent**: implements one task group in the worktree and commits. It decides small choices itself and logs them. On a choice that is the user's, or one later work builds on, it commits what's done, logs the question and stops.
- **One decision log per change**: `openspec/changes/<name>/decisions.md` (for a small fix, `openspec/changes/fix-<topic>/decisions.md`).
- **`CLAUDE.md` gains a Decisions section**: which decisions are the user's (`mine`), which are `expensive` and which are `cheap`, plus the entry format. It replaces trademark's "could change an eval number" rule with this repo's: ranking weights, K, budgets and caps in `config.yaml`; agent prompts and the profile; who can trigger paid API calls; new dependencies, data sources or job boards; production on Neon, Vercel or GitHub (migrations, env vars, secrets, deploys, merges); reversing a decision in a spec or `docs/`.
- **`reviewer` gains a third pass** that checks the diff against `decisions.md`: choices with no entry, entries the code ignores, misclassified entries.
- **`.claude/hooks/orchestrator-writes.sh`** blocks the orchestrator, in the main thread, from editing anything except a change's `decisions.md`. A self-check comes with it.
- **No db-agent.** The local database is disposable, CI tests every migration on a fresh Postgres, and Neon production migrations stay with `/ship` and the user. `settings.json` already makes them ask.

## Capabilities

### New Capabilities
- `dev-cycle`: the delegated flow, the decision log and the guards on the orchestrator.

### Modified Capabilities
None.

## Impact

- **New files:** `.claude/agents/orchestrator.md`, `spec-writer.md`, `implementer.md`; `.claude/hooks/orchestrator-writes.sh` and `test-orchestrator-writes.sh`.
- **Changed:** `.claude/agents/reviewer.md` (decisions pass), `CLAUDE.md` (Workflow line, Decisions section); `checker.md`, `reviewer.md` and `security-reviewer.md` run in the worktree their prompt names (D8).
- **No change** to application code, CI, `settings.json`, the Stop hook or `/ship`.
- Also on this branch: `AGENT.md` moved to `docs/archive/assignment-homework-1b.md`, with its references in `CLAUDE.md`, `backend/CLAUDE.md` and a comment in `backend/tests_tracker/test_clients.py` updated; `.claude/worktrees/` ignored.
