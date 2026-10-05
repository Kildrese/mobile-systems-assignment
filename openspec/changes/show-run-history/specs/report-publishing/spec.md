# Spec Delta

## ADDED Requirements

### Requirement: Publish the run's articles
`python -m app.publish_report` SHALL copy the published run's `fetch_log` rows into `tracker_articles`. It SHALL do this in the same transaction as the run and its offers, with the run id, stage, kind, URL, title, time, status and reason. Publishing a run again SHALL replace its article rows.

#### Scenario: Articles published
- **WHEN** a run logged 3 fetched, 9 skipped and 1 rejected document
- **THEN** `tracker_articles` holds those 13 rows for the run, with the same statuses

#### Scenario: Retried publish
- **WHEN** the same run is published twice
- **THEN** its articles appear once
