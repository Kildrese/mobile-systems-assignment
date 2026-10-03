# Spec Delta

## Purpose

Tracks each opportunity across runs as open, closed or unknown, decided by code from what the sources say, so the report can accumulate everything still open and list what closed.

## ADDED Requirements

### Requirement: Lifecycle fields
Each opportunity SHALL record `first_seen_run`, `last_seen_open_run`, `status` (`open`, `closed`, `unknown`), `closed_run` and `status_evidence` (what the decision was based on). A new opportunity SHALL start as `open`, with `first_seen_run` set to the current run.

#### Scenario: New opportunity
- **WHEN** an opportunity is created during run R
- **THEN** its `first_seen_run` and `last_seen_open_run` are R, and its status is `open`

### Requirement: Closing from job boards
For an opportunity from a job board, Liveness SHALL mark it `closed` when its board was read successfully in this run (including a `304`) and the job id is absent. When the board was `unreadable`, the status SHALL stay unchanged and `status_evidence` SHALL say the board was not readable. Liveness SHALL NOT call a model.

#### Scenario: Posting taken down
- **WHEN** an open opportunity's job id is missing from a board read successfully in run R
- **THEN** its status becomes `closed`, `closed_run` is R, and the evidence names the board read

#### Scenario: Board unreachable
- **WHEN** the board cannot be read in run R
- **THEN** the opportunity's status does not change, and the report counts it as still open with a note that it could not be checked

### Requirement: Closing from pages
For an opportunity whose only source is a page, Liveness SHALL send a conditional request through the fetch guardrails. A `404` or `410`, or page text matching a `lifecycle.closed_patterns` entry (for example "no longer accepting applications"), SHALL mark it `closed`. Timeouts and other failures SHALL set the status to `unknown`, never `closed`.

#### Scenario: Closing wording
- **WHEN** a page now reads "This position is no longer accepting applications"
- **THEN** the opportunity is `closed`, and the evidence quotes the matched text

#### Scenario: Timeout
- **WHEN** the page check times out after the capped retries
- **THEN** the status becomes `unknown`, not `closed`

### Requirement: Reopening
An opportunity that is `closed` or `unknown` SHALL become `open` again when a later run sees it listed or reachable. Its `first_seen_run` stays the same, so it is not reported as new.

#### Scenario: Reposted
- **WHEN** a closed opportunity's job id reappears on its board
- **THEN** its status returns to `open`, and it appears under Still open, not under New
