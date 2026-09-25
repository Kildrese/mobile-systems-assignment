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

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs on every pull request and every push to `master`, with no secrets:

- **backend:** ruff lint and format, the OpenAPI check, migrations and `alembic check` against a Postgres 17 service container, then `scripts/api-smoke.sh` against a running server;
- **frontend:** the API client check, typecheck, lint and build.

To run the same checks locally, see [development.md](development.md#checks).
