# CLAUDE.md

FastAPI backend (`backend/app`), agentic tracker (`backend/tracker`), verifier and CV/cover-letter drafter services (`services/verifier`, `services/drafter`), Vite/React frontend (`frontend`). Deployed on Vercel with Neon Postgres. Setup and layout: [docs/development.md](docs/development.md). The tracker's design, as submitted for Homework 1B: [docs/archive/assignment-homework-1b.md](docs/archive/assignment-homework-1b.md).

## Commands (the same ones CI runs, see `.github/workflows/ci.yml`)

```bash
# backend/ and services/*/
uv run ruff check && uv run ruff format --check
uv run pytest                     # backend: needs Postgres (./scripts/db-up.sh); services: none
uv run pytest tests_tracker       # backend/: tracker, no Postgres, no network
uv run python -m app.openapi --check
uv run alembic check              # needs Postgres
# frontend/
npm run api:check && npm run typecheck && npm test && npm run lint
```

## Workflow

1. Features start as an OpenSpec change (`/opsx:propose`) after a grilling round; no code before it's reviewed. Small fixes skip this.
2. Work on a feature branch (or worktree), never on `master`. PR against `master`; titles say what changed in plain words ("Read the SimplifyJobs list as an internship source").
3. Before the PR: the `checker` agent runs CI's commands, then the `reviewer` (correctness vs. the OpenSpec change, plus over-engineering) and, when the diff touches auth, prompts, fetching, secrets or paid API calls, the `security-reviewer`.
4. Shipping is `/ship <PR>` in the main session, never a subagent: migration order, secrets, merge, post-deploy checks. Production migrations, GitHub secrets and the merge are the user's steps.
5. After it's live: `/opsx:archive`.

`claude --agent orchestrator` runs steps 1–3 delegated: grilling → `spec-writer` → `implementer`(s) → `checker` → `reviewer` (+ `security-reviewer`) → second grilling on the flags → fresh implementers apply the answers → draft PR. Step 4 stays yours.

## Decisions

Every decision on a change goes in `openspec/changes/<name>/decisions.md` (for a small fix, `openspec/changes/fix-<topic>/decisions.md` alone): the user's grilling answers, choices the spec-writer made, and flags raised during implementation or review. Subagents read it before working and append to it; nothing about a decision lives only in a chat.

**The user's decisions (class `mine`).** Never defaulted by a subagent:
- Anything that changes what the tracker ranks or reports: ranking weights, K, budgets, caps and thresholds in `config.yaml`, the tracker's, verifier's and drafter's model prompts, the profile. (Claude Code's `.claude/agents/` are not in this list.)
- Who can trigger a paid API call (Groq, Tavily, Anthropic), and any new path to one.
- A new pip or npm dependency, data source, job board or external service.
- Production: Neon migrations, Vercel projects and env vars, GitHub secrets and workflows' triggers, deploys, merges, emailing anyone. (Commits, pushing `feat/*`/`fix/*` and draft PRs are fine.)
- Reversing a decision recorded in `openspec/specs/` or `docs/`.

**Classes and what they trigger:**
- `mine`: stop that branch of work (commit what is done), write the entry with `status: open`, report `blocked: D<n>`. Other work continues.
- `expensive` (not the user's, but later work builds on it: module layout, a table's shape, an API contract): same stop; the orchestrator decides.
- `cheap`: pick the default, write the entry with `status: resolved`, keep going.
- Unsure between two classes: take the higher one.

Entry format:

```md
## D4 Fit weight
- class: mine              # mine | expensive | cheap
- source: implementer, task 2.1   # grilling | spec-writer | implementer | reviewer
- status: open             # open | decided (user) | resolved (orchestrator or subagent)
- question: Fit 3 lets an unrated offer outrank a rated one on 2 test fixtures. Lower it?
- options: A keep 3 / B 2 / C rate before ranking
- built: A                 # what the branch does now; never shown to the user before they choose
- decision:                # who, what, date
- landed: backend/tracker/ranking.py:40; specs/internship-pipeline#Scenario: fit
```

## Gotchas

- The repo is **public**. Never commit `private/`, `.env*` (except `.env.example`), or anything from them. A hook blocks it.
- After changing `backend/app/schemas.py` or `backend/app/routers/`: `uv run python -m app.openapi` in `backend/`, then `npm run api:generate` in `frontend/`. Never edit `frontend/src/api/` by hand.
- Model change = a new Alembic migration (`uv run alembic revision --autogenerate`). Never edit a migration that has run in production.
- `reports/` and `traces/` are ignored except run1/run2. Production runs reach the database only via the daily cron, never via an API a user can call.
- Anything that spends on a paid API (Groq, Tavily, Anthropic) must say who can trigger it.
- CI tests fake every provider; tests must not need network or secrets.
