## Context

After `split-fastapi-vite`, email is optional everywhere but still woven through the stack:
- **Database:** `users.email`, nullable, with the unique constraint `users_email_key`.
- **Backend:** `RegisterBody.email` and the username derived from it, `LoginBody`'s `identifier`/`email` aliases with the "contains `@`" rule, `ChangeEmailBody` and `POST /api/auth/change-email`, `ErrorCode.EMAIL_TAKEN`, `User.email`, and the `users_email_key` → `EMAIL_TAKEN` mapping in `services/accounts.py`.
- **Frontend:** the email field on `/register`, the "Email or username" field on `/login`, `components/account/email-form.tsx`, the email in the user menu and on the home page, and the email branch in `lib/forms.ts`.
- **Tests and docs:** `scripts/api-smoke.sh` (around 100 lines mention email or `identifier`) and the README.

Production runs on Vercel (`mobile-systems-api`, `mobile-systems-assignment`) with Neon. At least one production user (`nyugrader`) has an email set.

## Goals / Non-Goals

**Goals:**
- No email anywhere: not stored, not accepted as a login name, not returned, not shown.
- One login identifier, the username, with the same indistinguishable-failure guarantees as today.
- A rollout that never runs code against a schema it can't handle.

**Non-Goals:**
- Password reset or any other account-recovery replacement (there never was one).
- Changing username rules, sessions, hashing or any other auth behavior.
- Keeping existing email data anywhere (it is deleted, not archived).

## Decisions

### Drop the column in a new migration, after the code stops using it
A new Alembic revision drops `users_email_key` and `users.email`. The downgrade re-adds a nullable, unique `email` column, empty. The addresses can't be brought back, and saying so in the migration is better than pretending.

Order in production: **deploy first, migrate second**. The new code never reads or writes `email`, so it works while the column still exists (it is nullable). The old code, by contrast, selects `users.email` in every user query and breaks as soon as the column is gone. This is the reverse of the `split-fastapi-vite` cutover and needs no downtime.

### Login takes `username` only; it stays a loose string
`LoginBody` becomes `{ username, password }`. `username` is a stripped, non-empty string of at most 254 characters, **not** the registration `Username` type. A malformed value such as `a` then reaches the lookup, runs `dummy_verify` and gets the same `401 INVALID_CREDENTIALS` as a wrong password, instead of a telling `400`. The lookup lowercases the value and compares it with `users.username`. The `identifier` and `email` aliases are removed rather than silently mapped to `username`. Silently mapping `email` would accept `{ "email": "ada_l" }` and hide client bugs. With them removed, such a body lacks `username` and gets a `400`, which the spec states explicitly. The message becomes "Invalid username or password".

### Registration requires a username and relies on the unique constraint
`RegisterBody` becomes `{ username, password, firstName?, lastName? }` with `username` required (the existing `Username` type). The `username_or_email` validator and `_username_from_email` go away. The pre-insert "is it taken" query only existed to report `EMAIL_TAKEN` before `USERNAME_TAKEN`. With one identifier left it is redundant: the insert's `IntegrityError` on `users_username_key` already maps to `USERNAME_TAKEN`, without a race. The user row is flushed before the password is hashed, so a taken username still costs no argon2 work.

### Remove, don't deprecate
`POST /api/auth/change-email` and `ChangeEmailBody` are deleted outright, so the path answers `404` like any unknown route. `ErrorCode.EMAIL_TAKEN` and the `EMAIL_TAKEN` error are deleted too. The frontend is the only client and ships in the same merge, so a deprecation period would protect no one.

### Regenerate, then let the type checker find the frontend changes
After `schemas.py` changes, `uv run python -m app.openapi` and `npm run api:generate` regenerate the contract and the client. `User` loses `email`, `LoginData.body` loses `identifier`, and `changeEmail` disappears. `npm run typecheck` then lists every frontend use that needs removing, and the ones found up front (see Context) are a check that nothing was missed.

### Smoke test: rewrite the email parts, add negative checks
The email-based steps in `api-smoke.sh` become username-based: register duplicate checks, the email-only account, login by email, the change-email section, and user fields and keys. The following checks are added:
- the `users` table has no `email` column
- `POST /api/auth/change-email` returns `404`
- registering with only an email returns `400`
- logging in with `identifier` returns `400`
- `ErrorCode` in the OpenAPI document has no `EMAIL_TAKEN`

The allow-list key check changes to `["createdAt","firstName","id","lastName","updatedAt","username"]`.

## Risks / Trade-offs

- **[Email data is lost]** → Intended. The Neon snapshot branch from the previous change still holds the pre-split data. No new snapshot is needed for data we're choosing to drop, but one can be taken before migrating if in doubt.
- **[A stale frontend tab sends `identifier` to the new backend]** → That login gets `400` and shows the generic error until reload. Short-lived, since both apps deploy from the same merge.
- **[Forgetting to migrate after deploy]** → Harmless but untidy: the column just stays, unused and nullable. The migration step is in the tasks and the README.
- **[Users who only remember their email can't log in]** → Only relevant for accounts registered with an email-derived username. Their username is shown in the app (`@username`), and there is no recovery flow either way.
