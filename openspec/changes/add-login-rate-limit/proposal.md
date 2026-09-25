## Why

`POST /api/auth/login` accepts unlimited attempts. argon2id makes each guess expensive for us, not for an attacker, who can guess one account's password indefinitely or spray a common password across many usernames. Every wrong guess also costs the server a 64 MiB argon2 verify, so unthrottled login is a cheap way to exhaust the backend.

## What Changes

- Failed logins are counted per **username** (lowercased) and per **client IP**. Each counter uses **exponential backoff**: after a failure, that key is locked for a wait that doubles with each further failure (1 s, 2 s, 4 s, … capped at 15 minutes).
- While a key is locked, `POST /api/auth/login` responds **`429 RATE_LIMITED`** with a `Retry-After` header, without looking up the user or verifying the password.
- Unknown usernames are counted and locked exactly like existing ones, so a `429` never reveals whether an account exists.
- A successful login resets the username's counter. Counters are forgotten after an hour without failures.
- Counters live in a new Postgres table, `login_throttles`, so the limit holds across Vercel instances. Keys are stored as SHA-256 hashes, never as typed usernames or raw IPs.
- CORS exposes `Retry-After` so the frontend can read it; the login form shows "Too many attempts. Try again in N seconds."

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `user-auth`: a new login rate-limiting requirement; login can now answer `429 RATE_LIMITED`.
- `api-docs`: the login operation documents `429`, and `ErrorCode` includes `RATE_LIMITED`.
- `web-auth-ui`: the login form handles `429`.

## Impact

- **Backend:** new model and migration (`login_throttles`), a throttle module (`app/throttle.py`), `app/services/accounts.py` (`login`), `app/routers/auth.py` (the `429` response and client IP), `app/errors.py`, `app/schemas.py` (`ErrorCode`), `app/main.py` (CORS `expose_headers`), `app/config.py` (new settings).
- **Contract:** `openapi/openapi.json` and the generated client in `frontend/src/api/`.
- **Frontend:** `components/auth/login-form.tsx`.
- **Tests:** backend tests for each scenario; the tests reset or bypass the throttle so existing login tests are unaffected.
- **Operations:** one migration to run on Neon (additive: migrate first, then deploy). One new optional environment variable on the backend project (`TRUST_FORWARDED_FOR`, see design).
