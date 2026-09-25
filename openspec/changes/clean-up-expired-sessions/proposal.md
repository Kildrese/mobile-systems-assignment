## Why

Expired sessions are never deleted. Every login adds a `sessions` row, and a row whose `expires_at` has passed stays forever unless the user logs out, changes their password or deletes their account. The table only grows, and it keeps token hashes around longer than they are useful.

## What Changes

- A successful `POST /api/auth/login` deletes the user's sessions whose `expires_at` is in the past, in the same transaction that creates the new session.
- Nothing else changes: the API, the responses and the other sessions of the user stay as they are.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `user-auth`: adds a requirement that logging in removes the user's expired sessions.

## Impact

- **Backend:** `app/services/accounts.py` (`login`). No migration: `sessions.user_id` is already indexed.
- **Tests:** `backend/tests/test_login.py`.
- **Not covered:** expired sessions of users who never log in again. A periodic cleanup (e.g. a scheduled job) can be added later if the table grows anyway.
