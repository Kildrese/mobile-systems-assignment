## 1. Archive add-claim-verifier (decisions D1, D5, D4 built as B)

Superseded by #38 (D16): the archive on master is #38's, and this branch no longer carries these moves.

- [x] 1.1 Create `openspec/specs/claim-verification/spec.md` from the change's `specs/claim-verification/spec.md`: a `# claim-verification Specification` heading, a `## Purpose` taken from the change's proposal (D9), then `## Requirements` with every ADDED requirement and its scenarios, unchanged
- [x] 1.2 Merge the other five delta specs into `openspec/specs/<capability>/spec.md` (`internship-pipeline`, `internship-report-view`, `opportunity-report`, `report-publishing`, `trace-log`): each MODIFIED requirement replaces the one with the same name in full; each ADDED requirement is appended to `## Requirements`. Stop and report if a MODIFIED name has no match
- [x] 1.3 Move `openspec/changes/add-claim-verifier/` to `openspec/changes/archive/2026-11-15-add-claim-verifier/` with `git mv`, its `specs/` folder included. Leave the five changes listed in D4 where they are

## 2. Write ORCHESTRATION.md (decisions D2, D3)

- [x] 2.1 Before writing, check every number against the code (D7) and note where each comes from: `config.yaml` `options.verifier` (`time_budget_ms`, `cold_start_ms`, `max_attempts`), the client timeout and backoff in `backend/tracker/usecases/internships/verifying.py`, the `Retry-After` handling, and the duplicate handling in `services/verifier`. If the code disagrees with D2, write what the code does and add an entry to `decisions.md`
- [x] 2.2 Create `ORCHESTRATION.md` at the repo root with headings in this order: "Why Vercel and Neon instead of Render", Q1 contract (TODO), Q2 "The network", Q3 "Duplicates", Q4 injection (TODO), Q5 "Was it worth it" (TODO)
- [x] 2.3 Write "Why Vercel and Neon instead of Render" per D2.1 and D3: the brief's Render free tier (spins down after 15 min idle, about 1 min cold start); Vercel Python functions still cold-start, in seconds; Fluid Compute reuses instances without a guarantee; instances are not durable; Neon suspends after idle and wakes on the first connection, and the verifier has no database. The trade is a smaller cold start and no 15-minute rule, not zero cold start
- [x] 2.4 Write Q2, cold start and timeouts only, per D2.2: client timeout = `time_budget_ms` + `cold_start_ms`, `max_attempts`, the backoff formula with jitter, `Retry-After` honored. Cold-start cost and per-call latency are marked placeholders (`<measure: ...>`), each with its one-line `curl` command; the latency table "from run 1 traces" is a placeholder table
- [x] 2.5 Write Q3 per D2.3: quote the code for both cases (first copy finished: stored response, no fetch, no model call; first copy running: `503` with `Retry-After: 5`), then what a restarted Vercel instance changes (empty in-memory store, one more fetch and model call, the orchestrator still counts the `request_id` once)
- [x] 2.6 Read the prose once against D3: short plain sentences, no em-dashes, no filler, no invented numbers (apply the humanizer skill if it loads)
- [x] 2.7 In `decisions.md`, add the built file and section to `landed:` for D1, D2, D3 and D5
