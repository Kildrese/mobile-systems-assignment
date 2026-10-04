# Spec Delta

## MODIFIED Requirements

### Requirement: Daily scheduled run
The tracker SHALL run once a day from a scheduled GitHub Actions workflow at 09:00 UTC, and MAY be started manually from the Actions tab by repository writers. At most one run SHALL be in progress at a time. The job's timeout SHALL exceed the policy's `limits.max_wall_seconds` by enough for setup, saving state and publishing (at least 5 minutes), so a run is never cut off by the job before its own wall-clock budget ends. The run's SQLite state SHALL be restored before the run and saved after it, so each run continues from the previous one.

#### Scenario: Scheduled run
- **WHEN** 09:00 UTC passes
- **THEN** the workflow runs `python -m tracker run` with the state from the previous run, then publishes the result

#### Scenario: Nothing ran
- **WHEN** the tracker exits `1` (invalid policy, missing key or locked state)
- **THEN** the job fails and nothing is published

#### Scenario: Partial run
- **WHEN** the tracker exits `2` or `3`
- **THEN** its report is still published with status `partial` or `failed`

#### Scenario: Run uses its full wall time
- **WHEN** a run takes its full `max_wall_seconds`
- **THEN** the job still saves the state and publishes the report before its timeout
