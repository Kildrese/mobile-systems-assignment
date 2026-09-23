# mobile-systems-assignment

Repository for the Mobile Systems coursework at NYU.

This project uses [OpenSpec](https://github.com/Fission-AI/OpenSpec) for spec-driven development. Proposed changes live under `openspec/changes/`, and approved specs live under `openspec/specs/`.

## Local setup

The stack is a Next.js (App Router, TypeScript) app that runs on your machine with npm, a PostgreSQL 17 database in Docker, and [Drizzle ORM](https://orm.drizzle.team) for the schema and migrations.

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) with Compose v2 (Docker Desktop is fine), **running**
- [Node.js](https://nodejs.org/) 20+ and npm
- A bash shell (macOS/Linux, or WSL / Git Bash on Windows)

### One command

```bash
./scripts/start.sh
```

This will:

1. create `.env` from `.env.example` if it doesn't exist,
2. run `npm install` if `node_modules` is missing,
3. start Postgres and wait until it's healthy,
4. apply pending migrations,
5. start the dev server at <http://localhost:3000>.

### Individual scripts

All scripts can be run from any directory.

| Script | What it does |
| --- | --- |
| `scripts/db-up.sh` | Start the Postgres container and wait until it's healthy |
| `scripts/db-down.sh` | Stop the container (data is kept) |
| `scripts/db-down.sh --reset` | Stop the container **and delete all data** |
| `scripts/db-migrate.sh` | Apply pending migrations |
| `scripts/dev.sh` | Start the Next.js dev server |
| `scripts/start.sh` | All of the above, in order |

### Changing the database schema

1. Edit `src/db/schema.ts`.
2. Generate a SQL migration: `npm run db:generate` (writes a new file to `drizzle/`).
3. Apply it: `npm run db:migrate` (or `./scripts/db-migrate.sh`).
4. Commit both the schema change and the generated files in `drizzle/`.

Use `npm run db:studio` to browse the database in Drizzle Studio.

### Configuration and ports

All configuration lives in `.env`, which is git-ignored. Docker Compose, Drizzle, and Next.js all read it. The defaults in `.env.example` are for local development only; don't reuse these credentials anywhere else.

If port `5432` is already taken (for example by a locally installed Postgres), change the port in both places in `.env`:

```dotenv
POSTGRES_PORT=5433
DATABASE_URL=postgres://postgres:postgres@localhost:5433/app
```

Then restart the database with `./scripts/db-down.sh && ./scripts/db-up.sh`.

Authentication uses two more variables:

| Variable | Purpose |
| --- | --- |
| `BETTER_AUTH_SECRET` | Signs session tokens. The value in `.env.example` is a local-only placeholder; generate a real one (`openssl rand -base64 32`) for any deployed environment. |
| `BETTER_AUTH_URL` | The app's base URL, `http://localhost:3000` locally. |

If you created `.env` before these were added, copy them over from `.env.example`.

### Without the scripts

The scripts are thin wrappers around these commands (run from the repo root):

```bash
cp .env.example .env         # once
npm install                  # once
docker compose up -d         # start Postgres
npm run db:migrate           # apply migrations
npm run dev                  # http://localhost:3000

docker compose down          # stop Postgres (keep data)
docker compose down -v       # stop Postgres and delete data
npm run typecheck            # type-check the project
```

## API

The app is a JSON API. Protected endpoints take `Authorization: Bearer <token>`, where the token comes from `POST /api/auth/login`.

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/healthz` | no | Liveness check, returns `{ "status": "ok" }` |
| POST | `/api/auth/register` | no | Create an account |
| POST | `/api/auth/login` | no | Get a bearer token |
| GET | `/api/auth/me` | yes | The logged-in user |
| GET / PATCH / DELETE | `/api/users/:id` | yes | Read, rename or delete your own account |

### API docs

- <http://localhost:3000/docs>: an interactive reference (Scalar). Log in with "Try it", then paste the token under the bearer auth settings to call protected endpoints.
- <http://localhost:3000/api/openapi.json>: the OpenAPI 3.1 document.

The document is generated from the Zod contracts in `src/lib/api/contracts.ts`, which also validate requests and shape responses. A copy is committed at `openapi/openapi.json` so API changes show up in diffs:

| Script | What it does |
| --- | --- |
| `npm run openapi:generate` | Rewrite `openapi/openapi.json` from the contracts (no server or database needed) |
| `npm run openapi:check` | Fail if `openapi/openapi.json` is out of date |

Run `npm run openapi:generate` and commit the result whenever you change a contract.

`scripts/api-smoke.sh` exercises every endpoint and security rule with curl against the running dev server (needs `jq`).

### Security decisions

The API enforces three rules. Each one is enforced in a single shared place, so a new route can't silently skip it:

1. **Password hashes are never returned.** Hashes live only in `account.password`, never on `user`. Every response goes through `handle()` (`src/lib/api/handler.ts`), which parses the handler's result through the contract's response schema. The `User` schema is an allow-list (`id`, `email`, `firstName`, `lastName`, `createdAt`, `updatedAt`), and Zod strips every other key. So even if a handler passes a raw database row or Better Auth's user object, nothing else leaves the server. Validation errors report only the field path and rule, never the submitted value. Unexpected errors return a generic `500` with no message or stack trace.
2. **A missing, bad or expired token returns `401`.** `handle()` resolves the session for every protected route. It accepts only a well-formed `Authorization: Bearer <token>` header and passes just that header to Better Auth, so the API is bearer-only and cookies are ignored. Unknown, expired or revoked tokens, and the token of a deleted user, all return `401`, never `200` or `500`.
3. **You can't touch another user's account; we return `404`, not `403`.** `GET`, `PATCH` and `DELETE /api/users/:id` compare `:id` with the caller's own id before any database access. Another user's id, an id that doesn't exist, and a value that isn't a UUID all get the same `404 NOT_FOUND` body. A `403` would confirm that the id belongs to a real account, letting anyone with a token probe which user ids exist. With `404`, "not yours" and "doesn't exist" can't be told apart, by content or by timing, since no lookup happens in either case.

Sessions last Better Auth's default of 7 days, and the expiry is extended as the token is used. Deleting an account cascades to its credentials and sessions, so its tokens stop working immediately. Better Auth's own HTTP routes are not mounted: our endpoints call its server API directly, so the endpoints above are the whole public surface. Login rate limiting is not implemented yet.

## Working with OpenSpec

To propose a new change with OpenSpec (via Claude Code):

```
/opsx:propose "your idea"
```
