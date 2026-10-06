# Deployment and CI

## Production

Production runs on Vercel as two projects on separate origins, with a Neon Postgres database:

| Project | Root | Notes |
| --- | --- | --- |
| `mobile-systems-api` | `backend/` | FastAPI, detected from `app/main.py`. Env: `DATABASE_URL` (Neon pooled), `DATABASE_URL_UNPOOLED` (direct), `CORS_ORIGINS` (the frontend's URL) |
| `mobile-systems-assignment` | `frontend/` | Vite static site. Env: `VITE_API_URL` (the backend's URL). `vercel.json` adds the SPA rewrite and security headers |

The design and rollout history is in `openspec/changes/archive/2026-09-24-split-fastapi-vite/`.

## Production migrations

Migrations run against Neon's direct (unpooled) connection, since the pooled endpoint runs PgBouncer in transaction mode:

```bash
./scripts/db-migrate-neon.sh        # reads DATABASE_URL_UNPOOLED from .env.neon (git-ignored)
```

Order matters. When a migration drops something the running code still reads (such as `users.email`), **deploy first and migrate second**. When it adds something the new code needs, migrate first.

## Daily internship tracker

`.github/workflows/tracker.yml` runs the tracker once a day, then `python -m app.publish_report` copies the latest finished run into Neon: one `tracker_runs` row (status, times, the Markdown report), one `internship_offers` row per offer in the report, with its section (`new`, `top_k`, `dropped`, `open`), rank and fields, and one `tracker_articles` row per document the run tried to read. The API serves them read-only (`/api/internships/latest`, `/runs`, `/runs/:id`, `/runs/:id/articles`), and no user can start a run. A manual run is "Run workflow" on the Actions tab.

It needs the repository secrets `GROQ_API_KEY`, `TAVILY_API_KEY` and `DATABASE_URL` (Neon, pooled), and the tracker migrations (`tracker_runs`, `tracker_articles`) applied to production first (`./scripts/db-migrate-neon.sh`). The tracker's SQLite state is carried between days in the Actions cache; if the cache is evicted, the next run starts fresh and lists every open offer as new once. Reports and traces are kept as run artifacts for 14 days.

### What starts the daily run

The workflow's only trigger is `workflow_dispatch`. GitHub's `schedule` never started a run of it, so the backend starts it instead:

1. A Vercel Cron Job on `mobile-systems-api` (`backend/vercel.json`, `0 9 * * *`) calls `GET /api/internal/tracker-dispatch` once a day. On the Hobby plan it fires anywhere between 09:00 and 09:59 UTC.
2. The route answers `404`, like any unknown path, unless the request carries `Authorization: Bearer $CRON_SECRET`, which Vercel adds to its cron calls. It isn't in the OpenAPI document.
3. It claims the UTC day in `tracker_dispatches` with one atomic insert. Only the call that gets the claim goes on. A repeated or simultaneous call answers `already_dispatched`, so a day never starts two runs. A `failed` day, or a claim stuck for over 5 minutes, can be claimed again.
4. It calls GitHub's `workflow_dispatch` for `tracker.yml` on `master`. `204` marks the day `dispatched` (the route answers `202`). Anything else marks it `failed` with GitHub's status and message, and the route answers `502`, which shows as a failed cron in Vercel's logs.

Env vars on the backend project (Production only; leave them unset locally and in previews, where the route then answers `404`):

| Variable | Value |
| --- | --- |
| `CRON_SECRET` | A random string of at least 16 characters (`openssl rand -hex 32`) |
| `GITHUB_DISPATCH_TOKEN` | A fine-grained personal access token: repository access only `mobile-systems-assignment`, permission Actions: read and write, expiry at most a year |

The migration that creates `tracker_dispatches` has to run on Neon before the code that uses it deploys (`./scripts/db-migrate-neon.sh`).

**Rotating the token.** Create a new token with the same settings before the old one expires, replace `GITHUB_DISPATCH_TOKEN` in Vercel, redeploy, then delete the old token in GitHub. An expired token shows up as `failed` days with `401: Bad credentials`.

**Checking a day.** `gh run list -w tracker.yml` lists the day's run, started by the token's owner. In Neon, `select * from tracker_dispatches order by day desc limit 7` shows each day's status, attempts and last error. To start a missed day, use "Run workflow" on the Actions tab, or call the route with the secret if the day's row is `failed`:

```bash
curl -i -H "Authorization: Bearer $CRON_SECRET" https://<backend>/api/internal/tracker-dispatch
```

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs on every pull request and every push to `master`, with no secrets:

- **backend:** ruff lint and format, the OpenAPI check, migrations and `alembic check` against a Postgres 17 service container, then the pytest suite (in its own `app_test` database on that server);
- **tracker:** ruff lint and format, then the tracker's tests (`pytest tests_tracker`) with no services and no network: every provider is faked;
- **frontend:** the API client check, typecheck, Vitest, lint and build.

To run the same checks locally, see [development.md](development.md#checks).
