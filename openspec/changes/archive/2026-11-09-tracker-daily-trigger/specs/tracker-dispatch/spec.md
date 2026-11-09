## ADDED Requirements

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
The claiming call SHALL send `POST https://api.github.com/repos/Kildrese/mobile-systems-assignment/actions/workflows/tracker.yml/dispatches` with body `{"ref": "master"}` and `Authorization: Bearer <GITHUB_DISPATCH_TOKEN>`, with a timeout of at most 10 seconds. On `204` it SHALL mark the date `dispatched` and answer `202` with status `dispatched`. On any other answer, a timeout, or a missing `GITHUB_DISPATCH_TOKEN`, it SHALL mark the date `failed` with GitHub's status and message (never the token), log the error, and answer `502`.

#### Scenario: GitHub accepts
- **WHEN** GitHub answers `204`
- **THEN** the date's row is `dispatched` and the response is `202`

#### Scenario: Token expired
- **WHEN** GitHub answers `401`
- **THEN** the date's row is `failed` with `401` and GitHub's message, and the response is `502`

#### Scenario: Token not configured
- **WHEN** `GITHUB_DISPATCH_TOKEN` is not set
- **THEN** GitHub is not called, the date's row is `failed`, and the response is `502`
