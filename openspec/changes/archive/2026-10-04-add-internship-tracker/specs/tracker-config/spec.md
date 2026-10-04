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

## ADDED Requirements

### Requirement: Model names are checked at startup
Before the first stage, `python -m tracker run` SHALL ask each model provider the policy uses for its model list, once per provider, and exit `1` naming every model the policy uses that is not in the list. When the list cannot be fetched (network failure, rejected key, an unexpected answer), the check SHALL be skipped, so the run's own failure handling deals with the provider.

#### Scenario: Retired model
- **WHEN** an agent profile names a model the provider no longer offers
- **THEN** the command exits `1` with a message naming the provider and model, before any model call

#### Scenario: Provider unreachable at startup
- **WHEN** the model list cannot be fetched because the network is down
- **THEN** the run starts, and its model calls fail and are retried as for any transient failure
