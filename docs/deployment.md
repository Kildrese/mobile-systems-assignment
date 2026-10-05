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

`.github/workflows/tracker.yml` runs the tracker every day at 09:17 UTC (5:17 in New York in summer, 4:17 in winter; off the hour, since GitHub may delay or drop scheduled runs at the start of an hour), then `python -m app.publish_report` copies the latest finished run into Neon: one `tracker_runs` row (status, times, the Markdown report) and one `internship_offers` row per offer in the report, with its section (`new`, `open`, `closed`), rank and fields. The API serves them read-only at `GET /api/internships/latest`; no route starts a run. A manual run is "Run workflow" on the Actions tab.

It needs the repository secrets `GROQ_API_KEY`, `TAVILY_API_KEY` and `DATABASE_URL` (Neon, pooled), and the `tracker_runs` migration applied to production first (`./scripts/db-migrate-neon.sh`). The tracker's SQLite state is carried between days in the Actions cache; if the cache is evicted, the next run starts fresh and lists every open offer as new once. Reports and traces are kept as run artifacts for 14 days.

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs on every pull request and every push to `master`, with no secrets:

- **backend:** ruff lint and format, the OpenAPI check, migrations and `alembic check` against a Postgres 17 service container, then the pytest suite (in its own `app_test` database on that server);
- **tracker:** ruff lint and format, then the tracker's tests (`pytest tests_tracker`) with no services and no network: every provider is faked;
- **frontend:** the API client check, typecheck, Vitest, lint and build.

To run the same checks locally, see [development.md](development.md#checks).
