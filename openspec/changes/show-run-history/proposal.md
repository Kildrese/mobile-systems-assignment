# Proposal

## Why

Assignment 1B, requirements 11 and 12: the screen behind the A1 login must show three things, fed by new backend endpoints that return `401` without a valid token:

- the latest report;
- **run history**: when each run happened and what changed;
- **the articles fetched on each run**, with title, URL, fetch time and status (fetched, skipped as already seen, or rejected by the guardrail).

Today the API serves only the latest run (`/latest`) and a run's Markdown export, so the page shows only the latest report.

Most of what history needs is already stored:
- `tracker_runs` keeps one row per published run;
- `internship_offers` keeps each run's sections, so "what changed" is a count per section.

What's missing is the list of articles. The tracker does work out every status: `fetch_article` returns `ok`, `cached` or `blocked`, a board answers `200` or `304`, a posting is new or already curated. But it writes them only to the trace, which is not published. A guardrail rejection is not stored anywhere else.

## What Changes

- **A fetch log in the tracker state.** It has one row for every document a run tried to read:
  - pages: the Scout's `fetch_article` and the Curator's detail pages;
  - job boards read by Collect;
  - postings that passed the prefilter.

  Each row has a title, URL, time, status (`fetched`, `skipped`, `rejected`, `failed`) and the reason.
- **Publishing** copies the run's log into a new `tracker_articles` table.
- **Three read-only endpoints:**
  - `GET /api/internships/runs`: run history, newest first, with section and article counts;
  - `GET /api/internships/runs/{id}`: a run's report, the same shape as `/latest`;
  - `GET /api/internships/runs/{id}/articles`: its fetch log.
- **Two pages:**
  - `/internships/history`: the run list;
  - `/internships/runs/:id`: that run's report and its articles.

  `/internships` links to both. Everything that came from the web is rendered as text. A URL is a link only when its scheme is `http` or `https`; a URL rejected by the guardrail, such as `javascript:…`, is shown as text.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `tracker-state`: the fetch log.
- `report-publishing`: publishing it.
- `internship-report-view`: the three endpoints, the documented routes, the history and run pages.

## Impact

- **Tracker code:**
  - `tracker/state.py`: the `fetch_log` table and `log_fetch()`;
  - `tracker/tools.py`: `fetch_article`;
  - `usecases/internships/sources.py`: boards and postings;
  - `usecases/internships/curation.py`: `fetch_posting_detail`.
- **Backend:**
  - an Alembic migration for `tracker_articles`;
  - `models.py`, `schemas.py`, `publish_report.py`, `routers/internships.py`.
- **Frontend:**
  - two routes in `App.tsx`;
  - pages in `components/internships/`;
  - the regenerated client.
- **Docs:** `docs/api.md` (the endpoint table, in A1's format), `docs/tracker.md` (state), and a README pointer to the schema.
- **Depends on `report-top-k-changes`.** The history counts use its section values (`new`, `top_k`, `dropped`, `open`), so that change goes first.
- **No change** to the agents, budgets or guardrails. The API still cannot start a run.
