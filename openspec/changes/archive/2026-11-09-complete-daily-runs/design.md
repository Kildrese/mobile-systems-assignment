# Design

## Context

Stage outcomes come from `StageOutcome.from_stop(stop)`: `complete` if the agent called `finish`, otherwise `partial` with the stop reason (`scout.max_steps`, `scout.max_tokens`, `max_wall_seconds`, `terminal:<kind>`). The run is `partial` when any stage is (agent-orchestration, "Stage and run outcomes"). The Scout has `max_steps: 12`, `max_tokens: 50000`, `max_searches: 6`, `max_fetches: 10` and `max_new_sources: 5`. One search, one fetch and one proposal already take three steps, so six searches cannot fit with their follow-ups in twelve steps.

Observed (2026-10-04): production `…d334` stopped on `scout.max_steps`; local `…608f` on `scout.max_steps` and Curate on `max_wall_seconds` (873 s); local `…1a78` on `scout.max_tokens` and Curate on `curator.max_steps` (870 s).

## Goals / Non-Goals

**Goals:**
- A run whose stages all did their work reports `complete`, with the Scout running daily.
- `partial` keeps meaning that something was cut off with work left.

**Non-Goals:**
- Making Curate cheaper per posting (option "4a"). Revisit once the first-run backlog has drained.
- Changing the rule that any partial stage makes the run partial.
- Running the Scout less often.

## Decisions

### D1. The Scout's work ends when its searches are spent
Searching is what the Scout is for. Once its searches are used up it has found everything it can this run, and the steps after that only read results and propose. So a step or token stop after the last search counts as the end of its work: `complete`, with reason `searches_spent` recorded in the trace and report. A stop while searches remain means the Scout was cut off before finishing what it set out to do, so it stays `partial`.

A wall-clock stop and a provider failure stay `partial` whatever the search count: they are run-level problems, not the end of the Scout's work.

Alternatives considered:
- *Exempt optional stages from the run status.* That would hide a Scout cut off after one search, which is a real shortfall.
- *Give the Scout more steps.* It would then use them on more pages and stop on the budget again: an open-ended task grows to fill whatever budget it has.
- *Fewer searches (say 4 in 12 steps).* This may help it reach `finish` itself, and can be tuned in config later. It does not define what "done" means.

### D2. Stop at the proposal cap
When `propose_source` accepts the `max_new_sources`-th proposal, code ends the Scout's stage as `complete` (reason `max_new_sources`) without another model call: further proposals would all be rejected, so further steps only cost tokens and wall time. The agent loop needs a way for a tool result to end the loop. The smallest form is a flag on the tool outcome that the loop checks after the tool runs, handled like a `finish`. The exact shape is left to implementation, provided the conductor and the other use cases see no change in behavior.

### D3. Orchestration lets a use case classify its stage's budget stop
The orchestration requirement currently defines `partial` as "stopped by a budget". It becomes "stopped by a budget with work left, or ended early with work left over", and a stage may return `complete` after a budget stop when its use case defines that stop as the end of its work (D1). Nothing changes for stages that don't define it, so the single-agent tracker and the other stages behave as before.

### D4. 1,500 seconds of wall time
Groq's free tier allows about 8,000 tokens a minute for `gpt-oss-120b`, with a separate pool for `gpt-oss-20b`, and the tracker waits out per-minute 429s (up to `retry.max_wait_seconds`). At 900 s the run stops while still mostly waiting. 1,500 s (25 minutes) fits in the existing 30-minute job timeout with about 5 minutes for checkout, `uv sync`, cache restore and save, publishing and artifact upload. That margin is now a requirement (report-publishing), so the two numbers can't drift apart silently. Cost is not the constraint: a run costs about $0.05 against `max_cost_usd: 0.50`.

## Risks / Trade-offs

- A Scout that spends its six searches on poor queries still counts as `complete`. That is accepted: the trace shows what it searched, and the proposal checks in code are unchanged.
- Longer runs mean more daily Groq tokens. The per-run `max_tokens` (150,000) is unchanged, so the daily total is bounded as before.
- If Curate still ends `partial` once the backlog has drained, runs stay partial. That is a real shortfall and the trigger for option 4a.
