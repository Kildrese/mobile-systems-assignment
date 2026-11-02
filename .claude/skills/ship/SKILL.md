---
name: ship
description: Ship a reviewed PR to production in this repo, covering Neon migration, secrets, new Vercel projects, merge and post-deploy checks. Usage /ship <PR number>.
disable-model-invocation: true
---

# Ship a PR to production

Production is the Vercel projects in `docs/deployment.md`, all connected to GitHub (a push to `master` deploys them, branches get previews), plus one Neon Postgres. **The merge is the deploy.** Never run `vercel deploy --prod`.

Steps marked **[you]** are the user's. Auto mode blocks Claude from production migrations and GitHub secret writes, and the merge is the user's decision. Give the exact `! <command>` and wait. Claude does everything else and stops at every permission prompt.

## 1. Readiness

- `gh pr view <n>` and `gh pr checks <n>`: CI and the Vercel previews must be green. If they aren't, stop and report.
- In the OpenSpec change's `tasks.md`, everything except the rollout tasks must be ticked.
- List what production needs, as a checklist:
  - **Migrations:** `git diff --name-only origin/master...HEAD -- backend/alembic/versions`
  - **Env vars and secrets:** new `Settings` fields, `os.environ` reads, `.env.example` lines, `secrets.*` in workflows.
  - **New Vercel project:** a new directory under `services/`.
  - **Tracker:** changes under `backend/tracker`, `config.yaml`, `.github/workflows/tracker.yml`.

  If the list is empty, skip to step 5.

## 2. Migration

**Order.** An additive migration (new table, column or index) runs now, **before the merge**, because the running code ignores it. A migration that drops or renames something the running code reads runs **after** the merge has deployed (step 5). If you're unsure which applies, ask. A rename is add + backfill now, then the drop in a later release.

**Pre-check (Claude), in `backend/`:**
1. `git merge origin/master`, then `uv run alembic heads` must show **one** head. Two heads means master gained a migration. Re-chain this branch's `down_revision` onto master's head, commit and push.
2. Preview offline: `uv run alembic upgrade <down_revision>:head --sql`. Summarize it for the user: tables and columns touched, and any `DROP`, `TRUNCATE`, `DELETE` or type change.
3. **Destructive SQL, or a data reset the user asks for:** push back first. Say what is lost and whether it can be recovered. Offer a rehearsal on a Neon branch (`neon-postgres-branches` skill) or a snapshot. Go on only after an explicit yes.

**[you]** `! ./scripts/db-migrate-neon.sh`. It works from a worktree and refuses to run with two heads.

**Verify:** Neon MCP `run_sql` with `SELECT version_num FROM alembic_version` must match the new head.

## 3. Secrets and env vars

- Never print a secret or put one on a command line. Generate tokens into a git-ignored file in the **main checkout** (`.env.<name>`), never into a scratchpad or temp directory. A token was lost that way once.
- **Vercel env (Claude, each write prompts):**
  - Plain values: Vercel MCP `create_project_env`.
  - Secrets: `vercel env add NAME production --sensitive --scope <team> --project <project> < file`. The repo root isn't `vercel link`ed.
  - Cron-only secrets go to production only. Add preview only when previews need the value.
- **GitHub Actions secrets [you]:** `! gh secret set NAME < file`.
- A paid API key (Groq, Tavily, Anthropic) needs two answers: who can trigger the spend, and whether a spend cap is set.
- Env changes reach production at the next deploy. If the merge already shipped, redeploy that project with the Vercel MCP (it asks first).

## 4. New Vercel project (new service only)

1. Vercel MCP `create_project` with `gitRepository` (`Kildrese/mobile-systems-assignment`) and root directory `services/<name>`. The verifier was first created without the Git link and didn't auto-deploy.
2. Then `update_project` with `sourceFilesOutsideRootDirectory: true`. Services install `packages/agentkit` from outside their root.
3. Add the project's row to the table in `docs/deployment.md`.

## 5. Merge [you]

`gh pr merge <n> --squash --delete-branch`. Claude runs it only when the user says "merge". For a destructive migration, run step 2 now, after the deploy below is green.

## 6. Verify

1. **Deploy status:** `gh api repos/Kildrese/mobile-systems-assignment/commits/<merge sha>/status`. Every Vercel context must be `success`. For a failure, read the build logs with Vercel MCP `get_deployment`.
2. **Health:** `curl -sf` each changed project:
   - API: `https://mobile-systems-api.vercel.app/healthz`
   - Frontend: `https://mobile-systems-assignment.vercel.app/`
   - Services: `/healthz` on the production domain from Vercel MCP `get_project`.
3. **Guards still hold:** new user routes answer 401 without a token, and `/api/internal/*` answers 404 without the cron secret.
4. **Runtime errors:** Vercel MCP `get_runtime_errors` for each changed project, over the last 15 minutes.
5. **Tracker touched:** offer `gh workflow run tracker.yml`. It spends Groq and Tavily quota and asks first. Then `gh run watch`, and check that a new `tracker_runs` row exists.
6. **Report:** a table of `project | deploy | health | errors | notes`.

## 7. Close out

- Tick the rollout tasks in `tasks.md`, then `/opsx:archive` in a follow-up PR.
- Update `docs/deployment.md` if projects, env vars or secrets changed.
- **Rollback:** Vercel MCP `request_rollback` restores the previous deployment instantly. A migration is never rolled back by hand: write a new forward migration.
