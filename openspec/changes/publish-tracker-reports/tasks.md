# Tasks

Implemented in PR #16 before this proposal existed. The tasks record what was built and how it was verified; any change from review becomes a new unchecked task.

## 1. Tables (report-publishing)

- [x] 1.1 Add `TrackerRun` and `InternshipOffer` models and their Alembic migration (design D4). Verify with `alembic upgrade head` and `alembic check`

## 2. Publisher (report-publishing)

- [x] 2.1 Implement `python -m app.publish_report`: newest finished run, rows by report section, carried-over summaries, replace on republish (design D3–D6). Verify with `tests/test_internships.py` over a two-run state file, and a manual publish of a real local state file
- [x] 2.2 Add `.github/workflows/tracker.yml`: 09:00 UTC schedule, manual dispatch, concurrency group, state in the Actions cache, publish after exit 0/2/3, reports and traces as artifacts (design D1, D2, D7)

## 3. API and web (internship-report-view)

- [x] 3.1 Add `GET /api/internships/latest` with its schemas, regenerate `openapi/openapi.json`. Verify with tests for auth, empty state, ordering, and 405 on writes
- [x] 3.2 Regenerate the client and add the `/internships` page with a link from home. Verify with typecheck, lint, Vitest and build

## 4. Markdown export (internship-report-view)

- [ ] 4.1 Render a run's rows as Markdown in the tracker report's layout (design D9). Verify with a unit test: three sections with counts, a new offer in full, a still-open table row, a `|` in a title escaped, empty sections said in one line
- [ ] 4.2 Add `GET /api/internships/runs/{id}/report.md` (`text/markdown`, attachment file name), regenerate `openapi/openapi.json`. Verify with tests: 200 with the headers, 404 for an unknown run, 401 without a token, and the documented-routes test updated
- [ ] 4.3 Regenerate the client and add the "Export .md" button on `/internships` (Blob download with the bearer header). Verify with typecheck, lint, build and a manual download
- [ ] 4.4 Document the route in `docs/api.md`

## 5. Rollout

- [ ] 5.1 Add the repository secrets `GROQ_API_KEY`, `TAVILY_API_KEY` and `DATABASE_URL`
- [ ] 5.2 Apply the migration to Neon (`./scripts/db-migrate-neon.sh`) before merging
- [ ] 5.3 Trigger the workflow manually once and check the page in production
