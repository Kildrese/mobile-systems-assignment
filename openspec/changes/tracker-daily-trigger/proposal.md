## Why

The daily tracker has never run on its own. `tracker.yml` has had a `schedule` trigger on `master` since 2026-10-04, but GitHub has created 0 `schedule` runs in this repository: the 2026-10-05 09:00 and 2026-10-06 09:17 slots were skipped without a trace, and all 4 production runs were started by hand (`workflow_dispatch`). Nothing on our side explains it (the workflow is `active`, the repo is public, the cron's last editor resolves to the owner's account), and re-committing the cron in #21 didn't help. GitHub's scheduler is best effort, so a daily report that depends on it can silently stop.

## What Changes

- **Vercel Cron starts the run.** The backend project (`mobile-systems-api`) gets a daily Vercel Cron Job (`0 9 * * *`, so 09:00–09:59 UTC on the Hobby plan). It calls a new internal route, which calls GitHub's `workflow_dispatch` endpoint for `tracker.yml` on `master` with a fine-grained token limited to this repository and to Actions read and write.
- **The route can't be reached by users.** It accepts only Vercel's `CRON_SECRET` bearer token, compared in constant time. Without it (no header, a user's session token, a wrong secret, or no secret configured) the answer is `404`, the same as for a path that doesn't exist. It is left out of the OpenAPI document, so it isn't in the docs or the generated frontend client.
- **At most one dispatch per UTC day.** A new `tracker_dispatches` table holds one row per day, keyed by the date. The route claims the day with one atomic `INSERT … ON CONFLICT` before calling GitHub, so of two calls arriving together, Postgres lets exactly one through. A failed dispatch marks the day `failed`, and a later call that day may claim it again. The table also records when each day's dispatch happened and why it failed.
- **BREAKING (decision):** "The API cannot start the tracker" becomes "No user can start the tracker". The internal route is the one exception, open only to the cron.
- **BREAKING (operations):** the `schedule` trigger is removed from `tracker.yml`, so GitHub's scheduler can't add a second run on a day it happens to work. `workflow_dispatch` becomes the only trigger, for the cron and for manual runs.

## Capabilities

### New Capabilities
- `tracker-dispatch`: the internal route Vercel Cron calls, how it authenticates the cron, the once-a-day claim in `tracker_dispatches`, and the GitHub call.

### Modified Capabilities
- `report-publishing`: "Daily scheduled run" says the run is started by the daily dispatch (not GitHub's `schedule`), that GitHub's scheduler can't add a run, and the time (it was still 09:00).
- `internship-report-view`: "The API cannot start the tracker" is renamed "No user can start the tracker" and allows the cron-only dispatch route.

## Impact

- **Backend:** a router `app/routers/internal.py`, a `TrackerDispatch` model and an Alembic migration for `tracker_dispatches`, two optional settings (`CRON_SECRET`, `GITHUB_DISPATCH_TOKEN`), and `backend/vercel.json` with the cron. It uses `httpx` for the GitHub call; no new dependency.
- **Workflow:** `.github/workflows/tracker.yml` loses `on.schedule`.
- **Outside the repo:** the owner creates the fine-grained token and sets both env vars on the Vercel backend project (Production).
- **Docs and comments:** `docs/deployment.md`, `docs/agent-loop.md`, and the comments in `tracker.yml`, `app/routers/internships.py` and `app/publish_report.py` that say no route can start a run.
- **Unchanged:** the job itself (state cache, exit codes, publishing, artifacts), the concurrency group, and the public read-only internship routes.
- **Order:** `complete-daily-runs` and `show-run-history` modify the same two requirements and aren't archived yet. Their changes are carried over here, so archive them first.
