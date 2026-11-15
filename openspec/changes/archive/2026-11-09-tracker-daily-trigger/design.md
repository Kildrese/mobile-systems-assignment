## Context

`tracker.yml` runs the tracker and publishes its report. Its `schedule` trigger (`17 9 * * *`, earlier `0 9 * * *`) has been on `master` since 2026-10-04, and GitHub has never created a `schedule` run from it: `GET /actions/runs?event=schedule` returns 0. What we checked:

- the workflow's state is `active`, and Actions are enabled with all actions allowed;
- the repository is public, not a fork, and `master` is the default branch;
- both commits that set the cron (#16, #21) resolve to the owner's account (`Kildrese`), so the scheduled actor exists;
- `workflow_dispatch` on the same file works (4 successful runs).

GitHub documents `schedule` as best effort, and people report crons that never register ([community #202602](https://github.com/orgs/community/discussions/202602)). Re-committing the cron in #21 didn't help. We stop depending on GitHub's scheduler.

The backend is FastAPI on Vercel (project `mobile-systems-api`, root `backend/`), with Neon Postgres and Alembic migrations. Until now no API route could start a run. The owner has agreed to relax that rule to "no user can start a run", which allows a route that only the cron can reach.

## Goals / Non-Goals

**Goals:**
- One run a day without anyone clicking anything, scheduled from config in this repository.
- No user, signed in or not, can start a run through the API.
- A duplicate cron call never starts a second run.
- A failed dispatch leaves a record that says why.

**Non-Goals:**
- Retrying automatically within the day, or catching up on missed days. Vercel calls the cron once; a manual run from the Actions tab covers a failed day.
- Deduplicating manual runs. A writer who starts one from the Actions tab means it.
- Alerting on a missed day (see Open Questions).

## Decisions

### D1. Vercel Cron calls an internal route

`backend/vercel.json`:

```json
{ "crons": [{ "path": "/api/internal/tracker-dispatch", "schedule": "0 9 * * *" }] }
```

Vercel sends `GET` to the path on the production deployment, with `Authorization: Bearer $CRON_SECRET`. On the Hobby plan a daily cron fires anywhere between 09:00 and 09:59 UTC ([Vercel docs](https://vercel.com/docs/cron-jobs/usage-and-pricing)), which is fine for a daily report.

Alternatives: cron-job.org (no code, but the schedule and the token live in a third-party dashboard, and that adds an account); a Neon Function trigger (new runtime and deploy path for one call); keep waiting on GitHub's `schedule` (failed twice, silently).

### D2. Only the cron can reach the route

- The route reads `Authorization`, strips `Bearer `, and compares it with `CRON_SECRET` using `secrets.compare_digest`. A missing or empty `CRON_SECRET` rejects everything, so a local or preview deployment without the secret has no reachable route.
- Every rejection is `404` with the API's usual not-found body. A user can't tell the route from a path that doesn't exist.
- User session tokens are never looked up: the route doesn't use `CurrentSession`, so a valid user token is just a wrong secret.
- `include_in_schema=False` keeps it out of `/api/openapi.json`, the docs page, the OpenAPI check and the generated frontend client.

Alternative: return `401` for a bad secret. That says the route exists, and nothing legitimate needs to know.

### D3. Claim the day in Postgres before calling GitHub

Table `tracker_dispatches`:

| Column | Type | Notes |
| --- | --- | --- |
| `day` | `date` | primary key, the UTC date |
| `status` | `text` | `claimed`, `dispatched` or `failed` |
| `claimed_at` | `timestamptz` | when the current claim was taken |
| `attempts` | `int` | how many calls claimed this day |
| `error` | `text`, null | GitHub's status and message for a failure |

The claim is one statement, so Postgres's row lock on the primary key makes it atomic:

```sql
INSERT INTO tracker_dispatches (day, status, claimed_at, attempts)
VALUES (:day, 'claimed', now(), 1)
ON CONFLICT (day) DO UPDATE
   SET status = 'claimed', claimed_at = now(), attempts = tracker_dispatches.attempts + 1, error = NULL
 WHERE tracker_dispatches.status = 'failed'
    OR (tracker_dispatches.status = 'claimed' AND tracker_dispatches.claimed_at < now() - interval '5 minutes')
RETURNING attempts
```

A row back means this call owns the day and calls GitHub. No row back means another call already has it, and the route answers `already_dispatched`. Two simultaneous calls serialize on the key, and the second sees the first's row. The claim is committed before the GitHub call, so the lock isn't held during the network request.

- **`failed` can be claimed again**, so a manual re-call of the route (or a second Vercel call) after a GitHub error isn't blocked for the rest of the day.
- **A `claimed` row older than 5 minutes can be claimed again.** That covers a function that died between the claim and the GitHub answer. The GitHub call times out after 10 s, well inside 5 minutes, so a live call is never overtaken.

Alternatives:
- **Ask GitHub whether a tracker run already started today, then dispatch.** Two calls can both see "none" and both dispatch. The check and the action aren't atomic, and GitHub can't make them so.
- **A Postgres advisory lock.** It stops two calls at the same moment, but not a duplicate an hour later, and leaves no record.
- **Rely on the workflow's concurrency group.** It queues the second run; it doesn't cancel it.

### D4. The GitHub call

`httpx.post` to `https://api.github.com/repos/Kildrese/mobile-systems-assignment/actions/workflows/tracker.yml/dispatches`, body `{"ref": "master"}`, headers `Authorization: Bearer $GITHUB_DISPATCH_TOKEN`, `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`, timeout 10 s. The repository and workflow are constants in the router. They never change, so they're not settings.

`204` → `dispatched`, answer `202`. Anything else → `failed` with `"<status>: <GitHub's message>"` (never the request headers), `logger.error`, answer `502`. A `502` shows as a failed cron invocation in Vercel's cron and runtime logs.

The token is a fine-grained personal access token: **repository access only `mobile-systems-assignment`, permission Actions: read and write**, expiring after at most a year. That is the least GitHub allows for `workflow_dispatch`. It lives only in the Vercel project's Production env, next to `DATABASE_URL`.

### D5. Remove `schedule` from the workflow

If GitHub's scheduler starts working one day, it would add a second daily run that the claim table can't see, because GitHub would start it directly. One trigger, one run.

## Risks / Trade-offs

- [`CRON_SECRET` leaks] → Whoever holds it can call the route, but the claim table still allows one dispatch a day, so the worst case is the run we wanted anyway. Rotate it in Vercel's env settings.
- [`GITHUB_DISPATCH_TOKEN` leaks] → It can start, cancel, re-run or delete workflow runs and read logs in this one repository. Logs don't contain the API keys (Actions masks secrets). Revoke it in GitHub.
- [The token expires and dispatches fail] → Each day gets a `failed` row with `401`, and Vercel's logs show a failed cron. Nobody is emailed (Vercel Hobby doesn't alert on cron failures). Mitigation: the docs put token rotation in the expiry month. The app shows the newest run's date, so a stale report is visible.
- [Vercel skips a day] → No row for that date. A manual run from the Actions tab covers it.
- [Vercel invokes the cron twice] → The second call gets `already_dispatched`. This is the case D3 exists for.
- [Clock edge at midnight UTC] → The cron fires between 09:00 and 09:59 UTC, nowhere near a date change.

## Migration Plan

1. The owner creates the fine-grained token (D4).
2. Set `CRON_SECRET` (random, at least 16 characters) and `GITHUB_DISPATCH_TOKEN` on the Vercel backend project, Production only.
3. Apply the migration to Neon (`./scripts/db-migrate-neon.sh`), then merge. Order: migrate first, since the new code needs the table.
4. After the deploy, call the route once by hand with the secret (`curl -H "Authorization: Bearer $CRON_SECRET" https://<api>/api/internal/tracker-dispatch`). Expect `202` and a new run in the Actions tab. A second call returns `already_dispatched`. Delete that day's row afterwards if the next day's test should start clean (not needed: the cron runs the next day anyway).
5. The next morning, check that a run started between 09:00 and 10:00 UTC and that its row is `dispatched`.

Rollback: remove the cron from `backend/vercel.json` (or unset `CRON_SECRET`, which turns the route into a `404`) and put the `schedule` block back in `tracker.yml`.

`complete-daily-runs` and `show-run-history` modify the same requirements ("Daily scheduled run", "The API cannot start the tracker"). Their text is carried over unchanged in this change's deltas. Archive them first.

## Open Questions

- Should a missed day alert someone (for example a GitHub issue opened by the route on `failed`, or a check in the app for "no run in 26 hours")? Left out until a missed day actually goes unnoticed.
