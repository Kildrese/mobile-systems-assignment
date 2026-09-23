## 1. Next.js Project Scaffold

- [x] 1.1 Scaffold a Next.js app at the repo root with `create-next-app` (TypeScript, App Router, ESLint, `src/` directory), preserving the existing `openspec/` and `.claude/` folders
- [x] 1.2 Verify `npm run dev` serves the default page at `http://localhost:3000` and `npx tsc --noEmit` passes
- [x] 1.3 Update `.gitignore` to ignore `.env` (but not `.env.example`)

## 2. Docker Postgres

- [x] 2.1 Create `.env.example` with `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT`, and a matching `DATABASE_URL`
- [x] 2.2 Create `docker-compose.yml` with a `db` service using `postgres:17`, env-based credentials, `${POSTGRES_PORT}:5432` port mapping, a named data volume, and a `pg_isready` healthcheck
- [x] 2.3 Verify `docker compose up -d` starts the container and it reports healthy

## 3. Drizzle Setup and Migrations

- [x] 3.1 Install `drizzle-orm`, `postgres`, and dev dependencies `drizzle-kit`, `dotenv`
- [x] 3.2 Create `drizzle.config.ts` (loads `.env`, schema `src/db/schema.ts`, output `drizzle/`, dialect `postgresql`, `DATABASE_URL` credentials)
- [x] 3.3 Define the `notes` table in `src/db/schema.ts` (`id` serial PK, `content` text not null, `created_at` timestamp default now not null)
- [x] 3.4 Create `src/db/index.ts` exporting a Drizzle client built from `DATABASE_URL`, throwing a clear error if it is missing, and caching the client on `globalThis` in development
- [x] 3.5 Add npm scripts `db:generate`, `db:migrate`, `db:studio`
- [x] 3.6 Run `npm run db:generate` to create the initial migration and commit the `drizzle/` folder
- [x] 3.7 Run `npm run db:migrate` against the local DB, confirm the `notes` table exists, and confirm a second run is a no-op

## 4. Demo Page

- [x] 4.1 Replace `src/app/page.tsx` with a Server Component that lists notes (newest first, content + created time) and shows an empty-state message when there are none
- [x] 4.2 Add a Server Action that validates non-empty trimmed input, inserts a note, and revalidates the page
- [x] 4.3 Add a form on the page wired to the Server Action; mark the page as dynamic so it always reads fresh data
- [x] 4.4 Manually verify adding a note shows it on the page and survives a DB container restart

## 5. Shell Scripts

- [x] 5.1 Create `scripts/db-up.sh`: resolve repo root, check `docker info`, `docker compose up -d`, poll until healthy with a timeout
- [x] 5.2 Create `scripts/db-down.sh`: `docker compose down`, with `--reset` also removing volumes (`-v`)
- [x] 5.3 Create `scripts/db-migrate.sh`: run `npm run db:migrate`
- [x] 5.4 Create `scripts/dev.sh`: run `npm run dev`
- [x] 5.5 Create `scripts/start.sh`: copy `.env.example` → `.env` if missing, `npm install` if `node_modules` is missing, then run db-up, db-migrate, dev in order
- [x] 5.6 Make all scripts executable (`chmod +x`), using `#!/usr/bin/env bash` and `set -euo pipefail`
- [x] 5.7 Verify scripts work when invoked from a subdirectory and that `db-up.sh` fails clearly when Docker is not running

## 6. Documentation and End-to-End Check

- [x] 6.1 Write the README local-setup section: prerequisites, `./scripts/start.sh`, individual scripts, schema-change workflow (edit schema → `db:generate` → `db:migrate`), changing `POSTGRES_PORT`, and the raw `docker compose`/`npm` commands
- [x] 6.2 End-to-end check: `./scripts/db-down.sh --reset`, remove `.env`, run `./scripts/start.sh`, and confirm the notes page loads and can add a note
