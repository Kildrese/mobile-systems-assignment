# Spec Delta

## ADDED Requirements

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
- `skipped`: it was already seen (served from state, a `304`, or a posting already curated);
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
- **WHEN** Collect keeps a posting that was curated in an earlier run
- **THEN** a `skipped` row of kind `posting` is logged, and a posting first seen in this run gets a `fetched` row

#### Scenario: Budget refusal
- **WHEN** a fetch is refused because `max_fetches` is reached
- **THEN** no row is logged
