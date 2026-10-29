## Why

The watchlist has 9 hand-picked boards, and the Scout adds at most 5 a run, found through 6 searches. [SimplifyJobs/Summer2027-Internships](https://github.com/SimplifyJobs/Summer2027-Internships) is a community-maintained list of Summer 2027 internships with a machine-readable file behind it (`.github/scripts/listings.json`, on branch `dev`). On 2026-10-28 it held 17,533 listings, 5,020 of them active. 470 active listings pass our title and location pre-filter, 109 of those posted in the last 14 days. Many are at companies we don't read today, and the board they link to is often not Greenhouse, Lever or Ashby (Workday, custom career pages).

## What Changes

- **New source kind `simplify`.** Its board identifier is a GitHub repository, `owner/repo`. Collect reads `https://raw.githubusercontent.com/<owner>/<repo>/dev/.github/scripts/listings.json` with the same guardrails, conditional requests (raw.githubusercontent.com sends an `ETag`) and failure handling as the job boards.
- **Seeded in `watchlist.yaml`** as `SimplifyJobs/Summer2027-Internships`. **The Scout can't propose it.** `propose_source` still accepts only `greenhouse`, `lever` and `ashby`, so a page can't add an aggregator.
- **Each listing has its own company.** One source no longer means one company. `RawPosting` gets an optional `company` and `raw_postings` a `listed_company` column, and reads use it before the source's company. The Curator's same-company candidates, `mark_same` and the report then work as they do for a board.
- **Only listings worth curating.** Code keeps a listing only if it is `active` and `is_visible`, its `terms` include `Summer 2027` (or it gives no term), and it was posted within `options.simplify_max_age_days` (default 14). The existing title and location pre-filter runs after that. Without the age cap, the first run would hand the Curator about 470 postings while its budget covers about 30.
- **Posting text is built from the listing's fields.** A listing has no description, so the text is company, title, locations, terms, category, degrees, posted date and the `sponsorship` value word for word. The Curator marks a field `unknown` when the listing doesn't give it, as it does today.
- **The Curator may open the application page behind a Simplify listing.** `fetch_posting_detail` allows a Simplify posting's own URL even when its host isn't in `fetch_hosts` (Workday, custom career pages). Only that exact URL can be fetched, and the core guardrails still apply. Many of these pages render with JavaScript, so their text is often empty. Quotes then come from the listing's fields, as without the fetch.
- **`options.board_max_bytes` default goes from 8 MB to 20 MB.** The whole file is read every run: GitHub serves no partial query, and Liveness needs every listing's `active` flag (design D7). The file is 13 MB today (about 1.8 MB compressed on the wire) and grows during the season.
- **Liveness needs no change.** A listing that is removed or marked inactive is no longer listed, so it closes when Simplify was read in that run, the same as a board.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `opportunity-curation`: "Curator tools" lets `fetch_posting_detail` open a Simplify posting's own page on any host.
- `opportunity-sources`: "Watchlist" gets the `simplify` kind and per-listing companies. "Job-board collectors" covers reading the Simplify listings. A new requirement, "Simplify listings", sets what is kept and what the posting text is.

## Impact

- **Tracker code:** `usecases/internships/sources.py` (kind, URL, board format, parser, listing filter), `curation.py` (`fetch_posting_detail` allows a Simplify posting's own host), `store.py` (a `listed_company` column on `raw_postings` through the store's migration, and `COALESCE` in the reads that join `sources`), `wiring.py` (the new option and the `board_max_bytes` default; `validate` also requires `raw.githubusercontent.com` in `fetch.allowed_hosts` when a `simplify` source is configured), `watchlist.yaml`.
- **Tests:** `tests_tracker/test_internships_sources.py`, plus a store test for the company fallback.
- **Docs:** `docs/tracker.md` (sources).
- **Unchanged:** the Scout's tools and proposal rules, Assess, Rank and Edit, the report format and publishing.
- **Budget:** the Curator keeps 20 fetches a run. Its instructions say to fetch a page only when the posting text lacks a field the record needs.
