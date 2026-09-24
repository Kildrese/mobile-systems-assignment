# mobile-systems-assignment

User accounts for the Mobile Systems coursework at NYU: register, log in with a username, and manage your account. Two apps in one repository:

- **`backend/`**: a JSON API in Python with [FastAPI](https://fastapi.tiangolo.com), SQLAlchemy 2, Alembic and PostgreSQL. Authentication is written in the project: argon2id password hashes and hashed, expiring session tokens.
- **`frontend/`**: a single-page app with Vite, React, React Router, Tailwind CSS and shadcn/ui. It only talks to the backend over HTTP, from another origin.

This project uses [OpenSpec](https://github.com/Fission-AI/OpenSpec) for spec-driven development. Proposed changes live under `openspec/changes/`, and approved specs live under `openspec/specs/`.

## Local setup

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) with Compose v2 (Docker Desktop is fine), **running**
- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- [Node.js](https://nodejs.org/) 20.19+ (22 or 24 recommended) and npm
- A bash shell (macOS/Linux, or WSL / Git Bash on Windows)
- For `scripts/api-smoke.sh`: `curl` and `jq`

### One command

```bash
./scripts/start.sh
```

This will:

1. create `.env`, `backend/.env` and `frontend/.env` from their `.env.example` files if they don't exist,
2. install the backend (`uv sync`) and frontend (`npm install`) dependencies if they're missing,
3. start Postgres and wait until it's healthy,
4. apply pending migrations,
5. create the test account (username `NYUgrader`, password `Courant2026!`) if it doesn't exist yet,
6. start the backend at <http://localhost:8000> and the frontend at <http://localhost:5173>.

Ctrl-C stops both servers. The database keeps running; stop it with `./scripts/db-down.sh`.

### Individual scripts

All scripts can be run from any directory.

| Script | What it does |
| --- | --- |
| `scripts/db-up.sh` | Start the Postgres container and wait until it's healthy |
| `scripts/db-down.sh` | Stop the container (data is kept) |
| `scripts/db-down.sh --reset` | Stop the container **and delete all data** |
| `scripts/db-migrate.sh` | Apply pending migrations (`alembic upgrade head`) |
| `scripts/db-seed.sh` | Create the test account unless it exists |
| `scripts/dev-backend.sh` | Start the FastAPI dev server (auto-reload) on port 8000 |
| `scripts/dev-frontend.sh` | Start the Vite dev server on port 5173 |
| `scripts/start.sh` | All of the above, in order |
| `scripts/api-smoke.sh` | Test every endpoint and security rule against the running backend |

### Without the scripts

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

Checks, as CI runs them:

```bash
# backend/
uv run ruff check && uv run ruff format --check
uv run python -m app.openapi --check        # openapi/openapi.json is up to date
uv run alembic check                        # models and migrations agree

# frontend/
npm run api:check                           # src/api matches openapi/openapi.json
npm run typecheck && npm run lint && npm run build
```

### Configuration

Each `.env` file is git-ignored; each `.env.example` next to it has working local defaults. These credentials are for local development only.

| File | Variable | Purpose |
| --- | --- | --- |
| `.env` | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT` | The Docker Compose database |
| `backend/.env` | `DATABASE_URL` | Postgres connection string (required; must match the values above) |
| | `DATABASE_URL_UNPOOLED` | Optional direct connection string; migrations use it when set (Neon) |
| | `CORS_ORIGINS` | Comma-separated frontend origins allowed to call the API (`http://localhost:5173`) |
| | `SESSION_TTL_DAYS` | Days of inactivity after which a token expires (default `7`) |
| `frontend/.env` | `VITE_API_URL` | The backend's origin (`http://localhost:8000`), read at build time |

If port `5432` is taken (for example by a locally installed Postgres), set `POSTGRES_PORT=5433` in `.env` and the same port in `backend/.env`'s `DATABASE_URL`, then restart the database with `./scripts/db-down.sh && ./scripts/db-up.sh`.

### Changing the database schema

1. Edit the models in `backend/app/models.py`.
2. Generate a migration: `uv run alembic revision --autogenerate -m "what changed"` in `backend/` (writes a file to `backend/alembic/versions/`). Review it.
3. Apply it: `./scripts/db-migrate.sh`.
4. Commit the model change and the migration. Never edit a migration that has already run in production.

Inspect the database with `docker compose exec db psql -U postgres -d app` or any Postgres client.

### Changing the API

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
frontend/               Vite + React SPA
  src/api/              generated by @hey-api/openapi-ts (don't edit)
  src/components/       ui/ (shadcn/ui), auth/, account/, layout/
  src/lib/              API client setup, token storage, auth context, form helpers
  src/routes/           pages, layouts and the route guards
  vite.config.ts        includes the Content-Security-Policy build plugin
openapi/openapi.json    the contract: written by the backend, read by the frontend
scripts/                dev, database and smoke-test scripts
```

## Architecture

The frontend (<http://localhost:5173>) and the backend (<http://localhost:8000>) are **separate origins**, as they are in production. Every call from the browser is a cross-origin request.

- **CORS:** the backend answers only origins listed in `CORS_ORIGINS`. It allows `GET`, `POST`, `PATCH` and `DELETE` with the `Authorization` and `Content-Type` headers, never sends `Access-Control-Allow-Credentials` (no cookies are involved), and adds the headers to error responses too, so the browser can read a `401`. Other origins get no CORS headers.
- **Bearer token in `localStorage`:** after login the frontend stores the token under `token` and sends it as `Authorization: Bearer <token>` to protected endpoints only. A `401` from any call removes the token and shows `/login?next=<current page>`. Route protection in the browser only decides what to show; the backend checks the token on every request.
- **Content-Security-Policy:** production builds carry a CSP `<meta>` tag that allows scripts only from the app's own origin (no inline scripts, no `eval`) and network requests only to itself and `VITE_API_URL`. Inline styles are allowed, because Radix's dialogs and menus insert computed `<style>` elements. `frontend/vercel.json` adds `frame-ancestors 'none'`. The dev server doesn't enforce the policy, because hot reload needs inline scripts. Lint forbids `dangerouslySetInnerHTML`.

A token in `localStorage` can be read by any script running on the page, so XSS is the main risk to it. React's escaping, the ban on `dangerouslySetInnerHTML` and the strict `script-src` are the defence, and a stolen token can be revoked on the server by logging out or changing the password. A cookie set by the backend would be a cross-site cookie (`SameSite=None`), which browsers increasingly block.

## Web UI

Open <http://localhost:5173>. Signed-out visitors are sent to the login page and come back to the page they asked for after signing in.

| Path | What it is |
| --- | --- |
| `/login` | Sign in with your username |
| `/register` | Create an account (you're signed in straight away) |
| `/` | Home (signed in), with a link to the API reference |
| `/account` | Change your username, name or password, or delete your account (signed in) |

**Known limitation:** there's no password reset.

## API

Protected endpoints take `Authorization: Bearer <token>`, where the token comes from `POST /api/auth/login`.

Accounts have no email: a user is identified by their username, which is also what they log in with. Usernames are 3-30 letters, digits, `_` or `.`, case-insensitive and stored lowercased.

- **Register** needs a `username` and a `password`. `firstName` (defaults to the username) and `lastName` (defaults to empty) are optional.
- **Log in** with `{ "username": …, "password": … }`. An unknown or malformed username and a wrong password all get the same `401 INVALID_CREDENTIALS` ("Invalid username or password").
- **Extra keys are ignored.** Request bodies may contain keys an endpoint doesn't define; they're dropped, never stored, and don't cause a `400`.
- **Errors** always look like `{ "error": { "code", "message", "details"? } }`. Invalid bodies are `400 VALIDATION_ERROR`, with `details` listing each field path and rule (never the submitted value).

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/healthz` | no | Liveness check, returns `{ "status": "ok" }` |
| POST | `/api/auth/register` | no | Create an account (`201`, no token) |
| POST | `/api/auth/login` | no | Get a bearer token and the user |
| GET | `/api/auth/me` | yes | The logged-in user |
| POST | `/api/auth/logout` | yes | Revoke the current token (`204`) |
| POST | `/api/auth/change-password` | yes | Needs the current password. Revokes every session and returns a new `token` |
| GET / PATCH / DELETE | `/api/users/:id` | yes | Read, update (username, first and last name) or delete your own account |

### API docs

- <http://localhost:8000/docs>: Swagger UI. Log in with "Try it out" on `POST /api/auth/login`, then paste the token under "Authorize" to call protected endpoints.
- <http://localhost:8000/api/openapi.json>: the OpenAPI 3.1 document, identical to the committed `openapi/openapi.json`.

### Security decisions

1. **Passwords are hashed with argon2id** ([pwdlib](https://github.com/frankie567/pwdlib), argon2-cffi's defaults: 64 MiB, 3 iterations, 4 lanes, above OWASP's minimums), with a random salt per hash. Hashes live only in `user_passwords`, never on `users`. A login for an unknown user still verifies the password against a dummy hash, so response times don't reveal which accounts exist.
2. **Password hashes are never returned.** Every route declares a Pydantic `response_model`, and the `User` model is an allow-list (`id`, `username`, `firstName`, `lastName`, `createdAt`, `updatedAt`): even when a route returns a database row, nothing else is serialized. Unexpected errors return a generic `500` and are logged without the request body.
3. **Session tokens are random and stored hashed.** A token is 32 random bytes (`secrets.token_urlsafe`); the database keeps only its SHA-256, so a leaked database can't be used to log in. A token expires after `SESSION_TTL_DAYS` (7) days without use; using it extends the expiry, at most once a day. Logout deletes that session; a password change deletes all of the user's sessions and issues one new token; deleting the account cascades to its password and sessions.
4. **A missing, bad or expired token returns `401`.** Only a well-formed `Authorization: Bearer <token>` header is accepted; cookies are ignored. Unknown, expired and revoked tokens, and the token of a deleted user, all get the same `401 UNAUTHORIZED`.
5. **You can't touch another user's account; we return `404`, not `403`.** `/api/users/:id` compares `:id` with the caller's own id before looking anything up. Another user's id, an id that doesn't exist and a value that isn't a UUID all get the same `404 NOT_FOUND`. A `403` would confirm that the id belongs to a real account.
6. **A wrong current password returns `403`, not `401`.** On change-password, `403 INVALID_PASSWORD` keeps clients from mistaking a typo for an expired token and signing the user out.

Login rate limiting is not implemented yet.

### Test account

`./scripts/start.sh` and `./scripts/db-seed.sh` create a user for graders: username **`NYUgrader`**, password **`Courant2026!`** (first name NYU, last name Grader). Seeding again leaves it unchanged.

## Deployment

Production is being moved to two deployments (frontend and backend on separate origins, with the Neon database reset); see the deployment tasks in `openspec/changes/split-fastapi-vite/tasks.md`. Migrations run against Neon's direct connection string: `./scripts/db-migrate-neon.sh` reads `DATABASE_URL_UNPOOLED` from `.env.neon`. When a migration drops something the running code still reads (such as `users.email`), deploy first and migrate second, once both production deployments are ready.

GitHub Actions (`.github/workflows/ci.yml`) runs on every pull request and every push to `master`:

- **backend:** ruff, the OpenAPI check, migrations and `alembic check` against a Postgres 17 service container, then the smoke test against a running server;
- **frontend:** the API client check, typecheck, lint and build.

## Working with OpenSpec

To propose a new change with OpenSpec (via Claude Code):

```
/opsx:propose "your idea"
```
