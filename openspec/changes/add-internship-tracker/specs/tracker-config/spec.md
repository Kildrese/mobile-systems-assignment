# Spec Delta

## MODIFIED Requirements

### Requirement: Policy file
The tracker SHALL read its policy from a YAML file: `config.yaml` at the repository root by default, or the path given with `--config`. The file SHALL define `topic`, `k`, `model` (provider, model name, per-call output token cap, optional sampling and reasoning-effort settings), `instructions`, `limits` and `fetch` (allowed schemes, allowed hosts, timeout, size cap). It MAY also define `agents` (named agent profiles) and `use_case` (the name of a use case built into the tracker); both are specified by the agent-orchestration capability. It MAY also define `options`, settings for the configured use case, which that use case validates before any network call.

#### Scenario: Default location
- **WHEN** a user runs the tracker from `backend/` without `--config`
- **THEN** it loads `config.yaml` from the repository root

#### Scenario: Explicit path
- **WHEN** a user passes `--config path/to/other.yaml`
- **THEN** the tracker loads that file and ignores the root `config.yaml`

#### Scenario: Invalid use-case options
- **WHEN** `config.yaml` sets `use_case: internships` and `options.filters` has an unknown key
- **THEN** the run stops before any network call with a message naming `options`
