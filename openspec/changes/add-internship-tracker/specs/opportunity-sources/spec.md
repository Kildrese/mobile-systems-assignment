# Spec Delta

## Purpose

Defines where opportunities come from: a watchlist of companies and their public job boards, which the Scout agent can extend, read each run by collectors written in code that cost no model tokens.

## ADDED Requirements

### Requirement: Watchlist
State SHALL hold a watchlist of sources. Each source is a public job board: a company name, a kind (`greenhouse`, `lever` or `ashby`), a board identifier, who added it (`config` or `scout`), and the run that added it. Sources listed under `options.watchlist` in `config.yaml`, or in the watchlist shipped with the use case when that is not set, SHALL be loaded into state at the start of every run.

#### Scenario: Seeded from config
- **WHEN** `config.yaml` lists a Greenhouse board for a company
- **THEN** after the run starts, state holds that source with `added_by: config`

### Requirement: Scout proposes sources
The Scout agent SHALL have a `propose_source(company, kind, board, evidence_url)` tool. Code SHALL accept a proposal only if: the kind is `greenhouse`, `lever` or `ashby`; the board identifier matches that job board's format; `evidence_url` was returned by search or fetched in this run; and the source is not already on the watchlist. Any other kind, such as a careers page, SHALL be rejected: a page the Scout read could otherwise put itself on the watchlist for every run. Accepted proposals SHALL be added with `added_by: scout`. Each run SHALL accept at most `agents.scout.options.max_new_sources` proposals.

#### Scenario: Valid proposal
- **WHEN** the Scout proposes a Lever board for a company, citing a page it fetched in this run
- **THEN** the source is added to the watchlist, and Collect reads it in the same run

#### Scenario: Scout proposes a page
- **WHEN** the Scout proposes a careers page, for example one an injected page told it to add
- **THEN** the proposal is rejected with reason `unknown_kind` and the watchlist is unchanged

#### Scenario: Proposal citing an unseen page
- **WHEN** the Scout proposes a source with an `evidence_url` it never fetched or saw in search results
- **THEN** the proposal is rejected with reason `unseen_evidence`

### Requirement: Job-board collectors
Collect SHALL read each Greenhouse, Lever and Ashby source through its public JSON endpoint, without keys and without a model. It SHALL produce one raw posting per job, with the board's job id, title, location, URL and description text. Each request SHALL go through the core fetch guardrails and the transient/terminal failure handling. A failed source SHALL be recorded as `unreadable` for this run and SHALL NOT stop the other sources. Retries SHALL honor a `Retry-After` up to `retry.max_wait_seconds`, and no request or wait SHALL go past the run's `max_wall_seconds`. When no source is readable, Collect SHALL be `failed` if state holds no opportunities yet, and `partial` otherwise. A source the Scout added that has never been read successfully SHALL be deactivated when it fails for a reason that does not pass by itself (HTTP 404 or 410, too large, not a supported content type, or a body the parser rejects); it is then not read again and cannot be proposed again. Config sources, and sources that were read successfully before, SHALL never be deactivated.

#### Scenario: One board down
- **WHEN** one Greenhouse board returns 503 after the capped retries, and the others succeed
- **THEN** the others' postings are collected, the failed source is marked `unreadable` for this run, and Collect completes

#### Scenario: Scout added a board that cannot be read
- **WHEN** a board the Scout proposed is larger than `options.board_max_bytes` on its first read
- **THEN** it is marked `unreadable`, deactivated, and not requested in later runs

### Requirement: Conditional requests
Collect and Liveness SHALL store each response's `ETag` and `Last-Modified` and send `If-None-Match` / `If-Modified-Since` on later runs. A `304` SHALL reuse the stored postings for that source and count as a successful read.

#### Scenario: Network cut after an earlier run
- **WHEN** no source can be read and state holds opportunities from an earlier run
- **THEN** Collect is `partial`, nothing is closed, and the report lists the earlier opportunities as still open

#### Scenario: Unchanged board
- **WHEN** a board returns `304 Not Modified` on the second run
- **THEN** its stored postings are reused, no body is downloaded, and the trace records status `not_modified`

### Requirement: Pre-filter in code
Before curation, code SHALL keep only postings whose title matches a `filters.title_keywords` entry (for example intern, internship, co-op) and whose location matches a `filters.locations` entry (for example New York, NYC, Remote US). Postings with no location are kept, so the Curator can resolve them. Postings filtered out SHALL be counted in the trace but not stored as opportunities.

#### Scenario: Senior role filtered
- **WHEN** a board lists "Senior Backend Engineer" in New York and "Software Engineering Intern, Summer 2027" in New York
- **THEN** only the intern posting reaches Curate, and the trace counts one filtered posting
