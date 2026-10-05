# Proposal

## Why

Assignment 1B, requirement 7: on the second run the report must be organized as **New since last run**, then **Still in top K**, then **Dropped**. The report has New since last run, Still open (every earlier open opportunity, accumulated across runs, with the top K marked) and Closed since last run.

The difference is more than the headings. The assignment's sections compare this run's top K with the last run's. Ours compare open with closed. So an opportunity that leaves the top K because a better one arrived, but is still open, is never reported as dropped: it stays under Still open with its "top K" mark gone. The state already holds what the comparison needs, because `ranks` stores every run's rank and top-K mark (requirement 6: "what your top K was last time").

## What Changes

- **The report's sections:**
  1. **New since last run**: unchanged.
  2. **Still in top K**: the current top K that are not new, with their rank change. One that was not in the last top K is marked "entered the top K".
  3. **Dropped**: every opportunity in the last run's top K that is not in this one, with its reason: `closed` (with the closing evidence) or `outranked` (with its new rank). Also any other opportunity closed since the last run.
  4. **Also open**: every other open opportunity first seen earlier, in one table by rank. This keeps the cumulative list, after the three required sections.
- **Each opportunity appears in exactly one section**, as now.
- **On a first run**, Still in top K and Dropped are empty and say so.
- **Publishing** writes the new section values (`new`, `top_k`, `dropped`, `open`), plus the previous rank and the reason an opportunity dropped. A migration maps old `closed` rows to `dropped`.
- **The `/internships` page** shows the four sections.

## Capabilities

### Modified Capabilities
- `opportunity-report`: the report layout.
- `report-publishing`: section values, previous rank and drop reason on each published offer.
- `internship-report-view`: the page's sections.

## Impact

- **Tracker code:** `backend/tracker/usecases/internships/report.py` (`sections()` and the Markdown) and `store.py` (the previous finished run's ranks).
- **Backend:** `app/models.py`, `app/schemas.py`, `app/publish_report.py`, and an Alembic migration that adds `previous_rank` and `drop_reason` to `internship_offers` and maps `closed` to `dropped`.
- **Frontend:** `components/internships/report.tsx`, plus the regenerated API client.
- **Docs:** `docs/tracker.md` ("Report").
- **No change** to ranking, lifecycle, curation or the agents.
- **Before `show-run-history`.** That change counts each run's sections, so this one goes first.
