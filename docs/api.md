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
| GET | `/api/internships/runs/:id/report.md` | yes | Download a run's Markdown report, exactly as the tracker wrote it (`404` if the run is unknown or has no report) |

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
| `/account` | Change your username, name or password, or delete your account (signed in) |
| `/internships` | The latest daily internship report: new since last run, still in top K, dropped (closed or outranked) and also open, with an "Export" button, an "Apply" link on every open offer, and links to the run history and this run's articles (signed in) |
| `/internships/history` | Every published run: when, its status, what changed (offers per section) and its articles per status (signed in) |
| `/internships/runs/:id` | One run's report and the articles it tried to read, each with its status and reason (signed in) |

Titles, URLs and reasons from the tracker came from the web. They are rendered as text, never HTML, and a URL is a link only when it is `http` or `https`, so a rejected `javascript:` URL shows as text.

## Tracker tables

The daily workflow writes these; the API only reads them. One user's view is everyone's: the tracker is one shared run, not per-user data.

| Table | One row per | Columns |
| --- | --- | --- |
| `tracker_runs` | Published run | `id` (the tracker's run id), `topic`, `status`, `stop_reason`, `started_at`, `ended_at`, `report_markdown`, `published_at` |
| `internship_offers` | Opportunity in a run's report | `run_id` → `tracker_runs`, `opportunity_id` (stable across runs), `section` (`new`, `top_k`, `dropped`, `open`), `rank`, `previous_rank`, `top_k`, `drop_reason`, the record's fields, `summary`, `status`, `status_evidence`, `verified`, `first_seen_at` |
| `tracker_articles` | Document a run tried to read | `run_id` → `tracker_runs`, `stage`, `kind` (`page`, `board`, `posting`), `url`, `title`, `status`, `reason`, `fetched_at` |

Deleting a run deletes its offers and articles (`ON DELETE CASCADE`); publishing a run again replaces them.

**Known limitations:** there's no password reset and no login rate limiting.
