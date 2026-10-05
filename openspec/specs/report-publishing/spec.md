# report-publishing Specification

## Purpose
The daily scheduled tracker run on GitHub Actions, the SQLite state carried between runs, and publishing each finished run into Postgres as one `tracker_runs` row and one `internship_offers` row per offer.
## Requirements
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
`python -m app.publish_report` SHALL copy the newest run with an end time from the tracker's state file into `tracker_runs`, with its Markdown report. It SHALL add one `internship_offers` row for every opportunity in that run's report. Each row records:
- the report section: `new`, `top_k`, `dropped` or `open`, for New since last run, Still in top K, Dropped and Also open;
- the rank, the top-K mark, and the rank in the last run (`previous_rank`);
- for a dropped row, the reason (`drop_reason`: `closed` or `outranked`);
- the record's fields, the work-authorization quote, the summary, the status and the evidence.

Unknown pay, deadline and quote, and a missing previous rank or drop reason, SHALL be null. Publishing a run again SHALL replace its rows.

#### Scenario: Sections match the report
- **WHEN** a run's report lists one opportunity under each of New since last run, Still in top K, Dropped and Also open
- **THEN** the published rows have sections `new`, `top_k`, `dropped` and `open` for those opportunities

#### Scenario: Dropped row
- **WHEN** an opportunity ranked 4th last run is outranked to 7th
- **THEN** its row has section `dropped`, rank 7, `previous_rank` 4 and `drop_reason` `outranked`

#### Scenario: Rows published before this change
- **WHEN** the migration runs on a database with rows in section `closed`
- **THEN** those rows have section `dropped` and `drop_reason` `closed`

#### Scenario: Retried publish
- **WHEN** the same run is published twice
- **THEN** its offers appear once

#### Scenario: Unfinished run
- **WHEN** the newest run in the state file has no end time
- **THEN** the newest finished run is published instead

#### Scenario: Summary from an earlier run
- **WHEN** an opportunity was summarized when it was new and is still in the top K in a later run
- **THEN** its row in the later run carries that summary

