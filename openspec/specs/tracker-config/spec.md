# tracker-config Specification

## Purpose
The tracker policy in `config.yaml` (topic, K, model, providers, limits, retry, fetch rules, instructions), validated in full before any network call and frozen for the run, with API keys read only from the environment.
## Requirements
### Requirement: Policy file
The tracker SHALL read its policy from a YAML file: `config.yaml` at the repository root by default, or the path given with `--config`. The file SHALL define `topic`, `k`, `model` (provider, model name, per-call output token cap, optional sampling and reasoning-effort settings), `instructions`, `limits` and `fetch` (allowed schemes, allowed hosts, timeout, size cap).

#### Scenario: Default location
- **WHEN** a user runs the tracker from `backend/` without `--config`
- **THEN** it loads `config.yaml` from the repository root

#### Scenario: Explicit path
- **WHEN** a user passes `--config path/to/other.yaml`
- **THEN** the tracker loads that file and ignores the root `config.yaml`

### Requirement: Limits are declared in policy
`limits` SHALL contain `max_steps` (model calls per run), `max_fetches`, `max_searches`, `max_tokens` (total prompt plus completion tokens per run), `max_cost_usd` and `max_wall_seconds`. Every limit SHALL be a positive number. A missing limit SHALL be a validation error, never treated as unlimited.

#### Scenario: Missing limit
- **WHEN** `config.yaml` omits `limits.max_fetches`
- **THEN** the tracker exits before any network call with a message naming `limits.max_fetches`

### Requirement: Policy is validated before any call
The tracker SHALL validate the whole policy before its first network request. It SHALL reject the policy when: `k` is outside 3 to 10; a tool name is unknown; `search_web`, `fetch_article` or `finish` is disabled; a scheme other than `http` or `https` is allowed; or a value has the wrong type. It SHALL exit with a non-zero status and a message naming each invalid field.

#### Scenario: K out of range
- **WHEN** `config.yaml` sets `k: 12`
- **THEN** the tracker exits with a non-zero status and a message saying `k` must be between 3 and 10, and makes no network request

#### Scenario: Policy cannot add tools
- **WHEN** `config.yaml` has a `tools` key
- **THEN** validation fails: the three tools are fixed in code, not set by policy

#### Scenario: Unsafe scheme in policy
- **WHEN** `fetch.allowed_schemes` contains `file`
- **THEN** validation fails, since only `http` and `https` may be allowed

### Requirement: Policy is fixed for the run
The tracker SHALL load the policy once at the start of a run, and nothing during the run SHALL change it. In particular, model output and retrieved text SHALL NOT change it.

#### Scenario: Config edited mid-run
- **WHEN** `config.yaml` is edited while a run is in progress
- **THEN** the run continues with the policy it loaded at start

### Requirement: Secrets come from the environment
API keys SHALL be read only from environment variables (`GROQ_API_KEY`, or the variable the model's provider entry names, and `TAVILY_API_KEY`), loading `backend/.env` when present. `config.yaml` SHALL NOT contain keys. `backend/.env.example` SHALL list each key variable with an empty value, and `.env` files SHALL stay git-ignored.

#### Scenario: Missing key
- **WHEN** a run starts with `TAVILY_API_KEY` unset
- **THEN** the tracker exits before any network call with a message naming `TAVILY_API_KEY` and pointing to `backend/.env.example`

#### Scenario: Example env lists keys
- **WHEN** a developer opens `backend/.env.example`
- **THEN** it contains `GROQ_API_KEY=` and `TAVILY_API_KEY=` with no values

