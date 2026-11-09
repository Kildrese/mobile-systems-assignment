# tracker-dispatch Specification

## Purpose
The internal route the daily Vercel Cron calls to start the tracker workflow through GitHub's `workflow_dispatch`, reachable only with `CRON_SECRET`, and claiming each UTC day at most once in `tracker_dispatches`.
## Requirements
### Requirement: Cron-only dispatch route
The backend SHALL serve `GET /api/internal/tracker-dispatch` for Vercel Cron. It SHALL accept a request only when its `Authorization` header is `Bearer <CRON_SECRET>`, compared in constant time. Every other request SHALL get `404` with the same body as an unknown path and SHALL NOT touch the database or GitHub: no header, a user's session token, a wrong secret, or `CRON_SECRET` not set. The route SHALL NOT appear in the OpenAPI document.

#### Scenario: Cron call
- **WHEN** a request carries `Authorization: Bearer <CRON_SECRET>`
- **THEN** the route goes on to claim the day

#### Scenario: Signed-in user
- **WHEN** a signed-in user calls the route with their session token
- **THEN** the response is `404` and nothing is dispatched

#### Scenario: Secret not configured
- **WHEN** `CRON_SECRET` is not set and a request carries `Authorization: Bearer ` with an empty or any value
- **THEN** the response is `404`

#### Scenario: Not documented
- **WHEN** the OpenAPI document is read
- **THEN** it has no `/api/internal` path

### Requirement: One dispatch per UTC day
A table `tracker_dispatches` SHALL hold at most one row per UTC date (the date is the primary key), with its status (`claimed`, `dispatched` or `failed`), when it was last claimed, the number of attempts, and the last error. Before calling GitHub, the route SHALL claim the current UTC date with a single atomic statement. It SHALL succeed only when no row exists for the date, when the row is `failed`, or when it is `claimed` and older than 5 minutes (a call that died mid-way). Only the call that claims the date SHALL call GitHub. Any other call SHALL answer `200` with status `already_dispatched` without calling GitHub.

#### Scenario: First call of the day
- **WHEN** the cron calls the route and the date has no row
- **THEN** a `claimed` row is inserted and GitHub is called once

#### Scenario: Duplicate call
- **WHEN** the cron calls the route again on a date whose row is `dispatched`
- **THEN** the response is `200` with status `already_dispatched` and GitHub is not called

#### Scenario: Two calls at once
- **WHEN** two authenticated calls arrive at the same moment on a date with no row
- **THEN** exactly one of them calls GitHub

#### Scenario: Retry after a failure
- **WHEN** a call arrives on a date whose row is `failed`
- **THEN** it claims the date again, increments the attempts and calls GitHub

#### Scenario: Stale claim
- **WHEN** a call arrives on a date whose row has been `claimed` for more than 5 minutes
- **THEN** it claims the date again and calls GitHub

### Requirement: Start the workflow on GitHub
The claiming call SHALL send `POST https://api.github.com/repos/Kildrese/mobile-systems-assignment/actions/workflows/tracker.yml/dispatches` with body `{"ref": "master", "inputs": {"source": "cron"}}` and `Authorization: Bearer <GITHUB_DISPATCH_TOKEN>`, with a read timeout of 10 seconds and 2 seconds for each other phase (connect, write, pool). On `204` it SHALL mark the date `dispatched` and answer `202` with status `dispatched`. When the dispatch and its one retry (next requirement) fail, or `GITHUB_DISPATCH_TOKEN` is missing, it SHALL mark the date `failed` with GitHub's status and message (never the token), log the error, and answer `502`.

#### Scenario: GitHub accepts
- **WHEN** GitHub answers `204`
- **THEN** the date's row is `dispatched` and the response is `202`

#### Scenario: Marked as the cron's run
- **WHEN** the route dispatches
- **THEN** the body carries the input `source: cron`, which names the run and lets the workflow's guard tell it from a manual run

#### Scenario: Token expired
- **WHEN** GitHub answers `401` to the dispatch, and so to the list of today's runs
- **THEN** the dispatch is not retried, the date's row is `failed` with 1 attempt, `401` and GitHub's message, and the response is `502`

#### Scenario: Token not configured
- **WHEN** `GITHUB_DISPATCH_TOKEN` is not set
- **THEN** GitHub is not called, the date's row is `failed`, and the response is `502`

### Requirement: Retry a failed dispatch once
When the dispatch fails (a timeout, a network error or any answer other than `204`) and `GITHUB_DISPATCH_TOKEN` is set, the same request SHALL wait 5 seconds and list the `workflow_dispatch` runs of `tracker.yml` created since 00:00 UTC that day (`GET .../actions/workflows/tracker.yml/runs`, read timeout 5 seconds). If one exists, a dispatch went through: the route SHALL mark the date `dispatched` and answer `202` without dispatching again. If none exists, it SHALL add one to the attempts and commit it, then dispatch once more with a read timeout of 20 seconds, then record the result as above. If the runs can't be listed, it SHALL NOT retry and SHALL mark the date `failed`. Every GitHub call SHALL limit connect, write and pool to 2 seconds each, so the request takes at most 58 seconds (16 + 5 + 11 + 26) and dispatches at most twice. No database transaction SHALL stay open across the wait or a GitHub call. No new cron or schedule is added. A dispatch GitHub accepted but didn't list yet can still be dispatched again; the workflow's guard (`report-publishing`, "Daily scheduled run") then skips the second run.

#### Scenario: Timeout, then the retry succeeds
- **WHEN** the dispatch times out, no run exists today, and the retry gets `204`
- **THEN** GitHub got two dispatches, the row is `dispatched` with 2 attempts, and the response is `202`

#### Scenario: Timeout, but the run started
- **WHEN** the dispatch times out and a `workflow_dispatch` run of `tracker.yml` already exists today
- **THEN** there is no second dispatch, the row is `dispatched` with 1 attempt, and the response is `202`

#### Scenario: Timeout, then the retry fails
- **WHEN** the dispatch times out, no run exists today, and the retry times out too
- **THEN** the row is `failed` with 2 attempts and the retry's error, and the response is `502`

#### Scenario: The retry is counted before it goes out
- **WHEN** the route dispatches again after a failure
- **THEN** the row already shows 2 attempts, and no transaction is open while either dispatch is in flight

#### Scenario: Runs can't be listed
- **WHEN** the dispatch times out and listing today's runs fails
- **THEN** there is no second dispatch, the row is `failed` with 1 attempt, and the response is `502`
