# Spec Delta

## MODIFIED Requirements

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
