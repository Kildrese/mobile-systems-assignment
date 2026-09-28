## 1. Backend

- [x] 1.1 `app/services/accounts.py`: in `login`, after the password check, delete the user's sessions with `expires_at <= now()` before creating the new one, and commit both together
- [x] 1.2 `backend/tests/test_login.py`: cover the three scenarios (expired deleted, other users untouched, failed login deletes nothing)
- [x] 1.3 `uv run ruff check`, `uv run ruff format --check` and `uv run pytest` pass

## 2. Ship

- [x] 2.1 Open a PR against `master`; CI green
- [x] 2.2 After merge, archive the change (`/opsx:archive clean-up-expired-sessions`)
