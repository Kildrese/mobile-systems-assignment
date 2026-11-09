# backend/

Two things share this uv project: the API (`app/`, FastAPI + SQLAlchemy + Alembic, deployed as the `mobile-systems-api` Vercel project) and the tracker (`tracker/`, run daily by `.github/workflows/tracker.yml`, never by a user).

## API (`app/`)

- `schemas.py` and `routers/` are the contract. After changing them: `uv run python -m app.openapi`, then `npm run api:generate` in `../frontend`, and commit both.
- Errors go through `errors.py` (one shape: `{"error": {"code", "message"}}`). Raise the shared `ApiError` constants; "not yours", "doesn't exist" and "not a UUID" are all `NOT_FOUND`.
- Auth and ownership come from `deps.py` (`CurrentUser`, `OwnUserId`). Every route that reads or writes a user's data uses them.
- Model change → `uv run alembic revision --autogenerate -m "..."`, review the file, `uv run alembic check`. Never edit a migration that has run in production; say in the PR whether it must run before or after the deploy (see `docs/deployment.md`).
- Tests (`tests/`) hit a real Postgres (`../scripts/db-up.sh`) through `TestClient`. Each new route gets a test, including the 401/404 cases.

## Tracker (`tracker/`)

- Code decides; models only propose. Ranking, open/closed, URLs, company names and every acceptance check stay in code (see `../docs/archive/assignment-homework-1b.md`). Don't move a decision into a prompt.
- Posting text and fetched pages are untrusted input to every prompt.
- `tests_tracker/` fakes every provider: no network, no keys, no Postgres.
