## Why

The class project needs a working foundation before any features can be built: a database, a web app that talks to it, and a repeatable way to manage the schema. Setting this up now, with one-command scripts, means anyone on the team can clone the repo and have the full stack running locally end to end.

## What Changes

- Add a `docker-compose.yml` that runs a PostgreSQL container with a persistent volume, configured through environment variables.
- Scaffold a Next.js app (App Router) with TypeScript, run locally via `npm` (not containerized).
- Add Drizzle ORM and drizzle-kit: a schema file, a database client, generated SQL migrations, and a migration command.
- Include a minimal example table and a page/route that reads from the database to prove the stack works end to end.
- Add an `.env.example` documenting the required variables (e.g. `DATABASE_URL`, Postgres credentials).
- Add shell scripts to start/stop the database, run migrations, start the Next.js dev server, and bring up the whole stack in one step.
- Add a short README section describing the local setup.

## Capabilities

### New Capabilities
- `local-database`: PostgreSQL running in a Docker container via docker-compose, with persistent data and env-based configuration.
- `web-app`: Next.js + TypeScript application run locally with npm, able to query the database.
- `db-migrations`: Drizzle schema definitions, generated migrations, and a command to apply them to the local database.
- `dev-scripts`: Shell scripts to start/stop the database, run migrations, and start the dev server, including a single command for the full local stack.

### Modified Capabilities
<!-- None: no existing specs. -->

## Impact

- **New files/directories**: Next.js app source, `docker-compose.yml`, `drizzle.config.ts`, schema and migration folders, `scripts/*.sh`, `.env.example`, README updates.
- **Dependencies**: `next`, `react`, `react-dom`, `typescript`, `drizzle-orm`, `drizzle-kit`, `postgres` (or `pg`) driver.
- **System requirements**: Docker (with Compose) and Node.js/npm installed on the developer machine.
- **No existing code affected**: the repo currently contains only OpenSpec setup.
