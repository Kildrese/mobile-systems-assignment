# Development

Everything here assumes the [quick start](../README.md#quick-start) works on your machine.

## Scripts

All scripts can be run from any directory.

| Script | What it does |
| --- | --- |
| `scripts/start.sh` | Env files, dependencies, database, migrations and seed, then both dev servers |
| `scripts/db-up.sh` | Start the Postgres container and wait until it's healthy |
| `scripts/db-down.sh` | Stop the container (data is kept) |
| `scripts/db-down.sh --reset` | Stop the container **and delete all data** |
| `scripts/db-migrate.sh` | Apply pending migrations (`alembic upgrade head`) |
| `scripts/db-seed.sh` | Create the test account unless it exists |
| `scripts/dev-backend.sh` | Start the FastAPI dev server (auto-reload) on port 8000 |
| `scripts/dev-frontend.sh` | Start the Vite dev server on port 5173 |
| `scripts/test.sh [backend\|frontend]` | Run the backend and frontend test suites (see [Tests](#tests)) |
| `scripts/db-migrate-neon.sh` | Apply migrations to production (see [deployment](deployment.md)) |

## Without the scripts

```bash
cp .env.example .env                        # once, and the same in backend/ and frontend/
docker compose up -d                        # start Postgres

cd backend
uv sync                                     # install dependencies
uv run alembic upgrade head                 # apply migrations
uv run python -m app.seed                   # create the test account
uv run fastapi dev                          # http://localhost:8000

cd frontend                                 # in another terminal
npm install
npm run dev                                 # http://localhost:5173
```

## Configuration

Each `.env` file is git-ignored; the `.env.example` next to it has working local defaults. These credentials are for local development only.

| File | Variable | Purpose |
| --- | --- | --- |
| `.env` | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT` | The Docker Compose database |
| `backend/.env` | `DATABASE_URL` | Postgres connection string (required; must match the values above) |
| | `DATABASE_URL_UNPOOLED` | Optional direct connection string; migrations use it when set (Neon) |
| | `CORS_ORIGINS` | Comma-separated frontend origins allowed to call the API (`http://localhost:5173`) |
| | `SESSION_TTL_DAYS` | Days of inactivity after which a token expires (default `7`) |
| `frontend/.env` | `VITE_API_URL` | The backend's origin (`http://localhost:8000`), read at build time |

## Tests

```bash
./scripts/test.sh                   # both suites
./scripts/test.sh backend -k login  # pytest only, extra args go to pytest
./scripts/test.sh frontend          # Vitest only
```

- **Backend** (`backend/tests/`, pytest): integration tests through FastAPI's `TestClient` against a real Postgres. They use a separate database, `DATABASE_URL`'s name plus `_test` (e.g. `app_test`), which they create, migrate from scratch on every run, and empty after each test, so your dev data is never touched. The derived URL must be on localhost; set `TEST_DATABASE_URL` to use another server. Every response is checked for leaked password or token hashes. Needs the database running (`./scripts/db-up.sh`; the script does this for you).
- **Frontend** (`frontend/src/**/*.test.ts`, Vitest): unit tests for the logic in `src/lib` (redirect safety, API error mapping, token storage). No DOM or backend needed.

## Checks

CI runs these on every pull request (see [deployment](deployment.md#ci)):

```bash
# backend/
uv run ruff check && uv run ruff format --check
uv run python -m app.openapi --check        # openapi/openapi.json is up to date
uv run alembic check                        # models and migrations agree (needs the database)
uv run pytest                               # tests (needs the database)

# frontend/
npm run api:check                           # src/api matches openapi/openapi.json
npm run typecheck && npm test && npm run lint && npm run build
```

## Changing the database schema

1. Edit the models in `backend/app/models.py`.
2. Generate a migration: `uv run alembic revision --autogenerate -m "what changed"` in `backend/` (writes a file to `backend/alembic/versions/`). Review it.
3. Apply it: `./scripts/db-migrate.sh`.
4. Commit the model change and the migration. Never edit a migration that has already run in production.

Inspect the database with `docker compose exec db psql -U postgres -d app` or any Postgres client.

## Changing the API

The Pydantic models in `backend/app/schemas.py` and the routes in `backend/app/routers/` are the contract. They validate requests, filter responses and generate the OpenAPI document. After changing them:

1. `uv run python -m app.openapi` in `backend/` rewrites `openapi/openapi.json` (no server or database needed).
2. `npm run api:generate` in `frontend/` regenerates the typed client in `frontend/src/api/` from it.
3. Commit all three. CI fails if either generated file is out of date.

## Project layout

```
backend/                FastAPI app (uv project)
  app/
    main.py             app factory: routers, CORS, error handlers, OpenAPI settings
    config.py           settings from environment variables
    db.py               engine (one pool per process) and per-request session
    models.py           SQLAlchemy models: users, user_passwords, sessions
    schemas.py          Pydantic request/response models (the API contract)
    security.py         argon2id hashing, token generation and hashing
    deps.py             bearer-token session and "own user id" dependencies
    errors.py           the error shape and exception handlers
    services/           account rules (register, login, change password, …)
    routers/            health, auth and users endpoints
    openapi.py          `python -m app.openapi [--check]`
    seed.py             `python -m app.seed`
  alembic/              migrations
  tests/                pytest suite
frontend/               Vite + React SPA
  src/api/              generated by @hey-api/openapi-ts (don't edit)
  src/components/       ui/ (shadcn/ui), auth/, account/, layout/
  src/lib/              API client setup, token storage, auth context, form helpers
  src/routes/           pages, layouts and the route guards
  vite.config.ts        includes the Content-Security-Policy build plugin
openapi/openapi.json    the contract: written by the backend, read by the frontend
openspec/               specs and change proposals
scripts/                dev, database and test scripts
docs/                   this documentation
```

## OpenSpec

Changes are proposed, implemented and archived with [OpenSpec](https://github.com/Fission-AI/OpenSpec). In Claude Code:

```
/opsx:propose "your idea"     # write proposal, design, specs and tasks
/opsx:apply                   # implement the tasks
/opsx:archive                 # merge the spec deltas into openspec/specs/ and archive the change
```
