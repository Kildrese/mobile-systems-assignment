## MODIFIED Requirements

### Requirement: Daily scheduled run
The tracker SHALL run once a day from a scheduled GitHub Actions workflow at 09:00 UTC, and MAY be started manually from the Actions tab by repository writers. At most one run SHALL be in progress at a time. The run's SQLite state SHALL be restored before the run and saved after it, so each run continues from the previous one. After publishing, the workflow SHALL run `python -m app.draft_new`, and a failure of that step SHALL NOT fail the job.

#### Scenario: Scheduled run
- **WHEN** 09:00 UTC passes
- **THEN** the workflow runs `python -m tracker run` with the state from the previous run, publishes the result, then drafts applications for new top-K offers

#### Scenario: Nothing ran
- **WHEN** the tracker exits `1` (invalid policy, missing key or locked state)
- **THEN** the job fails and nothing is published or drafted

#### Scenario: Partial run
- **WHEN** the tracker exits `2` or `3`
- **THEN** its report is still published with status `partial` or `failed`

#### Scenario: Drafting fails
- **WHEN** `python -m app.draft_new` exits non-zero
- **THEN** the job still succeeds, and the step's log names the failure
