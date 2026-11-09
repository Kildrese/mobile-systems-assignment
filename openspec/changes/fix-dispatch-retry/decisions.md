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
- status: resolved
- question: The run check itself fails (timeout, 401). Retry anyway or not?
- options: A don't retry, mark `failed` with a note / B retry blindly
- built: A, following D2's purpose: never risk a second paid run on an unconfirmed check. The day stays `failed` (the error says why) and is missed unless someone starts a run from the Actions tab.
- decision: implementer, 2026-11-09: A
- landed: backend/app/routers/internal.py (tracker_dispatch); specs/tracker-dispatch#Scenario: Runs can't be listed; backend/tests/test_tracker_dispatch.py::test_when_the_runs_cannot_be_listed_it_does_not_retry

Constraints: keep the whole cron request well inside the function timeout. CI tests fake GitHub, with no network: cover a timeout followed by a successful retry, a timeout where a run already exists (no second dispatch), and a timeout then a failed retry (row `failed`, attempts=2). Update openspec/specs/tracker-dispatch/spec.md with a requirement and scenarios for the retry. If this needs a migration, stop and log it as `expensive`.
