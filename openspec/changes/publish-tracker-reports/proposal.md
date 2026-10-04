# Proposal

> Written after the first implementation (PR #16), which skipped the proposal step. Review it as a proposal: where it is wrong, the code changes to match it, not the other way round.

## Why

The internship tracker (`add-internship-tracker`) writes its report to `reports/<run_id>.md`, which is git-ignored, and keeps its records in a local SQLite file. So no run output is visible to anyone but whoever ran it. Signed-in users of the web app should see the latest report, and runs should happen on their own every day, not when someone remembers to start one. Starting a run costs model and search quota, so no one should be able to trigger it through the public API.

## What Changes

- **Daily schedule.** A GitHub Actions workflow runs the tracker every day at 09:00 UTC (5:00 in New York in summer, 4:00 in winter), plus manual runs from the Actions tab. Production runs on Vercel serverless, which has no persistent disk and cannot run a job for 15 minutes, so the run cannot live in the API.
- **Publishing.** After the run, `python -m app.publish_report` copies the latest *finished* run from the tracker's SQLite state into Postgres: one `tracker_runs` row and one `internship_offers` row per opportunity in the report. Plain code does this, not an agent. The records are already verified and structured by the Curator and ranked by code, so a model would only add cost and a chance to change the facts.
- **Read-only API.** `GET /api/internships/latest`, for signed-in users, returns the latest run and its offers. No route starts, re-runs or changes a run.
- **Web page.** `/internships` shows the three report sections (new, still open, closed) with the top K marked.

## Capabilities

### New Capabilities
- `report-publishing`: the daily schedule, the state carried between runs, the publisher, and the two tables.
- `internship-report-view`: the read-only API route and the `/internships` page.

## Impact

- **Code:** `backend/app/publish_report.py`, `backend/app/routers/internships.py`, models and schemas, one Alembic migration, `frontend/src/components/internships/report.tsx`, a route in `App.tsx`, and the regenerated OpenAPI document and client.
- **Infrastructure:** `.github/workflows/tracker.yml`. Repository secrets `GROQ_API_KEY`, `TAVILY_API_KEY` and `DATABASE_URL`. The migration must be applied to Neon before the first scheduled run.
- **Dependencies:** stacked on `add-internship-tracker` (PR #15). The app imports the tracker's internship store read-only. The tracker still imports nothing from the app.
- **Docs:** `docs/deployment.md`, `docs/api.md` and `docs/tracker.md`.
