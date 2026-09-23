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

The home page shows a list of notes and a form for adding one. It's a small demo that proves the app can read from and write to the database.

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

## Working with OpenSpec

To propose a new change with OpenSpec (via Claude Code):

```
/opsx:propose "your idea"
```
