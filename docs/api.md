# API and web UI

## Interactive docs

- <http://localhost:8000/docs>: Swagger UI. Log in with "Try it out" on `POST /api/auth/login`, then paste the token under "Authorize" to call protected endpoints.
- <http://localhost:8000/api/openapi.json>: the OpenAPI 3.1 document, identical to the committed `openapi/openapi.json`.

## Endpoints

Protected endpoints take `Authorization: Bearer <token>`, where the token comes from `POST /api/auth/login`.

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/healthz` | no | Liveness check, returns `{ "status": "ok" }` |
| POST | `/api/auth/register` | no | Create an account (`201`, no token) |
| POST | `/api/auth/login` | no | Get a bearer token and the user |
| GET | `/api/auth/me` | yes | The logged-in user |
| POST | `/api/auth/logout` | yes | Revoke the current token (`204`) |
| POST | `/api/auth/change-password` | yes | Needs the current password. Revokes every session and returns a new `token` |
| GET / PATCH / DELETE | `/api/users/:id` | yes | Read, update (username, first and last name) or delete your own account |
| GET | `/api/internships/latest` | yes | The latest published tracker run and its offers (`run` is `null` before the first). Read-only: nothing in the API starts the tracker |
| GET | `/api/internships/runs` | yes | Run history, newest first: each run's times, status, offers per report section and articles per status. `limit` (1–100, default 30) caps how many |
| GET | `/api/internships/runs/:id` | yes | One run's report, the same shape as `/latest` (`404` if unknown) |
| GET | `/api/internships/runs/:id/articles` | yes | The documents the run tried to read (pages, job boards, postings), in fetch order, with title, URL, fetch time and status: `fetched`, `skipped` (already seen), `rejected` (by a fetch guardrail) or `failed` (`404` if unknown) |
| GET | `/api/profile` | yes | Your applicant profile: the four files' names, sizes and SHA-256, the upload time, and `canDraft`. Never the contents, never another user's |
| PUT | `/api/profile` | yes | Upload `cvDocx`, `factBank`, `rulesMd` and `checksYaml` (multipart, all four or nothing). `403` unless you're in `DRAFTING_USERS`; `400 INVALID_PROFILE` names the file and the reason (unknown CV layout, duplicate fact id, an id `checks.yaml` names that isn't in the fact bank, ...) |
| POST | `/api/drafts` | yes | `{opportunityId, coverLetter}`: draft for yourself, replacing your earlier draft of that offer. `403` not allowlisted, `409` no profile / already drafting / deadline passed, `429` 20 drafts today, `503` drafter not configured. Waits for the drafter (up to about two minutes) |
| GET | `/api/drafts` | yes | Your drafts and those shared with you, newest first; `opportunityId` filters. Each has its status, owner, checks, letter text and `profileOutdated` |
| GET | `/api/drafts/:id/cv.docx`, `/cover-letter.docx`, `/cover-letter.txt` | yes | Download a draft's files as `<Company>_<Title>_CV.docx` and so on. `404` for anyone but the owner and their viewers |
| GET | `/api/internships/runs/:id/report.md` | yes | Download a run's Markdown report, exactly as the tracker wrote it (`404` if the run is unknown or has no report) |

### The verifier (`services/verifier`)

A separate service, not under `/api`. Only the tracker calls it.

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/healthz` | no | `{ "status": "ok" }` |
| POST | `/verify` | `Bearer $VERIFIER_TOKEN` | Judge claims against the pages they cite |

A request is an envelope: `request_id` and `run_id` (UUIDs), `time_budget_ms`, `budget` (`max_steps` model calls, `max_fetches` HTTP requests including redirect hops, `max_tokens`) and `payload.claims` (1–20 of `{claim_id, text, source_url}`). A `200` answer is `{request_id, run_id, status, result: {verdicts: [{claim_id, verdict, evidence}]}, usage: {steps, fetches, tokens}, error}`, with `status` `complete` or `partial` (then `error` says why: `time_budget_exhausted`, `fetch_budget_exhausted`, `model_output_invalid`, ...).

| Status | When | Retry? |
| --- | --- | --- |
| 200 | Complete or partial work | no |
| 400 | The body fails the schema | never |
| 401 | Missing or wrong token (checked before the body) | never |
| 409 | A reused `request_id` with a different body | never |
| 500 | Retrying won't help: bad model key, daily quota (`status: failed`) | never |
| 503 | Model rate limit, or the same `request_id` still running. Has `Retry-After` | yes |

### The drafter (`services/drafter`)

A separate service, not under `/api`. Only the backend calls it (`POST /api/drafts` and `python -m app.draft_new`).

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/healthz` | no | `{ "status": "ok" }` |
| POST | `/draft` | `Bearer $DRAFTER_TOKEN` | Tailor the CV (and a letter) to one posting |

The envelope is the verifier's, with `payload: {posting_url, company, title, cover_letter, profile: {cv_docx_b64, fact_bank_yaml, rules_md, checks_yaml}}` (CV at most 2 MB, text files at most 200 KB). A `200` answer carries `result: {role_type, cv_docx_b64, cover_letter_docx_b64, cover_letter_text, checks: [{name, outcome, detail}], model}`; `partial` with `error.code` `posting_unreachable`, `does_not_fit` or `invalid_profile` has no CV. Statuses and retries follow the verifier's table above; a `429` from Anthropic becomes `503` with its `Retry-After`, a bad key or spend cap `500`.

## Conventions

- **Accounts have no email.** A user is identified by their username, which is also what they log in with. Usernames are 3-30 letters, digits, `_` or `.`, case-insensitive and stored lowercased.
- **Register** needs a `username` and a `password` (8-128 characters). `firstName` (defaults to the username) and `lastName` (defaults to empty) are optional.
- **Log in** with `{ "username": …, "password": … }`. An unknown or malformed username and a wrong password all get the same `401 INVALID_CREDENTIALS` ("Invalid username or password").
- **JSON is camelCase.** Users are returned as `id`, `username`, `firstName`, `lastName`, `createdAt`, `updatedAt` and nothing else.
- **Extra keys are ignored.** Request bodies may contain keys an endpoint doesn't define; they're dropped, never stored, and don't cause a `400`.
- **Errors** always look like `{ "error": { "code", "message", "details"? } }`. Invalid bodies are `400 VALIDATION_ERROR`, with `details` listing each field path and rule (never the submitted value).

| Status | Code | When |
| --- | --- | --- |
| 400 | `VALIDATION_ERROR` | Body isn't JSON or fails validation |
| 401 | `UNAUTHORIZED` | Missing, malformed, unknown, expired or revoked token |
| 401 | `INVALID_CREDENTIALS` | Login with an unknown username or wrong password |
| 403 | `INVALID_PASSWORD` | Wrong current password on change-password |
| 404 | `NOT_FOUND` | Unknown route, or a `/api/users/:id` that isn't your own |
| 405 | `METHOD_NOT_ALLOWED` | Wrong method on a known route |
| 409 | `USERNAME_TAKEN` | Register or rename to a username that exists |
| 500 | `INTERNAL` | Unexpected server error |

Why some of these are `404`/`403` rather than the more obvious status is explained in [architecture.md](architecture.md#security-decisions).

## Web UI

Open <http://localhost:5173>. Signed-out visitors are sent to the login page and come back to the page they asked for after signing in.

| Path | What it is |
| --- | --- |
| `/login` | Sign in with your username |
| `/register` | Create an account (you're signed in straight away) |
| `/` | Home (signed in), with a link to the API reference |
| `/account` | Change your username, name or password, or delete your account; upload your applicant profile if you're allowed to draft (signed in) |
| `/internships` | The latest daily internship report: new since last run, still in top K, dropped (closed or outranked) and also open, each top-K offer with its claims labeled Supported, Unsupported, Unreachable or Unverified (supported ones quote their evidence), with an "Export" button, an "Apply" link on every open offer, links to the run history and this run's articles, and on each open offer the drafts you may read (status, owner, Download CV and cover letter, Copy letter text, Checks), "Draft application" or "Draft again" with "Include cover letter" if you may draft, and "Deadline passed" when it has (signed in) |
| `/internships/history` | Every published run: when, its status (complete or partial), which service failed if any, what changed (offers per section) and its articles per status (signed in) |
| `/internships/runs/:id` | One run's report and the articles it tried to read, each with its status and reason (signed in) |

Titles, URLs, reasons, claims and evidence from the tracker came from the web. They are rendered as text, never HTML, and a URL is a link only when it is `http` or `https`, so a rejected `javascript:` URL shows as text.

## Tracker tables

The daily workflow writes these; the API only reads them. One user's view is everyone's: the tracker is one shared run, not per-user data.

| Table | One row per | Columns |
| --- | --- | --- |
| `tracker_runs` | Published run | `id` (the tracker's run id), `topic`, `status`, `stop_reason`, `failed_services` (e.g. `{verifier}`), `started_at`, `ended_at`, `report_markdown`, `published_at` |
| `internship_offers` | Opportunity in a run's report | `run_id` → `tracker_runs`, `opportunity_id` (stable across runs), `section` (`new`, `top_k`, `dropped`, `open`), `rank`, `previous_rank`, `top_k`, `drop_reason`, the record's fields, `summary`, `status`, `status_evidence`, `verified`, `claims` (JSONB, top K only: `[{field, text, verdict, evidence}]`), `first_seen_at` |
| `tracker_articles` | Document a run tried to read | `run_id` → `tracker_runs`, `stage`, `kind` (`page`, `board`, `posting`), `url`, `title`, `status`, `reason`, `fetched_at` |

## Profile and draft tables

Written by the API and `python -m app.draft_new`. Personal data: see [architecture.md](architecture.md#worker-services).

| Table | One row per | Columns |
| --- | --- | --- |
| `applicant_profiles` | User with a profile | `user_id` → `users` (PK), `cv_docx` (bytea), `fact_bank`, `rules_md`, `checks_yaml`, `files` (JSONB: size and SHA-256 per file), `viewer_ids` (uuid[]), `uploaded_at` |
| `application_drafts` | User and opportunity (unique) | `id` (in download URLs), `user_id` → `users`, `opportunity_id`, `company`, `title`, `cover_letter`, `status` (`pending`, `ready`, `partial`, `failed`), `cv_docx`, `letter_docx`, `letter_text`, `role_type`, `checks` (JSONB), `error`, `model`, `profile_hash`, `request_id`, `created_at`, `starts_day` and `starts` (for the daily cap) |

Deleting a user deletes their profile and drafts.

Deleting a run deletes its offers and articles (`ON DELETE CASCADE`); publishing a run again replaces them.

**Known limitations:** there's no password reset and no login rate limiting.
