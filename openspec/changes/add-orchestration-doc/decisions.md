# Decisions: add-orchestration-doc

Lean change: archive `add-claim-verifier`, and write the hosting parts of `ORCHESTRATION.md` (Assignment 2, "Agentic Orchestration"). The user could not be reached; the main session relayed his answers.

## D1 Archive add-claim-verifier now
- class: mine
- source: grilling (relayed by main session)
- status: decided
- question: Archive `add-claim-verifier` (all tasks checked) now?
- options: A archive now, syncing its delta specs into `openspec/specs/` / B wait
- decision: A. Kilian, relayed 2026-11-15. Use the OpenSpec archive workflow (`openspec archive add-claim-verifier`), so the delta specs land in `openspec/specs/`.
- landed:

## D2 Scope of ORCHESTRATION.md for now
- class: mine
- source: grilling (relayed by main session)
- status: decided
- question: Which parts of `ORCHESTRATION.md` (repo root) are written now?
- options: A hosting parts only, the rest as headed stubs / B the whole document
- decision: A. Kilian, relayed 2026-11-15. Write:
  1. "Why Vercel and Neon instead of Render": the brief asks for Render's free tier (spins down after 15 min idle, about 1 min cold start); the verifier (`services/verifier`) and drafter run on Vercel, the backend uses Neon Postgres. Say why.
  2. Q2 "The network", cold start and timeouts only: what a cold start costs on this setup; how timeouts were chosen from `config.yaml` `options.verifier` and `openspec/changes/add-claim-verifier/design.md` D8: client timeout = `time_budget_ms` + `cold_start_ms` = 60 s + 15 s; `max_attempts` 4; backoff min(2^n, 30) s with ±20% jitter; `Retry-After` honored. Check each number against the code before writing it.
  3. Q3 "Duplicates": both cases, quoting the actual code from `services/verifier`: first copy finished → stored response returned, no new fetch and no model call; first copy still running → `503` with `Retry-After: 5`. Then "what changes if the platform restarted the verifier in between", for Vercel: a new instance has an empty in-memory store (design D7), so it verifies once more; cost one fetch plus one model call; the orchestrator still counts the `request_id` once.
  Stubs with a heading and "TODO": Q1 contract, Q4 injection, Q5 was it worth it.
- landed:

## D3 Accuracy on cold starts, and placeholders instead of invented numbers
- class: mine
- source: grilling (relayed by main session)
- status: decided
- question: How does the document describe cold starts and numbers nobody has measured?
- decision: Kilian, relayed 2026-11-15. Honest, not flattering. Vercel + Neon do not "avoid cold starts":
  - Vercel Python functions still cold-start (seconds, not Render's ~1 min). Fluid Compute reuses instances but does not guarantee it. Instances are not durable, so the in-memory idempotency store loses its entries on a new instance, the same problem as on Render.
  - Neon's free tier suspends compute after idle and wakes on the first connection (sub-second to a few seconds). The verifier has no database, so Neon does not affect it.
  - The trade: a much smaller cold start and no 15-minute spin-down rule, not zero cold start.
  - Never invent measured numbers. `VERIFIER_URL` is not set in the orchestrator's container (checked 2026-11-15). Use marked placeholders such as `<measure: first /healthz after 20 min idle>`, each with the one-line `curl` command that measures it.
  - The per-call latency list "from run 1 traces" is a placeholder table: no run with the verifier exists yet in `reports/` or `traces/` (only run1/run2, from before the verifier).
  - Prose is submitted under Kilian's name: short plain sentences, no em-dashes, no filler (apply the humanizer skill if it loads).
- landed:

## D4 Archive the five changes with unchecked tasks?
- class: mine
- source: grilling (relayed by main session)
- status: open
- question: Five changes are done in code but still have unchecked tasks, mostly production steps that are yours. Archive them now?
  - `add-application-drafter`: 6.3 deploy `mobile-systems-drafter` (secrets, `DRAFTER_*` env, Neon migration), 6.4 first real draft checked in Word.
  - `agentic-dev-cycle`: 4.1 first real orchestrator run (decisions.md, hook payload check).
  - `complete-daily-runs`: 4.1 check the next two scheduled runs (Scout `complete`, Curate outcome).
  - `show-run-history`: 4.3 browser check with the injection page and a `javascript:` URL.
  - `tracker-daily-trigger`: 6.1 GitHub token, 6.2 `CRON_SECRET` and `GITHUB_DISPATCH_TOKEN` on Vercel, 6.3 Neon migration then merge and deploy, 6.4 call the route once, 6.5 check the next morning's run. `docs/deployment.md` already describes it as live.
- options: A archive all five now and list the leftover tasks in this file / B archive only fully-checked changes (just `add-claim-verifier`) / C leave everything as is
- built: B
- decision:
- landed:

## D5 This session cannot spawn subagents
- class: expensive
- source: orchestrator
- status: open
- question: The orchestrator run of 2026-11-15 had no `Agent` tool (its frontmatter lists `Agent(spec-writer, implementer, checker, reviewer, security-reviewer, Explore)`, but the harness did not expose it) and no `openspec` CLI on PATH. The orchestrator may not write `ORCHESTRATION.md` or move spec files itself. So D1 to D3 are logged but not built. How should the work run?
- options: A rerun with `claude --agent orchestrator` where `Agent` is available / B the main session spawns `spec-writer`, `implementer`, `checker`, `reviewer` directly with this file as the brief / C install the OpenSpec CLI in the container first (for `openspec archive`), then A or B
- built: nothing beyond this file
- decision:
- landed:
- note: evidence for `agentic-dev-cycle` task 4.1 ("note what broke").
