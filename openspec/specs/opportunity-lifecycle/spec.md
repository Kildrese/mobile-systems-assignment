# opportunity-lifecycle Specification

## Purpose
Open, closed and unknown status for each opportunity, the board and page liveness checks, and first-seen and last-seen tracking across runs.
## Requirements
### Requirement: Lifecycle fields
Each opportunity SHALL record `first_seen_run`, `status` (`open` or `closed`), `closed_run`, `checked_run` (the last run whose boards confirmed it) and `status_evidence` (what the decision was based on). A new opportunity SHALL start as `open`, with `first_seen_run` set to the current run.

#### Scenario: New opportunity
- **WHEN** an opportunity is created during run R
- **THEN** its `first_seen_run` is R, and its status is `open`

### Requirement: Closing from job boards
Liveness SHALL mark an opportunity `closed` when every board it is listed on was read successfully in this run (including a `304`) and none lists the job any more. When a board was `unreadable`, the status SHALL stay unchanged and `status_evidence` SHALL say the board was not readable. An opportunity that is already closed SHALL keep the run it closed in. Liveness SHALL NOT call a model or make requests: Collect has read the boards.

#### Scenario: Posting taken down
- **WHEN** an open opportunity's job id is missing from a board read successfully in run R
- **THEN** its status becomes `closed`, `closed_run` is R, and the evidence names the board read

#### Scenario: Board unreachable
- **WHEN** the board cannot be read in run R
- **THEN** the opportunity's status does not change, and the report counts it as still open with a note that it could not be checked

#### Scenario: Closed, then its board is unreadable
- **WHEN** an opportunity closed in run R, and its board cannot be read in run R+1
- **THEN** its `closed_run` stays R, so it is listed under Dropped as closed only in run R

### Requirement: Reopening
A `closed` opportunity SHALL become `open` again when a later run sees it listed. Its `first_seen_run` stays the same, so it is not reported as new.

#### Scenario: Reposted
- **WHEN** a closed opportunity's job id reappears on its board
- **THEN** its status returns to `open`, and it appears under Still in top K or Also open, not under New

