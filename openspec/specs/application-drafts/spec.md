# application-drafts Specification

## Purpose
When drafts are made (after each daily publish and on demand), how deadlines and the daily cap apply, storage of the latest draft per user and offer, its API and the offer card's downloads.
## Requirements
### Requirement: Drafts after each publish
After the daily workflow publishes a run, `python -m app.draft_new` SHALL request a CV-only draft for each offer in that run's top K that is new since the last run (section `new`), for every user in `DRAFTING_USERS` who has a profile, unless that user already has a draft for that opportunity, and within the same daily cap. A cover letter SHALL be requested only when the posting asks for one: its posting text in the tracker's state mentions "cover letter" (case-insensitive). Requests SHALL be sent one after another, with retries and backoff like the verifier client. A failure SHALL be recorded on the draft row and SHALL NOT fail the workflow.

#### Scenario: New top-K offer
- **WHEN** a run adds two new offers to the top K and `kiliandresse` has a profile
- **THEN** two CV drafts are stored for `kiliandresse`

#### Scenario: Drafter down
- **WHEN** every request to the drafter times out
- **THEN** the workflow still succeeds, and each offer's draft row has status `failed` with the reason

### Requirement: Deadlines are respected
No draft SHALL be requested for an offer whose deadline field is a date in the past. Its card SHALL say "Deadline passed".

#### Scenario: Past deadline
- **WHEN** an offer's deadline is 2026-10-23 and today is 2026-11-02
- **THEN** no draft is requested, and the card says "Deadline passed"

### Requirement: Draft on demand
`POST /api/drafts` with `{opportunity_id, cover_letter}` SHALL draft for the signed-in user if they are in `DRAFTING_USERS` and have a profile, replacing any earlier draft of that user for that opportunity. Users without a profile SHALL get `409` with "upload your profile first". Viewers of a shared profile SHALL NOT be able to draft for its owner. While a draft for the same user and opportunity is in progress, another request SHALL get `409`.

#### Scenario: Draft again
- **WHEN** `kiliandresse` clicks "Draft application" with a cover letter on an offer that already has a CV draft
- **THEN** the old draft is replaced by one with a CV and a letter

#### Scenario: No profile
- **WHEN** `cara` is in `DRAFTING_USERS` but has no profile, and calls `POST /api/drafts`
- **THEN** she gets `409` "upload your profile first"

### Requirement: Draft storage
`application_drafts` SHALL hold one row per user and opportunity: `status` (`pending`, `ready`, `partial`, `failed`), the CV `.docx`, the cover letter `.docx` and text (when present), the role type, the checks list, the model id, the profile hashes it used, the request id and the time. Only the latest row per user and opportunity SHALL exist.

#### Scenario: Profile changed
- **WHEN** a draft was made before `kiliandresse` uploaded a new fact bank
- **THEN** the card marks the draft "made with an older profile"

### Requirement: Draft downloads
`GET /api/drafts?opportunity_id=` SHALL list the drafts the caller may read: their own and those of owners who shared with them. `GET /api/drafts/:id/cv.docx`, `/cover-letter.docx` and `/cover-letter.txt` SHALL download a draft's files for the owner and the owner's viewers, and return `404` for anyone else. File names SHALL be `<Company>_<Title>_CV.docx` and `<Company>_<Title>_Cover_Letter.docx`, with unsafe characters removed.

#### Scenario: Owner downloads
- **WHEN** `kiliandresse` downloads the CV of a ready draft for Ramp's "Software Engineer Intern"
- **THEN** the browser saves `Ramp_Software_Engineer_Intern_CV.docx`

#### Scenario: Stranger
- **WHEN** `cara` requests that draft's CV URL
- **THEN** she gets `404`

### Requirement: Drafts on the offer card
On `/internships`, an offer card SHALL show, for each draft the user may read: its status, the owner when it isn't the user, buttons to download the CV and the cover letter (`.docx`), a "Copy letter text" button, and a "Checks" disclosure listing what code changed or rejected. The owner SHALL also see "Draft application" (with a "Include cover letter" checkbox) or "Draft again". All of it SHALL render as text, never as HTML.

#### Scenario: Ready draft
- **WHEN** a ready CV-only draft exists for `kiliandresse`
- **THEN** his card shows "Download CV", "Draft again", and the checks, and no letter buttons

