# Design

## Context

Every place that reads a document already ends with a known outcome, and each one is traced:

| Where | Outcomes today |
| --- | --- |
| `tools.fetch_article` (Scout) | `ok`, `cached` (served from `articles`), `blocked` (a `guard.Blocked` reason), `error`, `budget` |
| `curation.fetch_posting_detail` (Curator) | The same guarded fetch, for posting detail pages |
| `sources.collect_source` (Collect) | `ok` (200), `not_modified` (304), `error` (`too_large`, HTTP status, timeout) |
| Collect prefilter + `upsert_postings` | Each kept posting is new (`curation = 'pending'`) or already curated |

`app.publish_report` already copies the run and its offers into Postgres in one transaction, and replaces them on a retried publish.

## Goals / Non-Goals

**Goals:**
- For each published run, list every document it tried to read, with title, URL, time and one of the assignment's statuses.
- List the runs with what changed, and open any run's report.
- No web content can become markup or a `javascript:` link in the app.

**Non-Goals:**
- Per-user tracker data. The tracker is one shared daily run, and every signed-in user sees the same reports, as the latest report does today.
- Publishing runs that never reached the database (local runs). History is what the daily workflow published.
- Search results as articles. A search returns snippets the agent has not fetched, and those are in the trace.

## Decisions

### D1. Record the log in the state, not from the trace
Code that knows the outcome calls `state.log_fetch(db, run_id, stage, kind, url, title, status, reason)` at the point it decides, with the status from `state.fetch_status()`. The publisher reads `fetch_log` like any other state table.

*Alternative:* parse `traces/<run_id>.jsonl` at publish time, with no tracker change. Rejected for three reasons:
- the trace is a diagnostic format, not a schema;
- it lacks posting titles;
- it would make the publisher depend on a file outside the state.

### D2. Statuses
| Status | Means | Cases |
| --- | --- | --- |
| `fetched` | Read over the network this run | Page `ok`, board 200, a posting not seen before |
| `skipped` | Already seen, no download | Page served from state (`cached`), board 304, a posting first seen in an earlier run |
| `rejected` | Refused by a guardrail before or during the request | `guard.Blocked` reasons (scheme, credentials, host, address, DNS), `too_large`, `unsupported_content_type`, `too_many_redirects` |
| `failed` | Tried and did not get a usable answer | Timeout, connection error, HTTP 4xx/5xx |

A fetch refused by a budget made no request and was never tried, so it is not logged. It stays in the trace.

A posting counts as `skipped` when it was first seen in an earlier run, whether or not it has been curated yet: what the log records is whether the document is new to the tracker. A posting still waiting for the Curator shows in the report's "waiting for review" count.

### D3. Kinds and titles
`kind` is `page`, `board` or `posting`, so a long run can be filtered down to the pages the Scout read. The title is:
- a page's `<title>`, or empty when it was not fetched;
- for a board, "Company (Greenhouse board)";
- for a posting, its job title.

All text is stored as it came: titles cut to 300 characters, URLs to 2,048 (the guardrail's limit). A rejected URL is stored even when it is not a valid URL, because showing it is the point of the log.

### D4. "What changed" is counted, not stored
`GET /api/internships/runs` counts each run's `internship_offers` by section and its `tracker_articles` by status, with two `GROUP BY` queries over the page of runs. There are no counter columns to keep in sync. A run's own titles (what was new, what dropped) come from `GET /api/internships/runs/{id}`, which returns the same shape as `/latest`, and both share one handler.

The history is paged with `limit` (default 30, maximum 100) and `before` (a run id, since ids sort by start time).

### D5. Rendering web text
Titles, URLs, reasons and summaries are React text children, never `dangerouslySetInnerHTML`. A URL is an `<a href>` only when `new URL(url).protocol` is `http:` or `https:`, and otherwise plain text, because a rejected URL can be `javascript:` or `data:`. One helper, `webUrl()`, does this check; the articles table and the Apply button in the report both use it.

### D6. Pages
There are no Tabs or Table components in the app. The pages use a plain `<table>` with Tailwind classes rather than adding new shadcn components.

| Route | Shows |
| --- | --- |
| `/internships` | The latest report as now, plus "Run history" and "Articles in this run" links |
| `/internships/history` | Runs, newest first: time, status, counts per section, counts per article status, each row linking to its run |
| `/internships/runs/:id` | That run's report (the `InternshipReport` component, given a run id) and its articles table: title, URL, kind, fetch time, status, reason |

## Risks / Trade-offs

- **Postings can be many.** A board can list hundreds of jobs. Only postings that pass the prefilter are logged, so each run logs tens, not hundreds. The articles endpoint returns them all, with no pagination; add it if one run ever logs more than about 500.
- **The first run after this change has no older logs.** Runs published earlier have no articles, and their run pages say "No articles were recorded for this run."
