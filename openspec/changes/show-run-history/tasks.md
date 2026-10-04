# Tasks

Apply after `report-top-k-changes`.

## 1. Fetch log (tracker-state)

- [ ] 1.1 Add the `fetch_log` table (a new schema version) and `StateStore.log_fetch()`, with the length cuts from design D3
- [ ] 1.2 Log from `tools.fetch_article` and `curation.fetch_posting_detail` (`ok` → fetched, `cached` → skipped, `blocked` and guardrail errors → rejected, other errors → failed, budget → nothing), per design D2. Test each status, including the `169.254.169.254` and `javascript:` rejections
- [ ] 1.3 Log boards from `sources.collect_source` (200, 304, error) and kept postings from Collect (new → fetched, already curated → skipped). Write a two-run pipeline test: run 2's boards and postings are `skipped`

## 2. Publishing (report-publishing)

- [ ] 2.1 Write an Alembic migration for `tracker_articles` (FK to `tracker_runs` with `ON DELETE CASCADE`, an index on `run_id`), plus its model
- [ ] 2.2 Copy the run's `fetch_log` in `publish_report`, in the same transaction, replacing on republish. Test the "Articles published" and "Retried publish" scenarios

## 3. API (internship-report-view)

- [ ] 3.1 Add `GET /api/internships/runs` with section and article counts, `limit` and `before` (design D4)
- [ ] 3.2 Add `GET /api/internships/runs/{id}`, sharing the handler with `/latest`
- [ ] 3.3 Add `GET /api/internships/runs/{id}/articles`
- [ ] 3.4 Test 401, 404, empty logs, paging, and the documented-routes and 405 scenarios across all internship paths
- [ ] 3.5 Regenerate `openapi/openapi.json` and the frontend client

## 4. Pages (internship-report-view)

- [ ] 4.1 Add a `SafeLink` component (an http(s) link or plain text) with a Vitest test (`javascript:`, `data:`, relative and https URLs), and use it for Apply (design D5)
- [ ] 4.2 Let `InternshipReport` take an optional run id. Add `/internships/history` and `/internships/runs/:id` behind the login guard, with the links from `/internships`
- [ ] 4.3 Check in the browser with a published run whose log holds the test injection page (`tests_tracker/fixtures/injection.html`) and a rejected `javascript:` URL: nothing runs, and both show as text

## 5. Docs

- [ ] 5.1 Add the three endpoints to `docs/api.md` in A1's table format, and the `tracker_runs`, `internship_offers` and `tracker_articles` schema
- [ ] 5.2 Document `fetch_log` in `docs/tracker.md` (state)
