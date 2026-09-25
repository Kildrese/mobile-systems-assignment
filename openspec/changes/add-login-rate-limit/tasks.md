## 1. Decide

- [ ] 1.1 Settle the Open Questions in `design.md` (IP allowance, settings vs constants)

## 2. Backend: data and throttle

- [ ] 2.1 Add the `LoginThrottle` model (`key` text PK, `failures`, `locked_until`, `last_failure_at`) and generate the migration; `uv run alembic check` is clean
- [ ] 2.2 `app/config.py`: `trust_forwarded_for` (default false) and the backoff settings from 1.1
- [ ] 2.3 `app/throttle.py`: key hashing, `locked_for(db, keys) -> seconds | None`, `record_failure(db, keys)` as one atomic upsert with the one-hour decay and the day-old cleanup, `reset(db, key)`
- [ ] 2.4 Client IP: the socket peer, or the first `X-Forwarded-For` entry when `trust_forwarded_for` is set

## 3. Backend: API

- [ ] 3.1 `ErrorCode.RATE_LIMITED`, an `ApiError` carrying `Retry-After`, and the error handler sending that header
- [ ] 3.2 `accounts.login`: check the lock after validation and before the user lookup; record failures for both keys; reset the username key on success
- [ ] 3.3 `routers/auth.py`: document `429` on login; `main.py`: `expose_headers=["Retry-After"]`
- [ ] 3.4 Regenerate `openapi/openapi.json` and the frontend client

## 4. Frontend

- [ ] 4.1 `login-form.tsx`: handle `RATE_LIMITED` with the `Retry-After` message, keeping the username

## 5. Tests

- [ ] 5.1 Backend tests for every `Login rate limiting` scenario, driving time by moving `locked_until` in SQL rather than sleeping
- [ ] 5.2 Make the existing login tests independent of the throttle (reset it per test)
- [ ] 5.3 Vitest for the `429` message helper, if it lives in `src/lib`

## 6. Docs and ship

- [ ] 6.1 `docs/api.md` (the `429` row, remove "no login rate limiting" from known limitations), `docs/architecture.md` (a security decision entry), `docs/deployment.md` (`TRUST_FORWARDED_FOR=true` on the backend project)
- [ ] 6.2 PR against `master`; CI green
- [ ] 6.3 Production: run the migration on Neon, set `TRUST_FORWARDED_FOR=true` on `mobile-systems-api`, then deploy; verify that repeated wrong passwords get `429` with `Retry-After`
