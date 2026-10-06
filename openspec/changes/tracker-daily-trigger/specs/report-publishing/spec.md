# Spec Delta

## MODIFIED Requirements

### Requirement: Daily scheduled run
The tracker SHALL run once a day at 09:17 UTC. An external cron service SHALL start it by calling GitHub's `workflow_dispatch` REST endpoint for `tracker.yml` on `master`, authenticated with a fine-grained token limited to this repository and to Actions read and write. The workflow SHALL NOT have a `schedule` trigger, so GitHub's scheduler can't start a second run on the same day. Repository writers MAY also start a run manually from the Actions tab. The cron service SHALL notify the repository owner when a dispatch call doesn't return `204`. At most one run SHALL be in progress at a time. The job's timeout SHALL exceed the policy's `limits.max_wall_seconds` by enough for setup, saving state and publishing (at least 5 minutes), so a run is never cut off by the job before its own wall-clock budget ends. The run's SQLite state SHALL be restored before the run and saved after it, so each run continues from the previous one.

#### Scenario: Daily run
- **WHEN** 09:17 UTC passes and the cron service calls the dispatch endpoint
- **THEN** GitHub answers `204` and the workflow runs `python -m tracker run` with the state from the previous run, then publishes the result

#### Scenario: GitHub's scheduler can't add a run
- **WHEN** the workflow file on `master` is read
- **THEN** its only trigger is `workflow_dispatch`

#### Scenario: Dispatch fails
- **WHEN** the dispatch call answers anything other than `204` (for example `401` after the token expired)
- **THEN** no run starts and the cron service emails the repository owner

#### Scenario: Manual run while the daily run is in progress
- **WHEN** a writer starts a run while the daily run is still in progress
- **THEN** the second run waits for the first to finish and continues from its state

#### Scenario: Nothing ran
- **WHEN** the tracker exits `1` (invalid policy, missing key or locked state)
- **THEN** the job fails and nothing is published

#### Scenario: Partial run
- **WHEN** the tracker exits `2` or `3`
- **THEN** its report is still published with status `partial` or `failed`

#### Scenario: Run uses its full wall time
- **WHEN** a run takes its full `max_wall_seconds`
- **THEN** the job still saves the state and publishes the report before its timeout
