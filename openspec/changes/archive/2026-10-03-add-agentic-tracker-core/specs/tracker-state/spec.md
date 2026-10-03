# Spec Delta

## Purpose

Persists what the tracker has seen and reported between runs, in a local SQLite file, so later runs can skip known articles and compare their results with earlier ones.

## ADDED Requirements

### Requirement: State file
The tracker SHALL keep its state in one SQLite file, at the path set in policy (default `.tracker/state.sqlite` at the repository root). It SHALL create the file and its schema on first use. The file SHALL be git-ignored.

#### Scenario: First run
- **WHEN** a run starts and no state file exists
- **THEN** the file and its tables are created, and the run proceeds

#### Scenario: Git ignores state
- **WHEN** a developer runs `git status` after a run
- **THEN** the state file is not listed as untracked

### Requirement: Runs are recorded
Each run SHALL be recorded with its id, start and end time, topic, K, status (`complete`, `partial` or `failed`), stop reason and budget usage. A run that ends by a terminal failure or budget stop SHALL still be recorded with its status.

#### Scenario: Partial run recorded
- **WHEN** a run stops on its step budget
- **THEN** its record has status `partial` and stop reason `max_steps`

### Requirement: Articles are stored by canonical URL
Each fetched article SHALL be stored once under its canonical URL, together with original URL, title, extracted text, content hash, first-seen run and last-fetched time. Canonicalization SHALL lowercase scheme and host, drop the fragment, drop default ports, and remove common tracking parameters (`utm_*`, `gclid`, `fbclid`, `ref`).

#### Scenario: Tracking parameters
- **WHEN** `https://Example.com/news/1?utm_source=x#top` is fetched and later `https://example.com/news/1` is requested
- **THEN** the second request is served from state as the same article

### Requirement: Reported items are stored
The ranked items of each run's final report SHALL be stored with run id, rank, title, summary and source URLs, so a later run can compare its results against them.

#### Scenario: Items persisted
- **WHEN** a run finishes with five items
- **THEN** state holds five item rows for that run id, in rank order

### Requirement: Concurrent runs are refused
Only one run SHALL use a state file at a time. A second run started while one is active SHALL exit with a message saying another run holds the state file.

#### Scenario: Double start
- **WHEN** a user starts a run while another run on the same state file is in progress
- **THEN** the second run exits non-zero without changing state
