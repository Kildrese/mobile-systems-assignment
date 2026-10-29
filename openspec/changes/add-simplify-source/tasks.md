## 1. Sources

- [ ] 1.1 Add kind `simplify` to `board_url`, `PARSERS`, `BOARD_API_HOSTS` and `WatchlistEntry.kind`; keep `BOARD_KINDS` (what the Scout may propose) at the three job boards (design D1, D3)
- [ ] 1.2 Make `check_board_id` take the kind and accept `owner/repo` for `simplify`; quote owner and repo separately in the URL (design D2)
- [ ] 1.3 Add `parse_simplify`: keep `active`, `is_visible`, Summer 2027 or no term, posted within `simplify_max_age_days`; build the text from the fields (design D5, D6). The parser takes the cutoff, so `PARSERS` entries take `(body, ctx)` or Collect passes it via `functools.partial`
- [ ] 1.4 Add `SimplifyJobs/Summer2027-Internships` to `watchlist.yaml`, with the date it was checked

## 2. Store

- [ ] 2.1 Add `company` to `RawPosting` (default `""`) and a nullable `raw_postings.company` column through `_migrate`; write it in `upsert_postings`
- [ ] 2.2 Select `COALESCE(NULLIF(p.company, ''), s.company) AS company` in `posting`, `pending_postings`, `linked_postings` and every other read that joins `sources` for the company (design D4)

## 3. Wiring

- [ ] 3.1 Add `simplify_max_age_days: int = Field(default=14, gt=0)` to `InternshipOptions`, and change `board_max_bytes`'s default to 20 MB
- [ ] 3.2 In `validate`, require `raw.githubusercontent.com` in `fetch.allowed_hosts` only when the watchlist has a `simplify` source
- [ ] 3.3 Check the Scout's prompt, which lists the known companies, doesn't show "Simplify" as one

## 4. Tests (`tests_tracker/test_internships_sources.py`, list faked with the existing transport)

- [ ] 4.1 Parser: the scenarios in the spec (old, inactive, invisible, other term, `N/A` term kept, sponsorship line, `Other` left out)
- [ ] 4.2 Collect: a Simplify source stores postings with their own company; a `304` reuses the cached list
- [ ] 4.3 `propose_source` with kind `simplify` → `unknown_kind`
- [ ] 4.4 Store: a board posting still reports its source's company; a Simplify posting reports its own
- [ ] 4.5 Liveness: an opportunity listed only on Simplify closes when its listing turns inactive and the list was read
- [ ] 4.6 `validate` rejects a policy with a `simplify` source and `allowed_hosts` without raw.githubusercontent.com

## 5. Docs and check

- [ ] 5.1 Update `docs/tracker.md` (sources) and the comment at the top of `sources.py`
- [ ] 5.2 Run the tracker once against the live list with `config.smoke.yaml` and record how many listings Collect keeps
