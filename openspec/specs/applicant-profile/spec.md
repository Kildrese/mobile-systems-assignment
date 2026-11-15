# applicant-profile Specification

## Purpose
Each allowlisted user's profile files (master `cv.docx`, `fact_bank.yaml`, `rules.md`, `checks.yaml`): uploading, validating and storing them, owner-only access, and read-only sharing of drafts.
## Requirements
### Requirement: Only allowlisted users can draft
`DRAFTING_USERS` (a comma-separated list of usernames in the backend's environment, never in the repo) SHALL decide who may upload a profile and start drafts. Every other signed-in user SHALL get `403` from `PUT /api/profile` and `POST /api/drafts`, before any file is read or any drafter call is made. An empty or unset `DRAFTING_USERS` SHALL allow no one. The backend SHALL also refuse a draft, with `429`, once a user has started 20 drafts in the current UTC day, counted from `application_drafts`, before calling the drafter.

#### Scenario: Not allowlisted
- **WHEN** `DRAFTING_USERS=kiliandresse` and `nyugrader` uploads a profile or clicks "Draft application"
- **THEN** it gets `403`, and no drafter or model call happens

#### Scenario: Daily cap
- **WHEN** `kiliandresse` starts a 21st draft in one UTC day
- **THEN** it gets `429`, and the drafter is not called

#### Scenario: Unset allowlist
- **WHEN** `DRAFTING_USERS` is not set
- **THEN** every upload and draft request gets `403`

### Requirement: Profile files
An allowlisted user SHALL be able to upload an applicant profile of four files on `/account`: `cv.docx` (the master CV, at most 2 MB), `fact_bank.yaml`, `rules.md` and `checks.yaml` (each at most 200 KB). The API SHALL store them in one `applicant_profiles` row per user, replacing any earlier upload, with the upload time and the SHA-256 of each file. An upload SHALL be all four files or nothing.

#### Scenario: First upload
- **WHEN** `kiliandresse` uploads all four files
- **THEN** `GET /api/profile` returns the four file names, sizes, hashes and the upload time

#### Scenario: Partial upload
- **WHEN** an upload is missing `checks.yaml`
- **THEN** it returns `400` naming `checks.yaml`, and the stored profile is unchanged

### Requirement: Profile files are validated
Before storing, the API SHALL check that:
- `cv.docx` is a valid `.docx` that the drafter's layout map recognizes, with the EDUCATION, EXPERIENCE, PROJECTS and ADDITIONAL INFORMATION headings and the experience table;
- `fact_bank.yaml` is a list of items, each with a unique `id`, `section`, `entry`, `text`, `tags`, `on_master_cv` and `approved`;
- `checks.yaml` has the keys `banned_words`, `scope_words`, `cut_order`, `role_types` and `never_on_cv`, and every fact id it names exists in the fact bank;
- `rules.md` is UTF-8 text.

A file that fails SHALL return `400` with the file name and the reason, and nothing SHALL be stored.

#### Scenario: Duplicate fact id
- **WHEN** two fact-bank items share `id: exp.ipt.3`
- **THEN** the upload returns `400` naming `fact_bank.yaml` and `exp.ipt.3`

#### Scenario: Unknown CV layout
- **WHEN** the uploaded `.docx` has no EXPERIENCE heading
- **THEN** the upload returns `400` naming `cv.docx`

### Requirement: Only the owner reads the profile
`GET /api/profile` and the download of each profile file SHALL return only the caller's own profile. No route SHALL return another user's profile files or their contents, and the API SHALL NOT log file contents.

#### Scenario: Another user
- **WHEN** `nyugrader` calls `GET /api/profile`
- **THEN** it gets its own (empty) profile, never `kiliandresse`'s

### Requirement: Read-only draft sharing
An owner's profile SHALL hold a list of users who may read the owner's drafts. A viewer SHALL be able to list and download the owner's drafts, and SHALL NOT be able to start a draft for the owner, see the owner's profile files, or change the list. The list SHALL be set with `python -m app.share_drafts <owner> <viewer>` (and `--remove`), not through the API.

#### Scenario: nyugrader reads a draft
- **WHEN** `kiliandresse` has shared with `nyugrader`, and `nyugrader` opens an offer that has a draft by `kiliandresse`
- **THEN** the card shows that draft's downloads, labeled with the owner, and no "Draft application" button

#### Scenario: Not shared
- **WHEN** `cara` opens the same offer
- **THEN** her card shows no draft by `kiliandresse`

