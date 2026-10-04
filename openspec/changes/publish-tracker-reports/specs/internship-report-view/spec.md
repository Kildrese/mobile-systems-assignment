# Spec Delta

## ADDED Requirements

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
`GET /api/internships/runs/{id}/report.md` SHALL return, to a signed-in user, a Markdown file built from that run's `tracker_runs` row and its `internship_offers` rows, as `text/markdown; charset=utf-8` with `Content-Disposition: attachment; filename="internships-<run id>.md"`. The file SHALL follow the tracker report's layout:
- a header with the topic, run id, start time and status, with the stop reason when the run is not complete;
- **New since last run (n):** each offer by rank, with title, company, top-K mark, summary, location, term, pay and deadline when known, the work-authorization quote, a note when it was not checked in the run, and its link;
- **Still open (n):** one table with rank (top K marked), title (with "not checked this run" when unverified), company, location, term, first seen and link;
- **Closed since last run (n):** one line per offer with its closing evidence and link.

An empty section SHALL say so in one line. Text from the rows SHALL be kept to one line where the layout needs it, and `|` SHALL be escaped inside table cells.

#### Scenario: Export
- **WHEN** a signed-in user requests the export of a published run with one new and one still-open offer
- **THEN** the file has the three sections with counts 1, 1 and 0, the new offer in full, and the still-open offer as a table row

#### Scenario: Unknown run
- **WHEN** the id is not a published run
- **THEN** the response is `404`

#### Scenario: Not signed in
- **WHEN** the request has no valid bearer token
- **THEN** the response is `401`

#### Scenario: Cell text with a pipe
- **WHEN** an offer's title contains `|`
- **THEN** the table row escapes it, so the table keeps its columns

### Requirement: The API cannot start the tracker
The API SHALL expose no route that starts, re-runs or changes a tracker run or its published data.

#### Scenario: Write attempt
- **WHEN** a signed-in user sends `POST`, `PUT`, `PATCH` or `DELETE` to `/api/internships/latest`
- **THEN** the response is `405` and nothing runs

#### Scenario: Documented routes
- **WHEN** the OpenAPI document is read
- **THEN** its only internship paths are `/api/internships/latest` and `/api/internships/runs/{id}/report.md`, each with `GET` only

### Requirement: Internship page
The web app SHALL show the latest report at `/internships` to signed-in users, in three sections (New since last run, Still open, Closed since last run) with counts, top-K offers marked, each offer linking to its posting, and an "Export .md" button that downloads the run's Markdown export. Work-authorization wording SHALL appear only as a quote. An offer not checked in the run SHALL say so.

#### Scenario: Export button
- **WHEN** a signed-in user clicks "Export .md" on `/internships`
- **THEN** the browser saves the run's Markdown export as `internships-<run id>.md`

#### Scenario: No report yet
- **WHEN** a signed-in user opens `/internships` before the first publish
- **THEN** the page says there is no report yet

#### Scenario: Signed out
- **WHEN** a signed-out visitor opens `/internships`
- **THEN** they are sent to sign in and come back afterwards
