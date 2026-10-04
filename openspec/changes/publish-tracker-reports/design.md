# Design

## Context

The tracker runs as a CLI (`python -m tracker run`) over a SQLite state file that must persist between runs: it holds the watchlist, the known opportunities (needed to tell "new" from "still open"), and HTTP validators. A run may take up to `limits.max_wall_seconds` (900 s). The API and the web app run on Vercel with a Neon Postgres database.

## Goals / Non-Goals

**Goals:**
- One run a day, unattended, and its result readable in the web app.
- No API path can start a run or write tracker data.

**Non-Goals:**
- Showing or exporting past runs from the UI. Each run's rows are kept and the export route takes any run id, so a history view can come later.
- Moving the tracker's state from SQLite into Postgres.
- Per-user filters or notifications.

## Decisions

### D1. Schedule on GitHub Actions
Options were a Vercel cron (no persistent disk, function time limits), a VPS crontab (a machine to keep running), and GitHub Actions. Actions needs nothing new to host and keeps keys in repository secrets. GitHub cron is UTC only, so the job runs at `0 9 * * *`, which is 5:00 in New York during daylight time and 4:00 otherwise. A `concurrency` group keeps two runs from sharing the state file.

### D2. State carried in the Actions cache
`.tracker/` is restored from the newest `tracker-state-*` cache entry and saved under a new key after each run. GitHub evicts entries unused for 7 days. A daily job keeps the newest entry in use, but if it is evicted the next run starts from an empty state and lists every open offer as new once. That is acceptable for now. Durable storage (a release asset, an object store, or Postgres) is the upgrade if it isn't.

### D3. Publish by code, not by an agent
Every field in an opportunity record already carries a quote checked word for word, and ranks and statuses come from code. The publisher maps these records into rows with the same section rules as the Markdown report (`report.sections`), so the page and the report always agree. It reads through `OpportunityStore`, not raw SQL on the tracker's tables, except for summaries (D5).

### D4. Snapshot rows per run
`tracker_runs(id = tracker run id, topic, status, stop_reason, started_at, ended_at, report_markdown, published_at)`.
`internship_offers(run_id → tracker_runs ON DELETE CASCADE, opportunity_id, section, rank, top_k, company, title, role_type, term, locations text[], remote, url, compensation, deadline, work_authorization_quote, summary, status, status_evidence, verified, first_seen_at)`, unique on `(run_id, opportunity_id)`.
One row per offer per run, not one mutable row per opportunity. The table grows by a few dozen rows a day, every run stays reproducible, and "latest" is a single query. Publishing a run that exists deletes it first (cascading to its offers) and inserts again in one transaction, so a retried job is safe.

### D5. Summaries carry over
The Editor writes summaries only for new and top-K opportunities in the run that produced them. The publisher gives each offer the most recent summary that passed the checks in this run or an earlier one (run ids begin with their UTC time, so they sort by age). Otherwise a still-open offer would lose its summary the day after it was new.

### D6. Only finished runs
The publisher picks the newest run with `ended_at` set. A run that is still going, or was killed, has no ended time and a `running` status. The first real test against a local state file published such a run.

### D7. Which tracker exits publish
Exit `1` means nothing ran (invalid policy, missing key, locked state): the job fails without publishing. Exits `0` (complete), `2` (partial) and `3` (provider failure) all wrote a report and are published, and the page shows a non-complete status.

### D8. Read-only route
`GET /api/internships/latest` needs a session (`CurrentSession`) and returns `{run, offers}`, with `run: null` before the first publish rather than a 404, so the page needs no error path for "no report yet". Offers are ordered by rank (unranked last), then company. The router defines no other method. A test checks that the OpenAPI document lists no other internship path and that writes get 405.

### D9. Markdown export from the rows
`GET /api/internships/runs/{id}/report.md` renders the run's offer rows into the tracker report's three-section layout in `app/` code. It does not return `tracker_runs.report_markdown` (the tracker's own file), because the export should be exactly what the database holds and what the page shows. The differences from the tracker's file: the header has no budget or stage table (not published), and every new offer is shown in full, since the run's K is not published (the tracker shows the first K in full and lists the rest). `report_markdown` stays as the raw record of the run.

The route takes a run id, not "latest", so an export link always names one run. The page gets that id from `/latest`. The download goes through the generated client because it needs the bearer header, so a plain `<a href>` cannot fetch it. The page turns the text into a Blob and saves it with the file name from the response.

## Risks / Trade-offs

- GitHub may start scheduled jobs late and disables schedules in repositories with no activity for 60 days.
- An evicted cache resets "new" (D2).
- The publisher depends on the tracker's internship store layout. Both live in this repository and are tested together.
