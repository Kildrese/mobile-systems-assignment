# tracker-state Specification

## Purpose
SQLite state kept between runs (runs, fetched articles, searches, reported items), with canonical URLs, a lock that allows one run at a time, and schema versioning in `PRAGMA user_version`.
## Requirements
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

### Requirement: Fetches are logged per run
The tracker SHALL record, in a `fetch_log` table, one row for each document a run tried to read:
- a page fetched by `fetch_article` or `fetch_posting_detail`;
- a job board read by Collect;
- a posting kept by Collect's prefilter.

Each row SHALL hold:
- the run id;
- the stage (`scout`, `collect`, `curate` or the single-agent loop);
- the kind (`page`, `board` or `posting`);
- the URL as requested, cut to 2,048 characters;
- the title, cut to 300 characters, or empty when not fetched;
- the time;
- the status (`fetched`, `skipped`, `rejected` or `failed`);
- the reason, for `rejected` and `failed`.

The status is:
- `fetched`: the document was downloaded in this run;
- `skipped`: it was already seen (served from state, a `304`, or a posting first seen in an earlier run);
- `rejected`: a guardrail refused it (scheme, credentials, host, address, size, content type or redirects);
- `failed`: the request was tried and failed (timeout, connection error, HTTP error).

A fetch refused by a budget SHALL NOT be logged.

#### Scenario: Guardrail rejection
- **WHEN** the Scout calls `fetch_article` with `http://169.254.169.254/latest/meta-data/`
- **THEN** a `rejected` row with reason `blocked_address` and that URL is logged, and no connection is made

#### Scenario: Article already in state
- **WHEN** a run fetches a URL whose canonical form is already in `articles`
- **THEN** a `skipped` row with the stored title is logged

#### Scenario: Unchanged board
- **WHEN** a board answers `304 Not Modified`
- **THEN** a `skipped` row of kind `board` is logged

#### Scenario: Known posting
- **WHEN** Collect keeps a posting that was first seen in an earlier run
- **THEN** a `skipped` row of kind `posting` is logged, and a posting first seen in this run gets a `fetched` row

#### Scenario: Budget refusal
- **WHEN** a fetch is refused because `max_fetches` is reached
- **THEN** no row is logged

