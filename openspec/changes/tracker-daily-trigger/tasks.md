## 1. External trigger (repository owner, outside the repo)

- [ ] 1.1 Create a fine-grained PAT: repository access only `mobile-systems-assignment`, permission Actions: read and write, expiry at most one year (design D3)
- [ ] 1.2 Create a cron-job.org job: daily at 09:17 UTC, `POST https://api.github.com/repos/Kildrese/mobile-systems-assignment/actions/workflows/tracker.yml/dispatches`, headers `Authorization: Bearer <PAT>`, `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`, body `{"ref":"master"}`, failure emails on (design D1, D4)
- [ ] 1.3 Use the job's "Test run": it answers `204` and a `workflow_dispatch` run of "Internship tracker" appears in the Actions tab

## 2. Workflow

- [ ] 2.1 Remove the `schedule` block from `.github/workflows/tracker.yml`, keeping `workflow_dispatch` as the only trigger
- [ ] 2.2 Rewrite the workflow's header comment: an external cron dispatches it daily at 09:17 UTC because GitHub's `schedule` never fired here, manual runs use the same trigger, and the API still has no route that starts a run
- [ ] 2.3 Check that `gh workflow view tracker.yml` lists only `workflow_dispatch` once merged

## 3. Docs

- [ ] 3.1 `docs/deployment.md`, "Daily internship tracker": replace the scheduling sentence with the external trigger, and add the token settings, the exact request, how to rotate the token before it expires, and how to check that the day's run happened (`gh run list -w tracker.yml`)
- [ ] 3.2 Grep `README.md`, `docs/` and `AGENT.md` for "schedule", "09:00", "09:17" and "cron", and correct any text that says GitHub schedules the run

## 4. Verify

- [ ] 4.1 `openspec validate tracker-daily-trigger`
- [ ] 4.2 The morning after merging, `gh run list -w tracker.yml` shows a `workflow_dispatch` run started at about 09:17 UTC by the token's owner, and it published a report
