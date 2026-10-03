# Spec Delta

## Purpose

Defines the internship tracker's use case on top of the general agent orchestration: its three agents, the fixed order of its stages, and how the stages degrade when a budget or provider runs out.

## ADDED Requirements

### Requirement: Internship use case
With `use_case: internships` and the `scout`, `curator` and `editor` agent profiles in policy, `python -m tracker run` SHALL run the internship pipeline. Policy validation SHALL fail when any of those three profiles is missing.

#### Scenario: Missing profile
- **WHEN** `use_case: internships` is set, but `agents` has no `curator`
- **THEN** validation fails before any network call, naming `agents.curator`

### Requirement: Fixed stage order
The pipeline SHALL run, in this order: Scout (agent `scout`), Collect (code, required), Curate (agent `curator`), Liveness (code), Rank (code, required), Edit (agent `editor`), Report (code, required). The Scout, Curate and Edit stages MAY be disabled through their profile's `enabled`.

#### Scenario: Scout disabled
- **WHEN** `agents.scout.enabled` is false
- **THEN** the run starts at Collect with the existing watchlist, and the report notes that discovery was skipped

### Requirement: Agent privileges for this use case
The default profiles SHALL give:
- **Scout**: `search_web`, `fetch_article` and `propose_source`.
- **Curator**: `get_posting`, `fetch_posting_detail`, `save_record`, `mark_same` and `flag_unclear`, with `fetch_hosts` limited to the job-board posting hosts and the watchlist's domains.
- **Editor**: `get_opportunities` and `finish`.

The Curator and Editor SHALL NOT have `search_web` or `propose_source`.

#### Scenario: Committed profiles
- **WHEN** the committed `config.yaml` is loaded
- **THEN** the Curator and Editor profiles contain no search or source-proposal tool, and the Curator has a `fetch_hosts` list

### Requirement: Degraded runs still report
When the model provider fails terminally during Curate, the run SHALL skip Curate's remaining work and Edit, still run Liveness, Rank and Report from the existing records, and mark the report partial, naming the failure. When Collect cannot read any source and state has no earlier opportunities, the run SHALL fail with exit code `3` and a report saying no source was readable.

#### Scenario: Daily quota during Curate
- **WHEN** Groq returns a daily-quota 429 during Curate
- **THEN** Liveness, Rank and Report run, the report is partial and names the quota, and the command exits `2`

#### Scenario: Everything offline on the first run
- **WHEN** the network is cut and state is empty
- **THEN** the command exits `3`, and the report says no source could be read
