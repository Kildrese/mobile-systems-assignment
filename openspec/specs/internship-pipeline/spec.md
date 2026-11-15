# internship-pipeline Specification

## Purpose
The `internships` use case: its three agents (Scout, Curator, Editor) and their privileges, the fixed stage order, and how a run degrades when a budget or provider runs out.
## Requirements
### Requirement: Internship use case
With `use_case: internships` and the `scout`, `curator` and `editor` agent profiles in policy, `python -m tracker run` SHALL run the internship pipeline. Policy validation SHALL fail when any of those three profiles is missing.

#### Scenario: Missing profile
- **WHEN** `use_case: internships` is set, but `agents` has no `curator`
- **THEN** validation fails before any network call, naming `agents.curator`

### Requirement: Fixed stage order
The pipeline SHALL run, in this order: Scout (agent `scout`), Collect (code, required), Curate (agent `curator`), Liveness (code), Assess (agent `assessor`, only with an `assessor` profile and `options.profile`), Rank (code, required), Verify (remote verifier, only with a `verifier` section in policy), Edit (agent `editor`), Report (code, required). Verify SHALL rank again after storing verdicts, so Edit and Report see the final order. The Scout, Curate, Assess and Edit stages MAY be disabled through their profile's `enabled`, and Verify by leaving out `options.verifier`.

#### Scenario: Scout disabled
- **WHEN** `agents.scout.enabled` is false
- **THEN** the run starts at Collect with the existing watchlist, and the report notes that discovery was skipped

#### Scenario: Assess before Rank
- **WHEN** the policy has an `assessor` profile and `options.profile`
- **THEN** the trace's stage list is scout, collect, curate, liveness, assess, rank, verify, edit

#### Scenario: No verifier configured
- **WHEN** the policy has no `verifier` section
- **THEN** the run has no Verify stage, and every claim in the report is `unverified`

### Requirement: Agent privileges for this use case
The default profiles SHALL give:
- **Scout**: `search_web`, `fetch_article` and `propose_source`.
- **Curator**: `get_posting`, `fetch_posting_detail`, `save_record`, `mark_same` and `flag_unclear`, with `fetch_hosts` limited to the job-board posting hosts.
- **Editor**: `get_opportunities` and `finish`.
- **Assessor** (optional): `finish` only.

The Curator, Editor and Assessor SHALL NOT have `search_web` or `propose_source`.

#### Scenario: Committed profiles
- **WHEN** the committed `config.yaml` is loaded
- **THEN** the Curator, Editor and Assessor profiles contain no search or source-proposal tool, and the Curator has a `fetch_hosts` list

### Requirement: Degraded runs still report
When the model provider fails terminally during Curate, the run SHALL skip Curate's remaining work and Edit, still run Liveness, Rank and Report from the existing records, and mark the report partial, naming the failure. When the verifier fails, never answers after retries, or answers with a malformed response, the run SHALL continue with those claims `unverified`, mark the report partial, and name `verifier` as the failed service. When Collect cannot read any source and state has no earlier opportunities, the run SHALL fail with exit code `3` and a report saying no source was readable.

#### Scenario: Daily quota during Curate
- **WHEN** Groq returns a daily-quota 429 during Curate
- **THEN** Liveness, Rank and Report run, the report is partial and names the quota, and the command exits `2`

#### Scenario: Verifier down
- **WHEN** every `/verify` request fails with connection refused after its retries
- **THEN** Edit and Report run, the report is partial and names `verifier`, the claims are `unverified`, and the command exits `2`

#### Scenario: Everything offline on the first run
- **WHEN** the network is cut and state is empty
- **THEN** the command exits `3`, and the report says no source could be read

### Requirement: Scout stage outcome
The Scout's stage SHALL be `complete` when the Scout calls `finish`; when code has accepted `agents.scout.options.max_new_sources` proposals in the run, in which case code SHALL end the stage without another model call (reason `max_new_sources`); or when the Scout's step or token budget stops it after all of its `max_searches` have been used (reason `searches_spent`). It SHALL be `partial` when a step or token budget stops it with searches left, when the run's wall-clock budget stops it, or when a provider fails terminally. The reason SHALL appear in the stage's trace summary and in the report's stage table.

#### Scenario: Searches spent, then out of steps
- **WHEN** the Scout has used all its searches and then reaches `scout.max_steps` while reading results
- **THEN** the Scout's stage is `complete` with reason `searches_spent`, and the proposals it made are kept

#### Scenario: Out of steps with searches left
- **WHEN** the Scout reaches `scout.max_steps` having used 3 of 6 searches
- **THEN** the Scout's stage is `partial` with reason `scout.max_steps`

#### Scenario: Proposal cap reached
- **WHEN** code accepts the Scout's fifth proposal and `max_new_sources` is 5
- **THEN** the stage ends `complete` with reason `max_new_sources`, and no further model call is made for the Scout

#### Scenario: Wall clock
- **WHEN** the run's `max_wall_seconds` stops the Scout, whatever its search count
- **THEN** the Scout's stage is `partial` with reason `max_wall_seconds`

#### Scenario: Complete daily run
- **WHEN** the Scout ends `complete` by any of the rules above and every other stage is `complete`
- **THEN** the run is `complete` and the command exits `0`

### Requirement: Claims from records
The Verify stage SHALL turn each known field of a top-K opportunity (title, role type, term, locations, remote, compensation, deadline, work authorization) into one claim. The claim is a sentence made by code from a fixed template per field, using the field's value, the company and the title, for example "Acme's Software Engineering Intern posting lists pay of $55/hour." The claim's `source_url` SHALL be the opportunity's posting URL, and its `claim_id` SHALL be `<opportunity id>:<field>`. Claims SHALL NOT carry the Curator's quote, the summary or any page text. Unknown fields produce no claim.

#### Scenario: Unknown pay
- **WHEN** an opportunity's compensation is unknown
- **THEN** no compensation claim is sent

#### Scenario: Quote stays home
- **WHEN** claims are built for an opportunity whose work-authorization quote is stored
- **THEN** the claim's text holds the field's value, not the quote

### Requirement: Verify stage calls the verifier
The Verify stage SHALL send one `POST /verify` per top-K opportunity that has claims without a stored verdict for its current record hash. Each request gets a new `request_id`, the run's `run_id`, and the configured per-request `time_budget_ms` and budget. The client timeout SHALL be `time_budget_ms` plus `verifier.cold_start_ms`. Connection errors, timeouts and `503` SHALL be retried with exponential backoff and jitter, honoring `Retry-After`, up to `verifier.max_attempts`, resending the identical body with the same `request_id`. `400`, `401`, `409` and `500` SHALL NOT be retried. The stage SHALL validate every response against the response schema, including that each verdict's `claim_id` was sent in that request. An invalid response SHALL count as the verifier failing for that request, and none of its content SHALL be stored.

#### Scenario: Timeout then stored copy
- **WHEN** the first attempt times out and the retry returns the verifier's stored response
- **THEN** the verdicts are stored once, and the request's usage is charged once

#### Scenario: Unknown claim id
- **WHEN** a response contains a verdict for a `claim_id` that wasn't sent
- **THEN** the whole response is discarded, its claims stay `unverified`, and the run names `verifier` as failed

#### Scenario: Unauthorized
- **WHEN** the verifier answers `401`
- **THEN** the stage does not retry, and stops sending further requests in this run

### Requirement: Verifier budget share
`verifier.budget` SHALL set the per-request share, and `verifier.max_requests` the number of requests per run. The run's totals SHALL count each `request_id` once, with the `usage` it reported. A request that never got a valid answer SHALL be charged its full share. The stage SHALL NOT send a request whose full share would take the run past its total budget. Those claims stay `unverified`.

#### Scenario: Never answered
- **WHEN** a request times out on every attempt
- **THEN** the run's totals are charged that request's full `max_steps`, `max_fetches` and `max_tokens`

### Requirement: Verdicts are kept and reused
The tracker SHALL store each `supported` or `unsupported` verdict with its opportunity, field, evidence, run id and the hash of the record it checked. A claim SHALL be sent again only when the record's hash changes. `unreachable` verdicts SHALL be stored but retried on the next run. Claims without a stored verdict for the current hash are `unverified`.

#### Scenario: Unchanged record
- **WHEN** an opportunity in the top K was verified yesterday and its record is unchanged
- **THEN** no `/verify` request is sent for it today, and yesterday's verdicts are shown

