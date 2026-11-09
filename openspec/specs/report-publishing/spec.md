# report-publishing Specification

## Purpose
The daily scheduled tracker run on GitHub Actions, the SQLite state carried between runs, and publishing each finished run into Postgres as one `tracker_runs` row and one `internship_offers` row per offer.
## Requirements
### Requirement: Daily scheduled run
The tracker SHALL run once a day. A Vercel Cron Job on the backend project SHALL call the internal dispatch route (see `tracker-dispatch`) daily between 09:00 and 09:59 UTC, and that route SHALL start the workflow through GitHub's `workflow_dispatch` endpoint. The workflow SHALL NOT have a `schedule` trigger, so GitHub's scheduler can't add a second run on the same day. Repository writers MAY also start a run manually from the Actions tab. The workflow SHALL take a `source` input (default `manual`; the dispatch route sends `cron`) and show it in the run's name. Its first job SHALL, for a `cron` run only, list the day's (UTC) `workflow_dispatch` runs of `tracker.yml` with the job's `GITHUB_TOKEN` limited to `actions: read`, and skip all of the run's work when another `cron` run with a lower run number started that day. If the runs can't be listed, the cron run SHALL fail without running the tracker. A `manual` run SHALL never be skipped. At most one run SHALL be in progress at a time. The job's timeout SHALL exceed the policy's `limits.max_wall_seconds` by enough for setup, saving state and publishing (at least 5 minutes), so a run is never cut off by the job before its own wall-clock budget ends. The run's SQLite state SHALL be restored before the run and saved after it, so each run continues from the previous one. After publishing, the workflow SHALL run `python -m app.draft_new`, and a failure of that step SHALL NOT fail the job.

#### Scenario: Daily run
- **WHEN** the cron calls the dispatch route and it claims the day
- **THEN** the workflow runs `python -m tracker run` with the state from the previous run, publishes the result, then drafts applications for new top-K offers

#### Scenario: GitHub's scheduler can't add a run
- **WHEN** the workflow file on `master` is read
- **THEN** its only trigger is `workflow_dispatch`

#### Scenario: Second cron run on one day
- **WHEN** a `cron` run starts and an earlier `cron` run of `tracker.yml` was created the same UTC day
- **THEN** the guard skips the run: the tracker doesn't run and nothing is published or drafted

#### Scenario: Two cron runs created together
- **WHEN** two `cron` runs were created the same UTC day
- **THEN** only the one with the lower run number does the work, whichever starts first

#### Scenario: Manual run is never skipped
- **WHEN** a writer starts a run from the Actions tab on a day a `cron` run already happened
- **THEN** its `source` is `manual`, the guard doesn't check, and the run does its work

#### Scenario: Manual run while the daily run is in progress
- **WHEN** a writer starts a run while the daily run is still in progress
- **THEN** the second run waits for the first to finish and continues from its state

#### Scenario: Nothing ran
- **WHEN** the tracker exits `1` (invalid policy, missing key or locked state)
- **THEN** the job fails and nothing is published or drafted

#### Scenario: Partial run
- **WHEN** the tracker exits `2` or `3`
- **THEN** its report is still published with status `partial` or `failed`

#### Scenario: Run uses its full wall time
- **WHEN** a run takes its full `max_wall_seconds`
- **THEN** the job still saves the state and publishes the report before its timeout

#### Scenario: Drafting fails
- **WHEN** `python -m app.draft_new` exits non-zero
- **THEN** the job still succeeds, and the step's log names the failure

### Requirement: Publish the latest finished run
`python -m app.publish_report` SHALL copy the newest run with an end time from the tracker's state file into `tracker_runs`, with its Markdown report and the list of services that failed in it (`failed_services`, empty when none did). It SHALL add one `internship_offers` row for every opportunity in that run's report. Each row records:
- the report section: `new`, `top_k`, `dropped` or `open`, for New since last run, Still in top K, Dropped and Also open;
- the rank, the top-K mark, and the rank in the last run (`previous_rank`);
- for a dropped row, the reason (`drop_reason`: `closed` or `outranked`);
- the record's fields, the work-authorization quote, the summary, the status and the evidence;
- the fit rating (`fit_score`, 0 to 3) and its reason (`fit_reason`);
- its claims (`claims`): a list of `{field, text, verdict, evidence}`, with verdict `supported`, `unsupported`, `unreachable` or `unverified`, and evidence only on supported claims.

Unknown pay, deadline and quote, and a missing previous rank, drop reason or fit rating, SHALL be null. An offer outside the top K SHALL have an empty `claims` list. Publishing a run again SHALL replace its rows.

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

#### Scenario: Fit published
- **WHEN** an opportunity in the report is rated 2 with a reason, and another is not rated
- **THEN** the first row has `fit_score` 2 and that reason, and the second has both null

#### Scenario: Claims published
- **WHEN** a top-K opportunity has a supported pay claim and an unreachable term claim
- **THEN** its row's `claims` holds both, the pay claim with its evidence and the term claim with evidence null

#### Scenario: Verifier failed
- **WHEN** the run's Verify stage failed
- **THEN** its `tracker_runs` row has `failed_services` `["verifier"]`

#### Scenario: Runs published before this change
- **WHEN** the migration runs on existing rows
- **THEN** existing offers have `claims` `[]` and existing runs have `failed_services` `[]`

### Requirement: Publish the run's articles
`python -m app.publish_report` SHALL copy the published run's `fetch_log` rows into `tracker_articles`. It SHALL do this in the same transaction as the run and its offers, with the run id, stage, kind, URL, title, time, status and reason. Publishing a run again SHALL replace its article rows.

#### Scenario: Articles published
- **WHEN** a run logged 3 fetched, 9 skipped and 1 rejected document
- **THEN** `tracker_articles` holds those 13 rows for the run, with the same statuses

#### Scenario: Retried publish
- **WHEN** the same run is published twice
- **THEN** its articles appear once

