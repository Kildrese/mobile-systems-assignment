## 1. Sources

- [x] 1.1 Add kind `simplify` to `board_url`, `PARSERS`, `BOARD_API_HOSTS` and `WatchlistEntry.kind`; keep `BOARD_KINDS` (what the Scout may propose) at the three job boards (design D1, D3)
- [x] 1.2 Make `check_board_id` take the kind and accept `owner/repo` for `simplify`; quote owner and repo separately in the URL (design D2)
- [x] 1.3 Add `parse_simplify`: keep `active`, `is_visible`, Summer 2027 or no term, posted within `simplify_max_age_days`; build the text from the fields (design D5, D6). The parser takes the cutoff as `posted_after`, passed from Collect
- [x] 1.4 Add `SimplifyJobs/Summer2027-Internships` to `watchlist.yaml`, with the date it was checked

## 2. Store

- [x] 2.1 Add `company` to `RawPosting` (default `""`) and a nullable `raw_postings.listed_company` column through `_migrate`; write it in `upsert_postings`
- [x] 2.2 Select `COALESCE(p.listed_company, s.company) AS company` in `posting` and `pending_postings`; `linked_postings` keeps the source's company (design D4)

## 3. Curation

- [x] 3.1 In `fetch_posting_detail`, after the `url_mismatch` check, allow the URL's host for a posting from a `simplify` source (design D8); add to the Curator's instructions in `config.yaml`: fetch the page only when the text lacks a field the record needs

## 4. Wiring

- [x] 4.1 Add `simplify_max_age_days: int = Field(default=14, gt=0)` to `InternshipOptions`, and change `board_max_bytes`'s default to 20 MB
- [x] 4.2 In `validate`, require `raw.githubusercontent.com` in `fetch.allowed_hosts` only when the watchlist has a `simplify` source
- [x] 4.3 Check the Scout's prompt, which lists the known companies, doesn't show "Simplify" as one

## 5. Tests (`tests_tracker/test_internships_sources.py`, list faked with the existing transport)

- [x] 5.1 Parser: the scenarios in the spec (old, inactive, invisible, other term, `N/A` term kept, sponsorship line, `Other` left out)
- [x] 5.2 Collect: a Simplify source stores postings with their own company; a `304` reuses the cached list
- [x] 5.3 `propose_source` with kind `simplify` → `unknown_kind`
- [x] 5.4 Store: a board posting still reports its source's company; a Simplify posting reports its own
- [x] 5.5 Liveness: an opportunity listed only on Simplify closes when its listing turns inactive and the list was read
- [x] 5.6 `fetch_posting_detail`: a Simplify posting on an off-list host is fetched; a Greenhouse posting on an off-list host is `host_not_allowed`; a private-address URL from a listing is still `blocked_address`
- [x] 5.7 `validate` rejects a policy with a `simplify` source and `allowed_hosts` without raw.githubusercontent.com

## 6. Docs and check

- [x] 6.1 Update `docs/tracker.md` (sources) and the comment at the top of `sources.py`
- [x] 6.2 Run Collect once against the live list with `config.yaml` (2026-10-28: 913 listings kept by the parser, 89 past the pre-filter, so 89 pending for the Curator). Not a full agent run, which needs the API keys
