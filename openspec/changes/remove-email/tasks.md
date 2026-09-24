## 1. Worktree setup

- [x] 1.1 Create the env files for this worktree with a separate database: copy `.env.example` to `.env` with `POSTGRES_PORT=5433`, `backend/.env.example` to `backend/.env` with `DATABASE_URL=postgresql://postgres:postgres@localhost:5433/app`, and `frontend/.env.example` to `frontend/.env`. Port 5432 is taken by the main checkout's database; Docker Compose names this one `mobilesystems-remove-email`, so the two never share data
- [x] 1.2 Run `./scripts/start.sh` once (installs dependencies, starts the database on 5433, migrates, seeds), stop it, and confirm `./scripts/api-smoke.sh` passes against the backend before any change, as a baseline

## 2. Backend: data model and migration

- [x] 2.1 Remove `email` from `User` in `backend/app/models.py`
- [x] 2.2 Generate a migration (`uv run alembic revision --autogenerate -m "drop users.email"`), check that it drops `users_email_key` and `users.email`, and make `downgrade()` re-add a nullable unique `email` column with a comment that the data can't be restored
- [x] 2.3 Apply it locally (`./scripts/db-migrate.sh`), then confirm `uv run alembic check` reports no changes and `users` has no `email` column

## 3. Backend: API

- [x] 3.1 `app/schemas.py`: remove `email` from `User`; make `RegisterBody` `{ username (required, Username type), password, first_name?, last_name? }` and delete the `username_or_email` validator; make `LoginBody` `{ username (stripped, 1–254 characters, not the Username type), password }` and delete the aliases, `login_identifier` and its validator; delete `ChangeEmailBody` and `ErrorCode.EMAIL_TAKEN`; drop the `Email` alias and the `EmailStr` import if unused
- [x] 3.2 `app/errors.py`: delete `EMAIL_TAKEN`; change the `INVALID_CREDENTIALS` message to "Invalid username or password" and its comment
- [x] 3.3 `app/services/accounts.py`: remove `_username_from_email`, the email handling and the pre-insert "taken" query in `register` (the `users_username_key` → `USERNAME_TAKEN` mapping covers it); make `login` look up `users.username == body.username.lower()` only; delete `change_email`; drop `EMAIL_TAKEN` from `_TAKEN` and the imports
- [x] 3.4 `app/routers/auth.py`: delete the change-email route; update the register `409` description ("The username is already taken.") and the login `401` description ("Unknown username or wrong password (indistinguishable).")
- [x] 3.5 Check `app/seed.py` still works (`uv run python -m app.seed` on the migrated database)
- [x] 3.6 `uv run ruff check` and `uv run ruff format --check` pass; `grep -rni email backend/app` finds nothing

## 4. Contract

- [x] 4.1 Regenerate `openapi/openapi.json` (`uv run python -m app.openapi`) and review the diff: no `change-email` path, no `ChangeEmailBody`, no `email` in `User` or `RegisterBody`, `LoginBody` is `{ username, password }`, `ErrorCode` has no `EMAIL_TAKEN`
- [x] 4.2 Regenerate the frontend client (`npm run api:generate` in `frontend/`) and confirm `npm run api:check` passes

## 5. Frontend

- [x] 5.1 `components/auth/login-form.tsx`: a "Username" field (`id`/`name` `username`, `autoComplete="username"`, `maxLength` 254), send `{ username, password }`, and show "Invalid username or password"
- [x] 5.2 `components/auth/signup-form.tsx`: remove the email field and the `EMAIL_TAKEN` branch; send `{ firstName, lastName, username, password }`; log in with `{ username, password }`
- [x] 5.3 Delete `components/account/email-form.tsx` and remove it from the account page in `routes/pages.tsx`
- [x] 5.4 Remove the email from the user menu (`components/layout/user-menu.tsx`) and from the home page (`routes/pages.tsx`)
- [x] 5.5 `lib/forms.ts`: drop the email-specific `value_error` message
- [x] 5.6 `npm run typecheck`, `npm run lint` and `npm run build` pass; `grep -rni "email\|identifier" frontend/src --exclude-dir=api` finds nothing

## 6. Smoke test

- [x] 6.1 Rewrite the email-based steps of `scripts/api-smoke.sh` for usernames: register (success, duplicate username in another case, invalid fields), the username-only account, login by username (success, wrong password, unknown and malformed usernames with identical bodies), the DB row check, and drop the change-email section. Change the user key allow-list to `["createdAt","firstName","id","lastName","updatedAt","username"]`
- [x] 6.2 Add checks: `users` has no `email` column; `POST /api/auth/change-email` returns `404`; registering with only `email` and `password` returns `400`; logging in with `identifier` returns `400`; an `email` sent to register is ignored and not returned; `ErrorCode` in the served document has no `EMAIL_TAKEN`; the OpenAPI checks no longer expect `change-email`
- [x] 6.3 Run the smoke test against the running backend until every check passes

## 7. Docs and specs

- [x] 7.1 README: remove email from the API section (register, login, the endpoint table, change-email), the Web UI table, the security decisions (login lookup, 403 on change-email) and the test account description; state that accounts have no email
- [ ] 7.2 After archiving, update the `Purpose` line of `openspec/specs/user-auth/spec.md`, which still says "login by email or username" and names the Better Auth tables (deltas can't change it)

## 8. Verify and ship

- [x] 8.1 In a browser against `npm run build` + `vite preview` (backend `CORS_ORIGINS` must include the preview origin, or preview on port 5173): register without an email, sign out, log in by username, wrong password shows "Invalid username or password", the account page has no Email card, the menu shows no email, delete the account; no console errors
- [ ] 8.2 Commit on `feat/remove-email`, push, and open a PR against `master`; CI green
- [ ] 8.3 After the PR is merged and both Vercel production deployments are ready, run `./scripts/db-migrate-neon.sh` (deploy first, migrate second, see design), then verify production: `/healthz`, register and log in by username in the live frontend, `/api/auth/change-email` returns `404`, `NYUgrader` still logs in
