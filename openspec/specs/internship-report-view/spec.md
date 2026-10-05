# internship-report-view Specification

## Purpose
Read-only access to published tracker runs: the latest report and a run's Markdown export over the API, the `/internships` page, and the rule that nothing in the API can start the tracker.
## Requirements
### Requirement: Read the latest report
`GET /api/internships/latest` SHALL return the latest published run and its offers, best rank first with unranked offers last, to a signed-in user. Before any run is published it SHALL return `run: null` and no offers.

#### Scenario: Signed in
- **WHEN** a signed-in user requests the latest report
- **THEN** the response contains the newest run by start time and its offers ordered by rank

#### Scenario: Not signed in
- **WHEN** the request has no valid bearer token
- **THEN** the response is `401`

#### Scenario: No report yet
- **WHEN** no run has been published
- **THEN** the response is `200` with `run: null` and an empty `offers` list

### Requirement: Export a run as Markdown
`GET /api/internships/runs/{id}/report.md` SHALL return, to a signed-in user, the tracker's own Markdown report for that run as published (`tracker_runs.report_markdown`), as `text/markdown; charset=utf-8` with `Content-Disposition: attachment; filename="internships-<run id>.md"`.

#### Scenario: Export
- **WHEN** a signed-in user requests the export of a published run
- **THEN** the response body is that run's report exactly as the tracker wrote it

#### Scenario: Unknown run or no report
- **WHEN** the id is not a published run, or the run was published without a report
- **THEN** the response is `404`

#### Scenario: Not signed in
- **WHEN** the request has no valid bearer token
- **THEN** the response is `401`

### Requirement: The API cannot start the tracker
The API SHALL expose no route that starts, re-runs or changes a tracker run or its published data.

#### Scenario: Write attempt
- **WHEN** a signed-in user sends `POST`, `PUT`, `PATCH` or `DELETE` to `/api/internships/latest`
- **THEN** the response is `405` and nothing runs

#### Scenario: Documented routes
- **WHEN** the OpenAPI document is read
- **THEN** its only internship paths are `/api/internships/latest` and `/api/internships/runs/{id}/report.md`, each with `GET` only

### Requirement: Internship page
The web app SHALL show the latest report at `/internships` to signed-in users. The page SHALL have four sections in this order, with counts: New since last run, Still in top K, Dropped, Also open. On the page:
- top-K offers are marked, and an offer under Still in top K shows its previous rank, or "entered the top K";
- an offer under Dropped shows why: "Closed" with the evidence, or "Outranked, now #n";
- a rated offer shows "Fit n/3" and the reason; an unrated one shows nothing about fit;
- each open offer has an "Apply" button (external-link icon) that opens its posting in a new tab, only when the posting URL is `http` or `https`;
- an "Export" button (download icon) downloads the run's Markdown export;
- a "Run history" link goes to `/internships/history`, and an "Articles in this run" link to the latest run's page;
- work-authorization wording appears only as a quote;
- an offer not checked in the run says so.

#### Scenario: Dropped offers
- **WHEN** the latest run dropped one offer as closed and one as outranked to 7th
- **THEN** the Dropped section shows both, one marked "Closed" with its evidence and no Apply button, the other "Outranked, now #7" with its Apply button

#### Scenario: First run
- **WHEN** the latest run has nothing to compare with
- **THEN** Still in top K and Dropped say there is no earlier run yet

#### Scenario: Export button
- **WHEN** a signed-in user clicks "Export" on `/internships`
- **THEN** the browser saves the run's Markdown export as `internships-<run id>.md`

#### Scenario: No report yet
- **WHEN** a signed-in user opens `/internships` before the first publish
- **THEN** the page says there is no report yet

#### Scenario: Signed out
- **WHEN** a signed-out visitor opens `/internships`
- **THEN** they are sent to sign in and come back afterwards

#### Scenario: Fit shown
- **WHEN** the latest run rated an offer 3 with the reason "ML infrastructure role at an early-stage startup, as the profile asks."
- **THEN** its card shows "Fit 3/3" and that reason

