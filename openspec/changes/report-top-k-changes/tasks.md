# Tasks

## 1. Report (opportunity-report)

- [ ] 1.1 Add `OpportunityStore.previous_ranked_run(run_id)`: the newest earlier run with an end time and rows in `ranks` (design D1). Test it with a failed run in between
- [ ] 1.2 Rewrite `report.sections()` with the rules in design D2: `new`, `top_k`, `dropped` (with `previous_rank` and `drop_reason`), `also_open`. Write a table test covering every rule, the first run, an opportunity that entered the top K, a reopened one (D3), and one closed but never in the top K
- [ ] 1.3 Update the Markdown: section headings and order, the previous rank and "entered the top K", drop reasons with evidence or the new rank, and "no earlier run to compare with" on a first run. Write a pipeline test over two runs with the "Second day" scenario

## 2. Publishing (report-publishing)

- [ ] 2.1 Write an Alembic migration that adds `previous_rank` and `drop_reason` to `internship_offers` and updates `closed` rows to `dropped` / `closed` (design D4). Test that it upgrades and downgrades
- [ ] 2.2 Update `models.py`, `schemas.py` (the section enum, `previousRank`, `dropReason`) and `publish_report.offers()`. Write a test for the "Dropped row" scenario
- [ ] 2.3 Regenerate `openapi/openapi.json` and the frontend client

## 3. Page (internship-report-view)

- [ ] 3.1 Update `SECTIONS` and `Offer` in `components/internships/report.tsx`: the previous rank or "entered the top K", drop reasons, and Apply only on open offers. Check it in the browser with a published two-run state

## 4. Docs

- [ ] 4.1 Update `docs/tracker.md` ("Report") and the section list in `docs/api.md`
