# Spec Delta

## MODIFIED Requirements

### Requirement: Curator tools
The Curator agent SHALL work through pending postings listed in this run one at a time, the most relevant first: postings whose title matches `ranking.focus_keywords` before the others, then by id. Each posting SHALL get a fresh conversation whose task carries its text and same-company candidates, wrapped as untrusted data exactly as `get_posting` returns them, and that ends as soon as the posting is handled, without waiting for `finish`. The Curator SHALL have exactly these tools:
- `get_posting(id)` returns stored posting text as untrusted data.
- `fetch_posting_detail(posting_id, url)` fetches a posting's own page and keeps its text with that posting so quotes can come from it. A `url` that is not the posting's own URL is rejected with reason `url_mismatch`. The page's host SHALL be in the Curator's `fetch_hosts`, except for a posting from a `simplify` source: its own URL's host is allowed too, since a listing links to the company's own application page. The core fetch guardrails apply in full either way.
- `save_record(posting_id, record)` stores an opportunity record.
- `mark_same(posting_id, opportunity_id, reason)` links a posting to an existing opportunity.
- `flag_unclear(posting_id, reason)` parks a posting it cannot resolve.

The Curator SHALL NOT have `search_web` or source-proposal tools. Each pending posting SHALL end the stage either saved, linked, flagged, or still pending because the budget ran out.

#### Scenario: Missing location
- **WHEN** a posting's board JSON has no location, but its detail page does
- **THEN** the Curator may call `fetch_posting_detail` and save a record whose location quote comes from that page

#### Scenario: Detail page of another posting
- **WHEN** the Curator calls `fetch_posting_detail` for a posting with the URL of a different job
- **THEN** the call is rejected with reason `url_mismatch` and no request is made

#### Scenario: Application page behind a Simplify listing
- **WHEN** the Curator calls `fetch_posting_detail` for a Simplify posting whose URL is on `acme.wd1.myworkdayjobs.com`, which is not in `fetch_hosts`
- **THEN** the page is fetched and its text is kept with the posting; if it has no readable text, quotes still come from the listing's fields

#### Scenario: Off-host page of a board posting
- **WHEN** the Curator calls `fetch_posting_detail` for a Greenhouse posting whose stored URL is on a host not in `fetch_hosts`
- **THEN** the call is blocked with reason `host_not_allowed` and no request is made

#### Scenario: One call per posting
- **WHEN** the Curator saves a record for its posting
- **THEN** the conversation ends after that one model call, and the next posting's starts

#### Scenario: Budget runs out
- **WHEN** the Curator's step budget runs out with 4 postings unprocessed
- **THEN** those postings stay `pending` for the next run, they are the least relevant of the run's postings, and the stage outcome is partial
