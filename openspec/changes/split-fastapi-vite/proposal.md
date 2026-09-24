## Why

The app is one Next.js project that serves both the web UI and the JSON API from one origin. The UI calls the account code directly through Server Actions, not over HTTP. That hides the network behavior the course is about (cross-origin requests, CORS, token handling in the browser). It also means authentication is delegated to a library (Better Auth) instead of being understood and owned. Splitting into a Python API and a browser-only frontend on separate origins makes those concerns explicit. It also gives future projects, including a mobile client, the same HTTP API the web UI uses.

## What Changes

- **BREAKING** Replace the Next.js app with two apps in one repository:
  - `backend/`: a FastAPI service on its own origin (port 8000 locally) that serves the JSON API, `/healthz`, the OpenAPI document and the API reference.
  - `frontend/`: a Vite + React + React Router single-page app (port 5173 locally) that only talks to the backend over HTTP.
- **BREAKING** Replace Better Auth with hand-written authentication:
  - Passwords are hashed with argon2id.
  - Session tokens are random, stored only as a SHA-256 hash, and expire after 7 days of inactivity (sliding). Logout, password change and account deletion revoke them immediately.
- **BREAKING** Replace Drizzle with SQLAlchemy 2 and Alembic. The new schema has `users`, `user_passwords` and `sessions`:
  - Email is nullable, so users registered without an email are stored with `NULL` instead of a placeholder address.
  - The `name` column is dropped.
- **BREAKING** The web UI stops using a `session` cookie. It keeps the bearer token in `localStorage`, sends it in the `Authorization` header, and protects routes in the browser. The Next.js proxy and Server Actions go away.
- **BREAKING** Pydantic models replace the Zod contracts as the source of truth for request validation, response allow-lists and the OpenAPI document. FastAPI generates the document, and it's committed at `openapi/openapi.json`. The frontend's TypeScript types and API functions are generated from that file with `@hey-api/openapi-ts`.
- The backend configures CORS with an allow-list of frontend origins. It sends no credentials and allows the `Authorization` header.
- The frontend ships a strict Content-Security-Policy in production builds.
- The JSON API keeps its paths, request and response shapes, status codes and error format. `scripts/api-smoke.sh` remains the behavioral contract and is pointed at the new backend.
- The interactive API reference at `/docs` becomes FastAPI's Swagger UI, served by the backend.
- Dev scripts, the README and CI are rewritten for the two apps:
  - Python via `uv` for the backend, npm for the frontend.
  - One `scripts/start.sh` still brings everything up.
  - CI runs the smoke test against a Postgres service container.
- **BREAKING** Production data is wiped. The new schema starts empty, and the old Better Auth and Drizzle tables are dropped from Neon.

## Capabilities

### New Capabilities
- `backend-service`: The FastAPI service: running it locally with `uv`, configuration from environment variables, the database connection, CORS, and error handling (including mapping FastAPI's validation errors to the API's `400 VALIDATION_ERROR` shape).
- `frontend-app`: The Vite SPA: running and building it with npm, the backend URL setting, the generated API client and the CI check that keeps it in sync, token storage in `localStorage`, attaching the bearer header, handling `401`, and the production Content-Security-Policy.

### Modified Capabilities
- `user-auth`: New data model (tables, nullable email, no placeholder email, no `name`), argon2id hashing, hashed session tokens with a 7-day sliding expiry, and register rules without the reserved `no-email.invalid` domain.
- `user-management`: Deleting a user cascades to the new `user_passwords` and `sessions` tables.
- `api-docs`: Pydantic models instead of Zod contracts are the source of truth. The reference at `/docs` is Swagger UI on the backend. The generate and check commands move to the backend (`uv run`).
- `web-auth-ui`:
  - The session cookie is replaced by a `localStorage` token and client-side route protection.
  - Signing out calls `POST /api/auth/logout`.
  - Changing the password stores the new token.
  - The API reference link points to the backend.
- `db-migrations`: Alembic migrations replace Drizzle schema, migrations and Drizzle Studio.
- `dev-scripts`: The scripts start the backend and frontend, migrate with Alembic and seed with Python. `start.sh` runs both apps.
- `local-database`: `DATABASE_URL` moves to `backend/.env.example`, while the root `.env.example` keeps only the Docker Compose variables.
- `web-app`: Removed. The Next.js application is replaced by `backend-service` and `frontend-app`.

## Impact

- **Code:** `src/`, `drizzle/`, `drizzle.config.ts`, `next.config.ts`, `postcss.config.mjs`, `components.json`, `eslint.config.mjs` and the root `package.json` are removed or moved into `frontend/`. New `backend/` (FastAPI, SQLAlchemy, Alembic, pwdlib/argon2) and `frontend/` (Vite, React, React Router, Tailwind, shadcn/ui, hey-api).
- **API:** same endpoints and shapes. Differences:
  - A user without an email is still returned as `"email": null`, but is now stored as `NULL`.
  - Addresses at `no-email.invalid` are no longer rejected.
  - `/docs` becomes Swagger UI.
  - The backend runs on port 8000 locally instead of 3000.
- **Dependencies:** Python 3.12+ and `uv` become prerequisites, alongside Node.js, npm and Docker.
- **Deployment:** Vercel and Neon are reconfigured. The frontend and the backend become separate deployments on separate origins, and Neon's schema is reset. Where the backend is hosted is decided in `design.md`.
- **Tests and CI:** `scripts/api-smoke.sh` changes its base URL and the tables it inspects. GitHub Actions gains a backend job (lint, OpenAPI check, migrations, smoke test against Postgres) and a frontend job (client check, typecheck, lint, build).
