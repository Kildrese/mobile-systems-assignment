# Spec Delta

## MODIFIED Requirements

### Requirement: Fixed stage order
The pipeline SHALL run, in this order: Scout (agent `scout`), Collect (code, required), Curate (agent `curator`), Liveness (code), Assess (agent `assessor`, only with an `assessor` profile and `options.profile`), Rank (code, required), Edit (agent `editor`), Report (code, required). The Scout, Curate, Assess and Edit stages MAY be disabled through their profile's `enabled`.

#### Scenario: Scout disabled
- **WHEN** `agents.scout.enabled` is false
- **THEN** the run starts at Collect with the existing watchlist, and the report notes that discovery was skipped

#### Scenario: Assess before Rank
- **WHEN** the policy has an `assessor` profile and `options.profile`
- **THEN** the trace's stage list is scout, collect, curate, liveness, assess, rank, edit

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
