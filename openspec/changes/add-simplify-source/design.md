## Context

Collect reads each watchlist source's public JSON, parses it into `RawPosting`s, pre-filters on title and location, and upserts into `raw_postings` keyed by `(source_id, external_id)`. Everything after Collect gets a posting's company from its source (`JOIN sources s ... s.company`). Liveness closes an opportunity when every source it is listed on was read in the run and none lists it any more.

`listings.json` in SimplifyJobs/Summer2027-Internships (branch `dev`) is a JSON list. Each listing has: `id` (UUID), `company_name`, `title`, `url`, `locations` (list), `terms` (list, e.g. `Summer 2027`, `N/A`), `active`, `is_visible`, `date_posted` and `date_updated` (Unix seconds), `category`, `sponsorship` (`Other`, `Offers Sponsorship`, `Does Not Offer Sponsorship`, `U.S. Citizenship is Required`), `degrees`. Measured on 2026-10-28: 13.2 MB, 17,533 listings, 5,020 active and visible, 470 past our pre-filter, of which 61 / 109 / 191 were posted in the last 7 / 14 / 30 days.

## Goals / Non-Goals

**Goals:**
- Read the Simplify list every run, with the guardrails and caching a board gets.
- Give the Curator a backlog it can work through, not hundreds of postings on the first run.
- Keep the Scout unable to add an aggregator.

**Non-Goals:**
- Fetching each listing's linked page during Collect.
- Other aggregators or other Simplify repositories. A second one is a watchlist entry, since the board identifier is the repository.
- Widening the Curator's `fetch_hosts`.

## Decisions

### D1. A source kind, not a separate stage
`simplify` is a fourth entry in `board_url` and `PARSERS`. Collect, the HTTP cache, `unreadable` handling and Liveness then apply without change. A separate stage would duplicate all of that.

### D2. Board identifier is `owner/repo`, checked by its own pattern
`BOARD_ID` doesn't allow `/`. `check_board_id` takes the kind and, for `simplify`, matches `^[A-Za-z0-9-]{1,39}/[A-Za-z0-9._-]{1,100}$`, then quotes each part separately when the URL is built. The branch (`dev`) and the path are fixed in code. When Simplify moves them, the source goes `unreadable`, which the run reports as it does for a board.

### D3. Config only
`propose_source` checks the kind against the three job-board kinds, not against every kind the parser knows. A page the Scout reads can't put an aggregator of thousands of listings on the watchlist. The rejection reason stays `unknown_kind`.

### D4. Per-posting company, falling back to the source's
`RawPosting.company: str = ""`, and a nullable `raw_postings.company` column added by `OpportunityStore._migrate` (the store already tracks schema versions in `component_versions`). Reads that return a posting select `COALESCE(NULLIF(p.company, ''), s.company) AS company`. Boards leave it empty, so nothing changes for them. The source's own `company` is "Simplify", which shows only in Collect's trace and fetch log.

### D5. Filter in the parser, cap by age
`parse_simplify` drops listings that are not `active` or not `is_visible`, whose `terms` name only other terms, or whose `date_posted` is older than `simplify_max_age_days` (default 14, from the run's clock). Dropping them in the parser rather than the pre-filter means they never reach `raw_postings`, so an old listing never shows up as pending. The cost: a listing older than the cap that we already hold looks "no longer listed" to Liveness and closes. That's acceptable, because the cap is about whether we curate a listing, and by then its record was rated and ranked while it was fresh. If this closes too much, we exempt `external_id`s we already hold (see Open Questions).

Why 14 days: about 110 postings on the first run and about 8 a day after that. The Curator (35 steps) drains the first backlog in 3–4 runs, and pending postings carry over between runs. 30 days would double the first backlog for little gain.

### D6. Posting text from the fields
Lines `Company: …`, `Title: …`, `Locations: …`, `Terms: …`, `Category: …`, `Degrees: …`, `Posted: YYYY-MM-DD`, `Sponsorship: …`, each only when the listing has a value. `Sponsorship: Other` is left out, since it says nothing. Quotes the Curator saves are checked against this text, so a sponsorship value it records is word for word what Simplify says. The text goes through `wrap` like any posting: it is third-party data.

### D7. Size cap
The default `board_max_bytes` goes from 8 MB to 20 MB. `json.loads` of 13 MB stays well within a GitHub runner's memory. A `304` skips both the download and the size check.

## Risks / Trade-offs

- **The same role on a board and on Simplify**: two postings, one per source. When Simplify links the same Greenhouse/Ashby URL, `link_exact` joins them through the canonical URL. Otherwise the Curator sees a same-company candidate and can `mark_same`. Either way it ends as one opportunity listed on two sources, and it only closes when both stop listing it.
- **Simplify changes its schema** → the parser's validation fails → `bad_response`, source `unreadable`. A config source is never deactivated, so it is tried again the next run.
- **Thin records** → fewer known fields means lower fit ratings and ranks for those postings. That's honest, and better than not seeing them at all.

## Open Questions

- Should a listing we already hold stay "listed" after it ages past the cap (D5)? Start without it and look at the closed counts after a week.
