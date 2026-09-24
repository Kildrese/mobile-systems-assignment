## 1. Backend scaffold

- [x] 1.1 Create `backend/` as a uv project (Python ≥3.12): fastapi[standard], sqlalchemy, psycopg[binary], alembic, pydantic-settings, pwdlib[argon2]; dev: ruff. Commit `uv.lock`
- [x] 1.2 Add `app/config.py` (pydantic-settings: `DATABASE_URL` required with a clear error, `CORS_ORIGINS` list, `SESSION_TTL_DAYS=7`), `backend/.env.example`, and ignore `backend/.env` and `.venv`
- [x] 1.3 Add `app/db.py`: engine with psycopg (`prepare_threshold=None`, `pool_size=5`, `pool_pre_ping`), a session factory, and a `get_db` dependency
- [x] 1.4 Add `app/main.py` app factory with `openapi_url="/api/openapi.json"`, `docs_url="/docs"`, the CORS middleware from settings, and `GET /healthz` (no database access)
- [x] 1.5 Configure ruff (lint + format) in `pyproject.toml`; `uv run ruff check` and `ruff format --check` pass

## 2. Data model and migrations

- [x] 2.1 Write `app/models.py`:
  - `users`: UUID id; `email` nullable, unique; `username` unique; `first_name`; `last_name` default `''`; timestamps
  - `user_passwords`: `user_id` PK/FK with cascade; `hash`; timestamps
  - `sessions`: UUID id; `token_hash` unique; `user_id` FK with cascade and an index; `expires_at`; timestamps
- [x] 2.2 Initialise Alembic in `backend/alembic/`, with `env.py` reading `DATABASE_URL` from settings and `target_metadata` from the models
- [x] 2.3 Write the first migration: drop `user`, `account`, `session`, `verification` and `notes` (if they exist) and the `drizzle` schema, then create the three tables. Verify on the local database that still has the old tables, and on an empty one
- [x] 2.4 Confirm `alembic revision --autogenerate` produces an empty migration afterwards (models and migration agree)

## 3. Security primitives and errors

- [x] 3.1 `app/security.py`: a pwdlib argon2id `PasswordHash`; `hash_password`, `verify_password`, `dummy_verify` (module-level dummy hash); `new_token()` (`secrets.token_urlsafe(32)`) and `token_hash()` (SHA-256 hex)
- [x] 3.2 `app/errors.py`: `ApiError(status, code, message)` and handlers:
  - `ApiError` → the error shape
  - `RequestValidationError` → 400 `VALIDATION_ERROR`, details from loc/type/msg only, no input values
  - Starlette `HTTPException` → the error shape (`NOT_FOUND` for 404)
  - catch-all → logged 500 `INTERNAL`
- [x] 3.3 `app/schemas.py`:
  - a camelCase base model; `ErrorCode` enum; `ErrorResponse`; `Health`; `User` (`email: str | None`)
  - request models: `RegisterBody`, `LoginBody` (identifier/email/username validator), `UpdateUserBody` (at least one field), `ChangePasswordBody`, `ChangeEmailBody`
  - responses: `LoginResponse`, `ChangePasswordResponse`
  - the same length and format rules as today; unknown keys ignored
- [x] 3.4 `app/deps.py`: an `HTTPBearer(scheme_name="bearerAuth", auto_error=False)`-based `current_session` dependency that resolves the token hash to a non-expired session, extends `expires_at` when it was last extended more than a day ago, and raises 401 `UNAUTHORIZED` otherwise

## 4. Account service and routes

- [x] 4.1 `services/accounts.py` `register`:
  - defaults: derived username, `NULL` email, first name = username, empty last name; lowercasing
  - check taken email, then taken username (`EMAIL_TAKEN` before `USERNAME_TAKEN`)
  - insert user and password hash in one transaction, with the `IntegrityError`-by-constraint fallback
- [x] 4.2 `login`: pick email or username lookup by `@`; `dummy_verify` for unknown users; create a session; the same `INVALID_CREDENTIALS` for every failure
- [x] 4.3 `logout` (delete this session); `change_password` (verify, rehash, delete all of the user's sessions, create and return a new one); `change_email` (password check first, same-email no-op, taken → `EMAIL_TAKEN`, works for users without an email)
- [x] 4.4 `update_profile` (username/firstName/lastName; taken username → `USERNAME_TAKEN` by unique constraint) and `delete_account`
- [x] 4.5 `routers/auth.py` and `routers/users.py`:
  - explicit `operation_id`s matching today's (`register`, `login`, `getCurrentUser`, `logout`, `changePassword`, `changeEmail`, `getUser`, `updateUser`, `deleteUser`) and `healthCheck`
  - `response_model` and documented `responses` per status
  - the `/api/users/{id}` ownership check before any database access, with 404 for another user's id, an unknown id or a non-UUID
- [x] 4.6 `app/seed.py` (`python -m app.seed`): creates `NYUgrader`/`Courant2026!` (NYU Grader, no email) through `register`; exits 0 if the user already exists

## 5. OpenAPI contract

- [x] 5.1 `app/openapi.py` (`python -m app.openapi [--check]`) writes pretty-printed JSON with a trailing newline to `openapi/openapi.json`, runs without a database, and `--check` exits non-zero with a message on drift
- [x] 5.2 Make the component names match today's (`User`, `ErrorCode`, `Error`, `ValidationIssue`, `RegisterBody`, `LoginBody`, …) and give the bearer scheme the name `bearerAuth`. Regenerate `openapi/openapi.json` and review the diff against the old document
- [x] 5.3 Confirm `/docs` (Swagger UI) loads and "Authorize" with a token works

## 6. Smoke test against the new backend

- [x] 6.1 Update `scripts/api-smoke.sh`:
  - `BASE` defaults to `http://localhost:8000`
  - `sql()` uses `psql "$DATABASE_URL"` when available, else `docker compose exec db psql`
  - the hash scan uses `user_passwords.hash` and `sessions.token_hash`
  - the expired-session step updates `sessions.expires_at` by `token_hash` (`shasum -a 256`)
  - table names in the cascade and data checks are updated; the Better Auth-specific checks (`name`, `email_verified`) are removed
- [x] 6.2 Add checks: stored hashes start with `$argon2id$`; `sessions` holds the SHA-256 of the returned token but not the token itself; CORS preflight from `http://localhost:5173` is allowed and from `https://evil.example` gets no `Access-Control-Allow-Origin`; a 401 from an allowed origin carries CORS headers
- [x] 6.3 Run the smoke test against `uv run fastapi dev` until every check passes

## 7. Frontend scaffold

- [x] 7.1 Create `frontend/` with Vite (react-ts), React Router, Tailwind v4 (`@tailwindcss/vite`), the `@/` path alias, ESLint, and `@fontsource` for the fonts; add `npm run typecheck`
- [x] 7.2 Set up shadcn (`components.json`) and copy today's `src/components/ui/*` and `globals.css` theme tokens into `frontend/src`
- [x] 7.3 Add `frontend/.env.example` (`VITE_API_URL=http://localhost:8000`) and ignore `frontend/.env`
- [x] 7.4 Add `@hey-api/openapi-ts` config (input `../openapi/openapi.json`, output `src/api`, plugins: client-fetch and TanStack Query), `npm run api:generate`, and `npm run api:check` (generate to a temp dir, diff); generate and commit `src/api/`

## 8. Frontend auth and pages

- [x] 8.1 `lib/api.ts`: `client.setConfig` with `VITE_API_URL`, a request interceptor adding the bearer header from `localStorage.token`, and a response interceptor that clears the token and signals the auth context on 401
- [x] 8.2 The auth context (`user` from the `getCurrentUser` query, `signIn(token)`, `signOut()`), plus the `RequireAuth` and `PublicOnly` route components with a loading state; port `safeNext`
- [x] 8.3 A form helper that maps `VALIDATION_ERROR` details to field errors, plus human-readable messages (port of `lib/forms.ts`)
- [x] 8.4 Port the `/login` and `/register` pages (`login-form`, `signup-form`) to call the generated `login`/`register` and store the token; register then logs in; keep `next`
- [x] 8.5 Port the layout (`Brand`, header, `UserMenu` with logout calling the API and clearing the token), the `/` home page (name, @username, email if any, link to `<VITE_API_URL>/docs`) and the `Toaster`
- [x] 8.6 Port the `/account` cards: profile (PATCH), email (change-email, "no email yet" text), password (change-password, store the new token), delete (dialog, DELETE, clear the token)

## 9. Frontend security and build

- [x] 9.1 A Vite build plugin that injects the CSP `<meta>` with `connect-src 'self' <VITE_API_URL>`; lint rule forbidding `dangerouslySetInnerHTML`
- [x] 9.2 `frontend/vercel.json`: SPA rewrite to `/index.html` and a `Content-Security-Policy: frame-ancestors 'none'` header
- [x] 9.3 `npm run build` and `vite preview`: sign up, log in, reload, edit the profile, change the email and password, sign out and delete in a browser with no CSP violations in the console (relax only `style-src` if Radix requires it, and note it in the design)

## 10. Remove the Next.js app

- [x] 10.1 Delete `src/`, `drizzle/`, `drizzle.config.ts`, `next.config.ts`, `next-env.d.ts`, `postcss.config.mjs`, `components.json`, `eslint.config.mjs`, the root `package.json`/`package-lock.json`, `scripts/generate-openapi.ts`, `scripts/vercel-build.sh` and the root `vercel.json`
- [x] 10.2 Remove the Next-specific files: `AGENTS.md` and its `CLAUDE.md` reference. Update `.gitignore` and `.vercelignore` for the new layout
- [x] 10.3 Trim the root `.env.example` to the `POSTGRES_*` variables

## 11. Scripts, CI and docs

- [x] 11.1 Update `scripts/db-migrate.sh` (alembic), add `scripts/db-seed.sh`, `scripts/dev-backend.sh` and `scripts/dev-frontend.sh`; all executable, strict bash, runnable from any directory
- [x] 11.2 Rewrite `scripts/start.sh`: create the three env files, `uv sync` and `npm install` if needed, db-up, migrate, seed, then run both dev servers with a trap that stops both on exit
- [x] 11.3 Rewrite `.github/workflows/ci.yml`:
  - backend job: Postgres 17 service, uv, ruff, alembic upgrade, `openapi --check`, uvicorn + `api-smoke.sh`
  - frontend job: Node, `npm ci`, `api:check`, typecheck, lint, build
- [x] 11.4 Rewrite the README:
  - what it is; prerequisites (Docker, Python 3.12+ with uv, Node 20.9+)
  - `./scripts/start.sh` and the exact per-app commands
  - env variables per file, project layout, architecture (two origins, CORS, bearer in `localStorage` and CSP), the API table
  - security decisions (argon2id, hashed tokens, 404 for other users' ids, 403 for a wrong current password), the test account
- [x] 11.5 Verify on a fresh clone: `./scripts/start.sh` brings up both apps; register and log in through the UI; `api-smoke.sh` passes; data survives restarting the database and the backend

## 12. Deployment (after the backend host is decided, see design Open Questions)

- [x] 12.1 Create a Neon snapshot branch of `production` for rollback
- [ ] 12.2 Configure the backend deployment: `DATABASE_URL` (pooled), `DATABASE_URL_UNPOOLED`, `CORS_ORIGINS` = the frontend URL, and a deploy step running `alembic upgrade head` on the direct URL
- [ ] 12.3 Re-point the existing Vercel project at `frontend/` (framework Vite) with `VITE_API_URL` = the backend URL
- [ ] 12.4 Merge, verify production (`/healthz`, register, login, `/docs`, CORS from the frontend origin), and seed `NYUgrader` in production only if requested
