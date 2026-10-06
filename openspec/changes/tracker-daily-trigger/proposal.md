## Why

The daily tracker has never run on its own. `tracker.yml` has had a `schedule` trigger on `master` since 2026-10-04, but GitHub has created 0 `schedule` runs in this repository: the 2026-10-05 09:00 and 2026-10-06 09:17 slots were skipped without a trace, and all 4 production runs were started by hand (`workflow_dispatch`). Nothing on our side explains it (the workflow is `active`, the repo is public, the cron's last editor resolves to the owner's account), and re-committing the cron in #21 didn't help. GitHub's scheduler is best effort, so a daily report that depends on it can silently stop.

## What Changes

- **An external daily cron starts the run.** A cron service calls GitHub's REST endpoint `POST /repos/{owner}/{repo}/actions/workflows/tracker.yml/dispatches` with `ref: master` once a day at 09:17 UTC. It authenticates with a fine-grained personal access token limited to this repository and to Actions read and write.
- **BREAKING (operations):** the `schedule` trigger is removed from `tracker.yml`, so GitHub's scheduler can't start a second run on a day it happens to work. `workflow_dispatch` becomes the only trigger, for the cron and for manual runs alike.
- **A missed trigger gets noticed.** The cron service emails the owner when the dispatch call fails (anything other than `204`). A run that starts and fails is reported by GitHub's usual failed-workflow email to the token's owner.
- **Still no API route starts a run.** The cron talks to GitHub, not to our backend.
- **Docs:** `docs/deployment.md` describes the trigger, the token, how to rotate it, and how to check that the day's run happened.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `report-publishing`: the "Daily scheduled run" requirement says what starts the run (an external daily dispatch at 09:17 UTC, not GitHub's `schedule`), that GitHub's scheduler can't start a second daily run, and that a failed dispatch is reported. It also corrects the stale 09:00 time.

## Impact

- **Code:** `.github/workflows/tracker.yml` (drop `on.schedule`, update the header comment). No backend, tracker or frontend code changes.
- **Outside the repo:** a cron-job.org job and a fine-grained PAT (Actions: read and write, this repository only, expiring after at most a year). Both are set up by the repository owner. The token is stored only in the cron service, never in the repository.
- **Docs:** `docs/deployment.md`.
- **Unchanged:** the job itself (state cache, exit codes, publishing, artifacts), the concurrency group, and the read-only API.
