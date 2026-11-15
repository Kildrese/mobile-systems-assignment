# Spec Delta

## RENAMED Requirements

- FROM: `### Requirement: The API cannot start the tracker`
- TO: `### Requirement: No user can start the tracker`

## MODIFIED Requirements

### Requirement: No user can start the tracker
The API SHALL expose no route through which a user, signed in or not, can start, re-run or change a tracker run or its published data. The only route that can start a run SHALL be the cron-only dispatch route (`tracker-dispatch`), which answers `404` to any request without the cron secret and is not in the OpenAPI document.

#### Scenario: Write attempt
- **WHEN** a signed-in user sends `POST`, `PUT`, `PATCH` or `DELETE` to any `/api/internships` path
- **THEN** the response is `405` and nothing runs

#### Scenario: User calls the dispatch route
- **WHEN** a signed-in user calls `/api/internal/tracker-dispatch` with their session token
- **THEN** the response is `404` and nothing runs

#### Scenario: Documented routes
- **WHEN** the OpenAPI document is read
- **THEN** its only internship paths are these, each with `GET` only, and it has no `/api/internal` path:
  - `/api/internships/latest`
  - `/api/internships/runs`
  - `/api/internships/runs/{id}`
  - `/api/internships/runs/{id}/articles`
  - `/api/internships/runs/{id}/report.md`
