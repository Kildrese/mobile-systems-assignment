## Why

The app has no use for email addresses: nothing is ever sent to them (no verification, no password reset), yet they add a second login identifier, a uniqueness rule, a change-email flow and extra personal data to store. Accounts are already fully usable with a username alone, so email is removed entirely to keep the auth surface and the stored data as small as possible.

## What Changes

- **BREAKING** The `users.email` column is dropped by a new Alembic migration. Existing addresses in production are deleted with it.
- **BREAKING** `POST /api/auth/register` takes `{ username, password, firstName?, lastName? }`. `username` becomes required; `email` is no longer accepted (an `email` key is ignored like any other unknown key), and the username-from-email derivation is removed.
- **BREAKING** `POST /api/auth/login` takes `{ username, password }` only. The `identifier` and `email` aliases and the "contains `@` means email" rule are removed. The generic failure message becomes "Invalid username or password".
- **BREAKING** `POST /api/auth/change-email` is removed, and the `EMAIL_TAKEN` error code with it.
- **BREAKING** The `User` object loses `email`: its fields are `id`, `username`, `firstName`, `lastName`, `createdAt`, `updatedAt`.
- The frontend drops every email field: registration asks for names, username and password; the login field is "Username"; the account page loses the Email card; the header menu and home page no longer show an email.
- `openapi/openapi.json`, the generated frontend client, `scripts/api-smoke.sh` and the README are updated to match.
- Also corrected while touching it: the `user-management` spec still says a profile update sets a `name` column, which no longer exists.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `user-auth`: the data model loses `email`; registration requires a username and takes no email; login is by username only; the change-email requirement is removed; user objects lose `email`.
- `user-management`: the update requirement no longer mentions email (or the removed `name` column); an `email` key is now just an unknown key.
- `api-docs`: the documented endpoints no longer include change-email, and the `User` schema has no `email`.
- `web-auth-ui`: login by username, registration without email, no email in the header menu or on the home page, and the change-email card is removed.
- `dev-scripts`: the test-account seed no longer mentions an email.

## Impact

- **Backend:** `app/models.py`, a new migration in `alembic/versions/`, `app/schemas.py` (`User`, `RegisterBody`, `LoginBody`, `ChangeEmailBody`, `ErrorCode`), `app/services/accounts.py`, `app/routers/auth.py`, `app/errors.py`, `app/seed.py`.
- **Frontend:** `src/api/` (regenerated), `components/auth/login-form.tsx` and `signup-form.tsx`, `components/account/email-form.tsx` (deleted) and the account page, `components/layout/user-menu.tsx`, the home page, `lib/forms.ts`.
- **API clients:** anything that sends `identifier` or `email` to login, registers with only an email, or calls change-email breaks. The only client is this repository's frontend, which changes in the same release.
- **Data:** production loses all stored email addresses when the migration runs. There is no other use of them.
- **Tests and docs:** `scripts/api-smoke.sh`, `openapi/openapi.json`, the README.
