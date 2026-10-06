## 1. Database

- [ ] 1.1 Add `TrackerDispatch` to `backend/app/models.py`: `day` (date, primary key), `status`, `claimed_at`, `attempts`, `error` (design D3)
- [ ] 1.2 Add an Alembic migration creating `tracker_dispatches`, with a check constraint on `status` in (`claimed`, `dispatched`, `failed`); `alembic check` is clean

## 2. Dispatch route

- [ ] 2.1 Add optional settings `cron_secret` and `github_dispatch_token` to `app/config.py`, and both (empty) to `backend/.env.example`
- [ ] 2.2 Add `app/routers/internal.py` with `GET /api/internal/tracker-dispatch`, `include_in_schema=False`: constant-time `CRON_SECRET` check, raising the API's normal `404` on any mismatch or when the secret is unset (design D2)
- [ ] 2.3 Claim the UTC date with the single `INSERT … ON CONFLICT … DO UPDATE … WHERE … RETURNING` statement, committed before the GitHub call; no row back → `200` `{"status": "already_dispatched"}`
- [ ] 2.4 Call GitHub's `workflow_dispatch` with `httpx` (10 s timeout); `204` → mark `dispatched`, `202` `{"status": "dispatched"}`; otherwise or with no token → mark `failed` with status and message, `logger.error`, `502` (design D4)
- [ ] 2.5 Include the router in `app/main.py`
- [ ] 2.6 Update the comments in `app/routers/internships.py` and `app/publish_report.py`: no user can start a run; the cron-only dispatch route is the exception

## 3. Tests (`backend/tests/test_tracker_dispatch.py`, GitHub faked with `respx`)

- [ ] 3.1 No header, wrong secret, a signed-in user's token, and no `CRON_SECRET` configured each get `404` with the unknown-path body; GitHub is not called and no row is written
- [ ] 3.2 First call: `202`, one GitHub request with `{"ref": "master"}` and the token, row `dispatched`; second call: `200` `already_dispatched`, no second GitHub request
- [ ] 3.3 GitHub `401`: `502`, row `failed` with `401`; the next call claims again (`attempts` 2) and dispatches
- [ ] 3.4 A `claimed` row older than 5 minutes is claimed again; one younger than 5 minutes is not
- [ ] 3.5 Two concurrent calls on separate connections (threads) on an empty table: exactly one GitHub request
- [ ] 3.6 The OpenAPI document has no `/api/internal` path; the existing OpenAPI check and frontend client check still pass unchanged

## 4. Schedule and workflow

- [ ] 4.1 Add `backend/vercel.json` with the cron `{"path": "/api/internal/tracker-dispatch", "schedule": "0 9 * * *"}`, and check on a preview deploy that Vercel still detects the FastAPI app with this file present
- [ ] 4.2 Remove the `schedule` block from `.github/workflows/tracker.yml` and rewrite its header comment (dispatched daily by the backend's Vercel cron; manual runs use the same trigger)

## 5. Docs

- [ ] 5.1 `docs/deployment.md`: the backend's new env vars, the cron, the token settings and how to rotate it, the migrate-first order, and how to check a day (`gh run list -w tracker.yml`, the `tracker_dispatches` row)
- [ ] 5.2 `docs/agent-loop.md` diagram and any other text that says the scheduled job or GitHub's schedule starts the run, or that no route can start one

## 6. Rollout (repository owner)

- [ ] 6.1 Create the fine-grained token: only `mobile-systems-assignment`, Actions read and write, expiry at most a year
- [ ] 6.2 Set `CRON_SECRET` and `GITHUB_DISPATCH_TOKEN` on the Vercel backend project (Production)
- [ ] 6.3 Apply the migration to Neon, then merge and deploy
- [ ] 6.4 Call the route once with the secret: `202` and a new run in the Actions tab; a second call returns `already_dispatched`
- [ ] 6.5 The next morning: a run started between 09:00 and 10:00 UTC, and that day's row is `dispatched`
