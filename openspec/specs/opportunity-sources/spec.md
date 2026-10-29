# opportunity-sources Specification

## Purpose
The watchlist of job boards, sources proposed by the Scout and validated in code, the Greenhouse, Lever and Ashby collectors with conditional requests, and the title and location pre-filter.
## Requirements
### Requirement: Watchlist
State SHALL hold a watchlist of sources. Each source has a company name, a kind (`greenhouse`, `lever`, `ashby` or `simplify`), a board identifier, who added it (`config` or `scout`), and the run that added it. A `greenhouse`, `lever` or `ashby` source is one company's public job board. A `simplify` source is a SimplifyJobs internship list, and its board identifier is the GitHub repository (`owner/repo`). Sources listed under `options.watchlist` in `config.yaml`, or in the watchlist shipped with the use case when that is not set, SHALL be loaded into state at the start of every run. The shipped watchlist SHALL include the `simplify` source `SimplifyJobs/Summer2027-Internships`. A posting MAY carry its own company. When it does, that company SHALL be used for the posting everywhere after Collect (same-company candidates, `mark_same`, records, report) in place of the source's.

#### Scenario: Seeded from config
- **WHEN** `config.yaml` lists a Greenhouse board for a company
- **THEN** after the run starts, state holds that source with `added_by: config`

#### Scenario: Company from the listing
- **WHEN** a Simplify listing for company "Acme" is collected
- **THEN** the Curator sees its posting as an Acme posting, with Acme's existing opportunities as same-company candidates

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
Collect SHALL read each source through its public JSON endpoint, without keys and without a model: the Greenhouse, Lever and Ashby board APIs, and for a `simplify` source `https://raw.githubusercontent.com/<owner>/<repo>/dev/.github/scripts/listings.json`. It SHALL produce one raw posting per job, with the job's id, title, location, URL and description text. Each request SHALL go through the core fetch guardrails and the transient/terminal failure handling. A failed source SHALL be recorded as `unreadable` for this run and SHALL NOT stop the other sources. Retries SHALL honor a `Retry-After` up to `retry.max_wait_seconds`, and no request or wait SHALL go past the run's `max_wall_seconds`. When no source is readable, Collect SHALL be `failed` if state holds no opportunities yet, and `partial` otherwise. A source the Scout added that has never been read successfully SHALL be deactivated when it fails for a reason that does not pass by itself (HTTP 404 or 410, too large, not a supported content type, or a body the parser rejects); it is then not read again and cannot be proposed again. Config sources, and sources that were read successfully before, SHALL never be deactivated. Responses up to `options.board_max_bytes` (default 20 MB) SHALL be accepted. When a `simplify` source is configured, `fetch.allowed_hosts` SHALL allow `raw.githubusercontent.com`, or the policy is rejected before any network call.

#### Scenario: One board down
- **WHEN** one Greenhouse board returns 503 after the capped retries, and the others succeed
- **THEN** the others' postings are collected, the failed source is marked `unreadable` for this run, and Collect completes

#### Scenario: Scout added a board that cannot be read
- **WHEN** a board the Scout proposed is larger than `options.board_max_bytes` on its first read
- **THEN** it is marked `unreadable`, deactivated, and not requested in later runs

#### Scenario: Simplify list unchanged
- **WHEN** the Simplify list returns `304 Not Modified`
- **THEN** its stored listings are parsed again, no body is downloaded, and the source counts as read

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

### Requirement: Simplify listings
Code SHALL keep a Simplify listing only if it is `active` and `is_visible`, its `terms` include `Summer 2027` or name no term (empty or `N/A`), and its `date_posted` is within `options.simplify_max_age_days` (default 14) of the run's start. Listings dropped here SHALL NOT be stored. The title and location pre-filter SHALL apply to the kept listings as to any posting. A kept listing's posting SHALL have the listing's `id` as its id, its `company_name` as its company, its locations joined by `; ` as its location, and as its text one line each for company, title, locations, terms, category, degrees, posted date and sponsorship, leaving out lines with no value and a sponsorship of `Other`. The Scout SHALL NOT be able to propose a `simplify` source: `propose_source` SHALL reject it with reason `unknown_kind`.

#### Scenario: Old and inactive listings dropped
- **WHEN** the list holds an active Summer 2027 listing posted 3 days ago, one posted 40 days ago, and an inactive one posted yesterday
- **THEN** only the first is stored as a posting

#### Scenario: Other term dropped
- **WHEN** an active listing posted yesterday has terms `Fall 2026`
- **THEN** it is not stored

#### Scenario: Sponsorship in the text
- **WHEN** a kept listing has sponsorship `Does Not Offer Sponsorship`
- **THEN** its posting text contains the line `Sponsorship: Does Not Offer Sponsorship`, so the Curator can quote it

#### Scenario: Scout proposes the aggregator
- **WHEN** the Scout calls `propose_source` with kind `simplify`
- **THEN** the proposal is rejected with reason `unknown_kind` and the watchlist is unchanged

