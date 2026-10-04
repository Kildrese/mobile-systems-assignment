# Spec Delta

## ADDED Requirements

### Requirement: List runs
`GET /api/internships/runs` SHALL return published runs to a signed-in user, newest first. Each run SHALL include:
- its id, start and end time, status and stop reason;
- the number of its offers in each section (`new`, `top_k`, `dropped`, `open`);
- the number of its articles in each status (`fetched`, `skipped`, `rejected`, `failed`).

It SHALL take `limit` (default 30, at most 100) and `before` (a run id: only older runs).

#### Scenario: History
- **WHEN** a signed-in user requests the run list after three published runs
- **THEN** the response lists the three runs newest first, each with its section and article counts

#### Scenario: Paging
- **WHEN** the request has `limit=1&before=<id of the newest run>`
- **THEN** the response holds only the second-newest run

#### Scenario: Not signed in
- **WHEN** the request has no valid bearer token
- **THEN** the response is `401`

### Requirement: Read a run's report
`GET /api/internships/runs/{id}` SHALL return a published run and its offers to a signed-in user, in the same shape and order as `GET /api/internships/latest`.

#### Scenario: Earlier run
- **WHEN** a signed-in user requests a run that is not the latest
- **THEN** the response contains that run and its offers ordered by rank

#### Scenario: Unknown run
- **WHEN** the id is not a published run
- **THEN** the response is `404`

#### Scenario: Not signed in
- **WHEN** the request has no valid bearer token
- **THEN** the response is `401`

### Requirement: List a run's articles
`GET /api/internships/runs/{id}/articles` SHALL return a published run's articles to a signed-in user, in fetch order. Each article SHALL have its title, URL, kind, stage, fetch time, status and reason, exactly as stored.

#### Scenario: Articles
- **WHEN** a signed-in user requests the articles of a published run
- **THEN** each document the run tried to read is listed with its status

#### Scenario: Run without a log
- **WHEN** the run was published before articles were recorded
- **THEN** the response is `200` with an empty list

#### Scenario: Unknown run
- **WHEN** the id is not a published run
- **THEN** the response is `404`

#### Scenario: Not signed in
- **WHEN** the request has no valid bearer token
- **THEN** the response is `401`

### Requirement: Run history and run pages
The web app SHALL show, to signed-in users:
- `/internships/history`: the run list, newest first, with each run's time, status, counts per section and per article status, each linking to the run's page;
- `/internships/runs/:id`: that run's report, laid out like `/internships`, and a table of its articles (title, URL, kind, fetch time, status, reason).

`/internships` SHALL link to the history and to the latest run's articles. Text from the web (titles, URLs, reasons, summaries, quotes) SHALL be rendered as text, never as HTML. A URL SHALL be a link only when its scheme is `http` or `https`; otherwise it is shown as text.

#### Scenario: Injection page title
- **WHEN** a fetched page's title is `<img src=x onerror=alert(1)>`
- **THEN** the articles table shows those characters as text, and no script runs

#### Scenario: Rejected javascript URL
- **WHEN** a run logged `javascript:alert(1)` as rejected with reason `scheme_not_allowed`
- **THEN** the articles table shows the URL as plain text, not as a link

#### Scenario: Status shown
- **WHEN** a run's articles include fetched, skipped and rejected documents
- **THEN** each row shows its status, and rejected rows show their reason

#### Scenario: Signed out
- **WHEN** a signed-out visitor opens `/internships/history` or a run page
- **THEN** they are sent to sign in and come back afterwards

## MODIFIED Requirements

### Requirement: The API cannot start the tracker
The API SHALL expose no route that starts, re-runs or changes a tracker run or its published data.

#### Scenario: Write attempt
- **WHEN** a signed-in user sends `POST`, `PUT`, `PATCH` or `DELETE` to any `/api/internships` path
- **THEN** the response is `405` and nothing runs

#### Scenario: Documented routes
- **WHEN** the OpenAPI document is read
- **THEN** its only internship paths are these, each with `GET` only:
  - `/api/internships/latest`
  - `/api/internships/runs`
  - `/api/internships/runs/{id}`
  - `/api/internships/runs/{id}/articles`
  - `/api/internships/runs/{id}/report.md`

### Requirement: Internship page
The web app SHALL show the latest report at `/internships` to signed-in users. The page SHALL have four sections in this order, with counts: New since last run, Still in top K, Dropped, Also open. On the page:
- top-K offers are marked, and an offer under Still in top K shows its previous rank, or "entered the top K";
- an offer under Dropped shows why: "Closed" with the evidence, or "Outranked, now #n";
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
