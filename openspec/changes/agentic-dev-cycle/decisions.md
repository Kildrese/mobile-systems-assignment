# Decisions: agentic-dev-cycle

Port of the trademark repo's orchestrator flow. Grilling on 2026-11-08.

## D1 Where the rules live
- class: mine
- source: grilling
- status: decided
- question: Where do the Decisions rules go?
- options: A CLAUDE.md / B orchestrator.md only
- built: A
- decision: user, 2026-11-08: A. Subagents and the reviewer read them too.
- landed: proposal.md#What Changes; tasks 1.1

## D2 What is the user's
- class: mine
- source: grilling
- status: decided
- question: Which decisions are `mine` in this repo?
- options: A ranking weights, K, budgets and caps in config.yaml; prompts and profile; who can trigger paid calls; new dependencies, sources, boards; Neon/Vercel/GitHub production; reversing a spec or docs decision / B other
- built: A
- decision: user, 2026-11-08: A.
- landed: proposal.md#What Changes; specs/dev-cycle#Scenario: Implementer meets a decision of the user's

## D3 Database agent
- class: mine
- source: grilling
- status: decided
- question: Port trademark's db-agent for Neon?
- options: A no db-agent; production migrations stay with /ship and the user / B db-agent on Neon branches
- built: A
- decision: user, 2026-11-08: A, after asking why not B: production migrations are ordered against the merge, the local DB is disposable, CI tests migrations, settings.json already asks.
- landed: design.md#What changes from trademark

## D4 Which agents
- class: mine
- source: grilling
- status: decided
- question: Port orchestrator, spec-writer, implementer, reviewer?
- options: A all / B subset
- built: A. reviewer exists on master, so it gains the decisions pass only.
- decision: user, 2026-11-08: A.
- landed: tasks 2.1–2.4

## D5 Stop hook
- class: mine
- source: grilling
- status: decided
- question: Add a test-running Stop hook?
- options: A no / B run test.sh backend when backend/ changed
- built: A
- decision: user, 2026-11-08: A. The existing Stop hook (ruff, tsc) stays.
- landed: design.md#What changes from trademark

## D6 Branch
- class: mine
- source: grilling
- status: decided
- question: Where does this work happen?
- options: A own worktree feat/agentic-dev-cycle from master / B the drafter branch
- built: A
- decision: user, 2026-11-08: A.
- landed: .claude/worktrees/agentic-dev-cycle

## D7 Archive AGENT.md
- class: mine
- source: grilling
- status: decided
- question: AGENT.md is the Homework 1B write-up. Where does it go?
- options: A docs/archive/assignment-homework-1b.md
- built: A
- decision: user, 2026-11-08: A. 1B is graded and a branch freezes its state.
- landed: commit 6613c27

## D8 Worktree path for existing agents
- class: cheap
- source: implementer, task 2.4
- status: resolved
- question: checker, reviewer and security-reviewer assume the current checkout. The orchestrator briefs them with a worktree path. How do they find it?
- options: A one line each: run every command in the worktree the prompt names / B orchestrator cd's for them (it can't; subagents start in the main checkout)
- built: A
- decision: implementer, 2026-11-08: A, as trademark's reviewer does.
- landed: .claude/agents/checker.md:8; reviewer.md:12; security-reviewer.md:10

## D9 spec-writer's skill
- class: cheap
- source: implementer, task 2.2
- status: resolved
- question: tasks.md said preload openspec-propose; that skill creates the change folder, which the orchestrator already made.
- options: A openspec-ff-change, as trademark / B openspec-propose
- built: A
- decision: implementer, 2026-11-08: A.
- landed: .claude/agents/spec-writer.md:6

## D10 Review fixes
- class: cheap
- source: reviewer
- status: resolved
- question: Three should-fixes: "agent prompts" in the mine list is ambiguous; nobody commits the change folder; proposal Impact is stale.
- options: A fix all three as the reviewer suggested
- built: A
- decision: orchestrator (main session), 2026-11-09: A. Claude Code agent prompts are not `mine`; the orchestrator commits the change folder before each push; Impact updated. Unverified hook behaviour in --agent mode moved into task 4.1.
- landed: CLAUDE.md (Decisions); .claude/agents/reviewer.md (Pass 3); .claude/agents/orchestrator.md (Basics); proposal.md#Impact; tasks.md 4.1
