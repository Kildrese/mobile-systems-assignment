## Context

The repository currently contains only the OpenSpec setup. This change lays the foundation for the class project: a PostgreSQL database, a Next.js + TypeScript web app, Drizzle for schema and migrations, and shell scripts that make the local workflow a single command. The target is a developer machine with Docker (Compose v2) and Node.js/npm installed; there is no deployment target yet.

## Goals / Non-Goals

**Goals:**
- A fresh clone can reach a running app that reads from and writes to Postgres with one command (`./scripts/start.sh`).
- Database configuration lives in one place (`.env`) and is shared by Docker Compose, Drizzle, and Next.js.
- Schema changes follow a clear flow: edit the TypeScript schema → generate SQL migration → apply it.
- Scripts are simple, readable bash that students can understand and modify.

**Non-Goals:**
- Containerizing the Next.js app (it runs with `npm run dev` on the host).
- Production deployment, CI, hosting, or secrets management.
- Authentication, real domain models, or UI styling beyond a minimal demo page.
- Automated test suites (may come in a later change).

## Decisions

### Project layout: Next.js app at the repository root
The Next.js app, `docker-compose.yml`, `drizzle.config.ts`, and `.env` all live at the repo root, with scripts in `scripts/`.
- *Why*: A single `.env` is picked up natively by Docker Compose and Next.js, and by drizzle-kit via `dotenv`, so there is no duplicated configuration and `npm` commands work from the root without `cd`.
- *Alternative*: App in a `web/` subfolder (leaves room for a future mobile app). Rejected for now because it requires env sharing across directories; the app can be moved later if a mobile client is added.

### Next.js App Router with Server Components and Server Actions
Use `create-next-app` defaults (App Router, TypeScript, ESLint, `src/` directory). The demo page is a Server Component that queries the database directly; adding a record uses a Server Action.
- *Why*: No separate API layer is needed to prove the stack end to end, and it is the current Next.js default.
- *Alternative*: Pages Router or API routes, which add boilerplate without benefit here.

### Postgres driver: `postgres` (postgres.js) with `drizzle-orm/postgres-js`
- *Why*: Lightweight, no native dependencies, first-class Drizzle support.
- *Alternative*: `pg` (node-postgres); equally valid but slightly more setup.
- The DB client is created once in `src/db/index.ts` and cached on `globalThis` in development to avoid exhausting connections during hot reload.

### Migrations: `drizzle-kit generate` + `drizzle-kit migrate`
Schema lives in `src/db/schema.ts`; SQL migrations are generated into `drizzle/` and committed to git.
- *Why*: Generated SQL files are reviewable and reproducible across every student's machine.
- *Alternative*: `drizzle-kit push` (syncs schema without migration files). Handy for prototyping but leaves no history; it may still be used ad hoc but is not the documented flow.
- npm scripts: `db:generate`, `db:migrate`, `db:studio`.

### Database container: official `postgres:17` image via Docker Compose
- Named volume for persistence, a `pg_isready` healthcheck, and credentials/port taken from `.env` (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT`).
- *Why*: Compose makes start/stop/reset trivial and the healthcheck lets scripts wait until the DB actually accepts connections.

### Environment configuration
`.env.example` is committed; `.env` is git-ignored. `DATABASE_URL` is composed from the same values, e.g. `postgres://postgres:postgres@localhost:5432/app`. Scripts copy `.env.example` to `.env` if it does not exist.

### Shell scripts
All in `scripts/`, bash with `set -euo pipefail`, each resolving the repo root so they work from any directory:
- `db-up.sh`: start the Postgres container and wait until it is healthy.
- `db-down.sh`: stop the container (data kept); `--reset` flag also removes the volume.
- `db-migrate.sh`: apply pending migrations.
- `dev.sh`: start the Next.js dev server.
- `start.sh`: full stack: ensure `.env`, install deps if `node_modules` is missing, `db-up`, `db-migrate`, `dev`.

### Demo table
A single `notes` table (`id` serial PK, `content` text not null, `created_at` timestamp default now). The home page lists notes and has a form to add one, demonstrating reads, writes, and a migration.

## Risks / Trade-offs

- [Port 5432 already used by a locally installed Postgres] → Port is configurable via `POSTGRES_PORT` in `.env`; README mentions it.
- [Docker daemon not running] → `db-up.sh` checks `docker info` first and prints a clear error.
- [Scripts are bash-only; Windows users without WSL/Git Bash can't run them] → Accepted for a class setup; the underlying `docker compose` and `npm` commands are documented in the README.
- [Committed default credentials] → Acceptable for local-only development; `.env` itself is git-ignored and README notes they must not be reused elsewhere.
- [Too many DB connections during hot reload] → Cache the client on `globalThis` in dev.

## Migration Plan

Not applicable — greenfield setup with no existing data or users. Rollback is removing the added files and running `./scripts/db-down.sh --reset`.

## Open Questions

- Should a future mobile client live in this repo? If so, the web app may later move into a subfolder (see layout decision).
