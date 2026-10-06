## Context

`tracker.yml` runs the tracker and publishes its report. Its `schedule` trigger (`17 9 * * *`, earlier `0 9 * * *`) has been on `master` since 2026-10-04, and GitHub has never created a `schedule` run from it: `GET /actions/runs?event=schedule` returns 0. What we checked:

- the workflow's state is `active`, and Actions are enabled with all actions allowed;
- the repository is public, not a fork, and `master` is the default branch;
- both commits that set the cron (#16, #21) resolve to the owner's account (`Kildrese`), so the scheduled actor exists;
- `workflow_dispatch` on the same file works (4 successful runs).

GitHub documents `schedule` as best effort, and people report crons that never register until something "wakes" the repository ([community #202602](https://github.com/orgs/community/discussions/202602)). Re-committing the cron in #21 was that wake-up, and the next slot was still skipped. We can't fix GitHub's scheduler, so we stop depending on it.

The API has no route that starts a run, by design, and that stays true.

## Goals / Non-Goals

**Goals:**
- One run a day without anyone clicking anything.
- A missed day is noticed the same day.
- No new code, service or secret in our own stack.

**Non-Goals:**
- An endpoint in our backend that starts a run.
- Catching up on missed days, or retrying a failed run automatically. A failed run is investigated, as today.
- Moving the tracker off GitHub Actions.

## Decisions

### D1. An external cron calls `workflow_dispatch`

The cron service sends, once a day at 09:17 UTC:

```
POST https://api.github.com/repos/Kildrese/mobile-systems-assignment/actions/workflows/tracker.yml/dispatches
Authorization: Bearer <fine-grained PAT>
Accept: application/vnd.github+json
X-GitHub-Api-Version: 2022-11-28

{"ref": "master"}
```

GitHub answers `204`, and the run is the same job as a manual run.

Alternatives:
- **Keep waiting on `schedule`, or re-commit the cron again.** It already failed twice, and we only find out by looking.
- **A scheduled GitHub workflow in another repository that dispatches this one.** It depends on the same scheduler.
- **Vercel Cron, a Neon Function trigger or a Claude scheduled routine.** Each works, but each needs a small piece of code and puts the same token in another place. Vercel Cron would also need a route in our app that starts a run, which we don't want.
- **cron-job.org (chosen).** It is free and has nothing to deploy. It can send a POST with headers and a JSON body, and emails on failure. Its one cost is that the setup lives outside the repository, so `docs/deployment.md` records it step by step.

### D2. Remove `schedule` from the workflow

If GitHub's scheduler starts working one day, keeping both triggers would mean two runs a day. The concurrency group would make the second wait, not overlap. It would still cost a second Scout (6 Tavily credits, about 47,000 gpt-oss-120b tokens), write a near-empty second report, and make "New since last run" compare with a run from the same morning. One trigger, one run.

Alternative: keep `schedule` as a backup and skip a run when one already succeeded that day. That needs a step that queries the Actions API and has its own failure modes, to cover a scheduler that has never fired.

### D3. A fine-grained token, scoped to this repository

The token is a fine-grained personal access token with **Repository access: only `mobile-systems-assignment`** and **Permissions: Actions: read and write** (Metadata: read is added automatically). That is the least GitHub allows for `workflow_dispatch`. It expires after at most a year. A classic token with `repo` scope would grant write access to every repository the owner has.

The token is stored only in the cron service's job settings. It never goes into the repository or into GitHub secrets, since nothing in GitHub uses it.

### D4. How a missed day is noticed

- **The dispatch fails** (expired token, GitHub outage): cron-job.org treats any non-2xx answer as a failure and emails the owner.
- **The run fails:** GitHub emails the token's owner, who is the actor of a dispatched run, as it does today for manual runs.
- **The cron service itself doesn't fire:** nothing alerts. The frontend shows the newest run's time, so a stale date is visible. Watching for that is out of scope (see Open Questions).

## Risks / Trade-offs

- [The token leaks from the cron service] → It can only start, cancel, re-run or delete workflow runs and read their logs in this one repository. Logs never contain the API keys, since Actions masks secrets. The worst case is extra runs, which the concurrency group serializes and Groq/Tavily budgets cap. Revoke the token in GitHub settings to stop it.
- [The token expires and runs stop] → The first failed dispatch triggers cron-job.org's email. `docs/deployment.md` puts rotation in the expiry month.
- [The setup isn't in the repository] → `docs/deployment.md` lists the exact request, schedule and token settings, so anyone with owner access can recreate it in a few minutes.
- [cron-job.org has an outage] → That day is skipped. A manual run from the Actions tab is the fallback, as today.

## Migration Plan

1. The owner creates the fine-grained token (D3).
2. The owner creates the cron-job.org job (D1) and runs it once with "Test run". Expect `204` and a new `workflow_dispatch` run in the Actions tab.
3. Merge the workflow change that removes `schedule`, with the docs.
4. The next morning, check that a run started at about 09:17 UTC by the token's owner.

Rollback: disable the cron job and put the `schedule` block back.

`complete-daily-runs` also modifies the "Daily scheduled run" requirement (the job-timeout clause). Its text is carried over unchanged in this change's delta. Archive `complete-daily-runs` first so the two don't overwrite each other.

## Open Questions

- Should a stale run (no new run for over 26 hours) raise an alert? Not needed for one run a day while the owner checks the app daily. Revisit if that changes.
