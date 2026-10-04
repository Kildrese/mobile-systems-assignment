# Spec Delta

## Purpose

Turns raw postings into verified opportunity records: structured fields, each backed by a verbatim quote from the posting, with duplicates across sources merged into one opportunity. A small model does the reading, and code checks every claim.

## ADDED Requirements

### Requirement: Opportunity record
An opportunity record SHALL have: company, title, role type (`internship`, `new_grad`, `other`), term (for example "Summer 2027", or `unknown`), locations, remote policy, application URL, and, when the posting states them, compensation, deadline and work-authorization wording. Every field except company and URL SHALL carry the verbatim quote it was taken from, or `unknown` with no quote. The schema the Curator sees SHALL list the allowed values of role type and remote policy, and code SHALL accept them in any case and spacing, and `intern` for `internship`, storing the canonical value.

#### Scenario: Another spelling of an allowed value
- **WHEN** the Curator submits role type `Internship` and remote policy `Remote`
- **THEN** the record is stored with `internship` and `remote`

#### Scenario: Term not stated
- **WHEN** a posting never mentions a season or year
- **THEN** the record's term is `unknown`, with no quote

### Requirement: Curator tools
The Curator agent SHALL work through pending postings listed in this run one at a time, the most relevant first: postings whose title matches `ranking.focus_keywords` before the others, then by id. Each posting SHALL get a fresh conversation whose task carries its text and same-company candidates, wrapped as untrusted data exactly as `get_posting` returns them, and that ends as soon as the posting is handled, without waiting for `finish`. The Curator SHALL have exactly these tools:
- `get_posting(id)` returns stored posting text as untrusted data.
- `fetch_posting_detail(posting_id, url)` fetches a posting's own page, limited to the Curator's `fetch_hosts`, and keeps its text with that posting so quotes can come from it. A `url` that is not the posting's own URL is rejected with reason `url_mismatch`.
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

#### Scenario: One call per posting
- **WHEN** the Curator saves a record for its posting
- **THEN** the conversation ends after that one model call, and the next posting's starts

#### Scenario: Budget runs out
- **WHEN** the Curator's step budget runs out with 4 postings unprocessed
- **THEN** those postings stay `pending` for the next run, they are the least relevant of the run's postings, and the stage outcome is partial

### Requirement: Quotes are verified by code
`save_record` SHALL accept a record only when every non-`unknown` field's quote appears in that posting's stored text (board text or fetched detail page), compared after whitespace and case normalization. If a quote is not found, the record is rejected with reason `quote_not_found`, naming the field. The Curator may then retry, or mark the field `unknown`. On its next `save_record` for that posting in the same run, fields whose quote is still not found SHALL be saved as `unknown` instead, so a model that repeats a wrong quote does not retry forever; the title must still be found, and no unverified value is ever stored. A number given as a field's value (such as pay) SHALL be stored as text; its quote is checked as usual.

#### Scenario: Invented deadline
- **WHEN** the Curator saves a record with deadline "Nov 1" quoting text that is not in the posting
- **THEN** `save_record` returns `quote_not_found` for `deadline`, and nothing is stored

#### Scenario: The same wrong quote twice
- **WHEN** the Curator quotes term "Summer 2027" for a posting that says "Summer Intern 2027", is told the quote is not found, and sends the same record again
- **THEN** the record is saved with term `unknown` and every other field as verified

### Requirement: Work authorization is quoted, never judged
Work-authorization or sponsorship wording SHALL be stored only as the verbatim quote. No stage SHALL derive eligibility from it, filter on it or rank by it.

#### Scenario: Sponsorship clause
- **WHEN** a posting says "Candidates must be authorized to work in the US without sponsorship"
- **THEN** the record stores that sentence under work authorization, and the opportunity's rank is unaffected

### Requirement: Same-role resolution
Code SHALL first treat postings as the same opportunity when they share a job board and job id, or a canonical URL. For postings with different sources, code SHALL offer the Curator candidates from the same company with similar normalized titles, and the Curator decides with `mark_same` and a stated reason. Code SHALL refuse `mark_same` across different companies.

#### Scenario: Same role on two sources
- **WHEN** a company's Lever and Ashby boards both list "Software Engineer Intern (Summer 2027)"
- **THEN** after `mark_same`, one opportunity exists, with both URLs linked

#### Scenario: Cross-company link refused
- **WHEN** the Curator calls `mark_same` on postings from two different companies
- **THEN** the call returns reason `company_mismatch`, and nothing is linked
