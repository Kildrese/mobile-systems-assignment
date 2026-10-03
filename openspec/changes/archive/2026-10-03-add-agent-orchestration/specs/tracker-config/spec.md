# Spec Delta

## MODIFIED Requirements

### Requirement: Policy file
The tracker SHALL read its policy from a YAML file: `config.yaml` at the repository root by default, or the path given with `--config`. The file SHALL define `topic`, `k`, `model` (provider, model name, per-call output token cap, optional sampling and reasoning-effort settings), `instructions`, `limits` and `fetch` (allowed schemes, allowed hosts, timeout, size cap). It MAY also define `agents` (named agent profiles) and `use_case` (the name of a use case built into the tracker); both are specified by the agent-orchestration capability.

#### Scenario: Default location
- **WHEN** a user runs the tracker from `backend/` without `--config`
- **THEN** it loads `config.yaml` from the repository root

#### Scenario: Explicit path
- **WHEN** a user passes `--config path/to/other.yaml`
- **THEN** the tracker loads that file and ignores the root `config.yaml`

### Requirement: Policy is validated before any call
The tracker SHALL validate the whole policy before its first network request. It SHALL reject the policy when: `k` is outside 3 to 10; a tool name is unknown (including in an agent profile, which may only select tools registered in code); `search_web`, `fetch_article` or `finish` is disabled; a scheme other than `http` or `https` is allowed; or a value has the wrong type. It SHALL exit with a non-zero status and a message naming each invalid field.

#### Scenario: K out of range
- **WHEN** `config.yaml` sets `k: 12`
- **THEN** the tracker exits with a non-zero status and a message saying `k` must be between 3 and 10, and makes no network request

#### Scenario: Policy cannot add tools
- **WHEN** `config.yaml` has a top-level `tools` key
- **THEN** validation fails: tools are registered in code, not set by policy

#### Scenario: Agent profile selects only registered tools
- **WHEN** `agents.<name>.tools` lists a name that neither the core nor the configured use case registers in code
- **THEN** validation fails, naming `agents.<name>.tools` and the unknown tool

#### Scenario: Unsafe scheme in policy
- **WHEN** `fetch.allowed_schemes` contains `file`
- **THEN** validation fails, since only `http` and `https` may be allowed
