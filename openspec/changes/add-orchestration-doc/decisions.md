# Decisions: add-orchestration-doc

Lean change: archive `add-claim-verifier`, and write the hosting parts of `ORCHESTRATION.md` (Assignment 2, "Agentic Orchestration"). The user could not be reached; the main session relayed his answers.

## D1 Archive add-claim-verifier now
- class: mine
- source: grilling (relayed by main session)
- status: decided
- question: Archive `add-claim-verifier` (all tasks checked) now?
- options: A archive now, syncing its delta specs into `openspec/specs/` / B wait
- decision: A. Kilian, relayed 2026-11-15. Use the OpenSpec archive workflow (`openspec archive add-claim-verifier`), so the delta specs land in `openspec/specs/`.
- landed: add-orchestration-doc/proposal.md#What Changes; tasks.md 1.1-1.3 (by hand per D5, no CLI); openspec/specs/claim-verification/spec.md (new); openspec/specs/{internship-pipeline,internship-report-view,opportunity-report,report-publishing,trace-log}/spec.md; openspec/changes/archive/2026-11-15-add-claim-verifier/
- note: the method changed per D5: merged by hand, not with `openspec archive`. The outcome is the same.

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
- landed: add-orchestration-doc/proposal.md#What Changes; tasks.md 2.2-2.5; ORCHESTRATION.md#Why Vercel and Neon instead of Render, #Q2 The network, #Q3 Duplicates, stubs #Q1 The contract, #Q4 Injection, #Q5 Was it worth it

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
- landed: add-orchestration-doc/proposal.md#What Changes; tasks.md 2.3, 2.4, 2.6; ORCHESTRATION.md#Why Vercel and Neon instead of Render (cold-start table), #Q2 The network (latency tables, placeholders with curl/jq), #Q3 Duplicates#If the platform restarted the verifier in between

## D4 Archive the five changes with unchecked tasks?
- class: mine
- source: grilling (relayed by main session)
- status: decided (user)
- question: Five changes are done in code but still have unchecked tasks, mostly production steps that are yours. Archive them now?
  - `add-application-drafter`: 6.3 deploy `mobile-systems-drafter` (secrets, `DRAFTER_*` env, Neon migration), 6.4 first real draft checked in Word.
  - `agentic-dev-cycle`: 4.1 first real orchestrator run (decisions.md, hook payload check).
  - `complete-daily-runs`: 4.1 check the next two scheduled runs (Scout `complete`, Curate outcome).
  - `show-run-history`: 4.3 browser check with the injection page and a `javascript:` URL.
  - `tracker-daily-trigger`: 6.1 GitHub token, 6.2 `CRON_SECRET` and `GITHUB_DISPATCH_TOKEN` on Vercel, 6.3 Neon migration then merge and deploy, 6.4 call the route once, 6.5 check the next morning's run. `docs/deployment.md` already describes it as live.
- options: A archive all five now and list the leftover tasks in this file / B archive only fully-checked changes (just `add-claim-verifier`) / C leave everything as is
- built: A on claude/archive-finished-changes (B on the add-orchestration-doc branch before the decision)
- decision: A. Kilian, 2026-11-15: archive all five now and list their leftover tasks in this file. Done in a separate orchestrator session on its own branch.
- landed: openspec/changes/archive/2026-11-15-{complete-daily-runs,show-run-history,tracker-daily-trigger,add-application-drafter,agentic-dev-cycle}/; openspec/specs/{agent-orchestration,internship-pipeline,report-publishing,internship-report-view,tracker-state}/spec.md (updated); openspec/specs/{tracker-dispatch,applicant-profile,application-drafter,application-drafts,dev-cycle}/spec.md (new)
- leftover tasks (unchecked when archived):
  - `openspec/changes/archive/2026-11-15-complete-daily-runs/tasks.md` 4.1: "After merging, check the next two scheduled runs: the Scout ends `complete`, and note Curate's outcome and the "Waiting for review" count to decide on making Curate cheaper per posting"
  - `openspec/changes/archive/2026-11-15-show-run-history/tasks.md` 4.3: "(needs a browser; `web-url.test.ts` covers the `javascript:` URL) Check in the browser with a published run whose log holds the test injection page (`tests_tracker/fixtures/injection.html`) and a rejected `javascript:` URL: nothing runs, and both show as text"
  - `openspec/changes/archive/2026-11-15-tracker-daily-trigger/tasks.md` 6.1: "Create the fine-grained token: only `mobile-systems-assignment`, Actions read and write, expiry at most a year"
  - `openspec/changes/archive/2026-11-15-tracker-daily-trigger/tasks.md` 6.2: "Set `CRON_SECRET` and `GITHUB_DISPATCH_TOKEN` on the Vercel backend project (Production)"
  - `openspec/changes/archive/2026-11-15-tracker-daily-trigger/tasks.md` 6.3: "Apply the migration to Neon, then merge and deploy"
  - `openspec/changes/archive/2026-11-15-tracker-daily-trigger/tasks.md` 6.4: "Call the route once with the secret: `202` and a new run in the Actions tab; a second call returns `already_dispatched`"
  - `openspec/changes/archive/2026-11-15-tracker-daily-trigger/tasks.md` 6.5: "The next morning: a run started between 09:00 and 10:00 UTC, and that day's row is `dispatched`"
  - `openspec/changes/archive/2026-11-15-add-application-drafter/tasks.md` 6.3: "Deploy: create `mobile-systems-drafter` (root `services/drafter`, connected to git), set `DRAFTER_TOKEN` and `ANTHROPIC_API_KEY` (Kilian adds the key himself), set `DRAFTER_URL`, `DRAFTER_TOKEN` and `DRAFTING_USERS=kiliandresse` on the backend project and `DRAFTER_URL`, `DRAFTER_TOKEN` and `DRAFTING_USERS` in GitHub, and run the migration on Neon"
  - `openspec/changes/archive/2026-11-15-add-application-drafter/tasks.md` 6.4: "Kilian uploads his profile, run `python -m app.share_drafts kiliandresse nyugrader` against production, draft one real offer, and check the `.docx` in Word: one page, layout unchanged"
  - `openspec/changes/archive/2026-11-15-agentic-dev-cycle/tasks.md` 4.1: "First real orchestrator run on a small feature: `decisions.md` gets grilling entries with `landed:`, an implementer stops on a `mine` choice, the reviewer runs Pass 3. Also confirm with one real payload that the frontmatter hook fires in `--agent` main-thread mode and that its payload has no `agent_id`. Note what broke in this change's `decisions.md`."

## D5 This session cannot spawn subagents
- class: expensive
- source: orchestrator
- status: resolved
- question: The orchestrator run of 2026-11-15 had no `Agent` tool (its frontmatter lists `Agent(spec-writer, implementer, checker, reviewer, security-reviewer, Explore)`, but the harness did not expose it) and no `openspec` CLI on PATH. The orchestrator may not write `ORCHESTRATION.md` or move spec files itself. So D1 to D3 are logged but not built. How should the work run?
- options: A rerun with `claude --agent orchestrator` where `Agent` is available / B the main session spawns `spec-writer`, `implementer`, `checker`, `reviewer` directly with this file as the brief / C install the OpenSpec CLI in the container first (for `openspec archive`), then A or B
- built: nothing beyond this file
- decision: B. Main session (acting as orchestrator), 2026-11-15. The main session spawns spec-writer, implementer, checker and reviewer itself. Without the OpenSpec CLI, the archive follows the openspec-archive-change skill by hand: merge the delta specs into openspec/specs/, then move the change to openspec/changes/archive/2026-11-15-add-claim-verifier/.
- landed: add-orchestration-doc/tasks.md 1.1-1.3; archive done by hand: openspec/changes/archive/2026-11-15-add-claim-verifier/ and openspec/specs/ as in D1
- note: evidence for `agentic-dev-cycle` task 4.1 ("note what broke").

## D6 Section order in ORCHESTRATION.md
- class: cheap
- source: spec-writer
- status: resolved
- question: In which order do the sections go?
- decision: "Why Vercel and Neon instead of Render" first, then Q1 to Q5 in the brief's order, the stubs in place. Spec-writer, 2026-11-15.
- landed: add-orchestration-doc/tasks.md 2.2

## D7 A number in D2 that the code contradicts
- class: cheap
- source: spec-writer
- status: resolved
- question: D2 says to check each number against the code. What if one differs?
- decision: The document states what the code does, and the implementer adds an entry here naming the difference. The document describes the system as built. Spec-writer, 2026-11-15.
- landed: add-orchestration-doc/tasks.md 2.1

## D8 No links to ORCHESTRATION.md from other files
- class: cheap
- source: spec-writer
- status: resolved
- question: Link the new document from `CLAUDE.md`, `README` or `docs/`?
- decision: No. The change stays to the files D1 to D3 name. A link can come with the full document. Spec-writer, 2026-11-15.
- landed: add-orchestration-doc/proposal.md#Impact

## D9 Purpose line of the new claim-verification spec
- class: cheap
- source: spec-writer
- status: resolved
- question: The archive skill gives a new spec a `## Purpose` section, and the delta spec has none. What goes there?
- decision: One or two sentences taken from `add-claim-verifier/proposal.md` ("New Capabilities"), no new content. Requirements and scenarios are copied unchanged. Spec-writer, 2026-11-15.
- landed: add-orchestration-doc/tasks.md 1.1

## D10 Duplicate handling is quoted from packages/agentkit, not services/verifier
- class: cheap
- source: implementer, task 2.5
- status: resolved
- question: D2.3 says to quote the duplicate handling "from `services/verifier`". The code lives in `packages/agentkit/src/agentkit/service.py` (`Store`, `serve`, `RUNNING_RETRY_AFTER = 5`), shared with the drafter; `services/verifier/main.py:23` only creates the store. What does Q3 quote?
- options: A quote `service.py` with file:line, plus `main.py:23` and the verifier's tests / B quote only `services/verifier` files
- built: A
- decision: A (per D7: the document describes the code as built). Implementer, 2026-11-15.
- landed: ORCHESTRATION.md#Q3 Duplicates

## D11 The client retries 502 and 504 too, the spec says 503
- class: cheap
- source: implementer, task 2.1
- status: resolved
- question: `openspec/specs/internship-pipeline` ("Verify stage calls the verifier") says connection errors, timeouts and `503` are retried. `verifying.py:189` also retries `502` and `504`. Every other number in D2 matches the code (timeout 60 s + 15 s, `max_attempts` 4, backoff `min(2^attempt, 30)` s x 0.8-1.2, wait = max(backoff, `Retry-After`)).
- options: A the document states the code (502, 503, 504) and the spec is left as archived / B change the code or the spec
- built: A
- decision: A (per D7). Implementer, 2026-11-15. Whether the spec or the code should change is open in D13.
- landed: ORCHESTRATION.md#Q2 The network#How the timeouts were chosen

## D12 Verify stage ignores max_wall_seconds
- class: mine
- source: reviewer
- status: decided (user)
- question: Verifier hangs can push a run past GitHub's 30-minute job limit (`.github/workflows/tracker.yml:30`), so nothing is published. `config.yaml:47` sets `max_wall_seconds: 1500`, but `_fits` (`verifying.py:299-306`) never checks wall time. Make Verify stop at the run's wall-time budget?
- options: A Verify checks remaining wall time before each request and marks the rest unverified / B lower `max_attempts` or `cold_start_ms` / C leave it and document
- built: C
- decision: A. Kilian, 2026-11-15: Verify checks the run's remaining wall time before each request; claims it can't send are marked unverified. Built in a follow-up fix change.
- landed: ORCHESTRATION.md#Q2 The network#How the timeouts were chosen (documented as a known gap)

## D13 Retried statuses
- class: mine
- source: reviewer
- status: decided (user)
- question: The client retries 502, 503 and 504 (`verifying.py:189`); the spec (`openspec/specs/internship-pipeline`, "Verify stage calls the verifier") names only 503. Add 502/504 to the spec (Vercel gateway errors for crashed or timed-out functions) plus a tracker test, or narrow the code to 503?
- options: A spec + test (reviewer recommends) / B code to 503 only
- built: neither (the document states the code, per D11)
- note: a retry after a 504 can repeat a paid Groq call, because the first copy may have finished its model call before the gateway gave up.
- decision: A. Kilian, 2026-11-15: add 502 and 504 to the spec's retried statuses, plus a tracker test. Built in a follow-up fix change.
- landed: ORCHESTRATION.md#Q2 The network#How the timeouts were chosen

## D14 Three changes rewrite "Daily scheduled run", one from a stale base
- class: expensive
- source: orchestrator (archive of D4)
- status: resolved
- question: `report-publishing` "Daily scheduled run" is MODIFIED by complete-daily-runs (2026-10-04: 09:17 UTC, job timeout > `max_wall_seconds`), tracker-daily-trigger (2026-10-06: Vercel cron + `workflow_dispatch`, no `schedule`, keeps the timeout) and add-application-drafter (2026-11-02). The drafter's copy was written against the old main text (scheduled GitHub workflow at 09:00 UTC) and only adds the `app.draft_new` step. Replacing in order would revert the cron dispatch and the timeout. Also, show-run-history MODIFIES "The API cannot start the tracker", which tracker-daily-trigger then RENAMES to "No user can start the tracker".
- options: A apply in creation order, and for the drafter's stale copy keep tracker-daily-trigger's text and add only the drafter's new content (the `app.draft_new` sentence and any new scenario) / B apply literally in order / C stop and ask
- built: A
- decision: A. Orchestrator, 2026-11-15. Code agrees: `.github/workflows/tracker.yml` has only `workflow_dispatch`, `backend/vercel.json` has the cron, and the workflow runs `python -m app.draft_new`. Merge order: complete-daily-runs, show-run-history, tracker-daily-trigger, add-application-drafter, agentic-dev-cycle.
- landed: openspec/specs/report-publishing/spec.md#Requirement: Daily scheduled run (tracker-daily-trigger's text plus the drafter's `python -m app.draft_new` sentence; scenarios "Daily run" and "Nothing ran" also name the draft step, "Drafting fails" added; the 09:17 "Scheduled run" scenario is replaced by "Daily run"); openspec/specs/internship-report-view/spec.md#Requirement: No user can start the tracker (show-run-history's MODIFIED applied, then tracker-daily-trigger's RENAMED and MODIFIED)

## D15 show-run-history's "Internship page" copy is older than the main spec
- class: cheap
- source: implementer (archive of D4)
- status: resolved
- question: show-run-history (2026-10-05) MODIFIES `internship-report-view` "Internship page". add-claim-verifier, archived earlier the same day, wrote the main text from a base that already held show-run-history's version, and added the claims bullet, "Claim text and evidence SHALL render as text, never as HTML.", and the scenarios "Claims shown" and "Markup in evidence". Replacing the block would delete those. D14 covers only "Daily scheduled run".
- options: A apply D14's rule: keep the newer text and add only what the stale copy adds / B replace literally / C stop and ask
- built: A. The stale copy adds nothing (diffed: every line of it is in the main text), so the main "Internship page" block is unchanged.
- decision: A. Implementer, 2026-11-15, by analogy with D14; no spec content changes.
- landed: openspec/specs/internship-report-view/spec.md#Requirement: Internship page (unchanged); commit "Archive show-run-history"

## D16 #38 already archived the shipped changes
- class: expensive
- source: main session (rebuild of #41)
- status: resolved
- question: PR #38 (merged 2026-11-15) archived add-claim-verifier, add-application-drafter, complete-daily-runs, show-run-history and tracker-daily-trigger, with Kilian's confirmation that their production steps are done, and kept agentic-dev-cycle open. This branch did the same archive separately (D1, D4, D14, D15). Which wins?
- options: A keep #38's archive on master, drop this branch's archive commits / B keep this branch's
- decision: A. Main session, 2026-11-15, when rebuilding #41 on master at Kilian's request. D1, D4, D14 and D15 are superseded: the archive, the spec merges and agentic-dev-cycle's state are as #38 left them. The leftover-task list under D4 no longer applies, since Kilian confirmed in #38 that those steps are done.
- landed: #41 rebuilt on 14cdf5d with only ORCHESTRATION.md, the fix-verify-wall-time-and-retries change and these two change folders

