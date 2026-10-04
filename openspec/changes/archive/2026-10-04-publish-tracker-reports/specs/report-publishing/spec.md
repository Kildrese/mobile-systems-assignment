# Spec Delta

## ADDED Requirements

### Requirement: Daily scheduled run
The tracker SHALL run once a day from a scheduled GitHub Actions workflow at 09:00 UTC, and MAY be started manually from the Actions tab by repository writers. At most one run SHALL be in progress at a time. The run's SQLite state SHALL be restored before the run and saved after it, so each run continues from the previous one.

#### Scenario: Scheduled run
- **WHEN** 09:00 UTC passes
- **THEN** the workflow runs `python -m tracker run` with the state from the previous run, then publishes the result

#### Scenario: Nothing ran
- **WHEN** the tracker exits `1` (invalid policy, missing key or locked state)
- **THEN** the job fails and nothing is published

#### Scenario: Partial run
- **WHEN** the tracker exits `2` or `3`
- **THEN** its report is still published with status `partial` or `failed`

### Requirement: Publish the latest finished run
`python -m app.publish_report` SHALL copy the newest run with an end time from the tracker's state file into `tracker_runs`, with its Markdown report, and add one `internship_offers` row for every opportunity in that run's report. Each row records the report section (`new`, `open` or `closed`), rank, top-K mark, the record's fields, the work-authorization quote, the summary, status and evidence. Unknown pay, deadline and quote SHALL be null. Publishing a run again SHALL replace its rows.

#### Scenario: Sections match the report
- **WHEN** a run's report lists one opportunity as new and one as still open
- **THEN** the published rows have sections `new` and `open` for those opportunities

#### Scenario: Retried publish
- **WHEN** the same run is published twice
- **THEN** its offers appear once

#### Scenario: Unfinished run
- **WHEN** the newest run in the state file has no end time
- **THEN** the newest finished run is published instead

#### Scenario: Summary from an earlier run
- **WHEN** an opportunity was summarized when it was new and is still open in a later run
- **THEN** its row in the later run carries that summary
