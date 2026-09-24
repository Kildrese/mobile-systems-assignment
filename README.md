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

## Web UI

Open <http://localhost:3000>. Signed-out visitors are sent to the login page and come back to the page they asked for after signing in.

| Path | What it is |
| --- | --- |
| `/login` | Sign in with your email or username |
| `/register` | Create an account (you're signed in straight away) |
| `/` | Home (signed in) |
| `/account` | Change your username, name, email or password, or delete your account (signed in) |
| `/docs` | API reference (public) |

The browser session is an `HttpOnly`, `SameSite=Lax` cookie named `session` (`Secure` in production) holding the session token, set by Server Actions. JavaScript can't read it. The JSON API ignores this cookie and stays bearer-only. Forms and API endpoints share one implementation of every account rule (`src/lib/services/account.ts`).

**Known limitation:** email changes take effect immediately and aren't verified by email, because the app doesn't send email yet. There's also no password reset.

### Project layout

```
src/
  app/                  routes (Next.js App Router)
    (protected)/        signed-in pages and their layout: / and /account
    (public)/           signed-out pages and their layout: /login and /register
    api/                JSON API route handlers
    docs/ healthz/      API reference and health check
  actions/              Server Actions used by the web forms
  components/           React components (ui/ is shadcn/ui)
  db/                   Drizzle schema and client
  lib/
    api/                API contracts (Zod), route handler wrapper, OpenAPI
    services/           account rules shared by the API and the web UI
  proxy.ts              redirects signed-out visitors to /login
```

A folder in parentheses is a [route group](https://nextjs.org/docs/app/getting-started/project-structure#route-groups): it groups pages under a shared layout but isn't part of the URL, so `(protected)/account/page.tsx` is served at `/account`.

## Deployment

Production runs on [Vercel](https://vercel.com), with the database on [Neon](https://neon.com) (project `empty-firefly-03102623`, branch `production`).

### One-time setup

1. Install the CLIs and log in: `npm i -g neon vercel`, then `neon login` and `vercel login`.
2. Link the Neon project: `neon link --project-id empty-firefly-03102623 --branch production -y`. This writes the Neon connection strings into `.env`. Move `DATABASE_URL`, `DATABASE_URL_UNPOOLED` and `NEON_BRANCH` into a new `.env.neon`, and put the local `DATABASE_URL` back in `.env`. Otherwise local development and migrations will run against production.
3. Link the Vercel project (`vercel link`) and connect it to the GitHub repository in the Vercel dashboard (Settings → Git).
4. Set these Vercel environment variables (`vercel env add <NAME> production`):

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | Neon's **pooled** connection string (`DATABASE_URL` in `.env.neon`) |
| `BETTER_AUTH_SECRET` | A fresh secret, e.g. `openssl rand -base64 32`. Never the local placeholder. |
| `BETTER_AUTH_URL` | The production URL, e.g. `https://<project>.vercel.app` |
| `DATABASE_URL_UNPOOLED` | Neon's **direct** connection string (`DATABASE_URL_UNPOOLED` in `.env.neon`), used by the production build to run migrations |

These are set for Production only. Preview deployments build, but they have no database yet, so requests that touch it fail. A preview can leave `BETTER_AUTH_URL` unset; the app falls back to the deployment's own URL (`VERCEL_URL`).

### Deploying

Vercel is connected to this GitHub repository and deploys on its own:

- **Push to `master`** (including a merged pull request): a production deployment. Its build command, `scripts/vercel-build.sh` (set in `vercel.json`), runs `next build` and then applies pending migrations to Neon. A failed build never touches the database.
- **Pull request:** a preview deployment. Previews never run migrations, so they can't change the production database.

GitHub Actions (`.github/workflows/ci.yml`) runs typecheck, lint and `openapi:check` on every pull request and every push to `master`. It needs no secrets.

Migrations run just before the new version goes live, so for a moment the old code runs against the new schema. Keep them backwards compatible, for example add a column before the code that uses it and drop columns in a later deploy.

To migrate or deploy by hand, run `./scripts/db-migrate-neon.sh` (uses the direct connection string from `.env.neon`), then `vercel --prod`.

`neon.ts` holds the Neon project policy; apply changes to it with `neon deploy --no-env-pull`. The `--no-env-pull` flag keeps it from overwriting `.env`.

## API

The app is a JSON API. Protected endpoints take `Authorization: Bearer <token>`, where the token comes from `POST /api/auth/login`.

Every user has a username and usually an email, and can log in with either. Usernames are 3-30 letters, digits, `_` or `.`, case-insensitive and stored lowercased (Better Auth's `username` plugin rules).

- **Register** needs a `password` plus a `username`, an `email` or both. `firstName` and `lastName` are optional. Without a username, one is derived from the email. A user without an email is shown with `"email": null`.
- **Log in** with `{ "identifier": …, "password": … }`. `email` or `username` work in place of `identifier`, and each accepts either an email or a username: a value containing `@` is treated as an email.
- **Extra keys are ignored.** Request bodies may contain keys an endpoint doesn't define; they're dropped, never stored, and don't cause a `400`.

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/healthz` | no | Liveness check, returns `{ "status": "ok" }` |
| POST | `/api/auth/register` | no | Create an account |
| POST | `/api/auth/login` | no | Get a bearer token. `identifier` is your email or username |
| GET | `/api/auth/me` | yes | The logged-in user |
| POST | `/api/auth/logout` | yes | Revoke the current token (`204`) |
| POST | `/api/auth/change-password` | yes | Needs the current password. Revokes every session and returns a new `token` |
| POST | `/api/auth/change-email` | yes | Needs the current password. Changes the email immediately (no verification) |
| GET / PATCH / DELETE | `/api/users/:id` | yes | Read, update (username, first and last name) or delete your own account |

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

1. **Password hashes are never returned.** Hashes live only in `account.password`, never on `user`. Every response goes through `handle()` (`src/lib/api/handler.ts`), which parses the handler's result through the contract's response schema. The `User` schema is an allow-list (`id`, `email`, `username`, `firstName`, `lastName`, `createdAt`, `updatedAt`), and Zod strips every other key. So even if a handler passes a raw database row or Better Auth's user object, nothing else leaves the server. Validation errors report only the field path and rule, never the submitted value. Unexpected errors return a generic `500` with no message or stack trace.
2. **A missing, bad or expired token returns `401`.** `handle()` resolves the session for every protected route. It accepts only a well-formed `Authorization: Bearer <token>` header and passes just that header to Better Auth, so the API is bearer-only and cookies are ignored. Unknown, expired or revoked tokens, and the token of a deleted user, all return `401`, never `200` or `500`.
3. **You can't touch another user's account; we return `404`, not `403`.** `GET`, `PATCH` and `DELETE /api/users/:id` compare `:id` with the caller's own id before any database access. Another user's id, an id that doesn't exist, and a value that isn't a UUID all get the same `404 NOT_FOUND` body. A `403` would confirm that the id belongs to a real account, letting anyone with a token probe which user ids exist. With `404`, "not yours" and "doesn't exist" can't be told apart, by content or by timing, since no lookup happens in either case.

Sessions last Better Auth's default of 7 days, and the expiry is extended as the token is used. Deleting an account cascades to its credentials and sessions, so its tokens stop working immediately. Better Auth's own HTTP routes are not mounted: our endpoints call its server API directly, so the endpoints above are the whole public surface. Login rate limiting is not implemented yet.

A wrong current password on change-password or change-email returns `403 INVALID_PASSWORD`, not `401`, so clients don't mistake a typo for an expired token and sign the user out. After changing the password, store the token from the response: all older tokens stop working.

## Working with OpenSpec

To propose a new change with OpenSpec (via Claude Code):

```
/opsx:propose "your idea"
```
