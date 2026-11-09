# Decisions: fix-dispatch-retry

Branched from fix/archive-shipped-changes (PR #38), so the tracker-dispatch spec is in openspec/specs/tracker-dispatch/. Merge #38 first.

Evidence (prod check 2026-11-09): on Nov 6 the cron's dispatch call to GitHub failed with `ReadTimeout: The read operation timed out` (backend runtime error, route /fastapi, 09:38:41 UTC). The `tracker_dispatches` row is `failed`, `attempts=1`, never retried, and there's no tracker.yml run that day. The other 6 days are `dispatched`.

## D1 Retry a failed dispatch inside the same cron call
- class: mine
- source: grilling
- status: decided
- question: How should a failed dispatch be retried?
- options: A second Vercel cron later in the morning / B one retry inside the same cron request / C both
- decision: Kilian, 2026-11-09: B. On a timeout or error, wait briefly and retry once with a longer timeout. Add no new cron and no vercel.json schedule change.
- landed: backend/app/routers/internal.py (tracker_dispatch, RETRY_WAIT); specs/tracker-dispatch#Requirement: Retry a failed dispatch once; backend/tests/test_tracker_dispatch.py::test_a_timeout_is_retried_once, ::test_a_timeout_then_a_failed_retry_fails_the_day

## D2 Check GitHub before retrying
- class: mine
- source: grilling
- status: decided
- question: A timeout doesn't prove GitHub rejected the dispatch, so a blind retry could start two paid runs (Groq/Tavily/Anthropic) on one day. Guard against it?
- options: A before retrying, list today's tracker.yml workflow_dispatch runs (the token has Actions read) and mark the row dispatched if one exists / B retry blindly
- decision: Kilian, 2026-11-09: A (stated as part of the question he answered). Who can trigger a run is unchanged: only the cron, with CRON_SECRET.
- landed: backend/app/routers/internal.py (_ran_on); specs/tracker-dispatch#Scenario: Timeout, but the run started; backend/tests/test_tracker_dispatch.py::test_a_timeout_with_a_run_today_is_not_dispatched_again

## D3 Retry details: which errors, how long
- class: cheap
- source: implementer
- status: resolved
- question: Which failures get the retry, how long to wait, what timeout for the retry?
- options: A every failure except a missing token, wait 5 s, retry timeout 20 s / B only timeouts and 5xx
- built: A (D1 says "a timeout or error"; a retried 4xx costs one free GitHub call). Worst case 10+5+10+20 = 45 s, under Vercel's function timeout and the 5-minute stale-claim window.
- decision: implementer, 2026-11-09: A
- landed: backend/app/routers/internal.py (RETRY_WAIT, tracker_dispatch)

## D4 When today's runs can't be listed
- class: cheap
- source: implementer
- status: decided
- question: The run check itself fails (timeout, 401). Retry anyway or not?
- options: A don't retry, mark `failed` with a note / B retry blindly
- built: A, following D2's purpose: never risk a second paid run on an unconfirmed check. The day stays `failed` (the error says why) and is missed unless someone starts a run from the Actions tab.
- decision: implementer, 2026-11-09: A; confirmed by Kilian, 2026-11-09
- landed: backend/app/routers/internal.py (tracker_dispatch); specs/tracker-dispatch#Scenario: Runs can't be listed; backend/tests/test_tracker_dispatch.py::test_when_the_runs_cannot_be_listed_it_does_not_retry

## D5 Run-list lag before the retry
- class: mine
- source: reviewer (security), backend/app/routers/internal.py:120-128
- status: decided
- question: GitHub may accept a dispatch that timed out or got a 5xx, without the run showing in the list within RETRY_WAIT = 5 s (lag is likeliest exactly when GitHub is slow). _ran_on returns False, the retry dispatches again, and tracker.yml's `concurrency: tracker, cancel-in-progress: false` queues a second full paid run (Groq, Tavily, Anthropic). Only the cron can trigger it.
- options: A keep the single 5 s check / B on timeout or 5xx, re-check the list again before retrying (~10-15 s total wait, still < 60 s worst case) / C retry only on a 4xx/429 that proves GitHub refused; a timeout or 5xx with an empty list stays failed, no retry / D tracker job skips when today's report is already published
- built: A
- decision: Kilian, 2026-11-09: D, a guard in tracker.yml. Its first step exits without doing work if another cron-dispatched tracker run already started that UTC day (excluding itself). Keep the retry and the 5 s check (D2).
- landed: .github/workflows/tracker.yml (guard job, run job `if`); specs/report-publishing#Requirement: Daily scheduled run, #Scenario: Second cron run on one day, #Scenario: Two cron runs created together; specs/tracker-dispatch#Requirement: Retry a failed dispatch once; docs/deployment.md (What starts the daily run, step 6). The guard itself has no automated test (CI doesn't run workflows); its jq filter was checked by hand on a sample runs list.

## D7 Guard scope: manual runs
- class: cheap
- source: orchestrator
- status: resolved
- question: report-publishing has the scenario "Manual run while the daily run is in progress", so a deliberate run from the Actions tab must still go through. How does the guard tell the cron's runs from manual ones?
- options: A the route passes a workflow_dispatch input (e.g. source=cron, shown in run-name) and the guard only skips cron-sourced runs when another cron-sourced run exists today / B skip any second run that day
- decision: orchestrator, 2026-11-09: A. B would block manual runs and reverse a spec'd scenario.
- landed: .github/workflows/tracker.yml (`inputs.source`, `run-name`); backend/app/routers/internal.py (DISPATCH_BODY); specs/tracker-dispatch#Scenario: Marked as the cron's run; specs/report-publishing#Scenario: Manual run is never skipped; backend/tests/test_tracker_dispatch.py::test_dispatches_once_a_day

## D6 Reviewer should-fixes on the retry
- class: cheap
- source: reviewer
- status: resolved
- question: (1) httpx timeouts are per phase, so the real worst case is ~85 s, not 45 s, and the spec says "under a minute". (2) attempts += 1 (L127) is committed only at L131; if the function dies mid-retry the second dispatch isn't recorded. (3) The "Token expired" scenario can't happen as written: an expired token also 401s the runs list, so there's no retry; test_a_failed_day_can_be_claimed_again mocks the list as 200. (4) docs/deployment.md:41 doesn't mention the retry. (5) db.get_one (L113) keeps a transaction open through the sleep and HTTP calls.
- options: A fix all five / B leave them
- decision: orchestrator, 2026-11-09: A. (1) bound each call's total time (or make the spec's number honest) so the worst case is known and < 60 s; (2) commit attempts before the second dispatch; (3) reword the scenario and fix the test to match real behaviour; (4) update docs/deployment.md; (5) don't hold a transaction across the sleep/HTTP calls.
- landed: (1) backend/app/routers/internal.py (_timeout, DISPATCH_READ/RUNS_READ/RETRY_READ: read 10/5/20 s, connect/write/pool 2 s, worst case 58 s), specs/tracker-dispatch#Requirement: Retry a failed dispatch once, test_a_timeout_is_retried_once; (2)+(5) internal.py (tracker_dispatch: row updates via `update`, attempts committed before the retry, no ORM load across the calls), specs/tracker-dispatch#Scenario: The retry is counted before it goes out, test_no_transaction_is_held_and_the_retry_is_counted_first; (3) specs/tracker-dispatch#Scenario: Token expired, test_a_failed_day_can_be_claimed_again; (4) docs/deployment.md steps 4-6

## D8 Guard details: which cron run goes on, where the check lives, when GitHub can't be asked
- class: cheap
- source: implementer, D5/D7
- status: resolved
- question: (a) Two cron runs created seconds apart could each see the other and both skip. Which one goes on? (b) A step with an `if` on every later step, or a separate job? (c) The guard can't list the runs (API error): run or not?
- options: (a) A skip only when an earlier cron run (lower `run_number`) exists today / B skip when any other exists. (b) A separate `guard` job, `run` needs it / B a step. (c) A fail the guard, nothing runs / B run anyway
- built: (a) A: run numbers only grow, so exactly one of any set of same-day cron runs works; B could skip both. (b) A: one `if` on the job instead of eight; the guard job alone gets `actions: read`, the `run` job keeps `contents: read`; costs one extra runner start (seconds). (c) A, following D4 (confirmed by Kilian): never risk a second paid run on an unconfirmed check. That cron day is then missed unless someone starts a manual run.
- decision: implementer, 2026-11-09: (a) A, (b) A, (c) A
- landed: .github/workflows/tracker.yml (guard job); specs/report-publishing#Requirement: Daily scheduled run

Constraints: keep the whole cron request well inside the function timeout. CI tests fake GitHub, with no network: cover a timeout followed by a successful retry, a timeout where a run already exists (no second dispatch), and a timeout then a failed retry (row `failed`, attempts=2). Update openspec/specs/tracker-dispatch/spec.md with a requirement and scenarios for the retry. If this needs a migration, stop and log it as `expensive`.
